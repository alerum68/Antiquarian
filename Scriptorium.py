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


def env_path_for(subfolder: Optional[str]) -> Path:
    """Resolves the .env path for a settings group: the project root if subfolder is None,
    otherwise that tool's own subfolder, so each tool's config stays self-contained."""
    return BASE_DIR / subfolder / ".env" if subfolder else BASE_DIR / ".env"


# ==========================================
# UNIFIED ENV SCHEMA & CONTEXT OVERRIDES
# ==========================================
GLOBAL_VARS = {"API & Processing": {"GEMINI_API_KEY": "", "API_BUDGET": "20", "MODEL_NAME": "gemini-3.1-pro-preview",
                                    "COST_PER_1M_INPUT": "2.00", "COST_PER_1M_OUTPUT": "12.00",
                                    "CACHE_DISCOUNT_MULTIPLIER": "0.10"},
               "Script Locations": {"ANALYSIS_SCRIPT": "Paleographer/Paleographer.py",
                                    "ARCHIVIST_SCRIPT": "Archivist/Archivist.py",
                                    "VOYAGEUR_SCRIPT": "Voyageur/Voyageur.py",
                                    "REGISTRAR_SCRIPT": "Registrar/Registrar.py",
                                    "GAZETTEER_SCRIPT": "Gazetteer/Gazetteer.py",
                                    "PDFIX_SCRIPT": "PDFix/PDFix.py",
                                    "CLEANUP_CACHE_SCRIPT": "Paleographer/CacheCleanup.py"},
               "Global Directories": {"PROGRAM_DIR": "C:/Path/To/Your/Genealogy/Folder", "RM_DIR": "Roots Magic 11",
                                      "FTM_DIR": "Family Tree Maker", "MEDIA_DIR": "Media/Project",
                                      "CENSUS_IMAGE_DIR": "Census",
                                      "JSON_DIR": "Scriptorium/Working/Project/JSON", "IMAGE_EXTENSION": "jpg",
                                      "GEDCOM_OUTPUT_PATH": "GEDCOM/Project"},
               "Metadata & Organization": {"RESEARCHER": "Your Name", "ORG_NAME": "Your Historical Society",
                                           "SOFTWARE_NAME": "RootsMagic", "SOFTWARE_VERS": "11.0",
                                           "COPYRIGHT_START": "2024",
                                           "GEDCOM_NOTE": "This file contains original historical translations and "
                                                          "research.",
                                           "GEDCOM_CONC": "Please do not upload this raw GEDCOM to public, "
                                                          "collaborative trees without permission and attribution.",
                                           "REVIEW_COLOR": "1", "ROOT_SOURCE_ID": "@S1@"},
               "Standard Links": {"SUBM_ADDRESS": "https://www.example.com/contact",
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
# GEDCOM SOURCE FIELD REMAP
# ==========================================
# Archivist.py (the Create step) reads generic, unprefixed field names regardless of which
# record family it's building. Each tab's own schema still uses its prefixed names
# (CENSUS_*/CHURCH_*) so its settings stay grouped and self-explanatory in the UI; this
# table bridges the two. "census"/"scrip" only exist here so `family in FIELD_REMAP` (see
# execute_script) recognizes them as valid families - their one entry always targets
# IMAGE_DIR, which every consuming loop below explicitly skips and sets separately, so the
# loop body is a structural no-op for these two; only "church" has entries it actually uses.
FIELD_REMAP = {"census": {"CENSUS_IMAGE_DIR": "IMAGE_DIR"},
               "church": {"CHURCH_CALL_NUMBER": "CALL_NUMBER", "CHURCH_COLLECTION_URL": "COLLECTION_URL",
                          "CHURCH_COLLECTION_NAME": "COLLECTION_NAME", "CHURCH_REPOSITORY": "REPOSITORY",
                          "CHURCH_REPOSITORY_LOC": "REPOSITORY_LOC", "CHURCH_IMAGE_DIR": "IMAGE_DIR"},
               "scrip": {"SCRIP_IMAGE_DIR": "IMAGE_DIR"}}

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
PY_FILETYPES = [("Python files", "*.py"), ("All files", "*.*")]
SHP_FILETYPES = [("Shapefiles", "*.shp"), ("All files", "*.*")]

PATH_PICKER_FIELDS = {
    # Global: Script Locations (.py files, rooted at the toolbox's own code folder)
    "ANALYSIS_SCRIPT": {"kind": "open", "base_dir_key": TOOLBOX_DIR_SENTINEL, "filetypes": PY_FILETYPES},
    "ARCHIVIST_SCRIPT": {"kind": "open", "base_dir_key": TOOLBOX_DIR_SENTINEL, "filetypes": PY_FILETYPES},
    "VOYAGEUR_SCRIPT": {"kind": "open", "base_dir_key": TOOLBOX_DIR_SENTINEL, "filetypes": PY_FILETYPES},
    "REGISTRAR_SCRIPT": {"kind": "open", "base_dir_key": TOOLBOX_DIR_SENTINEL, "filetypes": PY_FILETYPES},
    "GAZETTEER_SCRIPT": {"kind": "open", "base_dir_key": TOOLBOX_DIR_SENTINEL, "filetypes": PY_FILETYPES},
    "PDFIX_SCRIPT": {"kind": "open", "base_dir_key": TOOLBOX_DIR_SENTINEL, "filetypes": PY_FILETYPES},
    "CLEANUP_CACHE_SCRIPT": {"kind": "open", "base_dir_key": TOOLBOX_DIR_SENTINEL, "filetypes": PY_FILETYPES},

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

    def __init__(self, text_widget, status_widget):
        self.text_widget = text_widget
        self.status_widget = status_widget
        self.queue = queue.Queue()
        self.ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
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
        ctk.set_default_color_theme("blue")

        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        self.string_vars: Dict[str, ctk.StringVar] = {}
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
        self.tabview.set("Voyageur")
        self._on_tab_change()

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

        self.main_container.grid_rowconfigure(0, weight=2)  # Prioritize top half for tabs
        self.main_container.grid_rowconfigure(1, weight=1)  # Bottom half for console
        self.main_container.grid_columnconfigure(0, weight=1)

        # Using the native CTkTabview for top-oriented tabs
        self.tabview = ctk.CTkTabview(self.main_container, command=self._on_tab_change)
        self.tabview.grid(row=0, column=0, sticky="nsew", padx=10, pady=(0, 10))

        for tab_name in self.tab_builders.keys():
            self.tabview.add(tab_name)

        self.console_frame = ctk.CTkFrame(self.main_container)
        self.console_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 0), padx=10)
        self.console_frame.grid_rowconfigure(1, weight=1)
        self.console_frame.grid_columnconfigure(0, weight=1)

        self.status_bar = ctk.CTkEntry(self.console_frame, font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
                                       text_color="#00FFFF", fg_color="#1a1a1a", border_width=1)
        self.status_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        self.status_bar.insert(0, "System Ready")
        self.status_bar.configure(state="readonly")

        # Set fixed fallback dimensions to prevent 0-height rendering geometry crash
        self.console_text = ctk.CTkTextbox(self.console_frame, font=ctk.CTkFont(family="Consolas", size=12),
                                           text_color="#00FF00", width=800, height=250)
        self.console_text.grid(row=1, column=0, sticky="nsew", padx=10, pady=(5, 10))
        self.console_text.configure(state="disabled")

        self.input_frame = ctk.CTkFrame(self.console_frame, fg_color="transparent")
        self.input_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.console_input = ctk.CTkEntry(self.input_frame,
                                          placeholder_text="Type script input here and press Enter...",
                                          state="disabled")
        self.console_input.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.console_input.bind("<Return>", self.send_input)

        self.cancel_btn = ctk.CTkButton(self.input_frame, text="Cancel", fg_color="darkred", hover_color="red",
                                        width=80, state="disabled", command=self.cancel_script)
        self.cancel_btn.grid(row=0, column=1)

        self.console = ConsoleRedirector(self.console_text, self.status_bar)

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

    def _on_tab_change(self):
        current_tab = self.tabview.get()
        if current_tab not in self.tabs_built:
            tab_frame = self.tabview.tab(current_tab)
            self.tab_builders[current_tab](tab_frame)
            self.tabs_built.add(current_tab)

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

    def _build_tab_header(self, frame: ctk.CTkFrame, title: str, help_key: str):
        """A helper method to standardize tab headers and eliminate duplicate code."""
        header_frame = ctk.CTkFrame(frame, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(header_frame, text=title, font=ctk.CTkFont(size=24, weight="bold")).pack(side="left")
        ctk.CTkButton(header_frame, text="Help", width=60, fg_color="#3B8ED0", hover_color="#2b7a4b",
                      command=lambda: self.show_help(help_key)).pack(side="right", padx=5)
        ctk.CTkButton(header_frame, text="Save Config", fg_color="#D4AC0D", hover_color="#B7950B",
                      text_color="black", command=self._save_env).pack(side="right", padx=5)

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
            # Rough allowance for the tab header row + docked action-button box that share
            # this same parent frame above/below the scroll area.
            available = parent.winfo_height() - 110
            if available > 100:
                scroll.configure(height=available)

        parent.bind("<Configure>", _resize_scroll)
        parent.after(50, _resize_scroll)

        for section, fields in schema_dict.items():
            ctk.CTkLabel(scroll, text=section, font=ctk.CTkFont(size=16, weight="bold"), text_color="#3B8ED0").pack(
                anchor="w", pady=(15, 5))
            for key in fields.keys():
                if key in skip_keys:
                    continue
                row = ctk.CTkFrame(scroll, fg_color="transparent")
                row.pack(fill="x", pady=2)

                # Generate hoverable, friendly labels
                desc = TOOLTIP_DESCRIPTIONS.get(key)
                friendly_name = self._clean_label(key)
                display_text = f"{friendly_name} ⓘ" if desc else friendly_name

                lbl = ctk.CTkLabel(row, text=display_text, width=250, anchor="w", cursor="hand2" if desc else "arrow")
                lbl.pack(side="left", padx=5)

                if desc:
                    ToolTip(lbl, desc)

                ctk.CTkEntry(row, textvariable=self.string_vars[key]).pack(side="left", fill="x", expand=True, padx=5)

                picker = PATH_PICKER_FIELDS.get(key)
                if picker:
                    ctk.CTkButton(row, text="Browse...", width=90,
                                  command=partial(self._browse_for_path, key, picker)
                                  ).pack(side="left", padx=5)

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
        self._build_tab_header(frame, "Global Environment Settings", "Global Settings")

        # Build buttons first so they dock safely to the bottom
        self._create_action_box(frame)

        self._build_form_ui(frame, GLOBAL_VARS)

    def _build_tab_archivist(self, frame: ctk.CTkFrame):
        self._build_tab_header(frame, "Archivist", "Archivist")

        ctk.CTkLabel(frame, text="Builds a GEDCOM from whatever JSON Voyageur or Paleographer already produced.",
                     text_color="gray").pack(side="top", anchor="w", pady=(0, 20))

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
    def _record_type_family(record_type_value: str) -> str:
        """Maps the record-type dropdown's current value to a FIELD_REMAP family key,
        defaulting to "church" (Parish) for anything unrecognized."""
        name = record_type_value.strip().lower()
        if name.endswith(".pmt"):
            name = name[:-4]
        return "scrip" if name == "scrip" else "church"

    @staticmethod
    def _get_pmt_settings_sections(record_type_value: str) -> List[str]:
        """Reads the settings_sections a .pmt's own YAML front matter declares (if any),
        telling the Paleographer tab which PALEOGRAPHER_VARS sections are actually
        relevant for that record type. A .pmt that doesn't declare this (or can't be
        read/parsed) returns an empty list, meaning "show everything" - so older or
        hand-edited .pmt files don't lose fields by omission."""
        name = record_type_value.strip() or "Parish.pmt"
        if not name.endswith(".pmt"):
            name += ".pmt"
        pmt_path = Path(__file__).resolve().parent / "Paleographer" / "prompts" / name
        try:
            raw = pmt_path.read_text(encoding="utf-8")
        except OSError:
            return []

        stripped = raw.lstrip()
        if not stripped.startswith("---"):
            return []
        parts = stripped.split("---", 2)
        if len(parts) < 3:
            return []
        try:
            front_matter = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            return []

        sections = front_matter.get("settings_sections")
        return list(sections) if sections else []

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
        self._build_tab_header(frame, "Paleographer", "Paleographer")

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
        actually reads from (CHURCH_IMAGE_DIR or SCRIP_IMAGE_DIR, nested under MEDIA_DIR -
        mirroring execute_script's own resolution), storing just the bare filename since
        that's what Paleographer.py compares DEBUG_FILE against."""
        family = self._record_type_family(self.string_vars["PALEOGRAPHER_RECORD_TYPE"].get())
        image_dir_key = "SCRIP_IMAGE_DIR" if family == "scrip" else "CHURCH_IMAGE_DIR"
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
        self._build_tab_header(frame, "Voyageur", "Voyageur")

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
        self._build_tab_header(frame, "Registrar", "Registrar")

        ctk.CTkLabel(frame, text="Finds logical duplicate people in RootsMagic.", text_color="gray").pack(side="top",
                                                                                                          anchor="w",
                                                                                                          pady=(0, 20))

        # Unified action buttons (Docked to bottom)
        btn_box = self._create_action_box(frame)
        ctk.CTkButton(btn_box, text="Run Script", fg_color="#2b7a4b", hover_color="#1e5935",
                      command=lambda: self.execute_script("REGISTRAR_SCRIPT", "standalone")).pack(side="left", padx=5)

        self._build_form_ui(frame, REGISTRAR_VARS)

    def _build_tab_gazetteer(self, frame: ctk.CTkFrame):
        self._build_tab_header(frame, "Gazetteer", "Gazetteer")

        ctk.CTkLabel(frame, text="Fixes historical US county jurisdictions utilizing geopandas.",
                     text_color="gray").pack(side="top", anchor="w", pady=(0, 20))

        # Unified action buttons (Docked to bottom)
        btn_box = self._create_action_box(frame)
        ctk.CTkButton(btn_box, text="Run Script", fg_color="#2b7a4b", hover_color="#1e5935",
                      command=lambda: self.execute_script("GAZETTEER_SCRIPT", "standalone")).pack(side="left", padx=5)

        self._build_form_ui(frame, GAZETTEER_VARS)

    def _build_tab_pdfix(self, frame: ctk.CTkFrame):
        self._build_tab_header(frame, "PDFix", "PDFix")

        ctk.CTkLabel(frame, text="Losslessly shrinks PDF file sizes in bulk (garbage-collection + stream "
                                 "compression via PyMuPDF) - no image rescaling.",
                     text_color="gray").pack(side="top", anchor="w", pady=(0, 20))

        # Unified action buttons (Docked to bottom)
        btn_box = self._create_action_box(frame)
        ctk.CTkButton(btn_box, text="Run Script", fg_color="#2b7a4b", hover_color="#1e5935",
                      command=lambda: self.execute_script("PDFIX_SCRIPT", "standalone")).pack(side="left", padx=5)

        self._build_form_ui(frame, PDFIX_VARS)

    def _peek_record_family(self, program_dir: str) -> str:
        """Peeks at the JSON file Archivist would build from (mirroring Archivist.py's own
        resolve_json_input: explicit JSON_FILE, else the most recently created *.json in
        JSON_DIR) just far enough to read its record_family field, so the single "Generate
        GEDCOM" button can dispatch without the user picking a mode. Falls back to "church"
        on any error - Archivist.py itself raises the real error when it actually runs."""
        json_dir_var = self.string_vars.get("JSON_DIR")
        json_file_var = self.string_vars.get("JSON_FILE")
        json_dir_setting = json_dir_var.get().strip() if json_dir_var is not None else ""
        json_file_name = json_file_var.get().strip() if json_file_var is not None else ""

        if json_dir_setting and os.path.isabs(json_dir_setting):
            json_dir_resolved = json_dir_setting
        else:
            json_dir_resolved = os.path.join(program_dir, json_dir_setting) if program_dir else json_dir_setting

        try:
            if json_file_name:
                candidate = (Path(json_file_name) if os.path.isabs(json_file_name)
                             else Path(json_dir_resolved) / json_file_name)
            else:
                candidates = sorted(Path(json_dir_resolved).glob("*.json"),
                                    key=lambda p: p.stat().st_mtime, reverse=True)
                candidate = candidates[0] if candidates else None

            if candidate and candidate.is_file():
                with open(candidate, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                family = loaded.get("record_family")
                if family:
                    return family
                return "census" if "pages" in loaded else "church"
        except (OSError, ValueError, IndexError):
            pass

        return "church"

    def execute_script(self, script_key, mode, on_success=None):
        """Prepares environment variables and launches an external script in a background
        thread. If on_success is given, it's called once the subprocess exits with code 0 -
        letting a caller chain a follow-up run (e.g. "Gather and Send to Archivist" auto-running
        Generate GEDCOM once a gather finishes cleanly), without chaining onto a cancelled
        or failed run."""
        self._save_env()

        script_path_var: Union[ctk.StringVar, None] = self.string_vars.get(script_key)
        if script_path_var is None or not script_path_var.get().strip():
            self.console.put(
                f"\n[System] The script path for '{script_key}' is empty or missing in Global Settings.\n")
            return

        script_path_str = script_path_var.get().strip()
        prog_dir_var: Union[ctk.StringVar, None] = self.string_vars.get("PROGRAM_DIR")
        program_dir = prog_dir_var.get().strip() if prog_dir_var is not None else ""

        if os.path.isabs(script_path_str):
            target_script_path = os.path.abspath(script_path_str)
        else:
            target_script_path = os.path.abspath(os.path.join(str(BASE_DIR), script_path_str))

        if not os.path.exists(target_script_path):
            self.console.put(f"\n[System] Could not find the script at: {target_script_path}\n")
            return

        self.status_bar.configure(state="normal")
        self.status_bar.delete(0, "end")
        self.status_bar.insert(0, f"Launching {os.path.basename(target_script_path)}...")
        self.status_bar.configure(state="readonly")

        run_env = os.environ.copy()
        run_env.update({k: str(v.get()) for k, v in self.string_vars.items()})

        # --- DYNAMIC PATH RESOLUTION ---
        def resolve_path(base, sub):
            if not sub:
                return ""
            if os.path.isabs(sub):
                return sub
            return os.path.join(base, sub).replace("\\", "/")

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

        if mode == "paleographer_api":
            family = self._record_type_family(self.string_vars["PALEOGRAPHER_RECORD_TYPE"].get())
            for src_key, dst_key in FIELD_REMAP.get(family, {}).items():
                if dst_key == "IMAGE_DIR":
                    continue
                var: Union[ctk.StringVar, None] = self.string_vars.get(src_key)
                env_overrides[dst_key] = var.get() if var is not None else ""

            image_dir_key = "SCRIP_IMAGE_DIR" if family == "scrip" else "CHURCH_IMAGE_DIR"
            master_db_key = "SCRIP_MASTER_DB_NAME" if family == "scrip" else "CHURCH_MASTER_DB_NAME"
            env_overrides.update({"IMAGE_DIR": env_overrides.get(image_dir_key, ""),
                                  "IMAGE_SOURCE_DIR": env_overrides.get(image_dir_key, ""),
                                  "GEDCOM_OUTPUT_NAME": self.string_vars["CHURCH_GEDCOM_NAME"].get(),
                                  "MASTER_DB_NAME": self.string_vars[master_db_key].get()})
        elif mode == "gedcom_auto":
            family = self._peek_record_family(program_dir)
            family_key = family if family in FIELD_REMAP else "church"

            for src_key, dst_key in FIELD_REMAP[family_key].items():
                if dst_key == "IMAGE_DIR":
                    continue
                var = self.string_vars.get(src_key)
                env_overrides[dst_key] = var.get() if var is not None else ""

            if family_key == "census":
                # GEDCOM_OUTPUT_NAME deliberately left unset here - Archivist's census
                # flavor derives it from the gathered JSON's own filename when it's blank
                # (see run_census_flavor), which is the name that actually matters for a
                # census run; CHURCH_GEDCOM_NAME doesn't apply to this family at all.
                env_overrides.update({"IMAGE_DIR": env_overrides.get("CENSUS_IMAGE_DIR", ""),
                                      "IMAGE_SOURCE_DIR": env_overrides.get("CENSUS_IMAGE_DIR", "")})
            else:
                # Previously only set in the paleographer_api branch above (the AI
                # transcription step, which never calls Archivist) and never here in
                # gedcom_auto (which is the only mode that actually does) - so clicking
                # "Generate GEDCOM" on a church/scrip register always wrote to Archivist's
                # module-level default filename instead of this configured one.
                image_dir_key = "SCRIP_IMAGE_DIR" if family_key == "scrip" else "CHURCH_IMAGE_DIR"
                env_overrides.update({"IMAGE_DIR": env_overrides.get(image_dir_key, ""),
                                      "IMAGE_SOURCE_DIR": env_overrides.get(image_dir_key, ""),
                                      "GEDCOM_OUTPUT_NAME": self.string_vars["CHURCH_GEDCOM_NAME"].get()})

        run_env.update(env_overrides)

        self._set_ui_state("disabled")

        def on_complete():
            self._set_ui_state("normal")
            self.status_bar.configure(state="normal")
            self.status_bar.delete(0, "end")
            self.status_bar.insert(0, "System Ready")
            self.status_bar.configure(state="readonly")

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
            elif self._cancel_requested:
                # terminate() reports the same exit code (1 on Windows) as a genuine
                # unhandled exception, so cancellation can only be told apart from a real
                # crash via this flag, not the returncode itself.
                self.console.put(f"\n[System] Task was cancelled by you.\n")
            else:
                self.console.put(
                    f"\n[System] {script_name} encountered an error (exit code "
                    f"{self.active_process.returncode}). Please check the text above for clues.\n")

        except (OSError, subprocess.SubprocessError, ValueError) as e:
            self.console.put(f"\n[System] Failed to execute {script_name}:\n{str(e)}\n")

        self.active_process = None
        # on_complete's own delay (100ms) fires first, re-enabling the UI, before
        # on_success (150ms) potentially launches a follow-up script through
        # execute_script - which disables the UI again itself - so the two calls'
        # UI-state changes can't race each other out of order.
        self.after(100, on_complete)
        if succeeded and on_success:
            self.after(150, on_success)

    def _set_ui_state(self, state):
        self._recursive_state(self.tabview, state)

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
