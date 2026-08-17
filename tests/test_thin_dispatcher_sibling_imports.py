"""Regression test for the runpy router's sys.path quirk.

Antiquarian.py launches each tool as `python Antiquarian.py --module <Tool>.<Tool>`
via runpy.run_module, which puts the repo root (not the tool's own subfolder) on
sys.path. Each thin-dispatcher script does bare sibling imports (e.g. Archivist.py's
`import Census`) that only resolve if the dispatcher inserts its own directory into
sys.path first - see Voyageur.py's fix, later mirrored in Archivist.py and
Paleographer.py. A dispatcher missing that shim fails with a ModuleNotFoundError
before it ever reaches its own logic; this test invokes the exact same subprocess
command the GUI uses and confirms none of them do."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# (module name passed to --module, extra CLI args). Args are whatever's needed to get
# each dispatcher past its own argument parsing and into the sibling imports.
DISPATCHERS = [
    ("Voyageur.Voyageur", ["A"]),
    ("Archivist.Archivist", []),
    ("Paleographer.Paleographer", []),
]


@pytest.mark.parametrize("module_name, extra_args", DISPATCHERS)
def test_dispatcher_sibling_imports_resolve_via_runpy_router(module_name, extra_args):
    env = os.environ.copy()
    # A clean, minimal env: whatever a dispatcher does past its own imports (missing
    # URL, missing JSON file, etc.) is a separate, expected failure mode - only a
    # ModuleNotFoundError from a missing sys.path shim is this test's concern.
    for leaky_key in ("GATHER_URL", "JSON_FILE", "JSON_DIR"):
        env.pop(leaky_key, None)
    # Extract.py's "agy" engine verifies AGY CLI auth via a live subprocess/network call
    # before doing anything else - real, but slow and flaky here, and irrelevant to this
    # test (the sibling-import failure this test targets happens at module load, before
    # main() ever branches on EXTRACTION_ENGINE). "api" skips that call entirely.
    env["EXTRACTION_ENGINE"] = "api"

    result = subprocess.run(
        [sys.executable, "Antiquarian.py", "--module", module_name, *extra_args],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=60,
    )

    assert "ModuleNotFoundError" not in result.stdout + result.stderr, (
        f"{module_name} failed a sibling import when launched via the runpy router:\n"
        f"{result.stdout}\n{result.stderr}"
    )
