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
