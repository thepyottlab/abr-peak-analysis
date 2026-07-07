import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from version import APP_VERSION


LATEST_RELEASE_URL = "https://api.github.com/repos/TomNaber/abr-peak-analysis/releases/latest"
MARKER_FILE = "install_mode.txt"
USER_AGENT = "ABR-Peak-Analysis-Updater"


def version_tuple(value):
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)$", value.strip())
    if not match:
        raise ValueError("Expected version like v2.0.0")
    return tuple(int(part) for part in match.groups())


def is_newer_version(latest, current=APP_VERSION):
    return version_tuple(latest) > version_tuple(current)


def marker_paths(executable=None, meipass=None):
    executable = Path(executable or sys.executable).resolve()
    paths = [executable.parent / MARKER_FILE]

    for parent in executable.parents:
        if parent.suffix == ".app":
            paths.append(parent / "Contents" / "Resources" / MARKER_FILE)
            paths.append(parent / "Contents" / "MacOS" / MARKER_FILE)
            break

    meipass = meipass or getattr(sys, "_MEIPASS", None)
    if meipass:
        paths.append(Path(meipass) / MARKER_FILE)
    return paths


def updates_enabled(paths=None):
    for path in paths or marker_paths():
        try:
            return path.read_text(encoding="utf-8").strip().lower() == "installer"
        except OSError:
            pass
    return False


def fetch_latest_release(url=LATEST_RELEASE_URL):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def platform_asset_spec(system=None, machine=None):
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()
    if system == "Windows" and machine in ("amd64", "x86_64"):
        return "ABR-Peak-Analysis-Setup-", "-win-x64.exe"
    if system == "Darwin" and machine in ("arm64", "aarch64"):
        return "ABR-Peak-Analysis-", "-macos-arm64.pkg"
    return None


def select_asset(release, system=None, machine=None):
    spec = platform_asset_spec(system, machine)
    if not spec:
        return None

    tag = release.get("tag_name", "")
    version = tag.lstrip("v")
    prefix, suffix = spec
    for asset in release.get("assets", []):
        name = asset.get("name", "")
        url = asset.get("browser_download_url")
        if (
            url
            and name.startswith(prefix)
            and name.endswith(suffix)
            and (tag in name or version in name)
        ):
            return {"tag": tag, "version": version, "name": name, "url": url}
    return None


def available_update(current_version=APP_VERSION):
    if not updates_enabled():
        return None

    release = fetch_latest_release()
    tag = release.get("tag_name", "")
    if not is_newer_version(tag, current_version):
        return None
    return select_asset(release)


def download_asset(asset, dest_dir=None):
    dest_dir = Path(dest_dir or tempfile.gettempdir()) / "ABR Peak Analysis Updates"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / asset["name"]

    request = urllib.request.Request(asset["url"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:
        with open(dest, "wb") as outfile:
            shutil.copyfileobj(response, outfile)
    return dest


def launch_installer(path, system=None):
    path = str(Path(path))
    system = system or platform.system()
    if system == "Windows":
        os.startfile(path)
    elif system == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen([path])
