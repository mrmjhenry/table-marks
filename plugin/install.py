#!/usr/bin/env python3
"""Install (or update) the math-prover Claude Code plugin.

Renders plugin/.mcp.json from the template with this repo's absolute path,
then copies the plugin into ~/.claude/skills/math-prover/, where Claude
Code auto-discovers it as `math-prover@skills-dir` in every project.

Rerun after editing anything under plugin/ (Claude Code sessions pick the
new copy up on restart). Stdlib only; run with any python3.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent
REPO = PLUGIN.parent
DEST = Path.home() / ".claude" / "skills" / "math-prover"
EXCLUDE = {".mcp.json.template", "install.py", "__pycache__"}


def main() -> int:
    template = (PLUGIN / ".mcp.json.template").read_text()
    rendered = template.replace("{{REPO_ROOT}}", str(REPO))
    (PLUGIN / ".mcp.json").write_text(rendered)
    print(f"rendered plugin/.mcp.json (repo root: {REPO})")

    if DEST.exists():
        shutil.rmtree(DEST)
    DEST.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(PLUGIN, DEST,
                    ignore=shutil.ignore_patterns(*EXCLUDE))
    n = sum(1 for _ in DEST.rglob("*") if _.is_file())
    print(f"installed to {DEST} ({n} files)")
    print("restart Claude Code sessions to pick up changes "
          "(loads as math-prover@skills-dir)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
