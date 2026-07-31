import io
import json
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from functools import partial
from pathlib import Path
from tkinter import filedialog
from typing import Union, Dict, Callable, List, Optional

import customtkinter as ctk
import yaml
from dotenv import set_key, dotenv_values

BASE_DIR = Path(__file__).resolve().parent

# Each tool's own script lives in a fixed subfolder of this codebase - hardcoded rather than
# a configurable Global Settings field, since the folder layout is the codebase's own, not
# something that varies per user or per project the way PROGRAM_DIR does.
SCRIPT_PATHS = {
    "ANALYSIS_SCRIPT": "Paleographer/Paleographer.py",
    "ARCHIVIST_SCRIPT": "Archivist/Archivist.py",
    "VOYAGEUR_SCRIPT": "Voyageur/Voyageur.py",
    "REGISTRAR_SCRIPT": "Registrar/Registrar.py",
    "GAZETTEER_SCRIPT": "Gazetteer/Gazetteer.py",
    "PDFIX_SCRIPT": "PDFix/PDFix.py",
    "CLEANUP_CACHE_SCRIPT": "Paleographer/CacheCleanup.py",
}


def env_path_for(subfolder: Optional[str]) -> Path:
    """Resolves the .env path for a settings group: the project root if subfolder is None,
    otherwise that tool's own subfolder, so each tool's config stays self-contained."""
    return BASE_DIR / subfolder / ".env" if subfolder else BASE_DIR / ".env"


# ==========================================
# COLOR PALETTE
# ==========================================
# Dark-mode values from assets/theme.json's own token set (the app forces
# ctk.set_appearance_mode("Dark"), so only these matter visually) - for the handful of
# widgets below that pass their own explicit color kwargs instead of riding the CTk theme.
C_SURFACE = "#202329"
C_SURFACE_RAISED = "#262A31"
C_TEXT = "#E7E6DE"
C_TEXT_MUTED = "#8A8D83"
C_ACCENT = "#8FA0CE"
C_ACCENT_STRONG = "#6C7EAE"
C_ON_ACCENT = "#141A28"
C_BRASS = "#CBA35F"
C_BRASS_SOFT = "#3A2F1C"
C_SUCCESS = "#74C285"
C_SUCCESS_HOVER = "#5CAA6E"
C_DANGER = "#E58585"
C_DANGER_HOVER = "#C96A6A"
C_BORDER = "#33363D"

# ==========================================
# UNIFIED ENV SCHEMA & CONTEXT OVERRIDES
# ==========================================
GLOBAL_VARS = {"API & Processing": {"GEMINI_API_KEY": "", "API_BUDGET": "20", "MODEL_NAME": "gemini-3.1-pro-preview",
                                    "COST_PER_1M_INPUT": "2.00", "COST_PER_1M_OUTPUT": "12.00",
                                    "CACHE_DISCOUNT_MULTIPLIER": "0.10"},
               "Global Directories": {"PROGRAM_DIR": "C:/Path/To/Your/Genealogy/Folder", "RM_DIR": "Roots Magic 11",
                                      "FTM_DIR": "Family Tree Maker", "MEDIA_DIR": "Media/Project",
                                      "CENSUS_IMAGE_DIR": "Census",
                                      "JSON_DIR": "Scriptorium/Working/Project/JSON", "IMAGE_EXTENSION": "jpg",
                                      "GEDCOM_OUTPUT_PATH": "GEDCOM/Project"},
               # Everything identifying who's doing the research and how it's attributed,
               # in one card - was two ("Metadata & Organization", "Standard Links").
               "Researcher & Organization": {"RESEARCHER": "Your Name", "ORG_NAME": "Your Historical Society",
                                             "SOFTWARE_NAME": "RootsMagic", "SOFTWARE_VERS": "11.0",
                                             "COPYRIGHT_START": "2024",
                                             "GEDCOM_NOTE": "This file contains original historical translations "
                                                            "and research.",
                                             "GEDCOM_CONC": "Please do not upload this raw GEDCOM to public, "
                                                            "collaborative trees without permission and "
                                                            "attribution.",
                                             "REVIEW_COLOR": "1", "ROOT_SOURCE_ID": "@S1@",
                                             "SUBM_ADDRESS": "https://www.example.com/contact",
                                             "MGS_GROUP_URL": "https://www.example.com/groups/main",
                                             "ANCESTRY_GROUP_URL": "https://www.ancestry.com/groups/example"}}

ARCHIVIST_VARS = {"Which JSON to Build From": {"JSON_FILE": ""},
                  "Location Overrides": {"STATE": "", "COUNTY": "", "TOWNSHIP": ""},
                  "Family Inference Tuning": {"MIN_MARRIAGE_AGE": "12", "MAX_SPOUSE_AGE_GAP": "25",
                                              "HUSBAND_CHILD_AGE_GAP_MIN": "14", "HUSBAND_CHILD_AGE_GAP_MAX": "60",
                                              "WIFE_CHILD_AGE_GAP_MIN": "12", "WIFE_CHILD_AGE_GAP_MAX": "50"}}

# ==========================================
# VOYAGEUR SOURCES
# ==========================================
# Each source is one Voyageur sub-script (Voyageur/<code>.py); adding a new Major Repository
# is exactly this - a new sub-script plus one more entry here, nothing else touched. "Merged"
# isn't a repository of its own - it orchestrates the Ancestry and FamilySearch gathers
# back-to-back against the same two URL fields, then merges the results (see
# Voyageur/Merged.py) - so its settings section below is filtered specially rather than
# getting its own VOYAGEUR_VARS entry.
VOYAGEUR_SOURCES = [("A", "Ancestry"), ("FS", "FamilySearch"), ("LAC", "LAC"),
                    ("Merged", "Merged (Ancestry + FamilySearch)")]

VOYAGEUR_VARS = {"Gather Settings": {"VOYAGEUR_SOURCE": ""},
                 "Ancestry": {"CENSUS_URL": ""},
                 "FamilySearch": {"FS_URL": ""},
                 "LAC": {"LAC_URL": "", "LAC_IMAGE_DIR": "LAC"}}

PALEOGRAPHER_VARS = {"Data & Directories": {"PALEOGRAPHER_RECORD_TYPE": "", "CHURCH_IMAGE_DIR": "Parish",
                                            "CHURCH_GEDCOM_NAME": "Parish.ged",
                                            "CHURCH_MASTER_DB_NAME": "parish_register.json",
                                            "PALEOGRAPHER_PDF_COMPRESSION_LEVEL": "2"},
                     "Parish Information": {"PARISH_NAME": "St. Generic Catholic Church",
                                            "PARISH_NAME_SHORT": "St. Generic Parish, Anytown, ST",
                                            "PARISH_CITY": "Anytown", "PARISH_STATE": "State",
                                            "PARISH_FILE_NAME": "Parish_Anytown",
                                            "DEFAULT_EVENT_LOCATION": "Anytown, Any County, State, USA"},
                     "Register Information": {"REGISTER_SOURCE_ID": "1",
                                              "REGISTER_NAME": "Baptisms, marriages and burials, 1850-1900",
                                              "VOLUME_TITLE": "Volume 1",
                                              "VOLUME_NUM": "1"},
                     "Church Citation (Source)": {"CHURCH_CALL_NUMBER": "Call #1234567",
                                                  "CHURCH_COLLECTION_URL":
                                                  "https://www.familysearch.org/search/collection",
                                                  "CHURCH_COLLECTION_NAME": "Generic Historical Collection",
                                                  "CHURCH_REPOSITORY": "FamilySearch.org",
                                                  "CHURCH_REPOSITORY_LOC": "Granite Mountain, UT"},
                     "Scrip Information": {"SCRIP_IMAGE_DIR": "Scrip", "SCRIP_MASTER_DB_NAME": "scrip_records.json",
                                           "SCRIP_COLLECTION_NAME": "Library and Archives Canada, RG15 Scrip Records",
                                           "SCRIP_DISTRICT": ""}}

REGISTRAR_VARS = {
    "File Paths (Relative to RootsMagic Dir)": {
        "REGISTRAR_RM_DATABASE": "Your Tree.rmtree"},
    "Matching Thresholds": {
            "REGISTRAR_FUZZY_THRESHOLD": "82",
            "REGISTRAR_MAX_AGE_GAP": "5",
            "REGISTRAR_FUZZY_THRESHOLD_STRICT": "95",
            "REGISTRAR_FAMILY_MATCH_THRESHOLD": "75"},
    "RootsMagic UI Settings": {
                "REGISTRAR_FOLDER_NAME": "!Duplicate Review",
                "REGISTRAR_COLOR_SET": "1",
                "REGISTRAR_COLOR_VALUE": "27"}}

GAZETTEER_VARS = {"File Paths": {"GAZETTEER_RM_DATABASE": "Your Tree.rmtree",
                                 "GAZETTEER_SHAPEFILE": "Scriptorium/Gazetteer/Reference/US_AtlasHCB_Counties/"
                                 "US_HistCounties_Shapefile/US_HistCounties.shp"},
                  "Settings": {"GAZETTEER_DEBUG_MODE": "False", "GAZETTEER_CREATE_BACKUP": "True"}}

PDFIX_VARS = {"Scan Settings": {"PDFIX_TARGET_DIR": ".", "PDFIX_COMPRESSION_LEVEL": "2",
                                "PDFIX_SIZE_THRESHOLD_MB": "0"},
              "Safety": {"PDFIX_CREATE_BACKUP": "True", "PDFIX_REPAIR_MODE": "False"}}

# ==========================================
# ENV FILE TARGETS
# ==========================================
# Global settings persist to the project root's .env. Each tool's own settings persist to a
# .env file inside that tool's own subfolder, so every tool stays runnable standalone.
ENV_TARGETS = [(GLOBAL_VARS, None),
               (ARCHIVIST_VARS, "Archivist"),
               (PALEOGRAPHER_VARS, "Paleographer"),
               (VOYAGEUR_VARS, "Voyageur"),
               (REGISTRAR_VARS, "Registrar"),
               (GAZETTEER_VARS, "Gazetteer"),
               (PDFIX_VARS, "PDFix")]

