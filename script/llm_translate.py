"""
LLM-based skill translator and battle engine extractor.

Reads crawled YAML, sends skills to OpenRouter in batches for:
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
    python script/llm_translate.py --model google/gemma-4-31b-it:free  # free test
    python script/llm_translate.py --model anthropic/claude-haiku-4.5  # cheaper
"""

import argparse
import json
import sys
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tqdm import tqdm

from llm_core import (
    CANONICAL_STATUSES, COMMON_RULES, SKILL_TAGS,
    DEFAULT_MODEL, MODEL_FREE, MODEL_GEMMA, MODEL_HAIKU, MODEL_SONNET,
    call_llm, parse_llm_output, autofix_frontend, has_kana,
    load_llm_cache, save_llm_cache, save_raw_cache,
    reset_token_totals, get_token_totals,
)
from paths import (
    HEROES_CRAWLED, SKILLS_CRAWLED, TRAITS_CRAWLED,
    SKILLS_CANONICAL, TRAITS_CANONICAL,
    HEROES_TRANSLATED,
    TRANSLATION_FAILURES_JSON,
)
DEFAULT_BATCH_SIZE = 5

# In-process accumulator for failures across all process_* runs in a single
# invocation. Flushed to TRANSLATION_FAILURES_JSON in main().
_FAILURE_LOG: dict[str, list[dict]] = {"skills": [], "traits": [], "heroes": []}

# Stores previous LLM output for failed items so retry can feed it back.
# Populated by process_batch, consumed by retry logic.
# Key: name, Value: (prev_yaml_str, error_str)
_correction_store: dict[str, tuple[str, str]] = {}

# Error counters for the current run. Reset per main() invocation.
_error_counts: dict[str, int] = {}


def _normalize_error(err: str) -> str:
    """Normalize error string to a stable category for counting."""
    if "found in battle" in err:
        return "template_in_battle"
    if "Japanese kana" in err:
        return "untranslated_name"
    if "not in vars" in err:
        return "dangling_var_ref"
    if "double braces" in err:
        return "double_braces"
    if "base but no max" in err:
        return "base_without_max"
    if "scaling (→)" in err:
        return "scaling_without_vars"
    if "English in description" in err:
        return "english_in_description"
    if "duplicate name" in err:
        return "duplicate_name"
    return err


def _count_error(category: str):
    cat = _normalize_error(category)
    _error_counts[cat] = _error_counts.get(cat, 0) + 1


def _print_error_summary():
    if not _error_counts:
        tqdm.write("\n[stats] No errors detected")
        return
    total = sum(_error_counts.values())
    tqdm.write(f"\n[stats] {total} errors across {len(_error_counts)} categories:")
    for cat, count in sorted(_error_counts.items(), key=lambda x: -x[1]):
        tqdm.write(f"  {count:>4}x  {cat}")


# Pricing per million tokens (input, output) for known models
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    MODEL_FREE: (0, 0),
    MODEL_GEMMA: (0.13, 0.40),
    MODEL_HAIKU: (0.80, 4.00),
    MODEL_SONNET: (3.00, 15.00),
}


def _print_token_summary(model: str):
    t = get_token_totals()
    if not t["calls"]:
        return
    tqdm.write(f"\n[tokens] {t['calls']} API calls")
    tqdm.write(f"  prompt:     {t['prompt']:>8,} tokens")
    tqdm.write(f"  completion: {t['completion']:>8,} tokens")
    if t["cached"]:
        tqdm.write(f"  cached:     {t['cached']:>8,} tokens")
    pricing = _MODEL_PRICING.get(model)
    if pricing:
        pin, pout = pricing
        cost = t["prompt"] * pin / 1_000_000 + t["completion"] * pout / 1_000_000
        tqdm.write(f"  est. cost:  ${cost:.4f}")


