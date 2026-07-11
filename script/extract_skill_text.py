# /// script
# dependencies = ["pyyaml"]
# ///
"""Extract ONLY skill name + description from data/skills.yaml.

Used to feed complexity-assessment subagents. Supports partitioning so
multiple agents can each inspect a slice of the full skill list.

Usage:
    uv run script/extract_skill_text.py                 # all skills
    uv run script/extract_skill_text.py --part 1/4       # partition 1 of 4
    uv run script/extract_skill_text.py --part 1/4 --json
"""
import argparse
import json
import sys
from pathlib import Path

import yaml

SKILLS = Path(__file__).resolve().parent.parent / "data" / "skills.yaml"


def load_entries():
    data = yaml.safe_load(SKILLS.read_text(encoding="utf-8"))
    out = []
    for key, entry in data.items():
        text = entry.get("text") or {}
        raw = entry.get("raw") or {}
        name = text.get("name") or raw.get("name") or key
        desc = text.get("description") or raw.get("description") or ""
        out.append({"key": key, "name": name, "description": desc.strip()})
    return out


def partition(items, part, total):
    return [it for i, it in enumerate(items) if i % total == (part - 1)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", help="N/M -> partition N of M (1-indexed)")
    ap.add_argument("--json", action="store_true", help="output JSON")
    args = ap.parse_args()

    entries = load_entries()
    if args.part:
        part, total = (int(x) for x in args.part.split("/"))
        entries = partition(entries, part, total)

    if args.json:
        json.dump(entries, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return

    for e in entries:
        print(f"### {e['name']}  [{e['key']}]")
        print(e["description"])
        print()

    print(f"--- {len(entries)} skills ---", file=sys.stderr)


if __name__ == "__main__":
    main()
