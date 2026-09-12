"""
Interactive CLI for managing data overrides.

Supports:
  - Quick add: paste raw text to add skills, heroes, or both at once (default)
  - Modify existing skills via natural language instructions
  - Recompile override skills from their raw_text

Default LLM driver is headless OMP (`@smol`). Pass `--backend openrouter`
to use OpenRouter instead.

Usage:
    python script/override.py                 # quick add (skills/heroes/mixed)
    python script/override.py --modify-skill
    python script/override.py --recompile
"""

import argparse
import re
import sys
import yaml

from llm_backend import (
    DEFAULT_BACKEND,
    prepare_task_dir,
    resolve_backend,
    resolve_model,
    run_omp_agent,
)
from llm_core import (
    COMMON_RULES, SKILL_OUTPUT_FORMAT,
    call_llm, parse_llm_output, autofix_frontend, load_overrides,
    validate_skill_entry, validate_entry_quality,
)
from paths import (
    OVERRIDES_YAML,
    SKILLS_CANONICAL, TRAITS_CANONICAL,
)

BACK_CMD = "<"

def _omp_parse(kind: str, raw_input: str, task_body: str, model: str, timeout: int = 600) -> dict:
    task_dir = prepare_task_dir(kind, raw_input, task_body)
    return run_omp_agent(task_dir=task_dir, model=model, timeout=timeout)


