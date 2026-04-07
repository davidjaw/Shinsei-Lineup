"""
LLM-based skill translator and battle engine extractor.

Reads crawled YAML, sends skills to Gemini in batches for:
  1. Translation (JP → CHT) for frontend display
  2. Battle engine structured extraction (vars, triggers, effects)

Usage:
    python script/llm_translate.py [options]

Examples:
    python script/llm_translate.py --limit 3               # test 3 skills
    python script/llm_translate.py --name 武田之赤備         # single skill
    python script/llm_translate.py                          # all skills
    python script/llm_translate.py --force --limit 5        # re-process, overwrite cache + output
    python script/llm_translate.py --batch-size 3           # 3 skills per LLM call
    python script/llm_translate.py --model gemini-3.1-pro-preview
"""

import argparse
import json
import sys
import yaml
from pathlib import Path
from tqdm import tqdm

from claude_test import call_claude
from llm_core import (
    CANONICAL_STATUSES, COMMON_RULES, SKILL_TAGS, DEFAULT_MODEL,
    call_gemini, parse_llm_output, autofix_frontend,
    load_llm_cache, save_llm_cache, save_raw_cache,
)
from paths import (
    HEROES_CRAWLED, SKILLS_CRAWLED, TRAITS_CRAWLED,
    SKILLS_TRANSLATED, SKILLS_BATTLE,
    TRAITS_TRANSLATED, TRAITS_BATTLE,
    HEROES_TRANSLATED,
    TRANSLATION_FAILURES_JSON,
)
DEFAULT_BATCH_SIZE = 5

# In-process accumulator for failures across all process_* runs in a single
# invocation. Flushed to TRANSLATION_FAILURES_JSON in main().
_FAILURE_LOG: dict[str, list[dict]] = {"skills": [], "traits": [], "heroes": []}


def _record_failures(kind: str, failed: list[tuple[str, str]]):
    for name, err in failed:
        _FAILURE_LOG[kind].append({"name": name, "error": err})


def _write_failure_manifest():
    """Write a manifest with copy-pasteable suggested fixes for the admin.

    Always overwrites the file: an empty manifest is itself useful (signals
    "last run was clean"). The build is NOT failed here — check_data_integrity
    is the gatekeeper.
    """
    has_any = any(_FAILURE_LOG.values())
    # NOTE: do NOT suggest --force here. --force means "ignore cache and
    # re-call the LLM". For LLM-side failures the cache miss already forces a
    # call, so --force only burns extra quota. The admin can add --force
    # manually if they actually want to re-translate something that succeeded
    # but looks wrong.
    suggestions: list[str] = []
    for kind, items in _FAILURE_LOG.items():
        if not items:
            continue
        names = sorted({item["name"] for item in items})
        if len(names) == 1:
            suggestions.append(
                f'python3 script/llm_translate.py --{kind} --name "{names[0]}"'
            )
        else:
            suggestions.append(f"python3 script/llm_translate.py --{kind}")
    if suggestions:
        suggestions.append(
            "python3 script/build_frontend_data.py && python3 script/check_data_integrity.py"
        )

    manifest = {
        "ok": not has_any,
        "summary": {kind: len(items) for kind, items in _FAILURE_LOG.items()},
        "failures": _FAILURE_LOG,
        "suggested_actions": suggestions,
    }
    TRANSLATION_FAILURES_JSON.parent.mkdir(parents=True, exist_ok=True)
    TRANSLATION_FAILURES_JSON.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), "utf-8"
    )

    if has_any:
        total = sum(len(v) for v in _FAILURE_LOG.values())
        tqdm.write(f"\n[warn] {total} item(s) failed translation. Manifest: {TRANSLATION_FAILURES_JSON}")
        tqdm.write("[suggested actions — copy/paste to retry]")
        for s in suggestions:
            tqdm.write(f"  {s}")
    else:
        tqdm.write(f"\n[ok] No translation failures. Manifest: {TRANSLATION_FAILURES_JSON}")

