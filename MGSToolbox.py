import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from typing import Union, Dict, Callable, List, Optional

import customtkinter as ctk
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
               "Script Locations": {"GATHER_DATA_SCRIPT": "MGS_Toolbox/ChurchRegisters/ChurchGatherData.py",
                                    "CHURCH_GEDCOM_SCRIPT": "MGS_Toolbox/ChurchRegisters/ChurchCreateGedcom.py",
                                    "CENSUS_EXTRACTOR_SCRIPT": "MGS_Toolbox/CensusConverter/CensusExtractor.py",
                                    "CENSUS_GEDCOM_SCRIPT": "MGS_Toolbox/CensusConverter/CensusConverter.py",
                                    "LAC_DOWNLOADER_SCRIPT": "MGS_Toolbox/LACDownloader/LACDownloader.py",
                                    "DUPE_SCRIPT": "MGS_Toolbox/Dupes/Dupes.py",
                                    "COUNTY_SCRIPT": "MGS_Toolbox/CountyFix/CountyFix.py",
                                    "CLEANUP_CACHE_SCRIPT": "MGS_Toolbox/ChurchRegisters/CacheCleanup.py"},
               "Global Directories": {"PROGRAM_DIR": "C:/Path/To/Your/Genealogy/Folder", "RM_DIR": "Roots Magic 11",
                                      "FTM_DIR": "Family Tree Maker", "MEDIA_DIR": "Media/Project",
                                      "CSV_DIR": "MGS_Toolbox/Working/Project/CSV",
                                      "JSON_DIR": "MGS_Toolbox/Working/Project/JSON", "IMAGE_EXTENSION": "jpg",
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

CENSUS_VARS = {"Extraction Target": {"CENSUS_URL": "", "CENSUS_IMAGE_DIR": "Census", },
               "Archival Info": {"CENSUS_YEAR": "1850", "ENUMERATION_DISTRICT": "", "FILM_NUMBER": "",
                                 "ROLL_NUMBER": ""},
               "Location Overrides": {"STATE": "State", "COUNTY": "County", "TOWNSHIP": "Township"},
               "Family Inference Tuning": {"MIN_MARRIAGE_AGE": "12", "MAX_SPOUSE_AGE_GAP": "25",
                                           "HUSBAND_CHILD_AGE_GAP_MIN": "14", "HUSBAND_CHILD_AGE_GAP_MAX": "60",
                                           "WIFE_CHILD_AGE_GAP_MIN": "12", "WIFE_CHILD_AGE_GAP_MAX": "50"},
               "Direct CSV Import (Ignore if Auto-Extracting)": {"CSV_FILE": "MyCensusData.csv",
                                                                 "CENSUS_CALL_NUMBER": "",
                                                                 "CENSUS_REPOSITORY": "Ancestry.com",
                                                                 "CENSUS_REPOSITORY_LOC": "",
                                                                 "CENSUS_COLLECTION_URL": "",
                                                                 "CENSUS_COLLECTION_NAME": "", "CENSUS_PUBLISHER": "",
                                                                 "CENSUS_PUB_LOC": ""}}

LAC_VARS = {"LAC Image Downloader Settings": {"LAC_URL": "", "LAC_IMAGE_DIR": "LAC"}}

CHURCH_VARS = {"Data & Directories": {"CHURCH_PROMPT_FILE": "", "CHURCH_IMAGE_DIR": "Parish",
                                      "CHURCH_GEDCOM_NAME": "Parish.ged",
                                      "CHURCH_MASTER_DB_NAME": "parish_register.json", },
               "Parish Information": {"PARISH_NAME": "St. Generic Catholic Church",
                                      "PARISH_NAME_SHORT": "St. Generic Parish, Anytown, ST", "PARISH_CITY": "Anytown",
                                      "PARISH_STATE": "State", "PARISH_FILE_NAME": "Parish_Anytown",
                                      "DEFAULT_EVENT_LOCATION": "Anytown, Any County, State, USA"},
               "Register Information": {"REGISTER_SOURCE_ID": "1",
                                        "VOLUME_TITLE": "Baptisms, marriages and burials, 1850-1900", "VOLUME_NUM": "1",
                                        "REGISTER_NAME": "Baptisms, marriages and burials, 1850-1900", },
               "Church Citation (Source)": {"CHURCH_CALL_NUMBER": "Call #1234567",
                                            "CHURCH_REPOSITORY": "FamilySearch.org",
                                            "CHURCH_REPOSITORY_LOC": "Granite Mountain, UT",
                                            "CHURCH_COLLECTION_URL": "https://www.familysearch.org/search/collection",
                                            "CHURCH_COLLECTION_NAME": "Generic Historical Collection, "
                                                                      "FamilySearch.org"},
               "Formatting & Roles": {"TRANSCRIPTION_HEADER": "Original Transcription:",
                                      "TRANSLATION_HEADER": "English Translation:", "ROLE_DEFAULT_WITNESS": "Witness",
                                      "ROLE_CLERGY": "Priest", "CLERGY_HONORIFIC": "Father",
                                      "PRIEST_NAMES": "John Smith,Michael Johnson,David Williams"}}

DUPE_VARS = {"File Paths (Relative to RootsMagic Dir)": {"DUPE_RM_DATABASE": "Your Tree.rmtree"},
             "Matching Thresholds": {"DUPE_FUZZY_THRESHOLD": "82", "DUPE_MAX_AGE_GAP": "5",
                                     "DUPE_FUZZY_THRESHOLD_STRICT": "95", "DUPE_FAMILY_MATCH_THRESHOLD": "75"},
             "RootsMagic UI Settings": {"DUPE_FOLDER_NAME": "!Duplicate Review", "DUPE_COLOR_SET": "1",
                                        "DUPE_COLOR_VALUE": "27"}}

COUNTY_VARS = {"File Paths": {"COUNTY_RM_DATABASE": "Your Tree.rmtree",
                              "COUNTY_SHAPEFILE": "MGS_Toolbox/CountyFix/Reference/US_AtlasHCB_Counties/"
                                                  "US_HistCounties_Shapefile/US_HistCounties.shp"},
               "Settings": {"COUNTY_DEBUG_MODE": "False", "COUNTY_CREATE_BACKUP": "True"}}

# ==========================================
# ENV FILE TARGETS
# ==========================================
# Global settings persist to the project root's .env. Each tool's own settings persist to a
# .env file inside that tool's own subfolder, so every tool stays runnable standalone.
ENV_TARGETS = [(GLOBAL_VARS, None),
               (CENSUS_VARS, "CensusConverter"),
               (CHURCH_VARS, "ChurchRegisters"),
               (LAC_VARS, "LACDownloader"),
               (DUPE_VARS, "Dupes"),
               (COUNTY_VARS, "CountyFix")]

# ==========================================
# TOOLTIP DESCRIPTIONS
# ==========================================
TOOLTIP_DESCRIPTIONS = {  # Global Settings
    "PROGRAM_DIR": "Your single base Genealogy folder. Everything else, including the MGS_Toolbox code, your "
                   "Roots Magic / Family Tree Maker databases, Media, and GEDCOM output, lives directly inside "
                   "this one folder.",
    "GEMINI_API_KEY": "Your personal API key from Google AI Studio. Used to read and transcribe handwritten images.",
    "MEDIA_DIR": "The base folder where your genealogy media is stored.",
    "API_BUDGET": "A safety limit for your AI costs (e.g., '20' means $20). The script stops if it spends this much.",
    "MODEL_NAME": "The AI model version you want to use (usually gemini-3.1-pro-preview or gemini-2.5-pro).",
    "RM_DIR": "The folder where your RootsMagic files live, relative to the Program Dir.",
    "CSV_DIR": "The folder where downloaded spreadsheet (CSV) files are kept.",
    "GEDCOM_OUTPUT_PATH": "The folder where the finished, ready-to-import GEDCOM files will be saved.",
    "RESEARCHER": "Your name. This will be added to the GEDCOM file to give you credit as the transcriber.",
    "COST_PER_1M_INPUT": "The price Google charges per 1 million input tokens (text/images sent to the AI).",
    "COST_PER_1M_OUTPUT": "The price Google charges per 1 million output tokens (JSON/text generated by the AI).",
    "CACHE_DISCOUNT_MULTIPLIER": "The fractional discount applied to tokens loaded from context caching (e.g., 0.10 "
                                 "means 10% of standard cost).",
    "ORG_NAME": "The name of your Historical Society, Library, or personal organization to include in GEDCOM headers.",
    "ROOT_SOURCE_ID": "The master SOUR (Source) ID used in RootsMagic for the researcher credit (e.g., @S1@).",
    "REVIEW_COLOR": "The numeric RootsMagic color code to paint people who have been flagged for manual review.",

    # Census
    "CENSUS_URL": "The web address (URL) of the specific Ancestry.com census page you want to extract.",
    "CENSUS_IMAGE_DIR": "The subfolder name (e.g., 'Census') inside your Base Media Directory. Can also be an "
                         "absolute path.",
    "CSV_FILE": "If you already have a downloaded CSV file you want to convert to GEDCOM, put its name here.",
    "CENSUS_YEAR": "The 4-digit year of the census (e.g., 1850).",
    "STATE": "The State for this census record. Overrides missing data.",
    "COUNTY": "The County for this census record. Overrides missing data.",
    "TOWNSHIP": "The Township for this census record. Overrides missing data.",
    "ENUMERATION_DISTRICT": "The Enumeration District for this census record.",
    "FILM_NUMBER": "The film number for this census record.", "ROLL_NUMBER": "The roll number for this census record.",
    "MIN_MARRIAGE_AGE": "The youngest plausible age someone could be married (used to group families correctly).",
    "MAX_SPOUSE_AGE_GAP": "The largest age gap allowed between a husband and wife before the AI assumes they are not "
                          "married.",
    "HUSBAND_CHILD_AGE_GAP_MIN": "The minimum plausible age difference between a father and his child.",
    "HUSBAND_CHILD_AGE_GAP_MAX": "The maximum plausible age difference between a father and his child.",
    "WIFE_CHILD_AGE_GAP_MIN": "The minimum plausible age difference between a mother and her child.",
    "WIFE_CHILD_AGE_GAP_MAX": "The maximum plausible age difference between a mother and her child.",
    "CENSUS_REPOSITORY": "The website or physical archive where this census was found (e.g., Ancestry.com).",
    "CENSUS_CALL_NUMBER": "The call number for the census collection.",
    "CENSUS_REPOSITORY_LOC": "The physical location of the repository.",
    "CENSUS_COLLECTION_URL": "The direct URL to the census collection.",
    "CENSUS_COLLECTION_NAME": "The name of the census collection.",
    "CENSUS_PUBLISHER": "The publisher of the census collection.", "CENSUS_PUB_LOC": "The location of the publisher.",

    # LAC Downloader
    "LAC_URL": "Paste the complete Heritage Canadiana link (e.g., "
                "https://heritage.canadiana.ca/iiif/oocihm.lac_reel_c2170/).",
    "LAC_IMAGE_DIR": "The subfolder name (e.g., 'LAC') inside your Base Media Directory. A subfolder per roll number "
                      "is created automatically inside it. Can also be an absolute path.",

    # Church
    "CHURCH_PROMPT_FILE": "Which .pmt prompt template (from ChurchRegisters/prompts) to use for this register. "
                          "Leave blank to use the default, Parish.pmt.",
    "CHURCH_IMAGE_DIR": "The subfolder name (e.g., 'Parish') inside your Base Media Directory. Can also be an "
                         "absolute path.",
    "CHURCH_GEDCOM_NAME": "The filename for the generated GEDCOM file.",
    "CHURCH_MASTER_DB_NAME": "The filename for the JSON database storing the extracted records.",
    "PARISH_NAME": "The full historical name of the church (e.g., St. Joseph Catholic Church).",
    "PARISH_NAME_SHORT": "A shortened name for the parish, used in file titles.",
    "PARISH_CITY": "The city where the parish is located.",
    "PARISH_STATE": "The state or province where the parish is located.",
    "PARISH_FILE_NAME": "The base filename used for parish exports.",
    "DEFAULT_EVENT_LOCATION": "The default location assigned to events if none is specified.",
    "REGISTER_SOURCE_ID": "The source ID assigned to this specific register volume.",
    "VOLUME_TITLE": "The title of the specific book you are transcribing (e.g., Baptisms 1840-1860).",
    "VOLUME_NUM": "The volume number of the register.", "REGISTER_NAME": "The name of the register.",
    "CHURCH_CALL_NUMBER": "The call number for the church register collection.",
    "CHURCH_REPOSITORY": "The repository holding the church register.",
    "CHURCH_REPOSITORY_LOC": "The location of the repository.",
    "PRIEST_NAMES": "A comma-separated list of priests who officiated. Helps the AI recognize messy signatures.",
    "CHURCH_COLLECTION_URL": "A link back to FamilySearch or Ancestry where you found these images.",
    "CHURCH_COLLECTION_NAME": "The name of the online collection holding these images.",
    "TRANSCRIPTION_HEADER": "The header text used for the original language transcription.",
    "TRANSLATION_HEADER": "The header text used for the English translation.",
    "ROLE_DEFAULT_WITNESS": "The default role name assigned to witnesses.",
    "ROLE_CLERGY": "The role name assigned to the clergy.",
    "CLERGY_HONORIFIC": "The honorific title added to the clergy's name (e.g., Father).",

    # Dupes
    "DUPE_RM_DATABASE": "The filename of your RootsMagic tree (e.g., 'Your Tree.rmtree') located in your RootsMagic "
                         "Folder.",
    "DUPE_FUZZY_THRESHOLD": "Score (0-100) for matching names when we KNOW their birth years. 82 is recommended.",
    "DUPE_MAX_AGE_GAP": "The maximum number of years apart two records can be and still be flagged as a duplicate.",
    "DUPE_COLOR_VALUE": "The numeric RootsMagic color code to paint duplicate people (27 is Slate).",
    "DUPE_FUZZY_THRESHOLD_STRICT": "A stricter threshold (0-100) used only for records missing a birth year.",
    "DUPE_FAMILY_MATCH_THRESHOLD": "Score (0-100) used to verify if relatives (parents/spouses) match between two "
                                   "suspected duplicates.",
    "DUPE_FOLDER_NAME": "The name of the Task Folder created in RootsMagic to hold duplicate review tasks.",
    "DUPE_COLOR_SET": "The Color Set in RootsMagic (0-indexed) to apply the color value to.",

    # County
    "COUNTY_RM_DATABASE": "The filename of your RootsMagic tree (e.g., 'Your Tree.rmtree') located in your RootsMagic "
                          "Folder.",
    "COUNTY_SHAPEFILE": "The path to the Newberry Atlas '.shp' file containing historical county boundaries. Relative "
                         "to your Program Dir (it ships alongside the CountyFix tool), not the RootsMagic folder.",
    "COUNTY_CREATE_BACKUP": "Set to 'True' to automatically create a backup of your RootsMagic file before fixing it "
                             "(Highly Recommended!).",
    "COUNTY_DEBUG_MODE": "Set to 'True' to print extra diagnostic information to the console while processing."}

# ==========================================
# CUSTOM UI LABELS OVERRIDE
# ==========================================
# Add keys here if you want them to display differently than standard Title Case.
CUSTOM_LABELS = {"GEMINI_API_KEY": "Google Gemini API Key", "PROGRAM_DIR": "Genealogy Root Directory",
                 "RM_DIR": "RootsMagic Folder", "FTM_DIR": "Family Tree Maker Folder",
                 "MEDIA_DIR": "Base Media Directory", "CSV_DIR": "CSV Download Folder",
                 "DUPE_RM_DATABASE": "RootsMagic Database Path", "COUNTY_RM_DATABASE": "RootsMagic Database Path",
                 "CENSUS_URL": "Ancestry Census URL", "CENSUS_IMAGE_DIR": "Census Image Save Folder",
                 "CSV_FILE": "Downloaded CSV File Name", "LAC_URL": "Heritage Canadiana URL"}


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


class ModularToolbox(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("MGS Modular Toolbox")

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

        self.string_vars = {}
        self.active_process = None
        self.is_waiting_for_downloads = False
        self.debug_file_var = ctk.StringVar(value="")
        self.tabs_built = set()

        self.help_texts = {"Census Generator": "Welcome to the Census Generator!\n\n"
                                               "How to use:\n"
                                               "1. Check your settings and enter the Ancestry URL for the census "
                                               "collection you want to extract.\n"
                                               "2. Fill out your archival info (like State, County, Township).\n"
                                               "3. Click '🚀 Extract & Auto-Generate'. This will automatically open "
                                               "your web browser.\n"
                                               "4. Wait for the tool to finish extracting the records and download "
                                               "them.\n"
                                               "5. Once downloaded, the Toolbox will automatically process the images "
                                               "and generate your GEDCOM file!\n\n"
                                               "Note: If you already have a downloaded CSV file and just want to "
                                               "create the GEDCOM, use the 'Generate CSV GEDCOM' button instead.",
                           "Register Transcriber": "Welcome to the Register Transcriber!\n\n"
                                                   "How to use:\n"
                                                   "1. Place your historical register images into the designated "
                                                   "Parish folder in your project.\n"
                                                   "2. Ensure you have your Gemini API key saved in the Global "
                                                   "Settings.\n"
                                                   "3. Click 'Step 1: Gather Data (API)'. The AI will read, "
                                                   "transcribe, and translate the handwritten records into a "
                                                   "database file.\n"
                                                   "4. When finished, click 'Step 2: Generate GEDCOM' to convert that "
                                                   "database into a family tree file you can import.\n\n"
                                                   "Note: If the AI gets stuck or runs out of memory, try clicking "
                                                   "'Clear Cache'.",
                           "LAC Downloader": "Welcome to the LAC Image Downloader!\n\n"
                                             "How to use:\n"
                                             "1. Paste the complete Library and Archives Canada (or Heritage "
                                             "Canadiana) IIIF URL into the settings box.\n"
                                             "2. Click 'Download Images'.\n\n"
                                             "The script will automatically strip the URL to locate the manifest, "
                                             "parse the Roll Number (e.g., c2170), save the manifest reference, and "
                                             "dynamically download all high-resolution images into your specific "
                                             "LAC media folder.",
                           "Duplicate Finder": "Welcome to the Duplicate Finder!\n\n"
                                               "How to use:\n"
                                               "This tool scans your RootsMagic tree for people who might be "
                                               "duplicated, using smart name and age matching.\n\n"
                                               "1. CRITICAL: Make sure RootsMagic is completely CLOSED before running "
                                               "this.\n"
                                               "2. Click 'Run Script' and follow the prompts in the console below.\n"
                                               "3. The tool will safely create 'Review Merge' tasks inside your "
                                               "RootsMagic database. Open RootsMagic and check your Task List to "
                                               "see the results!",
                           "County Fixer": "Welcome to the County Fixer!\n\n"
                                           "How to use:\n"
                                           "This tool looks at the dates of events in your tree and automatically "
                                           "corrects the County or Territory names to match historical boundaries "
                                           "for that exact year.\n\n"
                                           "1. CRITICAL: Make sure RootsMagic is completely CLOSED before running "
                                           "this.\n"
                                           "2. Make sure you have backed up your tree.\n"
                                           "3. Click 'Run Script'. It will update the display names of your places "
                                           "safely without breaking your maps or tracking IDs.",
                           "⚙️ Global Settings": "Welcome to Global Settings!\n\n"
                                                 "How to use:\n"
                                                 "These are the master settings shared across all of your tools.\n\n"
                                                 "1. Set your 'PROGRAM_DIR' first. This is the main folder for your "
                                                 "genealogy files. All other folder paths build off of this one.\n"
                                                 "2. Add your Gemini API Key here so the AI transcription tool can "
                                                 "function.\n"
                                                 "3. Update your name and organization so the GEDCOM files properly "
                                                 "credit your research.\n"
                                                 "4. Don't forget to click 'Save Global Config' when you make changes!"}

        self.tab_builders: Dict[str, Callable[[ctk.CTkFrame], None]] = {"Census Generator": self._build_tab_census,
                                                                        "Register Transcriber": self._build_tab_church,
                                                                        "LAC Downloader": self._build_tab_lac,
                                                                        "Duplicate Finder": self._build_tab_dupe,
                                                                        "County Fixer": self._build_tab_county,
                                                                        "⚙️ Global Settings": self._build_tab_global}

        self._build_layout()
        self._load_env_to_vars()

        # Force a geometry update before building the first tab.
        # This fixes a known CustomTkinter bug where CTkScrollableFrame
        # crashes with a math error if drawn before the window has a height.
        self.update_idletasks()
        self.tabview.set("Census Generator")
        self._on_tab_change()

    def _on_closing(self):
        """Forcefully terminates the window and kills any zombie threads running in background."""
        self.is_waiting_for_downloads = False
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

        self.cancel_btn = ctk.CTkButton(self.input_frame, text="🛑 Cancel", fg_color="darkred", hover_color="red",
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
        self.is_waiting_for_downloads = False
        if self.active_process and self.active_process.poll() is None:
            self.console.put("\n[System] Sending termination signal to process...\n")
            self.active_process.terminate()

    def _load_env_to_vars(self):
        for category_dict, subfolder in ENV_TARGETS:
            saved = dotenv_values(env_path_for(subfolder))
            for section, fields in category_dict.items():
                for key, default_val in fields.items():
                    val = saved.get(key) or default_val
                    self.string_vars[key] = ctk.StringVar(value=val)

    def _save_env(self):
        for category_dict, subfolder in ENV_TARGETS:
            env_path = env_path_for(subfolder)
            env_path.parent.mkdir(parents=True, exist_ok=True)
            for section, fields in category_dict.items():
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
        cleaned = key_str.replace("URL", "Url").replace("CSV", "Csv").replace("ID", "Id")
        cleaned = cleaned.replace("_", " ").title()
        return cleaned

    def _build_tab_header(self, frame: ctk.CTkFrame, title: str, help_key: str):
        """A helper method to standardize tab headers and eliminate duplicate code."""
        header_frame = ctk.CTkFrame(frame, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(header_frame, text=title, font=ctk.CTkFont(size=24, weight="bold")).pack(side="left")
        ctk.CTkButton(header_frame, text="❔ Help", width=60, fg_color="#3B8ED0", hover_color="#2b7a4b",
                      command=lambda: self.show_help(help_key)).pack(side="right", padx=5)

    def _create_action_box(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        """A helper method to standardize the action button frames and reduce code duplication."""
        btn_box = ctk.CTkFrame(parent, fg_color="transparent")
        btn_box.pack(side="bottom", fill="x", pady=10)  # Docked to bottom to prevent clipping
        ctk.CTkButton(btn_box, text="Save Config", fg_color="#3B8ED0", hover_color="#2b7a4b",
                      command=self._save_env).pack(side="left", padx=5)
        return btn_box

    def _build_form_ui(self, parent, schema_dict, skip_keys: Optional[set] = None):
        # Lowered default height footprint, scroll frame will expand to fill middle space safely
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent", width=800, height=200)
        scroll.pack(side="top", fill="both", expand=True, pady=10)
        skip_keys = skip_keys or set()

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

    def _build_tab_global(self, frame: ctk.CTkFrame):
        self._build_tab_header(frame, "Global Environment Settings", "⚙️ Global Settings")

        # Build buttons first so they dock safely to the bottom
        btn_box = self._create_action_box(frame)

        self._build_form_ui(frame, GLOBAL_VARS)

    def _build_tab_census(self, frame: ctk.CTkFrame):
        self._build_tab_header(frame, "Census Generator", "Census Generator")

        # Unified action buttons (Docked to bottom)
        btn_box = self._create_action_box(frame)
        ctk.CTkButton(btn_box, text="Generate CSV GEDCOM", fg_color="#3B8ED0", hover_color="#2b7a4b",
                      command=lambda: self.execute_script("CENSUS_GEDCOM_SCRIPT", "census")).pack(side="left", padx=5)
        ctk.CTkButton(btn_box, text="🚀 Extract & Auto-Generate", fg_color="#2b7a4b", hover_color="#1e5935",
                      command=lambda: self.execute_script("CENSUS_EXTRACTOR_SCRIPT", "standalone")).pack(side="left",
                                                                                                         padx=5)

        self._build_form_ui(frame, CENSUS_VARS)

    @staticmethod
    def _list_prompt_files() -> List[str]:
        """Lists every .pmt file in ChurchRegisters/prompts, for the prompt-template dropdown."""
        prompts_dir = Path(__file__).resolve().parent / "ChurchRegisters" / "prompts"
        if not prompts_dir.is_dir():
            return ["Parish.pmt"]
        found = sorted((p.name for p in prompts_dir.glob("*.pmt")), key=str.lower)
        return found or ["Parish.pmt"]

    def _build_tab_church(self, frame: ctk.CTkFrame):
        self._build_tab_header(frame, "Register Transcriber", "Register Transcriber")

        prompt_frame = ctk.CTkFrame(frame, fg_color="transparent")
        prompt_frame.pack(side="top", fill="x", pady=(10, 5))
        prompt_lbl = ctk.CTkLabel(prompt_frame, text="Prompt Template ⓘ", font=ctk.CTkFont(weight="bold"),
                                  cursor="hand2")
        prompt_lbl.pack(side="left")
        ToolTip(prompt_lbl, TOOLTIP_DESCRIPTIONS["CHURCH_PROMPT_FILE"])
        ctk.CTkComboBox(prompt_frame, values=self._list_prompt_files(),
                        variable=self.string_vars["CHURCH_PROMPT_FILE"], width=300).pack(side="left", padx=10)

        debug_frame = ctk.CTkFrame(frame, fg_color="transparent")
        debug_frame.pack(side="top", fill="x", pady=(10, 5))
        ctk.CTkLabel(debug_frame, text="Debug Image Filename (Leave blank for Batch):",
                     font=ctk.CTkFont(weight="bold")).pack(side="left")
        ctk.CTkEntry(debug_frame, textvariable=self.debug_file_var, width=300).pack(side="left", padx=10)

        # Unified action buttons (Docked to bottom)
        btn_box = self._create_action_box(frame)
        ctk.CTkButton(btn_box, text="Step 1: Gather Data (API)", fg_color="#3B8ED0", hover_color="#2b7a4b",
                      command=lambda: self.execute_script("GATHER_DATA_SCRIPT", "church_api")).pack(side="left", padx=5)
        ctk.CTkButton(btn_box, text="Step 2: Generate GEDCOM", fg_color="#2b7a4b", hover_color="#1e5935",
                      command=lambda: self.execute_script("CHURCH_GEDCOM_SCRIPT", "church_gedcom")).pack(side="left",
                                                                                                         padx=5)
        ctk.CTkButton(btn_box, text="Clear Cache", fg_color="#991b1b", hover_color="#7f1d1d",
                      command=lambda: self.execute_script("CLEANUP_CACHE_SCRIPT", "standalone")).pack(side="right",
                                                                                                      padx=5)

        self._build_form_ui(frame, CHURCH_VARS, skip_keys={"CHURCH_PROMPT_FILE"})

    def _build_tab_lac(self, frame: ctk.CTkFrame):
        self._build_tab_header(frame, "LAC Downloader", "LAC Downloader")

        # Unified action buttons (Docked to bottom)
        btn_box = self._create_action_box(frame)
        ctk.CTkButton(btn_box, text="Download Images", fg_color="#2b7a4b", hover_color="#1e5935",
                      command=lambda: self.execute_script("LAC_DOWNLOADER_SCRIPT", "lac")).pack(side="left", padx=5)

        self._build_form_ui(frame, LAC_VARS)

    def _build_tab_dupe(self, frame: ctk.CTkFrame):
        self._build_tab_header(frame, "Duplicate Finder", "Duplicate Finder")

        ctk.CTkLabel(frame, text="Finds logical duplicate people in RootsMagic.", text_color="gray").pack(side="top",
                                                                                                          anchor="w",
                                                                                                          pady=(0, 20))

        # Unified action buttons (Docked to bottom)
        btn_box = self._create_action_box(frame)
        ctk.CTkButton(btn_box, text="Run Script", fg_color="#2b7a4b", hover_color="#1e5935",
                      command=lambda: self.execute_script("DUPE_SCRIPT", "standalone")).pack(side="left", padx=5)

        self._build_form_ui(frame, DUPE_VARS)

    def _build_tab_county(self, frame: ctk.CTkFrame):
        self._build_tab_header(frame, "County Fixer", "County Fixer")

        ctk.CTkLabel(frame, text="Fixes historical US county jurisdictions utilizing geopandas.",
                     text_color="gray").pack(side="top", anchor="w", pady=(0, 20))

        # Unified action buttons (Docked to bottom)
        btn_box = self._create_action_box(frame)
        ctk.CTkButton(btn_box, text="Run Script", fg_color="#2b7a4b", hover_color="#1e5935",
                      command=lambda: self.execute_script("COUNTY_SCRIPT", "standalone")).pack(side="left", padx=5)

        self._build_form_ui(frame, COUNTY_VARS)

    def execute_script(self, script_key, mode):
        """Prepares environment variables and launches an external script in a background thread."""
        self._save_env()

        script_path_var: Union[ctk.StringVar, None] = self.string_vars.get(script_key)
        if not script_path_var or not script_path_var.get().strip():
            self.console.put(
                f"\n[System] ❌ The script path for '{script_key}' is empty or missing in Global Settings.\n")
            return

        script_path_str = script_path_var.get().strip()
        prog_dir_var: Union[ctk.StringVar, None] = self.string_vars.get("PROGRAM_DIR")
        program_dir = prog_dir_var.get().strip() if prog_dir_var else ""

        if os.path.isabs(script_path_str):
            target_script_path = os.path.abspath(script_path_str)
        else:
            target_script_path = os.path.abspath(os.path.join(program_dir, script_path_str))

        if not os.path.exists(target_script_path):
            self.console.put(f"\n[System] ❌ Could not find the script at: {target_script_path}\n")
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

        media_base = self.string_vars.get("MEDIA_DIR").get().strip() if "MEDIA_DIR" in self.string_vars else "Media"
        rm_base = self.string_vars.get("RM_DIR").get().strip() if "RM_DIR" in self.string_vars else "Roots Magic 11"

        full_media_dir = resolve_path(program_dir, media_base)
        full_rm_dir = resolve_path(program_dir, rm_base)

        env_overrides = {}

        # Pre-resolve these specific nested directory variables
        if "CHURCH_IMAGE_DIR" in self.string_vars:
            env_overrides["CHURCH_IMAGE_DIR"] = resolve_path(full_media_dir, self.string_vars["CHURCH_IMAGE_DIR"].get())
        if "CENSUS_IMAGE_DIR" in self.string_vars:
            env_overrides["CENSUS_IMAGE_DIR"] = resolve_path(full_media_dir, self.string_vars["CENSUS_IMAGE_DIR"].get())
        if "LAC_IMAGE_DIR" in self.string_vars:
            env_overrides["LAC_IMAGE_DIR"] = resolve_path(full_media_dir, self.string_vars["LAC_IMAGE_DIR"].get())
        if "DUPE_RM_DATABASE" in self.string_vars:
            env_overrides["DUPE_RM_DATABASE"] = resolve_path(full_rm_dir, self.string_vars["DUPE_RM_DATABASE"].get())
        if "COUNTY_RM_DATABASE" in self.string_vars:
            env_overrides["COUNTY_RM_DATABASE"] = resolve_path(full_rm_dir,
                                                               self.string_vars["COUNTY_RM_DATABASE"].get())

        if mode.startswith("church"):
            ch_call: Union[ctk.StringVar, None] = self.string_vars.get("CHURCH_CALL_NUMBER")
            ch_repo: Union[ctk.StringVar, None] = self.string_vars.get("CHURCH_REPOSITORY")
            ch_loc: Union[ctk.StringVar, None] = self.string_vars.get("CHURCH_REPOSITORY_LOC")
            ch_url: Union[ctk.StringVar, None] = self.string_vars.get("CHURCH_COLLECTION_URL")
            ch_name: Union[ctk.StringVar, None] = self.string_vars.get("CHURCH_COLLECTION_NAME")

            env_overrides.update({"IMAGE_DIR": env_overrides.get("CHURCH_IMAGE_DIR", ""),
                                  "IMAGE_SOURCE_DIR": env_overrides.get("CHURCH_IMAGE_DIR", ""),
                                  "GEDCOM_OUTPUT_NAME": self.string_vars["CHURCH_GEDCOM_NAME"].get(),
                                  "MASTER_DB_NAME": self.string_vars["CHURCH_MASTER_DB_NAME"].get(),
                                  "CALL_NUMBER": ch_call.get() if ch_call else "",
                                  "REPOSITORY": ch_repo.get() if ch_repo else "",
                                  "REPOSITORY_LOC": ch_loc.get() if ch_loc else "",
                                  "COLLECTION_URL": ch_url.get() if ch_url else "",
                                  "COLLECTION_NAME": ch_name.get() if ch_name else ""})
        elif mode == "census":
            env_overrides.update({"IMAGE_DIR": env_overrides.get("CENSUS_IMAGE_DIR", ""),
                                  "IMAGE_SOURCE_DIR": env_overrides.get("CENSUS_IMAGE_DIR", "")})
        elif mode == "lac":
            lac_url = self.string_vars["LAC_URL"].get() if "LAC_URL" in self.string_vars else ""
            roll_num = "Unknown_Roll"

            match = re.search(r'lac_reel_([a-zA-Z0-9]+)', lac_url, re.IGNORECASE)
            if match:
                roll_num = match.group(1)

            lac_base_dir = env_overrides.get("LAC_IMAGE_DIR", f"{full_media_dir}/LAC")
            lac_out_dir = f"{lac_base_dir}/{roll_num}".replace("\\", "/")

            env_overrides.update({"LAC_OUTPUT_DIR": lac_out_dir, "ROLL_NUMBER": roll_num})

        run_env.update(env_overrides)

        self._set_ui_state("disabled")

        def on_complete():
            self._set_ui_state("normal")
            self.status_bar.configure(state="normal")
            self.status_bar.delete(0, "end")
            self.status_bar.insert(0, "System Ready")
            self.status_bar.configure(state="readonly")

        args = [target_script_path]
        if mode == "church_api" and self.debug_file_var.get().strip():
            args.append(self.debug_file_var.get().strip())

        target_cwd = os.path.dirname(target_script_path) if os.path.exists(target_script_path) else None

        threading.Thread(target=self._run_subprocess, args=(args, run_env, target_cwd, on_complete),
                         daemon=True).start()

    def _run_subprocess(self, safe_cmd, run_env, target_cwd, on_complete):
        import io
        run_env['PYTHONUNBUFFERED'] = '1'
        run_env['PYTHONIOENCODING'] = 'utf-8'

        script_name = os.path.basename(safe_cmd[0])
        self.console.put(f"\n[System] 🚀 Starting {script_name}...\n")
        self.console.put("-" * 50 + "\n")

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

            if self.active_process.returncode not in (0, 1, 15):
                self.console.put(
                    f"\n[System] ❌ {script_name} encountered an error. Please check the text above for clues.\n")
            elif self.active_process.returncode in (1, 15):
                self.console.put(f"\n[System] 🛑 Task was cancelled by you.\n")
            else:
                self.console.put(f"\n[System] ✨ {script_name} finished successfully!\n")

        except (OSError, subprocess.SubprocessError, ValueError) as e:
            self.console.put(f"\n[System] ❌ Failed to execute {script_name}:\n{str(e)}\n")

        self.active_process = None
        self.after(100, on_complete)

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
    app = ModularToolbox()
    app.mainloop()
