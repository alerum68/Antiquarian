"""
Census.py - Household-grouping and CSV-shaped GEDCOM pipeline for Archivist.
"""

import json
import os
import re
import xml.etree.ElementTree as etree
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TypedDict, Union, cast

import pandas as pd
import Utils

CellValue = Union[str, int, float, bool, None]


class HouseholdUnit(TypedDict):
    """A candidate family unit built up while grouping census household members."""
    husband: Optional[pd.Series]
    wife: Optional[pd.Series]
    children: List[pd.Series]
    anchor: Optional[pd.Series]
    type: str


class FlagRecord(TypedDict):
    """A person flagged for manual review, with the reason and confidence score."""
    person: pd.Series
    reason: str
    confidence: float


# ==========================================
# CONFIGURATION & CONSTANTS
# ==========================================
CALL_NUMBER = ""
REPOSITORY = ""
REPOSITORY_LOC = ""
COLLECTION_URL = ""
COLLECTION_NAME = ""
# Derived from Country column in run_census_flavor()
COUNTRY = ""
# Display fallback when COLLECTION_NAME is missing
DEFAULT_COLLECTION_NAME = ""
PUBLISHER = ""
PUB_LOC = ""

IMAGE_DIR = Utils.safe_path(Utils.GENEALOGY_DIR, os.getenv("MEDIA_DIR", "Media"), "Census")
IMAGE_EXTENSION = "jpg"
FORM_TYPE = IMAGE_EXTENSION

CENSUS_YEAR = Utils.get_env_int("CENSUS_YEAR", 0)
ANCESTRY_START_RECORD_ID = Utils.get_env_int("ANCESTRY_START_RECORD_ID", 0)
APID_DB = ""
ANCESTRY_IMAGE_BASE_ID = ""
BASE_ID = ANCESTRY_IMAGE_BASE_ID.rstrip('_-')
STATE = ""
COUNTY = ""
TOWNSHIP = ""
ENUMERATION_DISTRICT = ""
FILM_NUMBER = ""
ROLL_NUMBER = ""
MIN_MARRIAGE_AGE = 12
MAX_SPOUSE_AGE_GAP = 25
HUSBAND_CHILD_AGE_GAP = (14, 60)
WIFE_CHILD_AGE_GAP = (12, 50)
REVIEW_THRESHOLD = 0.6


def get_census_era(year: int) -> str:
    if year <= 1840:
        return "pre1850"
    if year <= 1870:
        return "heuristic"
    return "relationship"


CENSUS_TEMPLATES = {47: {"schedule": False, "ed": False, "household": False},   # 1790-1840 (Filmed)
                    48: {"schedule": True, "ed": False, "household": True},    # 1850-1870 (Filmed)
                    49: {"schedule": True, "ed": True, "household": True}}     # 1880-1930 (Filmed), reused 1940+


def get_census_template_id(year: int) -> int:
    if year <= 1840:
        return 47
    if year <= 1870:
        return 48
    return 49


CENSUS_ERA = get_census_era(CENSUS_YEAR)
CENSUS_SOURCE_ID = Utils.resolve_source_id(f"Census_{CENSUS_YEAR}") if CENSUS_YEAR else Utils.NEXT_AUTO_SOURCE_ID


def get_gender(val: Union[pd.Series, dict, CellValue]) -> str:
    if isinstance(val, (pd.Series, dict)):
        str_val = Utils.clean_val(val.get("Gender", ""))
    else:
        str_val = Utils.clean_val(val)
    if not str_val:
        return "U"
    v = str_val.upper()
    if v.startswith(("M", "MALE")):
        return "M"
    elif v.startswith(("F", "FEMALE")):
        return "F"
    return "U"


# noinspection DuplicatedCode
def evaluate_task_priority(task_note: str) -> tuple:
    """Evaluates task notes for keywords to assign a priority, color code, and dynamic folder name."""
    task_note_lower = f"{task_note}".lower()

    rules = [
        (["conflict", "error", "mismatch", "discrepancy", "inconsistent", "contradict", "wrong"],
            1, "1", "Data Conflicts & Errors"),
        (["illegible", "unreadable", "hard to read", "faded", "damaged", "torn", "blot", "margin", "ink"],
            1, "1", "Legibility & Record Condition"),
        (["surname", "given name", "blank name", "no name", "unknown name", "alias", "dit name", "spelling",
          "identity"],
            1, "1", "Name & Identity Issues"),
        (["parent", "father", "mother", "sponsor", "godparent", "witness", "spouse", "bride", "groom", "relationship",
          "unknown parents"],
            2, "2", "Relationship & Participant Issues"),
        (["translate", "translation", "latin", "french", "language"],
            2, "2", "Translation Needed"),
        (["date", "year", "month", "day", "invalid", "chronology", "sequence", "estimated", "calculated", "age",
          "born"],
            3, "3", "Date & Chronology Issues"),
    ]

    for keywords, priority, color, folder in rules:
        if any(kw in task_note_lower for kw in keywords):
            return priority, color, folder

    return 3, "3", "General Review"


# noinspection DuplicatedCode
def _rmst_element_to_gedcom(elem: etree.Element) -> List[str]:
    """Converts a <Template> XML element into RootsMagic GEDCOM 0 _SRCTEMPLATE lines."""
    tid = elem.get("Id", "")
    name = (elem.findtext("Name") or "").strip()
    desc = (elem.findtext("Description") or "").strip()
    cat = (elem.findtext("Category") or "Simplified Citations for Genealogical Sources").strip()
    foot = (elem.findtext("Footnote") or "").strip()
    short = (elem.findtext("ShortFootnote") or "").strip()
    bibl = (elem.findtext("Bibliography") or "").strip()

    lines = [f"0 _SRCTEMPLATE {name}", f"1 TID {tid}"]
    if desc:
        lines.append(f"1 DESC {desc}")
    if cat:
        lines.append(f"1 CAT {cat}")
    if foot:
        lines.append(f"1 FOOT {foot}")
    if short:
        lines.append(f"1 SHORT {short}")
    if bibl:
        lines.append(f"1 BIBL {bibl}")

    for fld in elem.findall("Field"):
        f_type = (fld.findtext("Type") or "Text").strip()
        f_name = (fld.findtext("Name") or "").strip()
        f_disp = (fld.findtext("Display") or "").strip()
        f_hint = (fld.findtext("Hint") or "").strip()
        f_detl = "Y" if (fld.findtext("Detail") or "False").strip().lower() in ("true", "1", "y") else "N"
        f_lhnt = (fld.findtext("LongHint") or "").strip()

        lines.append("1 FIELD")
        lines.append(f"2 TYPE {f_type}")
        lines.append(f"2 NAME {f_name}")
        if f_disp:
            lines.append(f"2 DISP {f_disp}")
        if f_hint:
            lines.append(f"2 HINT {f_hint}")
        lines.append(f"2 DETL {f_detl}")
        if f_lhnt:
            lines.append(f"2 LHNT {f_lhnt}")
    return lines


_BUILTIN_SOURCE_TEMPLATES: Dict[int, List[str]] = {}