def _store_correction(name: str, entry: dict, errors: str):
    """Save a failed LLM output so the retry can include it as context."""
    prev_yaml = yaml.dump(
        {name: entry}, allow_unicode=True,
        default_flow_style=False, sort_keys=False,
    )
    # Truncate to avoid bloating the correction prompt
    _correction_store[name] = (prev_yaml[:3000], errors)


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
                f'uv run script/llm_translate.py --{kind} --name "{names[0]}"'
            )
        else:
            suggestions.append(f"uv run script/llm_translate.py --{kind}")
    if suggestions:
        suggestions.append(
            "uv run script/build_frontend_data.py && uv run script/check_data_integrity.py"
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


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = f"""\
You are a game data translator and structured extractor for 信長之野望：真戰 (Nobunaga's Ambition: Shinsei).

{COMMON_RULES}

For EACH skill, output a YAML document under that skill's name as the top-level key, containing THREE sections:

## `vars` — Shared variables (SINGLE source of numeric truth)
- Extract ALL numeric values referenced in both text and battle into ONE shared `vars` dict.
- Scaling values: use nested {{base, max, scale}} (e.g. {{base: 0.30, max: 0.60, scale: 武勇}}).
- Fixed values: use plain int/float (e.g. duration: 2).
- CRITICAL: `text.description` uses {{var:key}} to reference these vars.
  `battle.do` uses $key to reference these vars. Both reference the SAME vars dict.
  Do NOT duplicate vars between text and battle.

## `text` — Translation for frontend rendering (JP → Traditional Chinese)
- Translate to Traditional Chinese (繁體中文)
- REQUIRED fields: `name` (CHT skill name), `type`, `rarity`, `target`, `activation_rate`, `description`, `brief_description`, `tags`
- `rarity` must be just: S, A, or B
- `brief_description`: 15-25 chars, summarize the core mechanic without numbers
- `tags`: list from ONLY these allowed tags: """ + SKILL_TAGS + """
- Use {{var:key}} in description to reference the shared vars dict
- Do NOT include a `vars` field here — vars live at the top level

## `battle` — Structured extraction for battle engine
- ALL text (including `bonus.commander.description`) must be in Traditional Chinese (繁體中文)
- Use $key to reference the shared vars dict — do NOT include a `vars` field here
- NEVER use {{var:}}, {{status:}}, or {{scale:}} in battle — those are text-only. Battle uses $key for vars and plain Chinese for statuses (e.g. 會心, not {{status:會心}})
- `bonus.commander.description` follows the SAME $key rule: write $atk_debuff, NOT {{var:atk_debuff}}. Write （受統率影響）, NOT （{{scale:統率}}）.
- Map effects to `do` blocks: trigger/when/to/do
- Effect types: damage, heal, buff, debuff, applyStatus, removeStatus, addStack, roll, sequence, conditional
- Trigger types: always, battleStart, turnStart, beforeAction, afterAction, beforeAttack, afterAttack, onDamaged, onHeal
- Target types: self, allySingle, allyMultiple, allyAll, enemySingle, enemyMultiple, enemyAll
- 大将技 → `bonus.commander`

### Reference examples (correct format):

Example 1 (主動, damage + status + commander):
傲岸不遜:
  vars:
    dmg_rate:
      base: 0.59
      max: 1.18
    assault_debuff:
      base: 0.15
      max: 0.3
    atk_debuff:
      base: 0.15
      max: 0.3
    duration: 2
  text:
    name: 傲岸不遜
    type: 主動
    rarity: S
    target: 敵軍複數（2人）
    activation_rate: "35%"
    description: >
      對敵軍複數（2人）造成{var:dmg_rate}兵刃傷害，
      並施加{status:挑釁}狀態，使其突擊戰法傷害降低{var:assault_debuff}（{scale:統率}），持續{var:duration}回合。
    brief_description: 複數兵刃傷害並施加挑釁
    tags: [兵刃傷害, 群體傷害, 施加狀態, 減益, 主動發動, 大將技]
  battle:
    type: 主動
    trigger: beforeAction
    rate: 0.35
    do:
      - to: enemyMultiple
        count: 2
        do:
          - type: damage
            damage_type: 兵刃傷害
            value: $dmg_rate
          - type: applyStatus
            status: 挑釁
            duration: $duration
          - type: debuff
            stat: assault_damage
            value: $assault_debuff
            scale: 統率
            duration: $duration
    bonus:
      commander:
        description: 額外使敵軍普通攻擊傷害降低$atk_debuff（受統率影響）
        do:
          - type: debuff
            stat: normal_attack_damage
            value: $atk_debuff
            scale: 統率
            duration: $duration

Example 2 (指揮, conditional heal + status extension):
內助之賢:
  vars:
    extend_chance:
      base: 0.25
      max: 0.5
    heal_rate:
      base: 0.48
      max: 0.96
  text:
    name: 內助之賢
    type: 指揮
    rarity: S
    target: 自軍群體（2人）
    activation_rate: "100%"
    description: >
      戰鬥中，自軍群體（2人）施加持續性狀態時，有{var:extend_chance}（{scale:智略}）機率使該狀態延長1回合。
      每逢偶數回合，若敵軍全體處於持續性狀態中，則治療自軍全體（治療率{var:heal_rate}，{scale:智略}）。
    brief_description: 延長狀態持續並條件群體治療
    tags: [治療, 增益, 指揮效果, 智略系, 回合觸發]
  battle:
    type: 指揮
    trigger: always
    do:
      - trigger: onApplyStatus
        to: allyMultiple
        do:
          - type: roll
            chance: $extend_chance
            on_success:
              - type: extendDuration
                value: 1
      - trigger: turnStart
        when: isEvenTurn AND enemyAllHasStatus(continuous)
        to: allyAll
        do:
          - type: heal
            value: $heal_rate
            scale: 智略

Example 3 (被動, multi-status + HP conditional):
以戰養戰:
  vars:
    rebel_rate:
      base: 0.125
      max: 0.25
    extra_rebel_rate:
      base: 0.125
      max: 0.25
    crit_rate:
      base: 0.125
      max: 0.25
  text:
    name: 以戰養戰
    type: 被動
    rarity: S
    target: 自身
    activation_rate: "100%"
    description: >
      戰鬥中，使自身獲得{var:rebel_rate}{status:離反}。
      第5回合時，額外獲得{var:extra_rebel_rate}{status:離反}。
      自身兵力低於50%時，額外獲得{var:crit_rate}{status:會心}。
    brief_description: 獲得離反，低兵力時獲得會心
    tags: [增益, 施加狀態, 被動觸發, 武勇系, 條件觸發]
  battle:
    type: 被動
    trigger: always
    do:
      - trigger: battleStart
        to: self
        do:
          - type: applyStatus
            status: 離反
            value: $rebel_rate
      - trigger: turnStart
        when: turn == 5
        to: self
        do:
          - type: applyStatus
            status: 離反
            value: $extra_rebel_rate
      - trigger: always
        when: hp_rate <= 0.5
        to: self
        do:
          - type: applyStatus
            status: 會心
            value: $crit_rate

Example 4 (突擊, scaling activation_rate + 謀略傷害 + debuff):
五里霧中:
  vars:
    activation_rate:
      base: 0.2
      max: 0.35
    dmg_rate:
      base: 0.82
      max: 1.64
    confusion_chance:
      base: 0.3
      max: 0.6
    stat_debuff:
      base: 36
      max: 72
      type: flat
    debuff_duration: 2
  text:
    name: 五里霧中
    type: 突擊
    rarity: S
    target: 敵軍單體
    activation_rate: "20%→35%"
    description: >
      對敵軍單體造成{var:dmg_rate}謀略傷害（{scale:智略}），
      並有{var:confusion_chance}機率施加{status:混亂}狀態。
      同時降低目標智略{var:stat_debuff}點，持續{var:debuff_duration}回合。
    brief_description: 謀略傷害並機率施加混亂
    tags: [謀略傷害, 單體傷害, 施加狀態, 控制, 降低屬性, 突擊觸發, 智略系]
  battle:
    type: 突擊
    trigger: afterAttack
    rate: $activation_rate
    do:
      - to: enemySingle
        do:
          - type: damage
            damage_type: 謀略傷害
            value: $dmg_rate
            scale: 智略
          - type: roll
            chance: $confusion_chance
            on_success:
              - type: applyStatus
                status: 混亂
          - type: debuff
            stat: 智略
            value: $stat_debuff
            duration: $debuff_duration"""


def build_single_prompt(skill: dict) -> tuple[str, str]:
    raw = skill.get("raw", skill)  # support both canonical (has .raw) and legacy shape
    user = f"""\
Input skill:
name: {raw.get('name', skill.get('name', ''))}
type: {raw.get('type', 'unknown')}
rarity: {raw.get('rarity', '')}
target: {raw.get('target', '')}
activation_rate: {raw.get('activation_rate', '')}
source_hero: {raw.get('source_hero', '')}
description: |
  {raw.get('description', '')}
commander_bonus: {raw.get('commander_bonus', '') or 'none'}

---
Example output:
軍神:
  vars:
    charge_trigger_rate:
      base: 0.30
      max: 0.60
      scale: 武勇
    damage_per_stack:
      base: 0.05
      max: 0.10
      scale: 武勇
    max_charge: 12
    ally_count: 2
  text:
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
  battle:
    type: 被動
    trigger: always
    do:
      - trigger: afterAllyAction
        to: self
        do:
          type: roll
          chance: $charge_trigger_rate
          on_success:
            - type: addStack
              key: god_of_war_charge
              value: 1
              max: $max_charge

---
Output the YAML with skill name as top-level key, containing `vars`, `text`, and `battle`."""
    return (SYSTEM_PROMPT, user)


def build_batch_prompt(skills: list[tuple[str, dict]]) -> tuple[str, str]:
    skill_blocks = []
    for i, (name, skill) in enumerate(skills, 1):
        raw = skill.get("raw", skill)
        skill_blocks.append(f"""\
Skill {i}:
  name: {raw.get('name', name)}
  type: {raw.get('type', 'unknown')}
  rarity: {raw.get('rarity', '')}
  target: {raw.get('target', '')}
  activation_rate: {raw.get('activation_rate', '')}
  source_hero: {raw.get('source_hero', '')}
  description: |
    {raw.get('description', '')}
  commander_bonus: {raw.get('commander_bonus', '') or 'none'}""")

    joined = "\n\n".join(skill_blocks)

    user = f"""\
Input ({len(skills)} skills):

{joined}

---
Output YAML: each skill name as a top-level key, each containing `vars`, `text`, and `battle` sections.
`vars` is the SINGLE shared variable dict — do NOT put vars inside text or battle.
Process ALL {len(skills)} skills above."""
    return (SYSTEM_PROMPT, user)


# ---------------------------------------------------------------------------
# Trait Prompts
# ---------------------------------------------------------------------------

ALLOWED_TROOP_TYPES_STR = "足輕, 弓兵, 騎兵, 鐵炮, 器械"

TRAIT_SYSTEM_PROMPT = f"""\
You are a game data translator and structured extractor for 信長之野望：真戰 (Nobunaga's Ambition: Shinsei).

{COMMON_RULES}

For EACH trait (特性), first determine its `kind`:

- `kind: passive` — always-on effect with NO engine trigger. Includes:
  - Troop affinity (兵種レベル): buffs a troop type level (output `passive.affinity`)
  - Flat stat/damage buffs: e.g. "造成兵刃傷害增加2.2%" (output `passive.buffs`)
- `kind: triggered` — activates on an engine event (battleStart, turnStart, afterAttack, etc.).
  Has a `battle` section with `trigger` + `do` blocks, same shape as a triggered skill.

Output YAML with the trait name as top-level key, containing these sections:

## `vars` — Shared variables (SINGLE source, same rules as skills)
- Only if the trait has numeric values. Both text and battle/passive reference this.

## `text` — Translation (JP → Traditional Chinese 繁體中文)
- `name`: translated trait name
- `description`: translated description, use {{var:key}} for numeric values

## For `kind: passive` → output `passive` section (NO `battle`):
- `passive.affinity` — for troop_affinity traits:
  - `troop_types`: MUST be a YAML list. Allowed values ONLY: {ALLOWED_TROOP_TYPES_STR}
    IMPORTANT: 兵器→器械, 槍兵→足輕, 鐵砲→鐵炮 (use the correct CHT names)
  - `level`: integer
  - `level_cap_bonus`: integer (0 if not mentioned; detect 等級上限増加N)
- `passive.buffs` — for flat %buff traits:
  - list of {{target, stat, type: pct|flat, value: $var_ref}}

## For `kind: triggered` → output `battle` section (NO `passive`):
- `trigger`: when it activates (battleStart, turnStart, beforeAction, afterAttack, etc.)
- `do`: structured effects
- Effect types: damage, heal, buff, debuff, applyStatus, removeStatus, addStack, roll, sequence, conditional
- Target types: self, allySingle, allyMultiple, allyAll, enemySingle, enemyMultiple, enemyAll

### COMMON TRAIT MISTAKES — DO NOT DO THESE:
| Wrong | Right | Why |
| troop_types: [槍兵] | troop_types: [足輕] | 槍兵→足輕 |
| troop_types: [鐵砲] | troop_types: [鐵炮] | 砲→炮 |
| troop_types: [兵器] | troop_types: [器械] | 兵器→器械 |
| kind: passive + battle: | kind: triggered + battle: | passive has NO battle |
| kind: triggered + passive: | kind: triggered + battle: | triggered has NO passive |
| battle: {{status:威壓}} | battle: status: 威壓 | battle uses plain text |
| battle: {{var:rate}} | battle: $rate | battle uses $key |
| battle: （{{scale:武勇}}） | battle: scale: 武勇 | battle uses plain field |
| {{base: 0.5, max: 0.5}} | 0.5 | same value = fixed |
| {{base: 1.0}} (no max) | {{base: 0.5, max: 1.0}} | scaling needs both |
| 知略 | 智略 | JP→CHT kanji |

### CRITICAL REMINDERS (reinforcement of rules above)

Troop type mapping (MUST follow these, common mistake source):
- 兵器 → 器械
- 槍兵 → 足輕
- 鐵砲 → 鐵炮
Allowed troop types: {ALLOWED_TROOP_TYPES_STR} — NO other values.

Kind determination:
- `kind: passive` — always-on, NO trigger. Troop affinity OR flat stat/damage buffs.
- `kind: triggered` — has a trigger event. Output `battle` section, NOT `passive`.
- NEVER output both `passive` and `battle` in the same trait.

Template syntax reminder:
- `text.description`: use {{var:key}} for vars, {{status:name}} for statuses, （{{scale:stat}}） for scaling
- `battle` section (including all description fields): use $key for vars, plain Chinese for statuses and scaling (e.g. 會心 not {{status:會心}}, 受統率影響 not {{scale:統率}})
- vars with base/max MUST have BOTH fields. Same value at all levels = plain number, not {{base: X, max: X}}.

JP→CHT kanji (apply everywhere): 知略→智略, 撃→擊, 竜→龍, 発→發, 効→效, 覚→覺, 戦→戰, 総→總, 関→關, 豊→豐, 県→縣, 鉄→鐵, 条→條

Status effects — use ONLY canonical names: {CANONICAL_STATUSES}

Example passive (troop affinity):
馬術Ⅲ:
  text:
    name: 馬術Ⅲ
    description: 部隊的騎兵等級增加3
  kind: passive
  passive:
    affinity:
      troop_types: [騎兵]
      level: 3
      level_cap_bonus: 0

Example passive (%buff):
攻勢Ⅱ:
  vars:
    dmg_bonus: 0.013
  text:
    name: 攻勢Ⅱ
    description: 自軍全體造成傷害提高{{var:dmg_bonus}}
  kind: passive
  passive:
    buffs:
      - target: armyAll
        stat: damage_dealt
        type: pct
        value: $dmg_bonus

Example triggered (simple debuff):
赤備え:
  vars:
    reduction: 18
  text:
    name: 赤備
    description: 首次普通攻擊後，使攻擊目標的統率降低{{var:reduction}}（可疊加）
  kind: triggered
  battle:
    trigger: afterNormalAttack
    do:
      - when: firstTime
        to: enemySingle
        do: debuff
        stat: 統率
        value: $reduction
        stackable: true

Example triggered (damage + status + scaling vars):
槍衾:
  vars:
    dmg_rate:
      base: 0.36
      max: 0.72
    debuff_value:
      base: 0.10
      max: 0.20
    duration: 2
  text:
    name: 槍衾
    description: >
      對敵軍單體造成{{var:dmg_rate}}兵刃傷害（{{scale:武勇}}），
      並降低目標造成傷害{{var:debuff_value}}，持續{{var:duration}}回合。
    name: 槍衾
  kind: triggered
  battle:
    trigger: afterAttack
    do:
      - to: enemySingle
        do:
          - type: damage
            damage_type: 兵刃傷害
            value: $dmg_rate
            scale: 武勇
          - type: debuff
            stat: damage_dealt
            value: $debuff_value
            duration: $duration

Example passive (multiple troop types + level cap):
砲術指南Ⅱ:
  text:
    name: 砲術指南Ⅱ
    description: 部隊的鐵炮等級增加2，鐵炮等級上限增加1
  kind: passive
  passive:
    affinity:
      troop_types: [鐵炮]
      level: 2
      level_cap_bonus: 1

Example passive (conditional buff with var):
豪傑Ⅲ:
  vars:
    atk_bonus: 0.033
  text:
    name: 豪傑Ⅲ
    description: 自身造成兵刃傷害提高{{var:atk_bonus}}
  kind: passive
  passive:
    buffs:
      - target: self
        stat: blade_damage_dealt
        type: pct
        value: $atk_bonus

Example triggered (status effect — note: battle uses plain text, NOT {{status:}}):
威圧射撃:
  vars:
    intimidate_chance:
      base: 0.25
      max: 0.50
    duration: 1
  text:
    name: 威壓射擊
    description: >
      普通攻擊後，有{{var:intimidate_chance}}機率對目標施加{{status:威壓}}，持續{{var:duration}}回合。
  kind: triggered
  battle:
    trigger: afterNormalAttack
    do:
      - to: enemySingle
        do:
          - type: roll
            chance: $intimidate_chance
            on_success:
              - type: applyStatus
                status: 威壓
                duration: $duration
        stackable: true"""


def build_trait_single_prompt(trait: dict) -> tuple[str, str]:
    raw = trait.get("raw", trait)  # support both canonical (has .raw) and legacy shape
    user = f"""\
Input trait:
name: {raw.get('name', trait.get('name', ''))}
category: {raw.get('category', 'skill_like')}
description: |
  {raw.get('description', '')}

---
Output YAML with trait name as top-level key.
Include `kind`, `vars` (if any), `text`, and either `passive` or `battle` (not both)."""
    return (TRAIT_SYSTEM_PROMPT, user)


def build_trait_batch_prompt(traits: list[tuple[str, dict]]) -> tuple[str, str]:
    blocks = []
    for i, (name, trait) in enumerate(traits, 1):
        raw = trait.get("raw", trait)
        blocks.append(f"""\
Trait {i}:
  name: {raw.get('name', name)}
  category: {raw.get('category', 'skill_like')}
  description: |
    {raw.get('description', '')}""")

    joined = "\n\n".join(blocks)
    user = f"""\
Input ({len(traits)} traits):

{joined}

---
Output YAML: each trait name as top-level key.
Each must include `kind`, `vars` (if any), `text`, and either `passive` or `battle`.
Process ALL {len(traits)} traits above."""
    return (TRAIT_SYSTEM_PROMPT, user)


# ---------------------------------------------------------------------------
# Hero Prompts
# ---------------------------------------------------------------------------

HERO_SYSTEM_PROMPT = """\
You are a translator for historical Japanese figure names from the game 信長之野望：真戰 (Nobunaga's Ambition: Shinsei).

Translate hero names, faction (勢力) names, and clan (家門) names from Japanese to Traditional Chinese (繁體中文).

Key rules:
- Many names share the same kanji between JP and CHT, but some JP-specific kanji need conversion:
  黒→黑, 関→關, 豊→豐, 浅→淺, 広→廣, 竜→龍, 辺→邊, 桜→櫻, 沢→澤, 県→縣, 斎→齋, 滝→瀧, 弐→貳, 鉄→鐵, 従→從, 帯→帶, 徳→德, 条→條, 団→團, 覚→覺, 伝→傳, 予→預, 亜→亞, 斉→齊
- Names containing hiragana/katakana (e.g. 池田せん, お市の方) MUST be converted to kanji.
  Use the historical figure's known Chinese name: 池田せん→池田千, お市の方→阿市, まつ→阿松.
  The output MUST NOT contain any hiragana or katakana characters.
- Preserve names that are already identical in both languages
- These are real historical figures from Japan's Sengoku period
- CRITICAL: `faction` and `clan` are STRUCTURED VALUES, not free text.
  Translate ONLY the value the user gave you, character by character,
  using the kanji conversion table above. Do NOT infer the clan from
  the hero's surname. Do NOT substitute a different clan even if you
  think it would be more accurate. If the input clan is `豊臣`, the
  output MUST be `豐臣`, regardless of who the hero is. If the input
  clan is `北条`, the output MUST be `北條`. Treat clan/faction as
  opaque strings to transliterate, never to second-guess.

Output ONLY valid YAML. No markdown fences. No explanation.
Each JP name as a top-level key, with `name`, `faction`, and `clan` values."""


def build_hero_batch_prompt(heroes: list[tuple[str, str, str]]) -> tuple[str, str]:
    blocks = [f"  {name}: {{faction: {faction}, clan: {clan}}}" for name, faction, clan in heroes]
    joined = "\n".join(blocks)
    user = f"""\
Input ({len(heroes)} heroes):
{joined}

---
Output YAML: each JP name as top-level key with `name`, `faction`, and `clan` in Traditional Chinese.
Remember: `faction` and `clan` are transliterated from the input value
character-by-character. Never replace them with the hero's surname.

Example (note that 黒田官兵衛's clan is 豊臣, NOT 黒田):
豊臣秀吉:
  name: 豐臣秀吉
  faction: 豐臣
  clan: 豐臣
黒田官兵衛:
  name: 黑田官兵衛
  faction: 豐臣
  clan: 豐臣
瑞渓院:
  name: 瑞溪院
  faction: 北條
  clan: 北條
Process ALL {len(heroes)} heroes above."""
    return (HERO_SYSTEM_PROMPT, user)


# ---------------------------------------------------------------------------
# Correction prompts (retry with previous output + errors)
# ---------------------------------------------------------------------------

def build_skill_correction_prompt(
    skill: dict, prev_yaml: str, errors: str,
) -> tuple[str, str]:
    raw = skill.get("raw", skill)
    user = f"""\
Your previous translation of this skill had errors. Fix them.

ERRORS:
{errors}

YOUR PREVIOUS OUTPUT (contains mistakes — fix them):
{prev_yaml}

ORIGINAL INPUT:
name: {raw.get('name', skill.get('name', ''))}
type: {raw.get('type', 'unknown')}
rarity: {raw.get('rarity', '')}
target: {raw.get('target', '')}
activation_rate: {raw.get('activation_rate', '')}
source_hero: {raw.get('source_hero', '')}
description: |
  {raw.get('description', '')}
commander_bonus: {raw.get('commander_bonus', '') or 'none'}

---
Output corrected YAML with skill name as top-level key, containing `vars`, `text`, and `battle`.
In `battle`, use $key to reference vars (NOT {{var:key}}).
In `text`, use {{var:key}} to reference vars."""
    return (SYSTEM_PROMPT, user)


def build_skill_batch_correction_prompt(
    items: list[tuple[str, dict, str, str]],
) -> tuple[str, str]:
    """Build batch correction prompt. items: [(name, skill_data, prev_yaml, errors), ...]"""
    blocks = []
    for i, (name, skill, prev_yaml, errors) in enumerate(items, 1):
        raw = skill.get("raw", skill)
        blocks.append(f"""\
Skill {i} — {name}:
  ERRORS: {errors}
  PREVIOUS OUTPUT:
{prev_yaml}
  ORIGINAL INPUT:
    name: {raw.get('name', name)}
    type: {raw.get('type', 'unknown')}
    rarity: {raw.get('rarity', '')}
    target: {raw.get('target', '')}
    activation_rate: {raw.get('activation_rate', '')}
    description: |
      {raw.get('description', '')}
    commander_bonus: {raw.get('commander_bonus', '') or 'none'}""")

    joined = "\n\n".join(blocks)
    user = f"""\
Fix the following {len(items)} skills. Each had errors in the previous translation.

COMMON REMINDERS:
- In `battle` section, use $key to reference vars (NOT {{var:key}})
- In `text` section, use {{var:key}} to reference vars
- Translate ALL names to Traditional Chinese (no Japanese kana)
- activation_rate with scaling must have corresponding vars with base/max

{joined}

---
Output corrected YAML: each skill name as top-level key with `vars`, `text`, and `battle`.
Fix ALL {len(items)} skills above."""
    return (SYSTEM_PROMPT, user)


def build_trait_correction_prompt(
    trait: dict, prev_yaml: str, errors: str,
) -> tuple[str, str]:
    raw = trait.get("raw", trait)
    user = f"""\
Your previous translation of this trait had errors. Fix them.

ERRORS:
{errors}

YOUR PREVIOUS OUTPUT (contains mistakes — fix them):
{prev_yaml}

ORIGINAL INPUT:
name: {raw.get('name', trait.get('name', ''))}
category: {raw.get('category', 'skill_like')}
description: |
  {raw.get('description', '')}

---
Output corrected YAML with trait name as top-level key.
Include `kind`, `vars` (if any), `text`, and either `passive` or `battle` (not both).
In `battle`, use $key to reference vars (NOT {{var:key}})."""
    return (TRAIT_SYSTEM_PROMPT, user)


# ---------------------------------------------------------------------------
# Parse & validate
# ---------------------------------------------------------------------------


def validate_skill_entry(data: dict) -> list[str]:
    """Validate a single skill's LLM output structure (new canonical format)."""
    errors = []
    if not isinstance(data, dict):
        return ["not a dict"]

    text = data.get("text")
    if not text:
        errors.append("missing text")
    elif not isinstance(text, dict):
        errors.append("text not a dict")
    else:
        if not text.get("name"):
            errors.append("text.name missing")
        if not text.get("description"):
            errors.append("text.description missing")

    bt = data.get("battle")
    if not bt:
        errors.append("missing battle")
    elif not isinstance(bt, dict):
        errors.append("battle not a dict")

    return errors


def validate_trait_entry(data: dict) -> list[str]:
    """Validate a single trait's LLM output structure."""
    errors = []
    if not isinstance(data, dict):
        return ["not a dict"]

    text = data.get("text")
    if not text:
        errors.append("missing text")
    elif not isinstance(text, dict):
        errors.append("text not a dict")
    else:
        if not text.get("name"):
            errors.append("text.name missing")
        if not text.get("description"):
            errors.append("text.description missing")

    kind = data.get("kind")
    if not kind:
        errors.append("missing kind")
    elif kind == "passive":
        if not data.get("passive"):
            errors.append("kind=passive but missing passive section")
        if data.get("battle"):
            errors.append("kind=passive but has battle section (should not)")
    elif kind == "triggered":
        bt = data.get("battle")
        if not bt:
            errors.append("kind=triggered but missing battle section")
        elif not isinstance(bt, dict):
            errors.append("battle not a dict")
    else:
        errors.append(f"unknown kind '{kind}' (must be passive or triggered)")

    return errors


def validate_entry_quality(data: dict) -> list[str]:
    """Post-LLM quality checks on text section. Auto-fixes what it can, returns hard errors only."""
    text = data.get("text", {})
    if not isinstance(text, dict):
        return []

    # Auto-fix known issues first
    fixes = autofix_frontend(text)
    if fixes:
        tqdm.write(f"    [autofix] {'; '.join(fixes)}")

    errors = []
    desc = text.get("description", "")
    cmd_desc = text.get("commander_description", "")
    full_text = f"{desc} {cmd_desc}"
    vars_dict = data.get("vars", {})

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
        ref_key = ref.split(":")[0] if ":" in ref else ref
        if ref_key not in vars_dict:
            errors.append(f"{{var:{ref}}} not in vars")

    # 3. base without max
    for vk, vv in vars_dict.items():
        if isinstance(vv, dict) and 'base' in vv and 'max' not in vv:
            errors.append(f"vars.{vk} has base but no max")

    # 4. Double braces — autofix handles this, but catch if it leaked through
    if _re.search(r'\{\{(var|status|scale|dmg|stat):', full_text):
        errors.append("double braces in description (use single {)")

    # 5. Any text field contains Japanese kana — likely untranslated
    for field in ("name", "description", "commander_description", "brief_description", "target"):
        val = text.get(field, "")
        if has_kana(val):
            errors.append(f"text.{field} contains Japanese kana — not translated")

    # 6. activation_rate with → but no scaling vars
    act_rate = str(text.get("activation_rate", ""))
    if "→" in act_rate or "~" in act_rate:
        # Should have a var with base/max for this
        has_scaling_var = any(
            isinstance(v, dict) and "base" in v and "max" in v
            for v in vars_dict.values()
        )
        if not has_scaling_var:
            errors.append("activation_rate has scaling (→) but no vars use base/max")

    # 7. {var:} or {status:} leaked into battle section (should use $key)
    battle = data.get("battle", {})
    if isinstance(battle, dict):
        battle_str = str(battle)
        if _re.search(r'\{(var|status|scale):', battle_str):
            errors.append("{var:}/{status:}/{scale:} found in battle (use $key)")

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


def _run_batches_parallel(
    batches: list,
    *,
    desc: str,
    parallel: int,
    process_fn,
) -> tuple[dict, list]:
    """Dispatch batches to a thread pool and collect results.

    parallel=1 still goes through ThreadPoolExecutor — single code path so
    behavior is identical between sequential and parallel modes (easier to
    debug). The progress bar advances as batches *finish* (as_completed),
    which matches user expectations of "X of N done". Order of completion
    is non-deterministic but the callers key results by name in a dict, so
    the final output is order-independent.

    process_fn: callable taking one batch and returning (results, failed).
    """
    all_results: dict = {}
    all_failed: list = []
    if not batches:
        return all_results, all_failed

    # Run batch 1 alone to warm the prompt cache, then parallel the rest.
    # Without this, all initial parallel batches would each pay cache_write
    # (1.25x) instead of only the first one writing and the rest reading (0.1x).
    first, rest = batches[:1], batches[1:]
    try:
        results, failed = process_fn(first[0])
        all_results.update(results)
        all_failed.extend(failed)
    except Exception as e:
        tqdm.write(f"  EXC in {desc} batch 1 (cache warm): {e}")

    if rest:
        with ThreadPoolExecutor(max_workers=max(1, parallel)) as ex:
            futures = [ex.submit(process_fn, batch) for batch in rest]
            for fut in tqdm(as_completed(futures), total=len(futures),
                            desc=desc, unit="batch"):
                try:
                    results, failed = fut.result()
                except Exception as e:
                    tqdm.write(f"  EXC in {desc} batch: {e}")
                    continue
                all_results.update(results)
                all_failed.extend(failed)
    return all_results, all_failed


def process_batch(
    skills: list[tuple[str, dict]],
    model: str,
    force: bool,
    single_prompt_fn=None,
    batch_prompt_fn=None,
    cache_prefix: str = "skill",
    corrections: dict | None = None,
    correction_prompt_fn=None,
    provider: str | None = None,
    validate_fn=None,
) -> tuple[dict, list]:
    """Process a batch of items. Returns (results_dict, failed_list).

    corrections: dict mapping name → (prev_yaml, errors) for retry with feedback.
    """
    if single_prompt_fn is None:
        single_prompt_fn = build_single_prompt
    if batch_prompt_fn is None:
        batch_prompt_fn = build_batch_prompt
    if validate_fn is None:
        validate_fn = validate_skill_entry
    if corrections is None:
        corrections = {}
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
        name0 = uncached[0][0]
        if name0 in corrections and correction_prompt_fn:
            prev_yaml, errs = corrections[name0]
            system, user = correction_prompt_fn(uncached[0][1], prev_yaml, errs)
            tqdm.write(f"  [correct] {name0}: feeding back errors to LLM")
        else:
            system, user = single_prompt_fn(uncached[0][1])
    else:
        system, user = batch_prompt_fn(uncached)

    try:
        timeout = 180
        raw = call_llm(user, system_prompt=system, model=model, timeout=timeout, provider=provider)
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
                                         cache_prefix=cache_prefix,
                                         provider=provider)
                    results.update(r)
                    failed.extend(f)
                return results, failed
            else:
                failed.append((uncached[0][0], "YAML parse failed"))
                _count_error("parse_fail")
                tqdm.write(f"  PARSE FAIL: {uncached[0][0]}")
                return results, failed

        # For single skill, output might be nested under skill name or directly have text/battle
        if len(uncached) == 1:
            name = uncached[0][0]
            if "text" in parsed or "frontend" in parsed:
                # Direct output — normalize legacy "frontend" key
                entry = parsed
                if "frontend" in entry and "text" not in entry:
                    entry["text"] = entry.pop("frontend")
            elif name in parsed:
                entry = parsed[name]
                if "frontend" in entry and "text" not in entry:
                    entry["text"] = entry.pop("frontend")
            else:
                # Try first key
                first_key = next(iter(parsed), None)
                entry = parsed[first_key] if first_key else parsed
                if isinstance(entry, dict) and "frontend" in entry and "text" not in entry:
                    entry["text"] = entry.pop("frontend")

            errors = validate_fn(entry)
            quality = validate_entry_quality(entry) if not errors else []
            all_issues = errors + quality
            if all_issues:
                issue_str = "; ".join(all_issues)
                failed.append((name, issue_str))
                _store_correction(name, entry, issue_str)
                for iss in all_issues:
                    _count_error(iss)
                tqdm.write(f"  {'INVALID' if errors else 'QUALITY'}: {name} — {issue_str}")
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
                    _count_error("missing_from_output")
                    tqdm.write(f"  MISSING: {name} not in batch output")
                    continue

                errors = validate_fn(entry)
                if errors:
                    issue_str = "; ".join(errors)
                    failed.append((name, issue_str))
                    _store_correction(name, entry, issue_str)
                    for e in errors:
                        _count_error(e)
                    tqdm.write(f"  INVALID: {name} — {issue_str}")
                    continue

                quality = validate_entry_quality(entry)
                if quality:
                    issue_str = "; ".join(quality)
                    failed.append((name, issue_str))
                    _store_correction(name, entry, issue_str)
                    for q in quality:
                        _count_error(q)
                    tqdm.write(f"  QUALITY: {name} — {issue_str}")
                    continue

                # Normalize legacy "frontend" → "text"
                if "frontend" in entry and "text" not in entry:
                    entry["text"] = entry.pop("frontend")

                # Check for duplicate translated names within this batch
                fe_name = entry.get("text", {}).get("name", "")
                if fe_name and fe_name in seen_names:
                    failed.append((name, f"duplicate name '{fe_name}' in batch"))
                    _count_error("duplicate_name")
                    tqdm.write(f"  DUPE: {name} → '{fe_name}' conflicts with another skill in batch")
                    continue
                if fe_name:
                    seen_names.add(fe_name)

                save_llm_cache(f"{cache_prefix}_{name}", entry)
                results[name] = entry

    except Exception as e:
        for name, _ in uncached:
            failed.append((name, str(e)))
        _count_error("exception")
        tqdm.write(f"  FAILED batch: {e}")

    return results, failed


