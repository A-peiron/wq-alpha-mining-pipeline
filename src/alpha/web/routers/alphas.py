"""
routers/alphas.py
-----------------
本地因子记录相关 API / Local alpha records APIs

提供以下端点 / Provides the following endpoints:
  GET /api/alphas              — 可提交因子列表（读 submitable_alpha.csv）
  GET /api/alphas/distribution — Sharpe/Fitness 分布（按 tag 分组）
  GET /api/alphas/timeline     — 近N天每日新增可提交因子数量
  GET /api/alphas/funnel       — 挖掘漏斗（模拟总数→成功→通过check）
  GET /api/alphas/top          — 按指标排序的 top 因子
  GET /api/alphas/scatter      — Sharpe/Fitness/Turnover 散点图数据

数据来源 / Data source:
  records/submitable_alpha.csv — 由 check.py 写入的通过本地检验的因子
  records/simulations.jsonl    — 所有模拟记录
"""

import csv
import json
import threading
import requests as _requests
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

router = APIRouter()

# 项目根目录 / Project root
from alpha.core.config import ROOT_PATH
BASE = Path(ROOT_PATH)
RECORDS = BASE / "records"

# submitable_alpha.csv 中需要返回给前端的关键列
# Key columns from submitable_alpha.csv to return to frontend
ALPHA_COLUMNS = [
    "id", "region", "universe", "delay", "decay",
    "sharpe", "fitness", "returns", "turnover", "margin",
    "longCount", "shortCount", "dateCreated", "color",
    "tags", "self_corr", "prod_corr", "quality_status", "signal_light",
    "quality_tier", "quality_reasons", "review_status", "review_note",
    "check_time", "code",
    "official_check_status", "fallback_used", "fallback_corr",
    "review_priority", "dsi_signal", "diagnosis_summary", "risk_flags",
    "manual_submit_decision",
]

NUM_COLS = ("sharpe", "fitness", "returns", "turnover", "margin",
            "longCount", "shortCount", "self_corr", "prod_corr", "decay",
            "review_priority")


