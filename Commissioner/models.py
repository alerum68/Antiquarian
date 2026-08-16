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
    FactDefinition(
        name="Birth", scope=FactScope.PERSON, gedcom_tag="BIRT",
        use_value=False, use_date=True, use_place=True, custom=False, code="1",
    ),
    FactDefinition(
        name="Death", scope=FactScope.PERSON, gedcom_tag="DEAT",
        use_value=True, use_date=True, use_place=True, custom=False, code="2",
    ),
    FactDefinition(
        name="Christen", scope=FactScope.PERSON, gedcom_tag="CHR",
        use_value=False, use_date=True, use_place=True, custom=False, code="3",
    ),
    FactDefinition(
        name="Burial", scope=FactScope.PERSON, gedcom_tag="BURI",
        use_value=False, use_date=True, use_place=True, custom=False, code="4",
    ),
    FactDefinition(
        name="Cremation", scope=FactScope.PERSON, gedcom_tag="CREM",
        use_value=False, use_date=True, use_place=True, custom=False, code="5",
    ),
    FactDefinition(
        name="Adoption", scope=FactScope.PERSON, gedcom_tag="ADOP",
        use_value=False, use_date=True, use_place=True, custom=False, code="6",
    ),
    FactDefinition(
        name="Baptism", scope=FactScope.PERSON, gedcom_tag="BAPM",
        use_value=False, use_date=True, use_place=True, custom=False, code="7",
    ),
    FactDefinition(
        name="Bar Mitzvah", scope=FactScope.PERSON, gedcom_tag="BARM",
        use_value=False, use_date=True, use_place=True, custom=False, code="8",
    ),
    FactDefinition(
        name="Bas Mitzvah", scope=FactScope.PERSON, gedcom_tag="BASM",
        use_value=False, use_date=True, use_place=True, custom=False, code="9",
    ),
    FactDefinition(
        name="Blessing", scope=FactScope.PERSON, gedcom_tag="BLES",
        use_value=False, use_date=True, use_place=True, custom=False, code="10",
    ),
    FactDefinition(
        name="Christen (adult)", scope=FactScope.PERSON, gedcom_tag="CHRA",
        use_value=False, use_date=True, use_place=True, custom=False, code="11",
    ),
    FactDefinition(
        name="Confirmation", scope=FactScope.PERSON, gedcom_tag="CONF",
        use_value=False, use_date=True, use_place=True, custom=False, code="12",
    ),
    FactDefinition(
        name="First communion", scope=FactScope.PERSON, gedcom_tag="FCOM",
        use_value=False, use_date=True, use_place=True, custom=False, code="13",
    ),
    FactDefinition(
        name="Ordination", scope=FactScope.PERSON, gedcom_tag="ORDN",
        use_value=False, use_date=True, use_place=True, custom=False, code="14",
    ),
    FactDefinition(
        name="Naturalization", scope=FactScope.PERSON, gedcom_tag="NATU",
        use_value=False, use_date=True, use_place=True, custom=False, code="15",
    ),
    FactDefinition(
        name="Emigration", scope=FactScope.PERSON, gedcom_tag="EMIG",
        use_value=False, use_date=True, use_place=True, custom=False, code="16",
    ),
    FactDefinition(
        name="Immigration", scope=FactScope.PERSON, gedcom_tag="IMMI",
        use_value=False, use_date=True, use_place=True, custom=False, code="17",
    ),
    FactDefinition(
        name="Census", scope=FactScope.PERSON, gedcom_tag="CENS",
        use_value=False, use_date=True, use_place=True, custom=False, code="18",
    ),
    FactDefinition(
        name="Probate", scope=FactScope.PERSON, gedcom_tag="PROB",
        use_value=False, use_date=True, use_place=True, custom=False, code="19",
    ),
    FactDefinition(
        name="Will", scope=FactScope.PERSON, gedcom_tag="WILL",
        use_value=False, use_date=True, use_place=True, custom=False, code="20",
    ),
    FactDefinition(
        name="Graduation", scope=FactScope.PERSON, gedcom_tag="GRAD",
        use_value=False, use_date=True, use_place=True, custom=False, code="21",
    ),
    FactDefinition(
        name="Retirement", scope=FactScope.PERSON, gedcom_tag="RETI",
        use_value=False, use_date=True, use_place=True, custom=False, code="22",
    ),
    FactDefinition(
        name="Description", scope=FactScope.PERSON, gedcom_tag="DSCR",
        use_value=True, use_date=True, use_place=True, custom=False, code="23",
    ),
    FactDefinition(
        name="Education", scope=FactScope.PERSON, gedcom_tag="EDUC",
        use_value=True, use_date=True, use_place=True, custom=False, code="24",
    ),
    FactDefinition(
        name="Nationality", scope=FactScope.PERSON, gedcom_tag="NATI",
        use_value=True, use_date=True, use_place=True, custom=False, code="25",
    ),
    FactDefinition(
        name="Occupation", scope=FactScope.PERSON, gedcom_tag="OCCU",
        use_value=True, use_date=True, use_place=True, custom=False, code="26",
    ),
    FactDefinition(
        name="Property", scope=FactScope.PERSON, gedcom_tag="PROP",
        use_value=True, use_date=True, use_place=True, custom=False, code="27",
    ),
    FactDefinition(
        name="Religion", scope=FactScope.PERSON, gedcom_tag="RELI",
        use_value=True, use_date=True, use_place=True, custom=False, code="28",
    ),
    FactDefinition(
        name="Residence", scope=FactScope.PERSON, gedcom_tag="RESI",
        use_value=True, use_date=True, use_place=True, custom=False, code="29",
    ),
    FactDefinition(
        name="Soc Sec No", scope=FactScope.PERSON, gedcom_tag="SSN",
        use_value=True, use_date=False, use_place=False, custom=False, code="30",
    ),
    FactDefinition(
        name="LDS Baptism", scope=FactScope.PERSON, gedcom_tag="BAPL",
        use_value=False, use_date=True, use_place=True, custom=False, code="31",
    ),
    FactDefinition(
        name="LDS Endowment", scope=FactScope.PERSON, gedcom_tag="ENDL",
        use_value=False, use_date=True, use_place=True, custom=False, code="32",
    ),
    FactDefinition(
        name="LDS Seal to parents", scope=FactScope.PERSON, gedcom_tag="SLGC",
        use_value=False, use_date=True, use_place=True, custom=False, code="33",
    ),
    FactDefinition(
        name="Ancestral File Number", scope=FactScope.PERSON, gedcom_tag="AFN",
        use_value=True, use_date=False, use_place=False, custom=False, code="34",
    ),
    FactDefinition(
        name="Reference No", scope=FactScope.PERSON, gedcom_tag="REFN",
        use_value=True, use_date=False, use_place=False, custom=False, code="35",
    ),
    FactDefinition(
        name="Caste", scope=FactScope.PERSON, gedcom_tag="CAST",
        use_value=True, use_date=True, use_place=True, custom=False, code="36",
    ),
    FactDefinition(
        name="Title (Nobility)", scope=FactScope.PERSON, gedcom_tag="TITL",
        use_value=True, use_date=True, use_place=True, custom=False, code="37",
    ),
    FactDefinition(
        name="LDS Confirmation", scope=FactScope.PERSON, gedcom_tag="CONL",
        use_value=False, use_date=True, use_place=True, custom=False, code="38",
    ),
    FactDefinition(
        name="LDS Initiatory", scope=FactScope.PERSON, gedcom_tag="WAC",
        use_value=False, use_date=True, use_place=True, custom=False, code="39",
    ),
    FactDefinition(
        name="Degree", scope=FactScope.PERSON, gedcom_tag="EVEN",
        use_value=True, use_date=True, use_place=True, custom=False, code="500",
    ),
    FactDefinition(
        name="Military", scope=FactScope.PERSON, gedcom_tag="EVEN",
        use_value=True, use_date=True, use_place=True, custom=False, code="501",
    ),
    FactDefinition(
        name="Mission", scope=FactScope.PERSON, gedcom_tag="EVEN",
        use_value=True, use_date=True, use_place=True, custom=False, code="502",
    ),
    FactDefinition(
        name="Stillborn", scope=FactScope.PERSON, gedcom_tag="EVEN",
        use_value=False, use_date=True, use_place=True, custom=False, code="503",
    ),
    FactDefinition(
        name="Illness", scope=FactScope.PERSON, gedcom_tag="EVEN",
        use_value=True, use_date=True, use_place=True, custom=False, code="504",
    ),
    FactDefinition(
        name="Living", scope=FactScope.PERSON, gedcom_tag="EVEN",
        use_value=False, use_date=True, use_place=True, custom=False, code="505",
    ),
    FactDefinition(
        name="Election", scope=FactScope.PERSON, gedcom_tag="EVEN",
        use_value=True, use_date=True, use_place=True, custom=False, code="507",
    ),
    FactDefinition(
        name="Excommunication", scope=FactScope.PERSON, gedcom_tag="EVEN",
        use_value=False, use_date=True, use_place=True, custom=False, code="508",
    ),
    FactDefinition(
        name="Namesake", scope=FactScope.PERSON, gedcom_tag="EVEN",
        use_value=True, use_date=True, use_place=True, custom=False, code="509",
    ),
    FactDefinition(
        name="Alternate name", scope=FactScope.PERSON, gedcom_tag="EVEN",
        use_value=False, use_date=True, use_place=False, custom=False, code="900",
    ),
    FactDefinition(
        name="DNA test", scope=FactScope.PERSON, gedcom_tag="_DNA",
        use_value=False, use_date=True, use_place=False, custom=False, code="901",
    ),
    FactDefinition(
        name="Association", scope=FactScope.PERSON, gedcom_tag="EVEN",
        use_value=True, use_date=True, use_place=True, custom=False, code="902",
    ),
    FactDefinition(
        name="Miscellaneous", scope=FactScope.PERSON, gedcom_tag="EVEN",
        use_value=True, use_date=True, use_place=True, custom=False, code="999",
    ),
    FactDefinition(
        name="Race", scope=FactScope.PERSON, gedcom_tag="EVEN",
        use_value=True, use_date=True, use_place=False, custom=True, code="10001",
    ),
    FactDefinition(
        name="dit Name", scope=FactScope.PERSON, gedcom_tag="EVEN",
        use_value=True, use_date=True, use_place=True, custom=True, code="10002",
    ),
    FactDefinition(
        name="Scrip", scope=FactScope.PERSON, gedcom_tag="EVEN",
        use_value=True, use_date=True, use_place=True, custom=True, code="10004",
    ),
    FactDefinition(
        name="Marriage", scope=FactScope.FAMILY, gedcom_tag="MARR",
        use_value=False, use_date=True, use_place=True, custom=False, code="300",
    ),
    FactDefinition(
        name="Annulment", scope=FactScope.FAMILY, gedcom_tag="ANUL",
        use_value=False, use_date=True, use_place=True, custom=False, code="301",
    ),
    FactDefinition(
        name="Divorce", scope=FactScope.FAMILY, gedcom_tag="DIV",
        use_value=False, use_date=True, use_place=True, custom=False, code="302",
    ),
    FactDefinition(
        name="Divorce filed", scope=FactScope.FAMILY, gedcom_tag="DIVF",
        use_value=False, use_date=True, use_place=True, custom=False, code="303",
    ),
    FactDefinition(
        name="Engagement", scope=FactScope.FAMILY, gedcom_tag="ENGA",
        use_value=False, use_date=True, use_place=True, custom=False, code="304",
    ),
    FactDefinition(
        name="Marriage Bann", scope=FactScope.FAMILY, gedcom_tag="MARB",
        use_value=False, use_date=True, use_place=True, custom=False, code="305",
    ),
    FactDefinition(
        name="Marriage Contract", scope=FactScope.FAMILY, gedcom_tag="MARC",
        use_value=False, use_date=True, use_place=True, custom=False, code="306",
    ),
    FactDefinition(
        name="Marriage License", scope=FactScope.FAMILY, gedcom_tag="MARL",
        use_value=False, use_date=True, use_place=True, custom=False, code="307",
    ),
    FactDefinition(
        name="Marriage Settlement", scope=FactScope.FAMILY, gedcom_tag="MARS",
        use_value=False, use_date=True, use_place=True, custom=False, code="308",
    ),
    FactDefinition(
        name="LDS Seal to spouse", scope=FactScope.FAMILY, gedcom_tag="SLGS",
        use_value=False, use_date=True, use_place=True, custom=False, code="309",
    ),
    FactDefinition(
        name="Residence (family)", scope=FactScope.FAMILY, gedcom_tag="RESI",
        use_value=True, use_date=True, use_place=True, custom=False, code="310",
    ),
    FactDefinition(
        name="Census (family)", scope=FactScope.FAMILY, gedcom_tag="CENS",
        use_value=False, use_date=True, use_place=True, custom=False, code="311",
    ),
    FactDefinition(
        name="Separation", scope=FactScope.FAMILY, gedcom_tag="EVEN",
        use_value=False, use_date=True, use_place=True, custom=False, code="510",
    ),
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
    source_name: Optional[str] = Field(
        default=None,
        description=(
            "The name of the institution this document is from, if this sheet states it "
            "(e.g. a parish/church's own printed heading or running title), read exactly as "
            "written. Null if this sheet never states it."
        ),
    )
    source_location: Optional[str] = None