# ==========================================
# TOOLTIP DESCRIPTIONS
# ==========================================
TOOLTIP_DESCRIPTIONS = {  # Global Settings
    "PROGRAM_DIR": "Your single base Genealogy folder. Everything else, including the Scriptorium code, your "
                   "Roots Magic / Family Tree Maker databases, Media, and GEDCOM output, lives directly inside "
                   "this one folder.",
    "GEMINI_API_KEY": "Your personal API key from Google AI Studio. Used to read and transcribe handwritten images.",
    "MEDIA_DIR": "The base folder where your genealogy media is stored.",
    "API_BUDGET": "A safety limit for your AI costs (e.g., '20' means $20). The script stops if it spends this much.",
    "MODEL_NAME": "The AI model version you want to use (usually gemini-3.1-pro-preview or gemini-2.5-pro).",
    "RM_DIR": "The folder where your RootsMagic files live, relative to the Program Dir.",
    "JSON_DIR": "The folder where downloaded JSON data files are kept.",
    "GEDCOM_OUTPUT_PATH": "The folder where the finished, ready-to-import GEDCOM files will be saved.",
    "RESEARCHER": "Your name. This will be added to the GEDCOM file to give you credit as the transcriber.",
    "COST_PER_1M_INPUT": "The price Google charges per 1 million input tokens (text/images sent to the AI).",
    "COST_PER_1M_OUTPUT": "The price Google charges per 1 million output tokens (JSON/text generated by the AI).",
    "CACHE_DISCOUNT_MULTIPLIER": "The fractional discount applied to tokens loaded from context caching (e.g., 0.10 "
                                 "means 10% of standard cost).",
    "ORG_NAME": "The name of your Historical Society, Library, or personal organization to include in GEDCOM headers.",
    "ROOT_SOURCE_ID": "The master SOUR (Source) ID used in RootsMagic for the researcher credit (e.g., @S1@).",
    "REVIEW_COLOR": "The numeric RootsMagic color code to paint people who have been flagged for manual review.",

    # Archivist (Create step - Census)
    "CENSUS_IMAGE_DIR": "The subfolder name (e.g., 'Census') inside your Base Media Directory. Can also be an "
                         "absolute path.",
    "JSON_FILE": "Only needed to build from a specific JSON file Voyageur already gathered. Leave blank to "
                 "automatically use the most recently created JSON file in your JSON folder.",
    "STATE": "Leave blank to use the State Voyageur already gathered per-page from the JSON file. Only fill "
             "this in to force the same State on every record.",
    "COUNTY": "Leave blank to use the County Voyageur already gathered per-page from the JSON file. Only fill "
              "this in to force the same County on every record.",
    "TOWNSHIP": "Leave blank to use the Township/City Voyageur already gathered per-page from the JSON file. "
                "Only fill this in to force the same Township on every record.",
    "MIN_MARRIAGE_AGE": "The youngest plausible age someone could be married (used to group families correctly).",
    "MAX_SPOUSE_AGE_GAP": "The largest age gap allowed between a husband and wife before the AI assumes they are not "
                          "married.",
    "HUSBAND_CHILD_AGE_GAP_MIN": "The minimum plausible age difference between a father and his child.",
    "HUSBAND_CHILD_AGE_GAP_MAX": "The maximum plausible age difference between a father and his child.",
    "WIFE_CHILD_AGE_GAP_MIN": "The minimum plausible age difference between a mother and her child.",
    "WIFE_CHILD_AGE_GAP_MAX": "The maximum plausible age difference between a mother and her child.",

    # Voyageur (Gather step)
    "VOYAGEUR_SOURCE": "Which repository to gather from. Adding a new one is a new Voyageur sub-script, nothing "
                       "else changes here.",
    "CENSUS_URL": "The web address (URL) of the specific Ancestry.com census page you want to gather.",
    "FS_URL": "The web address (URL) of the specific FamilySearch record page you want to gather.",
    "LAC_URL": "Paste the complete Heritage Canadiana link (e.g., "
                "https://heritage.canadiana.ca/iiif/oocihm.lac_reel_c2170/).",
    "LAC_IMAGE_DIR": "The subfolder name (e.g., 'LAC') inside your Base Media Directory. A subfolder per roll number "
                      "is created automatically inside it. Can also be an absolute path.",

    # Paleographer
    "PALEOGRAPHER_RECORD_TYPE": "Which record type (from Paleographer/prompts) to transcribe. Leave blank to use the "
    "default, Parish.pmt.",
    "CHURCH_IMAGE_DIR": "The subfolder name (e.g., 'Parish') inside your Base Media Directory. Can also be an "
                         "absolute path.",
    "CHURCH_GEDCOM_NAME": "The filename for the generated GEDCOM file.",
    "CHURCH_MASTER_DB_NAME": "The filename for the JSON database storing the extracted records.",
    "PALEOGRAPHER_PDF_COMPRESSION_LEVEL": "How aggressively PDFix's lossless structural optimization (garbage "
                                          "collection + stream deflate) runs on a scanned PDF before it's uploaded "
                                          "to the AI: 0=low, 1=medium, 2=high (recommended). This never touches "
                                          "embedded image resolution/DPI, so transcription quality is unaffected "
                                          "at any level.",
    "PARISH_NAME": "The full historical name of the church (e.g., St. Joseph Catholic Church).",
    "PARISH_NAME_SHORT": "A shortened name for the parish, used in file titles.",
    "PARISH_CITY": "The city where the parish is located.",
    "PARISH_STATE": "The state or province where the parish is located.",
    "PARISH_FILE_NAME": "The base filename used for parish exports.",
    "DEFAULT_EVENT_LOCATION": "The default location assigned to events if none is specified.",
    "REGISTER_SOURCE_ID": "The source ID assigned to this specific register volume.",
    "REGISTER_NAME": "What this register contains and covers (e.g., 'Baptisms, marriages and burials, "
                     "1850-1900'). Used throughout the generated source citations, distinct from Volume Title.",
    "VOLUME_TITLE": "This specific volume/book's own title or label (e.g., 'Volume 1'). Used alongside "
                    "Register Name in the generated source citations.",
    "VOLUME_NUM": "The volume number of the register.",
    "CHURCH_CALL_NUMBER": "The call number for the church register collection.",
    "CHURCH_COLLECTION_URL": "A link back to FamilySearch or Ancestry where you found these images.",
    "CHURCH_COLLECTION_NAME": "The name of the specific collection these images belong to (e.g., 'Quebec, Catholic "
                              "Parish Registers'). Do not include the repository/website name here, that's set "
                              "separately below.",
    "CHURCH_REPOSITORY": "The archive or website hosting this collection (e.g., FamilySearch.org, Library and "
                         "Archives Canada, Ancestry.com).",
    "CHURCH_REPOSITORY_LOC": "The physical location or address of that repository, used in the citation (e.g., "
                             "'Granite Mountain, UT' for FamilySearch, 'Ottawa, ON' for LAC).",
    "SCRIP_IMAGE_DIR": "The subfolder name (e.g., 'Scrip') inside your Base Media Directory. Can also be an "
                       "absolute path.",
    "SCRIP_MASTER_DB_NAME": "The filename for the JSON database storing the extracted scrip records.",
    "SCRIP_COLLECTION_NAME": "The name of the archival collection these scrip files came from.",
    "SCRIP_DISTRICT": "The scrip district or region this batch of applications belongs to, if known.",

    # Registrar
    "REGISTRAR_RM_DATABASE": "The filename of your RootsMagic tree (e.g., 'Your Tree.rmtree') located in your "
                         "RootsMagic Folder.",
    "REGISTRAR_FUZZY_THRESHOLD": "Score (0-100) for matching names when we KNOW their birth years. 82 is "
                                 "recommended.",
    "REGISTRAR_MAX_AGE_GAP": "The maximum number of years apart two records can be and still be flagged as a "
                            "duplicate.",
    "REGISTRAR_COLOR_VALUE": "The numeric RootsMagic color code to paint duplicate people (27 is Slate).",
    "REGISTRAR_FUZZY_THRESHOLD_STRICT": "A stricter threshold (0-100) used only for records missing a birth year.",
    "REGISTRAR_FAMILY_MATCH_THRESHOLD": "Score (0-100) used to verify if relatives (parents/spouses) match between two "
    "suspected duplicates.",
    "REGISTRAR_FOLDER_NAME": "The name of the Task Folder created in RootsMagic to hold duplicate review tasks.",
    "REGISTRAR_COLOR_SET": "The Color Set in RootsMagic (0-indexed) to apply the color value to.",

    # Gazetteer
    "GAZETTEER_RM_DATABASE": "The filename of your RootsMagic tree (e.g., 'Your Tree.rmtree') located in your "
                          "RootsMagic Folder.",
    "GAZETTEER_SHAPEFILE": "The path to the Newberry Atlas '.shp' file containing historical county boundaries. "
                         "Relative to your Program Dir (it ships alongside the Gazetteer tool), not the RootsMagic "
                         "folder.",
    "GAZETTEER_CREATE_BACKUP": "Set to 'True' to automatically create a backup of your RootsMagic file before "
                             "fixing it (Highly Recommended!).",
    "GAZETTEER_DEBUG_MODE": "Set to 'True' to print extra diagnostic information to the console while processing.",

    # PDFix
    "PDFIX_TARGET_DIR": "The folder PDFix scans recursively for .pdf files, relative to your Base Media Directory "
                        "(or an absolute path elsewhere). Leave as '.' to optimize every PDF anywhere inside Media.",
    "PDFIX_COMPRESSION_LEVEL": "How aggressively to garbage-collect and deflate-compress PDF structure: 0=low, "
                               "1=medium, 2=high (recommended). This is lossless - it never touches image "
                               "resolution/DPI.",
    "PDFIX_SIZE_THRESHOLD_MB": "Only optimize PDFs larger than this size, in MB. Leave as 0 to optimize every PDF "
                              "regardless of size.",
    "PDFIX_CREATE_BACKUP": "Set to 'True' to save a '.pdf.backup' copy of each original before optimizing it in "
                          "place (Highly Recommended!).",
    "PDFIX_REPAIR_MODE": "Set to 'True' to attempt repairing structurally damaged/corrupted PDFs before "
                        "optimizing them."}

# ==========================================
# CUSTOM UI LABELS OVERRIDE
# ==========================================
# Add keys here if you want them to display differently than standard Title Case.
CUSTOM_LABELS = {
    "GEMINI_API_KEY": "Google Gemini API Key",
    "PROGRAM_DIR": "Genealogy Root Directory",
    "RM_DIR": "RootsMagic Folder",
    "FTM_DIR": "Family Tree Maker Folder",
    "MEDIA_DIR": "Base Media Directory",
    "JSON_DIR": "JSON Download Folder",
    "REGISTRAR_RM_DATABASE": "RootsMagic Database Path",
    "GAZETTEER_RM_DATABASE": "RootsMagic Database Path",
    "CENSUS_URL": "Ancestry Census URL",
    "CENSUS_IMAGE_DIR": "Census Image Save Folder",
    "JSON_FILE": "Downloaded JSON File Name",
    "LAC_URL": "Heritage Canadiana URL",
    "FS_URL": "FamilySearch Record URL",
    "VOYAGEUR_SOURCE": "Gather From",
    "CHURCH_REPOSITORY": "Repository Name",
    "CHURCH_REPOSITORY_LOC": "Repository Location",
    "PDFIX_TARGET_DIR": "PDF Scan Folder"}

# ==========================================
# PATH & FILE PICKER FIELDS
# ==========================================
# Keys that get a "Browse..." button next to their entry, opening a native dialog instead of
# requiring the value to be typed by hand. "kind" picks the dialog: "directory" for folder
# fields, "open" for picking an existing file, "save" for naming a new/output file (lets you
# type a name that doesn't exist yet). "base_dir_key" says which folder the dialog should
# start in: another field's key (resolved against PROGRAM_DIR, same as execute_script does),
# or one of the two sentinels below.
PROGRAM_DIR_SENTINEL = "__PROGRAM_DIR__"  # Distinct from the real "PROGRAM_DIR" settings key
TOOLBOX_DIR_SENTINEL = "__TOOLBOX_DIR__"  # The Scriptorium code folder itself (BASE_DIR).

RMTREE_FILETYPES = [("RootsMagic files", "*.rmtree"), ("All files", "*.*")]
JSON_FILETYPES = [("JSON files", "*.json"), ("All files", "*.*")]
GED_FILETYPES = [("GEDCOM files", "*.ged"), ("All files", "*.*")]
SHP_FILETYPES = [("Shapefiles", "*.shp"), ("All files", "*.*")]

