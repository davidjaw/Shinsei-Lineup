"""
Shared test harness for running prompts through Claude CLI.

Used by llm_translate.py and override.py for --claude-test mode.
No files are modified during testing.
"""

import subprocess


def call_claude(prompt: str, model: str = "haiku") -> str:
    """Call Claude CLI in non-interactive mode via stdin."""
    result = subprocess.run(
        ["claude", "-p", "--model", model],
        input=prompt, capture_output=True, text=True, timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI failed (rc={result.returncode}): {result.stderr[:300]}")
    return result.stdout.strip()
