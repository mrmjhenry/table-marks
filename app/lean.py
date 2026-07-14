"""Deterministic Lean 4 / Mathlib proof checking for the proof workspace.

The ground truth of the Lean layer: compile a snippet against the pinned
Mathlib project in lean/ and report structured diagnostics. No LLM is
involved here — the agent and the user both iterate against this checker.

The toolchain is an optional dependency: if elan/lake or the lean/ project
is missing, `checker.available` is False, the server hides all Lean
features, and nothing else changes. Setup (one-time):

    brew install elan-init          # or the official elan installer
    # the pinned toolchain + mathlib cache download on first use; the
    # lean/ project in this repo was created with
    #   lake new proofcheck math.toml   (Mathlib pinned in lakefile.toml)

Compiles are hash-cached in memory and capped by a semaphore: each run is
a separate `lake env lean --json` subprocess whose dominant cost (~30 s)
is loading Mathlib's oleans for `import Mathlib`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import time

from .store import ROOT

LEAN_DIR = ROOT / "lean"
COMPILE_TIMEOUT = 240          # seconds; import Mathlib alone costs ~30s
MAX_CONCURRENT = 2


class LeanChecker:
    def __init__(self):
        self.available = (shutil.which("lake") is not None
                          and (LEAN_DIR / "lakefile.toml").is_file()
                          and (LEAN_DIR / "lean-toolchain").is_file())
        self.toolchain = ((LEAN_DIR / "lean-toolchain").read_text().strip()
                          if self.available else None)
        self.mathlib_rev = None
        if self.available:
            for line in (LEAN_DIR / "lakefile.toml").read_text().splitlines():
                if line.strip().startswith("rev"):
                    self.mathlib_rev = line.split("=")[1].strip().strip('"')
        self._cache: dict[str, dict] = {}
        self._sem = asyncio.Semaphore(MAX_CONCURRENT)

    async def check(self, code: str, scratch_path=None) -> dict:
        """Compile `code`; return {ok, sorries, errors, duration_s}.

        `ok` means exit 0 AND no sorries — a genuinely closed proof.
        scratch_path (optional) persists the checked file (e.g. inside the
        session workspace) instead of a throwaway temp file.
        """
        if not self.available:
            return {"ok": False, "sorries": 0, "duration_s": 0.0,
                    "errors": [{"line": 0, "col": 0, "severity": "error",
                                "message": "Lean toolchain not installed"}]}
        key = hashlib.sha256(code.encode()).hexdigest()
        if key in self._cache and scratch_path is None:
            return self._cache[key]

        if scratch_path is None:
            scratch_path = LEAN_DIR / ".lake" / f"scratch_{key[:16]}.lean"
        scratch_path.parent.mkdir(parents=True, exist_ok=True)
        scratch_path.write_text(code)

        t0 = time.monotonic()
        async with self._sem:
            proc = await asyncio.create_subprocess_exec(
                "lake", "env", "lean", "--json", str(scratch_path),
                cwd=LEAN_DIR,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE)
            try:
                out, err = await asyncio.wait_for(proc.communicate(),
                                                  COMPILE_TIMEOUT)
            except TimeoutError:
                proc.kill()
                return {"ok": False, "sorries": 0,
                        "duration_s": round(time.monotonic() - t0, 1),
                        "errors": [{"line": 0, "col": 0, "severity": "error",
                                    "message": f"compile timed out after {COMPILE_TIMEOUT}s"}]}

        sorries = 0
        errors = []
        for line in out.decode(errors="replace").splitlines():
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("kind") == "hasSorry":
                sorries += 1
                continue
            if d.get("severity") in ("error", "warning"):
                errors.append({"line": d.get("pos", {}).get("line", 0),
                               "col": d.get("pos", {}).get("column", 0),
                               "severity": d["severity"],
                               "message": d.get("data", "")})
        stderr_txt = err.decode(errors="replace").strip()
        if proc.returncode != 0 and not errors:
            errors.append({"line": 0, "col": 0, "severity": "error",
                           "message": stderr_txt[:2000] or
                           f"lean exited with code {proc.returncode}"})
        result = {"ok": proc.returncode == 0 and sorries == 0
                        and not any(e["severity"] == "error" for e in errors),
                  "sorries": sorries,
                  "errors": errors,
                  "duration_s": round(time.monotonic() - t0, 1)}
        self._cache[key] = result
        return result


checker = LeanChecker()


def lean_result_word(check: dict) -> str:
    """UI/state word for a compile result: ok | has_sorries | failed."""
    if check["ok"]:
        return "ok"
    if check["sorries"] and not any(e["severity"] == "error" for e in check["errors"]):
        return "has_sorries"
    return "failed"
