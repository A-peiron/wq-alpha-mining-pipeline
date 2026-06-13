"""
web/routers/experiments.py
--------------------------
阶段 tag 查询 API（实验切换机制已废弃）

阶段 tag 现按设置页的 dataset/region/delay 动态生成，不再有多实验切换。
保留本路由仅为兼容前端「当前 Tag 方案」展示与旧前端的切换端点。

端点 / Endpoints:
  GET  /api/experiments         — 返回当前动态阶段 tag
  POST /api/experiments/switch  — 已废弃，返回 410
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from alpha.core.config import load_mining_config

router = APIRouter()


@router.get('')
async def list_experiments():
    """返回当前阶段 tag 映射（按 dataset/region/delay 动态生成）。"""
    tags = load_mining_config().get('tags', {})
    return {
        'active': 'baseline',
        'experiments': {'baseline': dict(tags)},
        'experiment_switch_deprecated': True,
        'message': '实验切换已废弃；阶段 tag 按设置页 dataset/region/delay 动态生成。',
    }


class SwitchRequest(BaseModel):
    name: str


@router.post('/switch')
async def switch_experiment(body: SwitchRequest):
    """实验切换已废弃，保留端点只为旧前端给出明确错误。"""
    raise HTTPException(
        status_code=410,
        detail='实验切换已废弃：阶段 tag 按设置页 dataset/region/delay 动态生成。',
    )