def load_source_template_lines(template_id: int) -> List[str]:
    """Finds and parses the given template ID from any .rmst files in Archivist or DEV,
    or falls back to the embedded _BUILTIN_SOURCE_TEMPLATES."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    archivist_dir = os.path.dirname(os.path.abspath(__file__))
    candidate_dirs = [
        os.path.join(archivist_dir, "Source Templates"),
        os.path.join(base_dir, "DEV", "Source Templates"),
        os.path.join(base_dir, "DEV"),
    ]
    for cdir in candidate_dirs:
        if os.path.isdir(cdir):
            for fname in os.listdir(cdir):
                if fname.endswith(".rmst"):
                    fpath = os.path.join(cdir, fname)
                    try:
                        tree = etree.parse(fpath)
                        root = tree.getroot()
                        elem = root.find(f".//Template[@Id='{template_id}']")
                        if elem is not None:
                            return _rmst_element_to_gedcom(elem)
                    except (etree.ParseError, OSError):
                        continue
    return _BUILTIN_SOURCE_TEMPLATES.get(template_id, [])


def get_source_templates(template_ids_used: set) -> List[str]:
    """Generates 0 _SRCTEMPLATE GEDCOM blocks for all referenced template IDs."""
    lines = []
    for tid in sorted(template_ids_used):
        t_lines = load_source_template_lines(tid)
        if t_lines:
            lines.extend(t_lines)
    return lines


# ==========================================
# CENSUS FLAVOR: HOUSEHOLD GROUPING
# ==========================================
def get_age(row: pd.Series) -> float:
    def parse_num(val: CellValue) -> Optional[float]:
        try:
            if pd.notna(val) and val is not None:
                val_str = str(val).strip()
                if val_str:
                    return float(val_str)
        except ValueError:
            pass
        return None

    b_yr = parse_num(row.get('Birth Year'))
    if b_yr is not None:
        return float(CENSUS_YEAR) - b_yr

    age = parse_num(row.get('Age'))
    return age if age is not None else -1.0


def evaluate_spouse_match(a: pd.Series, b: pd.Series) -> Tuple[bool, float, str]:
    g_a = get_gender(a.get('Gender', ''))
    g_b = get_gender(b.get('Gender', ''))
    if 'U' in (g_a, g_b) or g_a == g_b:
        return False, 0.0, "gender mismatch or unknown"
    age_a, age_b = get_age(a), get_age(b)
    if (age_a != -1 and age_a < MIN_MARRIAGE_AGE) or (age_b != -1 and age_b < MIN_MARRIAGE_AGE):
        return False, 0.0, "below minimum marriage age"
    if age_a != -1 and age_b != -1 and abs(age_a - age_b) >= MAX_SPOUSE_AGE_GAP:
        return False, 0.0, "spousal age gap too large"
    sur_a, sur_b = Utils.clean_val(a.get('Surname')), Utils.clean_val(b.get('Surname'))
    if sur_a and sur_b:
        if sur_a == sur_b:
            return True, 0.9, "matching surnames"
        else:
            return False, 0.0, "surnames differ"
    return True, 0.4, "surname missing for one party -- unverified pairing"


def evaluate_child_match(unit: HouseholdUnit, member: pd.Series) -> Tuple[bool, float, str]:
    h = unit.get('husband')
    w = unit.get('wife')
    if h is None and w is None:
        return False, 0.0, "no parents in unit"
    m_age = get_age(member)
    m_sur = Utils.clean_val(member.get('Surname'))
    if h is not None:
        u_sur = Utils.clean_val(h.get('Surname'))
    else:
        assert w is not None  # guaranteed: the check above ruled out both being None
        u_sur = Utils.clean_val(w.get('Surname'))
    if m_sur and u_sur and m_sur != u_sur:
        return False, 0.0, "surname mismatch"
    surname_conf = 0.9 if (m_sur and u_sur and m_sur == u_sur) else 0.5
    if m_age == -1:
        return True, min(surname_conf, 0.5), "no age data for child -- unverified"

    def in_rng(parent: Optional[pd.Series], gap_rng: Tuple[int, int]) -> Optional[bool]:
        if parent is None:
            return None
        p_age = get_age(parent)
        if p_age != -1:
            return gap_rng[0] <= (p_age - m_age) <= gap_rng[1]
        return None

    checks = []
    h_check = in_rng(h, HUSBAND_CHILD_AGE_GAP)
    if h_check is not None:
        checks.append(h_check)
    w_check = in_rng(w, WIFE_CHILD_AGE_GAP)
    if w_check is not None:
        checks.append(w_check)

    if checks:
        if not any(checks):
            return False, 0.0, "age gap outside plausible range for both parents"
        if not all(checks):
            surname_conf = min(surname_conf, 0.8)
    return True, surname_conf, "age and surname consistent with parentage"


def find_parent(units: List[HouseholdUnit], member: pd.Series) -> Optional[Tuple[int, float, str]]:
    best: Optional[Tuple[int, float, str]] = None
    for i in range(len(units) - 1, -1, -1):
        plausible, match_conf, match_rsn = evaluate_child_match(units[i], member)
        if plausible:
            if best is None:
                best = (i, match_conf, match_rsn)
            else:
                _, best_conf, _ = best
                if match_conf > best_conf:
                    best = (i, match_conf, match_rsn)
    return best


def parse_household(group: pd.DataFrame) -> Tuple[List[HouseholdUnit], List[pd.Series], List[FlagRecord]]:
    members = [row for _, row in group.iterrows()]
    n = len(members)
    flags: List[FlagRecord] = []
    units: List[HouseholdUnit] = []
    unrelated: List[pd.Series] = []
    consumed = set()

    def add_flag(p: pd.Series, flag_reason: str, flag_conf: float) -> None:
        if flag_conf < REVIEW_THRESHOLD:
            flags.append({'person': p, 'reason': flag_reason, 'confidence': flag_conf})

    for person in members:
        merge_reason = Utils.clean_val(person.get('_MergeReviewReason'))
        if merge_reason:
            add_flag(person, merge_reason, 0.0)

    def make_unit(mem1: pd.Series, mem2: Optional[pd.Series] = None,
                  anchor_person: Optional[pd.Series] = None) -> HouseholdUnit:
        m1_gen = get_gender(mem1)
        h_unit, w_unit = (None, mem1) if m1_gen == 'F' else (mem1, None)
        if mem2 is not None:
            h_unit, w_unit = (mem2, mem1) if m1_gen == 'F' else (mem1, mem2)
        return {'husband': h_unit, 'wife': w_unit, 'children': [], 'anchor': anchor_person, 'type': 'main'}

    if not members:
        return units, unrelated, flags

    head = members[0]
    i = 1
    if n > 1:
        sp_mem = members[1]
        plausible, sp_conf, sp_reason = evaluate_spouse_match(head, sp_mem)
        head_gender = get_gender(head)
        sp_gender = get_gender(sp_mem)
        if not plausible and head_gender != sp_gender and 'U' not in (head_gender, sp_gender):
            sp_age = get_age(sp_mem)
            if sp_age != -1 and any(get_age(x) > sp_age for x in members[2:]):
                plausible, sp_conf, sp_reason = True, 0.8, "step-parent pattern"
        if plausible:
            units.append(make_unit(head, sp_mem))
            add_flag(sp_mem, f"Possible spouse: {sp_reason}", sp_conf)
            consumed.update({0, 1})
            i = 2

    if 0 not in consumed:
        units.append(make_unit(head))
        consumed.add(0)

    while i < n:
        if i in consumed:
            i += 1
            continue
        m = members[i]
        if i + 1 < n and (i + 1) not in consumed:
            nxt = members[i + 1]
            sub_plausible, sub_sp_conf, sub_sp_reason = evaluate_spouse_match(m, nxt)
            if sub_plausible:
                fit_m = find_parent(units, m)
                fit_nxt = find_parent(units, nxt)
                m_is_child = False
                m_unit_idx = -1
                if fit_m is not None:
                    m_unit_idx, m_conf, _ = fit_m
                    m_is_child = (m_conf >= REVIEW_THRESHOLD)
                nxt_is_child = False
                if fit_nxt is not None:
                    _, nxt_conf, _ = fit_nxt
                    nxt_is_child = (nxt_conf >= REVIEW_THRESHOLD)

                if m_is_child and nxt_is_child:
                    m_unit = units[m_unit_idx]
                    last_c_age = -1.0
                    if m_unit['children']:
                        last_c_age = get_age(m_unit['children'][-1])
                    m_age = get_age(m)
                    if last_c_age != -1 and m_age != -1 and m_age > last_c_age and m_age >= MIN_MARRIAGE_AGE:
                        anc_member = m if Utils.clean_val(
                            m.get('Surname')) == Utils.clean_val(head.get('Surname')) else nxt
                        units[m_unit_idx]['children'].append(anc_member)
                        units.append(make_unit(m, nxt, anchor_person=anc_member))
                        flagged_person = nxt if anc_member is m else m
                        add_flag(flagged_person, "Paired as spouse due to age-sequence break.", 0.5)
                    else:
                        units[m_unit_idx]['children'].extend([m, nxt])
                    consumed.update({i, i + 1})
                    i += 2
                    continue
                elif m_is_child or nxt_is_child:
                    if m_is_child and fit_m is not None:
                        anc_member = m
                        anchor_idx, anchor_conf, anchor_rsn = fit_m
                    elif fit_nxt is not None:
                        anc_member = nxt
                        anchor_idx, anchor_conf, anchor_rsn = fit_nxt
                    else:
                        continue

                    units[anchor_idx]['children'].append(anc_member)
                    add_flag(anc_member, f"Possible child: {anchor_rsn}", anchor_conf)
                    units.append(make_unit(m, nxt, anchor_person=anc_member))
                    consumed.update({i, i + 1})
                    i += 2
                    continue
                else:
                    units.append(make_unit(m, nxt))
                    add_flag(nxt, f"Possible spouse (separate family unit): {sub_sp_reason}", sub_sp_conf)
                    consumed.update({i, i + 1})
                    i += 2
                    continue

        match = find_parent(units, m)
        if match:
            idx, match_conf, match_rsn = match
            units[idx]['children'].append(m)
            add_flag(m, f"Possible child: {match_rsn}", match_conf)
        else:
            m_sur = Utils.clean_val(m.get('Surname'))
            h_sur = Utils.clean_val(head.get('Surname'))
            if m_sur == h_sur and m_sur:
                units[0]['children'].append(m)
                add_flag(m, "Head-surname match; no age fit", 0.3)
            else:
                unrelated.append(m)
                add_flag(m, "Unrelated household member", 0.2)
        consumed.add(i)
        i += 1

    return units, unrelated, flags


# ==========================================
# CENSUS FLAVOR: RELATIONSHIP-COLUMN GROUPING
# ==========================================
RELATIONSHIP_COLUMN_CANDIDATES = ('Relationship to Head', 'Relationship', 'Relation to Head', 'Relation')
REL_HEAD = {'head', 'head of household', 'head of family', 'self', 'self head', 'housekeeper', 'partner'}
REL_SPOUSE = {'wife', 'husband', 'spouse'}
REL_CHILD = {'son', 'daughter', 'child', 'stepson', 'stepdaughter', 'step son', 'step daughter', 'adopted son',
             'adopted daughter', 'foster son', 'foster daughter'}
REL_SIBLING = {'brother', 'sister', 'half brother', 'half sister', 'stepbrother', 'stepsister', 'step brother',
               'step sister'}
REL_PARENT = {'father', 'mother', 'stepfather', 'stepmother', 'step father', 'step mother'}
REL_INLAW_SIBLING = {'brother in law', 'sister in law'}
REL_INLAW_PARENT = {'father in law', 'mother in law'}
REL_INLAW_CHILD = {'son in law', 'daughter in law'}
REL_GRANDCHILD = {'grandson', 'granddaughter', 'grandchild', 'great grandson', 'great granddaughter',
                  'great grandchild', 'step grandson', 'step granddaughter'}
REL_NIBLING = {'nephew', 'niece'}


def normalize_relationship(val: CellValue) -> str:
    v = Utils.clean_val(val).lower()
    v = v.replace('-', ' ')
    v = re.sub(r'[^a-z ]', '', v)
    return re.sub(r'\s+', ' ', v).strip()


def is_relationship_column(col_name: str) -> bool:
    norm = re.sub(r'[^a-z]', '', col_name.lower())
    return ('relation' in norm) and ('head' in norm)


def find_relationship_column(columns: Union[pd.Index, List[str]]) -> Optional[str]:
    exact = next((c for c in RELATIONSHIP_COLUMN_CANDIDATES if c in columns), None)
    if exact:
        return exact
    return next((c for c in columns if is_relationship_column(str(c))), None)


def resolve_cross_family_links(
        units: List[HouseholdUnit], unrelated: List[pd.Series], flags: List[FlagRecord]
) -> Tuple[List[HouseholdUnit], List[pd.Series], List[FlagRecord]]:
    for unit in units:
        if unit.get('type') == 'spouse_parents':
            wife = unit.get('anchor')
            if wife is None or not isinstance(wife, pd.Series):
                continue

            unit_children = unit.get('children')
            if not isinstance(unit_children, list):
                continue

            siblings = [c for c in unit_children if c is not wife]
            if not siblings or not isinstance(siblings[0], pd.Series):
                continue

            maiden_surname = Utils.clean_val(siblings[0].get('Surname'))
            if not maiden_surname:
                continue

            wife_age = get_age(wife)

            plausible_parent_unit = None
            parent_name = ""
            for other_unit in units:
                if other_unit is unit:
                    continue

                for pp, age_gap_range in (
                    (other_unit.get('husband'), HUSBAND_CHILD_AGE_GAP),
                    (other_unit.get('wife'), WIFE_CHILD_AGE_GAP),
                ):
                    if isinstance(pp, pd.Series):
                        pp_sur = Utils.clean_val(pp.get('Surname'))
                        pp_age = get_age(pp)

                        if pp_sur == maiden_surname:
                            if pp_age == -1 or wife_age == -1 or (
                                    age_gap_range[0] <= (pp_age - wife_age) <= age_gap_range[1]):
                                plausible_parent_unit = other_unit
                                parent_name = Utils.clean_val(pp.get('Given Name'))
                                break
                if plausible_parent_unit:
                    break

            if plausible_parent_unit:
                parent_children = plausible_parent_unit.get('children')
                if isinstance(parent_children, list):
                    if not any(wife is c for c in parent_children):
                        parent_children.append(wife)
                        flags.append({'person': wife,
                                      'reason': f"Inferred as child of {parent_name} {maiden_surname} via in-law links",
                                      'confidence': 0.85})

                    for sib in siblings:
                        if not any(sib is c for c in parent_children):
                            parent_children.append(sib)
                            flags.append({'person': sib,
                                          'reason': f"Inferred as child of {parent_name} {maiden_surname} via "
                                          f"sibling link to head's spouse",
                                          'confidence': 0.85})

                unit['children'] = [c for c in unit_children if c is not wife and c not in siblings]
                if unit.get('husband') is None and unit.get('wife') is None and not unit.get('children'):
                    unit['type'] = 'merged'

    units = [u for u in units if u.get('type') != 'merged']
    return units, unrelated, flags


def append_unit_if_not_empty(units: List[HouseholdUnit], unit: Optional[HouseholdUnit]) -> None:
    if unit and (unit['husband'] is not None or unit['wife'] is not None or len(unit['children']) > 1):
        units.append(unit)


def parse_household_relational(
        group: pd.DataFrame) -> Tuple[List[HouseholdUnit], List[pd.Series], List[FlagRecord]]:
    rel_col = find_relationship_column(group.columns)
    if rel_col is None:
        return parse_household(group)

    has_head = any(normalize_relationship(m.get(rel_col, '')) in REL_HEAD for _, m in group.iterrows())
    if not has_head:
        return parse_household(group)

    flags: List[FlagRecord] = []
    unrelated: List[pd.Series] = []
    units: List[HouseholdUnit] = []

    for _, m in group.iterrows():
        merge_reason = Utils.clean_val(m.get('_MergeReviewReason'))
        if merge_reason:
            flags.append({'person': m, 'reason': merge_reason, 'confidence': 0.0})

    current_unit: Optional[HouseholdUnit] = None
    primary_head: Optional[pd.Series] = None
    primary_spouse: Optional[pd.Series] = None
    last_child_inlaw_unit: Optional[HouseholdUnit] = None

    head_parents_unit: Optional[HouseholdUnit] = None
    spouse_parents_unit: Optional[HouseholdUnit] = None

    for _, m in group.iterrows():
        rel = normalize_relationship(m.get(rel_col, ''))

        if rel in REL_HEAD or current_unit is None or head_parents_unit is None or spouse_parents_unit is None:
            append_unit_if_not_empty(units, current_unit)
            append_unit_if_not_empty(units, head_parents_unit)
            append_unit_if_not_empty(units, spouse_parents_unit)

            current_unit = {'husband': None, 'wife': None, 'children': [], 'anchor': m, 'type': 'main'}
            head_parents_unit = {'husband': None, 'wife': None, 'children': [], 'anchor': m, 'type': 'head_parents'}
            spouse_parents_unit = {'husband': None, 'wife': None, 'children': [], 'anchor': None,
                                   'type': 'spouse_parents'}

            primary_head = None
            primary_spouse = None
            last_child_inlaw_unit = None

            if rel in REL_HEAD:
                if current_unit is not None:
                    if get_gender(m) == 'F':
                        current_unit['wife'] = m
                    else:
                        current_unit['husband'] = m

                primary_head = m
                if head_parents_unit is not None:
                    head_children = head_parents_unit.get('children')
                    if isinstance(head_children, list):
                        head_children.append(m)
            else:
                unrelated.append(m)
                flags.append(
                    {'person': m, 'reason': f"First person in household not listed as Head (rel: {rel.title()})",
                     'confidence': 0.3})
            continue

        if rel in REL_SPOUSE and current_unit is not None:
            if get_gender(m) == 'F':
                current_unit['wife'] = m
            else:
                current_unit['husband'] = m

            if primary_spouse is None and primary_head is not None and spouse_parents_unit is not None:
                primary_spouse = m
                spouse_parents_unit['anchor'] = m
                spouse_children = spouse_parents_unit.get('children')
                if isinstance(spouse_children, list):
                    spouse_children.append(m)

        elif rel in REL_CHILD and current_unit is not None:
            curr_children = current_unit.get('children')
            if isinstance(curr_children, list):
                curr_children.append(m)

        elif rel in REL_INLAW_CHILD and current_unit is not None:
            spouse_candidate = None
            h_sub: Optional[pd.Series]
            w_sub: Optional[pd.Series]
            m_gender = get_gender(m)
            target_gender = 'F' if m_gender == 'M' else ('M' if m_gender == 'F' else None)

            curr_children = current_unit.get('children')
            if isinstance(curr_children, list):
                for child in reversed(curr_children):
                    if target_gender is None or get_gender(child) == target_gender:
                        spouse_candidate = child
                        break

            if spouse_candidate is not None:
                h_sub = m if m_gender == 'M' else spouse_candidate
                w_sub = spouse_candidate if m_gender == 'M' else m
                last_child_inlaw_unit = {'husband': h_sub, 'wife': w_sub, 'children': [], 'anchor': m, 'type': 'sub'}
                units.append(last_child_inlaw_unit)
                flags.append({'person': m, 'reason': f"Paired as in-law spouse in sub-family (rel: {rel.title()})",
                              'confidence': 0.8})
            else:
                h_sub = m if m_gender == 'M' else None
                w_sub = None if m_gender == 'M' else m
                last_child_inlaw_unit = {'husband': h_sub, 'wife': w_sub, 'children': [], 'anchor': m, 'type': 'sub'}
                units.append(last_child_inlaw_unit)
                flags.append(
                    {'person': m, 'reason': f"In-law listed without matching spouse child (rel: {rel.title()})",
                     'confidence': 0.5})

        elif rel in REL_GRANDCHILD and current_unit is not None:
            if last_child_inlaw_unit is not None:
                last_children = last_child_inlaw_unit.get('children')
                if isinstance(last_children, list):
                    last_children.append(m)
            else:
                curr_children = current_unit.get('children')
                if isinstance(curr_children, list):
                    curr_children.append(m)
                flags.append({'person': m, 'reason': f"Grandchild attached to head family unit (rel: {rel.title()})",
                              'confidence': 0.6})

        elif rel in REL_SIBLING and primary_head is not None and head_parents_unit is not None:
            head_children = head_parents_unit.get('children')
            if isinstance(head_children, list):
                head_children.append(m)

        elif rel in REL_PARENT and primary_head is not None and head_parents_unit is not None:
            if get_gender(m) == 'F':
                head_parents_unit['wife'] = m
            else:
                head_parents_unit['husband'] = m

        elif rel in REL_INLAW_SIBLING and primary_spouse is not None and spouse_parents_unit is not None:
            spouse_children = spouse_parents_unit.get('children')
            if isinstance(spouse_children, list):
                spouse_children.append(m)

        elif rel in REL_INLAW_PARENT and primary_spouse is not None and spouse_parents_unit is not None:
            if get_gender(m) == 'F':
                spouse_parents_unit['wife'] = m
            else:
                spouse_parents_unit['husband'] = m

        elif rel in REL_NIBLING and current_unit is not None:
            curr_children = current_unit.get('children')
            if isinstance(curr_children, list):
                curr_children.append(m)
            flags.append({'person': m, 'reason': f"Niece/Nephew attached to household unit (rel: {rel.title()})",
                          'confidence': 0.5})

        elif rel:
            unrelated.append(m)
            flags.append({'person': m,
                          'reason': f"Stated relationship to head: {rel.title()} -- review for correct "
                          f"family placement",
                          'confidence': 0.5})
        else:
            unrelated.append(m)
            flags.append({'person': m, 'reason': "No relationship-to-head recorded -- review household placement",
                          'confidence': 0.2})

    append_unit_if_not_empty(units, current_unit)
    append_unit_if_not_empty(units, head_parents_unit)
    append_unit_if_not_empty(units, spouse_parents_unit)

    return resolve_cross_family_links(units, unrelated, flags)


# ==========================================
# CENSUS FLAVOR: GEDCOM EMISSION
# ==========================================
def get_row_val(r: pd.Series, cols: List[str], default: str) -> str:
    if default:
        return default
    for c in cols:
        if c in r.index:
            val = Utils.clean_val(r.get(c))
            if val:
                return val
    return ""


ARK_TYPE_PREFIX_RE = re.compile(r'^\d+:\d+:')


def strip_ark_type_prefix(value: str) -> str:
    """Strips a leading GEDCOM X type/version prefix (e.g. '1:1:' on a FamilySearch person
    ark, '3:1:' on a page-level record ark) for display in fields where only the bare
    identifier reads cleanly (REFN, a citation-level FSFTID) - the prefix is still required
    where it's functionally load-bearing (the clickable FamilySearch URL itself, and the
    media FILE path, which must match the real saved filename) and those call sites must
    NOT use this. A no-op on values with no such prefix (e.g. Ancestry's own numeric/
    synthesized rec_id), so it's safe to apply without checking the source first."""
    return ARK_TYPE_PREFIX_RE.sub('', str(value or ''))


