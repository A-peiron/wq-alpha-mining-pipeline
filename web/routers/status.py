"""
routers/status.py
-----------------
本地监控相关 API / Local monitoring APIs

数据来源 / Data sources:
  - records/simulations.jsonl — 每次模拟的详细记录 / Per-simulation detail records
  - records/submitable_alpha.csv — 本地可提交因子列表 / Local submittable alphas
  - records/events.jsonl — Web 控制台与预检事件 / Stage/control/precheck events
  - logs/digging.log / logs/check.log — 实际运行日志 / Runtime logs
"""

from __future__ import annotations

import asyncio
import csv
import json
import time
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter()

BASE = Path(__file__).parent.parent.parent
RECORDS = BASE / "records"
EVENTS_FILE = RECORDS / "events.jsonl"
DIGGING_LOG_FILE = BASE / "logs" / "digging.log"
CHECK_LOG_FILE = BASE / "logs" / "check.log"
_start_time = time.time()


def _today_bj() -> str:
    return datetime.now(tz=timezone(timedelta(hours=8))).strftime("%Y-%m-%d")


def _read_jsonl(path: Path) -> list[dict]:
    records = []
    if not path.exists():
        return records
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


@router.get("/status")
def get_status():
    events = _read_jsonl(EVENTS_FILE)
    last_event = events[-1] if events else None
    return {
        "phase": last_event.get("phase", "idle") if last_event else "idle",
        "detail": last_event.get("detail", "") if last_event else "",
        "updated_at": last_event.get("ts", "") if last_event else "",
        "last_event": last_event,
        "control_status_api": "/api/control/status",
        "server_uptime_s": round(time.time() - _start_time),
    }


@router.get("/stats")
def get_stats():
    jsonl = RECORDS / "simulations.jsonl"
    today = _today_bj()

    total = step1 = step2 = step3 = 0
    today_total = today_ok = 0
    today_pass = today_optimize = today_reject = today_unknown = 0
    today_green = today_yellow = today_red = today_dead = 0
    duration_sum = duration_count = 0
    hourly = [0] * 24
    now_ts = time.time()
    status_counter = Counter()

    if jsonl.exists():
        for line in jsonl.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue

            total += 1
            status_counter[r.get("status", "unknown")] += 1
            tag = r.get("tag", "")
            if "1step" in tag:
                step1 += 1
            elif "2step" in tag:
                step2 += 1
            elif "3step" in tag:
                step3 += 1

            if r.get("ts", "").startswith(today):
                today_total += 1
                if r.get("status") == "ok":
                    today_ok += 1
                # 质量统计（新字段，旧记录无此字段时为 unknown）
                qs = r.get("quality_status", "unknown")
                if qs == "PASS":
                    today_pass += 1
                elif qs == "OPTIMIZE":
                    today_optimize += 1
                elif qs == "REJECT":
                    today_reject += 1
                else:
                    today_unknown += 1
                sl = r.get("signal_light", "unknown")
                if sl == "GREEN":
                    today_green += 1
                elif sl == "YELLOW":
                    today_yellow += 1
                elif sl == "RED":
                    today_red += 1
                elif sl == "DEAD":
                    today_dead += 1

            dur = r.get("duration_s")
            if dur:
                duration_sum += dur
                duration_count += 1

            try:
                ts_dt = datetime.strptime(r["ts"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone(timedelta(hours=8)))
                age_h = (now_ts - ts_dt.timestamp()) / 3600
                if 0 <= age_h < 24:
                    hourly[23 - int(age_h)] += 1
            except Exception:
                pass

    submittable = 0
    sub_file = RECORDS / "submitable_alpha.csv"
    if sub_file.exists():
        try:
            with open(sub_file, encoding="utf-8", errors="replace") as f:
                submittable = max(0, sum(1 for _ in csv.reader(f)) - 1)
        except Exception:
            pass

    events = _read_jsonl(EVENTS_FILE)
    today_events = [e for e in events if e.get("ts", "").startswith(today)]
    event_counter = Counter(e.get("event", "unknown") for e in today_events)
    phase_counter = Counter(e.get("phase", "unknown") for e in today_events)
    skipped_counter = Counter()
    error_count = 0
    for event in today_events:
        if event.get("event") == "error":
            error_count += 1
        counts = event.get("counts") or {}
        for key, value in counts.items():
            if key not in ("total", "scheduled"):
                try:
                    skipped_counter[key] += int(value)
                except (TypeError, ValueError):
                    pass

    return {
        "today_simulated": today_total,
        "today_ok": today_ok,
        "today_success_rate": round(today_ok / today_total, 3) if today_total else 0,
        "avg_duration_s": round(duration_sum / duration_count, 1) if duration_count else 0,
        "step1_total": step1,
        "step2_total": step2,
        "step3_total": step3,
        "total_simulated": total,
        "status_counts": dict(status_counter),
        "submittable_count": submittable,
        "hourly_counts": hourly,
        "events_today": len(today_events),
        "event_counts": dict(event_counter),
        "phase_counts": dict(phase_counter),
        "skip_counts": dict(skipped_counter),
        "error_count": error_count,
        "recent_events": events[-20:],
        # 质量统计（依赖 simulate_single 写入 quality_status/signal_light）
        "today_pass": today_pass,
        "today_optimize": today_optimize,
        "today_reject": today_reject,
        "today_quality_unknown": today_unknown,
        "today_green": today_green,
        "today_yellow": today_yellow,
        "today_red": today_red,
        "today_dead": today_dead,
    }


@router.get("/simulations")
def get_simulations(page: int = 1, limit: int = 50, tag: str = "", status: str = ""):
    jsonl = RECORDS / "simulations.jsonl"
    records = []

    if jsonl.exists():
        for line in jsonl.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if tag and tag not in r.get("tag", ""):
                    continue
                if status and r.get("status") != status:
                    continue
                records.append(r)
            except json.JSONDecodeError:
                continue

    records.reverse()
    total = len(records)
    start = (page - 1) * limit
    return {"total": total, "page": page, "limit": limit, "items": records[start: start + limit]}


@router.get("/logs/stream")
async def stream_logs(kind: str = "digging"):
    log_file = CHECK_LOG_FILE if kind == "check" else DIGGING_LOG_FILE

    async def generator():
        waited = 0
        while not log_file.exists():
            await asyncio.sleep(2)
            waited += 2
            if waited >= 60:
                return

        with open(log_file, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            for line in lines[-200:]:
                yield f"data: {line.rstrip()}\n\n"

            while True:
                line = f.readline()
                if line:
                    yield f"data: {line.rstrip()}\n\n"
                else:
                    await asyncio.sleep(1)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/logs")
def get_logs(n: int = 100, kind: str = "digging"):
    log_file = CHECK_LOG_FILE if kind == "check" else DIGGING_LOG_FILE
    if not log_file.exists():
        return {"lines": []}
    lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    return {"lines": lines[-n:]}