def _load_submitable() -> list[dict]:
    """读取 submitable_alpha.csv 并做数值转换 / Load and parse submitable_alpha.csv."""
    sub_file = RECORDS / "submitable_alpha.csv"
    if not sub_file.exists():
        return []
    alphas = []
    try:
        with open(sub_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                alpha = {col: row.get(col, "") for col in ALPHA_COLUMNS}
                for num_col in NUM_COLS:
                    try:
                        alpha[num_col] = float(alpha[num_col]) if alpha[num_col] else None
                    except ValueError:
                        alpha[num_col] = None
                alphas.append(alpha)
    except Exception:
        pass
    return alphas


def _load_simulations() -> list[dict]:
    """读取 simulations.jsonl / Load simulations.jsonl."""
    sim_file = RECORDS / "simulations.jsonl"
    if not sim_file.exists():
        return []
    records = []
    try:
        with open(sim_file, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except Exception:
        pass
    return records


@router.get("/alphas")
def get_alphas():
    """
    获取本地可提交因子列表（已通过 self-corr 检验）
    Get local submittable alphas that passed the self-correlation check

    Returns a list of alpha dicts with key metrics, sorted by sharpe descending.
    按 sharpe 降序排列 / Sorted by sharpe descending.
    """
    alphas = _load_submitable()
    alphas.sort(key=lambda x: x.get("sharpe") or 0, reverse=True)
    return {"alphas": alphas, "total": len(alphas)}


@router.get("/alphas/distribution")
def get_distribution(tag: Optional[str] = Query(None, description="按 tag 过滤，逗号分隔多个")):
    """
    Sharpe / Fitness 分布（分桶统计）
    Sharpe/Fitness bucket distribution for chart rendering.
    """
    alphas = _load_submitable()

    if tag:
        tags_filter = {t.strip() for t in tag.split(",")}
        alphas = [a for a in alphas if any(t in (a.get("tags") or "") for t in tags_filter)]

    sharpe_buckets = {"<0.75": 0, "0.75-1.0": 0, "1.0-1.5": 0, "1.5-2.0": 0, ">2.0": 0}
    fitness_buckets = {"<0.5": 0, "0.5-0.75": 0, "0.75-1.0": 0, "1.0-1.5": 0, ">1.5": 0}

    for a in alphas:
        s = a.get("sharpe")
        f = a.get("fitness")
        if s is not None:
            s = abs(s)
            if s < 0.75:          sharpe_buckets["<0.75"] += 1
            elif s < 1.0:         sharpe_buckets["0.75-1.0"] += 1
            elif s < 1.5:         sharpe_buckets["1.0-1.5"] += 1
            elif s < 2.0:         sharpe_buckets["1.5-2.0"] += 1
            else:                 sharpe_buckets[">2.0"] += 1
        if f is not None:
            f = abs(f)
            if f < 0.5:           fitness_buckets["<0.5"] += 1
            elif f < 0.75:        fitness_buckets["0.5-0.75"] += 1
            elif f < 1.0:         fitness_buckets["0.75-1.0"] += 1
            elif f < 1.5:         fitness_buckets["1.0-1.5"] += 1
            else:                 fitness_buckets[">1.5"] += 1

    return {
        "total": len(alphas),
        "sharpe": sharpe_buckets,
        "fitness": fitness_buckets,
    }


@router.get("/alphas/timeline")
def get_timeline(days: int = Query(14, ge=1, le=90)):
    """
    近N天每日新增通过 check 的因子数量（折线图数据）
    Daily new submittable alphas for the past N days.
    """
    alphas = _load_submitable()
    now = datetime.now(timezone.utc)
    date_tags: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    all_tags: set[str] = set()

    for a in alphas:
        created = a.get("dateCreated", "")
        tags_str = a.get("tags", "") or ""
        if not created:
            continue
        try:
            # 支持多种日期格式
            for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(created[:19], fmt[:len(fmt)])
                    break
                except ValueError:
                    continue
            else:
                continue
            delta = (now.date() - dt.date()).days
            if 0 <= delta < days:
                date_str = dt.strftime("%Y-%m-%d")
                # 提取 step tag
                tag_label = "unknown"
                for kw in ["3step", "2step", "1step"]:
                    if kw in tags_str:
                        tag_label = kw
                        break
                date_tags[date_str][tag_label] += 1
                all_tags.add(tag_label)
        except Exception:
            continue

    # 生成连续日期序列
    dates = [(now.date() - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days - 1, -1, -1)]
    series: dict[str, list[int]] = {t: [date_tags[d].get(t, 0) for d in dates] for t in sorted(all_tags)}

    return {"dates": dates, "series": series}


@router.get("/alphas/funnel")
def get_funnel():
    """
    挖掘漏斗：模拟总次数 → 成功模拟数 → 通过 check 数
    Mining funnel: total simulated → success → passed check.
    """
    sims = _load_simulations()
    alphas = _load_submitable()

    total = len(sims)
    success = sum(1 for s in sims if s.get("status") == "ok" and s.get("alpha_id"))
    duplicated = sum(1 for s in sims if s.get("status") == "duplicated")
    passed_check = len(alphas)

    # 按 tag 分组统计
    by_tag: dict[str, dict] = defaultdict(lambda: {"total": 0, "success": 0})
    for s in sims:
        tag = s.get("tag", "unknown")
        # 统一映射到 step 级别
        label = "unknown"
        for kw in ["3step", "2step", "1step"]:
            if kw in tag:
                label = kw
                break
        by_tag[label]["total"] += 1
        if s.get("status") == "ok" and s.get("alpha_id"):
            by_tag[label]["success"] += 1

    return {
        "total": total,
        "success": success,
        "duplicated": duplicated,
        "passed_check": passed_check,
        "by_step": dict(by_tag),
    }


@router.get("/alphas/top")
def get_top(
    n: int = Query(20, ge=1, le=100),
    sort: str = Query("sharpe", description="排序字段: sharpe, fitness, turnover, self_corr"),
    tag: Optional[str] = Query(None),
):
    """
    按指标排序的 top 因子列表 / Top alphas sorted by metric.
    """
    alphas = _load_submitable()

    if tag:
        tags_filter = {t.strip() for t in tag.split(",")}
        alphas = [a for a in alphas if any(t in (a.get("tags") or "") for t in tags_filter)]

    reverse = sort not in ("turnover", "self_corr")
    alphas.sort(key=lambda x: abs(x.get(sort) or 0) if x.get(sort) is not None else 0, reverse=reverse)

    return {"items": alphas[:n], "total": len(alphas)}


@router.get("/alphas/scatter")
def get_scatter(tag: Optional[str] = Query(None)):
    """
    Sharpe / Fitness / Turnover 散点图数据
    Scatter plot data: Sharpe vs Fitness, size = Turnover.
    """
    alphas = _load_submitable()

    if tag:
        tags_filter = {t.strip() for t in tag.split(",")}
        alphas = [a for a in alphas if any(t in (a.get("tags") or "") for t in tags_filter)]

    points = []
    for a in alphas:
        s = a.get("sharpe")
        f = a.get("fitness")
        t = a.get("turnover")
        if s is None or f is None:
            continue
        tags_str = a.get("tags", "") or ""
        step_label = "unknown"
        for kw in ["3step", "2step", "1step"]:
            if kw in tags_str:
                step_label = kw
                break
        points.append({
            "sharpe": round(float(s), 4),
            "fitness": round(float(f), 4),
            "turnover": round(float(t), 4) if t is not None else None,
            "step": step_label,
            "id": a.get("id", ""),
            "code": (a.get("code") or "")[:80],  # 截断避免传输过大
        })

    return {"points": points, "total": len(points)}


# ─── 写回 CSV 辅助 ─────────────────────────────────────────────

_csv_lock = threading.Lock()


def _update_submitable_row(alpha_id: str, updates: dict) -> bool:
    sub_file = RECORDS / "submitable_alpha.csv"
    if not sub_file.exists():
        return False
    rows = []
    found = False
    try:
        with open(sub_file, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            for row in reader:
                if row.get("id") == alpha_id:
                    row.update(updates)
                    found = True
                rows.append(row)
        if found:
            with open(sub_file, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
    except Exception:
        return False
    return found


def _remove_submitable_row(alpha_id: str) -> bool:
    sub_file = RECORDS / "submitable_alpha.csv"
    if not sub_file.exists():
        return False
    rows = []
    found = False
    try:
        with open(sub_file, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            for row in reader:
                if row.get("id") == alpha_id:
                    found = True
                else:
                    rows.append(row)
        if found:
            with open(sub_file, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
    except Exception:
        return False
    return found


# ─── 人工提交接口 ──────────────────────────────────────────────

@router.post("/alphas/{alpha_id}/submit")
def submit_alpha_to_brain(alpha_id: str):
    """
    人工确认后提交单个 alpha 到 Brain 平台（需用户主动调用，不自动批量）
    """
    try:
        import sys
        from alpha.core.machine_lib import login
        from alpha.pipeline.submit_alpha import submit_alpha as _submit

        s = login()
        status_code = _submit(s, alpha_id)

        if status_code in (200, 201):
            with _csv_lock:
                _remove_submitable_row(alpha_id)
            return {"status": "ok", "alpha_id": alpha_id, "message": f"Alpha {alpha_id} 提交成功"}
        elif status_code == 403:
            return {"status": "rejected", "alpha_id": alpha_id, "message": "提交被平台拒绝（可能不达标或已提交）"}
        else:
            return {"status": "fail", "alpha_id": alpha_id, "message": f"提交失败，状态码: {status_code}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"提交失败: {str(e)}")


# ─── 官方回测检查接口 ──────────────────────────────────────────

BRAIN_API_URL = "https://api.worldquantbrain.com"


@router.get("/alphas/{alpha_id}/official-check")
def official_check(alpha_id: str):
    """
    调用 Brain 官方 /alphas/{id}/check 获取最新质量检查结果
    """
    try:
        import sys
        from alpha.core.machine_lib import login
        s = login()
        resp = s.get(f"{BRAIN_API_URL}/alphas/{alpha_id}/check", timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            checks = data.get("is", {}).get("checks", [])
            return {"alpha_id": alpha_id, "checks": checks, "raw": data}
        else:
            return {"alpha_id": alpha_id, "error": f"HTTP {resp.status_code}", "checks": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── 审核状态更新接口 ──────────────────────────────────────────

class ReviewRequest(BaseModel):
    review_status: Optional[str] = None
    review_note: Optional[str] = None


@router.patch("/alphas/{alpha_id}/review")
def update_review(alpha_id: str, body: ReviewRequest):
    """
    更新 submitable_alpha.csv 中某个因子的审核状态和备注
    """
    updates: dict = {}
    if body.review_status is not None:
        updates["review_status"] = body.review_status
    if body.review_note is not None:
        updates["review_note"] = body.review_note

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    with _csv_lock:
        found = _update_submitable_row(alpha_id, updates)

    if not found:
        raise HTTPException(status_code=404, detail=f"Alpha {alpha_id} not found in submitable list")

    return {"alpha_id": alpha_id, "updated": updates}


# ─── Order 5 复核队列接口 ─────────────────────────────────────

@router.get("/alphas/order5-queue")
def get_order5_queue():
    """
    返回 Order 5 相关性剪枝产出的人工复核队列（records/order5_review_queue.csv）
    """
    queue_file = RECORDS / "order5_review_queue.csv"
    if not queue_file.exists():
        return {
            "items": [],
            "total": 0,
            "kept_total": 0,
            "pruned_total": 0,
            "no_pnl_total": 0,
            "message": "Order 5 复核队列尚未生成，请先运行 digging_5step.py",
        }

    items = []
    try:
        with open(queue_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                items.append(dict(row))
    except Exception:
        pass

    def _is_truthy(value) -> bool:
        return str(value or '').strip().lower() in {'1', 'true', 'yes', 'y'}

    kept_total = pruned_total = no_pnl_total = 0
    for row in items:
        status = str(row.get('order5_status') or '').strip().lower()
        if not status:
            # 兼容旧文件：没有三态字段时回退到 pruned_by_corr 两态
            status = 'pruned_out' if _is_truthy(row.get('pruned_by_corr')) else 'kept'
        if status == 'pruned_out':
            pruned_total += 1
        elif status == 'no_pnl':
            no_pnl_total += 1
        else:
            kept_total += 1

    return {
        "items": items,
        "total": len(items),
        "kept_total": kept_total,
        "pruned_total": pruned_total,
        "no_pnl_total": no_pnl_total,
    }
