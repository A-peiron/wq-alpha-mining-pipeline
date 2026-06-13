"""
routers/platform.py
-------------------
WorldQuant Brain 平台数据 API / WorldQuant Brain platform data APIs

将平台的各类数据代理给前端，避免前端直接调用平台 API（跨域/凭证问题）
Proxies Brain platform data to frontend, avoiding CORS/credential issues.

提供以下端点 / Provides the following endpoints:
  GET /api/platform/overview         — 账号总览（积分/等级/各阶段因子数）
                                       Account overview (score/rank/stage counts)
  GET /api/platform/alphas           — 各阶段因子列表（IS/OS/PROD）
                                       Alpha list by stage
  GET /api/platform/alphas/{id}      — 单个因子完整详情 / Full alpha detail
  GET /api/platform/alphas/{id}/pnl  — 因子 PnL 曲线数据 / Alpha PnL time series
"""

import sys
import os
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException

# 将项目根目录加入路径 / Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from web.brain_client import brain

router = APIRouter()


def _safe_count(path: str) -> tuple[int, bool]:
    """调用 Brain API 取某查询的 count 字段。

    返回 (count, capped)：
      - count: 失败为 -1
      - capped: count 是否达到平台 10000 上限（真实值可能更大）
    """
    try:
        r = brain.get(path, timeout=20)
        r.raise_for_status()
        c = int(r.json().get("count", 0))
        return c, c >= 10000
    except Exception:
        return -1, False


@router.get("/overview")
def get_overview():
    """
    获取账号总览信息（真实平台数据）
    Get account overview from the live Brain platform.

    Returns 字段与前端 PlatformOverview 对齐：
        user_id / full_name / genius_level
        alphas_os_count   — OS（已通过、计入 weight）阶段因子数
        alphas_is_count   — IS（回测中/待审）阶段因子数
        unsubmitted_count — IS 阶段且 status=UNSUBMITTED
        *_capped          — 该计数是否达到平台 10000 上限
        stage_counts      — 原始各阶段计数（含失败标记 -1）
        fetched_at        — 数据抓取时间（本地）
    """
    try:
        resp = brain.get("/users/self", timeout=20)
        resp.raise_for_status()
        user_data = resp.json()
    except Exception as e:
        # 502：上游平台/凭证问题，前端据此提示去设置页配置账号
        raise HTTPException(status_code=502, detail=f"无法连接 Brain 平台（请确认设置页账号已配置）：{e}")

    os_count, os_capped = _safe_count("/users/self/alphas?stage=OS&limit=1")
    is_count, is_capped = _safe_count("/users/self/alphas?stage=IS&limit=1")
    prod_count, _ = _safe_count("/users/self/alphas?stage=PROD&limit=1")
    unsubmitted, unsub_capped = _safe_count("/users/self/alphas?stage=IS&status=UNSUBMITTED&limit=1")

    stage_counts = {"IS": is_count, "OS": os_count, "PROD": prod_count}

    return {
        "user_id": user_data.get("id"),
        "full_name": user_data.get("fullName"),
        "genius_level": user_data.get("geniusLevel"),
        "alphas_os_count": os_count,
        "alphas_is_count": is_count,
        "is_capped": is_capped,
        "unsubmitted_count": unsubmitted,
        "unsubmitted_capped": unsub_capped,
        "os_capped": os_capped,
        "total_alphas": sum(v for v in stage_counts.values() if v >= 0),
        "stage_counts": stage_counts,
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


@router.get("/alphas")
def get_platform_alphas(
    stage: str = "OS",
    page: int = 1,
    limit: int = 50,
    order: str = "-dateCreated",
):
    """
    获取平台上指定阶段的因子列表
    Get platform alphas filtered by stage

    Args:
        stage: "IS" | "OS" | "PROD" — 因子阶段 / Alpha stage
        page: 页码 / Page number
        limit: 每页条数（最大 100）/ Items per page (max 100)
        order: 排序字段，如 "-is.sharpe"（负号表示降序）
               Sort field e.g. "-is.sharpe" (minus = descending)
    """
    offset = (page - 1) * limit
    try:
        resp = brain.get(
            f"/users/self/alphas?stage={stage}&limit={limit}&offset={offset}&order={order}"
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Brain API error: {e}")

    # 只返回前端需要的关键字段，减少传输量
    # Return only key fields to reduce payload size
    items = []
    for a in data.get("results", []):
        is_data = a.get("is") or {}
        items.append({
            "id": a.get("id"),
            "code": (a.get("regular") or {}).get("code", ""),
            "dateCreated": a.get("dateCreated"),
            "stage": a.get("stage"),
            "status": a.get("status"),
            "color": a.get("color"),
            "tags": a.get("tags", []),
            "region": (a.get("settings") or {}).get("region"),
            "universe": (a.get("settings") or {}).get("universe"),
            "decay": (a.get("settings") or {}).get("decay"),
            "sharpe": is_data.get("sharpe"),
            "fitness": is_data.get("fitness"),
            "returns": is_data.get("returns"),
            "turnover": is_data.get("turnover"),
            "margin": is_data.get("margin"),
            "longCount": is_data.get("longCount"),
            "shortCount": is_data.get("shortCount"),
        })

    return {
        "total": data.get("count", 0),
        "page": page,
        "limit": limit,
        "stage": stage,
        "items": items,
    }


@router.get("/alphas/{alpha_id}")
def get_alpha_detail(alpha_id: str):
    """
    获取单个因子的完整详情（包含 IS checks 结果）
    Get full detail for a single alpha, including IS checks results

    Args:
        alpha_id: 因子 ID / Alpha ID
    """
    try:
        resp = brain.get(f"/alphas/{alpha_id}")
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Brain API error: {e}")


@router.get("/alphas/{alpha_id}/pnl")
def get_alpha_pnl(alpha_id: str):
    """
    获取因子 PnL 时间序列数据（用于前端画折线图）
    Get PnL time series for an alpha (for charting)

    Returns dates and cumulative PnL values.
    返回日期和累计 PnL 数组。
    """
    try:
        resp = brain.get(f"/alphas/{alpha_id}/recordsets/pnl")
        resp.raise_for_status()
        raw = resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Brain API error: {e}")

    # 整理为前端友好的格式 / Format for frontend charting
    records = raw.get("records", [])
    props = [p["name"] for p in raw.get("schema", {}).get("properties", [])]
    try:
        date_idx = props.index("date")
        pnl_idx = props.index("pnl")
        dates = [r[date_idx] for r in records]
        pnls = [r[pnl_idx] for r in records]
    except (ValueError, IndexError):
        dates, pnls = [], []

    return {"alpha_id": alpha_id, "dates": dates, "pnl": pnls}
