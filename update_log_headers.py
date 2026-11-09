"""Update legacy water and ambient CSV headers in a folder (default: current folder)."""

import argparse
import codecs
import csv
import io
import os
from pathlib import Path
import re
import shutil
import tempfile


AMBIENT = {
    "Near Ambi Temp. (°C)": "near_ambi_temp_c",
    "Far Ambi Temp. (°C)": "far_ambi_temp_c",
    "Near Ambi RH (% R.H.)": "near_ambi_hum",
    "Far Ambi RH (% R.H.)": "far_ambi_hum",
    "combo_state": "combo_state",
}


def new_header(name):
    match = re.fullmatch(r"(Cold|Hot) (Temp\.|Pres\.|Usage) \((.*)\)", name)
    if not match:
        return AMBIENT.get(name, name)
    side, measurement, unit = match.groups()
    if measurement == "Temp.":
        suffix = {"°C": "c", "°F": "f", "K": "k"}.get(unit, "c")
        return f"{side.lower()}_temp_{suffix}"
    suffix = "pres_kpa" if measurement == "Pres." else "usage_l"
    return f"{side.lower()}_{suffix}"


def update_file(path):
    temporary = None
    try:
        with path.open("rb") as source:
            first = source.readline()
            if not first:
                return False
            headers = next(csv.reader([first.decode("utf-8-sig")], strict=True))
            updated = [new_header(name) for name in headers]
            if headers == updated:
                return False
            if len(set(updated)) != len(updated):
                raise ValueError("renaming would leave duplicate column names")
            line = io.StringIO(newline="")
            csv.writer(line).writerow(updated)
            ending = first[len(first.rstrip(b"\r\n")):]
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as target:
                temporary = Path(target.name)
                if first.startswith(codecs.BOM_UTF8):
                    target.write(codecs.BOM_UTF8)
                target.write(line.getvalue()[:-2].encode("utf-8") + ending)
                shutil.copyfileobj(source, target)
        shutil.copymode(path, temporary)
        os.replace(temporary, path)
        return True
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", nargs="?", type=Path, default=Path.cwd())
    folder = parser.parse_args().folder
    if not folder.is_dir():
        parser.error(f"Directory not found: {folder}")
    errors = 0
    changed = 0
    for path in sorted(folder.iterdir()):
        name = path.name.lower()
        if not (name.endswith(".csv") and ("water" in name or "ambient" in name)
                and path.is_file()):
            continue
        try:
            if update_file(path):
                print(f"Updated {path.name}")
                changed += 1
        except (OSError, ValueError, csv.Error) as exc:
            print(f"Skipped {path.name}: {exc}")
            errors += 1
    print(f"Updated {changed} file(s).")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
