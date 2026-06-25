import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()

BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist"

SPEC_FILE = ROOT / "interact_agent.spec"

ISCC = shutil.which("ISCC.exe") or shutil.which("iscc.exe")
if ISCC is None:
    raise RuntimeError("ISCC.exe not found in PATH.")

INSTALLER_SCRIPT = ROOT / "installer" / "interact_agent.iss"

OUTPUT_DIR = ROOT / "installer" / "output"

VERSION_FILE = ROOT / "src" / "agent_version.py"


def run(cmd, env=None):
    subprocess.run(cmd, check=True, env=env)


def get_version():
    text = VERSION_FILE.read_text(encoding="utf-8")

    match = re.search(r'VERSION\s*=\s*"([^"]+)"', text)
    if not match:
        raise RuntimeError("VERSION not found.")

    return match.group(1)


def clean():
    shutil.rmtree(BUILD_DIR, ignore_errors=True)
    shutil.rmtree(DIST_DIR, ignore_errors=True)


def build_installer(version: str):
    env = os.environ.copy()

    env["INTERACT_VERSION"] = version
    env["INTERACT_VERSION_INFO"] = f"{version}.0"

    run(
        [
            ISCC,
            str(INSTALLER_SCRIPT),
        ],
        env=env,
    )


def main():
    version = get_version()

    print(f"\nBuilding InterAct Desktop Agent {version}\n")

    clean()

    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            str(SPEC_FILE),
        ]
    )

    exe = DIST_DIR / "InterActDesktopAgent.exe"

    if not exe.exists():
        raise RuntimeError("Executable not found.")

    build_installer(version)

    installer = OUTPUT_DIR / f"InterAct-Desktop-Agent-{version}-Setup.exe"

    if not installer.exists():
        raise RuntimeError("Installer not found.")

    print("\nSUCCESS\n")
    print(installer)


if __name__ == "__main__":
    main()