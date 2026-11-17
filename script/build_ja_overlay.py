"""
Build .build/ja.json: the Japanese text of the frontend catalog, as an overlay on .build/*.json.

The Japanese is the game's own, from the official cfg (`multi_lang` rows, `ja`): names, targets, short
descriptions and the skill descriptions. cfg descriptions carry numbered slots (`{1%}`) where the game fills in
numbers; the numbers stay ours (`vars` of the built skill, overrides included). Each slot is tied to a var by
lining the official text up with a text that names or spells out the numbers:

  A. the official zh-hant text against our description (its `{var:name}` tokens),
  B. the official ja text against the game8 ja text (literal numbers, matched to a var by value),
  C. the official zh-hant text against an override's `raw_text` (literal numbers, likewise).

A slot is settled when every source that reaches it gives the same value. What stays open is listed and that
skill keeps its zh-TW text (it is left out of the overlay) until `data/ja_overlay.yaml` names the slots.

Trait text is the game8 ja text (short, numbers written in); a trait game8 lacks is read from cfg the same way
as a skill. Terms (factions, clans, skill types, tags, statuses) are looked up in cfg by their zh-hant spelling;
`data/ja_overlay.yaml` holds the ones cfg lacks and the status descriptions, which are ours.

Usage:
    uv run script/build_ja_overlay.py            # writes .build/ja.json, prints what is missing
"""

from __future__ import annotations

import difflib
import json
import re
import sys
import unicodedata
from collections import defaultdict

import yaml

from merge_sources import opencc_s2tw
from paths import (
    BINGXUE_JSON,
    BUILD_DIR,
    CFG_CURRENT_JSON,
    DATA_DIR,
    HEROES_JSON,
    OVERRIDES_YAML,
    SKILLS_CANONICAL,
    SKILLS_JSON,
    STATUSES_JSON,
    TRAITS_CANONICAL,
)

JA_JSON = BUILD_DIR / "ja.json"
JA_HAND_YAML = DATA_DIR / "ja_overlay.yaml"

_TAG = re.compile(r"<[^>]+>")
_SLOT = re.compile(r"\{(\d+)(%?)\}")
_NUM = r"\d+(?:\.\d+)?%?"
_LITERAL = re.compile(rf"{_NUM}(?:(?:→|->|~|/){_NUM})?")
_TOKEN = re.compile(rf"\{{(\d+)%?\}}|\{{var:(\w+)\}}%?|({_LITERAL.pattern})")
_NAMED = re.compile(r"\{(scale|status|dmg|stat):([^}:]+)[^}]*\}")
_COMMANDER = re.compile(r"\s*\n?\s*大将技[:：]\s*")
_KANA = re.compile(r"[぀-ヿ]")


class Mark:
    """A number's place in a text: a slot, a var or a literal. All compare equal, so texts line up on them."""

    def __init__(self, kind: str, value: str):
        self.kind, self.value = kind, value

    def __eq__(self, other):
        return isinstance(other, Mark)

    def __hash__(self):
        return 0


def plain(text: str | None) -> str:
    """cfg text without its markup."""
    return _TAG.sub("", text or "").strip()


def tokens(text: str) -> list:
    """The text as characters and Marks, in a form two spellings of one sentence agree on."""
    text = _NAMED.sub(lambda m: f"受{m.group(2)}影響" if m.group(1) == "scale" else m.group(2), plain(text))
    text = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))
    out: list = []
    pos = 0
    for m in _TOKEN.finditer(text):
        out.extend(text[pos : m.start()])
        slot, var, literal = m.groups()
        out.append(Mark("slot", slot) if slot else Mark("var", var) if var else Mark("num", literal))
        pos = m.end()
    out.extend(text[pos:])
    return out


def lined_up(official: str, other: str) -> list[tuple[str, Mark]]:
    """(slot, the Mark across from it) for every slot of `official` that sits in a shared run of the two texts."""
    a, b = tokens(official), tokens(other)
    found = []
    for block in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        if block.size < 3:
            continue  # a slot with no shared words around it proves nothing
        for k in range(block.size):
            if a[block.a + k].__class__ is Mark and a[block.a + k].kind == "slot":
                found.append((a[block.a + k].value, b[block.b + k]))
    return found


def in_order(official: str, other: str) -> list[tuple[str, Mark]]:
    """(slot, the Mark at the same place) when both texts hold as many numbers and every literal pair agrees.

    For two zh spellings of one short sentence (a trait): the numbers then come in the same order.
    """
    a = [t for t in tokens(official) if t.__class__ is Mark]
    b = [t for t in tokens(other) if t.__class__ is Mark]
    literal_pairs = [(x, y) for x, y in zip(a, b) if x.kind == "num"]
    if len(a) != len(b) or any(not same(literal_value(x.value), literal_value(y.value)) for x, y in literal_pairs if y.kind == "num"):
        return []
    return [(x.value, y) for x, y in zip(a, b) if x.kind == "slot"]


