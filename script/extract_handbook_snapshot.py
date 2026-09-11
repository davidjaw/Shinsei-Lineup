"""Extract a Sialia station handbook share snapshot (player inventory).

The Taro H5 handbook at general.sialiagamesinc.com.tw loads a public
share snapshot via:

  GET {PLATFORM}/sns/web/api/cache/get_player_share_snapshot
      ?_json={"game_id":"s11","selectors":[...],"snapshot_id":"..."}

Hero / skill numeric ids are resolved against the same-season cfg.json
on the sialiaGAMESINC CDN (newer than data/cfg/cfg_current.json, which
tracks sialiagames.com.tw). Names are emitted in zh-hant (opencc s2tw
fallback when multi_lang has no entry).

Usage:
    uv run script/extract_handbook_snapshot.py
    uv run script/extract_handbook_snapshot.py --list
    uv run script/extract_handbook_snapshot.py --url 'https://…#/handbook?snapshot_id=…'
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from paths import BUILD_DIR, HANDBOOK_SNAPSHOT_JSON

DEFAULT_SNAPSHOT_ID = "6aa2c39e3709e7256cdff5bd"
DEFAULT_GAME_ID = "s11"

PLATFORM_BASE = "https://p11386-platform.sialiagamesinc.com.tw"
SNAPSHOT_PATH = "/sns/web/api/cache/get_player_share_snapshot"
CFG_URL = (
    "https://p11386-media-cdn.sialiagamesinc.com.tw/"
    "P11386/sns/public_config/release/cfg.json"
)

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "origin": "https://general.sialiagamesinc.com.tw",
    "referer": "https://general.sialiagamesinc.com.tw/xzdyw-station-sialiagamesinc",
    "user-agent": "Mozilla/5.0",
}

SELECTORS = [
    {"selector_type": "view", "data_view_type": "asset_overview"},
    {"selector_type": "view", "data_view_type": "hero"},
    {"selector_type": "view", "data_view_type": "skill"},
]

_HEX_ID_RE = re.compile(r"^[0-9a-f]{16,}$", re.IGNORECASE)

_opencc = None


def _s2tw(text: str | None) -> str | None:
    """Deterministic zh-hans → zh-hant (Taiwan). None-safe."""
    if not text:
        return text
    global _opencc
    if _opencc is None:
        from opencc import OpenCC

        _opencc = OpenCC("s2tw")
    return _opencc.convert(text)


def parse_snapshot_id(source: str) -> str:
    """Accept a raw snapshot_id or a handbook URL (hash or query)."""
    source = source.strip()
    if _HEX_ID_RE.fullmatch(source):
        return source
    parsed = urlparse(source)
    candidates = []
    if parsed.fragment:
        frag = parsed.fragment
        candidates.append(frag.split("?", 1)[1] if "?" in frag else frag)
    if parsed.query:
        candidates.append(parsed.query)
    for blob in candidates:
        qs = parse_qs(blob)
        if qs.get("snapshot_id"):
            return qs["snapshot_id"][0]
    raise ValueError(f"cannot parse snapshot_id from {source!r}")


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    os.replace(tmp, path)


class CfgIndex:
    def __init__(self, cfg: dict):
        self.version = cfg.get("version")
        self.heroes = {int(h["id"]): h for h in cfg.get("hero") or [] if h.get("id") is not None}
        self.skills = {int(s["id"]): s for s in cfg.get("skill") or [] if s.get("id") is not None}
        ml = cfg.get("multi_lang") or []
        self.ml_by_hans = {e["zh-hans"]: e for e in ml if e.get("zh-hans")}
        self.ml_by_id = {e["id"]: e for e in ml if e.get("id")}

    def names_for(self, hans: str | None) -> tuple[str | None, str | None, str | None]:
        """Return (zh-hant, ja, zh-hans)."""
        if not hans:
            return None, None, None
        ml = self.ml_by_hans.get(hans) or self.ml_by_id.get(hans)
        ja = (ml or {}).get("ja")
        hant = (ml or {}).get("zh-hant") or _s2tw(hans)
        return hant, ja, hans


def fetch_snapshot(client: httpx.Client, snapshot_id: str, game_id: str) -> dict:
    payload = {
        "game_id": game_id,
        "selectors": SELECTORS,
        "snapshot_id": snapshot_id,
    }
    resp = client.get(
        PLATFORM_BASE + SNAPSHOT_PATH,
        params={"_json": json.dumps(payload, separators=(",", ":"))},
        headers=HEADERS,
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise RuntimeError(
            f"snapshot API code={body.get('code')} message={body.get('message')!r}"
        )
    return body


def fetch_cfg(client: httpx.Client, url: str) -> dict:
    resp = client.get(url, headers={**HEADERS, "accept": "*/*"})
    resp.raise_for_status()
    return resp.json()


def load_cfg_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _blocks_by_view(body: dict) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for block in body.get("data") or []:
        view = (block.get("selector") or {}).get("data_view_type")
        if view:
            out[view] = block
    return out


def _as_int(value) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def resolve_skill_id(cfg: CfgIndex, skill_id: int | None) -> dict:
    if skill_id is None:
        return {"id": None}
    entry = cfg.skills.get(skill_id)
    if not entry:
        return {"id": skill_id, "unmatched": True}
    hant, ja, hans = cfg.names_for(entry.get("name"))
    arm = entry.get("arm_limit") or []
    return {
        "id": skill_id,
        "name": hant,
        "name_ja": ja,
        "name_hans": hans,
        "kind": _s2tw(entry.get("skill_kind")),
        "grade": entry.get("grade"),
        "arm_limit": [_s2tw(a) for a in arm],
    }


def resolve_hero(cfg: CfgIndex, raw: dict) -> dict:
    hid = _as_int(raw.get("type") or raw.get("id"))
    extra = raw.get("extra") or {}
    entry = cfg.heroes.get(hid) if hid is not None else None
    if not entry:
        resolved = {"id": hid, "unmatched": True}
    else:
        hant, ja, hans = cfg.names_for(entry.get("name"))
        born_hant, born_ja, born_hans = cfg.names_for(entry.get("born_skill"))
        resolved = {
            "id": hid,
            "name": hant,
            "name_ja": ja,
            "name_hans": hans,
            "star": entry.get("star"),
            "cost": entry.get("cost"),
            "camp": _s2tw(entry.get("camp")),
            "family": _s2tw(entry.get("family")),
            "born_skill": born_hant,
            "born_skill_ja": born_ja,
            "born_skill_hans": born_hans,
        }
    slots = []
    for slot in raw.get("skills") or []:
        if not slot:
            slots.append(None)
            continue
        sid = _as_int(slot.get("type") or slot.get("id"))
        item = resolve_skill_id(cfg, sid)
        item["level"] = slot.get("level")
        slots.append(item)
    resolved["level"] = raw.get("level")
    resolved["awaken"] = extra.get("awaken")
    resolved["skin"] = extra.get("skin")
    resolved["talent"] = extra.get("talent")
    resolved["skills"] = slots
    return resolved


def extract(body: dict, cfg: CfgIndex, snapshot_id: str, game_id: str) -> dict:
    blocks = _blocks_by_view(body)
    overview_block = blocks.get("asset_overview") or {}
    hero_block = blocks.get("hero") or {}
    skill_block = blocks.get("skill") or {}

    player_ids = {
        b.get("player_id")
        for b in (overview_block, hero_block, skill_block)
        if b.get("player_id")
    }
    player_id = next(iter(player_ids), None)

    overview = (overview_block.get("player_data") or {})
    raw_heroes = (hero_block.get("player_data") or {}).get("heros") or []
    raw_skills = (skill_block.get("player_data") or {}).get("skills") or []

    heroes = [resolve_hero(cfg, h) for h in raw_heroes]
    skills = []
    for s in raw_skills:
        sid = _as_int(s.get("type") or s.get("id"))
        skills.append(resolve_skill_id(cfg, sid))

    unmatched_heroes = [h["id"] for h in heroes if h.get("unmatched")]
    unmatched_skills = [s["id"] for s in skills if s.get("unmatched")]
    unmatched_equipped = sorted({
        slot["id"]
        for h in heroes
        for slot in (h.get("skills") or [])
        if slot and slot.get("unmatched") and slot.get("id") is not None
    })

    inv_h = [h.get("name_ja") or h.get("name") for h in heroes if not h.get("unmatched")]
    inv_s = [s.get("name_ja") or s.get("name") for s in skills if not s.get("unmatched")]

    return {
        "snapshot_id": snapshot_id,
        "game_id": game_id,
        "player_id": player_id,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cfg_version": cfg.version,
        "player_ids": sorted(player_ids),
        "overview": {
            "hero_count": overview.get("hero_count", len(raw_heroes)),
            "skill_count": overview.get("skill_count", len(raw_skills)),
        },
        "heroes": heroes,
        "skills": skills,
        "unmatched": {
            "heroes": unmatched_heroes,
            "skills": unmatched_skills,
            "equipped_skills": unmatched_equipped,
        },
        "inventory": {"inv_h": inv_h, "inv_s": inv_s},
    }


def _print_list(label: str, rows: list[dict]) -> None:
    print(f"\n{label} ({len(rows)})")
    for row in rows:
        if row.get("unmatched"):
            print(f"  [{row.get('id')}]  (unmatched)")
            continue
        extra = []
        if row.get("star") is not None:
            extra.append(f"{row['star']}★")
        if row.get("cost") is not None:
            extra.append(f"cost {row['cost']}")
        if row.get("camp"):
            extra.append(row["camp"])
        if row.get("kind"):
            extra.append(row["kind"])
        if row.get("grade") is not None:
            extra.append(f"grade {row['grade']}")
        suffix = f"  ({', '.join(str(x) for x in extra)})" if extra else ""
        print(f"  [{row.get('id')}] {row.get('name') or row.get('name_hans')}{suffix}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source",
        nargs="?",
        default=DEFAULT_SNAPSHOT_ID,
        help="Handbook URL or snapshot_id (default: %(default)s)",
    )
    parser.add_argument("--url", help="Alias for source when passing a handbook URL")
    parser.add_argument("--game-id", default=DEFAULT_GAME_ID, help="SNS game_id (default: s11)")
    parser.add_argument(
        "--cfg",
        type=Path,
        help="Local cfg.json (skip CDN fetch). Default: fetch sialiaGAMESINC cfg.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=HANDBOOK_SNAPSHOT_JSON,
        help=f"Output JSON (default: {HANDBOOK_SNAPSHOT_JSON})",
    )
    parser.add_argument("--list", action="store_true", help="Print resolved hero/skill names")
    args = parser.parse_args()

    try:
        snapshot_id = parse_snapshot_id(args.url or args.source)
    except ValueError as e:
        print(f"[extract_handbook] {e}", file=sys.stderr)
        return 2

    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    if args.cfg and not args.cfg.exists():
        print(f"[extract_handbook] cfg file not found: {args.cfg}", file=sys.stderr)
        return 2

    try:
        with httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            body = fetch_snapshot(client, snapshot_id, args.game_id)
            cfg_data = load_cfg_file(args.cfg) if args.cfg else fetch_cfg(client, CFG_URL)
    except httpx.HTTPError as e:
        print(f"[extract_handbook] network error: {e}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"[extract_handbook] response was not valid JSON: {e}", file=sys.stderr)
        return 2
    except RuntimeError as e:
        print(f"[extract_handbook] {e}", file=sys.stderr)
        return 2


    result = extract(body, CfgIndex(cfg_data), snapshot_id, args.game_id)
    _atomic_write_json(args.out, result)

    ov = result["overview"]
    um = result["unmatched"]
    print(
        f"[extract_handbook] player={result['player_id']} "
        f"heroes={len(result['heroes'])}/{ov['hero_count']} "
        f"skills={len(result['skills'])}/{ov['skill_count']} "
        f"unmatched_h={len(um['heroes'])} unmatched_s={len(um['skills'])} "
        f"cfg={result['cfg_version']}"
    )
    print(f"[extract_handbook] wrote {args.out}")

    if um["heroes"] or um["skills"] or um["equipped_skills"]:
        print(
            f"[extract_handbook] unmatched ids heroes={um['heroes']} "
            f"skills={um['skills']} equipped={um['equipped_skills']}",
            file=sys.stderr,
        )

    if args.list:
        _print_list("Heroes", result["heroes"])
        _print_list("Skills", result["skills"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
