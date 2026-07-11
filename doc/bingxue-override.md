# Hero 兵學 overrides

Apply per-hero 兵學 option pools into `data/overrides.yaml`.

## Script

```bash
uv run script/apply_bingxue_override.py path/to/paste.txt
uv run script/apply_bingxue_override.py --dry-run paste.txt
uv run script/apply_bingxue_override.py --force paste.txt   # overwrite differing existing
```

## Agent workflow

1. User pastes messy OCR/AI text (any layout).
2. Agent normalizes to the paste shape below (resolve aliases, e.g. 磨練→練磨).
3. Run the script. On `ERROR`, stop and ask the user (do not invent names).

## Paste shape (what the script accepts)

```text
武將名: 【兵學】

Major category - 機略          # CHT or JP direction label
主要兵學：
* CHT名 / JP名                 # 3 majors
次要兵學：
* CHT名I / JP名                # 6 minors (level suffix stripped)

---
Major category - 臨戰
...
```

Four directions required (unless `--allow-partial`). Names must exist in `data/bingxue.yaml`.

## Direction keys

| UI (CHT) | stored in override (JP) |
|----------|-------------------------|
| 武略 | 武略 |
| 陣立 | 陣立 |
| 機略 | 臨戦 |
| 臨戰 | 機略 |

Build re-keys JP→CHT for the frontend (`BINGXUE_JP_TO_CHT_DIR` in `script/paths.py`).

## Existing data guard

| State | Result |
|-------|--------|
| No existing bingxue | write |
| Existing **identical** | skip (exit 0) |
| Existing **differs** | `ERROR` + diff; needs `--force` |

Sources checked: `overrides` first, then crawled hero bingxue.

## Data shape written

```yaml
heroes:
  武將名:
    bingxue:
      陣立:
        major: [JP, JP, JP]
        minor: [JP, JP, JP, JP, JP, JP]
      武略: { major: [...], minor: [...] }
      臨戦: { major: [...], minor: [...] }
      機略: { major: [...], minor: [...] }
```

Option **definitions** live in `data/bingxue.yaml` (not this script). Player-selected loadout is runtime only.
