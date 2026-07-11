"""Apply per-hero 兵學 (bingxue) option pools into data/overrides.yaml.

Parses free-form paste text (CHT/JP names, CHT or JP direction labels),
resolves every option against data/bingxue.yaml, and writes the JP-keyed
structure expected by build_frontend_data.py.

Hard-fails on anything ambiguous or undefined so a human/agent can fix it.

Usage:
    uv run script/apply_bingxue_override.py path/to/paste.txt
    uv run script/apply_bingxue_override.py -                 # stdin
    uv run script/apply_bingxue_override.py --dry-run paste.txt
    uv run script/apply_bingxue_override.py --allow-partial paste.txt
    uv run script/apply_bingxue_override.py --force paste.txt  # overwrite existing

Expected paste shape (multi-hero ok)::

    伊達政宗: 【兵學】

    Major category - 機略
    主要兵學：
    * 離間之計 / 離間の計
    * 詭計百出
    * 破陣之勢 / 破陣の勢い

    次要兵學：
    * 神算I / 神算
    ...
    ---
    Major category - 武略
    ...
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

from paths import (
    BINGXUE_CANONICAL,
    BINGXUE_JP_TO_CHT_DIR,
    HEROES_CRAWLED,
    HEROES_TRANSLATED,
    OVERRIDES_YAML,
)

# Reverse of BINGXUE_JP_TO_CHT_DIR (CHT label → JP storage key).
BINGXUE_CHT_TO_JP_DIR = {cht: jp for jp, cht in BINGXUE_JP_TO_CHT_DIR.items()}

# Canonical order written into overrides (matches existing entries).
JP_DIR_ORDER = ("陣立", "武略", "臨戦", "機略")

EXPECTED_MAJOR = 3
EXPECTED_MINOR = 6

# Level suffixes players paste next to minor names (神算I, 多謀II, …).
_LEVEL_SUFFIX_RE = re.compile(
    r"(?:"
    r"I{1,3}|Ⅰ{1,3}|Ⅱ|Ⅲ|"
    r"[1-3]|"
    r"Lv\.?\s*[12]"
    r")$",
    re.IGNORECASE,
)

_HERO_HEADER_RE = re.compile(
    r"^\s*(?P<name>.+?)\s*[:：]\s*(?:【?\s*兵[學学]\s*】?)?\s*$"
)
_DIR_HEADER_RE = re.compile(
    r"(?:"
    r"Major\s+category\s*[-–—:：]\s*"
    r"|方向\s*[:：]\s*"
    r"|category\s*[-–—:：]\s*"
    r")"
    r"(?P<dir>\S+)",
    re.IGNORECASE,
)
_MAJOR_SEC_RE = re.compile(r"主要|major", re.IGNORECASE)
_MINOR_SEC_RE = re.compile(r"次要|minor", re.IGNORECASE)
_BULLET_RE = re.compile(r"^\s*(?:[\*\-•・]|[0-9]+[.)、])\s*")
_SEP_RE = re.compile(r"^\s*-{3,}\s*$")


class ApplyError(Exception):
    """Hard failure — undefined / ambiguous input. Exit non-zero."""


# ---------------------------------------------------------------------------
# Catalog + hero lookup
# ---------------------------------------------------------------------------

def load_bingxue_catalog() -> dict[str, dict]:
    if not BINGXUE_CANONICAL.exists():
        raise ApplyError(f"missing catalog: {BINGXUE_CANONICAL}")
    data = yaml.safe_load(BINGXUE_CANONICAL.read_text("utf-8")) or {}
    if not isinstance(data, dict):
        raise ApplyError(f"{BINGXUE_CANONICAL} is not a mapping")
    return data


def build_option_index(catalog: dict[str, dict]) -> dict[str, list[str]]:
    """Map any resolvable label → list of JP keys (len>1 = ambiguous)."""
    idx: dict[str, list[str]] = {}

    def add(label: str, jp: str) -> None:
        label = label.strip()
        if not label:
            return
        bucket = idx.setdefault(label, [])
        if jp not in bucket:
            bucket.append(jp)

    for jp, entry in catalog.items():
        raw = entry.get("raw") or {}
        add(jp, jp)
        name = (entry.get("name") or "").strip()
        if name:
            add(name, jp)
        # raw JP name is the key already; also accept effect-less aliases
        raw_name = (raw.get("name") or "").strip()
        if raw_name:
            add(raw_name, jp)
    return idx


def strip_level_suffix(token: str) -> str:
    t = token.strip()
    t = _LEVEL_SUFFIX_RE.sub("", t).strip()
    return t


def resolve_option(
    raw_token: str,
    index: dict[str, list[str]],
    *,
    hero: str,
    direction_jp: str,
    tier: str,
    catalog: dict[str, dict],
) -> str:
    """Resolve a pasted option token to a single JP catalog key. Hard-fails."""
    token = raw_token.strip()
    if not token:
        raise ApplyError(f"{hero}/{direction_jp}/{tier}: empty option token")

    # "CHT / JP" or "CHT／JP" dual form — both sides must agree if both resolve.
    parts = re.split(r"\s*[/／]\s*", token)
    parts = [strip_level_suffix(p) for p in parts if p.strip()]
    if not parts:
        raise ApplyError(f"{hero}/{direction_jp}/{tier}: empty after strip: {raw_token!r}")

    resolved: list[str] = []
    unknown: list[str] = []
    for p in parts:
        keys = index.get(p) or index.get(strip_level_suffix(p))
        if not keys:
            # last chance: original without strip already tried
            unknown.append(p)
            continue
        if len(keys) > 1:
            raise ApplyError(
                f"{hero}/{direction_jp}/{tier}: ambiguous option {p!r} → {keys}"
            )
        resolved.append(keys[0])

    if unknown and not resolved:
        raise ApplyError(
            f"{hero}/{direction_jp}/{tier}: UNDEFINED option {raw_token!r} "
            f"(tried {unknown}). Fix the name or add it to {BINGXUE_CANONICAL}."
        )
    if unknown and resolved:
        # One side of "A / B" unknown — still fail so typos aren't silently ignored.
        raise ApplyError(
            f"{hero}/{direction_jp}/{tier}: partial resolve for {raw_token!r}; "
            f"unknown side(s) {unknown}, known → {resolved}"
        )

    uniq = list(dict.fromkeys(resolved))
    if len(uniq) > 1:
        raise ApplyError(
            f"{hero}/{direction_jp}/{tier}: dual-name mismatch in {raw_token!r} → {uniq}"
        )
    jp = uniq[0]

    entry = catalog[jp]
    raw = entry.get("raw") or {}
    opt_tier = raw.get("tier")
    opt_dir = raw.get("direction")
    if opt_tier and opt_tier != tier:
        raise ApplyError(
            f"{hero}/{direction_jp}/{tier}: {jp!r} is tier={opt_tier!r} in catalog, "
            f"not {tier!r}"
        )
    if opt_dir and opt_dir != direction_jp:
        cht = BINGXUE_JP_TO_CHT_DIR.get(opt_dir, opt_dir)
        raise ApplyError(
            f"{hero}/{direction_jp}/{tier}: {jp!r} belongs to catalog direction "
            f"{opt_dir!r} (CHT {cht}), not {direction_jp!r}"
        )
    return jp


def resolve_direction(label: str, *, locale: str = "cht") -> str:
    """Return JP storage direction key.

    CHT and JP share the glyph 機略 but mean opposite directions after the
    臨戦↔機略 localization swap. Disambiguation:

      - 臨戰 (U+6230) → always CHT → JP 機略
      - 臨戦 (U+6226) → always JP  → JP 臨戦
      - 機略          → depends on ``locale`` (default ``cht`` → JP 臨戦)
      - 武略 / 陣立   → identical in both locales
    """
    lab = label.strip()
    if not lab:
        raise ApplyError("empty direction label")

    # Character-distinct forms are unambiguous regardless of locale.
    if lab == "臨戰":  # CHT
        return "機略"
    if lab == "臨戦":  # JP
        return "臨戦"

    if locale == "cht":
        # Prefer CHT map so 機略 → 臨戦 (what the TW client shows).
        if lab in BINGXUE_CHT_TO_JP_DIR:
            return BINGXUE_CHT_TO_JP_DIR[lab]
        if lab in BINGXUE_JP_TO_CHT_DIR:
            return lab
    elif locale == "jp":
        if lab in BINGXUE_JP_TO_CHT_DIR:
            return lab
        if lab in BINGXUE_CHT_TO_JP_DIR:
            return BINGXUE_CHT_TO_JP_DIR[lab]
    else:
        raise ApplyError(f"invalid --locale {locale!r} (use cht|jp)")

    raise ApplyError(
        f"undefined direction {label!r}. "
        f"Expected JP {list(BINGXUE_JP_TO_CHT_DIR)} or CHT {list(BINGXUE_CHT_TO_JP_DIR)}"
    )


def load_hero_name_index() -> dict[str, str]:
    """Map any known hero display/JP name → preferred overrides key (CHT if known)."""
    idx: dict[str, str] = {}

    def add(label: str, key: str) -> None:
        label = (label or "").strip()
        if label:
            idx.setdefault(label, key)

    if HEROES_TRANSLATED.exists():
        tr = yaml.safe_load(HEROES_TRANSLATED.read_text("utf-8")) or {}
        if isinstance(tr, dict):
            for jp, entry in tr.items():
                if isinstance(entry, dict):
                    cht = entry.get("name") or jp
                    add(jp, cht)
                    add(cht, cht)
                elif isinstance(entry, str):
                    add(jp, entry)
                    add(entry, entry)

    if HEROES_CRAWLED.exists():
        crawled = yaml.safe_load(HEROES_CRAWLED.read_text("utf-8")) or []
        if isinstance(crawled, list):
            for h in crawled:
                if not isinstance(h, dict):
                    continue
                jp = h.get("name") or h.get("name_jp") or ""
                key = idx.get(jp, jp)
                add(jp, key)
                for a in h.get("aliases") or []:
                    add(str(a), key)
        elif isinstance(crawled, dict):
            for k, h in crawled.items():
                add(str(k), idx.get(str(k), str(k)))
                if isinstance(h, dict):
                    add(h.get("name") or "", idx.get(str(k), str(k)))

    if OVERRIDES_YAML.exists():
        ov = yaml.safe_load(OVERRIDES_YAML.read_text("utf-8")) or {}
        for key, h in (ov.get("heroes") or {}).items():
            add(key, key)
            if isinstance(h, dict):
                add(h.get("name") or "", key)
                add(h.get("_name_jp") or "", key)
                for a in h.get("aliases") or []:
                    add(str(a), key)

    return idx


def resolve_hero(name: str, name_index: dict[str, str], overrides: dict) -> str:
    name = name.strip()
    if not name:
        raise ApplyError("empty hero name")
    key = name_index.get(name)
    if key is None:
        # exact key in overrides?
        if name in (overrides.get("heroes") or {}):
            return name
        raise ApplyError(
            f"undefined hero {name!r}. Not found in overrides / crawled / translated. "
            f"Add the hero first or fix the spelling."
        )
    return key


def _normalize_bingxue(bx: dict | None) -> dict[str, dict[str, list[str]]]:
    """Canonicalize a hero bingxue block for equality / diff."""
    if not bx or not isinstance(bx, dict):
        return {}
    out: dict[str, dict[str, list[str]]] = {}
    for d, groups in bx.items():
        if not isinstance(groups, dict):
            continue
        out[str(d)] = {
            "major": [str(x) for x in (groups.get("major") or [])],
            "minor": [str(x) for x in (groups.get("minor") or [])],
        }
    return out


def load_crawled_bingxue_by_key(name_index: dict[str, str]) -> dict[str, dict]:
    """Map overrides-style hero key → crawled bingxue (JP-direction-keyed)."""
    result: dict[str, dict] = {}
    if not HEROES_CRAWLED.exists():
        return result
    crawled = yaml.safe_load(HEROES_CRAWLED.read_text("utf-8")) or []
    items: list[dict] = []
    if isinstance(crawled, list):
        items = [h for h in crawled if isinstance(h, dict)]
    elif isinstance(crawled, dict):
        items = [h for h in crawled.values() if isinstance(h, dict)]

    for h in items:
        bx = h.get("bingxue")
        if not bx:
            continue
        jp = (h.get("name") or h.get("name_jp") or "").strip()
        key = name_index.get(jp) or jp
        # Prefer first seen; overrides checked separately
        result.setdefault(key, bx)
        cht = name_index.get(jp)
        if cht:
            result.setdefault(cht, bx)
    return result


def existing_bingxue_for_hero(
    hero_key: str,
    overrides: dict,
    crawled_bx: dict[str, dict],
) -> tuple[dict[str, dict[str, list[str]]] | None, str | None]:
    """Return (normalized bingxue or None, source label).

    Prefer overrides (what we write into), then crawled pool.
    """
    ov_h = (overrides.get("heroes") or {}).get(hero_key) or {}
    if isinstance(ov_h, dict) and ov_h.get("bingxue"):
        return _normalize_bingxue(ov_h["bingxue"]), "overrides"
    crawl = crawled_bx.get(hero_key)
    if crawl:
        return _normalize_bingxue(crawl), "crawled"
    return None, None


def format_bingxue_diff(
    hero_key: str,
    existing: dict[str, dict[str, list[str]]],
    incoming: dict[str, dict[str, list[str]]],
    *,
    source: str,
) -> str:
    """Human-readable diff; empty string if equal."""
    dirs = list(JP_DIR_ORDER)
    for d in list(existing) + list(incoming):
        if d not in dirs:
            dirs.append(d)

    lines: list[str] = []
    for d in dirs:
        cht = BINGXUE_JP_TO_CHT_DIR.get(d, d)
        eg = existing.get(d) or {"major": [], "minor": []}
        ig = incoming.get(d) or {"major": [], "minor": []}
        for tier in ("major", "minor"):
            a, b = eg.get(tier) or [], ig.get(tier) or []
            if a == b:
                continue
            lines.append(f"  {d} (CHT {cht}).{tier}:")
            lines.append(f"    - existing ({source}): {a}")
            lines.append(f"    + input:              {b}")

    if not lines:
        return ""
    header = (
        f"{hero_key} already has bingxue (source: {source}) that differs from input.\n"
        f"Pass --force to overwrite.\n"
        f"Diff:"
    )
    return header + "\n" + "\n".join(lines)


def guard_existing_bingxue(
    updates: dict[str, dict],
    *,
    overrides: dict,
    crawled_bx: dict[str, dict],
    force: bool,
) -> dict[str, dict]:
    """Drop no-op updates; error on conflict unless --force.

    Returns the subset of updates that still need writing.
    """
    to_write: dict[str, dict] = {}
    conflicts: list[str] = []

    for key, bx in updates.items():
        incoming = _normalize_bingxue(bx)
        existing, source = existing_bingxue_for_hero(key, overrides, crawled_bx)
        if existing is None:
            to_write[key] = bx
            continue
        if existing == incoming:
            print(f"[skip] {key}: bingxue already identical (source: {source})")
            continue
        if force:
            print(f"[force] {key}: overwriting existing bingxue (source: {source})")
            to_write[key] = bx
            continue
        diff = format_bingxue_diff(key, existing, incoming, source=source or "?")
        conflicts.append(diff)

    if conflicts:
        raise ApplyError("\n\n".join(conflicts))
    return to_write


# ---------------------------------------------------------------------------
# Parse free-form paste
# ---------------------------------------------------------------------------

def parse_option_line(line: str) -> str | None:
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    if _SEP_RE.match(s):
        return None
    if _DIR_HEADER_RE.search(s):
        return None
    if _MAJOR_SEC_RE.fullmatch(s.rstrip("：:")) or _MINOR_SEC_RE.fullmatch(s.rstrip("：:")):
        return None
    if s.rstrip("：:") in ("主要兵學", "次要兵學", "主要兵学", "次要兵学"):
        return None
    s = _BULLET_RE.sub("", s).strip()
    if not s:
        return None
    # skip pure section headers that survived
    if _MAJOR_SEC_RE.search(s) and len(s) < 12:
        return None
    if _MINOR_SEC_RE.search(s) and len(s) < 12:
        return None
    return s


def parse_paste(
    text: str, *, locale: str = "cht"
) -> list[tuple[str, dict[str, dict[str, list[str]]]]]:
    """Return [(hero_display_name, {jp_dir: {major: [...tokens], minor: [...tokens]}})].

    Tokens are still raw paste strings; resolution happens later.
    """
    lines = text.splitlines()
    heroes: list[tuple[str, dict]] = []
    cur_hero: str | None = None
    cur_dirs: dict[str, dict[str, list[str]]] = {}
    cur_dir: str | None = None
    cur_tier: str | None = None

    def flush_hero() -> None:
        nonlocal cur_hero, cur_dirs, cur_dir, cur_tier
        if cur_hero is not None:
            heroes.append((cur_hero, cur_dirs))
        cur_hero = None
        cur_dirs = {}
        cur_dir = None
        cur_tier = None

    dir_labels = set(BINGXUE_JP_TO_CHT_DIR) | set(BINGXUE_CHT_TO_JP_DIR) | {"臨戰", "臨戦"}

    for lineno, line in enumerate(lines, 1):
        raw = line.rstrip()
        if not raw.strip():
            continue

        # Hero header (only when it looks like "Name: …兵學" or first assignment)
        hm = _HERO_HEADER_RE.match(raw)
        if hm and ("兵" in raw or cur_hero is None or _SEP_RE.match(raw)):
            name = hm.group("name").strip()
            # Avoid treating "Major category - 機略" as hero
            if not re.search(r"category|主要|次要|major|minor", name, re.I):
                # "Name: 【兵學】" or plain "Name:"
                if "兵" in raw or raw.strip().endswith((":", "：")):
                    flush_hero()
                    cur_hero = name
                    continue

        dm = _DIR_HEADER_RE.search(raw)
        if dm:
            if cur_hero is None:
                raise ApplyError(f"line {lineno}: direction before hero name: {raw!r}")
            try:
                cur_dir = resolve_direction(dm.group("dir"), locale=locale)
            except ApplyError as e:
                raise ApplyError(f"line {lineno}: {e}") from e
            cur_dirs.setdefault(cur_dir, {"major": [], "minor": []})
            cur_tier = None
            continue

        # Bare direction line (e.g. just "武略")
        stripped = raw.strip().rstrip("：:")
        if stripped in dir_labels:
            if cur_hero is None:
                raise ApplyError(f"line {lineno}: direction before hero name: {raw!r}")
            cur_dir = resolve_direction(stripped, locale=locale)
            cur_dirs.setdefault(cur_dir, {"major": [], "minor": []})
            cur_tier = None
            continue

        if _MAJOR_SEC_RE.search(raw) and (
            "主要" in raw or re.search(r"\bmajor\b", raw, re.I)
        ):
            cur_tier = "major"
            continue
        if _MINOR_SEC_RE.search(raw) and (
            "次要" in raw or re.search(r"\bminor\b", raw, re.I)
        ):
            cur_tier = "minor"
            continue

        if _SEP_RE.match(raw):
            continue

        opt = parse_option_line(raw)
        if opt is None:
            continue
        if cur_hero is None:
            raise ApplyError(f"line {lineno}: option before hero name: {raw!r}")
        if cur_dir is None:
            raise ApplyError(f"line {lineno}: option before direction: {raw!r}")
        if cur_tier is None:
            raise ApplyError(
                f"line {lineno}: option before major/minor section: {raw!r}"
            )
        cur_dirs[cur_dir][cur_tier].append(opt)

    flush_hero()
    if not heroes:
        raise ApplyError("no hero blocks parsed from input")
    return heroes


def resolve_hero_bingxue(
    hero_display: str,
    raw_dirs: dict[str, dict[str, list[str]]],
    *,
    catalog: dict[str, dict],
    index: dict[str, list[str]],
    name_index: dict[str, str],
    overrides: dict,
    allow_partial: bool,
) -> tuple[str, dict]:
    hero_key = resolve_hero(hero_display, name_index, overrides)
    out: dict[str, dict[str, list[str]]] = {}

    for jp_dir in JP_DIR_ORDER:
        if jp_dir not in raw_dirs:
            if allow_partial:
                continue
            cht = BINGXUE_JP_TO_CHT_DIR.get(jp_dir, jp_dir)
            raise ApplyError(
                f"{hero_key}: missing direction {jp_dir!r} (CHT {cht}). "
                f"Pass --allow-partial to skip."
            )
        groups = raw_dirs[jp_dir]
        resolved_groups: dict[str, list[str]] = {}
        for tier in ("major", "minor"):
            tokens = groups.get(tier) or []
            expected = EXPECTED_MAJOR if tier == "major" else EXPECTED_MINOR
            if not allow_partial and len(tokens) != expected:
                raise ApplyError(
                    f"{hero_key}/{jp_dir}/{tier}: got {len(tokens)} options, "
                    f"expected {expected}. Pass --allow-partial to accept."
                )
            resolved = [
                resolve_option(
                    t,
                    index,
                    hero=hero_key,
                    direction_jp=jp_dir,
                    tier=tier,
                    catalog=catalog,
                )
                for t in tokens
            ]
            # duplicate check
            if len(resolved) != len(set(resolved)):
                raise ApplyError(
                    f"{hero_key}/{jp_dir}/{tier}: duplicate options {resolved}"
                )
            resolved_groups[tier] = resolved
        out[jp_dir] = resolved_groups

    # leftover unknown directions already resolved via resolve_direction
    extra = set(raw_dirs) - set(out)
    if extra:
        raise ApplyError(f"{hero_key}: unexpected directions {sorted(extra)}")

    return hero_key, out


# ---------------------------------------------------------------------------
# Write overrides.yaml (surgical edit — keep rest of file intact)
# ---------------------------------------------------------------------------

def _dump_bingxue_block(bingxue: dict) -> str:
    """YAML fragment for one hero's bingxue field, indented as a hero child."""
    ordered = {d: bingxue[d] for d in JP_DIR_ORDER if d in bingxue}
    # also include any extras deterministically
    for d in bingxue:
        if d not in ordered:
            ordered[d] = bingxue[d]
    fragment = yaml.dump(
        {"bingxue": ordered},
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=120,
    )
    return "".join(
        (("    " + line) if line else line) + "\n" for line in fragment.splitlines()
    )


