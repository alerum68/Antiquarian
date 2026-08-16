import os
import re
import shutil
import subprocess


def get_version() -> str:
    """Antiquarian.py's own APP_VERSION is the single source of truth - everything else
    (this build's zip filename, the compiled installer's filename/AppVersion) derives from
    it rather than keeping its own separately-hardcoded copy, which is exactly how the
    installer and the app itself drifted out of sync before."""
    with open("Antiquarian.py", "r", encoding="utf-8") as f:
        text = f.read()
    match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise RuntimeError("Could not find APP_VERSION in Antiquarian.py")
    return match.group(1)


def build():
    version = get_version()
    # Package the Antiquarian binary natively. --onedir prevents extraction penalties
    # for background subprocesses during runtime.
    print("Running PyInstaller...")
    subprocess.run([
        "python", "-m", "PyInstaller",
        "--name", "Antiquarian",
        "--onedir",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--add-data", "Commissioner/assets/theme.json;Commissioner/assets",
        "--add-data", "Archivist/settings_schema.yaml;Archivist",
        "--add-data", "Voyageur/settings_schema.yaml;Voyageur",
        "--add-data", "Paleographer/settings_schema.yaml;Paleographer",
        "--add-data", "Registrar/settings_schema.yaml;Registrar",
        "--add-data", "Gazetteer/settings_schema.yaml;Gazetteer",
        "--add-data", "PDFix/settings_schema.yaml;PDFix",
        "Antiquarian.py"
    ], check=True)

    dist_dir = os.path.join("dist", "Antiquarian")

    # Expose the raw prompts directory so power users can modify .pmt templates directly
    # without recompiling the executable.
    print("Copying Prompts...")
    prompts_src = os.path.join("Paleographer", "prompts")
    prompts_dst = os.path.join(dist_dir, "Prompts")
    if os.path.exists(prompts_dst):
        shutil.rmtree(prompts_dst)
    shutil.copytree(prompts_src, prompts_dst)

    # Expose the Voyageur userscript directly in the Sys directory to facilitate
    # easy browser installation via the first-launch Tampermonkey prompt.
    print("Copying Voyageur.js...")
    sys_dst = os.path.join(dist_dir, "Sys")
    os.makedirs(sys_dst, exist_ok=True)
    shutil.copy(os.path.join("Voyageur", "Voyageur.js"), os.path.join(sys_dst, "Voyageur.js"))

    # Bundle a portable version for users bypassing the Inno Setup installer. The zip's own
    # filename is versioned, but the folder inside it stays plain "Antiquarian" - unzipping
    # two different versions side by side shouldn't produce two differently-named folders.
    zip_base = f"Antiquarian_Portable_{version}"
    print(f"Zipping {zip_base}.zip...")
    shutil.make_archive(zip_base, "zip", "dist", "Antiquarian")

    # Hand the version to the next CI step (Inno Setup compile) via a real env var, so
    # installer.iss's AppVersion/output filename stay in sync with this same version
    # instead of carrying their own separately-maintained copy.
    github_env = os.environ.get("GITHUB_ENV")
    if github_env:
        with open(github_env, "a", encoding="utf-8") as f:
            f.write(f"APP_VERSION={version}\n")

    print(f"Build complete. Version {version}.")


if __name__ == "__main__":
    build()
