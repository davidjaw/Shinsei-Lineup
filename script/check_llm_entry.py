"""JSON CLI for LLM-output structure/quality checks.

Agent-facing: one JSON object on stdout, no tqdm, no extra logs.

Usage:
    uv run script/check_llm_entry.py --kind skill|trait|bingxue|hero|mixed|patch --file PATH [--write]
    uv run script/check_llm_entry.py --kind skill   # YAML on stdin
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from llm_core import (
    autofix_frontend,
    has_kana,
    validate_bingxue_entry,
    validate_entry_quality,
    validate_hero_entry,
    validate_skill_entry,
    validate_trait_entry,
)

KINDS = ("skill", "trait", "bingxue", "hero", "mixed", "patch")


def _load_yaml(raw: str):
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        return None, f"YAML parse failed: {e}"
    return data, None


def _dump_yaml(data) -> str:
    return yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _prefixed(key: str, msgs: list[str]) -> list[str]:
    return [f"{key}: {m}" for m in msgs]


def _is_flat_frontend(entry: dict) -> bool:
    return "description" in entry and "text" not in entry


def _autofix_entry(entry: dict) -> list[str]:
    if not isinstance(entry, dict):
        return []
    if isinstance(entry.get("text"), dict) or _is_flat_frontend(entry):
        return autofix_frontend(entry)
    return []


def _quality(entry: dict) -> list[str]:
    if not isinstance(entry, dict):
        return []
    if _is_flat_frontend(entry):
        wrapped = {"text": entry, "vars": entry.get("vars", {}), "battle": entry.get("battle", {})}
        return validate_entry_quality(wrapped, log=False)
    return validate_entry_quality(entry, log=False)


def _check_named_entries(block: dict, validate_fn, *, quality: bool) -> tuple[list[str], list[str], int]:
    errors: list[str] = []
    fixes: list[str] = []
    if not isinstance(block, dict):
        return ["not a dict"], [], 0
    count = 0
    for key, entry in block.items():
        count += 1
        if not isinstance(entry, dict):
            errors.append(f"{key}: not a dict")
            continue
        fixes.extend(_prefixed(key, _autofix_entry(entry)))
        errors.extend(_prefixed(key, validate_fn(entry)))
        if quality:
            errors.extend(_prefixed(key, _quality(entry)))
    return errors, fixes, count


def _kana_in(obj, path: str = "") -> list[str]:
    errors: list[str] = []
    if isinstance(obj, str):
        if has_kana(obj):
            loc = path or "value"
            errors.append(f"{loc} contains Japanese kana")
        return errors
    if isinstance(obj, dict):
        for k, v in obj.items():
            child = f"{path}.{k}" if path else str(k)
            errors.extend(_kana_in(v, child))
        return errors
    if isinstance(obj, list):
        for i, v in enumerate(obj):
            child = f"{path}[{i}]" if path else f"[{i}]"
            errors.extend(_kana_in(v, child))
    return errors


def check(kind: str, data) -> tuple[list[str], list[str], dict[str, int]]:
    errors: list[str] = []
    fixes: list[str] = []
    counts = {"skills": 0, "heroes": 0}

    if data is None:
        return ["empty document"], [], counts
    if not isinstance(data, dict):
        return ["not a dict"], [], counts

    if kind == "skill":
        errors, fixes, n = _check_named_entries(data, validate_skill_entry, quality=True)
        counts["skills"] = n
    elif kind == "trait":
        errors, fixes, n = _check_named_entries(data, validate_trait_entry, quality=True)
        counts["skills"] = n
    elif kind == "bingxue":
        errors, fixes, n = _check_named_entries(data, validate_bingxue_entry, quality=True)
        counts["skills"] = n
    elif kind == "hero":
        errors, fixes, n = _check_named_entries(data, validate_hero_entry, quality=False)
        counts["heroes"] = n
    elif kind == "mixed":
        extra = [k for k in data if k not in ("skills", "heroes")]
        if extra:
            errors.append(f"unexpected top-level keys: {', '.join(extra)}")
        if "skills" not in data and "heroes" not in data:
            errors.append("mixed document needs skills and/or heroes")
        if "skills" in data:
            if not isinstance(data["skills"], dict):
                errors.append("skills not a dict")
            else:
                se, sf, n = _check_named_entries(data["skills"], validate_skill_entry, quality=True)
                errors.extend(se)
                fixes.extend(sf)
                counts["skills"] = n
        if "heroes" in data:
            if not isinstance(data["heroes"], dict):
                errors.append("heroes not a dict")
            else:
                he, hf, n = _check_named_entries(data["heroes"], validate_hero_entry, quality=False)
                errors.extend(he)
                fixes.extend(hf)
                counts["heroes"] = n
    elif kind == "patch":
        if data.get("_rejected") is True:
            reason = data.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                errors.append("rejected patch needs a non-empty reason")
        elif not data:
            errors.append("empty patch")
        else:
            errors.extend(_kana_in(data))

    return errors, fixes, counts


def main() -> int:
    p = argparse.ArgumentParser(description="Validate LLM YAML output as JSON")
    p.add_argument("--kind", required=True, choices=KINDS)
    p.add_argument("--file", help="YAML file (default: stdin)")
    p.add_argument("--write", action="store_true", help="Apply autofixes and rewrite --file")
    args = p.parse_args()

    if args.file:
        try:
            raw = Path(args.file).read_text("utf-8")
        except OSError as e:
            print(json.dumps({"ok": False, "errors": [f"cannot read {args.file}: {e}"], "fixes": [], "counts": {"skills": 0, "heroes": 0}}, ensure_ascii=False))
            return 1
        data, parse_err = _load_yaml(raw)
    else:
        raw = sys.stdin.read()
        data, parse_err = _load_yaml(raw)

    if parse_err:
        print(json.dumps({"ok": False, "errors": [parse_err], "fixes": [], "counts": {"skills": 0, "heroes": 0}}, ensure_ascii=False))
        return 1

    try:
        errors, fixes, counts = check(args.kind, data)
        if args.write:
            if not args.file:
                print(json.dumps({"ok": False, "errors": ["--write requires --file"], "fixes": fixes, "counts": counts}, ensure_ascii=False))
                return 1
            try:
                Path(args.file).write_text(_dump_yaml(data), "utf-8")
            except OSError as e:
                print(json.dumps({"ok": False, "errors": [f"cannot write {args.file}: {e}"], "fixes": fixes, "counts": counts}, ensure_ascii=False))
                return 1
            # Recompute errors on the mutated doc; keep first-pass fixes in the report.
            errors, fixes2, counts = check(args.kind, data)
            seen = set(fixes)
            for f in fixes2:
                if f not in seen:
                    fixes.append(f)
                    seen.add(f)
    except Exception as e:
        print(json.dumps({"ok": False, "errors": [f"check failed: {e}"], "fixes": [], "counts": {"skills": 0, "heroes": 0}}, ensure_ascii=False))
        return 1

    ok = not errors
    print(json.dumps({"ok": ok, "errors": errors, "fixes": fixes, "counts": counts}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