class Participant(BaseModel):
    role_number: Optional[str] = Field(
        default=None,
        description=(
            "Leave null. The numeric role code is derived downstream from role_name, "
            "not chosen by you."
        ),
    )
    role_name: Optional[str] = Field(
        description=(
            "Choose exactly one value from this record type's valid role vocabulary, given in "
            "the system instructions. Null only when the source itself provides no "
            "relationship/role data at all for this person (e.g. a pre-1880 US census record) - "
            "never leave null merely because a role is unclear; use \"Other\" for that instead."
        ),
    )
    std_given: str = Field(
        description=(
            "Your best linguistic standardization of the given name, diacritics included. "
            "Diacritic stripping is handled downstream, not by you."
        ),
    )
    std_surname: Optional[str] = Field(
        default=None,
        description=(
            "Your best linguistic standardization of the surname, diacritics included. "
            "Diacritic stripping is handled downstream, not by you."
        ),
    )
    raw_given: Optional[str] = None
    raw_surname: Optional[str] = None
    dit_name: Optional[str] = None
    alternate_names: Optional[List[AlternateName]] = Field(
        default=None,
        description=(
            "A later annotator's marginal note suggesting a different spelling of this person's "
            "name (not the priest's own original entry, and not a disagreement to resolve - both "
            "readings are kept). Leave empty/null if the margin has no such note. Do not use this "
            "for your own uncertainty about the body text's own reading - that's "
            "std_given/std_surname plus review/review_reason."
        ),
    )
    prefix: Optional[str] = None
    suffix: Optional[str] = None
    sex: Literal["M", "F", "U"] = Field(
        description=(
            "Infer from role/given name if not explicitly stated. Use \"U\" only when genuinely "
            "indeterminate (e.g. an unfamiliar name with no role or contextual clue) - never "
            "leave this unset."
        ),
    )
    is_priest: bool
    age: Optional[str] = None
    age_unit: Optional[Literal["years", "months", "days"]] = Field(
        default=None,
        description=(
            "Unit for the age field. Infant baptism/burial ages are often given in months or days "
            "rather than years - set this explicitly whenever age is present; leave both null if "
            "no age is stated."
        ),
    )
    occupation: Optional[str] = None
    race: Optional[str] = None
    religion: Optional[str] = None
    residence: Optional[str] = None
    birth_date: Optional[str] = Field(
        default=None,
        description=(
            "Your best English-language reading of the date exactly as it appears. Final ISO "
            "formatting is handled downstream, not by you."
        ),
    )
    birth_place: Optional[str] = None
    death_date: Optional[str] = Field(
        default=None,
        description=(
            "Your best English-language reading of the date exactly as it appears. Final ISO "
            "formatting is handled downstream, not by you."
        ),
    )
    death_place: Optional[str] = None
    review: bool = Field(
        default=False,
        description=(
            "True if THIS participant's own data (name reading, dates, role assignment, etc.) is "
            "uncertain, guessed, illegible, or otherwise needs a human to double-check it."
        ),
    )
    review_reason: Optional[str] = Field(
        default=None,
        description=(
            "Short plain-English note (under 15 words) explaining why this participant needs "
            "review. Null if review is false."
        ),
    )
    facts: Optional[List[Fact]] = Field(
        default=None,
        description=(
            "Any fact about this participant beyond the fields above, named from this record "
            "type's valid event vocabulary (the same vocabulary event_type is drawn from) - e.g. "
            "an immigration year, a naturalization status. Leave empty/null when nothing beyond "
            "the fields above applies; do not duplicate a fact already covered by a named field "
            "(occupation, birth_date, etc.) here."
        ),
    )
    type_specific_fields: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Additional fields specific to this record type, defined by its .pmt file's front "
            "matter."
        ),
    )


