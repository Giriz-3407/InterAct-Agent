import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()

BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist"

SPEC_FILE = ROOT / "interact_agent.spec"

ISCC = Path(r"C:\Program Files\Inno Setup 7\ISCC.exe")
INSTALLER_SCRIPT = ROOT / "installer" / "interact_agent.iss"

OUTPUT_DIR = ROOT / "installer" / "output"


def run(cmd):
    print(f"\n> {' '.join(str(c) for c in cmd)}\n")
    subprocess.run(cmd, check=True)


def clean():
    print("Cleaning old build...")

    shutil.rmtree(BUILD_DIR, ignore_errors=True)
    shutil.rmtree(DIST_DIR, ignore_errors=True)


def build_exe():
    print("Building executable...")

    run([
        sys.executable,
        "-m",
        "PyInstaller",
        str(SPEC_FILE)
    ])


def verify_exe():
    exe = DIST_DIR / "InterActDesktopAgent.exe"

    if not exe.exists():
        raise FileNotFoundError(exe)

    print("Executable verified.")


def build_installer():
    print("Building installer...")

    run([
        str(ISCC),
        str(INSTALLER_SCRIPT)
    ])


def verify_installer():

    installers = list(OUTPUT_DIR.glob("*.exe"))

    if not installers:
        raise FileNotFoundError("Installer not found.")

    print("\nRelease build successful.\n")

    print("Installer:")

    for installer in installers:
        print(installer)


def main():

    if not ISCC.exists():
        raise FileNotFoundError(ISCC)

    clean()

    build_exe()

    verify_exe()

    build_installer()

    verify_installer()


if __name__ == "__main__":
    main()