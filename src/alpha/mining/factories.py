from __future__ import annotations

import re
from typing import Iterable


def generate_order3_candidates(expressions: Iterable[str]) -> list[str]:
    candidates: list[str] = []
    for expr in expressions:
        has_rank = "rank(" in expr
        has_zscore = "zscore(" in expr
        candidates.append(f"ts_decay_linear({expr}, 22)")
        if not has_rank:
            candidates.append(f"rank({expr})")
        elif not has_zscore:
            candidates.append(f"zscore({expr})")
    return candidates


def generate_order4_variants(expressions: Iterable[str]) -> list[str]:
    variants: list[str] = []
    windows = (10, 22, 66)
    for expr in expressions:
        variants.append(expr)
        if "rank(" not in expr:
            variants.append(f"rank({expr})")
        if "zscore(" not in expr:
            variants.append(f"zscore({expr})")
        if "normalize(" not in expr:
            variants.append(f"normalize({expr})")
        for window in windows:
            variants.append(f"ts_decay_linear({expr}, {window})")
    return list(dict.fromkeys(variants))


def expression_core(expr: str) -> str:
    return re.sub(r"\b\d+\b", "N", str(expr))


def deduplicate_by_core(items: Iterable[tuple[str, int]]) -> list[tuple[str, int]]:
    best_by_core: dict[str, tuple[str, int]] = {}
    for expr, decay in items:
        core = expression_core(expr)
        current = best_by_core.get(core)
        if current is None or abs(decay - 22) < abs(current[1] - 22):
            best_by_core[core] = (expr, decay)
    return list(best_by_core.values())