def literal_value(literal: str) -> tuple[float, ...] | None:
    """'7%→14%' as (0.07, 0.14); '2' as (2.0,)."""
    parts = re.split(r"→|->|~|/", unicodedata.normalize("NFKC", literal))
    try:
        return tuple(float(p[:-1]) / 100 if p.endswith("%") else float(p) for p in parts)
    except ValueError:
        return None


def var_value(value) -> tuple[float, ...] | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return (float(value),)
    if isinstance(value, str):
        return literal_value(re.sub(r"\s+", "", value)) if _LITERAL.fullmatch(unicodedata.normalize("NFKC", value)) else None
    if isinstance(value, dict) and isinstance(value.get("base"), (int, float)):
        top = value.get("max", value["base"])
        return (float(value["base"]), float(top)) if isinstance(top, (int, float)) else None
    return None


def same(a: tuple | None, b: tuple | None) -> bool:
    if a is None or b is None:
        return False
    a, b = (a[:1] if len(set(a)) == 1 else a), (b[:1] if len(set(b)) == 1 else b)
    return len(a) == len(b) and all(abs(x - y) < 1e-6 for x, y in zip(a, b))


def shows_percent(value) -> bool:
    """Whether the frontend prints this var with a % (src/composables/useTemplateParser.ts formatVarValue)."""
    if isinstance(value, dict):
        return value.get("type") != "flat"
    return isinstance(value, (int, float)) and 0 < value < 1


class Slots:
    """What each slot of one official text can be: `{var:name}` tokens and literals, with the value of each."""

    def __init__(self, final_vars: dict):
        self.vars = final_vars or {}
        self.found: dict[str, dict[str, tuple]] = defaultdict(dict)

    def add_var(self, slot: str, name: str) -> None:
        value = var_value(self.vars.get(name))
        if value is not None:
            self.found[slot][f"{{var:{name}}}"] = value

    def add_literal(self, slot: str, literal: str, names_from: dict | None = None, keep_literal: bool = True) -> None:
        """A literal becomes the var of that value; `names_from` (the vars before overrides) may name it instead."""
        value = literal_value(literal)
        names = [n for n, v in self.vars.items() if same(var_value(v), value)]
        if not names and names_from:
            names = [n for n, v in names_from.items() if n in self.vars and same(var_value(v), value)]
        for name in names:
            self.add_var(slot, name)
        if not names and keep_literal and value is not None:
            self.found[slot][literal.replace("->", "→")] = value

    def settled(self, slot: str) -> str | None:
        """The one thing the slot can be. A var beats a literal: where they differ the number is ours to state."""
        options = self.found.get(slot) or {}
        named = {o: v for o, v in options.items() if o.startswith("{var:")}
        values = list((named or options).values())
        if not values or any(not same(values[0], v) for v in values[1:]):
            return None
        return next(iter(named or options))  # the first found: source A, our own description, when it reached the slot

    def literals_against(self, slot: str, choice: str) -> list[str]:
        """Literals another source spells for the slot that differ from the chosen var's value."""
        options = self.found.get(slot) or {}
        return sorted(o for o, v in options.items() if not o.startswith("{var:") and not same(v, options.get(choice)))


def fill(text: str, slots: Slots, hand: dict, problems: list[str], notes: list[str]) -> str | None:
    """`text` with every slot replaced; None (and a line in `problems`) when one stays open or reads wrong.

    A slot that wants a percent (`{1%}`, or `{1}%`) gets `{var:name}%`: the frontend then prints a plain number
    such as 1.34 as 134% and eats the sign. A var the frontend prints the other way than the slot wants is a problem.
    """
    ok = True

    def one(m: re.Match) -> str:
        nonlocal ok
        slot = m.group(1)
        percent = bool(m.group(2)) or text[m.end() : m.end() + 1] in ("%", "％")
        by_hand = hand.get(int(slot), hand.get(slot))
        choice = slots.settled(slot) if by_hand is None else str(by_hand)
        if choice is None:
            options = ", ".join(sorted(slots.found.get(slot, {}))) or "nothing lines up"
            problems.append(f"slot {{{slot}}}: {options}")
            ok = False
            return m.group(0)
        if choice in slots.vars:
            choice = f"{{var:{choice}}}"
        var = re.fullmatch(r"\{var:(\w+)\}", choice)
        if not var:
            return choice[:-1] if choice.endswith("%") and not m.group(2) and percent else choice
        value = slots.vars.get(var.group(1))
        flat = isinstance(value, dict) and value.get("type") == "flat"
        if value is None or (percent and flat) or (not percent and shows_percent(value)):
            problems.append(f"slot {{{slot}}}: {choice} = {json.dumps(value)} does not print as the slot wants")
            ok = False
        if by_hand is None and slots.literals_against(slot, choice):
            notes.append(f"slot {{{slot}}} is {choice}; another source reads {', '.join(slots.literals_against(slot, choice))}")
        return choice + ("%" if m.group(2) else "")

    filled = _SLOT.sub(one, text)
    return filled if ok else None