def _find_heroes_section_span(lines: list[str]) -> tuple[int, int]:
    start = None
    for i, line in enumerate(lines):
        if re.match(r"^heroes\s*:\s*$", line):
            start = i
            break
    if start is None:
        raise ApplyError(f"{OVERRIDES_YAML}: no top-level 'heroes:' section")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if re.match(r"^[A-Za-z_\u4e00-\u9fff]", lines[j]):
            end = j
            break
    return start, end


def _find_hero_block(lines: list[str], hero_key: str, heroes_start: int, heroes_end: int) -> tuple[int, int] | None:
    """Return [start, end) line indices of `  hero_key:` block inside heroes."""
    header = re.compile(rf"^  {re.escape(hero_key)}\s*:")
    start = None
    for i in range(heroes_start + 1, heroes_end):
        if header.match(lines[i]):
            start = i
            break
    if start is None:
        return None
    end = heroes_end
    for j in range(start + 1, heroes_end):
        if re.match(r"^  \S", lines[j]):
            end = j
            break
    return start, end


def _replace_or_insert_bingxue(block_lines: list[str], bingxue_yaml: str) -> list[str]:
    """Inside one hero block (including header line), set bingxue field."""
    # Find existing bingxue at indent 4
    bx_start = None
    for i, line in enumerate(block_lines):
        if i == 0:
            continue
        if re.match(r"^    bingxue\s*:", line):
            bx_start = i
            break
    if bx_start is not None:
        bx_end = len(block_lines)
        for j in range(bx_start + 1, len(block_lines)):
            # next key at indent 4 (hero field) or less
            if re.match(r"^    \S", block_lines[j]) or re.match(r"^  \S", block_lines[j]):
                bx_end = j
                break
        return block_lines[:bx_start] + [bingxue_yaml.rstrip("\n")] + block_lines[bx_end:]

    # Insert before _action if present, else before trailing empty, else append
    insert_at = len(block_lines)
    for i, line in enumerate(block_lines):
        if i == 0:
            continue
        if re.match(r"^    _action\s*:", line):
            insert_at = i
            break
    return block_lines[:insert_at] + [bingxue_yaml.rstrip("\n")] + block_lines[insert_at:]


