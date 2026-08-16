# Packaging & Distribution Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** Package Scriptorium as a cross-platform `--onedir` app, refactor `.env` storage for read-only install directories, and create a dual-mode (Standard/Portable) Windows installer via Inno Setup.

**Architecture:** 
1. `Scriptorium.py` modified to act as a Single-Binary Router for subprocesses.
2. Configuration loading moved from `PROGRAM_DIR` to `%LOCALAPPDATA%\Scriptorium` (unless `.portable` exists).
3. Directory scaffolding updated to nest inside `GENEALOGY_DIR\Scriptorium`.
4. `build.py` orchestrates PyInstaller.
5. `installer.iss` handles the dual-mode Windows setup.

**Tech Stack:** Python, PyInstaller, Inno Setup (`.iss`).

---

### Task 1: Single-Binary Router (Scriptorium.py)

**Files:**
- Modify: `Scriptorium.py`

**Step 1: Write the failing test**
*N/A - This is an architectural launch script modification. We will verify manually or via integration.*

**Step 2: Write minimal implementation**

At the very bottom of `Scriptorium.py`:
```python
if __name__ == "__main__":
    import sys
    import importlib
    
    if "--module" in sys.argv:
        # Single-Binary Router mode: bypass GUI, run the requested module directly
        module_name = sys.argv[sys.argv.index("--module") + 1]
        
        # Determine correct python module path (e.g., "Voyageur.Voyageur")
        if module_name in ["Voyageur", "Paleographer", "Archivist"]:
            mod = importlib.import_module(f"{module_name}.{module_name}")
        elif module_name in ["Registrar", "Gazetteer"]:
            mod = importlib.import_module(f"Leaf.{module_name}")
        else:
            print(f"Unknown module {module_name}")
            sys.exit(1)
            
        if hasattr(mod, "main"):
            mod.main()
        sys.exit(0)
    else:
        # Standard GUI mode
        app = ScriptoriumApp()
        app.mainloop()
```

In `Scriptorium.py` `_run_subprocess` (around line 1890):
Change the subprocess command construction so that instead of executing the python script file directly, it passes the `--module` flag to itself.
```python
    def _run_subprocess(self, safe_cmd, run_env, target_cwd, on_complete, on_success=None):
        # safe_cmd usually looks like ["Voyageur/Voyageur.py", "--args..."]
        # Convert it to: [sys.executable, "--module", "Voyageur", "--args..."]
        
        # Extract the module name from the script path (e.g., "Voyageur/Voyageur.py" -> "Voyageur")
        script_path = safe_cmd[0]
        module_name = Path(script_path).stem
        
        # Build the router command
        router_cmd = [sys.executable, "--module", module_name] + safe_cmd[1:]
        
        # The rest of the subprocess call remains the same
        try:
            self.active_process = subprocess.Popen(router_cmd, stdin=subprocess.PIPE,
                                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0,
                                                   text=True, env=run_env, cwd=target_cwd,
                                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
```

**Step 3: Commit**
```bash
git add Scriptorium.py
git commit -m "feat(core): implement single-binary router for subprocess launching"
```

### Task 2: Configuration Storage Refactor

**Files:**
- Modify: `Scriptorium.py`

**Step 1: Write minimal implementation**

Add a `get_config_dir()` helper to `Scriptorium.py` near the top:
```python
def get_config_dir() -> Path:
    """Returns the directory where .env files should be stored."""
    program_dir = Path(__file__).parent.resolve()
    if (program_dir / '.portable').exists():
        return program_dir
        
    # Standard Mode: Use OS AppData
    if sys.platform == "win32":
        app_data = Path(os.getenv("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        app_data = Path.home() / ".config"
        
    config_dir = app_data / "Scriptorium"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir
```

Update `_load_env` and `_save_env` in `Scriptorium.py`:
Change `env_path = self.repo_root / ".env"` to:
```python
    env_path = get_config_dir() / ".env"
```
And similarly for the module-specific `.env` paths:
Change `env_path = self.repo_root / module_dir / ".env"` to:
```python
    env_path = get_config_dir() / f"{module_dir}.env"
```
*(Note: Because we are moving them to a flat `%LOCALAPPDATA%` folder, we rename `Voyageur/.env` to `Voyageur.env` to prevent collisions).*