def process_skills(
    *,
    offset: int = 0,
    limit: int | None = None,
    name_filter: str | None = None,
    force: bool = False,
    model: str = DEFAULT_MODEL,
    batch_size: int = DEFAULT_BATCH_SIZE,
    parallel: int = 1,
    provider: str | None = None,
    preserve_vars: bool = False,
):
    # Read from canonical file; fall back to crawled for bootstrap
    canonical_path = Path(SKILLS_CANONICAL)
    if canonical_path.exists():
        canonical = yaml.safe_load(canonical_path.read_text("utf-8")) or {}
        targets = [(name, entry) for name, entry in canonical.items()]
    else:
        skills = yaml.safe_load(Path(SKILLS_CRAWLED).read_text("utf-8"))
        if not skills:
            print("[error] No skills found")
            sys.exit(1)
        targets = list(skills.items())

    if name_filter:
        targets = [(n, s) for n, s in targets if name_filter in n]
        tqdm.write(f"[filter] Matched {len(targets)} skills for '{name_filter}'")
    if offset:
        targets = targets[offset:]
    if limit:
        targets = targets[:limit]

    tqdm.write(f"[llm] Processing {len(targets)} skills with {model} (batch={batch_size}, parallel={parallel})")

    batches = [targets[i:i + batch_size] for i in range(0, len(targets), batch_size)]
    all_results, all_failed = _run_batches_parallel(
        batches,
        desc="translate",
        parallel=parallel,
        process_fn=lambda b: process_batch(b, model, force, provider=provider),
    )

    # Auto-retry failed items with batch correction feedback
    if all_failed:
        retry_names = {name for name, _ in all_failed}
        retry_targets = [(n, s) for n, s in targets if n in retry_names]
        corrections = {n: _correction_store.pop(n) for n in retry_names if n in _correction_store}

        # Split into correctable (have previous output) and blind retry
        correctable = [(n, s) for n, s in retry_targets if n in corrections]
        blind = [(n, s) for n, s in retry_targets if n not in corrections]

        retry_results = {}
        all_failed = []

        if correctable:
            tqdm.write(f"\n[retry-correct] {len(correctable)} skills with batch correction feedback...")
            corr_batches = [correctable[i:i + batch_size] for i in range(0, len(correctable), batch_size)]
            for batch in tqdm(corr_batches, desc="correct", unit="batch"):
                items = [(n, s, *corrections[n]) for n, s in batch]
                system, user = build_skill_batch_correction_prompt(items)
                try:
                    raw = call_llm(user, system_prompt=system, model=model, timeout=180, provider=provider)
                    save_raw_cache("correct_" + "_".join(n for n, _ in batch), raw)
                    parsed = parse_llm_output(raw)
                    if parsed is None:
                        for n, _ in batch:
                            all_failed.append((n, "correction YAML parse failed"))
                            _count_error("parse_fail")
                        continue
                    parsed_values = list(parsed.values())
                    for i, (name, data) in enumerate(batch):
                        entry = parsed.get(name) or (parsed_values[i] if i < len(parsed_values) else None)
                        if not entry:
                            all_failed.append((name, "missing from correction output"))
                            continue
                        if "frontend" in entry and "text" not in entry:
                            entry["text"] = entry.pop("frontend")
                        errors = validate_skill_entry(entry)
                        quality = validate_entry_quality(entry) if not errors else []
                        issues = errors + quality
                        if issues:
                            issue_str = "; ".join(issues)
                            all_failed.append((name, issue_str))
                            for iss in issues:
                                _count_error(iss)
                            tqdm.write(f"  STILL BAD: {name} — {issue_str}")
                        else:
                            save_llm_cache(f"skill_{name}", entry)
                            retry_results[name] = entry
                except Exception as e:
                    for n, _ in batch:
                        all_failed.append((n, str(e)))
                    _count_error("exception")
                    tqdm.write(f"  FAILED correction batch: {e}")

        if blind:
            tqdm.write(f"\n[retry-blind] {len(blind)} skills without correction context...")
            blind_batches = [[item] for item in blind]
            blind_results, blind_failed = _run_batches_parallel(
                blind_batches,
                desc="retry",
                parallel=parallel,
                process_fn=lambda b: process_batch(b, model, force=True, provider=provider),
            )
            retry_results.update(blind_results)
            all_failed.extend(blind_failed)

        all_results.update(retry_results)

    # Merge results into canonical file
    if canonical_path.exists():
        canonical = yaml.safe_load(canonical_path.read_text("utf-8")) or {}
    else:
        canonical = {}

    updated = 0
    for name, data in all_results.items():
        entry = canonical.setdefault(name, {})
        if data.get("text"):
            entry["text"] = data["text"]
        if data.get("battle"):
            entry["battle"] = data["battle"]
        if data.get("vars") is not None:
            if preserve_vars and entry.get("vars"):
                # Keep existing vars, check for conflicts
                new_keys = set(data["vars"].keys())
                old_keys = set(entry["vars"].keys())
                if new_keys != old_keys:
                    tqdm.write(f"  [preserve-vars] {name}: LLM vars keys differ from existing "
                               f"(added: {new_keys - old_keys}, removed: {old_keys - new_keys}). "
                               f"Use --force-vars to accept LLM vars.")
                    all_failed.append((name, "vars key mismatch under --preserve-vars"))
                    continue
            else:
                entry["vars"] = data["vars"]
        updated += 1

    _save_yaml(canonical_path, canonical)

    tqdm.write(f"\n[done] {len(canonical)} skills ({updated} updated) → {canonical_path}")
    if all_failed:
        tqdm.write(f"[warn] {len(all_failed)} failed:")
        for name, err in all_failed:
            tqdm.write(f"  {name}: {err}")
    _record_failures("skills", all_failed)

    return all_results