BATTLE_EXAMPLE = """\
name: 軍神
type: 被動
vars:
  trigger_rate: 1.00
  charge_trigger_base: 0.30
  charge_trigger_max: 0.60
  damage_per_stack_base: 0.05
  damage_per_stack_max: 0.10
  max_charge: 12
trigger: always
rate: [$trigger_rate]
do:
  - trigger: afterAllyAction
    when:
      - type: allyActionType
        value: [attack, active, assault]
    to: self
    do:
      type: roll
      chance: $charge_trigger_base
      on_success:
        - to: self
          do:
            type: addStack
            key: god_of_war_charge
            value: 1
            max: $max_charge
bonus:
  commander:
    description: ...
    effects:
      - trigger: beforeHeroAction
        to: self
        do:
          type: addStack
          key: god_of_war_charge
          value: 1"""


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = f"""\
You are a game data translator and structured extractor for 信長之野望：真戰 (Nobunaga's Ambition: Shinsei).

{COMMON_RULES}

For EACH skill, output a YAML document under that skill's name as the top-level key, containing TWO sections:

## `frontend` — Translation for frontend rendering (JP → Traditional Chinese)
- Translate to Traditional Chinese (繁體中文)
- `rarity` must be just: S, A, or B
- `brief_description`: 15-25 chars, summarize the core mechanic without numbers. E.g., "會心增益，條件觸發對單體兵刃傷害並降低統率"
- `tags`: list from ONLY these allowed tags: """ + SKILL_TAGS + """
  Pick all that apply. E.g., [兵刃傷害, 單體傷害, 增益, 條件觸發, 降低屬性, 武勇系, 大將技]

## `battle` — Structured extraction for battle engine
- ALL text (including `bonus.commander.description`) must be in Traditional Chinese (繁體中文)
- Extract variables into `vars` following COMMON_RULES exactly (do not add base/max to fixed values, do not omit max from scaling values)
- Map effects to `do` blocks: trigger/when/to/do
- Effect types: damage, heal, buff, debuff, applyStatus, removeStatus, addStack, roll, sequence, conditional
- Trigger types: always, battleStart, turnStart, beforeAction, afterAction, beforeAttack, afterAttack, onDamaged, onHeal
- Target types: self, allySingle, allyMultiple, allyAll, enemySingle, enemyMultiple, enemyAll
- 大将技 → `bonus.commander`"""


def build_single_prompt(skill: dict) -> str:
    return f"""\
{SYSTEM_PROMPT}

---
Input skill:
name: {skill['name']}
type: {skill.get('type', 'unknown')}
rarity: {skill.get('rarity', '')}
target: {skill.get('target', '')}
activation_rate: {skill.get('activation_rate', '')}
source_hero: {skill.get('source_hero', '')}
description: |
  {skill.get('description', '')}
commander_bonus: {skill.get('commander_bonus', '') or 'none'}

---
Example frontend:
  name: 軍神
  type: 被動
  rarity: S
  target: 自己
  activation_rate: 100%
  description: >
    戰鬥中，以無法獲得{{status:亂舞}}狀態為代價，
    使友軍群體（{{var:ally_count}}人）有{{var:charge_trigger_rate}}機率（{{scale:武勇}}）使自身蓄力，
    普通攻擊傷害提高{{var:damage_per_stack}}（{{scale:武勇}}），最多疊{{var:max_charge}}次。
  brief_description: 犧牲亂舞，友軍蓄力提升普攻傷害
  tags: [增益, 被動觸發, 武勇系]
  vars:
    charge_trigger_rate:
      base: 0.30
      max: 0.60
      scale: 武勇
    damage_per_stack:
      base: 0.05
      max: 0.10
      scale: 武勇
    stat_debuff:
      base: 18
      max: 36
      type: flat
    max_charge: 12
    ally_count: 2

Example battle:
{BATTLE_EXAMPLE}

---
Output the YAML with skill name as top-level key, containing `frontend` and `battle`."""


def build_batch_prompt(skills: list[tuple[str, dict]]) -> str:
    skill_blocks = []
    for i, (name, skill) in enumerate(skills, 1):
        skill_blocks.append(f"""\
Skill {i}:
  name: {skill['name']}
  type: {skill.get('type', 'unknown')}
  rarity: {skill.get('rarity', '')}
  target: {skill.get('target', '')}
  activation_rate: {skill.get('activation_rate', '')}
  source_hero: {skill.get('source_hero', '')}
  description: |
    {skill.get('description', '')}
  commander_bonus: {skill.get('commander_bonus', '') or 'none'}""")

    joined = "\n\n".join(skill_blocks)

    return f"""\
{SYSTEM_PROMPT}

---
Input ({len(skills)} skills):

{joined}

---
Example frontend (for reference):
  name: 軍神
  type: 被動
  rarity: S
  target: 自己
  activation_rate: 100%
  description: >
    戰鬥中，以無法獲得{{status:亂舞}}狀態為代價，
    使友軍群體（{{var:ally_count}}人）有{{var:charge_trigger_rate}}機率（{{scale:武勇}}）使自身蓄力，
    普通攻擊傷害提高{{var:damage_per_stack}}（{{scale:武勇}}），最多疊{{var:max_charge}}次。
  brief_description: 犧牲亂舞，友軍蓄力提升普攻傷害
  tags: [增益, 被動觸發, 武勇系]
  vars:
    charge_trigger_rate:
      base: 0.30
      max: 0.60
      scale: 武勇
    max_charge: 12

Example battle (for reference):
{BATTLE_EXAMPLE}

---
Output YAML: each skill name as a top-level key, each containing `frontend` and `battle` sections.
Process ALL {len(skills)} skills above."""


