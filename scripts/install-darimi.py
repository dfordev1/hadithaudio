"""Install the pinned Darimi catalog, timings and per-hadith audio for the static site."""
import hashlib
from pathlib import Path
import shutil
import tempfile
from urllib.request import Request, urlopen
from zipfile import ZipFile

PUBLIC = Path(__file__).resolve().parents[1] / "public"
RELEASE = "https://github.com/playorbitt/arabic-word-reader/releases/download/darimi-main-reader-20261120/darimi-main-reader-20261120.zip"
SHA256 = "cef6dd459edc060b027f6ab7dc6acbf6f0a54b64bd0b74cb6be3f2261db992c6"


def install():
    destination = PUBLIC / "darimi"
    marker = destination / ".release"
    if marker.is_file() and marker.read_text().strip() == SHA256:
        return
    with tempfile.TemporaryDirectory(dir=PUBLIC.parent) as work:
        folder = Path(work)
        archive = folder / "catalog.zip"
        digest = hashlib.sha256()
        with urlopen(Request(RELEASE, headers={"User-Agent": "hadith.to-reader-build"}), timeout=180) as source, archive.open("wb") as output:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
                output.write(chunk)
        if digest.hexdigest() != SHA256:
            raise ValueError("Darimi release checksum mismatch")
        staging = folder / "darimi"
        with ZipFile(archive) as bundle:
            bundle.extractall(staging)
        (staging / ".release").write_text(SHA256)
        if destination.exists():
            destination.rename(folder / "previous")
        try:
            staging.rename(destination)
        except OSError:
            if (folder / "previous").exists():
                (folder / "previous").rename(destination)
            raise


if __name__ == "__main__":
    install()
