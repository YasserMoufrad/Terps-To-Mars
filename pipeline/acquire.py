"""Download official HiRISE inputs with a local checksum manifest."""

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen
from pipeline.logging_config import traced, event

BASE = "https://hirise.lpl.arizona.edu/PDS/DTM/ESP/ORB_071000_071099/ESP_071085_2345_ESP_071006_2345/"
SOURCES = {
    "dtm": "DTEEC_071085_2345_071006_2345_A01.IMG",
    "image": "ESP_071006_2345_RED_C_01_ORTHO.JP2",
    # Full-resolution (~0.25 m/pixel, 8-bit, 30081x50631) orthoimage for visual inspection
    # only; the DTM stays the elevation source. ~390 MB, never committed.
    "image_hd": "ESP_071006_2345_RED_A_01_ORTHO.JP2",
    "image_hd_label": "ESP_071006_2345_RED_A_01_ORTHO.LBL",
}


@traced("acquisition")
def download(kind, directory=Path("pipeline/raw")):
    """Fetch official kind (dtm/image) into directory and record bytes/source/SHA-256."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / SOURCES[kind]
    if destination.exists():
        raise FileExistsError(f"Will not overwrite {destination}")
    partial = destination.with_suffix(destination.suffix + ".part")
    digest = hashlib.sha256()
    event("download_started", dataset_id=SOURCES[kind], source=BASE + SOURCES[kind])
    try:
        with urlopen(BASE + SOURCES[kind], timeout=60) as response, partial.open("xb") as output:
            size = 0
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
                size += len(chunk)
            expected = response.headers.get("Content-Length")
            if expected is not None and size != int(expected):
                event("integrity_failure", level=40, expected_bytes=int(expected), actual_bytes=size)
                raise ValueError("Incomplete download")
        partial.rename(destination)
    except Exception:
        event("download_failed", level=40, dataset_id=SOURCES[kind], source=BASE + SOURCES[kind], exc_info=True)
        partial.unlink(missing_ok=True)
        raise
    manifest = {"source": BASE + SOURCES[kind], "bytes": size, "sha256": digest.hexdigest()}
    destination.with_suffix(destination.suffix + ".json").write_text(json.dumps(manifest, indent=2) + "\n")
    event("download_completed", dataset_id=SOURCES[kind], **manifest)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=SOURCES)
    arguments = parser.parse_args()
    print(json.dumps(download(arguments.kind), indent=2))