def tag_statuses(text: str, cht_text: str, status_ja: dict[str, str]) -> str:
    """Marks in the ja text the statuses our own description marks (`{status:CHT}`), longest name first."""
    wanted = {s for s in re.findall(r"\{status:([^}]+)\}", cht_text) if status_ja.get(s)}
    by_ja = {status_ja[s]: s for s in wanted}
    if not by_ja:
        return text
    names = "|".join(re.escape(n) for n in sorted(by_ja, key=len, reverse=True))
    # `{...}` tokens pass through whole: a var may be named after a status.
    return re.sub(rf"\{{[^}}]*\}}|{names}", lambda m: m.group(0) if m.group(0).startswith("{") else f"{{status:{by_ja[m.group(0)]}}}", text)


class Cfg:
    def __init__(self):
        cfg = json.loads(CFG_CURRENT_JSON.read_text("utf-8"))
        rows = [r for r in cfg.get("multi_lang", []) if isinstance(r.get("zh-hans"), str)]
        self.by_hans = {r["zh-hans"]: r for r in rows}
        self.by_hant: dict[str, dict] = {}
        for r in rows:
            if isinstance(r.get("zh-hant"), str):
                self.by_hant.setdefault(r["zh-hant"], r)
        self.skill = {s["id"]: s for s in cfg.get("skill", [])}
        self.skill_by_name = {s["name"]: s for s in cfg.get("skill", [])}
        self.skill_by_shown = {self.hant(s.get("show_name")): s for s in cfg.get("skill", [])}

    def ja(self, hans: str | None) -> str | None:
        return plain((self.by_hans.get(hans or "") or {}).get("ja")) or None

    def hant(self, hans: str | None) -> str:
        return plain((self.by_hans.get(hans or "") or {}).get("zh-hant") or opencc_s2tw(hans) or "")

    def ja_of_hant(self, hant: str | None) -> str | None:
        return plain((self.by_hant.get(hant or "") or {}).get("ja")) or None

    def skill_named(self, hant: str, kinds: tuple[str, ...]) -> dict | None:
        """The cfg skill of one of `kinds` whose zh-hant name, or shown name (馬術Ⅲ), is `hant`: for rows with no cfg_id."""
        row = self.by_hant.get(hant)
        skill = (self.skill_by_name.get(row["zh-hans"]) if row else None) or self.skill_by_shown.get(hant)
        return skill if skill and skill.get("skill_kind") in kinds else None


def game8_text(raw: dict) -> str:
    """A game8 description with its 大将技 part set off the way cfg text has it (game8 runs the two together)."""
    text, commander = raw.get("description") or "", raw.get("commander_bonus") or ""
    tail = "大将技：" + commander
    return text[: -len(tail)] + "\n" + tail if commander and text.endswith(tail) else text


def split_commander(text: str) -> tuple[str, str]:
    parts = _COMMANDER.split(text, maxsplit=1)
    return parts[0].strip(), (parts[1].strip() if len(parts) > 1 else "")


