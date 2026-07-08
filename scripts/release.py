"""Publish a GitHub release from local installer artifacts.

To publish a release:

1. Update `Source/version.py` and add the matching `### vX.Y.Z` section to `CHANGELOG.md`.
2. Commit the version/changelog/build-script changes.
3. Build the macOS `.pkg` on macOS and the Windows installer/portable `.exe` files on Windows.
4. Put all three generated files in `dist/installers/`.
5. Run `python scripts/release.py` from the repo root with the GitHub CLI installed and authenticated.
   Use `python scripts/release.py --draft` if you want to review in GitHub before publishing.
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from Source.version import APP_VERSION


INSTALLERS = ROOT / "dist" / "installers"
TAG = "v%s" % APP_VERSION
REPO = "TomNaber/abr-peak-analysis"


def changelog_notes():
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    start = re.search(r"^###\s+[vV]?%s\b.*$" % re.escape(APP_VERSION), text, re.M)
    if not start:
        raise SystemExit("CHANGELOG.md has no section for %s" % TAG)

    end = re.search(r"^###\s+", text[start.end():], re.M)
    body = text[start.end(): start.end() + end.start() if end else len(text)]
    return body.strip()


def expected_assets():
    names = [
        "ABR-Peak-Analysis-Setup-%s-win-x64.exe" % APP_VERSION,
        "ABR-Peak-Analysis-%s-win-x64-portable.exe" % APP_VERSION,
        "ABR-Peak-Analysis-%s-macos-arm64.pkg" % APP_VERSION,
    ]
    assets = [INSTALLERS / name for name in names]
    missing = [str(path) for path in assets if not path.is_file()]
    if missing:
        raise SystemExit("Missing release artifacts:\n" + "\n".join(missing))
    return assets


def run(*args):
    subprocess.run(args, cwd=ROOT, check=True)


def gh_command():
    gh = shutil.which("gh")
    if gh:
        return gh

    for path in ("/opt/homebrew/bin/gh", "/usr/local/bin/gh"):
        if Path(path).is_file():
            return path

    raise SystemExit(
        "GitHub CLI `gh` was not found. Install it, run `gh auth login`, "
        "then rerun `python scripts/release.py`."
    )


def clean_worktree():
    subprocess.run(["git", "diff", "--quiet"], cwd=ROOT, check=True)
    subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT, check=True)


def tag_exists():
    return subprocess.run(
        ["git", "rev-parse", "--verify", "refs/tags/%s" % TAG],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft", action="store_true")
    args = parser.parse_args()

    assets = expected_assets()
    notes = changelog_notes()
    gh = gh_command()
    clean_worktree()

    if not tag_exists():
        run("git", "tag", "-a", TAG, "-m", TAG)
    run("git", "push", "origin", TAG)

    with tempfile.TemporaryDirectory() as tmp:
        notes_file = Path(tmp) / "release-notes.md"
        notes_file.write_text(notes, encoding="utf-8")

        command = [gh, "release", "create", TAG, "--repo", REPO, "--title", TAG,
                   "--notes-file", str(notes_file)]
        if args.draft:
            command.append("--draft")
        command.extend(str(asset) for asset in assets)
        run(*command)


if __name__ == "__main__":
    main()