# ---------------------------------------------------------------------------
# Trait Prompts
# ---------------------------------------------------------------------------

TRAIT_SYSTEM_PROMPT = f"""\
You are a game data translator and structured extractor for 信長之野望：真戰 (Nobunaga's Ambition: Shinsei).

{COMMON_RULES}

For EACH trait (特性), output YAML with the trait name as top-level key, containing TWO sections:

## `frontend` — Translation (JP → Traditional Chinese 繁體中文)
- `name`: translated trait name
- `description`: translated description.
- `vars`: dict of variables. Only if the trait has numeric values.

## `battle` — Structured extraction for battle engine (type: 特性)
- ALL text must be in Traditional Chinese
- `type`: always "特性"
- `vars`: same as frontend
- `trigger`: when it activates (battleStart, turnStart, beforeAction, etc.)
- `do`: structured effects using trigger/when/to/do pattern
- Effect types: damage, heal, buff, debuff, applyStatus, removeStatus, addStack, roll, sequence, conditional
- Target types: self, allySingle, allyMultiple, allyAll, enemySingle, enemyMultiple, enemyAll

For troop_affinity traits (兵種レベル増加), the battle section should simply be:
  type: 特性
  category: troop_affinity
  troop_type: <type>
  level: <number>"""


def build_trait_single_prompt(trait: dict) -> str:
    return f"""\
{TRAIT_SYSTEM_PROMPT}

---
Input trait:
name: {trait['name']}
category: {trait.get('category', 'skill_like')}
description: |
  {trait.get('description', '')}

---
Output YAML with trait name as top-level key, containing `frontend` and `battle`."""


def build_trait_batch_prompt(traits: list[tuple[str, dict]]) -> str:
    blocks = []
    for i, (name, trait) in enumerate(traits, 1):
        blocks.append(f"""\
Trait {i}:
  name: {trait['name']}
  category: {trait.get('category', 'skill_like')}
  description: |
    {trait.get('description', '')}""")

    joined = "\n\n".join(blocks)
    return f"""\
{TRAIT_SYSTEM_PROMPT}

---
Input ({len(traits)} traits):

{joined}

---
Output YAML: each trait name as top-level key, each containing `frontend` and `battle` sections.
Process ALL {len(traits)} traits above."""


# ---------------------------------------------------------------------------
# Hero Prompts
# ---------------------------------------------------------------------------

HERO_SYSTEM_PROMPT = """\
You are a translator for historical Japanese figure names from the game 信長之野望：真戰 (Nobunaga's Ambition: Shinsei).

Translate hero names, faction names, and clan names from Japanese to Traditional Chinese (繁體中文).

Key rules:
- Many names share the same kanji between JP and CHT, but some JP-specific kanji need conversion:
  黒→黑, 関→關, 豊→豐, 浅→淺, 広→廣, 竜→龍, 辺→邊, 桜→櫻, 沢→澤, 県→縣, 斎→齋, 滝→瀧, 弐→貳, 鉄→鐵, 従→從, 帯→帶, 徳→德, 条→條, 団→團, 覚→覺, 伝→傳, 予→預, 亜→亞, 斉→齊
- Preserve names that are already identical in both languages
- These are real historical figures from Japan's Sengoku period

Output ONLY valid YAML. No markdown fences. No explanation.
Each JP name as a top-level key, with `name`, `faction`, `clan` values."""


def build_hero_batch_prompt(heroes: list[tuple[str, str, str]]) -> str:
    blocks = []
    for i, (name, faction, clan) in enumerate(heroes, 1):
        blocks.append(f"  {name}: {{faction: {faction}, clan: {clan}}}")

    joined = "\n".join(blocks)
    return f"""\
{HERO_SYSTEM_PROMPT}

---
Input ({len(heroes)} heroes):
{joined}

---
Output YAML: each JP name as top-level key with `name`, `faction`, `clan` in Traditional Chinese.
Example:
黒田官兵衛:
  name: 黑田官兵衛
  faction: 豐臣
  clan: 黑田
Process ALL {len(heroes)} heroes above."""


# ---------------------------------------------------------------------------
# Parse & validate
# ---------------------------------------------------------------------------