def skill_entry(skill: dict, cfg: Cfg, canon: dict, overrides: dict, hand: dict, status_ja: dict, report: dict) -> dict:
    name = skill["name"]
    entry: dict = {}
    c = cfg.skill.get(skill.get("cfg_id")) or cfg.skill_named(name, ("评定众",))
    if not skill.get("name_jp"):
        ja_name = hand.get("name") or (cfg.ja(c["name"]) if c else None) or cfg.ja_of_hant(name)
        if ja_name:
            entry["name"] = ja_name
        else:
            report["skill_names"].append(name)
    if c:
        for field, source in (("target", "target_tips"), ("brief_description", "short_tips")):
            if skill.get(field) and cfg.ja(c.get(source)):
                entry[field] = cfg.ja(c[source])
    cht = skill.get("description", "") + ("\n大將技：" + skill["commander_description"] if skill.get("commander_description") else "")
    raw = (canon.get(skill.get("name_jp")) or {}).get("raw") or {}
    patched = name in overrides or skill.get("name_jp") in overrides
    text = hand.get("description")
    if text is None and c and cfg.ja(c.get("tips")):
        slots = Slots(skill.get("vars") or {})
        official_ja, official_hant = cfg.ja(c["tips"]), cfg.hant(c["tips"])
        for slot, mark in lined_up(official_hant, cht):
            slots.add_var(slot, mark.value) if mark.kind == "var" else slots.add_literal(slot, mark.value)
        before = (canon.get(skill.get("name_jp")) or {}).get("vars") or {}
        for slot, mark in lined_up(official_ja, raw.get("description") or "") if raw else []:
            slots.add_literal(slot, mark.value, before, keep_literal=not patched)
        for slot, mark in lined_up(official_hant, (overrides.get(name) or {}).get("raw_text") or ""):
            slots.add_literal(slot, mark.value)
        problems: list[str] = []
        notes: list[str] = []
        text = fill(official_ja, slots, hand.get("slots") or {}, problems, notes)
        if problems:
            report["skills_open"][name] = {"ja": official_ja, "zh": cht, "vars": skill.get("vars"), "problems": problems}
        if notes:
            report["value_notes"][name] = notes
    elif text is None and raw.get("description") and not patched:
        text = game8_text(raw)  # no official text: the game8 wording, its numbers written in
    elif text is None:
        report["skills_no_source"].append(name)
    if text:
        body, commander = split_commander(tag_statuses(text, cht, status_ja))
        entry["description"] = body
        if commander or hand.get("commander_description"):
            entry["commander_description"] = hand.get("commander_description") or commander
    return entry


def numbers(text: str, variables: dict | None = None) -> list[tuple]:
    """Every number the text shows, vars filled in, sorted: for telling whether two texts state the same figures."""
    out = []
    for m in _TOKEN.finditer(unicodedata.normalize("NFKC", text or "")):
        slot, var, literal = m.groups()
        value = var_value((variables or {}).get(var)) if var else literal_value(literal) if literal else None
        if value is not None:
            out.append(tuple(round(x, 6) for x in (value[:1] if len(set(value)) == 1 else value)))
    return sorted(out)


def contains(more: list[tuple], fewer: list[tuple]) -> bool:
    left = list(more)
    for value in fewer:
        if value not in left:
            return False
        left.remove(value)
    return True


def trait_entries(heroes: list[dict], cfg: Cfg, canon: dict, hand: dict, report: dict) -> dict:
    out: dict = {}
    for hero in heroes:
        for trait in hero.get("traits") or []:
            name = trait["name"]
            if name in out:
                continue
            by_hand = hand.get(name) or {}
            raw = (canon.get(trait.get("name_jp")) or {}).get("raw") or {}
            c = cfg.skill_named(name, ("特性", "天赋"))
            entry = {"name": by_hand.get("name") or trait.get("name_jp") or (cfg.ja(c["show_name"]) if c else None)}
            text = by_hand.get("description") or raw.get("description")
            if text and not by_hand.get("description") and not contains(numbers(text), numbers(trait.get("description", ""), trait.get("vars"))):
                report["traits_numbers"][name] = {"ja": text, "zh": trait.get("description"), "vars": trait.get("vars")}
            if not text and c and cfg.ja(c.get("tips")):
                slots = Slots(trait.get("vars") or {})
                hant, ours = cfg.hant(c["tips"]), trait.get("description") or ""
                for slot, mark in lined_up(hant, ours) or in_order(hant, ours):
                    slots.add_var(slot, mark.value) if mark.kind == "var" else slots.add_literal(slot, mark.value)
                problems: list[str] = []
                text = fill(cfg.ja(c["tips"]), slots, by_hand.get("slots") or {}, problems, [])
                if problems:
                    report["traits_open"][name] = {"ja": cfg.ja(c["tips"]), "zh": trait.get("description"), "vars": trait.get("vars"), "problems": problems}
            if not entry["name"] or (trait.get("description") and not text):
                report["traits_missing"].append(name)
            out[name] = {k: v for k, v in {**entry, "description": text}.items() if v}
    return out


def term_table(heroes: list[dict], skills: list[dict], statuses: dict, cfg: Cfg, hand: dict, report: dict) -> dict:
    wanted: set[str] = set()
    for hero in heroes:
        wanted |= {hero.get("faction"), hero.get("clan"), hero.get("gender")}
        for trait in hero.get("traits") or []:
            wanted |= set((trait.get("affinity") or {}).get("troop_types") or [])
    for skill in skills:
        wanted |= {skill.get("type"), *(skill.get("tags") or [])}
    for table in ("_stats", "_damage_types"):
        wanted |= {row["name"] for row in (statuses.get(table) or {}).values()}
    out = {}
    for term in sorted(t for t in wanted if t):
        ja = hand.get(term) or cfg.ja_of_hant(term)
        if ja:
            out[term] = ja
        else:
            report["terms"].append(term)
    return {**out, **{k: v for k, v in hand.items() if k not in out}}


