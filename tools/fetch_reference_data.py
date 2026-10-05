"""Fetch the Earth reference data and check it (the list is in tools/reference_data.yaml).

    python tools/fetch_reference_data.py              fetch what is missing, then check every file
    python tools/fetch_reference_data.py --check      check only; fetch nothing

The files go to reference_data/ at the top of the repository, which git ignores (or to the folder named by the
environment variable WORLDENGINE_REFERENCE_DATA). About 35 MB. A file whose SHA-256 differs from the list is refused
and removed: the tests would otherwise be judged against data nobody looked at.
"""
import hashlib
import sys
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from worldengine import reference                        # noqa: E402

LIST = Path(__file__).resolve().parent / "reference_data.yaml"


def sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main(check_only=False) -> int:
    listed = yaml.safe_load(LIST.read_text())
    source, folder = listed["source"], reference.folder()
    folder.mkdir(parents=True, exist_ok=True)
    bad = 0
    for name, entry in listed["files"].items():
        target = folder / name
        if not target.exists():
            if check_only:
                print(f"missing   {name}")
                bad += 1
                continue
            url = f"{source['raw']}/{source['commit']}/{entry['path']}"
            print(f"fetching  {name} ({entry['bytes'] / 1e6:.1f} MB) from {url}")
            part = target.with_suffix(target.suffix + ".part")
            with urllib.request.urlopen(url, timeout=300) as response, open(part, "wb") as out:
                for block in iter(lambda: response.read(1 << 20), b""):
                    out.write(block)
            part.replace(target)
        found = sha256(target)
        if found != entry["sha256"] or target.stat().st_size != entry["bytes"]:
            print(f"REFUSED   {name}: SHA-256 {found}, expected {entry['sha256']}; the file is removed")
            target.unlink()
            bad += 1
        else:
            print(f"checked   {name}")
    print(f"reference data in {folder}: " + ("complete" if not bad else f"{bad} file(s) missing or refused"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(check_only="--check" in sys.argv[1:]))
