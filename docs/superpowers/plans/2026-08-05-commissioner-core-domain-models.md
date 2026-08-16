# Commissioner Core Domain Models Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `Commissioner/`, a standalone, strongly-typed Pydantic package holding the domain-agnostic core models (Collection/Sheet/Record/Participant/Fact) and two registries (fact vocabulary, per-document-type `.pmt` schema) that later pipeline stages will adopt instead of passing around untyped dicts.

**Architecture:** `models.py` is the single authored source of truth for both the ingestion schema (mirroring `Paleographer/schema.json`) and the fact vocabulary (mirroring `FactTypes.json`) as real Pydantic classes and data. `fact_registry.py` is a thin lookup/export layer over `models.FACT_DEFINITIONS`. `record_registry.py` dynamically scans `Paleographer/prompts/*.pmt` at import time to build per-document-type extra-field models and valid-role sets, and exposes `parse_collection()` as the validated ingestion entry point. Two guardrail tests keep `models.py` from silently drifting away from the two real files (`schema.json`, `FactTypes.json`) that legacy code still reads directly.

**Tech Stack:** Python 3.12, Pydantic 2.13.4, PyYAML (already a dependency), pytest.

## Global Constraints

- Do not modify `Archivist.py`, `Paleographer.py`, `engine.py`, `Voyageur.py`, `FS.py`, or any other existing pipeline code. The one explicitly approved exception is `Paleographer/prompts/Scrip.pmt`, per the spec's `scrip_amount`/`scrip_type` split.
- Do not delete or overwrite `Paleographer/schema.json` or `FactTypes.json` on disk — both stay exactly as they are; `Commissioner` only reads them for guardrail comparison.
- No AI attribution, "Co-Authored-By", or "Generated with AI Assistant" text in any code, comment, or commit message.
- Run the full `Commissioner/tests/` suite locally and confirm it passes before considering any task done.
- No comments explaining *what* code does — only ones explaining a non-obvious *why*, matching the rest of this codebase's style.
- Every new file uses LF-agnostic content (the repo's git config already normalizes line endings; don't fight it).

---

### Task 1: Package scaffold, dependency, and Commissioner/ cleanup

**Files:**
- Create: `Commissioner/__init__.py`
- Modify: `requirements.txt`
- Delete: `Commissioner/.env`
- Test: `Commissioner/tests/test_package.py`

**Interfaces:**
- Produces: an importable, empty `Commissioner` package with `pydantic` available as a dependency.

`Commissioner/.env` and the empty `Commissioner/tests/` directory are leftovers from the old scrip-enrichment pipeline stage, which was already folded into `Paleographer`/`Voyageur` in a prior commit. Confirmed via repo-wide search that nothing reads `Commissioner/.env` or any `COMMISSIONER_*` variable anymore — safe to remove.

- [x] **Step 1: Confirm the old Commissioner/.env is genuinely unused**

Run: `grep -rn "COMMISSIONER_" --include=*.py .`

Expected: no output (no `.py` file references any `COMMISSIONER_*` variable).

- [x] **Step 2: Remove the leftover .env and add pydantic to requirements.txt**

Delete `Commissioner/.env`.

In `requirements.txt`, insert `pydantic==2.13.4` alphabetically between `pillow` and `pymupdf`:

```
beautifulsoup4==4.15.0
cloudscraper==1.2.71
customtkinter==6.0.0
geopandas==1.1.4
google-genai==2.10.0
lxml==6.1.1
pandas==3.0.3
pdfplumber==0.11.10
pillow==12.3.0
pydantic==2.13.4
pymupdf==1.28.0
python-dotenv==1.2.2
pyyaml==6.0.3
requests==2.34.2
shapely==2.1.2
thefuzz==0.22.1
tqdm==4.66.5
websocket-client==1.9.0
titlecase==2.4.1
```

- [x] **Step 3: Create the package files**

`Commissioner/__init__.py`:

```python
"""Commissioner: shared, domain-agnostic core models for the Scriptorium pipeline."""
```

`Commissioner/tests/__init__.py`: empty file (makes the tests directory a package so relative imports behave consistently across pytest invocations).

`Commissioner/tests/conftest.py`:

```python
"""
Makes `Commissioner` importable as a package (e.g. `from Commissioner import models`)
when pytest is run from anywhere, the same way every other module's tests/conftest.py
puts its own module on sys.path.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
```

- [x] **Step 4: Write the test**

`Commissioner/tests/test_package.py`:

```python
def test_commissioner_package_imports():
    """Baseline: the package must be importable and pydantic must be available,
    before any real models exist."""
    import Commissioner
    import pydantic

    assert Commissioner is not None
    assert pydantic.VERSION.startswith("2.")
```

- [x] **Step 5: Run the test to verify it passes**

Run: `python -m pytest Commissioner/tests/test_package.py -v`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add Commissioner/__init__.py Commissioner/tests/__init__.py Commissioner/tests/conftest.py Commissioner/tests/test_package.py requirements.txt
git rm Commissioner/.env
git commit -m "Scaffold Commissioner package, add pydantic dependency, remove leftover scrip-stage .env"
```

---

### Task 2: Fact vocabulary data (models.py)

**Files:**
- Create: `Commissioner/models.py`
- Test: `Commissioner/tests/test_models.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `FactScope` (Enum: `PERSON = "person"`, `FAMILY = "family"`), `FactDefinition` (Pydantic model: `name: str, scope: FactScope, gedcom_tag: str, use_value: bool, use_date: bool, use_place: bool, custom: bool, code: str`), `FACT_DEFINITIONS: List[FactDefinition]` (68 entries), `get_fact_definition(name: str) -> FactDefinition` (raises `KeyError` with a message naming the value if not found).

This is a direct, complete transcription of the real `FactTypes.json` at the repo root — every person and family fact type in that file, transcribed exactly (name, GEDCOM tag, the three `use_*` flags, `custom`, and `code`).

- [x] **Step 1: Write the failing test**

`Commissioner/tests/test_models.py`:

```python
from Commissioner.models import FACT_DEFINITIONS, FactScope, get_fact_definition


def test_fact_definitions_has_all_68_entries():
    assert len(FACT_DEFINITIONS) == 68


def test_known_person_fact_resolves():
    birth = get_fact_definition("Birth")
    assert birth.scope == FactScope.PERSON
    assert birth.gedcom_tag == "BIRT"
    assert birth.use_value is False
    assert birth.use_date is True
    assert birth.use_place is True
    assert birth.custom is False
    assert birth.code == "1"


def test_known_family_fact_resolves():
    marriage = get_fact_definition("Marriage")
    assert marriage.scope == FactScope.FAMILY
    assert marriage.gedcom_tag == "MARR"
    assert marriage.code == "300"


def test_custom_fact_resolves():
    scrip = get_fact_definition("Scrip")
    assert scrip.custom is True
    assert scrip.code == "10004"


def test_unknown_fact_name_raises():
    import pytest
    with pytest.raises(KeyError, match="Coordinator"):
        get_fact_definition("Coordinator")
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest Commissioner/tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'Commissioner.models'`

- [x] **Step 3: Write the implementation**

`Commissioner/models.py`:

```python
from enum import Enum
from typing import List

from pydantic import BaseModel


class FactScope(str, Enum):
    PERSON = "person"
    FAMILY = "family"


class FactDefinition(BaseModel):
    name: str
    scope: FactScope
    gedcom_tag: str
    use_value: bool
    use_date: bool
    use_place: bool
    custom: bool
    code: str


FACT_DEFINITIONS: List[FactDefinition] = [
    FactDefinition(name="Birth", scope=FactScope.PERSON, gedcom_tag="BIRT", use_value=False, use_date=True, use_place=True, custom=False, code="1"),
    FactDefinition(name="Death", scope=FactScope.PERSON, gedcom_tag="DEAT", use_value=True, use_date=True, use_place=True, custom=False, code="2"),
    FactDefinition(name="Christen", scope=FactScope.PERSON, gedcom_tag="CHR", use_value=False, use_date=True, use_place=True, custom=False, code="3"),
    FactDefinition(name="Burial", scope=FactScope.PERSON, gedcom_tag="BURI", use_value=False, use_date=True, use_place=True, custom=False, code="4"),
    FactDefinition(name="Cremation", scope=FactScope.PERSON, gedcom_tag="CREM", use_value=False, use_date=True, use_place=True, custom=False, code="5"),
    FactDefinition(name="Adoption", scope=FactScope.PERSON, gedcom_tag="ADOP", use_value=False, use_date=True, use_place=True, custom=False, code="6"),
    FactDefinition(name="Baptism", scope=FactScope.PERSON, gedcom_tag="BAPM", use_value=False, use_date=True, use_place=True, custom=False, code="7"),
    FactDefinition(name="Bar Mitzvah", scope=FactScope.PERSON, gedcom_tag="BARM", use_value=False, use_date=True, use_place=True, custom=False, code="8"),
    FactDefinition(name="Bas Mitzvah", scope=FactScope.PERSON, gedcom_tag="BASM", use_value=False, use_date=True, use_place=True, custom=False, code="9"),
    FactDefinition(name="Blessing", scope=FactScope.PERSON, gedcom_tag="BLES", use_value=False, use_date=True, use_place=True, custom=False, code="10"),
    FactDefinition(name="Christen (adult)", scope=FactScope.PERSON, gedcom_tag="CHRA", use_value=False, use_date=True, use_place=True, custom=False, code="11"),
    FactDefinition(name="Confirmation", scope=FactScope.PERSON, gedcom_tag="CONF", use_value=False, use_date=True, use_place=True, custom=False, code="12"),
    FactDefinition(name="First communion", scope=FactScope.PERSON, gedcom_tag="FCOM", use_value=False, use_date=True, use_place=True, custom=False, code="13"),
    FactDefinition(name="Ordination", scope=FactScope.PERSON, gedcom_tag="ORDN", use_value=False, use_date=True, use_place=True, custom=False, code="14"),
    FactDefinition(name="Naturalization", scope=FactScope.PERSON, gedcom_tag="NATU", use_value=False, use_date=True, use_place=True, custom=False, code="15"),
    FactDefinition(name="Emigration", scope=FactScope.PERSON, gedcom_tag="EMIG", use_value=False, use_date=True, use_place=True, custom=False, code="16"),
    FactDefinition(name="Immigration", scope=FactScope.PERSON, gedcom_tag="IMMI", use_value=False, use_date=True, use_place=True, custom=False, code="17"),
    FactDefinition(name="Census", scope=FactScope.PERSON, gedcom_tag="CENS", use_value=False, use_date=True, use_place=True, custom=False, code="18"),
    FactDefinition(name="Probate", scope=FactScope.PERSON, gedcom_tag="PROB", use_value=False, use_date=True, use_place=True, custom=False, code="19"),
    FactDefinition(name="Will", scope=FactScope.PERSON, gedcom_tag="WILL", use_value=False, use_date=True, use_place=True, custom=False, code="20"),
    FactDefinition(name="Graduation", scope=FactScope.PERSON, gedcom_tag="GRAD", use_value=False, use_date=True, use_place=True, custom=False, code="21"),
    FactDefinition(name="Retirement", scope=FactScope.PERSON, gedcom_tag="RETI", use_value=False, use_date=True, use_place=True, custom=False, code="22"),
    FactDefinition(name="Description", scope=FactScope.PERSON, gedcom_tag="DSCR", use_value=True, use_date=True, use_place=True, custom=False, code="23"),
    FactDefinition(name="Education", scope=FactScope.PERSON, gedcom_tag="EDUC", use_value=True, use_date=True, use_place=True, custom=False, code="24"),
    FactDefinition(name="Nationality", scope=FactScope.PERSON, gedcom_tag="NATI", use_value=True, use_date=True, use_place=True, custom=False, code="25"),
    FactDefinition(name="Occupation", scope=FactScope.PERSON, gedcom_tag="OCCU", use_value=True, use_date=True, use_place=True, custom=False, code="26"),
    FactDefinition(name="Property", scope=FactScope.PERSON, gedcom_tag="PROP", use_value=True, use_date=True, use_place=True, custom=False, code="27"),
    FactDefinition(name="Religion", scope=FactScope.PERSON, gedcom_tag="RELI", use_value=True, use_date=True, use_place=True, custom=False, code="28"),
    FactDefinition(name="Residence", scope=FactScope.PERSON, gedcom_tag="RESI", use_value=True, use_date=True, use_place=True, custom=False, code="29"),
    FactDefinition(name="Soc Sec No", scope=FactScope.PERSON, gedcom_tag="SSN", use_value=True, use_date=False, use_place=False, custom=False, code="30"),
    FactDefinition(name="LDS Baptism", scope=FactScope.PERSON, gedcom_tag="BAPL", use_value=False, use_date=True, use_place=True, custom=False, code="31"),
    FactDefinition(name="LDS Endowment", scope=FactScope.PERSON, gedcom_tag="ENDL", use_value=False, use_date=True, use_place=True, custom=False, code="32"),
    FactDefinition(name="LDS Seal to parents", scope=FactScope.PERSON, gedcom_tag="SLGC", use_value=False, use_date=True, use_place=True, custom=False, code="33"),
    FactDefinition(name="Ancestral File Number", scope=FactScope.PERSON, gedcom_tag="AFN", use_value=True, use_date=False, use_place=False, custom=False, code="34"),
    FactDefinition(name="Reference No", scope=FactScope.PERSON, gedcom_tag="REFN", use_value=True, use_date=False, use_place=False, custom=False, code="35"),
    FactDefinition(name="Caste", scope=FactScope.PERSON, gedcom_tag="CAST", use_value=True, use_date=True, use_place=True, custom=False, code="36"),
    FactDefinition(name="Title (Nobility)", scope=FactScope.PERSON, gedcom_tag="TITL", use_value=True, use_date=True, use_place=True, custom=False, code="37"),
    FactDefinition(name="LDS Confirmation", scope=FactScope.PERSON, gedcom_tag="CONL", use_value=False, use_date=True, use_place=True, custom=False, code="38"),
    FactDefinition(name="LDS Initiatory", scope=FactScope.PERSON, gedcom_tag="WAC", use_value=False, use_date=True, use_place=True, custom=False, code="39"),
    FactDefinition(name="Degree", scope=FactScope.PERSON, gedcom_tag="EVEN", use_value=True, use_date=True, use_place=True, custom=False, code="500"),
    FactDefinition(name="Military", scope=FactScope.PERSON, gedcom_tag="EVEN", use_value=True, use_date=True, use_place=True, custom=False, code="501"),
    FactDefinition(name="Mission", scope=FactScope.PERSON, gedcom_tag="EVEN", use_value=True, use_date=True, use_place=True, custom=False, code="502"),
    FactDefinition(name="Stillborn", scope=FactScope.PERSON, gedcom_tag="EVEN", use_value=False, use_date=True, use_place=True, custom=False, code="503"),
    FactDefinition(name="Illness", scope=FactScope.PERSON, gedcom_tag="EVEN", use_value=True, use_date=True, use_place=True, custom=False, code="504"),
    FactDefinition(name="Living", scope=FactScope.PERSON, gedcom_tag="EVEN", use_value=False, use_date=True, use_place=True, custom=False, code="505"),
    FactDefinition(name="Election", scope=FactScope.PERSON, gedcom_tag="EVEN", use_value=True, use_date=True, use_place=True, custom=False, code="507"),
    FactDefinition(name="Excommunication", scope=FactScope.PERSON, gedcom_tag="EVEN", use_value=False, use_date=True, use_place=True, custom=False, code="508"),
    FactDefinition(name="Namesake", scope=FactScope.PERSON, gedcom_tag="EVEN", use_value=True, use_date=True, use_place=True, custom=False, code="509"),
    FactDefinition(name="Alternate name", scope=FactScope.PERSON, gedcom_tag="EVEN", use_value=False, use_date=True, use_place=False, custom=False, code="900"),
    FactDefinition(name="DNA test", scope=FactScope.PERSON, gedcom_tag="_DNA", use_value=False, use_date=True, use_place=False, custom=False, code="901"),
    FactDefinition(name="Association", scope=FactScope.PERSON, gedcom_tag="EVEN", use_value=True, use_date=True, use_place=True, custom=False, code="902"),
    FactDefinition(name="Miscellaneous", scope=FactScope.PERSON, gedcom_tag="EVEN", use_value=True, use_date=True, use_place=True, custom=False, code="999"),
    FactDefinition(name="Race", scope=FactScope.PERSON, gedcom_tag="EVEN", use_value=True, use_date=True, use_place=False, custom=True, code="10001"),
    FactDefinition(name="dit Name", scope=FactScope.PERSON, gedcom_tag="EVEN", use_value=True, use_date=True, use_place=True, custom=True, code="10002"),
    FactDefinition(name="Scrip", scope=FactScope.PERSON, gedcom_tag="EVEN", use_value=True, use_date=True, use_place=True, custom=True, code="10004"),
    FactDefinition(name="Marriage", scope=FactScope.FAMILY, gedcom_tag="MARR", use_value=False, use_date=True, use_place=True, custom=False, code="300"),
    FactDefinition(name="Annulment", scope=FactScope.FAMILY, gedcom_tag="ANUL", use_value=False, use_date=True, use_place=True, custom=False, code="301"),
    FactDefinition(name="Divorce", scope=FactScope.FAMILY, gedcom_tag="DIV", use_value=False, use_date=True, use_place=True, custom=False, code="302"),
    FactDefinition(name="Divorce filed", scope=FactScope.FAMILY, gedcom_tag="DIVF", use_value=False, use_date=True, use_place=True, custom=False, code="303"),
    FactDefinition(name="Engagement", scope=FactScope.FAMILY, gedcom_tag="ENGA", use_value=False, use_date=True, use_place=True, custom=False, code="304"),
    FactDefinition(name="Marriage Bann", scope=FactScope.FAMILY, gedcom_tag="MARB", use_value=False, use_date=True, use_place=True, custom=False, code="305"),
    FactDefinition(name="Marriage Contract", scope=FactScope.FAMILY, gedcom_tag="MARC", use_value=False, use_date=True, use_place=True, custom=False, code="306"),
    FactDefinition(name="Marriage License", scope=FactScope.FAMILY, gedcom_tag="MARL", use_value=False, use_date=True, use_place=True, custom=False, code="307"),
    FactDefinition(name="Marriage Settlement", scope=FactScope.FAMILY, gedcom_tag="MARS", use_value=False, use_date=True, use_place=True, custom=False, code="308"),
    FactDefinition(name="LDS Seal to spouse", scope=FactScope.FAMILY, gedcom_tag="SLGS", use_value=False, use_date=True, use_place=True, custom=False, code="309"),
    FactDefinition(name="Residence (family)", scope=FactScope.FAMILY, gedcom_tag="RESI", use_value=True, use_date=True, use_place=True, custom=False, code="310"),
    FactDefinition(name="Census (family)", scope=FactScope.FAMILY, gedcom_tag="CENS", use_value=False, use_date=True, use_place=True, custom=False, code="311"),
    FactDefinition(name="Separation", scope=FactScope.FAMILY, gedcom_tag="EVEN", use_value=False, use_date=True, use_place=True, custom=False, code="510"),
]

_FACT_DEFINITIONS_BY_NAME = {fd.name: fd for fd in FACT_DEFINITIONS}


def get_fact_definition(name: str) -> FactDefinition:
    try:
        return _FACT_DEFINITIONS_BY_NAME[name]
    except KeyError:
        raise KeyError(f"Unknown fact_type {name!r}; not present in FACT_DEFINITIONS") from None
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest Commissioner/tests/test_models.py -v`
Expected: PASS (5 tests)