def apply_to_overrides_file(
    updates: dict[str, dict],
    *,
    dry_run: bool,
) -> list[str]:
    """Apply hero_key → bingxue dict. Returns log lines."""
    if not OVERRIDES_YAML.exists():
        raise ApplyError(f"missing {OVERRIDES_YAML}")

    text = OVERRIDES_YAML.read_text("utf-8")
    lines = text.splitlines()
    heroes_start, heroes_end = _find_heroes_section_span(lines)
    logs: list[str] = []

    # Process in reverse line-order so earlier indices stay valid... actually we
    # rebuild by scanning and applying all updates in one pass.
    # Collect hero blocks to rewrite.
    new_lines = lines[: heroes_start + 1]
    i = heroes_start + 1
    remaining = dict(updates)

    while i < heroes_end:
        m = re.match(r"^  (\S.*?)\s*:", lines[i])
        if not m:
            new_lines.append(lines[i])
            i += 1
            continue
        key = m.group(1)
        block_end = heroes_end
        for j in range(i + 1, heroes_end):
            if re.match(r"^  \S", lines[j]):
                block_end = j
                break
        block = lines[i:block_end]
        if key in remaining:
            bx = remaining.pop(key)
            block = _replace_or_insert_bingxue(block, _dump_bingxue_block(bx))
            logs.append(f"updated heroes.{key}.bingxue")
        new_lines.extend(block)
        i = block_end

    # Heroes not yet in overrides — create minimal _action: modify entries
    for key, bx in remaining.items():
        entry = [
            f"  {key}:",
            _dump_bingxue_block(bx).rstrip("\n"),
            "    _action: modify",
            f"    _name_jp: {key}",
        ]
        new_lines.extend(entry)
        logs.append(f"created heroes.{key} (_action: modify) + bingxue")

    new_lines.extend(lines[heroes_end:])
    out = "\n".join(new_lines)
    if text.endswith("\n"):
        out += "\n"

    if dry_run:
        logs.append("no file written")
        return logs

    OVERRIDES_YAML.write_text(out, "utf-8")
    logs.append(f"wrote {OVERRIDES_YAML}")
    return logs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Apply hero 兵學 pools into data/overrides.yaml (hard-fail on undefined)."
    )
    p.add_argument(
        "input",
        help="Path to paste file, or '-' for stdin",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse + resolve only; do not write overrides.yaml",
    )
    p.add_argument(
        "--allow-partial",
        action="store_true",
        help="Allow missing directions or non-3/6 option counts",
    )
    p.add_argument(
        "--locale",
        choices=("cht", "jp"),
        default="cht",
        help="How to read direction labels (default: cht). "
        "Only matters for 機略, which is shared by both locales but swapped.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing bingxue when it differs from input. "
        "Identical existing data is always a no-op (no --force needed).",
    )
    args = p.parse_args(argv)

    if args.input == "-":
        text = sys.stdin.read()
    else:
        path = Path(args.input)
        if not path.exists():
            raise ApplyError(f"input not found: {path}")
        text = path.read_text("utf-8")

    catalog = load_bingxue_catalog()
    index = build_option_index(catalog)
    name_index = load_hero_name_index()
    overrides = (
        yaml.safe_load(OVERRIDES_YAML.read_text("utf-8"))
        if OVERRIDES_YAML.exists()
        else {}
    ) or {}
    crawled_bx = load_crawled_bingxue_by_key(name_index)

    parsed = parse_paste(text, locale=args.locale)
    updates: dict[str, dict] = {}
    for display, raw_dirs in parsed:
        key, bx = resolve_hero_bingxue(
            display,
            raw_dirs,
            catalog=catalog,
            index=index,
            name_index=name_index,
            overrides=overrides,
            allow_partial=args.allow_partial,
        )
        if key in updates:
            raise ApplyError(f"duplicate hero block for {key!r} in input")
        updates[key] = bx
        # preview
        print(f"[ok] {key}")
        for d in JP_DIR_ORDER:
            if d not in bx:
                continue
            cht = BINGXUE_JP_TO_CHT_DIR.get(d, d)
            print(
                f"  {d} (CHT {cht}): "
                f"major={bx[d]['major']} minor={bx[d]['minor']}"
            )

    updates = guard_existing_bingxue(
        updates,
        overrides=overrides,
        crawled_bx=crawled_bx,
        force=args.force,
    )
    if not updates:
        print("[done] nothing to write (all identical or empty)")
        return 0

    for line in apply_to_overrides_file(updates, dry_run=args.dry_run):
        print(f"[{'dry-run' if args.dry_run else 'done'}] {line}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ApplyError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)
