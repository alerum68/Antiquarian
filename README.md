# Michif Genealogical Society Toolbox

A desktop toolkit that takes the tedious parts of genealogy research: transcribing historical documents,
converting records into family tree files, downloading archival images, and cleaning up your database. It
automates all of it, so you can spend more time on the research itself.

Everything is controlled from a single application window. No command line, no code editing required.

## What It Does

Launch the Toolbox and you'll find a tab for each tool below. Enter your settings once, and the app remembers
them for next time.

**Census Records**
- **Census Extractor**: Point it at an Ancestry.com census page and it downloads the record images and data
  for you automatically.
- **Census Converter**: Turns that census data into a ready-to-import family tree file (GEDCOM), automatically
  grouping people into households and flagging anything that needs a second look.

**Church Registers**
- **Register Transcriber**: Reads photos of handwritten historical church registers (baptisms, marriages, and
  burials, including French and Latin) and translates and transcribes them into a structured, searchable
  record.
- **Register to GEDCOM**: Converts those transcribed records into a family tree file, complete with source
  citations and linked witnesses or godparents.

**Archival Images**
- **LAC Downloader**: Paste a link from Library and Archives Canada or Heritage Canadiana and it downloads
  every page image from that microfilm roll in full resolution, neatly organized into its own folder.

**Tree Maintenance**
- **Duplicate Finder**: Scans your RootsMagic tree for people who may have been entered twice, using smart
  name and age matching, and creates review tasks for anything it finds.
- **County Fixer**: Automatically corrects county and territory names in your tree to match historical
  boundaries for the actual date of each event.

## Getting Started

### What You'll Need
- **Python 3.8 or newer**
- **[TamperMonkey](https://www.tampermonkey.net/)** (a free browser extension), used by the Census Extractor
- The **[Newberry Atlas of Historical County Boundaries](https://publications.newberry.org/ahcb/downloads/gis/US_AtlasHCB_Counties.zip)**, if you plan to use the County Fixer. Download and extract it into a
  subfolder alongside `CountyFix.py`.

### Installation
1. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```
2. Install `CensusExtractor.js` in your browser's TamperMonkey dashboard.
3. Launch the Toolbox:
   ```bash
   python MGSToolbox.py
   ```

That's it. The app handles all configuration from there. Enter your folder paths, API key, and preferences
in the Global Settings tab, and every tool will use them automatically. 

## A Note on Safety

The **Duplicate Finder** and **County Fixer** make direct changes to your RootsMagic database file. Please:

- **Close RootsMagic completely** before running either tool.
- **Always back up your tree** before making changes.

This software is provided as-is, with no warranty. The author is not responsible for any data loss or database
corruption.

## License

This project is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE). In short: you're free to
use, modify, and share it for any noncommercial purpose (personal genealogy research, other historical or
genealogical societies, education, etc.), but it may not be used to build or sell a commercial product or
service. See the [LICENSE](LICENSE) file for the full terms.