def build_census_citation(row: pd.Series, rec_id: str, m_id: str, real_page: str, target_software: str,
                          row_town: str, row_county: str, row_state: str, row_roll: str, row_film: str,
                          row_ed: str = "") -> List[str]:
    giv = Utils.clean_val(row.get('Given Name'))
    sur = Utils.clean_val(row.get('Surname'))
    person_str = f"{giv} {sur}".strip()

    fam_num = get_row_val(row, ['Family Number', 'Family', 'Household Number', 'Household'], '')
    dwell_num = get_row_val(row, ['Dwelling Number', 'Dwelling', 'House Number'], '')

    fsftid = get_row_val(row, ['FSFTID'], '')
    fs_url = get_row_val(row, ['FamilySearch_URL'], '')
    # Prefer existing FSFTID; otherwise, use record ark for FS-sourced records
    citation_fsftid = fsftid or (strip_ark_type_prefix(rec_id) if fs_url else '')

    ancestry_url = get_row_val(row, ['Extracted_URL'], '') or (
        f"https://www.ancestry.com/search/collections/{APID_DB}/records/{rec_id}"
        if (APID_DB and rec_id) else "")

    cit = [f"2 SOUR @S{CENSUS_SOURCE_ID}@"]

    caps = CENSUS_TEMPLATES[get_census_template_id(CENSUS_YEAR)]
    ed_suffix = f", ED {row_ed}" if (caps["ed"] and row_ed) else ""
    row_loc = ", ".join(filter(None, [row_town, row_county, row_state]))

    if target_software == "RM":
        page_parts = [row_roll, f"{row_town}{ed_suffix}", real_page]
        if caps["household"]:
            page_parts.append(fam_num)
        page_parts.append(person_str)

        collection_title = COLLECTION_NAME or DEFAULT_COLLECTION_NAME
        cit.append(f"3 PAGE {'; '.join(filter(None, page_parts))}")

        detail_fields = [
            ("Page", f"p. {real_page}" if real_page else ""),
            ("SourceDetailPerson", person_str),
            ("Location", row_loc),
            ("CensusED", row_ed),
            ("HouseholdID", f"dwelling {dwell_num}, family {fam_num}" if (dwell_num and fam_num)
             else (fam_num or dwell_num)),
            ("Repository", "Ancestry.com" if not fs_url else "FamilySearch"),
            ("URL", ancestry_url),
            ("RefNumber", f"APID 1,{APID_DB}::{rec_id}" if (APID_DB and rec_id) else ""),
        ]
        for f_name, f_val in detail_fields:
            if f_val:
                cit.extend(["3 FIELD", f"4 NAME {f_name}", f"4 VALUE {f_val}"])

        cit.append("3 DATA")
        if APID_DB and rec_id:
            cit.extend([f"3 _APID 1,{APID_DB}::{rec_id}", "3 _WEBTAG",
                        f"4 NAME Anc- {collection_title}",
                        f"4 URL {ancestry_url}"])
        if citation_fsftid:
            cit.append(f"1 _FSFTID {citation_fsftid}")
        if fs_url:
            cit.extend(["3 _WEBTAG",
                        f"4 NAME FS- {collection_title}",
                        f"4 URL {fs_url}"])
        cit.extend(["3 QUAY 3", "3 _QUAL", "4 _SOUR O", "4 _INFO P", "4 _EVID D"])
        cit.append(f"3 OBJE {m_id}")
    else:
        link_url = ancestry_url
        cit.append(
            f"3 PAGE {person_str}; p. {real_page}, dwell. {dwell_num}, fam. {fam_num}; {row_town}{ed_suffix}; "
            f"{row_county}; {row_state}; Roll {row_roll}; Film {row_film}")
        cit.append("3 QUAY 3")
        if APID_DB and rec_id:
            cit.extend([f"3 _APID 1,{APID_DB}::{rec_id}", f"3 _LINK {link_url}", f"3 NOTE {link_url}"])
        if citation_fsftid:
            cit.append(f"1 _FSFTID {citation_fsftid}")
        if fs_url:
            cit.extend([f"3 _LINK {fs_url}", f"3 NOTE {fs_url}"])
        cit.append(f"3 OBJE {m_id}")
    return cit


