# Packaging & Distribution Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Package Scriptorium as a cross-platform `--onedir` app with a powerful dual-mode Windows installer, automated dependency downloads, GitHub auto-updating, and automated CI/CD builds.

**Architecture:** 
1. `Scriptorium.py` modified to act as a Single-Binary Router.
2. Configuration loading moved from `PROGRAM_DIR` to `%LOCALAPPDATA%\Scriptorium`.
3. Directory scaffolding updated.
4. Tampermonkey and Auto-Update triggers injected on startup.
5. `build.py` orchestrates PyInstaller.
6. `installer.iss` handles the dual-mode Windows setup + NodeJS + Gazetteer downloads.
7. `.github/workflows/build.yml` automates releases.

---

### Task 1: Single-Binary Router & Tampermonkey Hook (Scriptorium.py)
**Files:** `Scriptorium.py`
**Step 1:** At the bottom of `Scriptorium.py`, add CLI parsing for `--module <module_name>` to act as the subprocess router.
**Step 2:** Modify `_run_subprocess` to call `sys.executable` with `--module` instead of raw `.py` scripts.
**Step 3:** In the GUI init, add logic to check `self.global_env.get("TAMPERMONKEY_INSTALLED")`. If false/missing, prompt the user with a CustomTkinter messagebox. If they click "Install", use `webbrowser.open` on the Tampermonkey store link. Then launch `[GENEALOGY_DIR]/Scriptorium/Sys/Voyageur.js` via `os.startfile` fallback. Write `TAMPERMONKEY_INSTALLED=True` to `.env`.

### Task 2: Config Storage & Directory Scaffolding Defaults
**Files:** `Scriptorium.py`
**Step 1:** Create `get_config_dir()` to look for `%LOCALAPPDATA%\Scriptorium` (Standard) or the local directory if `.portable` exists. Update `_load_env` and `_save_env` to use it.
**Step 2:** In `__init__`, scaffold `Media`, `JSON`, `GEDCOM`, and `Sys\Gazetteer` inside `[GENEALOGY_DIR]\Scriptorium`. 

### Task 3: Auto-Updater (Scriptorium.py)
**Files:** `Scriptorium.py`
**Step 1:** Add a background thread function that hits `https://api.github.com/repos/alerum68/Scriptorium/releases/latest`.
**Step 2:** Compare `tag_name` to the current version. If newer, show a "New Version Available" popup with a button to open the release page.

### Task 4: PyInstaller Build Script (`build.py`)
**Files:** `build.py`
**Step 1:** Create `build.py` to run PyInstaller with `--onedir`.
**Step 2:** Do *not* bundle `Paleographer/prompts` into the binary. Manually copy the `prompts/` folder to `dist/Scriptorium/Prompts/`.
**Step 3:** Zip the `dist/Scriptorium` folder into `Scriptorium_Portable.zip`.

### Task 5: Inno Setup Installer Script
**Files:** `installer.iss`
**Step 1:** Create `installer.iss` with custom pages for `Genealogy` and `RootsMagic` directories, and the Standard vs Portable radio button.
**Step 2:** Add `[Code]` logic to check for `npm`. If missing, download `node-v20.x-x64.msi` and `msiexec /i node.msi /qn`. Then `Exec()` the `npm install -g @google/antigravity-cli` command.
**Step 3:** Use the Inno Download Plugin (or built-in `DownloadTemporaryFile`) to download `https://publications.newberry.org/ahcb/downloads/gis/US_AtlasHCB_Counties.zip` and the Canadian DB zip from GitHub raw, extracting them to `[Genealogy_Dir]\Scriptorium\Sys\Gazetteer`.

### Task 6: GitHub Actions CI/CD
**Files:** `.github/workflows/build.yml`
**Step 1:** Create a YAML workflow triggering on `push: tags: - 'v*'`.
**Step 2:** Define jobs for `windows-latest`, `macos-latest`, `ubuntu-latest`.
**Step 3:** Checkout code, run `pip install`, run `python build.py`.
**Step 4:** On Windows, run `iscc installer.iss`.
**Step 5:** Upload the resulting artifacts to the GitHub Release.
