---
name: override-format
description: Format TW/JP hero and skill paste into nested YAML (vars/text/battle or heroes) and iterate with script/check_llm_entry.py until ok.
---

1. Read `TASK.md` and `input.txt` in the task directory named in the user message.
2. Write a first candidate to `output.yaml` in that same directory. Shape is specified in `TASK.md` (`kind: skill|hero|mixed|patch`).
3. Process cwd is the repo root, so `--file output.yaml` would hit the wrong path. Check with the absolute path from the user message, or run `bash <task-dir>/check.sh`:
   `uv run script/check_llm_entry.py --kind <kind> --file <task-dir>/output.yaml --write`
4. If JSON `ok` is false, edit `output.yaml` from `errors` and repeat. Cap 5 check rounds.
5. Do not create or edit any file outside the task directory.
6. When `ok` is true, stop.
