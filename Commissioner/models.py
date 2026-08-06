from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


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
