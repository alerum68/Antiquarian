from datetime import date
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Type

import yaml
from pydantic import BaseModel, ConfigDict, create_model

from Commissioner.models import Collection

PMT_DIR = Path(__file__).resolve().parent.parent / "Paleographer" / "prompts"

_PRIMITIVE_TYPE_MAP: Dict[str, type] = {
    "string": str,
    "int": int,
    "float": float,
    "bool": bool,
    "date": date,
    "dict": Dict[str, Any],
    "list": List[Any],
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
        role_validation_mode: str,
    ):
        self.record_extra_model = record_extra_model
        self.participant_extra_model = participant_extra_model
        self.valid_roles = valid_roles
        self.role_validation_mode = role_validation_mode


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
    """Builds the validation-only model for a document type's extra fields.

    `extra="forbid"` is deliberate: this model is never used to *replace* the caller's
    type_specific_fields dict, only to check it, so an undeclared key must fail loudly
    rather than be silently ignored (and thereby silently dropped)."""
    field_definitions = {
        field["name"]: (Optional[_field_type_for(document_type, field)], None) for field in fields
    }
    return create_model(model_name, __config__=ConfigDict(extra="forbid"), **field_definitions)


def _build_registry(pmt_dir: Path = PMT_DIR) -> Dict[str, _DocumentTypeSchema]:
    registry: Dict[str, _DocumentTypeSchema] = {}
    for pmt_path in sorted(pmt_dir.glob("*.pmt")):
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

        role_validation_mode = front_matter.get("role_validation", "closed")

        registry[document_type] = _DocumentTypeSchema(
            record_extra_model, participant_extra_model, valid_roles, role_validation_mode
        )
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
    schema = _get_schema(document_type)
    if schema.role_validation_mode == "open":
        return
    if role_name not in schema.valid_roles:
        raise InvalidRoleError(
            f"{role_name!r} is not a valid role for document_type {document_type!r} "
            f"(valid roles: {sorted(schema.valid_roles)})"
        )


def parse_collection(raw_json: dict, document_type: str) -> Collection:
    _get_schema(document_type)  # raises UnknownDocumentTypeError early if unrecognized

    collection = Collection.model_validate(raw_json)

    for sheet in collection.sheets:
        for record in sheet.records:
            # Validation only - the caller's dict is deliberately left untouched. Replacing
            # it with the model's dump would inject None for every declared-but-absent field
            # and drop anything the document type doesn't declare.
            validate_record_extra_fields(document_type, record.type_specific_fields)

            for participant in record.participants:
                validate_participant_extra_fields(document_type, participant.type_specific_fields)
                validate_role_name(document_type, participant.role_name)

    return collection


def validate_soft(data: dict, document_type: str, label: str) -> None:
    """Runs parse_collection() as a visibility check, never a gate: a validation failure is
    logged and swallowed here so a Commissioner-side schema gap can never block a real
    Voyageur gather or a Paleographer MASTER_DB write. Shared by every soft-fail call site -
    see the sub-project 4 design spec
    (docs/superpowers/specs/2026-08-06-paleographer-commissioner-soft-fail-design.md)."""
    try:
        parse_collection(data, document_type)
    except Exception as e:
        print(f"[WARN] Commissioner validation failed for {label!r}: {e}")


def build_empty_sheet(file_name: str, file_type: str, page_id: Optional[str] = None) -> dict:
    """Builds a Commissioner-shaped placeholder sheet dict: a real document_metadata (the
    image reference) wrapping exactly one empty-content Record (participants: [], every
    other field its model default). Paleographer's own get_processed_files treats a sheet
    with no record carrying non-empty participants as unprocessed, so this placeholder gets
    picked up and replaced by a real AI pass rather than silently skipped forever."""
    return {
        "page_id": page_id if page_id is not None else file_name,
        "document_metadata": {
            "file_name": file_name,
            "file_type": file_type,
            "volume": None,
            "pages": None,
            "source_name": None,
            "source_location": None,
        },
        "records": [{
            "record_id": None,
            "page": None,
            "record_number": None,
            "event_type": None,
            "year": None,
            "event_date": None,
            "event_place": None,
            "citation_details": None,
            "citation_text": None,
            "review": False,
            "review_reason": None,
            "continues_on_next_image": False,
            "continues_from_previous_image": False,
            "type_specific_fields": {},
            "participants": [],
        }],
    }


def get_field_remap(document_type: str) -> Dict[str, str]:
    """Returns document_type's own .pmt front matter field_remap table (e.g.
    {"CHURCH_MASTER_DB_NAME": "MASTER_DB_NAME", ...}). Reuses the same lightweight
    _load_pmt_front_matter() the rest of this module already uses, rather than
    Paleographer/engine.py's own TYPE_CFG - engine.py transitively imports google.genai,
    pdfplumber, PIL, PDFix, and ScriptoriumMCP.agy_client, a dependency chain LAC.py (a
    standalone, light-dependency script) must not be forced to pull in."""
    _get_schema(document_type)  # raises UnknownDocumentTypeError early if unrecognized
    front_matter = _load_pmt_front_matter(PMT_DIR / f"{document_type}.pmt")
    return front_matter.get("field_remap") or {}
