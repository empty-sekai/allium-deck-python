from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "wheels.yml"


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_only_push_tags_can_publish() -> None:
    workflow = workflow_text()
    assert "if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')" in workflow


def test_all_actions_are_pinned_to_full_commit_sha() -> None:
    uses = re.findall(r"^\s*- uses: (\S+)", workflow_text(), flags=re.MULTILINE)
    assert uses
    for action in uses:
        assert re.search(r"@[0-9a-f]{40}$", action), action


def test_release_toolchain_and_pypi_retry_are_fixed() -> None:
    workflow = workflow_text()
    assert "toolchain: 1.94.1" in workflow
    assert "skip-existing: true" in workflow


def test_python_abi_floor_remains_310() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    cargo = (ROOT / "Cargo.toml").read_text(encoding="utf-8")
    assert 'requires-python = ">=3.10,<4"' in pyproject
    assert 'features = ["abi3-py310"]' in cargo


def test_native_binding_pins_the_reviewed_deck_004_release_commit() -> None:
    cargo = (ROOT / "Cargo.toml").read_text(encoding="utf-8")
    assert 'rev = "2cf7e77736c1d545f0858ec96711feae9e6fcbed"' in cargo