def validate_skill_entry(data: dict) -> list[str]:
    """Validate a single skill's LLM output structure."""
    errors = []
    if not isinstance(data, dict):
        return ["not a dict"]

    fe = data.get("frontend")
    if not fe:
        errors.append("missing frontend")
    elif not isinstance(fe, dict):
        errors.append("frontend not a dict")
    else:
        if not fe.get("name"):
            errors.append("frontend.name missing")
        if not fe.get("description"):
            errors.append("frontend.description missing")

    bt = data.get("battle")
    if not bt:
        errors.append("missing battle")
    elif not isinstance(bt, dict):
        errors.append("battle not a dict")

    return errors


def validate_frontend_quality(data: dict) -> list[str]:
    """Post-LLM quality checks on frontend section. Auto-fixes what it can, returns hard errors only."""
    fe = data.get("frontend", {})
    if not isinstance(fe, dict):
        return []

    # Auto-fix known issues first
    fixes = autofix_frontend(fe)
    if fixes:
        tqdm.write(f"    [autofix] {'; '.join(fixes)}")

    # Now check for remaining hard errors
    errors = []
    desc = fe.get("description", "")
    cmd_desc = fe.get("commander_description", "")
    full_text = f"{desc} {cmd_desc}"
    vars_dict = fe.get("vars", {})

    import re as _re

    # 1. English words in CHT description (var names leaking through)
    english_words = _re.findall(r'(?<!\{var:)(?<!\{status:)(?<!\{scale:)(?<!\{dmg:)(?<!\{stat:)\b[a-zA-Z_]{3,}\b', full_text)
    ok_words = {'var', 'status', 'scale', 'dmg', 'stat', 'base', 'max', 'flat'}
    bad_words = [w for w in english_words if w.lower() not in ok_words]
    if bad_words:
        errors.append(f"English in description: {bad_words[:3]}")

    # 2. {var:X} references not in vars
    var_refs = _re.findall(r'\{var:(\w+)\}', full_text)
    for ref in var_refs:
        if ref not in vars_dict:
            errors.append(f"{{var:{ref}}} not in vars")

    # 3. base without max
    for vk, vv in vars_dict.items():
        if isinstance(vv, dict) and 'base' in vv and 'max' not in vv:
            errors.append(f"vars.{vk} has base but no max")

    return errors


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------

def _load_existing_yaml(path: Path) -> dict:
    if path.exists():
        data = yaml.safe_load(path.read_text("utf-8"))
        return data if isinstance(data, dict) else {}
    return {}


