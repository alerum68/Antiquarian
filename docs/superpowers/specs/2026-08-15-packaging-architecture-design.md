# Packaging & Distribution Architecture Design

**Goal:** Package Scriptorium as a cross-platform `--onedir` PyInstaller app with a powerful, dual-mode Windows installer, automated dependency downloads, GitHub auto-updating, and CI/CD automated builds.

## Section 1: PyInstaller & Subprocess Routing
Because Scriptorium heavily utilizes background tasks, packaging the app as a single `--onefile` executable causes severe extraction delays on every subprocess launch.
* **Build Mode:** We compile Scriptorium via PyInstaller in `--onedir` mode.
* **Single-Binary Router:** `Scriptorium.py` is updated to handle a `--module` CLI flag. Instead of launching `.py` files, it calls itself (e.g., `Scriptorium.exe --module Voyageur`) and directly routes execution to the background task, bypassing the GUI.
* **Living Prompts:** The `Paleographer/prompts` folder is copied directly into the `dist/` output folder instead of being baked into the `.exe`. This allows users to manually edit `.pmt` files in the distribution.

## Section 2: Dual-Mode Installer & Dependencies (Inno Setup)
The `installer.iss` script offers two paradigms:
* **Standard Mode:** Installs binaries to `C:\Program Files\Scriptorium`. Scaffolds directories in the user's selected `Genealogy` directory and saves `.env` to `%LOCALAPPDATA%`.
* **Portable Mode:** Bypasses `Program Files`. Installs everything directly into `[Genealogy_Dir]\Scriptorium`. Drops a `.portable` file and saves `.env` next to the `.exe`.

**Automated Dependency Resolution:**
* **Node.js / AGY CLI:** Installer checks for `npm`. If missing, it prompts the user, silently downloads the Node.js MSI, installs it, and runs `npm install -g AGY-cli`.
* **Gazetteer Databases:** Installer downloads the `US_AtlasHCB_Counties.zip` (503 MB) and the Canadian DB from the GitHub repo, and extracts them into `\Sys\Gazetteer`.

## Section 3: First-Launch UX & Auto-Updating
* **Tampermonkey:** On first launch, `Scriptorium.py` checks if Tampermonkey is configured. If not, it opens the browser to install it, then launches `\Sys\Voyageur.js` to trigger the script installation automatically.
* **Auto-Updating:** On startup, `Scriptorium.py` checks `https://api.github.com/repos/alerum68/Scriptorium/releases/latest`. If a newer version is found, it prompts the user to download and run the new installer.

## Section 4: CI/CD Pipeline (GitHub Actions)
* A `.github/workflows/build.yml` pipeline triggers whenever a new GitHub Release tag is created.
* GitHub automatically provisions Windows, Mac, and Linux VMs.
* It builds the `.exe` (and Inno Setup installer), `.dmg`, and `.deb`.
* It automatically attaches these compiled binaries to the GitHub release page.
*(Future: SignPath Foundation will be integrated into this CI to sign the binaries for free).*
