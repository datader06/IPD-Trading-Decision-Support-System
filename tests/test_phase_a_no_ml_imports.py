"""Phase A must not depend on the ML package (src/ml). This guard parses every Phase A source file and fails if one imports `ml`.

Phase A = everything except src/ml/, scripts/run_phase_b_*.py and tests/test_phase_b_*.py (and this file's own name is irrelevant: it
only reads files). The shared replay helpers live in src/replay_context.py so both phases can use them.
Run: python -m pytest tests/test_phase_a_no_ml_imports.py -q
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def phase_a_files():
    files = [ROOT / "config.py", ROOT / "kite_login.py"]
    files += sorted((ROOT / "src").glob("*.py"))  # non-recursive: src/ml is excluded
    files += sorted(p for p in (ROOT / "scripts").glob("*.py") if not p.name.startswith("run_phase_b_"))
    files += sorted(p for p in (ROOT / "tests").glob("*.py") if not p.name.startswith("test_phase_b_"))
    files += sorted((ROOT / "legacy" / "handoff" / "handoff" / "code").rglob("*.py"))
    return [p for p in files if p.exists()]


def ml_imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            bad += [a.name for a in node.names if a.name == "ml" or a.name.startswith("ml.")]
        elif isinstance(node, ast.ImportFrom) and node.module and (node.module == "ml" or node.module.startswith("ml.")):
            bad.append(node.module)
    return bad


def test_phase_a_code_never_imports_the_ml_package():
    files = phase_a_files()
    assert len(files) > 40  # the guard is really looking at the code base
    offenders = {str(p.relative_to(ROOT)): ml_imports(p) for p in files if ml_imports(p)}
    assert offenders == {}, offenders


def test_the_guard_detects_an_ml_import(tmp_path):
    for src in ("import ml", "import ml.labels", "from ml import labels", "from ml.labels import ReplayContext"):
        f = tmp_path / "x.py"
        f.write_text(src + "\n", encoding="utf-8")
        assert ml_imports(f), src
    f.write_text("import mlx\nfrom mlflow import x\nimport replay_context\n", encoding="utf-8")
    assert ml_imports(f) == []


def test_common_replay_module_is_self_contained():
    text = (ROOT / "src" / "replay_context.py").read_text(encoding="utf-8")
    assert ml_imports(ROOT / "src" / "replay_context.py") == []
    for name in ("class ReplayContext", "def replay_row", "def check_row"):
        assert name in text