def save_overrides(data: dict):
    OVERRIDES_YAML.parent.mkdir(parents=True, exist_ok=True)
    with open(OVERRIDES_YAML, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


class GoBack(Exception):
    """Raised when user types '<' to go back to previous step."""


def load_existing_skills() -> dict:
    """Load canonical skills for reference during modifications."""
    if SKILLS_CANONICAL.exists():
        data = yaml.safe_load(SKILLS_CANONICAL.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    return {}


def load_existing_traits() -> dict:
    """Load canonical traits for lookup during hero creation."""
    if TRAITS_CANONICAL.exists():
        data = yaml.safe_load(TRAITS_CANONICAL.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    return {}


def _check_back(val: str):
    if val == BACK_CMD:
        raise GoBack()


def _confirm_overwrite(name: str, overrides: dict) -> bool:
    """If skill already exists in overrides, ask user whether to overwrite. Returns True to proceed."""
    existing = overrides.get("skills", {}).get(name)
    if not existing:
        return True
    print(f"\n  [warn] '{name}' already exists in overrides:")
    print(f"    type: {existing.get('type', '?')}  rarity: {existing.get('rarity', '?')}")
    desc = existing.get("description", "")
    if desc:
        print(f"    description: {desc[:80]}{'...' if len(desc) > 80 else ''}")
    return prompt_confirm(f"  Overwrite '{name}'?", default=False)


def prompt_input(label: str, required: bool = True, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        val = input(f"  {label}{suffix}: ").strip()
        _check_back(val)
        if not val and default:
            return default
        if val or not required:
            return val
        print(f"  (required, type '<' to go back)")


def prompt_choice(label: str, choices: list[str], default: str = "") -> str:
    choices_str = "/".join(choices)
    suffix = f" [{default}]" if default else ""
    while True:
        val = input(f"  {label} ({choices_str}){suffix}: ").strip()
        _check_back(val)
        if not val and default:
            return default
        if val in choices:
            return val
        print(f"  please choose: {choices_str} (type '<' to go back)")


def prompt_confirm(label: str, default: bool = True) -> bool:
    suffix = "[Y/n]" if default else "[y/N]"
    val = input(f"  {label} {suffix}: ").strip().lower()
    if val == BACK_CMD:
        raise GoBack()
    if not val:
        return default
    return val in ("y", "yes")


def find_skill(name: str) -> dict | None:
    """Check if a skill exists in translated data or overrides."""
    skills = load_existing_skills()
    for key, data in skills.items():
        if key == name or data.get("name") == name:
            return data
    overrides = load_overrides()
    for key, data in overrides.get("skills", {}).items():
        if key == name or data.get("name") == name:
            return data
    return None


def find_trait(name: str) -> dict | None:
    """Check if a trait exists in translated data. Try both CHT name and JP key."""
    traits = load_existing_traits()
    # Try as JP key
    if name in traits:
        return traits[name]
    # Try as CHT name
    for key, data in traits.items():
        if data.get("name") == name:
            return data
    return None


# ---------------------------------------------------------------------------
# Modify Skill
# ---------------------------------------------------------------------------

MODIFY_TASK_RULES = """\
Rules:
1. If the instruction is ambiguous or unclear (e.g., which field to change, base or max, etc.), output ONLY:
   ```yaml
   _rejected: true
   reason: "<explanation of what's unclear, in Traditional Chinese>"
   ```
2. If the instruction is clear, output ONLY the fields that need to change as a YAML dict.
   - Use the same field names and structure as the original skill.
   - For nested fields like vars, only include the changed sub-fields.
   - All text must be in Traditional Chinese."""


def _build_modify_prompt(skill_yaml: str, instruction: str) -> str:
    return f"""\
You are a game data editor for 信長之野望：真戰 (Nobunaga's Ambition: Shinsei).

{COMMON_RULES}

Below is the current skill data in YAML format:

```yaml
{skill_yaml}
```

The user wants to modify this skill with the following instruction:
"{instruction}"

{MODIFY_TASK_RULES}"""


def do_modify_skill(model: str, backend: str):
    skills = load_existing_skills()
    if not skills:
        print("[error] No translated skills found. Run llm_translate.py first.")
        return

    print("\n=== Modify Existing Skill ===")
    skill_name = prompt_input("Skill name (CHT or JP)")

    # Find the skill
    target_key = None
    target_data = None
    for key, data in skills.items():
        if key == skill_name or data.get("name") == skill_name:
            target_key = key
            target_data = data
            break

    # Also check overrides
    overrides = load_overrides()
    if target_key is None:
        for key, data in overrides.get("skills", {}).items():
            if key == skill_name or data.get("name") == skill_name:
                target_key = key
                target_data = data
                break

    if target_key is None:
        print(f"[error] Skill '{skill_name}' not found.")
        return

    print(f"\n  Found: {target_key}")
    print(f"  Name: {target_data.get('name', target_key)}")
    print(f"  Type: {target_data.get('type', '?')}")
    desc = target_data.get('description', '')
    print(f"  Description: {desc[:80]}{'...' if len(desc) > 80 else ''}")

    instruction = prompt_input("\nModification instruction (natural language)")

    skill_yaml = yaml.dump(
        {target_key: target_data},
        allow_unicode=True, default_flow_style=False, sort_keys=False,
    )
    prompt = _build_modify_prompt(skill_yaml, instruction)

    raw = ""
    try:
        if backend == "omp":
            print(f"\n[llm] Processing via omp {model}…")
            task_body = (
                prompt
                + "\n\nWrite the result to output.yaml in this task directory as kind `patch`."
            )
            result = _omp_parse("patch", skill_yaml, task_body, model)
        else:
            print("\n[llm] Processing modification...")
            raw = call_llm(prompt, model=model)
            result = parse_llm_output(raw)
    except Exception as e:
        print(f"[error] LLM call failed: {e}")
        return

    if result is None:
        print("[error] Failed to parse LLM response.")
        if raw:
            print(f"  Raw output:\n{raw[:500]}")
        return

    if result.get("_rejected"):
        print(f"\n[rejected] {result.get('reason', 'unknown reason')}")
        return

    print("\n[preview] Changes to apply:")
    print(yaml.dump(result, allow_unicode=True, default_flow_style=False, sort_keys=False))

    if not prompt_confirm("Apply these changes?"):
        print("[cancelled]")
        return

    overrides = load_overrides()
    overrides.setdefault("skills", {})
    existing = overrides["skills"].get(target_key, {})
    # Deep merge new changes into existing overrides for this skill
    for k, v in result.items():
        if isinstance(v, dict) and isinstance(existing.get(k), dict):
            existing[k].update(v)
        else:
            existing[k] = v
    overrides["skills"][target_key] = existing
    save_overrides(overrides)
    print(f"[done] Override saved for '{target_key}' in {OVERRIDES_YAML}")


# ---------------------------------------------------------------------------
# Quick Add (unified: skills, heroes, or mixed)
# ---------------------------------------------------------------------------


def _collect_raw_input() -> str:
    """Collect raw text from user as a single block.
    Returns the full pasted text. LLM handles splitting into individual items."""
    print("  Paste all items (two blank lines or '.' to finish, '<' to cancel):\n")
    all_lines = []
    blank_count = 0
    while True:
        try:
            line = input("  > ")
        except EOFError:
            break
        if line.strip() == BACK_CMD:
            return ""
        if line.strip() == ".":
            break
        if not line.strip():
            blank_count += 1
            if blank_count >= 2:
                break
            all_lines.append("")
            continue
        blank_count = 0
        all_lines.append(line)

    return "\n".join(all_lines).strip()


def _flatten_skill_entry(entry: dict) -> dict:
    """Flatten LLM output (vars/text/battle) into override format."""
    text = entry.get("text", {})
    result = {}
    if isinstance(text, dict):
        for k, v in text.items():
            result[k] = v
    if entry.get("vars"):
        result["vars"] = entry["vars"]
    if entry.get("battle"):
        result["battle"] = entry["battle"]
    return result


def _ask_skill_metadata(name: str, result: dict) -> bool:
    """Ask user for metadata LLM couldn't determine. Modifies result in place.
    Returns False if user wants to go back (skip this item)."""
    try:
        if not result.get("is_event_skill"):
            if prompt_confirm(f"  Is '{name}' an event skill (事件戰法)?", default=False):
                result["is_event_skill"] = True

        if not result.get("is_event_skill"):
            if not result.get("unique_hero"):
                uh = prompt_input(f"  Unique hero for '{name}' (固有武將, empty if teachable)", required=False)
                if uh:
                    result["unique_hero"] = uh
                    result["is_unique"] = True
            if not result.get("unique_hero") and not result.get("source_hero"):
                sh = prompt_input(f"  Source hero for '{name}' (傳承者, empty if none)", required=False)
                if sh:
                    result["source_hero"] = sh
        return True
    except GoBack:
        return False


_HERO_MARKER_RE = re.compile(r"武將名\s*[:：]\s*(\S+)")


def _looks_like_skill_in_raw(name: str, raw_paste: str) -> bool:
    """True if `name` appears in raw_paste followed by a skill-shaped header
    (e.g. `(S) 種類：...`). A trait-shaped occurrence (e.g. `name: 描述`) returns False."""
    for m in re.finditer(re.escape(name), raw_paste):
        window = raw_paste[m.end():m.end() + 60]
        if re.search(r"\s*\([SAB]\)\s*種類", window):
            return True
    return False


def _extract_trait_description(name: str, entry: dict, raw_paste: str) -> str:
    """Recover the trait's plain description from the entry's raw_text or raw_paste."""
    raw = ""
    if isinstance(entry, dict):
        text = entry.get("text")
        if isinstance(text, dict):
            raw = text.get("raw_text", "") or ""
        raw = raw or entry.get("raw_text", "") or entry.get("description", "") or ""
    for sep in (":", "："):
        prefix = f"{name}{sep}"
        if raw.startswith(prefix):
            return raw[len(prefix):].strip()
    if raw:
        return raw.strip()
    m = re.search(
        re.escape(name) + r"\s*[:：]\s*(.+?)(?=\s+\S+\s*[:：]|\s+\S+\s+\([SAB]\)|武將名|$)",
        raw_paste,
    )
    return m.group(1).strip() if m else ""


def _find_hero_for_trait(trait_name: str, raw_paste: str, hero_names: list[str]) -> str | None:
    """The hero a trait belongs to is the next `武將名:` after it in raw_paste.
    Falls back to the sole hero when there's only one."""
    m = re.search(re.escape(trait_name), raw_paste)
    if not m:
        return hero_names[0] if len(hero_names) == 1 else None
    hero_m = _HERO_MARKER_RE.search(raw_paste, m.end())
    if not hero_m:
        return hero_names[0] if len(hero_names) == 1 else None
    candidate = hero_m.group(1).strip()
    return candidate if candidate in hero_names else (hero_names[0] if len(hero_names) == 1 else None)


def _reclassify_traits_as_skills(
    parsed_keys: list[str],
    parsed_values: list[dict],
    is_hero_flags: list[bool],
    raw_paste: str,
) -> tuple[list[str], list[dict], list[bool], int]:
    """Detect trait-shaped entries misclassified under skills and move them into the
    matching hero's `traits` list. Returns filtered (keys, values, flags, reclassified_count)."""
    hero_names = [k for k, f in zip(parsed_keys, is_hero_flags) if f]
    if not hero_names:
        return parsed_keys, parsed_values, is_hero_flags, 0

    new_keys: list[str] = []
    new_values: list[dict] = []
    new_flags: list[bool] = []
    traits_by_hero: dict[str, list[dict]] = {}

    for name, entry, is_hero in zip(parsed_keys, parsed_values, is_hero_flags):
        if is_hero or _looks_like_skill_in_raw(name, raw_paste):
            new_keys.append(name)
            new_values.append(entry)
            new_flags.append(is_hero)
            continue
        hero = _find_hero_for_trait(name, raw_paste, hero_names)
        if not hero:
            print(f"  [warn] '{name}' looks like a trait but no matching hero — leaving under skills")
            new_keys.append(name)
            new_values.append(entry)
            new_flags.append(False)
            continue
        traits_by_hero.setdefault(hero, []).append({
            "name": name,
            "description": _extract_trait_description(name, entry, raw_paste),
            "active": True,
        })
        print(f"  [reclass] '{name}' moved from skills → traits of '{hero}'")

    for name, entry, is_hero in zip(new_keys, new_values, new_flags):
        if is_hero and name in traits_by_hero and isinstance(entry, dict):
            entry.setdefault("traits", []).extend(traits_by_hero[name])

    return new_keys, new_values, new_flags, sum(len(v) for v in traits_by_hero.values())


def do_quick_add(model: str, backend: str):
    print("\n=== Quick Add ===")
    print("  1. Skills (default)")
    print("  2. Heroes")
    print("  3. Mixed (skills + heroes)")
    mode = prompt_input("Mode", default="1")

    if mode not in ("1", "2", "3"):
        print("[error] Invalid mode")
        return

    raw_paste = _collect_raw_input()
    if not raw_paste:
        print("[cancelled]")
        return

    # --- Build prompt: send entire paste as one block, let LLM split ---
    if mode == "1":
        user = f"""\
The following is raw skill data (already in Traditional Chinese).
Parse ALL skills and output each as a separate top-level YAML key with `vars`, `text`, and `battle` sections.

IMPORTANT: In the `text` section, include a `raw_text` field containing the EXACT original text
from the input that describes this skill (copy verbatim, do not paraphrase or reformat).

---
{raw_paste}
---
Output YAML: each skill name as a top-level key, containing `vars`, `text` (with `raw_text`), and `battle` sections.
Parse ALL skills in the input above."""
        system = OVERRIDE_SYSTEM_PROMPT
    elif mode == "2":
        user = f"""\
Parse all heroes below. Extract: name, rarity (1-5), cost, faction, clan, gender,
stats (lea/val/int/pol/cha/spd), unique_skill, teachable_skill, assembly_skill, and traits.

Stat key mapping: 統率→lea, 武勇→val, 智略→int, 政務→pol, 魅力→cha, 速度→spd.
If 評定衆戰法/傳承戰法 is 無 or empty, use empty string "".

Each trait: {{name, description, active: true}} (include vars only if the description contains a scaling number).

---
{raw_paste}
---
Output YAML: each hero name as top-level key with all fields."""
        system = OVERRIDE_SYSTEM_PROMPT
    else:  # mode == "3"
        user = f"""\
The input below contains MULTIPLE heroes with their skills AND traits (already in Traditional Chinese).
Parse every item into ONE YAML document with EXACTLY two top-level keys: `skills:` and `heroes:`.

### Output structure (mandatory — no other top-level keys allowed):

```
skills:
  <skill CHT name>:
    vars: ...
    text: ...   # include raw_text (exact original skill text, verbatim)
    battle: ...
  # ... one entry per full skill ...
heroes:
  <hero CHT name>:
    name: <str CHT>
    rarity: <int 1-5>
    cost: <int>
    faction: <str, from 勢力>
    clan: <str, from 氏族>
    gender: 男|女
    stats: {{lea: <num>, val: <num>, int: <num>, pol: <num>, cha: <num>, spd: <num>}}
    unique_skill: <CHT name, from 固有戰法>
    teachable_skill: <CHT name or "", from 傳承戰法>
    assembly_skill: <CHT name or "", from 評定衆戰法>
    traits:
      - {{name: <str>, description: <str>, active: true}}
      # ... one entry per trait belonging to THIS hero ...
  # ... one entry per hero ...
```

### How to classify each input item:

**SKILL** — has rarity marker `(S)/(A)/(B)` AND fields `種類:`, `發動機率:`, `效果:`.
  Place under `skills:` with the full `vars`/`text`/`battle` structure.

**HERO** — introduced by `武將名:` followed by stats (稀有度/Cost/勢力/氏族/性別/統率/武勇/智略/政務/魅力/速度)
  and skill refs (固有戰法/傳承戰法/評定衆戰法).
  Place under `heroes:`. Stat key map: 統率→lea, 武勇→val, 智略→int, 政務→pol, 魅力→cha, 速度→spd.
  Keep decimals as-is. If 傳承戰法 or 評定衆戰法 is 無/empty, use "".

**TRAIT** — short `名稱: 描述` WITHOUT `種類:`/`發動機率:` markers.
  Traits belong to the hero announced by the NEXT `武將名:` marker (same block).
  Place each trait ONLY inside that hero's `traits` list. Never put a trait as a key
  under `skills:` or as a top-level `heroes:` entry.

### Concrete example — VERY COMMON mistake:

If the input contains:
  弓槍術II: 部隊的足輕、弓兵等級上升2級
  武將名: 阿初
  ...

WRONG output (弓槍術II emitted as a skill):
  skills:
    弓槍術II: {{vars: ..., text: ..., battle: ...}}    # ← WRONG, this is a trait
  heroes:
    阿初: {{traits: []}}                                # ← missing the trait

CORRECT output (弓槍術II nested under 阿初):
  skills: {{}}  # no 弓槍術II key here
  heroes:
    阿初:
      traits:
        - {{name: 弓槍術II, description: 部隊的足輕、弓兵等級上升2級, active: true}}

Rule of thumb: if an input line has NO `(S)/(A)/(B)` marker and NO `種類:` field,
it is a trait. It goes under `heroes.<name>.traits`, never under `skills:`.

### Input:
---
{raw_paste}
---

Remember: the output has EXACTLY two top-level keys (`skills`, `heroes`). Any trait emitted
as a top-level key or as a skill is an error."""
        system = OVERRIDE_SYSTEM_PROMPT

    kind = {"1": "skill", "2": "hero", "3": "mixed"}[mode]
    raw_resp = ""
    try:
        if backend == "omp":
            print(f"\n[llm] Processing via omp {model}…")
            task_body = (
                f"{system}\n\n{user}\n\n"
                f"Write the result to output.yaml in this task directory as kind `{kind}`."
            )
            parsed = _omp_parse(kind, raw_paste, task_body, model)
        else:
            print("\n[llm] Processing...")
            raw_resp = call_llm(user, system_prompt=system, model=model, timeout=300)
            parsed = parse_llm_output(raw_resp)
    except Exception as e:
        print(f"[error] LLM call failed: {e}")
        return

    if parsed is None:
        print("[error] Failed to parse LLM response.")
        if raw_resp:
            print(f"  Raw output:\n{raw_resp[:500]}")
        return

    # Mode 3 expects a structured `{skills: {...}, heroes: {...}}` response.
    # Fall back to flat + per-entry detection if the LLM ignored the format.
    if mode == "3":
        skills_block = parsed.get("skills") if isinstance(parsed.get("skills"), dict) else None
        heroes_block = parsed.get("heroes") if isinstance(parsed.get("heroes"), dict) else None
        if skills_block is None and heroes_block is None:
            print("  [warn] LLM did not use structured skills/heroes groups — falling back to per-entry detection")
            parsed_keys = list(parsed.keys())
            parsed_values = list(parsed.values())
            is_hero_flags = [isinstance(v, dict) and "stats" in v for v in parsed_values]
        else:
            skills_block = skills_block or {}
            heroes_block = heroes_block or {}
            parsed_keys = list(skills_block.keys()) + list(heroes_block.keys())
            parsed_values = list(skills_block.values()) + list(heroes_block.values())
            is_hero_flags = [False] * len(skills_block) + [True] * len(heroes_block)
        parsed_keys, parsed_values, is_hero_flags, reclassified = _reclassify_traits_as_skills(
            parsed_keys, parsed_values, is_hero_flags, raw_paste,
        )
        if reclassified:
            print(f"  [reclass] {reclassified} trait(s) moved into hero traits lists")
    else:
        parsed_keys = list(parsed.keys())
        parsed_values = list(parsed.values())
        is_hero_flags = [mode == "2"] * len(parsed_keys)

    # Confirm count — warn but continue if user says no
    count_warning = False
    print(f"\n  LLM parsed {len(parsed_keys)} item(s):")
    for i, k in enumerate(parsed_keys, 1):
        tag = " [hero]" if is_hero_flags[i - 1] else ""
        print(f"    {i}. {k}{tag}")
    if not prompt_confirm(f"  {len(parsed_keys)} items, correct?", default=True):
        count_warning = True
        print("  [warn] Count mismatch noted — will warn at the end. Continuing...")

    # --- Validate and collect good/bad ---
    good: list[tuple[str, dict, dict]] = []  # (name, entry, result)
    bad: list[tuple[str, dict, str]] = []  # (name, entry, errors)

    for i, (name, entry) in enumerate(zip(parsed_keys, parsed_values)):
        is_hero_entry = is_hero_flags[i]

        if is_hero_entry:
            if not isinstance(entry, dict) or not entry.get("name"):
                print(f"  [INVALID HERO] {name}: missing name")
                bad.append((name, entry, "missing name"))
                continue
            print(f"  [VALID HERO] {name}")
            result = entry
        else:
            errors = validate_skill_entry(entry)
            if errors:
                print(f"  [INVALID] {name}: {'; '.join(errors)}")
                bad.append((name, entry, "; ".join(errors)))
                continue
            quality = validate_entry_quality(entry)
            if quality:
                print(f"  [QUALITY] {name}: {'; '.join(quality)}")
            else:
                print(f"  [VALID] {name}")
            result = _flatten_skill_entry(entry)

        good.append((name, entry, result))

    # --- Retry bad skill-shaped ones with error feedback ---
    bad_skills = [
        (n, e, err) for n, e, err in bad
        if not (isinstance(e, dict) and "stats" in e)
    ]
    if bad_skills and mode in ("1", "3"):
        print(f"\n[retry] {len(bad_skills)} failed skill(s)...")
        error_summary = "\n".join(f"  {name}: {errs}" for name, _, errs in bad_skills)
        retry_user = f"""\
Previous attempt had errors:
{error_summary}

Fix these errors. Re-parse these skills from the original input:

---
{raw_paste}
---
Only output the failed skills: {', '.join(name for name, _, _ in bad_skills)}"""

        try:
            if backend == "omp":
                retry_body = (
                    f"{system}\n\n{retry_user}\n\n"
                    "Write the result to output.yaml in this task directory as kind `skill`."
                )
                retry_parsed = _omp_parse("skill", raw_paste, retry_body, model)
            else:
                raw_resp = call_llm(retry_user, system_prompt=system, model=model, timeout=300)
                retry_parsed = parse_llm_output(raw_resp)
        except Exception as e:
            print(f"  [retry failed] {e}")
            retry_parsed = None

        if retry_parsed:
            for rname, rentry in retry_parsed.items():
                errors = validate_skill_entry(rentry)
                if errors:
                    print(f"  [STILL BAD] {rname}: {'; '.join(errors)}")
                    continue
                quality = validate_entry_quality(rentry)
                if quality:
                    print(f"  [QUALITY] {rname}: {'; '.join(quality)}")
                else:
                    print(f"  [FIXED] {rname}")
                result = _flatten_skill_entry(rentry)
                good.append((rname, rentry, result))

    if not good:
        print("\n[done] No valid items to add.")
        return

    # --- Check hero skill references (issue 2) ---
    if mode in ("2", "3"):
        existing_skills = load_existing_skills()
        ov = load_overrides()
        override_skills = ov.get("skills", {})
        # Collect all known skill names: keys + translated names + names from this batch
        all_skill_names = set(existing_skills.keys()) | set(override_skills.keys())
        for sk in existing_skills.values():
            if isinstance(sk, dict) and sk.get("text", {}).get("name"):
                all_skill_names.add(sk["text"]["name"])
        for sk in override_skills.values():
            if isinstance(sk, dict) and sk.get("name"):
                all_skill_names.add(sk["name"])
        # Also include skills from this batch
        for gname, _, gresult in good:
            all_skill_names.add(gname)
            if isinstance(gresult, dict) and gresult.get("name"):
                all_skill_names.add(gresult["name"])

        for name, entry, result in good:
            is_hero = "stats" in result or mode == "2"
            if not is_hero:
                continue
            for field in ("unique_skill", "teachable_skill"):
                sk = result.get(field, "")
                if sk and sk not in all_skill_names:
                    print(f"  [warn] Hero '{name}' references skill '{sk}' ({field}) — not found")

    # --- Confirm each item ---
    overrides = load_overrides()
    overrides.setdefault("skills", {})
    overrides.setdefault("heroes", {})
    added = 0
    accept_all = False
    overwrite_all = False

    print(f"\n  {len(good)} item(s) ready. Confirm each: y=accept, n=skip, yy=accept all remaining")

    for seq, (name, entry, result) in enumerate(good):
        print(f"\n--- [{seq+1}/{len(good)}] {name} ---")

        # Always ask for metadata (even under yy)
        if mode in ("1", "3") and isinstance(entry, dict) and "battle" in entry:
            if not _ask_skill_metadata(name, result):
                print(f"  [skipped]")
                continue

        if not accept_all:
            # Show preview before asking
            print(yaml.dump({name: result}, allow_unicode=True, default_flow_style=False, sort_keys=False))

            # Check overwrite
            if not overwrite_all:
                existing = overrides.get("skills", {}).get(name) or overrides.get("heroes", {}).get(name)
                if existing:
                    desc = existing.get("description", "")
                    print(f"  [warn] '{name}' already exists (type: {existing.get('type', '?')}, rarity: {existing.get('rarity', '?')})")
                    if desc:
                        print(f"    description: {desc[:80]}{'...' if len(desc) > 80 else ''}")
                    ow = prompt_input("  Overwrite? (y/n/yy=overwrite all)", default="n").strip().lower()
                    if ow == "yy":
                        overwrite_all = True
                    elif ow != "y":
                        print(f"  [skipped]")
                        continue

            answer = prompt_input("  Accept? (y/n/yy)", default="y").strip().lower()
            if answer == "yy":
                accept_all = True
            elif answer != "y":
                print(f"  [skipped]")
                continue
        else:
            # accept_all: still check overwrite
            if not overwrite_all:
                existing = overrides.get("skills", {}).get(name) or overrides.get("heroes", {}).get(name)
                if existing:
                    print(f"  [warn] '{name}' already exists — skipped (use overwrite-all to force)")
                    continue

        # Save
        is_hero = mode == "2" or (mode == "3" and "stats" in result)
        if is_hero:
            result["_action"] = "add"
            overrides["heroes"][name] = result
        else:
            result["_action"] = "add"
            overrides["skills"][name] = result
        added += 1
        print(f"  [added]")

    if added:
        save_overrides(overrides)

    # Final summary
    warnings = []
    if count_warning:
        warnings.append("LLM item count was flagged as incorrect")
    if bad:
        still_bad = [name for name, _, _ in bad if not any(n == name for n, _, _ in good)]
        if still_bad:
            warnings.append(f"{len(still_bad)} item(s) failed validation: {', '.join(still_bad)}")

    print(f"\n[done] {added}/{len(good)} item(s) added to {OVERRIDES_YAML}")
    if warnings:
        for w in warnings:
            print(f"  [warn] {w}")



# ---------------------------------------------------------------------------
# Recompile overrides
# ---------------------------------------------------------------------------

OVERRIDE_SYSTEM_PROMPT = f"""\
You are a game data formatter for 信長之野望：真戰 (Nobunaga's Ambition: Shinsei).
The input is already in Traditional Chinese — do NOT translate, just extract and reformat.

{COMMON_RULES}

{SKILL_OUTPUT_FORMAT}"""


def do_recompile(model: str, name_filter: str | None = None, dry_run: bool = False, backend: str = DEFAULT_BACKEND):
    """Recompile override skills from raw_text into current structured format."""
    overrides = load_overrides()
    skills = overrides.get("skills", {})

    # Find skills with raw_text that need recompiling
    targets = {}
    for key, skill in skills.items():
        if skill.get("_action") != "add":
            continue
        raw = skill.get("raw_text")
        if not raw:
            continue
        if name_filter and name_filter not in key:
            continue
        targets[key] = skill

    if not targets:
        print("[recompile] No skills with raw_text found.")
        if not name_filter:
            print("  Add raw_text field to override skills to enable recompiling.")
        return

    print(f"[recompile] {len(targets)} skills to process with {model}")

    # Build batch prompt
    blocks = []
    for i, (key, skill) in enumerate(targets.items(), 1):
        meta_parts = []
        if skill.get("is_event_skill"):
            meta_parts.append("Event skill (事件戰法)")
        if skill.get("unique_hero"):
            meta_parts.append(f"Unique to: {skill['unique_hero']}")
        if skill.get("source_hero"):
            meta_parts.append(f"Teachable from: {skill['source_hero']}")
        meta = "; ".join(meta_parts) or "none"

        blocks.append(f"""\
Skill {i}:
  name: {skill.get('name', key)}
  type: {skill.get('type', 'unknown')}
  rarity: {skill.get('rarity', 'S')}
  target: {skill.get('target', '')}
  activation_rate: {skill.get('activation_rate', '')}
  metadata: {meta}
  raw_text: |
    {skill['raw_text']}""")

    user = f"""\
Reformat these {len(targets)} skills into the current structured format.
Each already has a Chinese description — do NOT translate, just reformat.

{chr(10).join(blocks)}

---
Output YAML: each skill name as a top-level key, containing `vars`, `text`, and `battle` sections."""

    raw = ""
    try:
        if backend == "omp":
            print(f"[llm] Processing via omp {model}…")
            task_body = (
                f"{OVERRIDE_SYSTEM_PROMPT}\n\n{user}\n\n"
                "Write the result to output.yaml in this task directory as kind `skill`."
            )
            parsed = _omp_parse("skill", user, task_body, model)
        else:
            print(f"[llm] Sending {len(targets)} skills...")
            raw = call_llm(user, system_prompt=OVERRIDE_SYSTEM_PROMPT, model=model, timeout=300)
            parsed = parse_llm_output(raw)
    except Exception as e:
        print(f"[error] LLM call failed: {e}")
        return

    if not parsed:
        print("[error] Failed to parse LLM output")
        if raw:
            print(f"  Raw output:\n{raw[:500]}")
        return

    parsed_values = list(parsed.values())
    updated = 0

    for i, (key, skill) in enumerate(targets.items()):
        entry = parsed.get(key) or parsed.get(skill.get("name", ""))
        if not entry and i < len(parsed_values):
            entry = parsed_values[i]
        if not entry:
            print(f"  MISSING: {key}")
            continue

        # Auto-fix (pass parent so vars-aware fixes apply)
        text = entry.get("text", {})
        if isinstance(text, dict):
            fixes = autofix_frontend(entry)
            if fixes:
                print(f"  [autofix] {key}: {'; '.join(fixes)}")

        # Preview
        print(f"\n{'='*50}")
        print(f"  {key}:")
        print(yaml.dump(entry, allow_unicode=True, default_flow_style=False, sort_keys=False, indent=2))

        if dry_run:
            updated += 1
            continue

        if not prompt_confirm(f"  Apply recompile for '{key}'?"):
            print(f"  [skip] {key}")
            continue

        # Merge back: keep raw_text + metadata, update structured fields
        new_skill = {"_action": "add", "raw_text": skill["raw_text"]}
        # Preserve metadata
        for meta_key in ("is_event_skill", "unique_hero", "is_unique", "source_hero"):
            if meta_key in skill:
                new_skill[meta_key] = skill[meta_key]

        # Flatten text section into top level (override format is flat)
        if isinstance(text, dict):
            for tk, tv in text.items():
                new_skill[tk] = tv
        # Keep vars and battle at top level
        if entry.get("vars"):
            new_skill["vars"] = entry["vars"]
        if entry.get("battle"):
            new_skill["battle"] = entry["battle"]

        overrides["skills"][key] = new_skill
        updated += 1

    if not dry_run and updated:
        save_overrides(overrides)
    print(f"\n[recompile] {updated}/{len(targets)} skills processed")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    p = argparse.ArgumentParser(description="Interactive override manager for game data")
    p.add_argument("--modify-skill", action="store_true", help="Modify an existing skill")
    p.add_argument("--recompile", action="store_true", help="Recompile override skills from raw_text")
    p.add_argument("--dry-run", action="store_true", help="Preview recompile without saving")
    p.add_argument("--name", help="Filter by name (for --recompile)")
    p.add_argument("--backend", choices=("omp", "openrouter"), default=None,
                   help="LLM driver (default: omp; auto openrouter if --model is vendor/name)")
    p.add_argument("--model", default=None,
                   help="OMP role/id (default @smol) or OpenRouter model")
    args = p.parse_args()
    backend = resolve_backend(args.backend, args.model)
    model = resolve_model(backend, args.model)

    if args.recompile:
        do_recompile(model, name_filter=args.name, dry_run=args.dry_run, backend=backend)
        return

    if args.modify_skill:
        do_modify_skill(model, backend)
    else:
        do_quick_add(model, backend)


if __name__ == "__main__":
    main()
