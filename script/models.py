"""
Pydantic v2 models describing the TARGET canonical schema for skills and traits.

This is Phase 0 scaffolding: nothing in the live pipeline imports these yet.
The audit script (audit_canonical.py) uses them to dry-fit current YAML data
against the proposed shape and report drift / violations.

Design decisions (see plan: hidden-coalescing-kahn.md):
- Two independent top-level models (Skill, Trait), no Ability base class.
- Vars hoisted to entry level: SHARED between text template refs ({var:X})
  and battle field refs ($X). Single source of numeric truth.
- Trait `kind` discriminator: passive (truly always-on) vs triggered (any
  engine-driven timing). Mutually exclusive — a trait has either `passive`
  or `battle`, never both.
- Skill `kind` is always 'skill' for the engine-side discriminator; the
  game's six skill types (主動/被動/指揮/突擊/兵種/陣法) live in `text.type`.
- Closed troop vocabulary enforced via Literal: exactly five values.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Shared vocabulary
# ---------------------------------------------------------------------------

TroopType = Literal["足輕", "弓兵", "騎兵", "鐵炮", "器械"]

SKILL_TYPES = Literal["主動", "被動", "指揮", "突擊", "兵種", "陣法"]


class _StrictModel(BaseModel):
    """Base class: forbid unknown fields so schema drift surfaces immediately."""
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Vars: a single dict per entry, used by both text and battle
# ---------------------------------------------------------------------------
# Vars values are intentionally loose (Any) at this audit phase. Real schema
# typing (e.g. {base, max, scale} for scaling vars vs plain int/float for
# constants) can be tightened in Phase 1+ once the audit shows the actual
# distribution of value shapes in the wild.

VarsDict = dict[str, Any]


# ---------------------------------------------------------------------------
# Skill
# ---------------------------------------------------------------------------

class RawSkill(_StrictModel):
    """Original JP fields from game8.jp crawl."""
    name: str
    rarity: Optional[str] = None
    type: Optional[str] = None
    target: Optional[str] = None
    activation_rate: Optional[str] = None
    description: Optional[str] = None
    commander_bonus: Optional[str] = None
    source_hero: Optional[str] = None
    is_unique: bool = False
    is_teachable: bool = False
    is_event_skill: bool = False
    detail_url: Optional[str] = None
    icon: Optional[str] = None


class TextSkill(_StrictModel):
    """CHT translation + frontend display metadata."""
    name: str
    type: SKILL_TYPES
    rarity: str
    target: Optional[str] = None
    activation_rate: Optional[str] = None
    description: str
    brief_description: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    commander_description: Optional[str] = None


class BattleSkill(_StrictModel):
    """Engine-facing structured effect spec."""
    type: Optional[str] = None  # mirrors text.type
    trigger: Optional[str] = None
    do: list[dict] = Field(default_factory=list)
    bonus: Optional[dict] = None


class Skill(_StrictModel):
    raw: RawSkill
    vars: VarsDict = Field(default_factory=dict)
    text: TextSkill
    battle: BattleSkill = Field(default_factory=BattleSkill)
    meta: Optional[dict] = None  # provenance, _action, etc.


# ---------------------------------------------------------------------------
# Trait
# ---------------------------------------------------------------------------

class RawTrait(_StrictModel):
    name: str
    description: Optional[str] = None
    category: Optional[str] = None  # legacy 'troop_affinity' / 'skill_like' from old battle yaml
    source_heroes: list[str] = Field(default_factory=list)


class TextTrait(_StrictModel):
    name: str
    description: str


class Affinity(_StrictModel):
    """Closed-vocab troop affinity. The integer 'level' is the trait's
    contribution to a team-level aggregator; 'level_cap_bonus' raises the
    per-team cap from default 10."""
    troop_types: list[TroopType] = Field(min_length=1)
    level: int = Field(ge=0)
    level_cap_bonus: int = Field(ge=0, default=0)


class PassiveBuff(_StrictModel):
    """Always-on stat/damage modifier contribution. Engine reads these
    declaratively, no trigger/do pipeline."""
    target: str  # self / armyAll / etc.
    stat: str   # 統率 / damage_dealt / crit_damage / ...
    type: Literal["pct", "flat"]
    value: Any  # int/float OR a $var reference string


class PassiveBlock(_StrictModel):
    """Container for the passive (always-on) effect data on a trait.
    At least one of affinity / buffs must be present."""
    affinity: Optional[Affinity] = None
    buffs: list[PassiveBuff] = Field(default_factory=list)

    @model_validator(mode="after")
    def _at_least_one(self):
        if self.affinity is None and not self.buffs:
            raise ValueError("passive block requires affinity and/or non-empty buffs")
        return self


class BattleTrait(_StrictModel):
    """Triggered trait body — same shape as a triggered skill's battle section."""
    trigger: str
    do: list[dict] = Field(default_factory=list)


class Trait(_StrictModel):
    raw: RawTrait
    vars: VarsDict = Field(default_factory=dict)
    text: TextTrait
    kind: Literal["passive", "triggered"]
    passive: Optional[PassiveBlock] = None
    battle: Optional[BattleTrait] = None
    meta: Optional[dict] = None

    @model_validator(mode="after")
    def _kind_matches_body(self):
        if self.kind == "passive":
            if self.passive is None:
                raise ValueError("kind=passive requires a passive block")
            if self.battle is not None:
                raise ValueError("kind=passive must not carry a battle block")
        elif self.kind == "triggered":
            if self.battle is None:
                raise ValueError("kind=triggered requires a battle block")
            if self.passive is not None:
                raise ValueError("kind=triggered must not carry a passive block")
        return self
