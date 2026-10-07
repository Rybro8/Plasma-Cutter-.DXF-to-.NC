"""Check GitHub for a newer dxftogcode and offer to install it.

Git clones are updated with `git pull --ff-only`. ZIP downloads are updated by
downloading the latest main branch and copying the dxftogcode folder over this one.
Exits with UPDATED (10) when files changed so install_and_run.bat can restart itself.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

REPO = "Rybro8/Plasma-Cutter-.DXF-to-.NC"
BRANCH = "main"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(APP_DIR)
VERSION_FILE = os.path.join(APP_DIR, ".version")
SKIP = {".venv", ".version", "__pycache__"}
PROMPT_SECONDS = 15
UPDATED = 10


def ask(question):
    """Ask Y/N; default to Yes after PROMPT_SECONDS so an unattended launch still starts."""
    print(f"{question} [Y/n] (updating in {PROMPT_SECONDS}s) ", end="", flush=True)
    try:
        import msvcrt
    except ImportError:
        return input().strip().lower() != "n"
    deadline = time.time() + PROMPT_SECONDS
    while time.time() < deadline:
        if msvcrt.kbhit():
            key = msvcrt.getwch().lower()
            print(key)
            return key != "n"
        time.sleep(0.1)
    print("y")
    return True


def git(*args):
    return subprocess.run(["git", "-C", REPO_ROOT, *args], capture_output=True, text=True, timeout=60)


def update_with_git():
    if git("fetch", "-q", "origin", BRANCH).returncode != 0:
        print("Could not reach GitHub, skipping update check.")
        return 0
    behind = git("rev-list", "--count", f"HEAD..origin/{BRANCH}").stdout.strip()
    if not behind or behind == "0":
        print("dxftogcode is up to date.")
        return 0
    if not ask(f"An update is available ({behind} new change(s)). Install it?"):
        return 0
    result = git("pull", "--ff-only", "origin", BRANCH)
    if result.returncode != 0:
        print("Update failed (local changes in the folder?):")
        print(result.stderr.strip())
        return 0
    print("Updated.")
    return UPDATED


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "dxftogcode-updater"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def update_from_zip():
    try:
        info = json.loads(fetch(f"https://api.github.com/repos/{REPO}/commits/{BRANCH}"))
        latest = info["sha"]
    except Exception:
        print("Could not reach GitHub, skipping update check.")
        return 0

    try:
        with open(VERSION_FILE) as f:
            current = f.read().strip()
    except OSError:
        # First run of a fresh download: assume it is the latest and start tracking.
        current = None
    if current is None:
        with open(VERSION_FILE, "w") as f:
            f.write(latest)
        return 0
    if current == latest:
        print("dxftogcode is up to date.")
        return 0
    if not ask("An update is available. Install it?"):
        return 0

    try:
        data = fetch(f"https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip")
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            # Archive entries look like "<repo>-main/dxftogcode/backend/converter.py".
            for name in zf.namelist():
                parts = name.split("/")
                if len(parts) < 3 or parts[1] != "dxftogcode" or not parts[-1]:
                    continue
                rel = parts[2:]
                if rel[0] in SKIP:
                    continue
                dest = os.path.join(APP_DIR, *rel)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with zf.open(name) as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)
    except Exception as e:
        print(f"Update failed: {e}")
        return 0

    with open(VERSION_FILE, "w") as f:
        f.write(latest)
    print("Updated.")
    return UPDATED


def main():
    print("Checking for updates...")
    use_git = os.path.isdir(os.path.join(REPO_ROOT, ".git")) and shutil.which("git")
    return update_with_git() if use_git else update_from_zip()


if __name__ == "__main__":
    sys.exit(main())
