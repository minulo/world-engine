"""Fetch the Earth reference data and check it (the list is in tools/reference_data.yaml).

    python tools/fetch_reference_data.py              fetch what is missing or wrong, then check every file
    python tools/fetch_reference_data.py --check      check only; fetch nothing, remove nothing

The files go to reference_data/ at the top of the repository, which git ignores (or to the folder named by the
environment variable WORLDENGINE_REFERENCE_DATA). About 35 MB. A file whose size or SHA-256 differs from the list
is refused: it is removed and fetched once more, and if it is still wrong it is removed again. The tests would
otherwise be judged against data nobody looked at.
"""
import http.client
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import earth_reference as reference                      # noqa: E402
from worldengine import console                          # noqa: E402


def right(path, entry) -> bool:
    return path.exists() and path.stat().st_size == entry["bytes"] and reference.sha256(path) == entry["sha256"]


def fetch(url, target) -> str:
    """Fetch one file; returns nothing on success, or a sentence saying what went wrong."""
    part = target.with_suffix(target.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=300) as response, open(part, "wb") as out:
            for block in iter(lambda: response.read(1 << 20), b""):
                out.write(block)
    except (urllib.error.URLError, http.client.HTTPException, OSError) as problem:
        part.unlink(missing_ok=True)
        return f"could not be fetched from {url}: {problem}"
    part.replace(target)
    return ""


def fetch_all(check_only=False, listed=None, folder=None, say=print) -> int:
    """Fetch and check (or, with check_only, check: nothing is fetched, removed or created, not even the folder).
    Returns 0 if every file is there and right, 1 otherwise."""
    listed = listed or reference.listed()
    source, folder = listed["source"], Path(folder) if folder else reference.folder()
    if not check_only:
        folder.mkdir(parents=True, exist_ok=True)
    bad = 0
    for name, entry in listed["files"].items():
        target = folder / name
        if right(target, entry):
            say(f"checked   {name}")
            continue
        if check_only:
            say(f"missing   {name}" if not target.exists() else f"REFUSED   {name}: it is not the file the list names")
            bad += 1
            continue
        if target.exists():
            say(f"REFUSED   {name}: it is not the file the list names; it is removed and fetched again")
            target.unlink()
        url = f"{source['raw']}/{source['commit']}/{entry['path']}"
        say(f"fetching  {name} ({entry['bytes'] / 1e6:.1f} MB) from {url}")
        problem = fetch(url, target)
        if problem:
            say(f"FAILED    {name} {problem}")
            bad += 1
        elif not right(target, entry):
            say(f"REFUSED   {name}: SHA-256 {reference.sha256(target)}, {target.stat().st_size} bytes; expected "
                f"{entry['sha256']}, {entry['bytes']} bytes. The file is removed")
            target.unlink()
            bad += 1
        else:
            say(f"checked   {name}")
    say(f"reference data in {folder}: " + ("complete" if not bad else f"{bad} file(s) missing or refused"))
    return 1 if bad else 0


def parser():
    p = console.tool_parser(__doc__, "python tools/fetch_reference_data.py")
    p.add_argument("--check", action="store_true")
    return p


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    console.print_anywhere()
    return fetch_all(check_only=args.check)


if __name__ == "__main__":
    sys.exit(main())
