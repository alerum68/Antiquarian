import re
from pathlib import Path

import pytest

import Antiquarian

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_VAR_PATTERN = re.compile(r"os\.(?:getenv|environ\.get)\(\s*[\"']([A-Z][A-Z0-9_]*)[\"']")

# PROGRAM_DIR is set by the Antiquarian launcher, never user-configured: the codebase
# resolves its own install location via the __PROGRAM_DIR__ sentinel (see Antiquarian.py)
# rather than a settings key, so it is excluded from schema completeness checks.
# PROMPTS_DIR is the same shape - a sensible "Prompts" default resolved relative to
# GENEALOGY_DIR (see Paleographer/engine.py's _prompt_search_dirs), overridable by hand-
# editing .env for advanced use, but not a GUI-exposed setting.
INTERNAL_KEYS = {"PROGRAM_DIR", "PROMPTS_DIR", "AGY_CLI_BIN", "GEDCOM_OUTPUT_NAME", "APID_DB",
                 "ANCESTRY_IMAGE_BASE_ID"}

TOOL_DIRS = {
    "Archivist": BASE_DIR / "Archivist",
    "Voyageur": BASE_DIR / "Voyageur",
    "Paleographer": BASE_DIR / "Paleographer",
    "Registrar": BASE_DIR / "Registrar",
    "Gazetteer": BASE_DIR / "Gazetteer",
    "PDFix": BASE_DIR / "PDFix",
}


def _env_keys_read_by(tool_dir: Path) -> set:
    keys = set()
    for py_file in tool_dir.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        keys.update(ENV_VAR_PATTERN.findall(text))
    return keys


def _global_keys() -> set:
    keys = set()
    for fields in Antiquarian.GLOBAL_VARS.values():
        keys.update(fields.keys())
    return keys


def _schema_keys(tool_dir: Path) -> set:
    schema = Antiquarian.load_tool_schema(tool_dir)
    keys = set()
    for fields in schema.values():
        keys.update(fields.keys())
    return keys


@pytest.mark.parametrize("tool_name", sorted(TOOL_DIRS))
def test_tool_schema_covers_every_env_var_the_tool_reads(tool_name):
    tool_dir = TOOL_DIRS[tool_name]
    read_keys = _env_keys_read_by(tool_dir) - _global_keys() - INTERNAL_KEYS
    schema_keys = _schema_keys(tool_dir)

    missing = read_keys - schema_keys
    assert not missing, (
        f"{tool_name} reads env var(s) {sorted(missing)} via os.getenv/os.environ.get "
        f"that are absent from {tool_dir / 'settings_schema.yaml'} - add them."
    )
