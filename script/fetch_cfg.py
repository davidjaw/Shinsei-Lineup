"""
Fetch the official Sialia Games cfg.json (CHT/CN server config) and maintain
a versioned archive.

Output:
  data/cfg/cfg_current.json   — latest fetched config (uncompressed JSON)
  data/.cfg_history/cfg-<version>.json.gz
                              — prior versions, gzipped; last 10 retained

If the fetched bytes equal the current file (byte-identical), skip both the
archive step and the re-write. Pass --force to ignore identity and proceed.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from pathlib import Path

import httpx

from paths import (
    CFG_CURRENT_JSON,
    CFG_DIR,
    CFG_HISTORY_DIR,
)

CFG_URL = (
    "https://p11386-media-cdn.sialiagamesinc.com.tw/"
    "P11386/sns/public_config/release/cfg.json"
)
HEADERS = {
    "accept": "*/*",
    "referer": "https://general.sialiagamesinc.com.tw/",
}

HISTORY_KEEP = 10


def _read_version(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("version")
    except (OSError, json.JSONDecodeError):
        return None


def _archive_current(current: Path, history_dir: Path) -> Path | None:
    """Move current config to history as gzipped file. Returns archive path."""
    if not current.exists():
        return None
    version = _read_version(current) or "unknown"
    history_dir.mkdir(parents=True, exist_ok=True)
    archive_path = history_dir / f"cfg-{version}.json.gz"
    # Avoid clobber: if same version already archived, suffix with index.
    if archive_path.exists():
        i = 1
        while (history_dir / f"cfg-{version}.{i}.json.gz").exists():
            i += 1
        archive_path = history_dir / f"cfg-{version}.{i}.json.gz"
    with current.open("rb") as src, gzip.open(archive_path, "wb") as dst:
        dst.write(src.read())
    return archive_path


def _prune_history(history_dir: Path, keep: int) -> list[Path]:
    """Keep only the most recently modified `keep` archives."""
    if not history_dir.exists():
        return []
    archives = sorted(
        history_dir.glob("cfg-*.json.gz"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    pruned = []
    for old in archives[keep:]:
        old.unlink()
        pruned.append(old)
    return pruned


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as f:
        f.write(content)
    os.replace(tmp, path)


def fetch(force: bool = False) -> dict:
    """Fetch cfg.json. Returns a status dict with keys:
    {fetched: bool, swapped: bool, version: str, archived: Path|None,
     pruned: list[Path], bytes: int}.
    """
    with httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        resp = client.get(CFG_URL, headers=HEADERS)
        resp.raise_for_status()
        new_bytes = resp.content  # httpx auto-decompresses gzip
        # Validate JSON before any disk mutation.
        new_data = json.loads(new_bytes)

    new_version = new_data.get("version", "unknown")
    current_bytes = CFG_CURRENT_JSON.read_bytes() if CFG_CURRENT_JSON.exists() else None
    identical = current_bytes is not None and current_bytes == new_bytes

    if identical and not force:
        return {
            "fetched": True,
            "swapped": False,
            "version": new_version,
            "archived": None,
            "pruned": [],
            "bytes": len(new_bytes),
        }

    archived = _archive_current(CFG_CURRENT_JSON, CFG_HISTORY_DIR)
    _atomic_write(CFG_CURRENT_JSON, new_bytes)
    pruned = _prune_history(CFG_HISTORY_DIR, HISTORY_KEEP)

    return {
        "fetched": True,
        "swapped": True,
        "version": new_version,
        "archived": archived,
        "pruned": pruned,
        "bytes": len(new_bytes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-archive and re-write even if fetched bytes match current.",
    )
    args = parser.parse_args()

    CFG_DIR.mkdir(parents=True, exist_ok=True)

    try:
        status = fetch(force=args.force)
    except httpx.HTTPError as e:
        print(f"[fetch_cfg] network error: {e}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as e:
        print(f"[fetch_cfg] response was not valid JSON: {e}", file=sys.stderr)
        return 2

    if status["swapped"]:
        archived = status["archived"]
        archived_str = str(archived) if archived else "(no prior version)"
        print(
            f"[fetch_cfg] updated → version={status['version']} "
            f"size={status['bytes']:,}B archived={archived_str}"
        )
        if status["pruned"]:
            print(f"[fetch_cfg] pruned {len(status['pruned'])} old archive(s)")
    else:
        print(f"[fetch_cfg] no change (version={status['version']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
