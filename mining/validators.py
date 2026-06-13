from __future__ import annotations

import csv
import glob
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from config import RECORDS_PATH, write_event


TS_ONLY_OPS = {
    "ts_rank", "ts_zscore", "ts_delta", "ts_sum", "ts_av_diff", "ts_decay_linear",
    "ts_mean", "ts_std_dev", "ts_corr", "ts_backfill", "ts_delay", "ts_product",
}

VEC_PREFIXES = ("vec_avg(", "vec_sum(")


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]
    warnings: list[str]


@dataclass
class PreparedCandidates:
    items: list
    total: int
    scheduled: int
    skipped: dict[str, int]
    invalid_examples: list[dict]


def normalize_alpha_expression(expr: str) -> str:
    return re.sub(r"\s+", "", str(expr or "").strip())


def validate_alpha_expression(expr: str) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    normalized = normalize_alpha_expression(expr)

    if not normalized:
        errors.append("empty")
        return ValidationResult(False, errors, warnings)

    depth = 0
    max_depth = 0
    for ch in normalized:
        if ch == "(":
            depth += 1
            max_depth = max(max_depth, depth)
        elif ch == ")":
            depth -= 1
            if depth < 0:
                errors.append("unmatched_right_parenthesis")
                break
    if depth > 0:
        errors.append("missing_right_parenthesis")

    if ",," in normalized or "(," in normalized or ",)" in normalized:
        errors.append("malformed_comma")

    if max_depth > 8:
        warnings.append("deep_nesting")

    op_count = normalized.count("(")
    if op_count > 12:
        warnings.append("too_many_operators")

    if any(op in normalized for op in TS_ONLY_OPS):
        for pattern in ("ts_rank(vec_", "ts_zscore(vec_", "ts_delta(vec_", "ts_sum(vec_"):
            if pattern in normalized:
                errors.append("vector_used_directly_in_ts_op")
                break

    return ValidationResult(not errors, errors, warnings)


def load_known_expressions(tags: Optional[Sequence[str]] = None) -> set[str]:
    known: set[str] = set()
    tag_set = {t for t in (tags or []) if t}

    patterns = []
    if tag_set:
        patterns.extend(os.path.join(RECORDS_PATH, f"{tag}_simulated_alpha_expression.txt") for tag in tag_set)
    patterns.append(os.path.join(RECORDS_PATH, "*_simulated_alpha_expression.txt"))

    for pattern in patterns:
        for path in glob.glob(pattern):
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    known.update(normalize_alpha_expression(line) for line in f if line.strip())
            except OSError:
                continue

    sim_path = os.path.join(RECORDS_PATH, "simulations.jsonl")
    if os.path.exists(sim_path):
        try:
            with open(sim_path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    expr = record.get("expression") or record.get("code")
                    if expr:
                        known.add(normalize_alpha_expression(expr))
        except OSError:
            pass

    sub_path = os.path.join(RECORDS_PATH, "submitable_alpha.csv")
    if os.path.exists(sub_path):
        try:
            with open(sub_path, encoding="utf-8", errors="replace", newline="") as f:
                for row in csv.DictReader(f):
                    expr = row.get("code") or row.get("expression")
                    if expr:
                        known.add(normalize_alpha_expression(expr))
        except OSError:
            pass

    return {expr for expr in known if expr}


def prepare_expressions(
    candidates: Iterable,
    expression_getter=lambda item: item,
    known_expressions: Optional[set[str]] = None,
    tags: Optional[Sequence[str]] = None,
    phase: str = "unknown",
) -> PreparedCandidates:
    known = set(known_expressions or load_known_expressions(tags))
    seen_batch: set[str] = set()
    prepared = []
    skipped = Counter()
    invalid_examples: list[dict] = []
    total = 0

    for item in candidates:
        total += 1
        expr = normalize_alpha_expression(expression_getter(item))
        result = validate_alpha_expression(expr)
        if not result.valid:
            reason = "+".join(result.errors)
            skipped[reason] += 1
            if len(invalid_examples) < 5:
                invalid_examples.append({"expression": expr, "errors": result.errors})
            continue
        if expr in seen_batch:
            skipped["duplicate_in_batch"] += 1
            continue
        if expr in known:
            skipped["known_expression"] += 1
            continue
        seen_batch.add(expr)
        prepared.append(item)

    summary = PreparedCandidates(
        items=prepared,
        total=total,
        scheduled=len(prepared),
        skipped=dict(skipped),
        invalid_examples=invalid_examples,
    )

    write_event(
        phase=phase,
        event="precheck",
        detail=f"{summary.scheduled}/{summary.total} candidates scheduled",
        counts={"total": summary.total, "scheduled": summary.scheduled, **summary.skipped},
        extra={"invalid_examples": invalid_examples},
    )
    return summary