def get_census_notes(row: pd.Series) -> List[str]:
    note_cols = ['Quality', 'Real Estate Value', 'Personal Estate Value', 'Cannot Read, Write', 'Disability Condition',
                 'Deaf Dumb Blind Insane', 'Idiotic Pauper Convict']
    notes = [f"{c}: {Utils.clean_val(row[c])}" for c in note_cols if c in row and Utils.clean_val(row[c])]
    if CENSUS_YEAR == 1870:
        flags = {'Father Foreign Born': "Father of foreign birth.", 'Mother Foreign Born': "Mother of foreign birth.",
                 'Male Citizen Over 21': "Male citizen of the United States of 21 years of age and upwards.",
                 'Voting Rights Denied': "Male citizen of 21 years of age and upwards whose right to vote is "
                                         "denied or abridged on grounds other than rebellion or other crime."}
        notes.extend([msg for flag_col, msg in flags.items() if Utils.clean_val(row.get(flag_col))])
    return notes


CORE_COLUMNS = {'given name', 'surname', 'gender', 'sex', 'age', 'birth year', 'birth month', 'month of birth', 'page',
                'page_number', 'real page', 'real_page', 'family number', 'household number', 'family', 'household',
                'dwelling number', 'dwelling', 'line number', 'line', 'household_id', 'row_index_id', 'birth place',
                'birthplace', 'occupation', 'occupation category', 'industry', 'trade or profession',
                'usual occupation', 'employer', 'class of worker', 'hours worked', 'weeks worked',
                'months unemployed past year', 'out of work', 'seeking work', 'race', 'color',
                'nationality', 'attended school', 'highest grade of school completed', 'highest grade completed',
                'married within year', 'relationship to head', 'relationship', 'relation to head', 'relation',
                'quality', 'real estate value', 'personal estate value', 'cannot read, write', 'disability condition',
                'deaf dumb blind insane', 'idiotic pauper convict', 'father foreign born', 'mother foreign born',
                'male citizen over 21', 'voting rights denied', 'image_id', 'country', 'state', 'county', 'city',
                'place_details', 'roll', 'film', 'enumeration_district', 'apid_db', 'extracted_url', 'pid', 'street',
                'street address', 'address', 'house number', 'publisher', 'publisher location',
                'repository', 'repository location', 'fsftid', 'familysearch_url', 'alternatenames',
                'alternatebirthplaces', '_mergereviewreason'}

DYNAMIC_EVENT_RULES = [(re.compile(r'immigrat', re.I), 'IMMI'),
                       (re.compile(r'year of naturali[sz]', re.I), 'NATU_DATE'),
                       (re.compile(r'naturali[sz]ation status|^naturali[sz]', re.I), 'NATU'),
                       (re.compile(r'veteran|military|regiment|survivor of union|confederate|which war|pension', re.I),
                        'MILITARY'), (re.compile(r'residence', re.I), 'RESI'),
                       (re.compile(r'religio|church affiliation', re.I), 'RELI'),
                       (re.compile(r'maiden name', re.I), 'MAIDEN')]

PRE1850_ALLOWED_TAGS = {'MILITARY'}
MONTH_ABBR = {'1': 'JAN', '01': 'JAN', 'JAN': 'JAN', 'JANUARY': 'JAN', '2': 'FEB', '02': 'FEB', 'FEB': 'FEB',
              'FEBRUARY': 'FEB', '3': 'MAR', '03': 'MAR', 'MAR': 'MAR', 'MARCH': 'MAR', '4': 'APR', '04': 'APR',
              'APR': 'APR', 'APRIL': 'APR', '5': 'MAY', '05': 'MAY', 'MAY': 'MAY', '6': 'JUN', '06': 'JUN',
              'JUN': 'JUN', 'JUNE': 'JUN', '7': 'JUL', '07': 'JUL', 'JUL': 'JUL', 'JULY': 'JUL', '8': 'AUG',
              '08': 'AUG', 'AUG': 'AUG', 'AUGUST': 'AUG', '9': 'SEP', '09': 'SEP', 'SEP': 'SEP', 'SEPT': 'SEP',
              'SEPTEMBER': 'SEP', '10': 'OCT', 'OCT': 'OCT', 'OCTOBER': 'OCT', '11': 'NOV', 'NOV': 'NOV',
              'NOVEMBER': 'NOV', '12': 'DEC', 'DEC': 'DEC', 'DECEMBER': 'DEC'}
RESIDENCE_YEAR_PATTERN = re.compile(r'(1[89]\d{2})')
RESIDENCE_RELATIVE_PATTERN = re.compile(r'(\d+)\s*year', re.I)

US_STATES_AND_TERRITORIES = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in", "ia", "ks", "ky", "la",
    "me", "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok",
    "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv", "wi", "wy", "dc",
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut", "delaware",
    "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa", "kansas", "kentucky",
    "louisiana", "maine", "maryland", "massachusetts", "michigan", "minnesota", "mississippi", "missouri",
    "montana", "nebraska", "nevada", "new hampshire", "new jersey", "new mexico", "new york", "north carolina",
    "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina",
    "south dakota", "tennessee", "texas", "utah", "vermont", "virginia", "washington", "west virginia",
    "wisconsin", "wyoming", "district of columbia",
    "dakota territory", "minnesota territory", "illinois territory", "indiana territory", "michigan territory",
    "wisconsin territory", "iowa territory", "missouri territory", "northwest territory", "oregon territory",
    "washington territory", "utah territory", "new mexico territory", "nebraska territory", "kansas territory",
    "colorado territory", "nevada territory", "idaho territory", "arizona territory", "montana territory",
    "wyoming territory", "hawaii territory", "alaska territory", "indian territory",
    "united states", "united states of america", "usa", "u.s.a.", "us", "u.s.",
}

# This project's core subjects are overwhelmingly Canadian/Métis/HBCA-region families
# (see Gazetteer.CA_PROVINCE_NAMES, the same modern province names reused here), so a
# Canadian or historical fur-trade-region birthplace must be excluded from "foreign" the
# same as a US one - confirmed live this gap existed: "Hudsen Bay Ter T"/"Rupert's Land"/
# any Canadian province would otherwise have been misclassified as foreign and dumped
# verbatim into a NATI tag.
CANADIAN_PROVINCES_AND_TERRITORIES = {
    "alberta", "british columbia", "manitoba", "new brunswick", "newfoundland",
    "nova scotia", "northwest territories", "north-west territories", "ontario",
    "prince edward island", "quebec", "saskatchewan", "yukon", "nunavut",
    "canada", "rupert's land", "ruperts land", "red river settlement", "red river",
    "assiniboia", "hudson's bay territory", "hudsons bay territory", "hudson bay territory",
    "north west territory",
}

