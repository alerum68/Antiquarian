# The Scriptorium

*A genealogy research toolkit built for the Michif Genealogical Society.*

A desktop toolkit that takes the tedious parts of genealogy research: transcribing historical documents,
converting records into family tree files, downloading archival images, and cleaning up your database. It
automates all of it, so you can spend more time on the research itself.

Everything is controlled from a single application window. No command line, no code editing required.

## What It Does

Launch The Scriptorium and you'll find a tab for each tool below, arranged in the order you'd typically use
them: Gather your source material, Analyze anything that still needs AI transcription, then Create your
GEDCOM. Enter your settings once, and the app remembers them for next time.

**Voyageur (Gather)**

Talks to a repository's website and brings back images, plus any index data the site already provides. Pick
a repository from the dropdown:
- **Ancestry**: scrapes an already-indexed census page (the site has already transcribed it, so no AI is
  needed later) and downloads the record images and index data automatically.
- **FamilySearch**: reads an indexed church-register page's Image Index table and citation info, and
  automatically links duplicate entries from overlapping registers back to the same person. (Image download
  for FamilySearch is upcoming; for now this gathers index data and citations.)
- **LAC**: downloads every page image from a Library and Archives Canada / Heritage Canadiana microfilm roll
  in full resolution, neatly organized into its own folder.

**Paleographer (Analysis)**

Reads photos or PDFs of historical documents (church registers, scrip applications, and any other record
type you add) and translates and transcribes them into a structured, searchable record using AI. Adding
support for a new kind of document is as simple as adding one prompt file, no code required. Large multi-page
documents are submitted as a background batch job rather than tying up the app.

**Archivist (Create)**

One "Generate GEDCOM" button: reads whichever JSON file Voyageur or Paleographer most recently produced,
automatically detects what kind of record it holds (census, church/parish, scrip...), and builds a
ready-to-import family tree file (GEDCOM) - grouping people into households, linking witnesses and
godparents, and flagging anything that needs a second look. No need to pick a mode yourself.

**Tree Maintenance**
- **Registrar**: Scans your RootsMagic tree for people who may have been entered twice, using smart
  name and age matching, and creates review tasks for anything it finds.
- **Gazetteer**: Automatically corrects county and territory names in your tree to match historical
  boundaries for the actual date of each event.

## Getting Started

### What You'll Need
- **Python 3.8 or newer**
- **[TamperMonkey](https://www.tampermonkey.net/)** (a free browser extension), used by Voyageur's Ancestry
  and FamilySearch gathers (LAC downloads directly, no browser extension needed)
- The **[Newberry Atlas of Historical County Boundaries](https://publications.newberry.org/ahcb/downloads/gis/US_AtlasHCB_Counties.zip)**, if you plan to use Gazetteer. Download and extract it into a
  subfolder alongside `Gazetteer.py`.

### Installation
1. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```
2. Install `Voyageur/Voyageur.js` in your browser's TamperMonkey dashboard - one script covers
   every repository that needs a live browser session, detected automatically from the URL.
3. Launch The Scriptorium:
   ```bash
   python Scriptorium.py
   ```

That's it. The app handles all configuration from there. Enter your folder paths, API key, and preferences
in the Global Settings tab, and every tool will use them automatically. 

## A Note on Safety

**Registrar** and **Gazetteer** make direct changes to your RootsMagic database file. Please:

- **Close RootsMagic completely** before running either tool.
- **Always back up your tree** before making changes.

This software is provided as-is, with no warranty. The author is not responsible for any data loss or database
corruption.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for planned work and ideas that aren't scheduled yet.

## License

This project is licensed under the [PolyForm Noncommercial License 1.0.0](LICENSE). In short: you're free to
use, modify, and share it for any noncommercial purpose (personal genealogy research, other historical or
genealogical societies, education, etc.), but it may not be used to build or sell a commercial product or
service. See the [LICENSE](LICENSE) file for the full terms.
