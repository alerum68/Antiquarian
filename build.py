import os
import shutil
import subprocess


def build():
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

    # Bundle a portable version for users bypassing the Inno Setup installer
    print("Zipping Antiquarian_Portable.zip...")
    shutil.make_archive("Antiquarian_Portable", "zip", "dist", "Antiquarian")

    print("Build complete.")


if __name__ == "__main__":
    build()
