# Packaging & Distribution Architecture Design

**Goal:** Package Scriptorium as a cross-platform compiled application with a powerful, dual-mode Windows installer that protects user data and maximizes subprocess performance.

## Section 1: PyInstaller & Subprocess Routing
Because Scriptorium heavily utilizes background tasks (like Voyageur and Paleographer), packaging the app as a single `--onefile` executable would cause severe performance penalties due to extraction delays on every subprocess launch.

* **Build Mode:** We will use a `build.py` script that compiles Scriptorium via PyInstaller in `--onedir` mode (creating an application folder).
* **Single-Binary Router:** `Scriptorium.py` will be updated to handle a `--module` CLI flag. Instead of launching `.py` files, it will call itself (e.g., `Scriptorium.exe --module Voyageur`) and directly route execution to the requested background task, bypassing the GUI.

## Section 2: Dual-Mode Installer (Inno Setup)
We will provide an Inno Setup script (`installer.iss`) that offers two installation paradigms:

### A. Standard Mode
* Installs the application binaries to the secure, read-only `C:\Program Files\Scriptorium`.
* Prompts the user for their **Genealogy Directory** and **RootsMagic Directory**.
* Saves those paths in a `.env` configuration file located in `%LOCALAPPDATA%\Scriptorium`.
* **Scaffolding:** When Scriptorium launches, it reads the `.env` and automatically creates `Media`, `JSON`, `Working`, and `GEDCOM` explicitly inside `[Genealogy_Directory]\Scriptorium`.

### B. Portable Mode (Self-Contained)
* Bypasses `Program Files` entirely.
* Prompts the user for their **Genealogy Directory** and **RootsMagic Directory**.
* Installs the entire application folder directly into `[Genealogy_Directory]\Scriptorium`.
* Drops a hidden `.portable` trigger file into the directory.
* Saves the `.env` configuration file directly next to the `.exe`.
* **Scaffolding:** Because it is portable, `Media`, `JSON`, and `GEDCOM` are scaffolded directly inside that same install folder.

*Note: The `build.py` script will also generate a raw `Scriptorium_Portable.zip` containing the `.portable` file for users who wish to bypass the installer entirely.*

## Section 3: Configuration Refactor
To support Standard Mode's read-only install directory, `Scriptorium.py`'s configuration logic will be refactored to look for the `.portable` file on startup:
* **If `.portable` exists:** Read/write `.env` settings from `PROGRAM_DIR`.
* **If `.portable` is missing:** Read/write `.env` settings from the OS user-data folder (`%LOCALAPPDATA%\Scriptorium` or Mac/Linux equivalent).
