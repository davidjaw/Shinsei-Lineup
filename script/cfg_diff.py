"""
Diff the current cfg.json against (a) the most recently archived cfg, and
(b) cfg's own internal consistency between multi_lang and skill.name.

Outputs:
  .build/cfg_diff_report.md       — full markdown report (gitignored)
  data/cfg/last_diff_summary.txt  — one-line summary suitable for PR review

Phase 1 is warn-only: any anomaly is reported but exit is always 0. Phase 4
flips to block mode (count regressions exceed thresholds → exit 1).
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from paths import (
    CFG_CURRENT_JSON,
    CFG_DIFF_REPORT,
    CFG_DIR,
    CFG_HISTORY_DIR,
    CFG_LAST_DIFF_SUMMARY,
)

# Roman-numeral normalization: cfg's multi_lang uses Unicode (Ⅰ, Ⅱ),
# cfg.skill.name often uses ASCII (I, II). When checking internal
# consistency, treat them as equivalent before flagging a mismatch.
ROMAN_MAP = {
    "Ⅰ": "I", "Ⅱ": "II", "Ⅲ": "III", "Ⅳ": "IV", "Ⅴ": "V",
    "Ⅵ": "VI", "Ⅶ": "VII", "Ⅷ": "VIII", "Ⅸ": "IX", "Ⅹ": "X",
}


def _normalize_for_compare(s: str) -> str:
    if not s:
        return s
    out = unicodedata.normalize("NFC", s)
    for k, v in ROMAN_MAP.items():
        out = out.replace(k, v)
    return out


@dataclass
class Anomaly:
    severity: str   # "block" | "warn" | "info"
    category: str
    detail: str


@dataclass
class Report:
    new_version: str
    old_version: str | None
    anomalies: list[Anomaly] = field(default_factory=list)
    counts_new: dict[str, int] = field(default_factory=dict)
    counts_old: dict[str, int] = field(default_factory=dict)

    @property
    def blockers(self) -> list[Anomaly]:
        return [a for a in self.anomalies if a.severity == "block"]

    @property
    def warnings(self) -> list[Anomaly]:
        return [a for a in self.anomalies if a.severity == "warn"]


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _load_current() -> dict:
    if not CFG_CURRENT_JSON.exists():
        raise FileNotFoundError(
            f"{CFG_CURRENT_JSON} does not exist. Run fetch_cfg.py first."
        )
    with CFG_CURRENT_JSON.open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_latest_archived() -> tuple[dict | None, Path | None]:
    """Return the most recently modified archived cfg, or (None, None)."""
    if not CFG_HISTORY_DIR.exists():
        return None, None
    archives = sorted(
        CFG_HISTORY_DIR.glob("cfg-*.json.gz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not archives:
        return None, None
    latest = archives[0]
    with gzip.open(latest, "rb") as f:
        return json.loads(f.read()), latest


# ---------------------------------------------------------------------------
# Diff: time-series (current vs prior)
# ---------------------------------------------------------------------------

# Keys that must remain present at top level.
REQUIRED_TOP_KEYS = {"hero", "skill", "multi_lang", "version"}

# Drop thresholds (percentage). Beyond these, a block-severity anomaly fires
# (in block mode). In warn mode, it remains an anomaly with severity=block but
# the script still exits 0.
DROP_THRESHOLD_PCT = {
    "hero": 5.0,
    "skill": 5.0,
    "multi_lang": 10.0,
}


def _diff_timeseries(new: dict, old: dict, report: Report) -> None:
    # Top-level keys
    new_keys = set(new.keys())
    old_keys = set(old.keys())
    missing = REQUIRED_TOP_KEYS & old_keys - new_keys
    for k in missing:
        report.anomalies.append(Anomaly(
            "block", "structure",
            f"top-level key {k!r} present in old cfg but missing in new cfg",
        ))
    added_keys = new_keys - old_keys
    for k in added_keys:
        report.anomalies.append(Anomaly(
            "info", "structure",
            f"new top-level key {k!r} added (size={_sizeof(new[k])})",
        ))

    # Counts per kind
    for kind in ("hero", "skill", "multi_lang"):
        if kind not in new or kind not in old:
            continue
        n_new = len(new[kind])
        n_old = len(old[kind])
        report.counts_new[kind] = n_new
        report.counts_old[kind] = n_old
        if n_old == 0:
            continue
        delta_pct = (n_old - n_new) / n_old * 100.0
        if delta_pct > DROP_THRESHOLD_PCT[kind]:
            report.anomalies.append(Anomaly(
                "block", "count",
                f"{kind} count dropped {delta_pct:.1f}% "
                f"({n_old} → {n_new}); threshold {DROP_THRESHOLD_PCT[kind]}%",
            ))
        elif n_new != n_old:
            report.anomalies.append(Anomaly(
                "info", "count",
                f"{kind} count {n_old} → {n_new} ({n_new - n_old:+d})",
            ))

    # Tracked entries deletion: heroes + skills indexed by id
    for kind in ("hero", "skill"):
        if kind not in new or kind not in old:
            continue
        new_ids = {e.get("id"): e for e in new[kind] if "id" in e}
        old_ids = {e.get("id"): e for e in old[kind] if "id" in e}
        deleted = set(old_ids) - set(new_ids)
        if deleted:
            sample = sorted(deleted)[:5]
            report.anomalies.append(Anomaly(
                "block", "deletion",
                f"{len(deleted)} {kind} entries deleted "
                f"(sample ids: {sample})",
            ))

    # Per-skill tips length regression: if a skill's tips shrunk by >30%, warn.
    if "skill" in new and "skill" in old:
        new_by_id = {e["id"]: e for e in new["skill"] if "id" in e}
        for old_skill in old["skill"]:
            sid = old_skill.get("id")
            if sid not in new_by_id:
                continue
            old_tips = old_skill.get("tips") or ""
            new_tips = new_by_id[sid].get("tips") or ""
            if not old_tips:
                continue
            if len(new_tips) < len(old_tips) * 0.7:
                report.anomalies.append(Anomaly(
                    "warn", "tips_shrink",
                    f"skill id={sid} name={old_skill.get('name')!r} tips "
                    f"shrunk {len(old_tips)} → {len(new_tips)} chars",
                ))

    # Per-skill skill_kind changes (mechanical change requiring battle-update)
    if "skill" in new and "skill" in old:
        new_by_id = {e["id"]: e for e in new["skill"] if "id" in e}
        for old_skill in old["skill"]:
            sid = old_skill.get("id")
            if sid not in new_by_id:
                continue
            old_k = old_skill.get("skill_kind")
            new_k = new_by_id[sid].get("skill_kind")
            if old_k and new_k and old_k != new_k:
                report.anomalies.append(Anomaly(
                    "warn", "skill_kind",
                    f"skill id={sid} name={old_skill.get('name')!r} "
                    f"skill_kind: {old_k!r} → {new_k!r}",
                ))


def _sizeof(v) -> str:
    if isinstance(v, list):
        return f"list[{len(v)}]"
    if isinstance(v, dict):
        return f"dict[{len(v)}]"
    return type(v).__name__


# ---------------------------------------------------------------------------
# Diff: internal consistency (multi_lang vs skill.name)
# ---------------------------------------------------------------------------

def _diff_internal(cfg: dict, report: Report) -> None:
    """Find places where multi_lang.zh-hans and cfg.skill.name disagree."""
    skill_names = {s.get("name") for s in cfg.get("skill", []) if s.get("name")}
    skill_names_norm = {_normalize_for_compare(n): n for n in skill_names}
    ml = cfg.get("multi_lang", [])

    # Names that exist in multi_lang.zh-hans but not in any cfg.skill.name.
    # We only flag those that look skill-ish: short (≤40 chars), no font tags,
    # not biographical prose. Exclude entries that are clearly translations of
    # full sentences (those have font tags or are very long).
    inconsistencies: list[tuple[str, str]] = []

    for entry in ml:
        hans = entry.get("zh-hans")
        if not hans or len(hans) > 40 or "<" in hans:
            continue
        if hans in skill_names:
            continue
        # Try roman-numeral normalization
        norm = _normalize_for_compare(hans)
        if norm in skill_names_norm:
            actual = skill_names_norm[norm]
            if actual != hans:
                inconsistencies.append((hans, actual))

    if inconsistencies:
        report.anomalies.append(Anomaly(
            "info", "internal_consistency",
            f"{len(inconsistencies)} multi_lang↔skill.name mismatches "
            f"(roman-numeral or character variants). Suggested entries for "
            f"data/source_corrections.yaml (skill_name_alias) are listed in the report.",
        ))
        # Stash the suggestions in metadata via a magic anomaly entry
        for ml_name, skill_name in inconsistencies[:50]:
            report.anomalies.append(Anomaly(
                "info", "alias_suggestion",
                f"  {ml_name!r} → {skill_name!r}",
            ))


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _write_report(report: Report, archived_path: Path | None) -> None:
    CFG_DIFF_REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append(f"# cfg.json diff report")
    lines.append("")
    lines.append(f"- new version: `{report.new_version}`")
    if report.old_version:
        lines.append(f"- prior version: `{report.old_version}`")
        lines.append(f"- archive source: `{archived_path}`")
    else:
        lines.append("- prior version: (no archive — first run)")
    lines.append("")

    if report.counts_new or report.counts_old:
        lines.append("## Counts")
        lines.append("")
        lines.append("| kind | old | new | delta |")
        lines.append("|------|-----|-----|-------|")
        for kind in ("hero", "skill", "multi_lang"):
            n_new = report.counts_new.get(kind)
            n_old = report.counts_old.get(kind)
            if n_new is None and n_old is None:
                continue
            delta = (n_new or 0) - (n_old or 0)
            lines.append(f"| {kind} | {n_old or '—'} | {n_new or '—'} | {delta:+d} |")
        lines.append("")

    blockers = report.blockers
    warnings = report.warnings
    infos = [a for a in report.anomalies if a.severity == "info"]

    if blockers:
        lines.append(f"## ⛔ Blockers ({len(blockers)})")
        for a in blockers:
            lines.append(f"- **[{a.category}]** {a.detail}")
        lines.append("")
    else:
        lines.append("## ⛔ Blockers: 0")
        lines.append("")

    if warnings:
        lines.append(f"## ⚠️ Warnings ({len(warnings)})")
        for a in warnings:
            lines.append(f"- **[{a.category}]** {a.detail}")
        lines.append("")
    else:
        lines.append("## ⚠️ Warnings: 0")
        lines.append("")

    if infos:
        lines.append(f"## ℹ️ Info ({len(infos)})")
        for a in infos:
            lines.append(f"- **[{a.category}]** {a.detail}")
        lines.append("")

    CFG_DIFF_REPORT.write_text("\n".join(lines), encoding="utf-8")


def _write_summary(report: Report) -> None:
    """One-line summary, committable."""
    counts_blob = ""
    if report.counts_new and report.counts_old:
        deltas = []
        for kind in ("hero", "skill", "multi_lang"):
            n_new = report.counts_new.get(kind, 0)
            n_old = report.counts_old.get(kind, 0)
            d = n_new - n_old
            if d != 0:
                deltas.append(f"{kind} {d:+d}")
        counts_blob = ", ".join(deltas) if deltas else "no count changes"
    elif report.counts_new:
        counts_blob = ", ".join(f"{k} {v}" for k, v in report.counts_new.items())

    n_block = len(report.blockers)
    n_warn = len(report.warnings)
    if report.old_version:
        line = (
            f"cfg {report.new_version} vs {report.old_version}: "
            f"{counts_blob}; "
            f"{n_block} blocker(s), {n_warn} warning(s)"
        )
    else:
        line = (
            f"cfg {report.new_version} (initial baseline): "
            f"{counts_blob}; "
            f"{n_block} blocker(s), {n_warn} warning(s)"
        )
    CFG_DIR.mkdir(parents=True, exist_ok=True)
    CFG_LAST_DIFF_SUMMARY.write_text(line + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(threshold_mode: str = "warn") -> int:
    cur = _load_current()
    old, archived_path = _load_latest_archived()
    report = Report(
        new_version=str(cur.get("version", "?")),
        old_version=str(old.get("version", "?")) if old else None,
    )
    # Always populate counts for the new cfg, regardless of whether we have a
    # prior version to compare against.
    for kind in ("hero", "skill", "multi_lang"):
        if kind in cur:
            report.counts_new[kind] = len(cur[kind])

    if old is not None:
        _diff_timeseries(cur, old, report)
    _diff_internal(cur, report)

    _write_report(report, archived_path)
    _write_summary(report)

    n_block = len(report.blockers)
    n_warn = len(report.warnings)
    print(
        f"[cfg_diff] version={report.new_version} "
        f"prior={report.old_version or '(initial)'} "
        f"blockers={n_block} warnings={n_warn} "
        f"report={CFG_DIFF_REPORT}"
    )

    if threshold_mode == "block" and n_block > 0:
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("warn", "block"),
        default="warn",
        help=(
            "warn: always exit 0 (Phase 1-3); block: exit 1 if any blockers "
            "(Phase 4)."
        ),
    )
    args = parser.parse_args()
    try:
        return run(threshold_mode=args.mode)
    except FileNotFoundError as e:
        print(f"[cfg_diff] {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
