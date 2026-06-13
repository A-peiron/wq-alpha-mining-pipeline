from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass(frozen=True)
class MiningStage:
    id: str
    label: str
    description: str
    script: Optional[str]
    input_tag_key: Optional[str]
    output_tag_key: Optional[str]
    mutex_group: Optional[str]
    enabled: bool
    log_file: str
    reserved: bool = False


STAGES: tuple[MiningStage, ...] = (
    MiningStage(
        id="order1",
        label="Order 1 广撒网",
        description="字段 × 基础/时序算子生成一阶候选并回测",
        script="digging_1step.py",
        input_tag_key=None,
        output_tag_key="step1_tag",
        mutex_group="digging",
        enabled=True,
        log_file="digging.log",
    ),
    MiningStage(
        id="order2_group",
        label="Order 2 分组增强",
        description="从一阶高分因子出发套 group 中性化/分组算子",
        script="digging_2step.py",
        input_tag_key="step1_tag",
        output_tag_key="step2_tag",
        mutex_group="digging",
        enabled=True,
        log_file="digging.log",
    ),
    MiningStage(
        id="order3_decay",
        label="Order 3 参数增强",
        description="从二阶高分因子出发套 decay/rank/zscore 外层增强",
        script="digging_3step.py",
        input_tag_key="step2_tag",
        output_tag_key="step3_tag",
        mutex_group="digging",
        enabled=True,
        log_file="digging.log",
    ),
    MiningStage(
        id="order4_variant",
        label="Order 4 变体扩展",
        description="rank/zscore/normalize/ts_decay_linear 变体回测，从 Order 3 高分因子出发扩展候选池",
        script="digging_4step.py",
        input_tag_key="step3_tag",
        output_tag_key="order4_tag",
        mutex_group="digging",
        enabled=True,
        log_file="digging.log",
        reserved=False,
    ),
    MiningStage(
        id="order5_prune",
        label="Order 5 相关性剪枝",
        description="对 Order 4 候选做本地 PnL 相关性剪枝，产出人工复核队列（不回测，不自动提交）",
        script="digging_5step.py",
        input_tag_key="order4_tag",
        output_tag_key="order5_tag",
        mutex_group="digging",
        enabled=True,
        log_file="digging.log",
        reserved=False,
    ),
    MiningStage(
        id="check",
        label="Check 人工清单",
        description="粗筛/精筛自相关，输出人工提交清单",
        script="check.py",
        input_tag_key=None,
        output_tag_key=None,
        mutex_group=None,
        enabled=True,
        log_file="check.log",
    ),
)

ALIASES = {
    "1step": "order1",
    "2step": "order2_group",
    "3step": "order3_decay",
}


def normalize_stage_id(name: str) -> str:
    return ALIASES.get(name, name)


def get_stage(name: str) -> Optional[MiningStage]:
    stage_id = normalize_stage_id(name)
    for stage in STAGES:
        if stage.id == stage_id:
            return stage
    return None


def list_stages(config: Optional[dict] = None) -> list[dict]:
    tags = {}
    if config:
        tags = config.get("tags", {}) or {}

    items = []
    for stage in STAGES:
        item = asdict(stage)
        item["input_tag"] = tags.get(stage.input_tag_key or "") if stage.input_tag_key else None
        item["output_tag"] = tags.get(stage.output_tag_key or "") if stage.output_tag_key else None
        items.append(item)
    return items


def runnable_stage_ids() -> set[str]:
    return {stage.id for stage in STAGES if stage.enabled and stage.script}