NON_FOREIGN_BIRTHPLACES = US_STATES_AND_TERRITORIES | CANADIAN_PROVINCES_AND_TERRITORIES


def is_foreign_birthplace(birth_place: str) -> bool:
    if not birth_place:
        return False
    parts = [p.strip().lower() for p in birth_place.split(",") if p.strip()]
    if not parts:
        return False
    if parts[-1] in {"unknown", "at sea", "not stated", "none", "n/a", "?"}:
        return False
    if parts[-1] in NON_FOREIGN_BIRTHPLACES or parts[0] in NON_FOREIGN_BIRTHPLACES:
        return False
    return True


def get_occupation_value(row: pd.Series) -> Tuple[str, str]:
    # 1. Primary Selection
    # capitalize_text_string (not clean_val alone) on every raw-sourced piece here - a real census
    # source can hand back ALL-CAPS or lowercase text, and every other proper-noun-like
    # census field in this module (race, birth_place, occupation itself pre-refactor)
    # already normalizes to Title Case. The connector words this function assembles
    # itself ("at"/"working in") are left alone - they're ours, not sourced data.
    base_occ = Utils.capitalize_text_string(row.get('Usual Occupation'))
    if not base_occ:
        base_occ = Utils.capitalize_text_string(row.get('Occupation'))
    if not base_occ:
        base_occ = Utils.capitalize_text_string(row.get('Occupation Category'))
    if not base_occ:
        base_occ = Utils.capitalize_text_string(row.get('Trade or Profession'))

    employer = Utils.capitalize_text_string(row.get('Employer'))
    industry = Utils.capitalize_text_string(row.get('Industry'))

    # 2. Unemployment Override
    is_unemployed = (Utils.clean_val(row.get('Out Of Work')) == 'Yes' or
                     Utils.clean_val(row.get('Seeking Work')) == 'Yes')

    # 3. Concatenation
    occ_str = ""
    if is_unemployed:
        occ_str = "Unemployed"
        if base_occ:
            occ_str += f" from {base_occ}"
    else:
        occ_str = base_occ if base_occ else ""

    if occ_str and employer:
        occ_str += f" at {employer}"
    if occ_str and industry:
        occ_str += f", working in {industry}"

    # 4. Notes
    notes_parts = []
    for field in ['Class of Worker', 'Hours Worked', 'Weeks Worked', 'Months Unemployed Past Year']:
        val = Utils.clean_val(row.get(field))
        if val:
            notes_parts.append(f"{field}: {val}")

    notes_str = "; ".join(notes_parts)

    return occ_str, notes_str


def get_education_value(row: pd.Series) -> Optional[str]:
    grade = Utils.clean_val(row.get('Highest Grade of School Completed', row.get('Highest Grade Completed', '')))
    if grade:
        return grade
    if Utils.clean_val(row.get('Attended School')):
        return ''
    return None


def get_birth_date(row: pd.Series, birth_year: float) -> str:
    month_str = get_row_val(row, ['Birth Month', 'Birth month', 'Month of Birth'], '')
    abbr = MONTH_ABBR.get(month_str.upper())
    return f"{abbr} {int(birth_year)}" if abbr else str(int(birth_year))


def build_residence_event(col_name: str, val: str, cit: List[str], loc: str, street: str = "") -> List[str]:
    year_match = RESIDENCE_YEAR_PATTERN.search(col_name)
    if year_match:
        date_val = year_match.group(1)
    else:
        rel_match = RESIDENCE_RELATIVE_PATTERN.search(col_name)
        date_val = str(CENSUS_YEAR - int(rel_match.group(1))) if rel_match else str(CENSUS_YEAR)

    evt = ["1 RESI", f"2 DATE {date_val}", f"2 PLAC {val or loc}"]
    if street:
        evt.append(f"2 ADDR {street}")
    evt.extend(["2 _PROOF proven"] + cit)
    return evt


def build_dynamic_events_and_notes(row: pd.Series, cit: List[str], giv: str, columns: List[str], loc: str,
                                   street: str) -> Tuple[List[str], List[str]]:
    events: List[str] = []
    notes: List[str] = []
    for col_str in columns:
        if col_str.strip().lower() in CORE_COLUMNS:
            continue
        if is_relationship_column(col_str):
            continue
        val = Utils.clean_val(row.get(col_str))
        if not val:
            continue
        tag = next((t for pat, t in DYNAMIC_EVENT_RULES if pat.search(col_str)), None)
        if CENSUS_ERA == 'pre1850' and tag not in PRE1850_ALLOWED_TAGS:
            tag = None

        if tag == 'IMMI':
            year_match = re.search(r'\d{4}', val)
            events.extend(["1 IMMI", f"2 DATE {year_match.group(0) if year_match else val}", "2 _PROOF proven"] + cit)
        elif tag == 'NATU_DATE':
            year_match = re.search(r'\d{4}', val)
            events.extend(["1 NATU", f"2 DATE {year_match.group(0) if year_match else val}", "2 _PROOF proven"] + cit)
        elif tag == 'NATU':
            events.extend(["1 NATU", f"2 DATE {CENSUS_YEAR}", f"2 NOTE {col_str}: {val}", "2 _PROOF proven"] + cit)
        elif tag == 'MILITARY':
            events.extend(["1 EVEN", "2 TYPE Military Service", f"2 DATE {CENSUS_YEAR}", f"2 NOTE {col_str}: {val}",
                           "2 _PROOF proven"] + cit)
        elif tag == 'RESI':
            events.extend(build_residence_event(col_str, val, cit, loc, street))
        elif tag == 'RELI':
            events.extend([f"1 RELI {val}", "2 _PROOF proven"] + cit)
        elif tag == 'MAIDEN':
            events.extend([f"1 NAME {giv} /{val}/", "2 TYPE maiden"] + cit)
            notes.append(f"Maiden name recorded ({val}) -- review for parental FAMC link")
        else:
            notes.append(f"{col_str}: {val}")
    return events, notes


def build_census_task(rec_id: str, giv: str, sur: str, record_label: str, reasons: List[Tuple[str, float]],
                      citation_block: List[str], media_path: Union[str, Path], media_title: str,
                      target_software: str) -> Tuple[List[str], str]:
    task_id = f"@T{rec_id}@"
    summary = "; ".join(r for r, _ in reasons)
    _, _, folder_name = evaluate_task_priority(summary)
    min_c = min((c for _, c in reasons), default=1.0)
    priority = 1 if min_c < 0.3 else (2 if min_c < REVIEW_THRESHOLD else 3)

    task_citation = []
    if citation_block and citation_block[0].startswith("2 SOUR"):
        task_citation = Utils.dedent_citation_lines(citation_block)

    link_url = f"https://www.ancestry.com/search/collections/{APID_DB}/records/{rec_id}"
    weblink = Utils.weblink_lines(link_url, COLLECTION_NAME or DEFAULT_COLLECTION_NAME,
                                  target_software)

    task_records = [f"0 {task_id} _TASK",
                    f"1 DESC {sur or '[No Surname]'}, {giv or '[No Given Name]'} ({record_label}): {summary}",
                    f"1 REFN {strip_ark_type_prefix(rec_id)}", f"1 _LINK @I{rec_id}@", "1 TYPE 2",
                    f"1 DATE {Utils.CURRENT_DATE}",
                    f"1 _LDATE {Utils.CURRENT_DATE}", f"1 NOTE {summary}", "1 STAT NEW", f"1 PRTY {priority}",
                    f"1 _COLOR {Utils.REVIEW_COLOR}"] + weblink + task_citation + [
        "1 OBJE", f"2 FILE {media_path}", "2 FORM jpg", f"2 TITL {media_title}", "2 _TYPE PHOTO"]
    return task_records, folder_name


def get_census_sources(target_software: str) -> List[str]:
    tid = 10008
    source_title = COLLECTION_NAME or DEFAULT_COLLECTION_NAME
    repository = Utils.clean_val(REPOSITORY) or "Ancestry.com Operations, Inc."
    primary_creator = ("United States. Bureau of the Census"
                       if ("U.S." in source_title or "United States" in source_title)
                       else (Utils.clean_val(Utils.ORG_NAME) or "Census Bureau"))
    department = "National Archives and Records Administration"
    date_str = str(CENSUS_YEAR) if CENSUS_YEAR else ""
    publisher = Utils.clean_val(PUBLISHER)
    pub_loc = Utils.clean_val(PUB_LOC)

    if target_software == "RM":
        tmplt_fields = [
            "2 FIELD", "3 NAME PrimaryCreator", f"3 VALUE {primary_creator}",
            "2 FIELD", "3 NAME Department", f"3 VALUE {department}",
            "2 FIELD", "3 NAME Date", f"3 VALUE {date_str}",
            "2 FIELD", "3 NAME SourceDescription", f"3 VALUE {source_title}",
        ]
        if publisher:
            tmplt_fields += ["2 FIELD", "3 NAME Publisher", f"3 VALUE {publisher}"]
        if pub_loc:
            tmplt_fields += ["2 FIELD", "3 NAME PublishLocation", f"3 VALUE {pub_loc}"]
        if repository:
            tmplt_fields += ["2 FIELD", "3 NAME Repository", f"3 VALUE {repository}"]

        bibl = (f"{primary_creator}, {department}. {date_str}. {source_title}. {pub_loc}: {publisher}."
                if (pub_loc and publisher)
                else f"{primary_creator}, {department}. {date_str}. {source_title}.")

        return [f"0 @S{CENSUS_SOURCE_ID}@ SOUR", f"1 REFN {CENSUS_SOURCE_ID}",
                f"1 ABBR {source_title}",
                f"1 TITL {source_title}",
                f"1 _BIBL {bibl}",
                "1 REPO @R1@", "1 _TMPLT", f"2 TID {tid}"] + tmplt_fields + [
            f"0 {Utils.ROOT_SOURCE_ID} SOUR", f"1 TITL {Utils.ORG_NAME}", "1 AUTH",
            f"1 PUBL Researcher: {Utils.RESEARCHER}."] + Utils.weblink_lines(
            Utils.MGS_GROUP_URL, "Facebook Group", "RM") + Utils.weblink_lines(Utils.ANCESTRY_GROUP_URL, "Ancestry Group", "RM")  # noqa: E501
    else:
        return [f"0 @S{CENSUS_SOURCE_ID}@ SOUR", f"1 REFN {CENSUS_SOURCE_ID}",
                f"1 TITL {source_title}",
                f"1 PUBL {PUB_LOC}: {PUBLISHER}", "1 REPO @R1@", f"1 _APID 1,{APID_DB}::0",
                f"0 {Utils.ROOT_SOURCE_ID} SOUR", f"1 TITL {Utils.ORG_NAME}", f"1 AUTH Research conducted by {Utils.RESEARCHER}.",  # noqa: E501
                f"1 _LINK {Utils.MGS_GROUP_URL}", "2 NAME Facebook Group", f"1 _LINK {Utils.ANCESTRY_GROUP_URL}",
                "2 NAME Ancestry Group"]