PATH_PICKER_FIELDS = {
    # Global: Directories (folders, relative to PROGRAM_DIR unless absolute)
    "PROGRAM_DIR": {"kind": "directory", "base_dir_key": PROGRAM_DIR_SENTINEL, "always_absolute": True},
    "RM_DIR": {"kind": "directory", "base_dir_key": PROGRAM_DIR_SENTINEL},
    "FTM_DIR": {"kind": "directory", "base_dir_key": PROGRAM_DIR_SENTINEL},
    "MEDIA_DIR": {"kind": "directory", "base_dir_key": PROGRAM_DIR_SENTINEL},
    "JSON_DIR": {"kind": "directory", "base_dir_key": PROGRAM_DIR_SENTINEL},
    "GEDCOM_OUTPUT_PATH": {"kind": "directory", "base_dir_key": PROGRAM_DIR_SENTINEL},

    # Archivist
    "CENSUS_IMAGE_DIR": {"kind": "directory", "base_dir_key": "MEDIA_DIR"},
    "JSON_FILE": {"kind": "open", "base_dir_key": "JSON_DIR", "filetypes": JSON_FILETYPES},

    # Voyageur
    "LAC_IMAGE_DIR": {"kind": "directory", "base_dir_key": "MEDIA_DIR"},

    # Paleographer
    "CHURCH_IMAGE_DIR": {"kind": "directory", "base_dir_key": "MEDIA_DIR"},
    "CHURCH_GEDCOM_NAME": {"kind": "save", "base_dir_key": "GEDCOM_OUTPUT_PATH", "filetypes": GED_FILETYPES,
                           "defaultextension": ".ged"},
    "CHURCH_MASTER_DB_NAME": {"kind": "save", "base_dir_key": "JSON_DIR", "filetypes": JSON_FILETYPES,
                              "defaultextension": ".json"},
    "SCRIP_IMAGE_DIR": {"kind": "directory", "base_dir_key": "MEDIA_DIR"},
    "SCRIP_MASTER_DB_NAME": {"kind": "save", "base_dir_key": "JSON_DIR", "filetypes": JSON_FILETYPES,
                             "defaultextension": ".json"},

    # Registrar
    "REGISTRAR_RM_DATABASE": {"kind": "open", "base_dir_key": "RM_DIR", "filetypes": RMTREE_FILETYPES},

    # Gazetteer
    "GAZETTEER_RM_DATABASE": {"kind": "open", "base_dir_key": "RM_DIR", "filetypes": RMTREE_FILETYPES},
    "GAZETTEER_SHAPEFILE": {"kind": "open", "base_dir_key": PROGRAM_DIR_SENTINEL, "filetypes": SHP_FILETYPES},

    # PDFix
    "PDFIX_TARGET_DIR": {"kind": "directory", "base_dir_key": "MEDIA_DIR"},
}

# ==========================================
# RICHER FIELD WIDGETS (toggles/segments/sliders instead of plain text entries)
# ==========================================
# Keyed by settings key; any key not listed here keeps the default plain CTkEntry behavior.
FIELD_WIDGETS = {
    # Real booleans in the schema - a switch, not a "True"/"False" text box.
    "GAZETTEER_DEBUG_MODE": {"type": "toggle"},
    "GAZETTEER_CREATE_BACKUP": {"type": "toggle"},
    "PDFIX_CREATE_BACKUP": {"type": "toggle"},
    "PDFIX_REPAIR_MODE": {"type": "toggle"},

    # Small fixed set of labeled options, stored as a numeric string.
    "PALEOGRAPHER_PDF_COMPRESSION_LEVEL": {"type": "segmented",
                                           "options": [("0", "Low"), ("1", "Medium"), ("2", "High")]},
    "PDFIX_COMPRESSION_LEVEL": {"type": "segmented", "options": [("0", "Low"), ("1", "Medium"), ("2", "High")]},

    # Bounded numeric tuning knobs.
    "MIN_MARRIAGE_AGE": {"type": "slider", "min": 0, "max": 30, "step": 1},
    "MAX_SPOUSE_AGE_GAP": {"type": "slider", "min": 0, "max": 50, "step": 1},
    "HUSBAND_CHILD_AGE_GAP_MIN": {"type": "slider", "min": 0, "max": 30, "step": 1},
    "HUSBAND_CHILD_AGE_GAP_MAX": {"type": "slider", "min": 30, "max": 90, "step": 1},
    "WIFE_CHILD_AGE_GAP_MIN": {"type": "slider", "min": 0, "max": 30, "step": 1},
    "WIFE_CHILD_AGE_GAP_MAX": {"type": "slider", "min": 20, "max": 70, "step": 1},
    "REGISTRAR_FUZZY_THRESHOLD": {"type": "slider", "min": 0, "max": 100, "step": 1},
    "REGISTRAR_MAX_AGE_GAP": {"type": "slider", "min": 0, "max": 20, "step": 1},
    "REGISTRAR_FUZZY_THRESHOLD_STRICT": {"type": "slider", "min": 0, "max": 100, "step": 1},
    "REGISTRAR_FAMILY_MATCH_THRESHOLD": {"type": "slider", "min": 0, "max": 100, "step": 1},
    "API_BUDGET": {"type": "slider", "min": 0, "max": 200, "step": 5, "suffix": "$"},
    "CACHE_DISCOUNT_MULTIPLIER": {"type": "slider", "min": 0, "max": 1, "step": 0.05},
    "PDFIX_SIZE_THRESHOLD_MB": {"type": "slider", "min": 0, "max": 100, "step": 1, "suffix": "MB"},
}


# ==========================================
# CUSTOM WIDGET CLASSES
# ==========================================
class ToolTip:
    """Creates a hover tooltip for a given widget, bypassing CtkToplevel bugs using pure tkinter."""

    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.id = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)
        self.widget.bind("<ButtonPress>", self.leave)

    def enter(self, _event=None):
        self.schedule()

    def leave(self, _event=None):
        self.unschedule()
        self.hide()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(400, self.show)

    def unschedule(self):
        id_ = self.id
        self.id = None
        if id_:
            try:
                self.widget.after_cancel(id_)
            except (ValueError, tk.TclError):
                pass

    def show(self):
        self.unschedule()

        # Safety Check 1: Ensure mouse is strictly inside the widget bounds before drawing
        try:
            x, y = self.widget.winfo_pointerxy()
            wx_root = self.widget.winfo_rootx()
            wy_root = self.widget.winfo_rooty()
            w_width = self.widget.winfo_width()
            w_height = self.widget.winfo_height()

            if not (wx_root <= x <= wx_root + w_width and wy_root <= y <= wy_root + w_height):
                return
        except tk.TclError:
            pass

        def tip_pos_calculator(w_widget, tip_label, *, tip_delta=(10, 15), pad=(5, 3, 5, 3)):
            s_width, s_height = w_widget.winfo_screenwidth(), w_widget.winfo_screenheight()
            width, height = (pad[0] + tip_label.winfo_reqwidth() + pad[2],
                             pad[1] + tip_label.winfo_reqheight() + pad[3])
            mouse_x, mouse_y = w_widget.winfo_pointerxy()
            x1, y1 = mouse_x + tip_delta[0], mouse_y + tip_delta[1]
            x2, y2 = x1 + width, y1 + height

            x_delta = x2 - s_width
            if x_delta < 0:
                x_delta = 0
            y_delta = y2 - s_height
            if y_delta < 0:
                y_delta = 0

            offscreen = (x_delta, y_delta) != (0, 0)
            if offscreen:
                if x_delta:
                    x1 = mouse_x - tip_delta[0] - width
                if y_delta:
                    y1 = mouse_y - tip_delta[1] - height
            return x1, y1

        self.hide()

        # FIX: We use a raw tkinter Toplevel instead of CtkToplevel.
        # Ctk intercepts overrideredirect focus events and causes ghost windows.
        self.tooltip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        if sys.platform == 'darwin':
            tw.wm_attributes('-transparent', True)

        # Build the tooltip label
        label = ctk.CTkLabel(tw, text=self.text, justify="left", fg_color="#1a1a1a", text_color="#E0E0E0",
                             corner_radius=8, padx=12, pady=8, font=ctk.CTkFont(size=12))
        label.pack()

        # Position it next to the cursor
        x, y = tip_pos_calculator(self.widget, label)
        tw.wm_geometry(f"+{x}+{y}")

        # Safety Check 2: If the mouse accidentally wanders INTO the tooltip, kill it.
        tw.bind("<Leave>", self.leave)

    def hide(self):
        tw = self.tooltip_window
        self.tooltip_window = None
        if tw:
            try:
                tw.destroy()
            except tk.TclError:
                pass


class ConsoleRedirector:
    """Manages UI updates for streamed console text, routing progress bars appropriately."""

    def __init__(self, text_widget, status_widget, on_progress=None, on_line=None):
        self.text_widget = text_widget
        self.status_widget = status_widget
        self.on_progress = on_progress
        self.on_line = on_line
        self.queue = queue.Queue()
        self.ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        # Paleographer prints "[3/45] Processing file.jpg..." with end="" (no newline),
        # so a single 50ms tick may only see a few characters of it - this buffer
        # accumulates raw text across ticks so the regex still matches once it's complete.
        self._progress_buffer = ""
        self._progress_re = re.compile(r'\[(\d+)/(\d+)\] Processing')
        self.update_gui()

    def put(self, text):
        self.queue.put(text)

    def update_gui(self):
        """Routes transient progress bars to the top entry, and permanent logs below."""
        if self.queue.empty():
            self.text_widget.after(50, self.update_gui)
            return

        self.text_widget.configure(state="normal")

        chars = []
        while not self.queue.empty():
            chars.append(self.queue.get_nowait())

        if chars:
            text_chunk = "".join(chars)
            clean_chunk = self.ansi_escape.sub('', text_chunk)
            clean_chunk = clean_chunk.replace('\r\n', '\n')

            if self.on_progress is not None:
                self._progress_buffer = (self._progress_buffer + clean_chunk)[-500:]
                matches = list(self._progress_re.finditer(self._progress_buffer))
                if matches:
                    current, total = matches[-1].groups()
                    self.on_progress(int(current), int(total))

            if '\r' in clean_chunk:
                parts = clean_chunk.split('\r')
                for i, part in enumerate(parts):
                    if i == 0 and part:
                        self.text_widget.insert("end", part)
                    elif i > 0:
                        if '\n' in part:
                            log_parts = part.rsplit('\n', 1)
                            if log_parts[0]:
                                self.text_widget.insert("end", log_parts[0] + '\n')
                            if len(log_parts) > 1 and log_parts[1]:
                                self.status_widget.configure(state="normal")
                                self.status_widget.delete(0, "end")
                                self.status_widget.insert(0, log_parts[1])
                                self.status_widget.configure(state="readonly")
                        else:
                            self.status_widget.configure(state="normal")
                            self.status_widget.delete(0, "end")
                            self.status_widget.insert(0, part)
                            self.status_widget.configure(state="readonly")
            else:
                self.text_widget.insert("end", clean_chunk)

            if self.on_line is not None:
                lines = [ln for ln in clean_chunk.replace('\r', '\n').split('\n') if ln.strip()]
                if lines:
                    self.on_line(lines[-1])

        try:
            current_lines = int(self.text_widget.index('end-1c').split('.')[0])
            if current_lines > 1500:
                self.text_widget.delete("1.0", f"{current_lines - 1500}.0")
        except (ValueError, TypeError, AttributeError):
            pass

        self.text_widget.see("end")
        self.text_widget.configure(state="disabled")
        self.text_widget.after(50, self.update_gui)


