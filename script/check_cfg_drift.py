"""
Match-rate floor check: every kind in data/prototype/*_proto.yaml must
keep at least its baseline cfg-match coverage. Catches regressions where
a cfg refresh removed entries the build expects.

Run alone (`uv run script/check_cfg_drift.py`) or as part of `npm run data`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

from paths import PROTOTYPE_DIR

# Regression floors (NOT target match rates). A drop below means a cfg refresh
# stopped recognising entries the build previously matched — investigate before
# loosening. Re-baseline upward as upstream coverage stabilises; never lower
# silently.
#
# Why each kind sits where it does:
#   skills   — game8 and cfg overlap is near-complete; drops here usually mean
#              a renamed cfg entry (add it to source_corrections.yaml).
#   heroes   — every crawled hero must resolve; failure is a regression.
#   traits   — game8 carries some traits cfg doesn't expose; 0.85 reflects
#              that structural gap, not a quality issue.
#   bingxue  — tight floor because the 天赋 set is small and stable.
#   assembly — 评定众 only matches via base name (after stripping 普/良/优
#              tiers); many crawled entries lack a ja↔hans bridge in cfg yet.
EXPECTED_RATES = {
    "skills":   0.98,
    "heroes":   1.00,
    "traits":   0.85,
    "bingxue":  0.95,
    "assembly": 0.30,
}


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text("utf-8")) or {}


def check() -> list[str]:
    errors: list[str] = []
    for kind, floor in EXPECTED_RATES.items():
        proto = _load(PROTOTYPE_DIR / f"{kind}_proto.yaml")
        if not proto:
            errors.append(f"{kind}: prototype not found (run `uv run script/merge_sources.py`)")
            continue
        total = len(proto)
        matched = sum(
            1 for v in proto.values()
            if (v.get("match") or {}).get("confidence") in ("high", "low")
        )
        actual = matched / total if total else 0.0
        if actual < floor:
            errors.append(
                f"{kind}: matched {matched}/{total} ({actual:.1%}), "
                f"expected ≥ {floor:.0%}"
            )
    return errors


def main() -> int:
    errors = check()
    if errors:
        for e in errors:
            print(f"[check-cfg-drift] FAIL: {e}", file=sys.stderr)
        return 1
    print("[check-cfg-drift] all kinds met match-rate floors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