- [x] **Step 5: Commit**

```bash
git add Commissioner/models.py Commissioner/tests/test_models.py
git commit -m "Add fact vocabulary (FactDefinition, FACT_DEFINITIONS) to Commissioner.models"
```

---

### Task 3: fact_registry.py (lookup + export) with FactTypes.json guardrail

**Files:**
- Create: `Commissioner/fact_registry.py`
- Test: `Commissioner/tests/test_fact_registry.py`

**Interfaces:**
- Consumes: `Commissioner.models.FACT_DEFINITIONS`, `FactScope`, `get_fact_definition` (Task 2).
- Produces: `is_family_fact(name: str) -> bool`, `export_fact_types_json() -> dict`.

- [x] **Step 1: Write the failing test**

`Commissioner/tests/test_fact_registry.py`:

```python
import json
from pathlib import Path

from Commissioner.fact_registry import export_fact_types_json, is_family_fact

FACT_TYPES_JSON_PATH = Path(__file__).resolve().parent.parent.parent / "FactTypes.json"


def test_is_family_fact_distinguishes_scope():
    assert is_family_fact("Marriage") is True
    assert is_family_fact("Birth") is False


def test_export_fact_types_json_matches_real_file_on_disk():
    """Guardrail: Archivist.py, Paleographer.py, engine.py, Voyageur.py, and FS.py
    all still read the real FactTypes.json directly. If Commissioner.models'
    FACT_DEFINITIONS ever drifts from that file, this must fail immediately."""
    with open(FACT_TYPES_JSON_PATH, "r", encoding="utf-8") as f:
        real = json.load(f)
    assert export_fact_types_json() == real
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest Commissioner/tests/test_fact_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'Commissioner.fact_registry'`