def status_entries(statuses: dict, cfg: Cfg, hand: dict, report: dict) -> dict:
    out = {}
    for key, row in statuses.items():
        if key.startswith("_"):
            continue
        by_hand = hand.get(key) or {}
        entry = {"name": by_hand.get("name") or cfg.ja_of_hant(key), "description": by_hand.get("description")}
        if not entry["name"] or (row.get("description") and not entry["description"]):
            report["statuses"].append(key)
        out[key] = {k: v for k, v in entry.items() if v}
    return out


def bingxue_entries(bingxue: dict, hand: dict, report: dict) -> dict:
    """The crawled `description_jp` with its two levels (`2.5%/5%`) as a range the frontend switches by level
    (`2.5%→5%`), or the hand text where the crawl is behind an override."""
    out = {}
    for key, row in bingxue.items():
        text = (hand.get(key) or {}).get("description") or re.sub(rf"({_NUM})/({_NUM})", r"\1→\2", row.get("description_jp") or "")
        if not contains(numbers(text), numbers(row.get("description", ""), row.get("vars"))):
            report["bingxue_numbers"][key] = {"ja": text, "zh": row.get("description"), "vars": row.get("vars")}
        out[key] = {"description": text}
    return out


def build() -> tuple[dict, dict]:
    heroes = json.loads(HEROES_JSON.read_text("utf-8"))
    skills = json.loads(SKILLS_JSON.read_text("utf-8"))
    statuses = json.loads(STATUSES_JSON.read_text("utf-8"))
    bingxue = json.loads(BINGXUE_JSON.read_text("utf-8"))
    hand = (yaml.safe_load(JA_HAND_YAML.read_text("utf-8")) if JA_HAND_YAML.exists() else None) or {}
    overrides = (yaml.safe_load(OVERRIDES_YAML.read_text("utf-8")) or {}).get("skills") or {}
    skills_canon = yaml.safe_load(SKILLS_CANONICAL.read_text("utf-8")) or {}
    traits_canon = yaml.safe_load(TRAITS_CANONICAL.read_text("utf-8")) or {}
    cfg = Cfg()
    report: dict = {
        "terms": [], "statuses": [], "skill_names": [], "skills_no_source": [], "skills_open": {},
        "traits_missing": [], "traits_open": {}, "traits_numbers": {}, "bingxue_numbers": {}, "value_notes": {},
    }
    status_rows = status_entries(statuses, cfg, hand.get("statuses") or {}, report)
    status_ja = {key: row["name"] for key, row in status_rows.items() if row.get("name")}
    skill_hand = hand.get("skills") or {}
    skill_rows = {s["name"]: skill_entry(s, cfg, skills_canon, overrides, skill_hand.get(s["name"]) or {}, status_ja, report) for s in skills}
    overlay = {
        "terms": term_table(heroes, skills, statuses, cfg, hand.get("terms") or {}, report),
        "statuses": status_rows,
        "skills": {name: row for name, row in skill_rows.items() if row},
        "traits": trait_entries(heroes, cfg, traits_canon, hand.get("traits") or {}, report),
        "bingxue": bingxue_entries(bingxue, hand.get("bingxue") or {}, report),
    }
    report["skills_total"] = len(skills)
    report["skills_described"] = sum(1 for row in skill_rows.values() if row.get("description"))
    return overlay, report


def main() -> int:
    overlay, report = build()
    JA_JSON.write_text(json.dumps(overlay, ensure_ascii=False, indent=1) + "\n", "utf-8")
    (BUILD_DIR / "ja_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(f"[ja] skills described {report['skills_described']}/{report['skills_total']}, traits {len(overlay['traits'])}, "
          f"terms {len(overlay['terms'])}, statuses {len(overlay['statuses'])}")
    for label in ("terms", "statuses", "skill_names", "skills_no_source", "traits_missing"):
        if report[label]:
            print(f"[ja] {label} without ja ({len(report[label])}): {'、'.join(report[label])}")
    for label in ("skills_open", "traits_open", "traits_numbers", "bingxue_numbers", "value_notes"):
        if report[label]:
            print(f"[ja] {label} ({len(report[label])}): {'、'.join(report[label])}  (see .build/ja_report.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