class Record(BaseModel):
    record_id: Optional[str] = Field(
        default=None,
        description=(
            "Leave null. Derived downstream from event_type and record_number, not chosen by you."
        ),
    )
    page: Optional[str] = None
    record_number: Optional[str] = None
    event_type: Optional[str] = Field(
        default=None,
        description=(
            "Choose exactly one value from this record type's valid event vocabulary, given in "
            "the system instructions."
        ),
    )
    year: Optional[str] = None
    event_date: Optional[str] = Field(
        default=None,
        description=(
            "Your best English-language reading of the date exactly as it appears (e.g. "
            "'December 12, 1850'). Final ISO formatting is handled downstream, not by you."
        ),
    )
    event_place: Optional[str] = None
    citation_details: Optional[str] = None
    citation_text: Optional[str] = None
    review: bool = Field(
        default=False,
        description=(
            "True if any part of this record (dates, place, transcription, translation, or any "
            "participant) is uncertain, guessed, illegible, or otherwise needs a human to "
            "double-check it."
        ),
    )
    review_reason: Optional[str] = Field(
        default=None,
        description=(
            "Short plain-English note (under 15 words) explaining why this record needs review. "
            "Null if review is false."
        ),
    )
    continues_on_next_image: bool = Field(
        default=False,
        description=(
            "True ONLY for the LAST record on this image, when its content appears to end "
            "abruptly at the very bottom of the visible page - cut off mid-sentence, no natural "
            "closing or signature - suggesting it continues onto content you cannot see. False "
            "for every other record, and false for the last record too if it has a normal, "
            "complete ending. See UNIVERSAL OUTPUT RULES for how this is used."
        ),
    )
    continues_from_previous_image: bool = Field(
        default=False,
        description=(
            "True ONLY if a 'CONTINUATION FROM PREVIOUS IMAGE' context block was given to you AND "
            "this record's content is what completes it - in that case this must be the FIRST "
            "record you output, containing the FULL merged content (the given prior content plus "
            "what you read here), and record_number/year copied from the given context. False in "
            "every other case, including when no such context was given at all."
        ),
    )
    type_specific_fields: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Additional fields specific to this record type, defined by its .pmt file's front "
            "matter. For a pre-1850 US census record with only a named head of household, this is "
            "also where an unnamed household_tally (age/sex/race bracket counts) belongs - not "
            "fabricated participant entries."
        ),
    )
    participants: List[Participant] = Field(default_factory=list)


class Sheet(BaseModel):
    page_id: Optional[str] = None
    document_metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    records: List[Record] = Field(default_factory=list)


class Collection(BaseModel):
    collection_title: Optional[str] = None
    record_type_name: Optional[str] = None
    collection_metadata: Dict[str, Any] = Field(default_factory=dict)
    sheets: List[Sheet] = Field(default_factory=list)
    model_config = {"extra": "allow"}