class Scriptorium(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("The Scriptorium")

        # Wider aspect ratio for the main window
        window_width = 1440
        window_height = 720

        # Calculate exact center of the user's monitor
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        center_x = int((screen_width / 2) - (window_width / 2))
        center_y = int((screen_height / 2) - (window_height / 2))

        self.geometry(f"{window_width}x{window_height}+{center_x}+{center_y}")
        self.minsize(1000, 600)  # Prevents scrollbars from squishing to 0 height and crashing

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme(str(BASE_DIR / "assets" / "theme.json"))

        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        self.string_vars: Dict[str, ctk.StringVar] = {}
        # Per-key state ("default"/"blank"/"user") so the settings form can visually tell
        # apart an untouched placeholder, a field deliberately left empty and saved that
        # way, and a real user-entered value - see _build_form_ui's field-state styling.
        self.field_state: Dict[str, str] = {}
        self.active_process = None
        self._cancel_requested = False
        self.debug_file_var = ctk.StringVar(value="")
        self.tabs_built = set()

        self.help_texts = {"Voyageur": "Welcome to Voyageur!\n\n"
                           "Voyageur is the Gather step: it talks to a repository's website and "
                           "brings back whatever it has, images plus any index data the site "
                           "already provides.\n\n"
                           "How to use:\n"
                           "1. Pick which repository to gather from in the dropdown (Ancestry, "
                           "FamilySearch, or LAC for now, more to come).\n"
                           "2. Paste the record/collection URL for that repository into its "
                           "settings box.\n"
                           "3. Click the gather button. Ancestry and FamilySearch open your "
                           "browser and drive a Tampermonkey script there; LAC downloads "
                           "directly.\n\n"
                           "Once gathering finishes, head to Paleographer (if the images need AI "
                           "transcription) or straight to Archivist to build your GEDCOM.\n\n"
                           "\"Gather and Send to Archivist\" runs the gather and then automatically "
                           "builds the GEDCOM as soon as it finishes cleanly, in one click - skip "
                           "this if the images still need Paleographer's AI transcription first.",
                           "Paleographer": "Welcome to Paleographer!\n\n"
                           "Paleographer is the Analysis step: it reads historical document images "
                           "and turns them into structured data using AI.\n\n"
                           "How to use:\n"
                           "1. Pick a record type from the dropdown (Parish, Scrip, or any other "
                           ".pmt file you've added to Paleographer/prompts).\n"
                           "2. Place your historical document images or PDFs into that type's "
                           "designated folder in your project.\n"
                           "3. Ensure you have your Gemini API key saved in the Global Settings.\n"
                           "4. Click 'Run Analysis (API)'. The AI will read, transcribe, and "
                           "translate the records into a database file. Large multi-page documents "
                           "are submitted as a batch job; click the same button again later to "
                           "retrieve the results once Gemini finishes.\n\n"
                           "When finished, head to Archivist to build your GEDCOM.\n\n"
                           "Note: If the AI gets stuck or runs out of memory, try clicking "
                           "'Clear Cache'.",
                           "Archivist": "Welcome to Archivist!\n\n"
                           "Archivist is the Create step: the single place that turns a finished "
                           "JSON file, from Voyageur's Gather or Paleographer's Analysis, into a "
                           "GEDCOM file you can import.\n\n"
                           "How to use:\n"
                           "1. Check your settings (image folder, location overrides, etc).\n"
                           "2. Click 'Generate GEDCOM'. Archivist reads whichever JSON is currently "
                           "configured, automatically detects what kind of record it holds "
                           "(census, church/parish, scrip...), and builds the right GEDCOM without "
                           "you needing to pick a mode.",
                           "Registrar": "Welcome to the Registrar!\n\n"
                           "How to use:\n"
                           "This tool scans your RootsMagic tree for people who might be "
                           "duplicated, using smart name and age matching.\n\n"
                           "1. CRITICAL: Make sure RootsMagic is completely CLOSED before running "
                           "this.\n"
                           "2. Click 'Run Script' and follow the prompts in the console below.\n"
                           "3. The tool will safely create 'Review Merge' tasks inside your "
                           "RootsMagic database. Open RootsMagic and check your Task List to "
                           "see the results!",
                           "Gazetteer": "Welcome to the Gazetteer!\n\n"
                                           "How to use:\n"
                                           "This tool looks at the dates of events in your tree and automatically "
                                           "corrects the County or Territory names to match historical boundaries "
                                           "for that exact year.\n\n"
                                           "1. CRITICAL: Make sure RootsMagic is completely CLOSED before running "
                                           "this.\n"
                                           "2. Make sure you have backed up your tree.\n"
                                           "3. Click 'Run Script'. It will update the display names of your places "
                                           "safely without breaking your maps or tracking IDs.",
                           "PDFix": "Welcome to PDFix!\n\n"
                           "This tool losslessly shrinks the file size of every PDF in a folder (and its "
                           "subfolders), by removing dead internal structure and re-compressing streams. "
                           "It never rescales embedded image resolution.\n\n"
                           "1. Set your PDF Scan Folder, relative to your Base Media Directory.\n"
                           "2. Leave 'Create Backup' on unless you're confident - it rewrites PDFs in "
                           "place.\n"
                           "3. Click 'Run Script' and follow along in the console below.",
                           "Global Settings": "Welcome to Global Settings!\n\n"
                                              "How to use:\n"
                                              "These are the master settings shared across all of your tools.\n\n"
                                              "1. Set your 'PROGRAM_DIR' first. This is the main folder for your "
                                              "genealogy files. All other folder paths build off of this one.\n"
                                              "2. Add your Gemini API Key here so the AI transcription tool can "
                                              "function.\n"
                                              "3. Update your name and organization so the GEDCOM files properly "
                                              "credit your research.\n"
                                              "4. Don't forget to click 'Save Global Config' when you make changes!"}

        self.tab_builders: Dict[str, Callable[[ctk.CTkFrame], None]] = {"Voyageur": self._build_tab_voyageur,
                                                                        "Paleographer": self._build_tab_paleographer,
                                                                        "Archivist": self._build_tab_archivist,
                                                                        "Registrar": self._build_tab_registrar,
                                                                        "Gazetteer": self._build_tab_gazetteer,
                                                                        "PDFix": self._build_tab_pdfix,
                                                                        "Global Settings": self._build_tab_global}

        self._build_layout()
        self._load_env_to_vars()

        # Force a geometry update before building the first tab.
        # This fixes a known CustomTkinter bug where CTkScrollableFrame
        # crashes with a math error if drawn before the window has a height.
        self.update_idletasks()
        self._switch_tab("Voyageur")

    def _on_closing(self):
        """Forcefully terminates the window and kills any zombie threads running in background."""
        if self.active_process and self.active_process.poll() is None:
            try:
                self.active_process.terminate()
                self.active_process.kill()
            except (OSError, subprocess.SubprocessError):
                pass
        self.destroy()
        sys.exit(0)

    def _build_layout(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.main_container = ctk.CTkFrame(self, corner_radius=10)
        self.main_container.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")

        self.main_container.grid_rowconfigure(0, weight=1)
        self.main_container.grid_columnconfigure(0, weight=0)  # sidebar: fixed width
        self.main_container.grid_columnconfigure(1, weight=1)  # main panel: expands

        self._build_sidebar(self.main_container)

        self.main_panel = ctk.CTkFrame(self.main_container, fg_color="transparent")
        self.main_panel.grid(row=0, column=1, sticky="nsew")
        self.main_panel.grid_columnconfigure(0, weight=1)
        self.main_panel.grid_rowconfigure(2, weight=1)  # content_area is the only row that expands

        # Sits above content_area, so it stays visible - and reflects the truth - no matter
        # which tab is active when a background job is running.
        self.status_row = ctk.CTkFrame(self.main_panel, fg_color="transparent")
        self.status_row.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        self.status_row.grid_columnconfigure(1, weight=1)

        self.run_indicator = ctk.CTkLabel(self.status_row, text="●", width=20,
                                          font=ctk.CTkFont(size=16, weight="bold"), text_color=C_TEXT_MUTED)
        self.run_indicator.grid(row=0, column=0, padx=(0, 5))
        self.run_tooltip = ToolTip(self.run_indicator, "Idle - no script running")

        self.status_bar = ctk.CTkEntry(self.status_row, font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
                                       text_color=C_ACCENT, fg_color=C_SURFACE_RAISED, border_width=1,
                                       border_color=C_BORDER)
        self.status_bar.grid(row=0, column=1, sticky="ew")
        self.status_bar.insert(0, "System Ready")
        self.status_bar.configure(state="readonly")

        # Reopens/dismisses the pop-up console at any time, not just while a script is
        # running - lives in status_row (outside content_area) so _recursive_state's
        # disable-while-running pass never touches it.
        self.console_toggle_btn = ctk.CTkButton(self.status_row, text="Console", width=90, height=28,
                                                fg_color="transparent", border_width=1, border_color=C_BORDER,
                                                text_color=C_TEXT, hover_color=C_SURFACE_RAISED,
                                                command=self._toggle_console)
        self.console_toggle_btn.grid(row=0, column=2, padx=(8, 0))

        # A dedicated row (not just a bare progress bar) so it can carry an explicit height
        # and a live percentage readout - a plain default-height CTkProgressBar reads as
        # nearly invisible against the surface color.
        self.progress_row = ctk.CTkFrame(self.main_panel, fg_color="transparent")
        self.progress_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(8, 0))
        self.progress_row.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(self.progress_row, mode="determinate", height=16,
                                               progress_color=C_ACCENT, fg_color=C_SURFACE)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=0, column=0, sticky="ew")

        self.progress_pct_label = ctk.CTkLabel(self.progress_row, text="0%", width=36,
                                               font=ctk.CTkFont(size=12, weight="bold"), text_color=C_TEXT_MUTED)
        self.progress_pct_label.grid(row=0, column=1, padx=(10, 0))

        self.progress_row.grid_remove()  # hidden until a run reports real [i/total] progress

        # --- content area: one frame per tab, created lazily on first visit and tkraise()'d
        # by _switch_tab instead of a CTkTabview tab strip. ---
        self.content_area = ctk.CTkFrame(self.main_panel, fg_color="transparent")
        self.content_area.grid(row=2, column=0, sticky="nsew", padx=10, pady=(5, 5))
        self.content_area.grid_rowconfigure(0, weight=1)
        self.content_area.grid_columnconfigure(0, weight=1)
        self.content_area.bind("<Configure>", self._on_content_area_resize)

        self.tab_frames: Dict[str, ctk.CTkFrame] = {}
        # Keyed by each tab's own content frame -> that tab's _build_tab_header() frame, so
        # the console overlay below can measure exactly how tall THIS tab's title+description
        # rendered (it varies - description length differs per tab) and cover only the body
        # beneath it, never the header itself.
        self.tab_header_frames: Dict[ctk.CTkFrame, ctk.CTkFrame] = {}

        # --- pop-up console: hidden by default, raised over the active tab's body (leaving
        # that tab's own header visible) the moment execute_script starts a job. A sibling of
        # the tab frames inside content_area, shown/hidden via place()/place_forget() instead
        # of grid, so it never claims a grid slot of its own. ---
        self.console_overlay = ctk.CTkFrame(self.content_area, fg_color=C_SURFACE, corner_radius=8,
                                            border_width=1, border_color=C_ACCENT)
        self.console_overlay.grid_rowconfigure(1, weight=1)
        self.console_overlay.grid_columnconfigure(0, weight=1)
        self._console_expanded = False

        overlay_hdr = ctk.CTkFrame(self.console_overlay, fg_color="transparent")
        overlay_hdr.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        ctk.CTkLabel(overlay_hdr, text="Console", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=C_TEXT).pack(side="left")
        self._console_status_label = ctk.CTkLabel(
            overlay_hdr, text="", font=ctk.CTkFont(size=12), text_color=C_TEXT_MUTED)
        self._console_status_label.pack(side="left", padx=(8, 0))
        # A click-bound label, not a CTkButton - _recursive_state only disables CTkButtons
        # while a script runs, so this stays clickable to dismiss the overlay mid-run.
        back_label = ctk.CTkLabel(overlay_hdr, text="Back to Settings  ▲", font=ctk.CTkFont(size=12, weight="bold"),
                                  text_color=C_ACCENT, cursor="hand2")
        back_label.pack(side="right")
        back_label.bind("<Button-1>", self._toggle_console)

        # Set fixed fallback dimensions to prevent 0-height rendering geometry crash
        self.console_text = ctk.CTkTextbox(self.console_overlay, font=ctk.CTkFont(family="Consolas", size=12),
                                           text_color=C_SUCCESS, width=800, height=220)
        self.console_text.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 10))
        self.console_text.configure(state="disabled")

        self.input_frame = ctk.CTkFrame(self.console_overlay, fg_color="transparent")
        self.input_frame.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 18))
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.console_input = ctk.CTkEntry(self.input_frame, height=32,
                                          placeholder_text="Type script input here and press Enter...",
                                          state="disabled")
        self.console_input.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.console_input.bind("<Return>", self.send_input)

        self.cancel_btn = ctk.CTkButton(self.input_frame, text="Cancel", fg_color=C_DANGER, hover_color=C_DANGER_HOVER,
                                        text_color=C_ON_ACCENT, width=80, height=32,
                                        state="disabled", command=self.cancel_script)
        self.cancel_btn.grid(row=0, column=1)

        self.console = ConsoleRedirector(self.console_text, self.status_bar,
                                         on_progress=self._on_progress_update, on_line=self._on_console_line)

    def _build_sidebar(self, parent):
        """Left nav rail replacing the old top CTkTabview: a plain (non-scrolling) list of
        the pipeline tools (Voyageur/Paleographer/Archivist, ungrouped) plus a labeled
        Utilities group (Registrar/Gazetteer/PDFix) and a footer pinned to the bottom (Help,
        Global Settings). Text-only nav items - no icons, no pipeline connector marks.
        A plain frame (not CTkScrollableFrame) for the nav list - six items plus one group
        label comfortably fit the sidebar's height without ever needing to scroll."""
        # width= + grid_propagate(False): without this, CTkFrame shrinks itself to fit its
        # children's natural size regardless of sticky="nsew", so the dark background
        # wouldn't fill the sidebar's full column.
        self.sidebar = ctk.CTkFrame(parent, fg_color=C_SURFACE, corner_radius=8, width=210)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.sidebar.grid_propagate(False)

        self.nav_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.nav_frame.pack(side="top", fill="x", padx=8, pady=(14, 4))

        ctk.CTkLabel(self.nav_frame, text="Scriptorium", font=ctk.CTkFont(family="Georgia", size=17, weight="bold")
                     ).pack(anchor="w", padx=6, pady=(0, 14))

        self._nav_buttons: Dict[str, ctk.CTkButton] = {}

        def add_group_label(text):
            ctk.CTkLabel(self.nav_frame, text=text.upper(), font=ctk.CTkFont(size=10, weight="bold"),
                         text_color=C_TEXT_MUTED).pack(anchor="w", padx=6, pady=(10, 4))

        def add_nav_button(container, tab_name, command=None):
            btn = ctk.CTkButton(container, text=tab_name, anchor="w", fg_color="transparent",
                                hover_color=C_SURFACE_RAISED, text_color=C_TEXT,
                                command=command or partial(self._switch_tab, tab_name))
            btn.pack(fill="x", pady=1)
            self._nav_buttons[tab_name] = btn
            return btn

        add_nav_button(self.nav_frame, "Voyageur")
        add_nav_button(self.nav_frame, "Paleographer")
        add_nav_button(self.nav_frame, "Archivist")

        add_group_label("Utilities")
        add_nav_button(self.nav_frame, "Registrar")
        add_nav_button(self.nav_frame, "Gazetteer")
        add_nav_button(self.nav_frame, "PDFix")

        self.sidebar_footer = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.sidebar_footer.pack(side="bottom", fill="x", padx=8, pady=(4, 14))
        ctk.CTkFrame(self.sidebar_footer, height=1, fg_color=C_BORDER).pack(fill="x", pady=(0, 6))
        add_nav_button(self.sidebar_footer, "Help", command=self._show_current_help)
        # "Global Settings" doubles as both a real tab_name (drives _switch_tab / active-
        # highlight bookkeeping the same as any other nav button) and its own settings form.
        add_nav_button(self.sidebar_footer, "Global Settings")

    def _switch_tab(self, tab_name):
        """Replaces CTkTabview's own tab switching: lazily creates a tab's own frame and
        builds its content into it on first visit, raises it, and updates which sidebar
        nav button reads as active."""
        self.current_tab_name = tab_name
        if tab_name not in self.tab_frames:
            frame = ctk.CTkFrame(self.content_area, fg_color="transparent")
            frame.grid(row=0, column=0, sticky="nsew")
            self.tab_frames[tab_name] = frame
        frame = self.tab_frames[tab_name]
        if tab_name not in self.tabs_built:
            self.tab_builders[tab_name](frame)
            self.tabs_built.add(tab_name)
        frame.tkraise()
        if self._console_expanded:
            # frame.tkraise() just restacked this tab above the overlay too (they're
            # siblings in content_area) - if the console was left open while switching
            # tabs, re-show it on top, repositioned for the new tab's own header height.
            self._show_console_overlay()
        for name, btn in self._nav_buttons.items():
            if name == tab_name:
                btn.configure(fg_color=C_ACCENT, text_color=C_ON_ACCENT)
            elif name != "Help":
                btn.configure(fg_color="transparent", text_color=C_TEXT)

    def _show_current_help(self):
        """The sidebar's single Help entry point - always shows whichever tab is actually
        on screen right now."""
        self.show_help(getattr(self, "current_tab_name", "Voyageur"))

    def _toggle_console(self, _event=None):
        self._console_expanded = not self._console_expanded
        if self._console_expanded:
            self._show_console_overlay()
        else:
            self.console_overlay.place_forget()

    def _show_console_overlay(self):
        """Positions the pop-up console to cover the active tab's body while leaving that
        tab's own title/description header visible above it - header height is measured
        live (not hardcoded) since description text length, and therefore wrapped height,
        differs per tab. CTk's place() rejects literal width/height (they can only be set
        at widget construction), so the vertical offset is expressed as a relheight
        fraction of content_area's own current height instead of a pixel height."""
        self.update_idletasks()
        header = self.tab_header_frames.get(self.tab_frames.get(self.current_tab_name))
        header_h = header.winfo_height() + 4 if header else 0
        content_h = self.content_area.winfo_height()
        frac = max(0.05, (content_h - header_h) / content_h) if content_h > 0 else 1.0
        self.console_overlay.place(relx=0, rely=0, relwidth=1, relheight=frac, x=0, y=header_h)
        self.console_overlay.lift()

    def _on_content_area_resize(self, _event=None):
        """content_area's own <Configure> fires on window resize - reposition the overlay
        (its relheight fraction was computed from a specific content_area height, so it
        drifts as the window is resized) only while it's actually showing."""
        if self._console_expanded:
            self._show_console_overlay()

    def _expand_console(self):
        """Called by execute_script the moment a job actually starts, so first-run output
        is never silently missed behind a dismissed console - collapsing back is left to
        the user via the status row's Console toggle."""
        self._console_expanded = True
        self._show_console_overlay()

    def _on_console_line(self, line):
        self._console_status_label.configure(text=line[:100])

    def _on_progress_update(self, current, total):
        """Fed by ConsoleRedirector whenever it spots Paleographer's own
        "[i/total] Processing ..." line in the streamed output."""
        if total <= 0:
            return
        self.progress_row.grid()
        pct = min(1.0, current / total)
        self.progress_bar.set(pct)
        self.progress_pct_label.configure(text=f"{int(pct * 100)}%")

    def send_input(self, _event=None):
        if self.active_process and self.active_process.poll() is None:
            user_text = self.console_input.get()
            try:
                self.console.put(f"{user_text}\n")
                self.active_process.stdin.write((user_text + "\n").encode('utf-8'))
                self.active_process.stdin.flush()
                self.console_input.delete(0, 'end')
            except (OSError, BrokenPipeError, AttributeError) as e:
                self.console.put(f"\n[System] Failed to send input: {e}\n")

    def cancel_script(self):
        if self.active_process and self.active_process.poll() is None:
            self._cancel_requested = True
            self.console.put("\n[System] Sending termination signal to process...\n")
            self.active_process.terminate()

    def _load_env_to_vars(self):
        for category_dict, subfolder in ENV_TARGETS:
            saved = dotenv_values(env_path_for(subfolder))
            for fields in category_dict.values():
                for key, default_val in fields.items():
                    # `key in saved` (not `saved.get(key) or default_val`) - a key the user
                    # deliberately blanked and saved is present in the file with value "",
                    # which is falsy in Python; `or default_val` was silently reviving the
                    # placeholder default every time settings loaded, making it impossible
                    # to actually test/run with a field left blank on purpose. Only a key
                    # genuinely absent from the file (never saved at all) falls back to the
                    # placeholder default now.
                    val = saved[key] if key in saved else default_val
                    self.string_vars[key] = ctk.StringVar(value=val)
                    if key not in saved:
                        self.field_state[key] = "default"
                    elif saved[key] == "":
                        self.field_state[key] = "blank"
                    else:
                        self.field_state[key] = "user"

    def _save_env(self):
        for category_dict, subfolder in ENV_TARGETS:
            env_path = env_path_for(subfolder)
            env_path.parent.mkdir(parents=True, exist_ok=True)
            for fields in category_dict.values():
                for key in fields.keys():
                    clean_val = self.string_vars[key].get().replace('\\', '/')
                    set_key(str(env_path), key, clean_val)
        self.console.put("\n[System] Environment variables saved (global settings to the root .env, "
                         "each tool's settings to its own subfolder).\n")

    def show_help(self, tab_name):
        """Displays a clean pop-up window with help instructions."""
        help_window = ctk.CTkToplevel(self)
        help_window.title(f"Help: {tab_name}")
        help_window.geometry("550x380")
        help_window.attributes('-topmost', True)  # Keeps the window easily accessible on top

        title = ctk.CTkLabel(help_window, text=f"How to use: {tab_name}", font=ctk.CTkFont(size=20, weight="bold"))
        title.pack(pady=(20, 10), padx=20, anchor="w")

        help_text = self.help_texts.get(tab_name, "Help information is unavailable.")

        textbox = ctk.CTkTextbox(help_window, wrap="word", font=ctk.CTkFont(size=14))
        textbox.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        textbox.insert("1.0", help_text)
        textbox.configure(state="disabled")  # Make read-only

    @staticmethod
    def _clean_label(key_str: str) -> str:
        """Converts UPPER_SNAKE_CASE to friendly Title Case, or uses a custom override."""
        if key_str in CUSTOM_LABELS:
            return CUSTOM_LABELS[key_str]

        # Handle some specific acronyms nicely
        cleaned = key_str.replace("URL", "Url").replace("JSON", "Json").replace("ID", "Id")
        cleaned = cleaned.replace("_", " ").title()
        return cleaned

    def _build_tab_header(self, frame: ctk.CTkFrame, title: str, role_tag: str, description: str):
        """A helper method to standardize tab headers and eliminate duplicate code."""
        header_frame = ctk.CTkFrame(frame, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 4))

        title_row = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_row.pack(fill="x")
        ctk.CTkLabel(title_row, text=title, font=ctk.CTkFont(family="Georgia", size=24, weight="bold")
                     ).pack(side="left")
        ctk.CTkLabel(title_row, text=role_tag, font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
                     fg_color=C_BRASS_SOFT, text_color=C_BRASS, corner_radius=4, padx=8, pady=2
                     ).pack(side="left", padx=(10, 0))
        # Outline/secondary style, not filled - this is a secondary action on every tab
        # (the tab's own primary action already saves everything too, via execute_script's
        # own _save_env() call), not the one thing this screen is for.
        ctk.CTkButton(title_row, text="Save Config", fg_color="transparent", hover_color=C_SURFACE_RAISED,
                      border_width=1, border_color=C_BRASS, text_color=C_BRASS,
                      command=self._save_env).pack(side="right", padx=5)

        ctk.CTkLabel(header_frame, text=description, font=ctk.CTkFont(size=13), text_color=C_TEXT_MUTED,
                     anchor="w", justify="left", wraplength=760).pack(fill="x", pady=(6, 0))

        # Recorded so the pop-up console overlay can measure this tab's actual rendered
        # header height (it varies - description length differs per tab) and cover only the
        # body beneath it, never the header itself.
        self.tab_header_frames[frame] = header_frame

    def _create_action_box(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        """A helper method to standardize the action button frames and reduce code duplication."""
        btn_box = ctk.CTkFrame(parent, fg_color="transparent")
        btn_box.pack(side="bottom", fill="x", pady=10)  # Docked to bottom to prevent clipping
        return btn_box

    def _build_form_ui(self, parent, schema_dict, skip_keys: Optional[set] = None):
        # CTkScrollableFrame doesn't reliably grow past its constructed height from
        # pack(fill="both", expand=True) alone (a known CustomTkinter limitation) - it just
        # stays at this small initial height, with the rest of the tab left as dead, unused
        # space below it. Given a starting size here since the widget needs one to exist at
        # all; _resize_scroll below recomputes it to actually fill the tab once real
        # dimensions are known, and again on every resize.
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent", width=800, height=200)
        scroll.pack(side="top", fill="both", expand=True, pady=10)
        skip_keys = skip_keys or set()

        def _resize_scroll(_event=None):
            parent.update_idletasks()
            # Actual height of every other direct child sharing this same parent frame (the
            # tab header, the docked action-button box) - measured directly rather than
            # guessed as a fixed constant, since that varies per tab.
            siblings_height = sum(
                child.winfo_height() for child in parent.winfo_children() if child is not scroll
            )
            available = parent.winfo_height() - siblings_height - 20
            if available > 100:
                scroll.configure(height=available)

        parent.bind("<Configure>", _resize_scroll)
        parent.after(50, _resize_scroll)

        for section_index, (section, fields) in enumerate(schema_dict.items()):
            visible_keys = [k for k in fields.keys() if k not in skip_keys]
            if not visible_keys:
                continue

            header = ctk.CTkFrame(scroll, fg_color="transparent", cursor="hand2")
            header.pack(fill="x", pady=(15, 5))
            arrow_lbl = ctk.CTkLabel(header, text="", font=ctk.CTkFont(size=16, weight="bold"),
                                     text_color=C_ACCENT, width=16)
            arrow_lbl.pack(side="left")
            ctk.CTkLabel(header, text=section, font=ctk.CTkFont(size=16, weight="bold"),
                         text_color=C_ACCENT).pack(side="left")

            content = ctk.CTkFrame(scroll, fg_color="transparent")

            # First section open by default (most forms are short enough that this alone
            # is already usable); the rest start collapsed so a field-heavy tab isn't one
            # long wall of every setting scrolled past to find the one that matters.
            expanded = {"state": section_index == 0}

            def render_content():
                for key in visible_keys:
                    row = ctk.CTkFrame(content, fg_color="transparent")
                    row.pack(fill="x", pady=2)

                    # Generate hoverable, friendly labels
                    desc = TOOLTIP_DESCRIPTIONS.get(key)
                    friendly_name = self._clean_label(key)
                    display_text = f"{friendly_name} ⓘ" if desc else friendly_name

                    lbl = ctk.CTkLabel(row, text=display_text, width=250, anchor="w",
                                       cursor="hand2" if desc else "arrow")
                    lbl.pack(side="left", padx=5)

                    if desc:
                        ToolTip(lbl, desc)

                    widget_spec = FIELD_WIDGETS.get(key)

                    if widget_spec is None:
                        # Field-state styling: a value never explicitly saved (still just
                        # the placeholder default) renders dimmed, so it reads as a
                        # suggestion rather than real configuration; a deliberately-blanked,
                        # saved value gets an explicit hint instead of just looking like an
                        # empty box that was never filled in; a real saved value renders
                        # normally. Only meaningful for a plain text entry - a switch/
                        # slider/segment always shows a concrete position, with no real
                        # equivalent of a grayed-out placeholder.
                        state = self.field_state.get(key, "user")
                        entry = ctk.CTkEntry(row, textvariable=self.string_vars[key],
                                             text_color=C_TEXT_MUTED if state == "default" else None,
                                             placeholder_text="(intentionally blank)" if state == "blank" else "")
                        entry.pack(side="left", fill="x", expand=True, padx=5)

                        def _on_edit(_name, _index, _mode, key=key, entry=entry):
                            # Once the user actually types something, this is no longer
                            # just a placeholder default sitting there unedited - promote
                            # it visually to a real, normal-colored value immediately, not
                            # just on next load.
                            if self.field_state.get(key) == "default":
                                self.field_state[key] = "user"
                                entry.configure(text_color=None)

                        self.string_vars[key].trace_add("write", _on_edit)

                        picker = PATH_PICKER_FIELDS.get(key)
                        if picker:
                            ctk.CTkButton(row, text="Browse...", width=90,
                                          command=partial(self._browse_for_path, key, picker)
                                          ).pack(side="left", padx=5)
                    elif widget_spec["type"] == "toggle":
                        ctk.CTkSwitch(row, text="", variable=self.string_vars[key],
                                      onvalue="True", offvalue="False").pack(side="left", padx=5)
                    elif widget_spec["type"] == "segmented":
                        self._build_segmented_field(row, key, widget_spec)
                    elif widget_spec["type"] == "slider":
                        self._build_slider_field(row, key, widget_spec)

            render_content()

            # Every one of these must capture this iteration's own header/content/arrow_lbl/
            # expanded as default-argument values, not as ordinary closure-over-loop-variable
            # references - a plain `for` loop reuses the same local variable slots on every
            # pass, so a closure that only *reads* them (rather than binding them as defaults
            # at definition time) would have every section's click handler end up acting on
            # whichever section happened to be built last.
            def apply_expanded_state(expanded=expanded, arrow_lbl=arrow_lbl, content=content, header=header):
                arrow_lbl.configure(text="▼" if expanded["state"] else "▶")
                if expanded["state"]:
                    content.pack(fill="x", after=header)
                else:
                    content.pack_forget()

            def toggle(_event=None, expanded=expanded, apply_expanded_state=apply_expanded_state):
                expanded["state"] = not expanded["state"]
                apply_expanded_state()

            header.bind("<Button-1>", toggle)
            arrow_lbl.bind("<Button-1>", toggle)
            for child in header.winfo_children():
                child.bind("<Button-1>", toggle)

            apply_expanded_state()

    def _build_segmented_field(self, row, key, widget_spec):
        """Renders a FIELD_WIDGETS "segmented" field: a small fixed set of (stored_value,
        display_label) pairs, e.g. compression level "0"/"1"/"2" shown as Low/Medium/High."""
        options = widget_spec["options"]
        value_to_label = dict(options)
        label_to_value = {label: value for value, label in options}
        seg_var = ctk.StringVar(value=value_to_label.get(self.string_vars[key].get(), options[0][1]))

        def _on_segment(selected_label):
            self.string_vars[key].set(label_to_value.get(selected_label, self.string_vars[key].get()))

        ctk.CTkSegmentedButton(row, values=[label for _, label in options], variable=seg_var,
                               command=_on_segment).pack(side="left", padx=5)

    def _build_slider_field(self, row, key, widget_spec):
        """Renders a FIELD_WIDGETS "slider" field: a bounded numeric tuning knob with a live,
        directly-editable readout, still just reading/writing the same string-valued setting."""
        lo, hi = widget_spec["min"], widget_spec["max"]
        step = widget_spec.get("step", 1)
        suffix = widget_spec.get("suffix", "")
        try:
            current_val = float(self.string_vars[key].get())
        except ValueError:
            current_val = lo

        value_var = ctk.StringVar(value=f"{current_val:g}{suffix}")
        value_entry = ctk.CTkEntry(row, textvariable=value_var, width=70, justify="right")
        value_entry.pack(side="right", padx=(5, 0))

        def _apply_typed_value(_event=None):
            raw = value_var.get().strip()
            if suffix and raw.endswith(suffix.strip()):
                raw = raw[:-len(suffix.strip())].strip()
            try:
                typed = float(raw)
            except ValueError:
                value_var.set(f"{slider.get():g}{suffix}")
                return
            rounded = round(max(lo, min(hi, typed)) / step) * step
            slider.set(rounded)
            value_var.set(f"{rounded:g}{suffix}")
            self.string_vars[key].set(f"{rounded:g}")

        value_entry.bind("<Return>", _apply_typed_value)
        value_entry.bind("<FocusOut>", _apply_typed_value)

        def _on_slide(new_val):
            rounded = round(new_val / step) * step
            value_var.set(f"{rounded:g}{suffix}")
            self.string_vars[key].set(f"{rounded:g}")

        steps = max(1, round((hi - lo) / step))
        slider = ctk.CTkSlider(row, from_=lo, to=hi, number_of_steps=steps, command=_on_slide)
        slider.set(current_val)
        slider.pack(side="left", fill="x", expand=True, padx=5)
        # CTkSlider binds MouseWheel-over-the-slider (on its internal canvas) to change its
        # own value by default - this hijacks scrolling the settings page whenever the
        # cursor merely passes over a slider on the way down. No public API to disable it,
        # so unbind directly.
        slider._canvas.unbind("<MouseWheel>")

    def _resolve_base_dir(self, base_dir_key: str) -> str:
        """Resolves a directory setting (like JSON_DIR) against PROGRAM_DIR the same way
        execute_script does, so a file browser opens in the same folder the script itself
        will actually look in. The two sentinels resolve to PROGRAM_DIR's own current value
        and to the toolbox's own code folder, respectively, since neither is itself a
        directory setting nested inside another."""
        prog_dir_var = self.string_vars.get("PROGRAM_DIR")
        program_dir = prog_dir_var.get().strip() if prog_dir_var is not None else ""
        if base_dir_key == TOOLBOX_DIR_SENTINEL:
            return str(BASE_DIR)
        if base_dir_key == PROGRAM_DIR_SENTINEL:
            return program_dir or os.getcwd()
        base_var = self.string_vars.get(base_dir_key)
        base_setting = base_var.get().strip() if base_var is not None else ""
        if not base_setting:
            return program_dir or os.getcwd()
        if os.path.isabs(base_setting):
            return base_setting
        return os.path.join(program_dir, base_setting) if program_dir else base_setting

    def _browse_for_path(self, key: str, picker: dict):
        """Opens the dialog matching the field's picker "kind", then stores the result back
        into its StringVar - relative to the field's own base folder when possible (matching
        how these fields are normally typed in), or as a full path for anything picked from
        outside that folder."""
        base_dir = self._resolve_base_dir(picker["base_dir_key"])
        kind = picker.get("kind", "open")
        title = f"Select {self._clean_label(key)}"
        initial_dir = base_dir if os.path.isdir(base_dir) else None

        if kind == "directory":
            selected = filedialog.askdirectory(title=title, initialdir=initial_dir)
        elif kind == "save":
            current_name = os.path.basename(self.string_vars[key].get().strip())
            selected = filedialog.asksaveasfilename(
                title=title, initialdir=initial_dir, initialfile=current_name or None,
                defaultextension=picker.get("defaultextension", ""),
                filetypes=picker.get("filetypes", [("All files", "*.*")]))
        else:
            selected = filedialog.askopenfilename(
                title=title, initialdir=initial_dir,
                filetypes=picker.get("filetypes", [("All files", "*.*")]))

        if not selected:
            return

        selected_path = Path(selected).resolve()
        if picker.get("always_absolute"):
            self.string_vars[key].set(str(selected_path).replace("\\", "/"))
            return

        try:
            rel = selected_path.relative_to(Path(base_dir).resolve())
            self.string_vars[key].set(str(rel).replace("\\", "/"))
        except ValueError:
            self.string_vars[key].set(str(selected_path).replace("\\", "/"))

    def _build_tab_global(self, frame: ctk.CTkFrame):
        self._build_tab_header(frame, "Global Settings", "SHARED",
                               "The API key, folders, and researcher credit every tool above shares, "
                               "so you only enter them once.")

        # Build buttons first so they dock safely to the bottom
        self._create_action_box(frame)

        self._build_form_ui(frame, GLOBAL_VARS)

    def _build_tab_archivist(self, frame: ctk.CTkFrame):
        self._build_tab_header(frame, "Archivist", "BUILD",
                               "Turns gathered or transcribed records into a sourced GEDCOM file, working out "
                               "who belongs to which family from ages, roles, and household position.")

        # Unified action buttons (Docked to bottom)
        btn_box = self._create_action_box(frame)
        ctk.CTkButton(btn_box, text="Generate GEDCOM", fg_color="#2b7a4b", hover_color="#1e5935",
                      command=lambda: self.execute_script("ARCHIVIST_SCRIPT", "gedcom_auto")).pack(side="left",
                                                                                                   padx=5)

        self._build_form_ui(frame, ARCHIVIST_VARS)

    @staticmethod
    def _list_record_types() -> List[str]:
        """Lists every .pmt file in Paleographer/prompts, for the record-type dropdown.
        Adding a new record type is exactly this: drop a new .pmt file in that folder,
        nothing else, and it shows up here automatically."""
        prompts_dir = Path(__file__).resolve().parent / "Paleographer" / "prompts"
        if not prompts_dir.is_dir():
            return ["Parish.pmt"]
        found = sorted((p.name for p in prompts_dir.glob("*.pmt")), key=str.lower)
        return found or ["Parish.pmt"]

    @staticmethod
    def _read_pmt_front_matter(record_type_value: str) -> dict:
        """Reads a .pmt file's own YAML front matter directly - the same declarative data
        Paleographer.py/Archivist.py themselves read (via engine.parse_type_config /
        apply_record_type_field_remap) to resolve their own settings and vocabulary. The
        GUI shell has no hardcoded knowledge of what a record type means; it only ever
        reads whatever that record type's own file declares. Returns {} for a .pmt that
        doesn't exist or can't be parsed."""
        name = record_type_value.strip() or "Parish.pmt"
        if not name.endswith(".pmt"):
            name += ".pmt"
        pmt_path = Path(__file__).resolve().parent / "Paleographer" / "prompts" / name
        try:
            raw = pmt_path.read_text(encoding="utf-8")
        except OSError:
            return {}

        stripped = raw.lstrip()
        if not stripped.startswith("---"):
            return {}
        parts = stripped.split("---", 2)
        if len(parts) < 3:
            return {}
        try:
            return yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            return {}

    def _get_pmt_settings_sections(self, record_type_value: str) -> List[str]:
        """Reads the settings_sections a .pmt's own front matter declares (if any), telling
        the Paleographer tab which PALEOGRAPHER_VARS sections are actually relevant for
        that record type. Undeclared (or unparseable) returns an empty list, meaning "show
        everything" - so older or hand-edited .pmt files don't lose fields by omission."""
        sections = self._read_pmt_front_matter(record_type_value).get("settings_sections")
        return list(sections) if sections else []

    def _get_pmt_field_remap(self, record_type_value: str) -> Dict[str, str]:
        """Reads the field_remap a .pmt's own front matter declares (prefixed settings-tab
        key -> generic runtime name Paleographer.py/Archivist.py each read from their own
        .env - see Parish.pmt/Scrip.pmt). The GUI only ever needs this for its own display
        purposes (e.g. picking the right image-dir field to browse from); the scripts
        resolve it themselves at runtime regardless of whether Scriptorium is involved."""
        return self._read_pmt_front_matter(record_type_value).get("field_remap") or {}

    def _on_record_type_change(self, _value: Optional[str] = None):
        """Rebuilds the settings form to only show the fields the selected .pmt's own
        settings_sections declares as relevant, instead of every Paleographer field for
        every record type."""
        record_type = self.string_vars["PALEOGRAPHER_RECORD_TYPE"].get()

        if hasattr(self, "paleographer_form_container"):
            for child in self.paleographer_form_container.winfo_children():
                child.destroy()
            sections = self._get_pmt_settings_sections(record_type)
            filtered = {name: fields for name, fields in PALEOGRAPHER_VARS.items()
                        if not sections or name in sections}
            self._build_form_ui(self.paleographer_form_container, filtered,
                                skip_keys={"PALEOGRAPHER_RECORD_TYPE"})

    def _build_tab_paleographer(self, frame: ctk.CTkFrame):
        self._build_tab_header(frame, "Paleographer", "TRANSCRIBE",
                               "Reads scanned parish registers and scrip records with AI, transcribing and "
                               "translating the handwriting into structured entries.")

        type_frame = ctk.CTkFrame(frame, fg_color="transparent")
        type_frame.pack(side="top", fill="x", pady=(10, 5))
        type_lbl = ctk.CTkLabel(type_frame, text="Record Type ⓘ", font=ctk.CTkFont(weight="bold"), cursor="hand2")
        type_lbl.pack(side="left")
        ToolTip(type_lbl, TOOLTIP_DESCRIPTIONS["PALEOGRAPHER_RECORD_TYPE"])
        ctk.CTkComboBox(type_frame, values=self._list_record_types(),
                        variable=self.string_vars["PALEOGRAPHER_RECORD_TYPE"], width=300,
                        command=self._on_record_type_change).pack(side="left", padx=10)

        debug_frame = ctk.CTkFrame(frame, fg_color="transparent")
        debug_frame.pack(side="top", fill="x", pady=(10, 5))
        ctk.CTkLabel(debug_frame, text="Debug Filename (Leave blank for Batch):",
                     font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkEntry(debug_frame, textvariable=self.debug_file_var, width=300).pack(side="left", padx=10)
        ctk.CTkButton(debug_frame, text="Browse...", width=90,
                      command=self._browse_debug_file).pack(side="left")

        # Unified action buttons (Docked to bottom)
        btn_box = self._create_action_box(frame)
        ctk.CTkButton(btn_box, text="Run Analysis (API)", fg_color="#3B8ED0", hover_color="#2b7a4b",
                      command=lambda: self.execute_script("ANALYSIS_SCRIPT", "paleographer_api")
                      ).pack(side="left", padx=5)
        ctk.CTkButton(btn_box, text="Clear Cache", fg_color="#991b1b", hover_color="#7f1d1d",
                      command=lambda: self.execute_script("CLEANUP_CACHE_SCRIPT", "standalone")).pack(side="right",
                                                                                                      padx=5)

        # Persistent container the filtered settings form gets rebuilt into whenever the
        # Record Type changes, so switching types only shows the fields that type uses.
        self.paleographer_form_container = ctk.CTkFrame(frame, fg_color="transparent")
        self.paleographer_form_container.pack(side="top", fill="both", expand=True)

        self._on_record_type_change()

    def _browse_debug_file(self):
        """Opens a file browser rooted in whichever image folder the current Record Type
        actually reads from (nested under MEDIA_DIR - mirroring how each script resolves
        its own IMAGE_DIR), storing just the bare filename since that's what Paleographer.py
        compares DEBUG_FILE against. Which prefixed key that is comes directly from the
        active .pmt's own field_remap declaration - never a hardcoded record-type name."""
        record_type = self.string_vars["PALEOGRAPHER_RECORD_TYPE"].get()
        field_remap = self._get_pmt_field_remap(record_type)
        image_dir_key = next((src for src, dst in field_remap.items() if dst == "IMAGE_DIR"), "CHURCH_IMAGE_DIR")
        media_base = self._resolve_base_dir("MEDIA_DIR")
        image_dir_var = self.string_vars.get(image_dir_key)
        image_setting = image_dir_var.get().strip() if image_dir_var is not None else ""
        if image_setting and os.path.isabs(image_setting):
            source_dir = image_setting
        else:
            source_dir = os.path.join(media_base, image_setting) if image_setting else media_base

        selected = filedialog.askopenfilename(
            title="Select Debug Image File", initialdir=source_dir if os.path.isdir(source_dir) else None,
            filetypes=[("Image/PDF files", "*.jpg *.jpeg *.png *.tif *.tiff *.pdf"), ("All files", "*.*")])
        if not selected:
            return
        self.debug_file_var.set(os.path.basename(selected))

    @staticmethod
    def _voyageur_label_for_code(code: str) -> str:
        return next((label for c, label in VOYAGEUR_SOURCES if c == code), VOYAGEUR_SOURCES[0][1])

    @staticmethod
    def _voyageur_code_for_label(label: str) -> str:
        return next((c for c, lbl in VOYAGEUR_SOURCES if lbl == label), VOYAGEUR_SOURCES[0][0])

    def _on_voyageur_source_change(self, _value: Optional[str] = None):
        """Rebuilds the settings form and gather button to match the selected repository -
        each source only shows its own settings section, mirroring how Paleographer's Record
        Type dropdown filters its own form down to one .pmt's declared sections."""
        label = self.string_vars["VOYAGEUR_SOURCE"].get() or VOYAGEUR_SOURCES[0][1]
        code = self._voyageur_code_for_label(label)

        if hasattr(self, "voyageur_gather_btn"):
            self.voyageur_gather_btn.configure(text=f"Gather from {label}",
                                               command=lambda: self.execute_script("VOYAGEUR_SCRIPT", code))

        if hasattr(self, "voyageur_send_to_archivist_btn"):
            # Chains straight into Generate GEDCOM (the same "gedcom_auto" mode the
            # Archivist tab's own button uses) only once the gather actually finishes
            # cleanly - see execute_script's on_success.
            self.voyageur_send_to_archivist_btn.configure(
                command=lambda: self.execute_script(
                    "VOYAGEUR_SCRIPT", code,
                    on_success=lambda: self.execute_script("ARCHIVIST_SCRIPT", "gedcom_auto")))

        if hasattr(self, "voyageur_form_container"):
            for child in self.voyageur_form_container.winfo_children():
                child.destroy()
            if code == "Merged":
                # Needs both source's URL fields at once, not just its own section.
                filtered = {name: fields for name, fields in VOYAGEUR_VARS.items()
                            if name in ("Ancestry", "FamilySearch")}
            else:
                filtered = {name: fields for name, fields in VOYAGEUR_VARS.items() if name == label}
            self._build_form_ui(self.voyageur_form_container, filtered, skip_keys={"VOYAGEUR_SOURCE"})

    def _build_tab_voyageur(self, frame: ctk.CTkFrame):
        self._build_tab_header(frame, "Voyageur", "GATHER",
                               "Pulls census, vital, and land records straight from Ancestry, FamilySearch, or "
                               "Library and Archives Canada into a file ready for the next step.")

        source_frame = ctk.CTkFrame(frame, fg_color="transparent")
        source_frame.pack(side="top", fill="x", pady=(10, 5))
        source_lbl = ctk.CTkLabel(source_frame, text="Gather From ⓘ", font=ctk.CTkFont(weight="bold"),
                                  cursor="hand2")
        source_lbl.pack(side="left")
        ToolTip(source_lbl, TOOLTIP_DESCRIPTIONS["VOYAGEUR_SOURCE"])
        if not self.string_vars["VOYAGEUR_SOURCE"].get():
            self.string_vars["VOYAGEUR_SOURCE"].set(VOYAGEUR_SOURCES[0][1])
        ctk.CTkComboBox(source_frame, values=[label for _, label in VOYAGEUR_SOURCES],
                        variable=self.string_vars["VOYAGEUR_SOURCE"], width=200,
                        command=self._on_voyageur_source_change).pack(side="left", padx=10)

        # Unified action buttons (Docked to bottom)
        btn_box = self._create_action_box(frame)
        self.voyageur_gather_btn = ctk.CTkButton(btn_box, text="Gather", fg_color="#3B8ED0", hover_color="#2b7a4b")
        self.voyageur_gather_btn.pack(side="left", padx=5)

        self.voyageur_send_to_archivist_btn = ctk.CTkButton(
            btn_box, text="Gather and Send to Archivist", fg_color="#2b7a4b", hover_color="#1e5935")
        self.voyageur_send_to_archivist_btn.pack(side="left", padx=5)

        # Persistent container the filtered settings form gets rebuilt into whenever the
        # source changes, so switching repositories only shows the fields that source uses.
        self.voyageur_form_container = ctk.CTkFrame(frame, fg_color="transparent")
        self.voyageur_form_container.pack(side="top", fill="both", expand=True)

        self._on_voyageur_source_change()

    def _build_tab_registrar(self, frame: ctk.CTkFrame):
        self._build_tab_header(frame, "Registrar", "DEDUPE",
                               "Finds logical duplicate people in RootsMagic using smart name and age matching, "
                               "and flags them for manual review.")

        # Unified action buttons (Docked to bottom)
        btn_box = self._create_action_box(frame)
        ctk.CTkButton(btn_box, text="Run Script", fg_color="#2b7a4b", hover_color="#1e5935",
                      command=lambda: self.execute_script("REGISTRAR_SCRIPT", "standalone")).pack(side="left", padx=5)

        self._build_form_ui(frame, REGISTRAR_VARS)

    def _build_tab_gazetteer(self, frame: ctk.CTkFrame):
        self._build_tab_header(frame, "Gazetteer", "UTILITY",
                               "Corrects County or Territory place names in RootsMagic to match historical "
                               "boundaries for the exact year of each event.")

        # Unified action buttons (Docked to bottom)
        btn_box = self._create_action_box(frame)
        ctk.CTkButton(btn_box, text="Run Script", fg_color="#2b7a4b", hover_color="#1e5935",
                      command=lambda: self.execute_script("GAZETTEER_SCRIPT", "standalone")).pack(side="left", padx=5)

        self._build_form_ui(frame, GAZETTEER_VARS)

    def _build_tab_pdfix(self, frame: ctk.CTkFrame):
        self._build_tab_header(frame, "PDFix", "UTILITY",
                               "Losslessly shrinks PDF file sizes in bulk (garbage-collection + stream "
                               "compression) - no image rescaling.")

        # Unified action buttons (Docked to bottom)
        btn_box = self._create_action_box(frame)
        ctk.CTkButton(btn_box, text="Run Script", fg_color="#2b7a4b", hover_color="#1e5935",
                      command=lambda: self.execute_script("PDFIX_SCRIPT", "standalone")).pack(side="left", padx=5)

        self._build_form_ui(frame, PDFIX_VARS)

    def execute_script(self, script_key, mode, on_success=None):
        """Prepares environment variables and launches an external script in a background
        thread. If on_success is given, it's called once the subprocess exits with code 0 -
        letting a caller chain a follow-up run (e.g. "Gather and Send to Archivist" auto-running
        Generate GEDCOM once a gather finishes cleanly), without chaining onto a cancelled
        or failed run."""
        self._save_env()

        script_path_str = SCRIPT_PATHS.get(script_key)
        if not script_path_str:
            self.console.put(f"\n[System] Unknown script key: '{script_key}'.\n")
            return

        target_script_path = os.path.abspath(os.path.join(str(BASE_DIR), script_path_str))

        if not os.path.exists(target_script_path):
            self.console.put(f"\n[System] Could not find the script at: {target_script_path}\n")
            return

        script_display_name = os.path.basename(target_script_path)
        self.status_bar.configure(state="normal")
        self.status_bar.delete(0, "end")
        self.status_bar.insert(0, f"Launching {script_display_name}...")
        self.status_bar.configure(state="readonly")
        self.run_indicator.configure(text_color=C_ACCENT)
        self.run_tooltip.text = f"Running: {script_display_name}"
        self._expand_console()

        run_env = os.environ.copy()
        run_env.update({k: str(v.get()) for k, v in self.string_vars.items()})

        # --- DYNAMIC PATH RESOLUTION ---
        def resolve_path(base, sub):
            if not sub:
                return ""
            if os.path.isabs(sub):
                return sub
            return os.path.join(base, sub).replace("\\", "/")

        prog_dir_var: Union[ctk.StringVar, None] = self.string_vars.get("PROGRAM_DIR")
        program_dir = prog_dir_var.get().strip() if prog_dir_var is not None else ""
        media_dir_var = self.string_vars.get("MEDIA_DIR")
        media_base = media_dir_var.get().strip() if media_dir_var is not None else "Media"
        rm_dir_var = self.string_vars.get("RM_DIR")
        rm_base = rm_dir_var.get().strip() if rm_dir_var is not None else "Roots Magic 11"

        full_media_dir = resolve_path(program_dir, media_base)
        full_rm_dir = resolve_path(program_dir, rm_base)

        env_overrides = {}

        # Pre-resolve these specific nested directory variables
        nested_dir_keys = [("CHURCH_IMAGE_DIR", full_media_dir), ("SCRIP_IMAGE_DIR", full_media_dir),
                           ("CENSUS_IMAGE_DIR", full_media_dir), ("LAC_IMAGE_DIR", full_media_dir),
                           ("REGISTRAR_RM_DATABASE", full_rm_dir), ("GAZETTEER_RM_DATABASE", full_rm_dir),
                           ("PDFIX_TARGET_DIR", full_media_dir)]
        for key, base_dir in nested_dir_keys:
            if key in self.string_vars:
                env_overrides[key] = resolve_path(base_dir, self.string_vars[key].get())

        # Nothing else to compute here: every prefixed setting (CHURCH_*/SCRIP_*/CENSUS_*)
        # is already in run_env from the blanket string_vars dump above (with the nested
        # image-dir ones now resolved to full paths, via nested_dir_keys). Paleographer.py
        # and Archivist.py each resolve their own generic runtime settings (IMAGE_DIR,
        # MASTER_DB_NAME, CALL_NUMBER, GEDCOM_OUTPUT_NAME, etc.) directly from those env
        # vars via their own field_remap table (declared in the active .pmt's front
        # matter) - the same resolution they use when run standalone, with no dependency
        # on this GUI computing anything family/record-type-specific on their behalf.
        run_env.update(env_overrides)

        self._set_ui_state("disabled")

        def on_complete(status_msg="System Ready"):
            # Shows the outcome of the run that just finished (success/failed/cancelled and
            # which script), not a generic "System Ready" that erases that information the
            # moment the run ends - stays until the next run overwrites it.
            self._set_ui_state("normal")
            self.status_bar.configure(state="normal")
            self.status_bar.delete(0, "end")
            self.status_bar.insert(0, status_msg)
            self.status_bar.configure(state="readonly")
            self.run_indicator.configure(text_color=C_TEXT_MUTED)
            self.run_tooltip.text = "Idle - no script running"
            self.progress_bar.set(0)
            self.progress_pct_label.configure(text="0%")
            self.progress_row.grid_remove()

        args = [target_script_path]
        if mode == "paleographer_api" and self.debug_file_var.get().strip():
            args.append(self.debug_file_var.get().strip())
        elif script_key == "VOYAGEUR_SCRIPT":
            # Voyageur.py is a thin dispatcher; the mode IS the source code (A/FS/LAC).
            args.append(mode)

        target_cwd = os.path.dirname(target_script_path) if os.path.exists(target_script_path) else None

        threading.Thread(target=self._run_subprocess, args=(args, run_env, target_cwd, on_complete, on_success),
                         daemon=True).start()

    def _run_subprocess(self, safe_cmd, run_env, target_cwd, on_complete, on_success=None):
        run_env['PYTHONUNBUFFERED'] = '1'
        run_env['PYTHONIOENCODING'] = 'utf-8'

        script_name = os.path.basename(safe_cmd[0])
        self.console.put(f"\n[System] Starting {script_name}...\n")
        self.console.put("-" * 50 + "\n")

        self._cancel_requested = False
        succeeded = False
        status_msg = f"{script_name}: did not start"
        try:
            self.active_process = subprocess.Popen([sys.executable] + safe_cmd, stdin=subprocess.PIPE,
                                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0,
                                                   env=run_env, cwd=target_cwd)

            stdout_stream = io.TextIOWrapper(self.active_process.stdout, encoding='utf-8', newline='', errors='replace')

            while True:
                char = stdout_stream.read(1)
                if not char:
                    break
                self.console.put(char)

            self.active_process.wait()

            if self.active_process.returncode == 0:
                self.console.put(f"\n[System] {script_name} finished successfully!\n")
                succeeded = True
                status_msg = f"{script_name}: finished successfully"
            elif self._cancel_requested:
                # terminate() reports the same exit code (1 on Windows) as a genuine
                # unhandled exception, so cancellation can only be told apart from a real
                # crash via this flag, not the returncode itself.
                self.console.put(f"\n[System] Task was cancelled by you.\n")
                status_msg = f"{script_name}: cancelled"
            else:
                self.console.put(
                    f"\n[System] {script_name} encountered an error (exit code "
                    f"{self.active_process.returncode}). Please check the text above for clues.\n")
                status_msg = f"{script_name}: failed (exit code {self.active_process.returncode})"

        except (OSError, subprocess.SubprocessError, ValueError) as e:
            self.console.put(f"\n[System] Failed to execute {script_name}:\n{str(e)}\n")
            status_msg = f"{script_name}: failed to start"

        self.active_process = None
        # on_complete's own delay (100ms) fires first, re-enabling the UI, before
        # on_success (150ms) potentially launches a follow-up script through
        # execute_script - which disables the UI again itself - so the two calls'
        # UI-state changes can't race each other out of order.
        self.after(100, partial(on_complete, status_msg))
        if succeeded and on_success:
            self.after(150, on_success)

    def _set_ui_state(self, state):
        # Deliberately only content_area, not self.sidebar - tab switching should stay
        # possible while a script runs in the background.
        self._recursive_state(self.content_area, state)

        if hasattr(self, 'console_input'):
            if state == "disabled":
                self.console_input.configure(state="normal")
                self.cancel_btn.configure(state="normal")
            else:
                self.console_input.configure(state="disabled")
                self.cancel_btn.configure(state="disabled")

    def _recursive_state(self, widget, state):
        if isinstance(widget, ctk.CTkButton):
            widget.configure(state=state)
        for child in widget.winfo_children():
            self._recursive_state(child, state)


if __name__ == "__main__":
    app = Scriptorium()
    app.mainloop()
