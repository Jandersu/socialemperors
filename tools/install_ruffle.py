#!/usr/bin/env python3
"""Install the pinned, checksum-verified browser runtime from Ruffle's release.

Only the server operator runs this script. Players receive these files directly
from this application's origin and do not install Flash or an extension.
"""

import argparse
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile


VERSION = "0.7.1"
ARCHIVE = f"ruffle-{VERSION}-web-selfhosted.zip"
URL = f"https://github.com/ruffle-rs/ruffle/releases/download/v{VERSION}/{ARCHIVE}"
SHA256 = "ef12edbee135d581a9cd523837d746da30a07a64dbf1cf472d2e472c656f4b5e"
DESTINATION = Path(__file__).resolve().parent.parent / "templates" / "vendor" / "ruffle"


def install(archive_path=None):
    if archive_path:
        data = Path(archive_path).read_bytes()
    else:
        request = urllib.request.Request(URL, headers={"User-Agent": "Social-Emperors-Runtime-Installer"})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError("Ruffle archive checksum mismatch; installation was cancelled.")

    files = {}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for entry in archive.infolist():
            # Ship the runtime and its notices; source maps are development-only.
            name = entry.filename
            if Path(name).name != name:
                raise ValueError("Unexpected nested path in the Ruffle archive.")
            if name.endswith((".js", ".wasm")) or name.startswith("LICENSE_") or name in {"README.md", "package.json"}:
                files[name] = archive.read(entry)

    if "ruffle.js" not in files or not any(name.endswith(".wasm") for name in files):
        raise ValueError("The Ruffle archive is missing its browser runtime.")
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for name, contents in files.items():
        (DESTINATION / name).write_bytes(contents)
    manifest = {
        "version": VERSION,
        "source": URL,
        "archive_sha256": SHA256,
        "files": {name: hashlib.sha256(contents).hexdigest() for name, contents in sorted(files.items())},
    }
    (DESTINATION / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Installed Ruffle {VERSION} ({len(files)} files) in {DESTINATION}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="Use a previously downloaded release zip (checksum is still verified).")
    args = parser.parse_args()
    try:
        install(args.archive)
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Unable to install Ruffle: {exc}\n")
