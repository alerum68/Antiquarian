"""
Boilerplate schema-to-UI mapping for Registrar and RootsMagic SQLite tables.

Maps the RootsMagic tables/columns touched by Registrar.py (extract_people_from_rm
and write_tasks_to_db) to the CustomTkinter StringVar keys defined in Scriptorium.py
under REGISTRAR_VARS.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class RMColumn:
    """Represents a column in a RootsMagic SQLite table."""
    table_name: str
    column_name: str
    data_type: str
    description: str


@dataclass(frozen=True)
class StringVarMapping:
    """Maps a CustomTkinter StringVar key to its corresponding RootsMagic schema column(s)."""
    string_var_key: str
    category: str
    default_value: str
    target_table: str
    target_column: str
    description: str


# ==========================================
# ROOTSMAGIC TABLES TOUCHED BY REGISTRAR.PY
# ==========================================

TAG_TABLE_COLUMNS: List[RMColumn] = [
    RMColumn("TagTable", "TagID", "INTEGER", "Primary key for tags and task folders"),
    RMColumn("TagTable", "TagType", "INTEGER", "Tag classification (1 = Task Folder)"),
    RMColumn("TagTable", "TagValue", "INTEGER", "Tag payload value"),
    RMColumn("TagTable", "TagName", "TEXT", "Folder or tag display name"),
    RMColumn("TagTable", "Description", "TEXT", "Optional description text"),
    RMColumn("TagTable", "UTCModDate", "REAL", "UTC modification timestamp"),
]

TASK_TABLE_COLUMNS: List[RMColumn] = [
    RMColumn("TaskTable", "TaskID", "INTEGER", "Primary key for tasks"),
    RMColumn("TaskTable", "TaskType", "INTEGER", "Task type code (2 = Main Task)"),
    RMColumn("TaskTable", "RefNumber", "TEXT", "Unique reference code (e.g. MGS-1-2)"),
    RMColumn("TaskTable", "Name", "TEXT", "Task title / summary name"),
    RMColumn("TaskTable", "Status", "INTEGER", "Task progress status (0 = Unstarted)"),
    RMColumn("TaskTable", "Priority", "INTEGER", "Task priority rating (0 = Highest, 4 = Lowest)"),
    RMColumn("TaskTable", "Date1", "TEXT", "Start date string"),
    RMColumn("TaskTable", "Date2", "TEXT", "Due date string"),
    RMColumn("TaskTable", "Date3", "TEXT", "Completion date string"),
    RMColumn("TaskTable", "SortDate1", "INTEGER", "Numeric sort date 1"),
    RMColumn("TaskTable", "SortDate2", "INTEGER", "Numeric sort date 2"),
    RMColumn("TaskTable", "SortDate3", "INTEGER", "Numeric sort date 3"),
    RMColumn("TaskTable", "Filename", "TEXT", "Associated external file path"),
    RMColumn("TaskTable", "Details", "TEXT", "Task details and duplicate match statistics"),
    RMColumn("TaskTable", "Results", "TEXT", "Task outcome / resolution summary"),
    RMColumn("TaskTable", "UTCModDate", "REAL", "UTC modification timestamp"),
    RMColumn("TaskTable", "Exclude", "INTEGER", "Exclusion flag from reports"),
]

TASK_LINK_TABLE_COLUMNS: List[RMColumn] = [
    RMColumn("TaskLinkTable", "TaskID", "INTEGER", "Foreign key referencing TaskTable.TaskID"),
    RMColumn("TaskLinkTable", "OwnerType", "INTEGER", "Owner entity type (0 = Person, 18 = Folder/Tag)"),
    RMColumn("TaskLinkTable", "OwnerID", "INTEGER", "ID of the linked PersonID or TagID"),
    RMColumn("TaskLinkTable", "UTCModDate", "REAL", "UTC modification timestamp"),
]

PERSON_TABLE_COLUMNS: List[RMColumn] = [
    RMColumn("PersonTable", "PersonID", "INTEGER", "Primary key for individuals"),
    RMColumn("PersonTable", "Color1..N", "INTEGER", "Color highlight value for set (Color1 to Color10)"),
]

NAME_TABLE_COLUMNS: List[RMColumn] = [
    RMColumn("NameTable", "OwnerID", "INTEGER", "Foreign key referencing PersonID"),
    RMColumn("NameTable", "Given", "TEXT", "Given / first names"),
    RMColumn("NameTable", "Surname", "TEXT", "Surname / last name"),
    RMColumn("NameTable", "BirthYear", "INTEGER", "Extracted birth year"),
    RMColumn("NameTable", "IsPrimary", "INTEGER", "Primary name flag (1 = Primary)"),
]

FAMILY_TABLE_COLUMNS: List[RMColumn] = [
    RMColumn("FamilyTable", "FamilyID", "INTEGER", "Primary key for couples / family units"),
    RMColumn("FamilyTable", "FatherID", "INTEGER", "PersonID of father / husband"),
    RMColumn("FamilyTable", "MotherID", "INTEGER", "PersonID of mother / wife"),
]

CHILD_TABLE_COLUMNS: List[RMColumn] = [
    RMColumn("ChildTable", "FamilyID", "INTEGER", "Foreign key referencing FamilyTable.FamilyID"),
    RMColumn("ChildTable", "ChildID", "INTEGER", "Foreign key referencing PersonID"),
]


# ==========================================
# ENV_TARGETS SHAPED CONFIG DICTIONARY
# ==========================================
# Mirrors the dict-of-dicts structure used in Scriptorium.py (REGISTRAR_VARS)

REGISTRAR_CONFIG_SCHEMA: Dict[str, Dict[str, str]] = {
    "File Paths (Relative to RootsMagic Dir)": {
        "REGISTRAR_RM_DATABASE": "Your Tree.rmtree",
    },
    "Matching Thresholds": {
        "REGISTRAR_FUZZY_THRESHOLD": "82",
        "REGISTRAR_MAX_AGE_GAP": "5",
        "REGISTRAR_FUZZY_THRESHOLD_STRICT": "95",
        "REGISTRAR_FAMILY_MATCH_THRESHOLD": "75",
    },
    "RootsMagic UI Settings": {
        "REGISTRAR_FOLDER_NAME": "!Duplicate Review",
        "REGISTRAR_COLOR_SET": "1",
        "REGISTRAR_COLOR_VALUE": "27",
    },
}

# Tuple matching Scriptorium.py's ENV_TARGETS entry for Registrar
REGISTRAR_ENV_TARGET = (REGISTRAR_CONFIG_SCHEMA, "Registrar")


# ==========================================
# SCHEMA TO STRINGVAR MAPPINGS
# ==========================================

UI_SCHEMA_MAPPINGS: Dict[str, StringVarMapping] = {
    "REGISTRAR_RM_DATABASE": StringVarMapping(
        string_var_key="REGISTRAR_RM_DATABASE",
        category="File Paths (Relative to RootsMagic Dir)",
        default_value="Your Tree.rmtree",
        target_table="SQLite Database",
        target_column="N/A",
        description="Path to the RootsMagic .rmtree SQLite database file",
    ),
    "REGISTRAR_FUZZY_THRESHOLD": StringVarMapping(
        string_var_key="REGISTRAR_FUZZY_THRESHOLD",
        category="Matching Thresholds",
        default_value="82",
        target_table="NameTable",
        target_column="Given, Surname",
        description="Name token set ratio cutoff score for Pass 1 matching",
    ),
    "REGISTRAR_MAX_AGE_GAP": StringVarMapping(
        string_var_key="REGISTRAR_MAX_AGE_GAP",
        category="Matching Thresholds",
        default_value="5",
        target_table="NameTable",
        target_column="BirthYear",
        description="Maximum allowed birth year difference for Pass 1 matching",
    ),
    "REGISTRAR_FUZZY_THRESHOLD_STRICT": StringVarMapping(
        string_var_key="REGISTRAR_FUZZY_THRESHOLD_STRICT",
        category="Matching Thresholds",
        default_value="95",
        target_table="NameTable",
        target_column="Given, Surname",
        description="Strict name token set ratio cutoff score for Pass 2 (missing birth year)",
    ),
    "REGISTRAR_FAMILY_MATCH_THRESHOLD": StringVarMapping(
        string_var_key="REGISTRAR_FAMILY_MATCH_THRESHOLD",
        category="Matching Thresholds",
        default_value="75",
        target_table="FamilyTable / ChildTable",
        target_column="FatherID, MotherID, ChildID",
        description="Name similarity threshold for verifying linked relative names",
    ),
    "REGISTRAR_FOLDER_NAME": StringVarMapping(
        string_var_key="REGISTRAR_FOLDER_NAME",
        category="RootsMagic UI Settings",
        default_value="!Duplicate Review",
        target_table="TagTable",
        target_column="TagName",
        description="Name of the RootsMagic task folder (TagType=1) where duplicate tasks are grouped",
    ),
    "REGISTRAR_COLOR_SET": StringVarMapping(
        string_var_key="REGISTRAR_COLOR_SET",
        category="RootsMagic UI Settings",
        default_value="1",
        target_table="PersonTable",
        target_column="Color{N}",
        description="RootsMagic color set index (1-based index determining PersonTable.Color{N} column)",
    ),
    "REGISTRAR_COLOR_VALUE": StringVarMapping(
        string_var_key="REGISTRAR_COLOR_VALUE",
        category="RootsMagic UI Settings",
        default_value="27",
        target_table="PersonTable",
        target_column="Color{N}",
        description="Color ID assigned to flagged individuals in PersonTable (e.g. 27 = Slate)",
    ),
}