def get_location_string(row: pd.Series) -> str:
    row_state = get_row_val(row, ['State', 'State/Province'], '') or STATE
    row_county = get_row_val(row, ['County', 'Parish'], '') or COUNTY
    row_town = get_row_val(row, ['City', 'Township', 'Town', 'Civil Division', 'Ward'], '') or TOWNSHIP
    row_country = get_row_val(row, ['Country'], '') or 'USA'

    return ", ".join(filter(None, [row_town, row_county, row_state, row_country]))


def parse_alternate_entries(row: pd.Series, column: str) -> List[dict]:
    raw = row.get(column)
    if not raw or (isinstance(raw, float) and pd.isna(raw)):
        return []
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def build_alternate_name_lines(alt_entries: List[dict], cit: List[str]) -> List[str]:
    lines: List[str] = []
    for entry in alt_entries:
        value = Utils.clean_val(entry.get('value'))
        if not value:
            continue
        alt_giv, alt_sur = Utils.split_full_name(value)
        lines.append(f"1 NAME {alt_giv} /{alt_sur}/")
        lines.append("2 _PROOF proposed")
        lines.extend(cit)
    return lines


def build_alternate_birth_lines(alt_entries: List[dict], birth_year: Optional[float], row: pd.Series,
                                cit: List[str]) -> List[str]:
    lines: List[str] = []
    for entry in alt_entries:
        value = Utils.clean_val(entry.get('value'))
        if not value:
            continue
        lines.append("1 BIRT")
        if birth_year is not None:
            lines.append(f"2 DATE {get_birth_date(row, birth_year)}")
        lines.append(f"2 PLAC {value}")
        lines.append("2 _PROOF proposed")
        lines.extend(cit)
    return lines


def build_gedcom_from_census(df_in: pd.DataFrame, target_software: str) -> None:
    df = df_in.copy()

    fam_col = next((c for c in ['Family Number', 'Family', 'Household Number', 'Household'] if c in df.columns), None)
    if not fam_col:
        fam_col = next((c for c in ['Dwelling Number', 'Dwelling', 'House Number'] if c in df.columns), None)

    if fam_col:
        df['Household_ID'] = (df[fam_col] != df[fam_col].shift()).cumsum()
    else:
        df['Household_ID'] = range(len(df))

    str_columns: List[str] = list(df.columns.astype(str))

    ged = ["0 HEAD", f"1 SOUR {Utils.SOFTWARE_NAME}", f"2 VERS {Utils.SOFTWARE_VERS}", f"2 CORP {Utils.ORG_NAME}", "1 GEDC",  # noqa: E501
           "2 VERS 5.5.1", "2 FORM LINEAGE-LINKED", "1 CHAR UTF-8", f"1 DATE {Utils.CURRENT_DATE}",
           f"1 COPR Copyright {Utils.COPYRIGHT_START}", "1 SUBM @SUB1@"]
    if Utils.GEDCOM_NOTE:
        ged.append(f"1 NOTE {Utils.GEDCOM_NOTE}")
        if Utils.GEDCOM_CONC:
            ged.append(f"2 CONC {Utils.GEDCOM_CONC}")

    fam_links: Dict[Any, List[str]] = {i: [] for i in df.index}
    fam_blocks: List[str] = []
    used_fam_ids = set()
    media_dict: Dict[str, Dict[str, Union[str, Path]]] = {}
    task_blocks: List[str] = []
    folder_tasks: Dict[str, List[str]] = {}
    review_flags: Dict[Any, List[Tuple[str, float]]] = {}

    for _, group in df.groupby('Household_ID'):
        units: List[HouseholdUnit]
        unrelated: List[pd.Series]
        flags: List[FlagRecord]
        if CENSUS_ERA == 'pre1850':
            units, unrelated, flags = [], [], []
        elif CENSUS_ERA == 'heuristic':
            units, unrelated, flags = parse_household(group)
        else:
            units, unrelated, flags = parse_household_relational(group)

        for flag in flags:
            flag_person = flag.get('person')
            if isinstance(flag_person, pd.Series):
                review_flags.setdefault(flag_person.name, []).append(
                    (str(flag.get('reason', '')), float(flag.get('confidence', 0.0))))

        for person in unrelated:
            review_flags.setdefault(person.name, [])

        for u in units:
            h = u.get('husband')
            w = u.get('wife')
            children_list = u.get('children', [])
            anc = u.get('anchor')
            u_type = u.get('type', 'main')

            if h is None and w is None and not children_list:
                continue

            anchor_row = h if isinstance(h, pd.Series) else (w if isinstance(w, pd.Series) else (
                anc if isinstance(anc, pd.Series) else (children_list[0] if children_list else None)))
            if not isinstance(anchor_row, pd.Series):
                continue

            anchor_pid = Utils.clean_val(anchor_row.get('PID')) or str(
                ANCESTRY_START_RECORD_ID + cast(int, anchor_row.name))

            base_f_id = f"@F{anchor_pid}_{u_type}@" if u_type != 'main' else f"@F{anchor_pid}@"
            f_id = base_f_id
            counter = 1
            while f_id in used_fam_ids:
                f_id = f"{base_f_id[:-1]}_{counter}@"
                counter += 1

            used_fam_ids.add(f_id)

            fam_blocks.append(f"0 {f_id} FAM")

            if isinstance(h, pd.Series):
                h_idx = Utils.clean_val(h.get('PID')) or str(ANCESTRY_START_RECORD_ID + cast(int, h.name))
                fam_blocks.append(f"1 HUSB @I{h_idx}@")
                fam_links[h.name].append(f"1 FAMS {f_id}")
            if isinstance(w, pd.Series):
                w_idx = Utils.clean_val(w.get('PID')) or str(ANCESTRY_START_RECORD_ID + cast(int, w.name))
                fam_blocks.append(f"1 WIFE @I{w_idx}@")
                fam_links[w.name].append(f"1 FAMS {f_id}")
            if isinstance(children_list, list):
                for child in children_list:
                    if isinstance(child, pd.Series):
                        c_idx = Utils.clean_val(child.get('PID')) or str(
                            ANCESTRY_START_RECORD_ID + cast(int, child.name))
                        fam_blocks.append(f"1 CHIL @I{c_idx}@")
                        fam_links[child.name].append(f"1 FAMC {f_id}")

            if (isinstance(h, pd.Series) and pd.notna(h.get('Married within Year'))) or (
                    isinstance(w, pd.Series) and pd.notna(w.get('Married within Year'))):
                fam_blocks.extend(["1 MARR", f"2 DATE EST {CENSUS_YEAR}", "2 _PROOF proven"])

    current_line_page_key = None
    synthesized_line_num = 0
    for idx, row in df.iterrows():
        page_key = Utils.clean_val(row.get('Page_Number', ''))
        if page_key != current_line_page_key:
            current_line_page_key = page_key
            synthesized_line_num = 0
        synthesized_line_num += 1
        if not Utils.clean_val(row.get('Line Number', row.get('Line', ''))):
            row['Line Number'] = str(synthesized_line_num)

        row_pid = Utils.clean_val(row.get('PID', row.get('pid', '')))
        rec_id = row_pid if row_pid else str(ANCESTRY_START_RECORD_ID + cast(int, idx))
        giv = Utils.clean_val(row.get('Given Name'))
        sur = Utils.clean_val(row.get('Surname'))
        gen = get_gender(row)

        row_loc = get_location_string(row)

        row_state = get_row_val(row, ['State', 'State/Province'], '') or STATE
        row_county = get_row_val(row, ['County', 'Parish'], '') or COUNTY
        row_town = get_row_val(row, ['City', 'Township', 'Town', 'Civil Division', 'Ward'], '') or TOWNSHIP
        row_street = get_row_val(row, ['Street', 'Street Address', 'Address', 'House Number'], '')

        row_roll = get_row_val(row, ['Roll', 'Roll Number', 'NARA Roll'], '') or ROLL_NUMBER
        row_film = get_row_val(row, ['Film', 'FHL Film Number', 'Microfilm'], '') or FILM_NUMBER
        row_ed = get_row_val(row, ['Enumeration District', 'Enumeration_District', 'ED'], '') or ENUMERATION_DISTRICT

        page = get_row_val(row, ['Page', 'Page_Number', 'Page Number'], '')
        real_page = get_row_val(row, ['Real Page', 'Real_Page', 'Page', 'Page_Number'], '')

        image_id_val = Utils.clean_val(row.get('Image_ID', ''))
        if not image_id_val:
            image_id_val = f"{BASE_ID}_{page.zfill(5)}"

        image_stem = Path(image_id_val).stem
        image_suffix = Path(image_id_val).suffix.lstrip('.').lower()
        if image_suffix == 'jpeg':
            image_suffix = 'jpg'

        m_id = f"@M{image_stem}@"
        image_name = image_stem

        if image_name not in media_dict:
            img_filename = f"{image_stem}.{image_suffix}" if image_suffix else f"{image_stem}.{IMAGE_EXTENSION}"
            img_path = Path(str(IMAGE_DIR)) / img_filename
            media_dict[image_name] = {'id': m_id, 'img': img_path, 'form': image_suffix or FORM_TYPE,
                                      'title': f"{CENSUS_YEAR} Census, {row_county}, Image {image_name}"}

        cit = build_census_citation(row, rec_id, m_id, real_page, target_software, row_town, row_county, row_state,
                                    row_roll, row_film, row_ed)

        alt_names = parse_alternate_entries(row, 'AlternateNames')
        row_fsftid = get_row_val(row, ['FSFTID'], '')
        fs_tree_link = (Utils.weblink_lines(f"https://www.familysearch.org/tree/person/details/{row_fsftid}",
                                            "FamilySearch Family Tree", target_software)
                        if row_fsftid else [])
        ged.extend(
            [f"0 @I{rec_id}@ INDI", f"1 REFN {strip_ark_type_prefix(rec_id)}"]
            + ([f"1 _FSFTID {row_fsftid}"] if row_fsftid else [])
            + fs_tree_link
            + [f"1 NAME {giv} /{sur}/"] + cit +
            build_alternate_name_lines(alt_names, cit) +
            [f"1 SEX {gen}", f"1 SOUR {Utils.ROOT_SOURCE_ID}", f"2 NAME Researcher: {Utils.RESEARCHER}",
             f"2 _TITL Researcher: {Utils.RESEARCHER}"]
        )

        if (person_flags := review_flags.get(idx, [])) and target_software == "RM":
            fam_lbl_num = get_row_val(row, ['Family Number', 'Family', 'Household Number', 'Household'], '')
            lbl = f"{CENSUS_YEAR}, Fam {fam_lbl_num}, p.{real_page}"
            task_records, folder = build_census_task(rec_id, giv, sur, lbl, person_flags, cit,
                                                     media_dict[image_name]['img'],
                                                     str(media_dict[image_name]['title']), target_software)
            task_blocks.extend(task_records)
            folder_tasks.setdefault(folder, []).append(f"1 _TASK @T{rec_id}@")
            ged.extend([f"1 _TASK @T{rec_id}@", f"1 _COLOR {Utils.REVIEW_COLOR}"])

        b_yr = row.get('Birth Year')
        age = row.get('Age')
        birth_year = None
        if pd.notna(b_yr):
            try:
                birth_year = float(b_yr)
            except ValueError:
                pass
        elif pd.notna(age):
            try:
                birth_year = float(CENSUS_YEAR) - float(age)
            except ValueError:
                pass

        birth_place = Utils.clean_val(row.get('Birth Place', row.get('Birthplace', '')))

        if birth_year is not None or birth_place:
            ged.append("1 BIRT")
            if birth_year is not None:
                ged.append(f"2 DATE {get_birth_date(row, birth_year)}")
            if birth_place:
                ged.append(f"2 PLAC {birth_place}")
            ged.append("2 _PROOF proposed")
            ged.extend(cit)

        alt_birth_places = parse_alternate_entries(row, 'AlternateBirthPlaces')
        ged.extend(build_alternate_birth_lines(alt_birth_places, birth_year, row, cit))

        occ, occ_notes = get_occupation_value(row)
        if occ:
            occ_evt = [f"1 OCCU {occ}", f"2 DATE {CENSUS_YEAR}", f"2 PLAC {row_loc}"]
            if occ_notes:
                occ_evt.append(f"2 NOTE {occ_notes}")
            occ_evt.extend(["2 _PROOF proven"] + cit)
            ged.extend(occ_evt)

        if race := Utils.capitalize_text_string(row.get('Race', row.get('Color', ''))):
            ged.extend([f"1 FACT {race}", "2 TYPE Race", f"2 DATE {CENSUS_YEAR}", "2 _PROOF proposed"] + cit)

        nat_val = Utils.clean_val(row.get('Nationality'))
        if not nat_val and birth_place and is_foreign_birthplace(birth_place):
            nat_val = birth_place
        if nat_val:
            ged.extend([f"1 NATI {nat_val}", f"2 DATE {CENSUS_YEAR}", "2 _PROOF proven"] + cit)

        edu_val = get_education_value(row)

        if edu_val is not None:
            ged.extend(["1 EDUC" + (f" {edu_val}" if edu_val else ""), f"2 DATE {CENSUS_YEAR}", f"2 PLAC {row_loc}",
                        "2 _PROOF proven"] + cit)

        dyn_events, dyn_notes = build_dynamic_events_and_notes(row, cit, giv, str_columns, row_loc, row_street)
        ged.extend(dyn_events)

        cens_evt = ["1 CENS", f"2 DATE {CENSUS_YEAR}", f"2 PLAC {row_loc}"]
        if row_street:
            cens_evt.append(f"2 ADDR {row_street}")
        cens_evt.extend(["2 _PROOF proven"] + cit)
        ged.extend(cens_evt)

        if notes := (get_census_notes(row) + dyn_notes):
            ged.append(f"2 NOTE {' | '.join(notes)}")
        ged.extend(fam_links.get(idx, []))

    ged.extend(fam_blocks)
    ged.extend(task_blocks)

    for folder, tasks in folder_tasks.items():
        ged.append(f"0 _FOLDER {folder}")
        ged.extend(tasks)

    ged.extend(get_census_sources(target_software))
    for m in media_dict.values():
        ged.extend([f"0 {m['id']} OBJE", f"1 FILE {m['img']}", f"2 FORM {m.get('form') or FORM_TYPE}",
                    f"1 TITL {m['title']}"])

    if target_software == "RM":
        ged.extend(
            ["0 _EVDEF Race", "1 TYPE P", "1 TITL Race", "1 ABBR Race", "1 SENT [person] was of [Desc] ethnicity.",
             "1 PLAC N", "1 DATE Y", "1 DESC Y", "0 _EVDEF EDUC", "1 TYPE P", "1 TITL Education", "1 ABBR Education",
             "1 SENT [person] was being educated < [Desc]>< [Date]>< [PlaceDetails]>< [Place].", "1 PLAC Y", "1 DATE Y",
             "1 DESC Y", "0 _EVDEF Military Service", "1 TYPE P", "1 TITL Military Service", "1 ABBR Mil. Service",
             "1 SENT [person] had military service.< [Desc]>< [Date]>.", "1 PLAC N", "1 DATE Y", "1 DESC Y"])
        ged.extend(get_source_templates({10008}))

    ged.extend(["0 @SUB1@ SUBM", f"1 NAME {Utils.RESEARCHER}", f"1 ADDR {Utils.SUBM_ADDRESS}", f"1 NOTE {Utils.ORG_NAME}", "0 @R1@ REPO",  # noqa: E501
                f"1 NAME {REPOSITORY}", f"1 ADDR {REPOSITORY_LOC}", f"1 CALN {CALL_NUMBER}", "2 MEDI Electronic",
                f"2 _URL {COLLECTION_URL}", "0 TRLR"])

    output_path = Utils.resolve_gedcom_output_path(target_software)
    output_path.write_text("\n".join(ged), encoding="utf-8")
    print(f"Success! {len(df)} individuals converted and saved to {output_path}")