**Step 2: Commit**
```bash
git add Scriptorium.py
git commit -m "feat(core): move config storage to LocalAppData for read-only installs"
```

### Task 3: Directory Scaffolding Defaults

**Files:**
- Modify: `Scriptorium.py`

**Step 1: Write minimal implementation**

In `Scriptorium.py`'s `__init__`, after loading `GLOBAL_VARS`:
```python
    # Ensure Scriptorium defaults exist in GENEALOGY_DIR
    gen_dir = Path(self.global_env.get("GENEALOGY_DIR", str(Path.home() / "Documents" / "Genealogy")))
    
    # Check if we are running in portable mode
    if (Path(__file__).parent.resolve() / '.portable').exists():
        scriptorium_dir = Path(__file__).parent.resolve()
    else:
        scriptorium_dir = gen_dir / "Scriptorium"
        
    scriptorium_dir.mkdir(parents=True, exist_ok=True)
    
    # Set fallback defaults for the core directories if they aren't explicitly set in the .env
    if "MEDIA_DIR" not in self.global_env:
        self.global_env["MEDIA_DIR"] = str(scriptorium_dir / "Media")
    if "JSON_DIR" not in self.global_env:
        self.global_env["JSON_DIR"] = str(scriptorium_dir / "JSON")
    if "GEDCOM_OUTPUT_PATH" not in self.global_env:
        self.global_env["GEDCOM_OUTPUT_PATH"] = str(scriptorium_dir / "GEDCOM")
        
    # Scaffold them
    Path(self.global_env["MEDIA_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(self.global_env["JSON_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(self.global_env["GEDCOM_OUTPUT_PATH"]).mkdir(parents=True, exist_ok=True)
```

**Step 2: Commit**
```bash
git add Scriptorium.py
git commit -m "feat(core): scaffold directories inside Genealogy_Dir or portable root"
```

### Task 4: PyInstaller Build Script (`build.py`)

**Files:**
- Create: `build.py`

**Step 1: Write minimal implementation**

Create `build.py` in the project root:
```python
import os
import subprocess
import shutil
from pathlib import Path

def main():
    print("Building Scriptorium (--onedir)...")
    
    # Clean previous builds
    shutil.rmtree("build", ignore_errors=True)
    shutil.rmtree("dist", ignore_errors=True)
    
    # Collect all the required dynamic imports and data files
    hidden_imports = [
        "--hidden-import=Voyageur.Voyageur",
        "--hidden-import=Paleographer.Paleographer",
        "--hidden-import=Archivist.Archivist",
        "--hidden-import=Commissioner.models"
    ]
    
    data_files = [
        "--add-data=Voyageur/field_maps;Voyageur/field_maps",
        "--add-data=Paleographer/prompts;Paleographer/prompts",
        "--add-data=Archivist/FactTypes.json;Archivist"
    ]
    
    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name=Scriptorium",
    ] + hidden_imports + data_files + ["Scriptorium.py"]
    
    subprocess.run(cmd, check=True)
    
    # Create the Portable Zip
    print("Creating Scriptorium_Portable.zip...")
    portable_dir = Path("dist/Scriptorium")
    (portable_dir / ".portable").touch()
    
    shutil.make_archive("dist/Scriptorium_Portable", 'zip', "dist", "Scriptorium")
    print("Build complete!")

if __name__ == "__main__":
    main()
```

**Step 2: Commit**
```bash
git add build.py
git commit -m "feat(build): add pyinstaller build script for onedir and portable zip"
```

### Task 5: Inno Setup Installer Script

**Files:**
- Create: `installer.iss`

**Step 1: Write minimal implementation**

Create `installer.iss` in the project root. Include custom pascal scripting to handle the Standard vs Portable radio buttons, and the Genealogy/RootsMagic directory text boxes. 
*(Note: Full Inno Setup Pascal code is verbose; the implementer will draft the `.iss` file with a `[Code]` block utilizing `CreateCustomPage`, `CreateRadioButton`, and `CreateDirEditControl`, and write the results to `%LOCALAPPDATA%\Scriptorium\.env` in the `CurStepChanged` function).*

**Step 2: Commit**
```bash
git add installer.iss
git commit -m "feat(build): add dual-mode Inno Setup installer script"
```