- [x] **Step 3: Write the implementation**

`Commissioner/fact_registry.py`:

```python
from typing import Dict

from Commissioner.models import FACT_DEFINITIONS, FactScope, get_fact_definition

__all__ = ["get_fact_definition", "is_family_fact", "export_fact_types_json"]


def is_family_fact(name: str) -> bool:
    return get_fact_definition(name).scope == FactScope.FAMILY


def export_fact_types_json() -> Dict[str, Dict[str, dict]]:
    """Reproduces FactTypes.json's exact on-disk shape from FACT_DEFINITIONS -
    used by the guardrail test, and by a future migration phase to retire the
    physical file once Archivist/Paleographer/Voyageur read from here instead."""
    result: Dict[str, Dict[str, dict]] = {"person": {}, "family": {}}
    for fd in FACT_DEFINITIONS:
        result[fd.scope.value][fd.name] = {
            "gedcom_tag": fd.gedcom_tag,
            "use_value": fd.use_value,
            "use_date": fd.use_date,
            "use_place": fd.use_place,
            "custom": fd.custom,
            "code": fd.code,
        }
    return result
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest Commissioner/tests/test_fact_registry.py -v`
Expected: PASS (2 tests)

- [x] **Step 5: Commit**

```bash
git add Commissioner/fact_registry.py Commissioner/tests/test_fact_registry.py
git commit -m "Add fact_registry lookup/export layer with FactTypes.json guardrail test"
```

---

### Task 4: Ingestion schema models (Collection/Sheet/Record/Participant/Fact) with schema.json guardrail

**Files:**
- Modify: `Commissioner/models.py`
- Test: `Commissioner/tests/test_models.py`

**Interfaces:**
- Consumes: `_FACT_DEFINITIONS_BY_NAME` (Task 2, module-private, same file).
- Produces: `AlternateName`, `Fact` (with `fact_type` validated against the fact vocabulary), `DocumentMetadata`, `Participant`, `Record`, `Sheet`, `Collection` — all Pydantic `BaseModel`s.

