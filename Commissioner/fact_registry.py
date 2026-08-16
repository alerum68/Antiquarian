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