def _save_yaml(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def process_batch(
    skills: list[tuple[str, dict]],
    model: str,
    force: bool,
    single_prompt_fn=None,
    batch_prompt_fn=None,
    cache_prefix: str = "skill",
) -> tuple[dict, list]:
    """Process a batch of items. Returns (results_dict, failed_list)."""
    if single_prompt_fn is None:
        single_prompt_fn = build_single_prompt
    if batch_prompt_fn is None:
        batch_prompt_fn = build_batch_prompt
    results = {}
    failed = []

    uncached = []
    for name, data in skills:
        if not force:
            cached = load_llm_cache(f"{cache_prefix}_{name}")
            if cached:
                results[name] = cached
                continue
        uncached.append((name, data))

    if not uncached:
        return results, failed

    if len(uncached) == 1:
        prompt = single_prompt_fn(uncached[0][1])
    else:
        prompt = batch_prompt_fn(uncached)

    try:
        # Longer timeout for batches
        timeout = 60 + 40 * len(uncached)
        raw = call_gemini(prompt, model=model, timeout=timeout)
        batch_label = "batch_" + "_".join(n for n, _ in uncached)
        save_raw_cache(batch_label, raw)

        parsed = parse_llm_output(raw)
        if parsed is None:
            # Batch parse failed → fallback to single
            if len(uncached) > 1:
                tqdm.write(f"  batch parse failed, falling back to single...")
                for name, data in uncached:
                    r, f = process_batch([(name, data)], model, force=True,
                                         single_prompt_fn=single_prompt_fn,
                                         batch_prompt_fn=batch_prompt_fn,
                                         cache_prefix=cache_prefix)
                    results.update(r)
                    failed.extend(f)
                return results, failed
            else:
                failed.append((uncached[0][0], "YAML parse failed"))
                tqdm.write(f"  PARSE FAIL: {uncached[0][0]}")
                return results, failed

        # For single skill, output might be nested under skill name or directly have frontend/battle
        if len(uncached) == 1:
            name = uncached[0][0]
            if "frontend" in parsed:
                # Direct output
                entry = parsed
            elif name in parsed:
                entry = parsed[name]
            else:
                # Try first key
                first_key = next(iter(parsed), None)
                entry = parsed[first_key] if first_key else parsed

            errors = validate_skill_entry(entry)
            quality = validate_frontend_quality(entry) if not errors else []
            all_issues = errors + quality
            if all_issues:
                failed.append((name, "; ".join(all_issues)))
                tqdm.write(f"  {'INVALID' if errors else 'QUALITY'}: {name} — {'; '.join(all_issues)}")
            else:
                save_llm_cache(f"{cache_prefix}_{name}", entry)
                results[name] = entry
        else:
            # Batch output: keys may be translated (CHT) instead of original JP names.
            # Match by position: LLM preserves input order.
            parsed_values = list(parsed.values())
            seen_names = set()
            for i, (name, _) in enumerate(uncached):
                # Try exact match first, then positional
                if name in parsed:
                    entry = parsed[name]
                elif i < len(parsed_values):
                    entry = parsed_values[i]
                else:
                    failed.append((name, "missing from batch output"))
                    tqdm.write(f"  MISSING: {name} not in batch output")
                    continue

                errors = validate_skill_entry(entry)
                if errors:
                    failed.append((name, "; ".join(errors)))
                    tqdm.write(f"  INVALID: {name} — {'; '.join(errors)}")
                    continue

                quality = validate_frontend_quality(entry)
                if quality:
                    failed.append((name, "; ".join(quality)))
                    tqdm.write(f"  QUALITY: {name} — {'; '.join(quality)}")
                    continue

                # Check for duplicate translated names within this batch
                fe_name = entry.get("frontend", {}).get("name", "")
                if fe_name and fe_name in seen_names:
                    failed.append((name, f"duplicate name '{fe_name}' in batch"))
                    tqdm.write(f"  DUPE: {name} → '{fe_name}' conflicts with another skill in batch")
                    continue
                if fe_name:
                    seen_names.add(fe_name)

                save_llm_cache(f"{cache_prefix}_{name}", entry)
                results[name] = entry

    except Exception as e:
        for name, _ in uncached:
            failed.append((name, str(e)))
        tqdm.write(f"  FAILED batch: {e}")

    return results, failed


def process_skills(
    *,
    limit: int | None = None,
    name_filter: str | None = None,
    force: bool = False,
    model: str = DEFAULT_MODEL,
    batch_size: int = DEFAULT_BATCH_SIZE,
):
    skills = yaml.safe_load(Path(SKILLS_CRAWLED).read_text("utf-8"))
    if not skills:
        print("[error] No skills found in", SKILLS_CRAWLED)
        sys.exit(1)

    targets = list(skills.items())
    if name_filter:
        targets = [(n, s) for n, s in targets if name_filter in n]
        tqdm.write(f"[filter] Matched {len(targets)} skills for '{name_filter}'")
    if limit:
        targets = targets[:limit]

    tqdm.write(f"[llm] Processing {len(targets)} skills with {model} (batch={batch_size})")

    all_results = {}
    all_failed = []

    # Split into batches
    batches = [targets[i:i + batch_size] for i in range(0, len(targets), batch_size)]

    for batch in tqdm(batches, desc="translate", unit="batch"):
        results, failed = process_batch(batch, model, force)
        all_results.update(results)
        all_failed.extend(failed)

    # Auto-retry failed items one-by-one
    if all_failed:
        retry_names = {name for name, _ in all_failed}
        retry_targets = [(n, s) for n, s in targets if n in retry_names]
        tqdm.write(f"\n[retry] {len(retry_targets)} failed skills, retrying one-by-one...")
        all_failed = []
        for item in tqdm(retry_targets, desc="retry", unit="skill"):
            results, failed = process_batch([item], model, force=True)
            all_results.update(results)
            all_failed.extend(failed)

    # Merge into output files. --force normally truncates, but ONLY when we're
    # processing the full set; with --name/--limit truncating would wipe every
    # untouched entry from the YAML (data loss). In filtered mode we always
    # merge into the existing file.
    full_run = name_filter is None and limit is None
    frontend_skills = {} if (force and full_run) else _load_existing_yaml(SKILLS_TRANSLATED)
    battle_skills = {} if (force and full_run) else _load_existing_yaml(SKILLS_BATTLE)

    new_fe, new_bt = 0, 0
    for name, data in all_results.items():
        if data.get("frontend"):
            is_new = name not in frontend_skills
            frontend_skills[name] = data["frontend"]
            if is_new:
                new_fe += 1
        if data.get("battle"):
            is_new = name not in battle_skills
            battle_skills[name] = data["battle"]
            if is_new:
                new_bt += 1

    _save_yaml(SKILLS_TRANSLATED, frontend_skills)
    _save_yaml(SKILLS_BATTLE, battle_skills)

    updated = len(all_results) - new_fe
    tqdm.write(f"\n[done] {len(frontend_skills)} frontend skills ({new_fe} new, {updated} updated) → {SKILLS_TRANSLATED}")
    tqdm.write(f"[done] {len(battle_skills)} battle skills → {SKILLS_BATTLE}")
    if all_failed:
        tqdm.write(f"[warn] {len(all_failed)} failed:")
        for name, err in all_failed:
            tqdm.write(f"  {name}: {err}")
    _record_failures("skills", all_failed)

    return all_results


def process_traits(
    *,
    limit: int | None = None,
    name_filter: str | None = None,
    force: bool = False,
    model: str = DEFAULT_MODEL,
    batch_size: int = DEFAULT_BATCH_SIZE,
):
    traits = yaml.safe_load(Path(TRAITS_CRAWLED).read_text("utf-8"))
    if not traits:
        print("[error] No traits found in", TRAITS_CRAWLED)
        sys.exit(1)

    targets = list(traits.items())
    if name_filter:
        targets = [(n, t) for n, t in targets if name_filter in n]
        tqdm.write(f"[filter] Matched {len(targets)} traits for '{name_filter}'")
    if limit:
        targets = targets[:limit]

    tqdm.write(f"[llm] Processing {len(targets)} traits with {model} (batch={batch_size})")

    all_results = {}
    all_failed = []

    batches = [targets[i:i + batch_size] for i in range(0, len(targets), batch_size)]

    for batch in tqdm(batches, desc="traits", unit="batch"):
        results, failed = process_batch(
            batch, model, force,
            single_prompt_fn=build_trait_single_prompt,
            batch_prompt_fn=build_trait_batch_prompt,
            cache_prefix="trait",
        )
        all_results.update(results)
        all_failed.extend(failed)

    # Auto-retry failed items one-by-one
    if all_failed:
        retry_names = {name for name, _ in all_failed}
        retry_targets = [(n, t) for n, t in targets if n in retry_names]
        tqdm.write(f"\n[retry] {len(retry_targets)} failed traits, retrying one-by-one...")
        all_failed = []
        for item in tqdm(retry_targets, desc="retry", unit="trait"):
            results, failed = process_batch(
                [item], model, force=True,
                single_prompt_fn=build_trait_single_prompt,
                batch_prompt_fn=build_trait_batch_prompt,
                cache_prefix="trait",
            )
            all_results.update(results)
            all_failed.extend(failed)

    full_run = name_filter is None and limit is None
    frontend_traits = {} if (force and full_run) else _load_existing_yaml(TRAITS_TRANSLATED)
    battle_traits = {} if (force and full_run) else _load_existing_yaml(TRAITS_BATTLE)

    new_fe, new_bt = 0, 0
    for name, data in all_results.items():
        if data.get("frontend"):
            is_new = name not in frontend_traits
            frontend_traits[name] = data["frontend"]
            if is_new:
                new_fe += 1
        if data.get("battle"):
            is_new = name not in battle_traits
            battle_traits[name] = data["battle"]
            if is_new:
                new_bt += 1

    _save_yaml(TRAITS_TRANSLATED, frontend_traits)
    _save_yaml(TRAITS_BATTLE, battle_traits)

    tqdm.write(f"\n[done] {len(frontend_traits)} frontend traits ({new_fe} new) → {TRAITS_TRANSLATED}")
    tqdm.write(f"[done] {len(battle_traits)} battle traits → {TRAITS_BATTLE}")
    if all_failed:
        tqdm.write(f"[warn] {len(all_failed)} failed:")
        for name, err in all_failed:
            tqdm.write(f"  {name}: {err}")
    _record_failures("traits", all_failed)

    return all_results


def process_hero_batch(
    heroes: list[tuple[str, str, str]],
    model: str,
    force: bool,
) -> tuple[dict, list]:
    """Process a batch of heroes. Returns (results_dict, failed_list)."""
    results = {}
    failed = []

    uncached = []
    for name, faction, clan in heroes:
        if not force:
            cached = load_llm_cache(f"hero_{name}")
            if cached:
                results[name] = cached
                continue
        uncached.append((name, faction, clan))

    if not uncached:
        return results, failed

    prompt = build_hero_batch_prompt(uncached)

    try:
        timeout = 60 + 20 * len(uncached)
        raw = call_gemini(prompt, model=model, timeout=timeout)
        batch_label = "batch_hero_" + "_".join(n for n, _, _ in uncached[:5])
        save_raw_cache(batch_label, raw)

        parsed = parse_llm_output(raw)
        if parsed is None:
            for name, _, _ in uncached:
                failed.append((name, "YAML parse failed"))
            tqdm.write(f"  PARSE FAIL: hero batch")
            return results, failed

        parsed_values = list(parsed.values())
        for i, (name, _, _) in enumerate(uncached):
            if name in parsed:
                entry = parsed[name]
            elif i < len(parsed_values):
                entry = parsed_values[i]
            else:
                failed.append((name, "missing from batch output"))
                tqdm.write(f"  MISSING: {name} not in batch output")
                continue

            if not isinstance(entry, dict) or not entry.get("name"):
                failed.append((name, "invalid: missing name field"))
                tqdm.write(f"  INVALID: {name} — missing name field")
                continue

            save_llm_cache(f"hero_{name}", entry)
            results[name] = entry

    except Exception as e:
        for name, _, _ in uncached:
            failed.append((name, str(e)))
        tqdm.write(f"  FAILED hero batch: {e}")

    return results, failed


def process_heroes(
    *,
    limit: int | None = None,
    name_filter: str | None = None,
    force: bool = False,
    model: str = DEFAULT_MODEL,
    batch_size: int = 25,
):
    raw_data = yaml.safe_load(Path(HEROES_CRAWLED).read_text("utf-8"))
    if not raw_data:
        print("[error] No heroes found in", HEROES_CRAWLED)
        sys.exit(1)

    # Input is a list; extract unique (name, faction, clan) tuples
    seen = set()
    targets = []
    for hero in raw_data:
        name = hero.get("name", "")
        if not name or name in seen:
            continue
        seen.add(name)
        targets.append((name, hero.get("faction", ""), hero.get("clan", "")))

    if name_filter:
        targets = [(n, f, c) for n, f, c in targets if name_filter in n]
        tqdm.write(f"[filter] Matched {len(targets)} heroes for '{name_filter}'")
    if limit:
        targets = targets[:limit]

    tqdm.write(f"[llm] Processing {len(targets)} heroes with {model} (batch={batch_size})")

    all_results = {}
    all_failed = []

    batches = [targets[i:i + batch_size] for i in range(0, len(targets), batch_size)]

    for batch in tqdm(batches, desc="heroes", unit="batch"):
        results, failed = process_hero_batch(batch, model, force)
        all_results.update(results)
        all_failed.extend(failed)

    # Merge into output
    full_run = name_filter is None and limit is None
    hero_translated = {} if (force and full_run) else _load_existing_yaml(HEROES_TRANSLATED)

    new_count = 0
    for name, data in all_results.items():
        is_new = name not in hero_translated
        hero_translated[name] = data
        if is_new:
            new_count += 1

    _save_yaml(HEROES_TRANSLATED, hero_translated)

    updated = len(all_results) - new_count
    tqdm.write(f"\n[done] {len(hero_translated)} heroes ({new_count} new, {updated} updated) → {HEROES_TRANSLATED}")
    if all_failed:
        tqdm.write(f"[warn] {len(all_failed)} failed:")
        for name, err in all_failed:
            tqdm.write(f"  {name}: {err}")
    _record_failures("heroes", all_failed)

    return all_results


def claude_test(kind: str = "skills", num: int = 10, batch_size: int = 5, model: str = "haiku"):
    """Run prompts through Claude CLI for testing. No files saved."""
    import random

    if kind == "skills":
        data = yaml.safe_load(Path(SKILLS_CRAWLED).read_text("utf-8"))
        items = list(data.items())
        samples = random.sample(items, min(num, len(items)))
        batches = [samples[i:i + batch_size] for i in range(0, len(samples), batch_size)]
        for i, batch in enumerate(batches):
            prompt = build_batch_prompt(batch) if len(batch) > 1 else build_single_prompt(batch[0][1])
            names = ', '.join(n for n, _ in batch)
            print(f"\n{'='*60}")
            print(f"BATCH {i+1}/{len(batches)}: {names}")
            print(f"{'='*60}")
            try:
                raw = call_claude(prompt, model=model)
                parsed = parse_llm_output(raw)
                if parsed is None:
                    print(f"[PARSE FAIL] Raw:\n{raw[:500]}")
                    continue
                # Validate each skill
                for name, _ in batch:
                    entry = parsed.get(name)
                    if not entry:
                        # Try positional
                        vals = list(parsed.values())
                        idx = [n for n, _ in batch].index(name)
                        entry = vals[idx] if idx < len(vals) else None
                    if not entry:
                        print(f"  {name}: MISSING from output")
                        continue
                    errors = validate_skill_entry(entry)
                    quality = validate_frontend_quality(entry) if not errors else []
                    if errors or quality:
                        print(f"  {name}: {'|'.join(errors + quality)}")
                    else:
                        fe = entry.get("frontend", {})
                        print(f"  {name} → {fe.get('name', '?')} | {fe.get('type', '?')} | brief: {fe.get('brief_description', '?')}")
                        print(f"    tags: {fe.get('tags', [])}")
                        desc = fe.get('description', '')
                        print(f"    desc: {desc[:80]}{'...' if len(desc) > 80 else ''}")
            except Exception as e:
                print(f"  [ERROR] {e}")
    elif kind == "traits":
        data = yaml.safe_load(Path(TRAITS_CRAWLED).read_text("utf-8"))
        items = list(data.items())
        samples = random.sample(items, min(num, len(items)))
        batches = [samples[i:i + batch_size] for i in range(0, len(samples), batch_size)]
        for i, batch in enumerate(batches):
            prompt = build_trait_batch_prompt(batch) if len(batch) > 1 else build_trait_single_prompt(batch[0][1])
            names = ', '.join(n for n, _ in batch)
            print(f"\n{'='*60}")
            print(f"BATCH {i+1}/{len(batches)}: {names}")
            print(f"{'='*60}")
            try:
                raw = call_claude(prompt, model=model)
                parsed = parse_llm_output(raw)
                if parsed is None:
                    print(f"[PARSE FAIL] Raw:\n{raw[:500]}")
                else:
                    for name, _ in batch:
                        entry = parsed.get(name)
                        if entry:
                            fe = entry.get("frontend", {})
                            print(f"  {name} → {fe.get('name', '?')}: {fe.get('description', '?')[:60]}")
                        else:
                            print(f"  {name}: MISSING")
            except Exception as e:
                print(f"  [ERROR] {e}")
    elif kind == "heroes":
        data = yaml.safe_load(Path(HEROES_CRAWLED).read_text("utf-8"))
        items = [(h["name"], h.get("faction", ""), h.get("clan", "")) for h in data if h.get("name")]
        samples = random.sample(items, min(num, len(items)))
        prompt = build_hero_batch_prompt(samples)
        print(f"\n{'='*60}")
        print(f"HEROES ({len(samples)} samples)")
        print(f"{'='*60}")
        try:
            raw = call_claude(prompt, model=model)
            parsed = parse_llm_output(raw)
            if parsed is None:
                print(f"[PARSE FAIL] Raw:\n{raw[:500]}")
            else:
                for name, _, _ in samples:
                    entry = parsed.get(name)
                    if entry:
                        print(f"  {name} → {entry.get('name', '?')} | {entry.get('faction', '?')}")
                    else:
                        print(f"  {name}: MISSING")
        except Exception as e:
            print(f"  [ERROR] {e}")

    print(f"\n[claude-test] Done. No files were modified.")


def main():
    p = argparse.ArgumentParser(description="LLM translate + extract skills, traits, and heroes")
    p.add_argument("--skills", action="store_true", help="Process skills only")
    p.add_argument("--traits", action="store_true", help="Process traits only")
    p.add_argument("--heroes", action="store_true", help="Process heroes only")
    p.add_argument("--limit", type=int, help="Max items to process")
    p.add_argument("--name", help="Filter by name (substring)")
    p.add_argument("--force", action="store_true", help="Ignore cache, overwrite output")
    p.add_argument("--model", default=DEFAULT_MODEL, help="Gemini model to use")
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Items per LLM call")
    p.add_argument("--claude-test", action="store_true", help="Print prompts for Claude Code testing (no LLM call, no file writes)")
    p.add_argument("--test-num", type=int, default=10, help="Number of random samples for --claude-test")
    args = p.parse_args()

    if args.claude_test:
        kind = "skills" if args.skills else "traits" if args.traits else "heroes" if args.heroes else "skills"
        claude_test(kind=kind, num=args.test_num, batch_size=args.batch_size, model=args.model)
        return

    # Default: all if none specified
    none_specified = not args.skills and not args.traits and not args.heroes
    do_skills = args.skills or none_specified
    do_traits = args.traits or none_specified
    do_heroes = args.heroes or none_specified

    if do_skills:
        process_skills(
            limit=args.limit,
            name_filter=args.name,
            force=args.force,
            model=args.model,
            batch_size=args.batch_size,
        )
    if do_traits:
        process_traits(
            limit=args.limit,
            name_filter=args.name,
            force=args.force,
            model=args.model,
            batch_size=args.batch_size,
        )
    if do_heroes:
        process_heroes(
            limit=args.limit,
            name_filter=args.name,
            force=args.force,
            model=args.model,
            batch_size=args.batch_size,
        )

    _write_failure_manifest()


if __name__ == "__main__":
    main()