def process_traits(
    *,
    offset: int = 0,
    limit: int | None = None,
    name_filter: str | None = None,
    force: bool = False,
    model: str = DEFAULT_MODEL,
    batch_size: int = DEFAULT_BATCH_SIZE,
    parallel: int = 1,
    provider: str | None = None,
    preserve_vars: bool = False,
):
    # Read from canonical file; fall back to crawled for bootstrap
    canonical_path = Path(TRAITS_CANONICAL)
    if canonical_path.exists():
        canonical = yaml.safe_load(canonical_path.read_text("utf-8")) or {}
        targets = [(name, entry) for name, entry in canonical.items()]
    else:
        traits = yaml.safe_load(Path(TRAITS_CRAWLED).read_text("utf-8"))
        if not traits:
            print("[error] No traits found")
            sys.exit(1)
        targets = list(traits.items())

    if name_filter:
        targets = [(n, t) for n, t in targets if name_filter in n]
        tqdm.write(f"[filter] Matched {len(targets)} traits for '{name_filter}'")
    if offset:
        targets = targets[offset:]
    if limit:
        targets = targets[:limit]

    tqdm.write(f"[llm] Processing {len(targets)} traits with {model} (batch={batch_size}, parallel={parallel})")

    batches = [targets[i:i + batch_size] for i in range(0, len(targets), batch_size)]
    all_results, all_failed = _run_batches_parallel(
        batches,
        desc="traits",
        parallel=parallel,
        process_fn=lambda b: process_batch(
            b, model, force,
            single_prompt_fn=build_trait_single_prompt,
            batch_prompt_fn=build_trait_batch_prompt,
            cache_prefix="trait",
            provider=provider,
            validate_fn=validate_trait_entry,
        ),
    )

    # Auto-retry failed items with correction feedback (single-item for traits)
    if all_failed:
        retry_names = {name for name, _ in all_failed}
        retry_targets = [(n, t) for n, t in targets if n in retry_names]
        corrections = {n: _correction_store.pop(n) for n in retry_names if n in _correction_store}
        tqdm.write(f"\n[retry] {len(retry_targets)} failed traits ({len(corrections)} with correction feedback)...")
        retry_batches = [[item] for item in retry_targets]
        retry_results, all_failed = _run_batches_parallel(
            retry_batches,
            desc="retry",
            parallel=parallel,
            process_fn=lambda b: process_batch(
                b, model, force=True,
                single_prompt_fn=build_trait_single_prompt,
                batch_prompt_fn=build_trait_batch_prompt,
                cache_prefix="trait",
                corrections=corrections,
                correction_prompt_fn=build_trait_correction_prompt,
                provider=provider,
                validate_fn=validate_trait_entry,
            ),
        )
        all_results.update(retry_results)

    # Merge results into canonical file
    if canonical_path.exists():
        canonical = yaml.safe_load(canonical_path.read_text("utf-8")) or {}
    else:
        canonical = {}

    updated = 0
    for name, data in all_results.items():
        entry = canonical.setdefault(name, {})
        # Normalize legacy "frontend" → "text"
        if "frontend" in data and "text" not in data:
            data["text"] = data.pop("frontend")
        if data.get("text"):
            entry["text"] = data["text"]
        if data.get("kind"):
            entry["kind"] = data["kind"]
        if data.get("battle"):
            entry["battle"] = data["battle"]
        if data.get("passive"):
            entry["passive"] = data["passive"]
        if data.get("vars") is not None:
            if preserve_vars and entry.get("vars"):
                new_keys = set(data["vars"].keys())
                old_keys = set(entry["vars"].keys())
                if new_keys != old_keys:
                    tqdm.write(f"  [preserve-vars] {name}: vars keys differ "
                               f"(added: {new_keys - old_keys}, removed: {old_keys - new_keys}). "
                               f"Use --force-vars to accept.")
                    all_failed.append((name, "vars key mismatch under --preserve-vars"))
                    continue
            else:
                entry["vars"] = data["vars"]
        updated += 1

    _save_yaml(canonical_path, canonical)

    tqdm.write(f"\n[done] {len(canonical)} traits ({updated} updated) → {canonical_path}")
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
    provider: str | None = None,
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

    system, user = build_hero_batch_prompt(uncached)

    try:
        timeout = 180
        raw = call_llm(user, system_prompt=system, model=model, timeout=timeout, provider=provider)
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

            # Check kana in all translated fields
            kana_fields = [f for f in ("name", "faction", "clan") if has_kana(entry.get(f, ""))]
            if kana_fields:
                issue = f"Japanese kana in: {', '.join(kana_fields)}"
                failed.append((name, issue))
                tqdm.write(f"  QUALITY: {name} — {issue}")
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
    offset: int = 0,
    limit: int | None = None,
    name_filter: str | None = None,
    force: bool = False,
    model: str = DEFAULT_MODEL,
    batch_size: int = 25,
    parallel: int = 1,
    provider: str | None = None,
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
    if offset:
        targets = targets[offset:]
    if limit:
        targets = targets[:limit]

    tqdm.write(f"[llm] Processing {len(targets)} heroes with {model} (batch={batch_size}, parallel={parallel})")

    batches = [targets[i:i + batch_size] for i in range(0, len(targets), batch_size)]
    all_results, all_failed = _run_batches_parallel(
        batches,
        desc="heroes",
        parallel=parallel,
        process_fn=lambda b: process_hero_batch(b, model, force, provider=provider),
    )

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


