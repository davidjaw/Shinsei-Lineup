"""LLM backends: OMP (default) and OpenRouter.

Oneshot (`complete`) is for batch translate. Agent (`run_omp_agent`) is for
override.py: the model writes output.yaml and loops on check_llm_entry.py.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

from llm_core import DEFAULT_MODEL, call_llm, parse_llm_output
from paths import OMP_TASKS_DIR

DEFAULT_BACKEND = "omp"
OMP_DEFAULT_MODEL = "@smol"

_KIND_RE = re.compile(r"^kind:\s*(\w+)\s*$", re.MULTILINE)


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def omp_bin() -> str:
    env = os.environ.get("OMP_BIN")
    path = env if env else shutil.which("omp")
    if not path or not Path(path).is_file():
        raise RuntimeError("omp not found on PATH; install OMP or pass --backend openrouter")
    return path


def resolve_backend(backend: str | None, model: str | None) -> str:
    """If --backend was omitted and --model looks like vendor/name, use openrouter."""
    if backend:
        return backend
    if model and "/" in model and not model.startswith("@"):
        return "openrouter"
    return DEFAULT_BACKEND


def resolve_model(backend: str, model: str | None) -> str:
    if model:
        return model
    if backend == "omp":
        return OMP_DEFAULT_MODEL
    return DEFAULT_MODEL


def prepare_task_dir(kind: str, raw_input: str, task_body: str) -> Path:
    task_dir = OMP_TASKS_DIR / uuid4().hex
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "input.txt").write_text(raw_input, "utf-8")
    (task_dir / "TASK.md").write_text(f"kind: {kind}\n\n{task_body}", "utf-8")
    out_path = (task_dir / "output.yaml").resolve()
    check_cmd = shlex.join([
        "uv", "run", "script/check_llm_entry.py",
        "--kind", kind, "--file", str(out_path), "--write",
    ])
    (task_dir / "check.sh").write_text(f"#!/bin/sh\n{check_cmd}\n", "utf-8")
    return task_dir


def _stderr_tail(text: str | None, n: int = 2000) -> str:
    if not text:
        return ""
    return text[-n:]


def _omp_argv(
    *,
    model: str,
    timeout: int,
    oneshot: bool,
    system_prompt_path: Path | None,
    append_prompt_path: Path | None,
) -> list[str]:
    root = str(repo_root())
    argv = [
        omp_bin(),
        "-p",
        "--model", model,
        "--yolo",
        "--no-session",
        "--no-title",
        "--no-lsp",
        "--no-pty",
        "--max-time", f"{timeout}s",
        "--cwd", root,
    ]
    if oneshot:
        argv.extend(["--no-tools"])
        if system_prompt_path is not None:
            argv.extend(["--system-prompt", str(system_prompt_path)])
    else:
        argv.extend([
            "--tools", "read,write,edit,bash",
            "--skills", "override-format",
        ])
        if append_prompt_path is not None:
            argv.extend(["--append-system-prompt", str(append_prompt_path)])
    return argv


def _run_omp(
    argv: list[str],
    *,
    stdin: str | None,
    capture_stdout: bool,
    timeout: int,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv,
        input=stdin,
        stdout=subprocess.PIPE if capture_stdout else None,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(repo_root()),
        timeout=timeout + 30,
    )


def _retry_model(model: str) -> str | None:
    if model.startswith("@") and len(model) > 1:
        return model[1:]
    return None


def _raise_omp(
    proc: subprocess.CompletedProcess,
    extra: str = "",
    task_dir: Path | None = None,
) -> None:
    tail = _stderr_tail(proc.stderr)
    msg = f"omp exited {proc.returncode}"
    if extra:
        msg = f"{msg}; {extra}"
    if task_dir is not None:
        msg = f"{msg}; task_dir: {task_dir}"
    if tail:
        msg = f"{msg}\n{tail}"
    raise RuntimeError(msg)


def complete(
    prompt: str,
    *,
    system_prompt: str | None = None,
    model: str,
    backend: str,
    timeout: int = 180,
    provider: str | None = None,
    max_tokens: int = 16000,
) -> str:
    if backend == "openrouter":
        return call_llm(
            prompt,
            system_prompt=system_prompt,
            model=model,
            timeout=timeout,
            max_tokens=max_tokens,
            provider=provider,
        )
    if backend != "omp":
        raise ValueError(f"unknown backend {backend!r}")
    root = repo_root()
    build = root / ".build"
    build.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="omp-sys-", suffix=".md", dir=str(build))
    sys_path = Path(tmp_name)
    try:
        os.write(fd, (system_prompt or "").encode("utf-8"))
        os.close(fd)
        sys_path = sys_path.resolve()
        models_to_try = [model]
        alt = _retry_model(model)
        if alt:
            models_to_try.append(alt)
        last: subprocess.CompletedProcess | None = None
        for m in models_to_try:
            argv = _omp_argv(
                model=m,
                timeout=timeout,
                oneshot=True,
                system_prompt_path=sys_path,
                append_prompt_path=None,
            )
            last = _run_omp(argv, stdin=prompt, capture_stdout=True, timeout=timeout)
            if last.returncode == 0:
                return (last.stdout or "").strip()
            if m is models_to_try[-1]:
                _raise_omp(last)
        assert last is not None
        _raise_omp(last)
    finally:
        try:
            sys_path.unlink(missing_ok=True)
        except OSError:
            pass
    raise RuntimeError("omp oneshot failed")  # unreachable


def _load_parsed_output(task_dir: Path) -> dict | None:
    out_path = task_dir / "output.yaml"
    if not out_path.is_file():
        return None
    return parse_llm_output(out_path.read_text("utf-8"))


def _checked_output(kind: str, parsed: dict, task_dir: Path, *, keep: bool) -> dict:
    from check_llm_entry import check

    out_path = task_dir / "output.yaml"
    try:
        errors, _, _ = check(kind, parsed)
    except Exception as e:
        print(f"[warn] checker failed on {out_path}: {e}")
        print(f"  task_dir: {task_dir}")
        return parsed
    if errors:
        print(f"[warn] checker rejected {out_path}: {'; '.join(errors)}")
        print(f"  task_dir: {task_dir}")
        return parsed
    if not keep:
        shutil.rmtree(task_dir, ignore_errors=True)
    return parsed


def run_omp_agent(*, task_dir: Path, model: str, timeout: int = 600) -> dict:
    task_md_path = task_dir / "TASK.md"
    if not task_md_path.is_file():
        raise RuntimeError(f"missing {task_md_path}")

    task_text = task_md_path.read_text("utf-8")
    kind_m = _KIND_RE.search(task_text)
    if not kind_m:
        raise RuntimeError("TASK.md missing kind:")
    kind = kind_m.group(1)

    worker = (repo_root() / "script" / "prompts" / "omp_worker.md").resolve()
    append_path = worker if worker.is_file() else None

    task_abs = str(task_dir.resolve())
    out_abs = str((task_dir / "output.yaml").resolve())
    check_sh = str((task_dir / "check.sh").resolve())
    user_msg = (
        "Read skill://override-format (project skill .omp/skills/override-format/) "
        "and follow it. "
        f"Task directory: {task_abs}. Only write files inside that directory. "
        f"Process cwd is the repo root. Write output.yaml to {out_abs}. "
        f"Check with: uv run script/check_llm_entry.py --kind {kind} --file {out_abs} --write "
        f"(or bash {check_sh})."
    )

    models_to_try = [model]
    alt = _retry_model(model)
    if alt:
        models_to_try.append(alt)

    last: subprocess.CompletedProcess | None = None
    for m in models_to_try:
        argv = _omp_argv(
            model=m,
            timeout=timeout,
            oneshot=False,
            system_prompt_path=None,
            append_prompt_path=append_path,
        )
        argv.extend(["--", user_msg])
        try:
            last = _run_omp(argv, stdin=None, capture_stdout=False, timeout=timeout)
        except subprocess.TimeoutExpired:
            parsed = _load_parsed_output(task_dir)
            if parsed is not None:
                print(f"[warn] omp timed out; using {task_dir / 'output.yaml'}")
                print(f"  task_dir: {task_dir}")
                return _checked_output(kind, parsed, task_dir, keep=True)
            raise RuntimeError(
                f"omp timed out after {timeout + 30} seconds; task_dir: {task_dir}"
            )
        if last.returncode == 0:
            break
        if m is models_to_try[-1]:
            parsed = _load_parsed_output(task_dir)
            if parsed is not None:
                print(f"[warn] omp exited {last.returncode}; using {task_dir / 'output.yaml'}")
                print(f"  task_dir: {task_dir}")
                return _checked_output(kind, parsed, task_dir, keep=True)
            _raise_omp(last, task_dir=task_dir)
    assert last is not None
    if last.returncode != 0:
        _raise_omp(last, task_dir=task_dir)

    parsed = _load_parsed_output(task_dir)
    if parsed is None:
        _raise_omp(last, extra=f"missing or unparseable {task_dir / 'output.yaml'}", task_dir=task_dir)
    return _checked_output(kind, parsed, task_dir, keep=False)
