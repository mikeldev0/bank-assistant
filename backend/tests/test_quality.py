"""Prove the committed Python quality gates fail on deliberate regressions."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "backend/pyproject.toml"


def ruff(*arguments):
    return subprocess.run(
        [sys.executable, "-m", "ruff", *map(str, arguments)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def test_complexity_gate_accepts_simple_code_and_rejects_eleven_paths(tmp_path):
    path = tmp_path / "fixture.py"
    path.write_text("def identity(value):\n    return value\n")
    assert ruff("check", "--config", CONFIG, path).returncode == 0
    branches = "".join(f"    if value == {i}:\n        return {i}\n" for i in range(10))
    path.write_text(f"def classify(value):\n{branches}    return -1\n")
    result = ruff("check", "--config", CONFIG, path)
    assert result.returncode == 1
    assert "C901" in result.stdout and "11 > 10" in result.stdout


def test_format_gate_checks_without_mutation_then_accepts_formatted_code(tmp_path):
    path = tmp_path / "fixture.py"
    source = "value={1:2,3:4}"
    path.write_text(source)
    assert ruff("format", "--config", CONFIG, "--check", path).returncode == 1
    assert path.read_text() == source
    assert ruff("format", "--config", CONFIG, path).returncode == 0
    assert path.read_text() != source
    assert ruff("format", "--config", CONFIG, "--check", path).returncode == 0
