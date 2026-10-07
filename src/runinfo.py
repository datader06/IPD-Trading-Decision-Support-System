"""Run identity for results folders (Phase A, reproducibility).

The older runners name results/<hash>/ after `git rev-parse --short HEAD`, which fails here because the folder is not a git
repository. This helper returns the git hash when available, otherwise `nogit-<8 hex>`: a SHA-1 over the code that produces the
results (config, src, the Phase A runner, the legacy engine). The same code therefore always maps to the same folder.
"""
import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODE_GLOBS = ("config.py", "src/*.py", "scripts/run_phase_a.py", "legacy/handoff/handoff/code/*.py")


def code_hash():
    h = hashlib.sha1()
    for g in CODE_GLOBS:
        for p in sorted(ROOT.glob(g)):
            h.update(p.relative_to(ROOT).as_posix().encode())
            h.update(p.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:8]


def run_id():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True,
                                       stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "nogit-" + code_hash()
