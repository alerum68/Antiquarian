# Packaging & Distribution Implementation Plan

> **For AGY:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Package Antiquarian as a cross-platform `--onedir` app with a powerful dual-mode Windows installer, automated dependency downloads, GitHub auto-updating, and automated CI/CD builds.

**Architecture:** 
1. `Antiquarian.py` modified to act as a Single-Binary Router.
2. Configuration loading moved from `PROGRAM_DIR` to `%LOCALAPPDATA%\Antiquarian`.
3. Directory scaffolding updated.
4. Tampermonkey and Auto-Update triggers injected on startup.
5. `build.py` orchestrates PyInstaller and copies `Voyageur.js` to `Sys`.
6. `installer.iss` handles the dual-mode Windows setup + NodeJS + Gazetteer downloads.
7. `.github/workflows/build.yml` automates sandbox and release builds.

---

### Task 1: Single-Binary Router & Tampermonkey Hook (Antiquarian.py)
**Files:** `Antiquarian.py`
**Step 1:** At the bottom of `Antiquarian.py`, add CLI parsing for `--module <module_name>` to act as the subprocess router.
**Step 2:** Modify `_run_subprocess` to call `sys.executable` with `--module` instead of raw `.py` scripts.
**Step 3:** In the GUI init, add logic to check `self.global_env.get("TAMPERMONKEY_INSTALLED")`. If false/missing, prompt the user with a CustomTkinter messagebox. If they click "Install", use `webbrowser.open` on the Tampermonkey store link. Then launch `[GENEALOGY_DIR]/Antiquarian/Sys/Voyageur.js` via `os.startfile` fallback. Write `TAMPERMONKEY_INSTALLED=True` to `.env`.

### Task 2: Config Storage & Directory Scaffolding Defaults
**Files:** `Antiquarian.py`
**Step 1:** Create `get_config_dir()` to look for `%LOCALAPPDATA%\Antiquarian` (Standard) or the local directory if `.portable` exists. Update `_load_env` and `_save_env` to use it.
**Step 2:** In `__init__`, scaffold `Media`, `JSON`, `GEDCOM`, and `Sys\Gazetteer` inside `[GENEALOGY_DIR]\Antiquarian`. 

### Task 3: Auto-Updater (Antiquarian.py)
**Files:** `Antiquarian.py`
**Step 1:** Add a background thread function that hits `https://api.github.com/repos/alerum68/Antiquarian/releases/latest`.
**Step 2:** Compare `tag_name` to the current version. If newer, show a "New Version Available" popup with a button to open the release page.

### Task 4: PyInstaller Build Script (`build.py`)
**Files:** `build.py`
**Step 1:** Create `build.py` to run PyInstaller with `--onedir`.
**Step 2:** Do *not* bundle `Paleographer/prompts` into the binary. Manually copy the `prompts/` folder to `dist/Antiquarian/Prompts/`.
**Step 3:** Manually copy `Voyageur/Voyageur.js` to `dist/Antiquarian/Sys/Voyageur.js`.
**Step 4:** Zip the `dist/Antiquarian` folder into `Antiquarian_Portable.zip`.

### Task 5: Inno Setup Installer Script
**Files:** `installer.iss`
**Step 1:** Create `installer.iss` with custom pages for `Genealogy` and `RootsMagic` directories, and the Standard vs Portable radio button.
**Step 2:** Add `[Code]` logic to check for `npm`. If missing, download `node-v20.x-x64.msi` and `msiexec /i node.msi /qn`. Then `Exec()` the `npm install -g @google/AGY-cli` command.
**Step 3:** Use the Inno Download Plugin (or built-in `DownloadTemporaryFile`) to download `https://publications.newberry.org/ahcb/downloads/gis/US_AtlasHCB_Counties.zip` and the Canadian DB zip from GitHub raw, extracting them to `[Genealogy_Dir]\Antiquarian\Sys\Gazetteer`.

### Task 6: GitHub Actions CI/CD (Sandbox & Release)
**Files:** `.github/workflows/build.yml`
**Step 1:** Create a YAML workflow triggering on TWO events: `push` to `main` (Sandbox) and `push` to `tags` (Release).
**Step 2:** Define jobs for `windows-latest`. Checkout code, run `pip install`, run `python build.py`.
**Step 3:** On Windows, run `iscc installer.iss`.
**Step 4:** For pushes to `main`, upload the `.exe` as a "Workflow Artifact" (a private zip you can download to test without publishing).
**Step 5:** For pushes to `tags`, upload the `.exe` directly to a public GitHub Release.
