"""
web/routers/experiments.py
--------------------------
实验配置管理 API / Experiment config management API

端点 / Endpoints:
  GET  /api/experiments         — 列出实验及当前 active
  POST /api/experiments/switch  — 切换 active_experiment
"""

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import load_mining_config

router = APIRouter()

WORK_DIR = Path(__file__).parent.parent.parent
CONFIG_PATH = WORK_DIR / 'experiment_config.json'


def _load_config() -> dict:
    try:
        with open(str(CONFIG_PATH), encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail='experiment_config.json 不存在')
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f'配置文件格式错误: {e}')


def _save_config(config: dict):
    with open(str(CONFIG_PATH), 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def _baseline_only(config: dict) -> dict:
    """实验切换已废弃：只对外暴露 baseline，避免前端再出现 v2_decay_outer。"""
    experiments = config.get('experiments', {})
    if not isinstance(experiments, dict):
        experiments = {}
    baseline = experiments.get('baseline')
    if not isinstance(baseline, dict):
        # 兼容极端情况：没有 baseline 时取第一个可用实验，但仍命名为 baseline 暴露。
        baseline = next((v for v in experiments.values() if isinstance(v, dict)), {})
    if config.get('active_experiment') != 'baseline':
        config['active_experiment'] = 'baseline'
        _save_config(config)
    return baseline


@router.get('')
async def list_experiments():
    """返回当前 baseline tag 映射；实验切换入口已废弃。"""
    config = _load_config()
    baseline = dict(_baseline_only(config))
    baseline.update(load_mining_config().get('tags', {}))
    return {
        'active': 'baseline',
        'experiments': {'baseline': baseline},
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
        detail='实验切换已废弃：v2_decay_outer 不再使用，请保持 baseline 并通过设置页参数生成阶段 tag。',
    )