def main():
    p = argparse.ArgumentParser(description="LLM translate + extract skills, traits, and heroes")
    p.add_argument("--skills", action="store_true", help="Process skills only")
    p.add_argument("--traits", action="store_true", help="Process traits only")
    p.add_argument("--heroes", action="store_true", help="Process heroes only")
    p.add_argument("--offset", type=int, default=0, help="Skip first N items")
    p.add_argument("--limit", type=int, help="Max items to process")
    p.add_argument("--name", help="Filter by name (substring)")
    p.add_argument("--force", action="store_true", help="Ignore cache, overwrite output")
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"OpenRouter model: free={MODEL_FREE}, gemma={MODEL_GEMMA}, haiku={MODEL_HAIKU}, sonnet={MODEL_SONNET} (default)")
    p.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Items per LLM call")
    p.add_argument("--parallel", type=int, default=1, help="Number of batches to dispatch concurrently (default: 1, recommended max: 5)")
    p.add_argument("--provider", help="OpenRouter provider name (e.g. Parasail, 'Google AI Studio', Anthropic)")
    p.add_argument("--preserve-vars", action="store_true", help="Keep existing vars; abort if LLM output has different keys")
    p.add_argument("--force-vars", action="store_true", help="Accept LLM vars even under --preserve-vars (override conflict)")
    args = p.parse_args()

    _error_counts.clear()
    _correction_store.clear()
    reset_token_totals()

    # Default: all if none specified
    none_specified = not args.skills and not args.traits and not args.heroes
    do_skills = args.skills or none_specified
    do_traits = args.traits or none_specified
    do_heroes = args.heroes or none_specified

    pv = args.preserve_vars and not args.force_vars

    if do_skills:
        process_skills(
            offset=args.offset,
            limit=args.limit,
            name_filter=args.name,
            force=args.force,
            model=args.model,
            batch_size=args.batch_size,
            parallel=args.parallel,
            preserve_vars=pv,
            provider=args.provider,
        )
    if do_traits:
        process_traits(
            offset=args.offset,
            limit=args.limit,
            name_filter=args.name,
            force=args.force,
            model=args.model,
            batch_size=args.batch_size,
            parallel=args.parallel,
            preserve_vars=pv,
            provider=args.provider,
        )
    if do_heroes:
        process_heroes(
            offset=args.offset,
            limit=args.limit,
            name_filter=args.name,
            force=args.force,
            model=args.model,
            batch_size=args.batch_size,
            parallel=args.parallel,
            provider=args.provider,
        )

    _write_failure_manifest()
    _print_error_summary()
    _print_token_summary(args.model)


if __name__ == "__main__":
    main()