def get_json_fallback(df: pd.DataFrame, columns: List[str], current: str) -> str:
    if current and str(current).strip() and str(current).strip() != '0':
        return str(current)
    for c in columns:
        if c in df.columns:
            valid_vals = df[df[c].astype(str).str.strip() != ''][c]
            if not valid_vals.empty:
                modes = valid_vals.mode()
                if not modes.empty:
                    return Utils.clean_val(modes.iloc[0])
    return ""


def load_census_dataframe(data: dict) -> pd.DataFrame:
    """Flattens the nested {census_year, location, pages: [{..., people: [...]}]} shape
    (produced by Voyageur.js/FS.py/MergedCensus.py) into one row per person, broadcasting each page's
    metadata onto every person on that page, so the existing DataFrame-based household
    grouping keeps working unchanged."""
    rows = []
    for page in data.get('pages', []):
        page_meta = {
            'Page_Number': page.get('page_number', ''), 'Image_ID': page.get('image_id', ''),
            'Country': page.get('country', ''), 'State': page.get('state', ''),
            'County': page.get('county', ''), 'City': page.get('city', ''),
            'Place_Details': page.get('place_details', ''),
            'Enumeration_District': page.get('enumeration_district', ''),
            'Film': page.get('film_number', ''), 'Roll': page.get('roll_number', ''),
            'APID_DB': page.get('apid_db', ''),
            'Publisher': page.get('publisher', ''), 'Publisher Location': page.get('pub_loc', ''),
            'Repository': page.get('repository', ''), 'Repository Location': page.get('repository_loc', ''),
        }
        for person in page.get('people', []):
            row = dict(person.get('columns', {}))
            row.update(page_meta)
            row['PID'] = person.get('pid', '')
            row['Extracted_URL'] = person.get('extracted_url', '')
            row['FSFTID'] = person.get('fsftid', '')
            row['FamilySearch_URL'] = person.get('familysearch_url', '')
            row['AlternateNames'] = json.dumps(person.get('alternate_names', []))
            row['AlternateBirthPlaces'] = json.dumps(person.get('alternate_birth_places', []))
            rows.append(row)
    df = pd.DataFrame(rows)
    for numeric_col in ['Age', 'Birth Year']:
        if numeric_col in df.columns:
            df[numeric_col] = pd.to_numeric(df[numeric_col], errors='coerce')
    return df


FACT_TYPE_TO_COLUMN = {
    "Occupation": "Occupation", "Education": "Highest Grade Completed",
    "Immigration": "Immigration Year", "Naturalization": "Naturalization Status",
    "Military": "Military Service", "Residence": "Residence", "Religion": "Religion",
    "Property": "Real Estate Value", "Miscellaneous": "Miscellaneous Note",
    "Nationality": "Nationality",
}