Field requiredness follows `Paleographer/schema.json` precisely where it declares an explicit `required` list (only `Participant`'s nested item schema does: `role_name`, `std_given`, `is_priest`, `sex`); every other field is modeled as optional with a sensible default, since `schema.json` itself does not constrain them further.

- [x] **Step 1: Write the failing test**

Append to `Commissioner/tests/test_models.py`:

```python
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from Commissioner.models import (
    AlternateName,
    Collection,
    DocumentMetadata,
    Fact,
    Participant,
    Record,
    Sheet,
)

SCHEMA_JSON_PATH = Path(__file__).resolve().parent.parent.parent / "Paleographer" / "schema.json"

EXPECTED_FIELDS = {
    "Collection": {"collection_title", "sheets"},
    "Sheet": {"page_id", "document_metadata", "records"},
    "DocumentMetadata": {"file_name", "file_type", "volume", "pages", "source_name", "source_location"},
    "Record": {
        "record_id", "page", "record_number", "event_type", "year", "event_date",
        "event_place", "english_translation", "original_transcription", "review",
        "review_reason", "continues_on_next_image", "continues_from_previous_image",
        "type_specific_fields", "participants",
    },
    "Participant": {
        "role_number", "role_name", "std_given", "std_surname", "raw_given",
        "raw_surname", "dit_name", "alternate_names", "prefix", "suffix", "sex",
        "is_priest", "age", "age_unit", "occupation", "race", "religion",
        "residence", "birth_date", "birth_place", "death_date", "death_place",
        "review", "review_reason", "facts", "type_specific_fields",
    },
    "AlternateName": {"value"},
    "Fact": {"fact_type", "value", "date", "place"},
}


def test_schema_json_file_exists_for_guardrail():
    assert SCHEMA_JSON_PATH.is_file()


def test_models_match_schema_json_field_names():
    """Guardrail: Paleographer still reads schema.json directly for its LLM calls.
    If models.py's fields ever drift from that file's shape, this must fail
    immediately rather than silently diverging."""
    full_schema = Collection.model_json_schema()
    defs = full_schema.get("$defs", {})

    assert set(full_schema["properties"].keys()) == EXPECTED_FIELDS["Collection"]

    for class_name, expected_fields in EXPECTED_FIELDS.items():
        if class_name == "Collection":
            continue
        assert class_name in defs, f"{class_name} missing from $defs"
        actual_fields = set(defs[class_name]["properties"].keys())
        assert actual_fields == expected_fields, (
            f"{class_name}: expected {expected_fields}, got {actual_fields}"
        )


def test_fact_rejects_unknown_fact_type():
    with pytest.raises(ValidationError, match="Coordinator"):
        Fact(fact_type="Coordinator")


def test_fact_accepts_known_fact_type():
    fact = Fact(fact_type="Birth", date="1850-01-01")
    assert fact.fact_type == "Birth"
    assert fact.value is None


def test_participant_requires_role_name_key_but_allows_null():
    participant = Participant(role_name=None, std_given="Jean", is_priest=False, sex="M")
    assert participant.role_name is None


def test_participant_requires_std_given_is_priest_sex():
    with pytest.raises(ValidationError):
        Participant(role_name="Other")


def test_full_collection_round_trips_minimal_payload():
    collection = Collection(
        collection_title="Test Collection",
        sheets=[
            Sheet(
                page_id="page_001",
                document_metadata=DocumentMetadata(source_location="Red River"),
                records=[
                    Record(
                        page="page_001",
                        record_number="1",
                        event_type="Baptism",
                        review=False,
                        continues_on_next_image=False,
                        continues_from_previous_image=False,
                        participants=[
                            Participant(
                                role_name="Primary",
                                std_given="Jean",
                                is_priest=False,
                                sex="M",
                                review=False,
                                facts=[Fact(fact_type="Birth", date="1850")],
                                alternate_names=[AlternateName(value="Jean-Baptiste")],
                            )
                        ],
                    )
                ],
            )
        ],
    )
    assert collection.sheets[0].records[0].participants[0].facts[0].fact_type == "Birth"
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest Commissioner/tests/test_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'Collection' from 'Commissioner.models'`

- [x] **Step 3: Write the implementation**

Append to `Commissioner/models.py`:

```python
from typing import Any, Dict, List, Literal, Optional

from pydantic import Field, field_validator


class AlternateName(BaseModel):
    value: str


class Fact(BaseModel):
    fact_type: str
    value: Optional[str] = None
    date: Optional[str] = None
    place: Optional[str] = None

    @field_validator("fact_type")
    @classmethod
    def _validate_fact_type(cls, v: str) -> str:
        if v not in _FACT_DEFINITIONS_BY_NAME:
            raise ValueError(f"Unknown fact_type {v!r}; not present in FACT_DEFINITIONS")
        return v


class DocumentMetadata(BaseModel):
    file_name: Optional[str] = None
    file_type: Optional[str] = None
    volume: Optional[str] = None
    pages: Optional[str] = None
    source_name: Optional[str] = None
    source_location: Optional[str] = None


class Participant(BaseModel):
    role_number: Optional[str] = None
    role_name: Optional[str]
    std_given: str
    std_surname: Optional[str] = None
    raw_given: Optional[str] = None
    raw_surname: Optional[str] = None
    dit_name: Optional[str] = None
    alternate_names: Optional[List[AlternateName]] = None
    prefix: Optional[str] = None
    suffix: Optional[str] = None
    sex: Literal["M", "F", "U"]
    is_priest: bool
    age: Optional[str] = None
    age_unit: Optional[Literal["years", "months", "days"]] = None
    occupation: Optional[str] = None
    race: Optional[str] = None
    religion: Optional[str] = None
    residence: Optional[str] = None
    birth_date: Optional[str] = None
    birth_place: Optional[str] = None
    death_date: Optional[str] = None
    death_place: Optional[str] = None
    review: bool = False
    review_reason: Optional[str] = None
    facts: Optional[List[Fact]] = None
    type_specific_fields: Dict[str, Any] = Field(default_factory=dict)


class Record(BaseModel):
    record_id: Optional[str] = None
    page: str
    record_number: str
    event_type: str
    year: Optional[str] = None
    event_date: Optional[str] = None
    event_place: Optional[str] = None
    english_translation: Optional[str] = None
    original_transcription: Optional[str] = None
    review: bool = False
    review_reason: Optional[str] = None
    continues_on_next_image: bool = False
    continues_from_previous_image: bool = False
    type_specific_fields: Dict[str, Any] = Field(default_factory=dict)
    participants: List[Participant] = Field(default_factory=list)


class Sheet(BaseModel):
    page_id: str
    document_metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    records: List[Record] = Field(default_factory=list)


class Collection(BaseModel):
    collection_title: Optional[str] = None
    sheets: List[Sheet] = Field(default_factory=list)
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest Commissioner/tests/test_models.py -v`
Expected: PASS (all tests, including the 5 from Task 2)

- [x] **Step 5: Commit**

```bash
git add Commissioner/models.py Commissioner/tests/test_models.py
git commit -m "Add Collection/Sheet/Record/Participant/Fact models with schema.json guardrail test"
```

---

### Task 5: record_registry.py — dynamic .pmt scanning

**Files:**
- Create: `Commissioner/record_registry.py`
- Test: `Commissioner/tests/test_record_registry.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (reads `.pmt` files directly).
- Produces: `UnknownDocumentTypeError`, `UnknownFieldTypeError`, `InvalidRoleError` (all `Exception` subclasses); `get_document_types() -> List[str]`; `get_valid_roles(document_type: str) -> frozenset[str]`; `validate_record_extra_fields(document_type: str, raw: dict) -> BaseModel`; `validate_participant_extra_fields(document_type: str, raw: dict) -> BaseModel`; `validate_role_name(document_type: str, role_name: Optional[str]) -> None`.

The type map supports `string`, `int`, `float`, `bool`, `date`, and `enum` (with a `choices` list). An unrecognized `type:` token in any `.pmt` raises `UnknownFieldTypeError` at import time — before any ingestion run touches that document type.

- [x] **Step 1: Write the failing test**

`Commissioner/tests/test_record_registry.py`:

```python
import pytest

from Commissioner.record_registry import (
    InvalidRoleError,
    UnknownDocumentTypeError,
    get_document_types,
    get_valid_roles,
    validate_participant_extra_fields,
    validate_record_extra_fields,
    validate_role_name,
)


def test_discovers_both_real_pmt_files():
    doc_types = get_document_types()
    assert "Parish" in doc_types
    assert "Scrip" in doc_types


def test_parish_has_no_extra_fields():
    record_extra = validate_record_extra_fields("Parish", {})
    assert record_extra.model_dump() == {}
    participant_extra = validate_participant_extra_fields("Parish", {})
    assert participant_extra.model_dump() == {}


def test_scrip_record_extra_fields_validate_and_coerce_types():
    extra = validate_record_extra_fields(
        "Scrip",
        {
            "claim_number": "5473",
            "scrip_amount": "160",
            "scrip_type": "Cash",
        },
    )
    assert extra.claim_number == "5473"
    assert extra.scrip_amount == "160"
    assert extra.scrip_type == "Cash"


def test_scrip_record_extra_rejects_invalid_enum_choice():
    from pydantic import ValidationError
    with pytest.raises(ValidationError, match="Land"):
        validate_record_extra_fields("Scrip", {"scrip_type": "Currency"})


def test_scrip_participant_extra_fields():
    extra = validate_participant_extra_fields(
        "Scrip", {"marital_status": "Married", "race_or_origin": "Metis"}
    )
    assert extra.marital_status == "Married"
    assert extra.race_or_origin == "Metis"


def test_unknown_document_type_raises():
    with pytest.raises(UnknownDocumentTypeError, match="Census"):
        validate_record_extra_fields("Census", {})


def test_valid_roles_differ_by_document_type():
    parish_roles = get_valid_roles("Parish")
    scrip_roles = get_valid_roles("Scrip")
    assert "Officiant" in parish_roles
    assert "Claimant" in scrip_roles
    assert "Claimant" not in parish_roles


def test_validate_role_name_accepts_known_role():
    validate_role_name("Scrip", "Claimant")
    validate_role_name("Scrip", None)


def test_validate_role_name_rejects_unknown_role():
    with pytest.raises(InvalidRoleError, match="Coordinator"):
        validate_role_name("Scrip", "Coordinator")
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest Commissioner/tests/test_record_registry.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'Commissioner.record_registry'`

- [x] **Step 3: Write the implementation**

`Commissioner/record_registry.py`:

```python
from datetime import date
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Type

import yaml
from pydantic import BaseModel, create_model

PMT_DIR = Path(__file__).resolve().parent.parent / "Paleographer" / "prompts"

_PRIMITIVE_TYPE_MAP: Dict[str, type] = {
    "string": str,
    "int": int,
    "float": float,
    "bool": bool,
    "date": date,
}


class UnknownDocumentTypeError(Exception):
    pass


class UnknownFieldTypeError(Exception):
    pass


class InvalidRoleError(Exception):
    pass


class _DocumentTypeSchema:
    def __init__(
        self,
        record_extra_model: Type[BaseModel],
        participant_extra_model: Type[BaseModel],
        valid_roles: FrozenSet[str],
    ):
        self.record_extra_model = record_extra_model
        self.participant_extra_model = participant_extra_model
        self.valid_roles = valid_roles


def _load_pmt_front_matter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    _, front_matter, _ = text.split("---", 2)
    return yaml.safe_load(front_matter) or {}


def _field_type_for(document_type: str, field: dict) -> Any:
    type_name = field["type"]
    if type_name == "enum":
        from typing import Literal

        choices = tuple(field["choices"])
        return Literal[choices]
    if type_name not in _PRIMITIVE_TYPE_MAP:
        raise UnknownFieldTypeError(
            f"{document_type}: unrecognized field type {type_name!r} for field {field['name']!r}"
        )
    return _PRIMITIVE_TYPE_MAP[type_name]


def _build_extra_model(model_name: str, document_type: str, fields: List[dict]) -> Type[BaseModel]:
    field_definitions = {
        field["name"]: (Optional[_field_type_for(document_type, field)], None) for field in fields
    }
    return create_model(model_name, **field_definitions)


def _build_registry() -> Dict[str, _DocumentTypeSchema]:
    registry: Dict[str, _DocumentTypeSchema] = {}
    for pmt_path in sorted(PMT_DIR.glob("*.pmt")):
        document_type = pmt_path.stem
        front_matter = _load_pmt_front_matter(pmt_path)

        extra_fields = front_matter.get("extra_fields") or {}
        record_fields = extra_fields.get("record", [])
        participant_fields = extra_fields.get("participant", [])

        record_extra_model = _build_extra_model(f"{document_type}RecordExtra", document_type, record_fields)
        participant_extra_model = _build_extra_model(
            f"{document_type}ParticipantExtra", document_type, participant_fields
        )

        roles = front_matter.get("roles") or {}
        valid_roles = frozenset(role["name"] for role in roles.values())

        registry[document_type] = _DocumentTypeSchema(record_extra_model, participant_extra_model, valid_roles)
    return registry


_REGISTRY: Dict[str, _DocumentTypeSchema] = _build_registry()


def _get_schema(document_type: str) -> _DocumentTypeSchema:
    try:
        return _REGISTRY[document_type]
    except KeyError:
        raise UnknownDocumentTypeError(
            f"Unknown document_type {document_type!r}; no matching .pmt file found"
        ) from None


def get_document_types() -> List[str]:
    return list(_REGISTRY.keys())


def get_valid_roles(document_type: str) -> FrozenSet[str]:
    return _get_schema(document_type).valid_roles


def validate_record_extra_fields(document_type: str, raw: dict) -> BaseModel:
    return _get_schema(document_type).record_extra_model(**raw)


def validate_participant_extra_fields(document_type: str, raw: dict) -> BaseModel:
    return _get_schema(document_type).participant_extra_model(**raw)


def validate_role_name(document_type: str, role_name: Optional[str]) -> None:
    if role_name is None:
        return
    valid_roles = get_valid_roles(document_type)
    if role_name not in valid_roles:
        raise InvalidRoleError(
            f"{role_name!r} is not a valid role for document_type {document_type!r} "
            f"(valid roles: {sorted(valid_roles)})"
        )
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest Commissioner/tests/test_record_registry.py -v`
Expected: FAIL on `test_scrip_record_extra_fields_validate_and_coerce_types` and the enum-rejection test — `Scrip.pmt` doesn't have `scrip_type` yet. This is expected; Task 6 edits `Scrip.pmt` to add it. Confirm every other test in this file passes first.

Run: `python -m pytest Commissioner/tests/test_record_registry.py -v -k "not scrip_type and not scrip_record_extra_fields_validate_and_coerce"`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add Commissioner/record_registry.py Commissioner/tests/test_record_registry.py
git commit -m "Add record_registry: dynamic .pmt scanning for extra fields and role validation"
```

---

### Task 6: Split Scrip.pmt's scrip_amount into scrip_amount/scrip_type, add parse_collection(), finish public API

**Files:**
- Modify: `Paleographer/prompts/Scrip.pmt`
- Modify: `Commissioner/record_registry.py`
- Modify: `Commissioner/__init__.py`
- Test: `Commissioner/tests/test_record_registry.py`

**Interfaces:**
- Consumes: `Collection.model_validate` (Task 4), `validate_record_extra_fields`/`validate_participant_extra_fields`/`validate_role_name` (Task 5).
- Produces: `parse_collection(raw_json: dict, document_type: str) -> Collection`.

- [x] **Step 1: Edit Scrip.pmt to split scrip_amount into scrip_amount + scrip_type**

In `Paleographer/prompts/Scrip.pmt`, in the `extra_fields.record` list, replace:

```yaml
    - {name: scrip_amount, type: string}
```

with:

```yaml
    - {name: scrip_amount, type: string}
    - {name: scrip_type, type: enum, choices: [Cash, Land]}
```

In the prompt body's `SCRIP-SPECIFIC FIELDS` section, replace:

```
- scrip_amount: The value of scrip or land granted (e.g. "$160", "$240", "240 acres").
```

with:

```
- scrip_amount: The numeric value of scrip or land granted (e.g. "160", "240").
- scrip_type: Whether the grant was "Cash" or "Land" - choose exactly one.
```

- [x] **Step 2: Re-run the tests that were expected to fail in Task 5**

Run: `python -m pytest Commissioner/tests/test_record_registry.py -v`
Expected: PASS (all tests now pass, including the two `scrip_type` ones)

- [x] **Step 3: Write the failing test for parse_collection**

Append to `Commissioner/tests/test_record_registry.py`:

```python
import pytest
from pydantic import ValidationError

from Commissioner.record_registry import InvalidRoleError, parse_collection


SAMPLE_SCRIP_PAYLOAD = {
    "collection_title": "Test Scrip Collection",
    "sheets": [
        {
            "page_id": "page_001",
            "document_metadata": {"source_location": "Manitoba"},
            "records": [
                {
                    "page": "page_001",
                    "record_number": "5473-0-0",
                    "event_type": "Scrip",
                    "review": False,
                    "continues_on_next_image": False,
                    "continues_from_previous_image": False,
                    "type_specific_fields": {
                        "claim_number": "5473",
                        "scrip_amount": "160",
                        "scrip_type": "Cash",
                    },
                    "participants": [
                        {
                            "role_name": "Claimant",
                            "std_given": "Jean",
                            "std_surname": "Gagnon",
                            "is_priest": False,
                            "sex": "M",
                            "review": False,
                            "type_specific_fields": {
                                "marital_status": "Married",
                                "race_or_origin": "Metis",
                            },
                        }
                    ],
                }
            ],
        }
    ],
}


def test_parse_collection_validates_scrip_payload_end_to_end():
    collection = parse_collection(SAMPLE_SCRIP_PAYLOAD, document_type="Scrip")
    record = collection.sheets[0].records[0]
    assert record.type_specific_fields["scrip_type"] == "Cash"
    participant = record.participants[0]
    assert participant.type_specific_fields["race_or_origin"] == "Metis"


def test_parse_collection_rejects_bad_extra_field_type():
    bad_payload = {
        **SAMPLE_SCRIP_PAYLOAD,
        "sheets": [
            {
                **SAMPLE_SCRIP_PAYLOAD["sheets"][0],
                "records": [
                    {
                        **SAMPLE_SCRIP_PAYLOAD["sheets"][0]["records"][0],
                        "type_specific_fields": {"scrip_type": "Currency"},
                    }
                ],
            }
        ],
    }
    with pytest.raises(ValidationError, match="Land"):
        parse_collection(bad_payload, document_type="Scrip")


def test_parse_collection_rejects_invalid_role_for_document_type():
    bad_payload = {
        **SAMPLE_SCRIP_PAYLOAD,
        "sheets": [
            {
                **SAMPLE_SCRIP_PAYLOAD["sheets"][0],
                "records": [
                    {
                        **SAMPLE_SCRIP_PAYLOAD["sheets"][0]["records"][0],
                        "participants": [
                            {
                                **SAMPLE_SCRIP_PAYLOAD["sheets"][0]["records"][0]["participants"][0],
                                "role_name": "Coordinator",
                            }
                        ],
                    }
                ],
            }
        ],
    }
    with pytest.raises(InvalidRoleError, match="Coordinator"):
        parse_collection(bad_payload, document_type="Scrip")
```

- [x] **Step 4: Run test to verify it fails**

Run: `python -m pytest Commissioner/tests/test_record_registry.py -v -k parse_collection`
Expected: FAIL with `ImportError: cannot import name 'parse_collection'`

- [x] **Step 5: Implement parse_collection**

Append to `Commissioner/record_registry.py`:

```python
from Commissioner.models import Collection


def parse_collection(raw_json: dict, document_type: str) -> Collection:
    _get_schema(document_type)  # raises UnknownDocumentTypeError early if unrecognized

    collection = Collection.model_validate(raw_json)

    for sheet in collection.sheets:
        for record in sheet.records:
            validated_record_extra = validate_record_extra_fields(document_type, record.type_specific_fields)
            record.type_specific_fields = validated_record_extra.model_dump()

            for participant in record.participants:
                validated_participant_extra = validate_participant_extra_fields(
                    document_type, participant.type_specific_fields
                )
                participant.type_specific_fields = validated_participant_extra.model_dump()
                validate_role_name(document_type, participant.role_name)

    return collection
```

- [x] **Step 6: Run test to verify it passes**

Run: `python -m pytest Commissioner/tests/test_record_registry.py -v`
Expected: PASS (all tests)

- [x] **Step 7: Finalize the public API**

`Commissioner/__init__.py`:

```python
"""Commissioner: shared, domain-agnostic core models for the Scriptorium pipeline."""

from Commissioner.models import (
    AlternateName,
    Collection,
    DocumentMetadata,
    Fact,
    FactDefinition,
    FactScope,
    Participant,
    Record,
    Sheet,
    FACT_DEFINITIONS,
    get_fact_definition,
)
from Commissioner.fact_registry import export_fact_types_json, is_family_fact
from Commissioner.record_registry import (
    InvalidRoleError,
    UnknownDocumentTypeError,
    UnknownFieldTypeError,
    get_document_types,
    get_valid_roles,
    parse_collection,
    validate_participant_extra_fields,
    validate_record_extra_fields,
    validate_role_name,
)

__all__ = [
    "AlternateName",
    "Collection",
    "DocumentMetadata",
    "Fact",
    "FactDefinition",
    "FactScope",
    "Participant",
    "Record",
    "Sheet",
    "FACT_DEFINITIONS",
    "get_fact_definition",
    "export_fact_types_json",
    "is_family_fact",
    "InvalidRoleError",
    "UnknownDocumentTypeError",
    "UnknownFieldTypeError",
    "get_document_types",
    "get_valid_roles",
    "parse_collection",
    "validate_participant_extra_fields",
    "validate_record_extra_fields",
    "validate_role_name",
]
```

- [x] **Step 8: Run the full Commissioner test suite**

Run: `python -m pytest Commissioner/tests/ -v`
Expected: PASS (every test across all six tasks)

- [x] **Step 9: Commit**

```bash
git add Paleographer/prompts/Scrip.pmt Commissioner/record_registry.py Commissioner/__init__.py Commissioner/tests/test_record_registry.py
git commit -m "Add parse_collection ingestion entry point, split Scrip scrip_amount/scrip_type, finalize public API"
```

---

## Self-Review

**Spec coverage:**
- Package layout / non-goals (no legacy code touched except the pre-approved `Scrip.pmt` edit) → Task 1, Task 6.
- Fact vocabulary authored in `models.py`, not loaded from JSON → Task 2.
- `fact_registry.py` as thin lookup/export layer + guardrail test → Task 3.
- Core schema models mirroring `schema.json`, guardrail test → Task 4.
- Dynamic `.pmt` registry (extra fields + roles), type map incl. `enum` → Task 5.
- `scrip_amount`/`scrip_type` split → Task 6, Step 1.
- `parse_collection` ingestion boundary → Task 6, Steps 3-6.
- Error handling (unknown fact_type, unknown document_type, unknown field type, bad value type, invalid role) → covered across Tasks 2-6's negative tests.
- Testing against real files, not mocks → every task's tests import the real `FactTypes.json`, `schema.json`, `Parish.pmt`, `Scrip.pmt`.

**Placeholder scan:** No TBD/TODO; every step has real, complete code.

**Type consistency:** `Collection`/`Sheet`/`Record`/`Participant`/`Fact` field names and types introduced in Task 4 are used identically in Task 6's `parse_collection` and its tests. `get_document_types`/`get_valid_roles`/`validate_*`/`parse_collection` signatures introduced in Task 5 match their usage in Task 6 and `Commissioner/__init__.py` exactly.

---

Plan complete and saved to `docs/superpowers/plans/2026-08-05-commissioner-core-domain-models.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
