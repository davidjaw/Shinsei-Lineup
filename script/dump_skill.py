# /// script
# dependencies = ["pyyaml"]
# ///
"""Dump one skill's descriptions (JP + CHT) and meta.

Usage: uv run script/dump_skill.py <key>
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "data" / "skills.yaml"


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: dump_skill.py <skill-key>")
    key = sys.argv[1]
    d = yaml.safe_load(SKILLS.read_text(encoding="utf-8"))
    e = d.get(key)
    if not e:
        sys.exit(f"skill not found: {key}")
    raw, text = e.get("raw", {}), e.get("text", {})
    print(f"# {text.get('name', key)}  [key: {key}]")
    print(f"rarity={raw.get('rarity')} type={text.get('type')} "
          f"target={raw.get('target')} activation={raw.get('activation_rate')} "
          f"source={raw.get('source_hero')}")
    print("\n## JP description\n" + str(raw.get("description", "")))
    print("\n## CHT description\n" + str(text.get("description", "")))


if __name__ == "__main__":
    main()