def build_census_dataframe_from_unified(data: dict) -> Tuple[pd.DataFrame, str, str]:
    """Adapts the shared sheets[].records[].participants[] schema into the same flat,
    old-column-named DataFrame shape load_census_dataframe has always produced."""
    citation = data.get('citation', {}) or {}
    census_year_str = ""
    year_match = re.search(r'(\d{4})', data.get('record_type_name', '') or '')
    if year_match:
        census_year_str = year_match.group(1)

    location_str = ""
    rows = []
    fallback_family_counter = 0
    for sheet in data.get('sheets', []):
        doc_meta = sheet.get('document_metadata', {})
        for record in sheet.get('records', []):
            ts = record.get('type_specific_fields', {}) or {}
            if not location_str:
                location_str = ts.get('state', '') or doc_meta.get('source_location', '')

            fallback_family_counter += 1
            family_id = ts.get('family_number') or f"__record_{fallback_family_counter}"

            page_meta = {
                'Page_Number': sheet.get('page_id', ''), 'Image_ID': doc_meta.get('file_name', ''),
                'Country': ts.get('country', ''), 'State': ts.get('state', ''),
                'County': ts.get('county', ''), 'City': ts.get('city', ''),
                'Place_Details': ts.get('place_details', ''),
                'Enumeration_District': ts.get('enumeration_district', ''),
                'Film': ts.get('film_number', ''), 'Roll': ts.get('roll_number', ''),
                'APID_DB': ts.get('apid_db', '') or citation.get('apid_db', ''),
                'Publisher': citation.get('publisher', ''), 'Publisher Location': citation.get('pub_loc', ''),
                'Repository': citation.get('repository', ''), 'Repository Location': citation.get('repository_loc', ''),
                'Collection Name': citation.get('collection_name', ''),
                'Collection URL': citation.get('collection_url', ''),
                'Family Number': family_id,
            }
            for p in record.get('participants', []):
                pts = p.get('type_specific_fields', {}) or {}
                row: Dict[str, Any] = dict(page_meta)
                row['Given Name'] = p.get('std_given', '') or ''
                row['Surname'] = p.get('std_surname', '') or ''
                row['Gender'] = p.get('sex', '') or ''
                if p.get('age'):
                    row['Age'] = p['age']
                if p.get('role_name'):
                    row['Relationship to Head'] = p['role_name']
                if pts.get('line_number'):
                    row['Line Number'] = pts['line_number']
                if pts.get('married_within_year'):
                    row['Married within Year'] = pts['married_within_year']
                if pts.get('street'):
                    row['Street'] = pts['street']
                if p.get('birth_place'):
                    row['Birth Place'] = p['birth_place']
                if p.get('race'):
                    row['Race'] = p['race']
                for fact in p.get('facts', []) or []:
                    col = FACT_TYPE_TO_COLUMN.get(fact.get('fact_type', ''), fact.get('fact_type', ''))
                    row[col] = fact.get('value') or fact.get('date') or fact.get('place') or ''
                row['PID'] = pts.get('pid', '')
                row['Extracted_URL'] = pts.get('extracted_url', '')
                row['FSFTID'] = pts.get('fsftid', '')
                row['FamilySearch_URL'] = pts.get('familysearch_url', '')
                row['AlternateNames'] = json.dumps(p.get('alternate_names', []) or [])
                row['AlternateBirthPlaces'] = json.dumps(pts.get('alternate_birth_places', []) or [])
                if pts.get('merge_review_reason'):
                    row['_MergeReviewReason'] = pts['merge_review_reason']
                rows.append(row)

    df = pd.DataFrame(rows)
    for numeric_col in ['Age', 'Birth Year']:
        if numeric_col in df.columns:
            df[numeric_col] = pd.to_numeric(df[numeric_col], errors='coerce')
    return df, census_year_str, location_str


def run_census_flavor(data: dict) -> None:
    global STATE, COUNTY, TOWNSHIP, ENUMERATION_DISTRICT, ROLL_NUMBER, FILM_NUMBER, CENSUS_YEAR, CENSUS_ERA
    global APID_DB, COLLECTION_NAME, COLLECTION_URL, PUBLISHER, PUB_LOC, CALL_NUMBER, REPOSITORY_LOC, REPOSITORY
    global IMAGE_DIR, CENSUS_SOURCE_ID, COUNTRY, DEFAULT_COLLECTION_NAME

    if "pages" in data:
        census_df = load_census_dataframe(data)
        payload_year = Utils.clean_val(data.get('census_year'))
        payload_location = Utils.clean_val(data.get('location'))
    else:
        census_df, payload_year, payload_location = build_census_dataframe_from_unified(data)

    STATE = get_json_fallback(census_df, ['State', 'State/Province'], STATE)
    COUNTY = get_json_fallback(census_df, ['County', 'Parish'], COUNTY)
    TOWNSHIP = get_json_fallback(census_df, ['City', 'Township', 'Town', 'Civil Division', 'Ward'], TOWNSHIP)
    ENUMERATION_DISTRICT = get_json_fallback(census_df, ['Enumeration District', 'Enumeration_District', 'ED'],
                                             ENUMERATION_DISTRICT)
    ROLL_NUMBER = get_json_fallback(census_df, ['Roll', 'Roll Number', 'NARA Roll'], ROLL_NUMBER)
    FILM_NUMBER = get_json_fallback(census_df, ['Film', 'FHL Film Number', 'Microfilm'], FILM_NUMBER)

    census_year_str = get_json_fallback(census_df, ['Census Year', 'Year', 'Census_Year'], str(CENSUS_YEAR))
    CENSUS_YEAR = int(census_year_str) if census_year_str and census_year_str.isdigit() else 0
    if not CENSUS_YEAR:
        CENSUS_YEAR = int(payload_year) if payload_year.isdigit() else 0
    CENSUS_ERA = get_census_era(CENSUS_YEAR)

    record_type_name = data.get("record_type_name") or f"Census_{CENSUS_YEAR}"
    APID_DB = get_json_fallback(census_df, ['APID_DB', 'APID', 'Database ID', 'dbid'], APID_DB)

    citation = data.get("citation") or {}
    cc = citation.get("collection_id")
    apid = APID_DB or citation.get("apid_db")

    cc_val = str(cc) if cc is not None else ""
    apid_val = str(apid) if apid is not None else ""

    if cc_val.strip():
        CENSUS_SOURCE_ID = cc_val.strip()
    elif apid_val.strip():
        CENSUS_SOURCE_ID = apid_val.strip()
    else:
        CENSUS_SOURCE_ID = Utils.resolve_source_id(record_type_name, COLLECTION_NAME)

    # Country-aware, never hardcoded: read back whatever the gather itself recorded in
    # its own 'Country' column (Ancestry: Voyageur.js's ancestryCountryFromState();
    # FamilySearch: FS.py's own "canada" in collection_title.lower() check) rather than
    # assuming USA. Confirmed live (2026-08-15, dbId 1578, Ontario) that the old
    # unconditional "United States Federal Census" text mislabeled every Canadian
    # gather's citation weblinks/source title/image-organizing fallback alike.
    COUNTRY = get_json_fallback(census_df, ['Country'], COUNTRY)
    # Generic "{country} Census" - not a fixed US-or-Canada choice, so any country this
    # project ever gathers plugs in the same way with no country list to maintain.
    # Defaults to "USA" only when country is absent/unrecognized (this project's
    # long-standing default). Matches Voyageur's own census_collection_folder_name()
    # convention (Voyageur/_gather_helpers.py) so citation text and image-folder naming
    # never diverge.
    DEFAULT_COLLECTION_NAME = f'{CENSUS_YEAR} {COUNTRY or "USA"} Census' if CENSUS_YEAR else COLLECTION_NAME
    COLLECTION_NAME = get_json_fallback(census_df, ['Collection Name', 'Collection_Name', 'Collection'],
                                        COLLECTION_NAME) or DEFAULT_COLLECTION_NAME
    COLLECTION_URL = get_json_fallback(census_df, ['Collection URL', 'Collection_URL', 'URL'], COLLECTION_URL) or (
        f"https://www.ancestry.com/search/collections/{APID_DB}" if APID_DB else COLLECTION_URL)
    PUBLISHER = get_json_fallback(census_df, ['Publisher', 'Census Publisher'], PUBLISHER)
    PUB_LOC = get_json_fallback(census_df, ['Publisher Location', 'Pub Loc'], PUB_LOC)
    REPOSITORY_LOC = get_json_fallback(census_df, ['Repository Location', 'Repo Loc'], REPOSITORY_LOC)
    REPOSITORY = get_json_fallback(census_df, ['Repository', 'Source Repository'], REPOSITORY)

    if 'FSFTID' in census_df.columns and (census_df['FSFTID'].astype(str).str.strip() != '').any():
        REPOSITORY = PUBLISHER or REPOSITORY
        REPOSITORY_LOC = PUB_LOC or REPOSITORY_LOC

    CALL_NUMBER = CALL_NUMBER or (f"{FILM_NUMBER}, roll {ROLL_NUMBER}".strip(", ")
                                  if (FILM_NUMBER or ROLL_NUMBER) else CALL_NUMBER)

    location_str = payload_location
    if IMAGE_DIR and CENSUS_YEAR and location_str:
        location_folder = re.sub(r'^USA\s*-\s*', '', location_str)
        # Try the current folder-naming scheme first - the real collection name
        # (sanitized the same way Voyageur's own census_collection_folder_name() does)
        # when one was captured, else the generic "{year} {country} Census" template;
        # fall back to the legacy unconditional "{year} US Federal Census" name every
        # gather - any country - used before this fix, so already-gathered images stay
        # linkable without requiring a re-gather.
        current_folder_name = (
            re.sub(r'[/\\?%*:|"<>]', "-", COLLECTION_NAME).strip() if COLLECTION_NAME
            else f'{CENSUS_YEAR} {COUNTRY or "USA"} Census'
        )
        nested_dir = Path(IMAGE_DIR) / current_folder_name / location_folder
        if not nested_dir.is_dir():
            legacy_dir = Path(IMAGE_DIR) / f"{CENSUS_YEAR} US Federal Census" / location_folder
            if legacy_dir.is_dir():
                nested_dir = legacy_dir
        if nested_dir.is_dir():
            IMAGE_DIR = str(nested_dir)

    if not os.getenv("GEDCOM_OUTPUT_NAME", "").strip():
        parts = [f"{CENSUS_YEAR} Census" if CENSUS_YEAR else "Census"]
        if COUNTRY:
            parts.append(COUNTRY)
        if STATE:
            parts.append(STATE)
        if COUNTY:
            parts.append(COUNTY)
        
        city_ed = []
        if TOWNSHIP:
            city_ed.append(TOWNSHIP)
        if ENUMERATION_DISTRICT:
            city_ed.append(ENUMERATION_DISTRICT)
        if city_ed:
            parts.append(", ".join(city_ed))
        
        provider = "Ancestry" if APID_DB else "FamilySearch" if ('FSFTID' in census_df.columns and (census_df['FSFTID'].astype(str).str.strip() != '').any()) else ""
        if provider:
            parts.append(provider)
        
        base_name = " - ".join(parts)
        base_name = re.sub(r'[/\\?%*:|"<>]', "-", base_name).strip()
        Utils.GEDCOM_OUTPUT_NAME = f"{base_name}.ged"

    for software in Utils.resolve_gedcom_output_targets():
        build_gedcom_from_census(census_df, software)
