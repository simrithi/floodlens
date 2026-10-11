"""Fetch a city's FABDEM bare-earth tile (Delhi N28E077, Bengaluru N12E077) without downloading the 3 GB archive.

FABDEM (University of Bristol) is Copernicus GLO-30 with buildings and trees removed. It is only
published as 10x10 degree zips, so this reads the zip's directory and the one member we need with
HTTP range requests.

usage: python scripts/fetch_fabdem.py [--city delhi|bengaluru]
"""

import argparse
import io
import sys
import zipfile
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.cities import CITIES  # noqa: E402


class HttpRangeFile(io.RawIOBase):
    """Seekable read-only file over HTTP range requests (enough for zipfile)."""

    def __init__(self, url: str):
        self.url = url
        self.session = requests.Session()
        head = self.session.head(url, allow_redirects=True, timeout=60)
        head.raise_for_status()
        self.size = int(head.headers["Content-Length"])
        self.pos = 0
        self.fetched = 0

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        self.pos = {0: offset, 1: self.pos + offset, 2: self.size + offset}[whence]
        return self.pos

    def read(self, n: int = -1) -> bytes:
        if n < 0:
            n = self.size - self.pos
        if n == 0 or self.pos >= self.size:
            return b""
        end = min(self.size, self.pos + n) - 1
        r = self.session.get(self.url, headers={"Range": f"bytes={self.pos}-{end}"}, timeout=300)
        r.raise_for_status()
        data = r.content
        self.pos += len(data)
        self.fetched += len(data)
        return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", default="delhi", choices=sorted(CITIES))
    c = CITIES[parser.parse_args().city]
    FABDEM_PATH = c.fabdem_path
    if FABDEM_PATH.exists():
        print(f"already have {FABDEM_PATH}")
        return
    remote = HttpRangeFile(c.fabdem_zip_url)
    with zipfile.ZipFile(remote) as z:
        member = next(n for n in z.namelist() if n.endswith(f"{c.fabdem_tile}.tif"))
        info = z.getinfo(member)
        print(f"{member}: {info.compress_size / 1e6:.1f} MB compressed, {info.file_size / 1e6:.1f} MB")
        FABDEM_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = FABDEM_PATH.with_suffix(".part")
        with z.open(member) as src, open(tmp, "wb") as dst:
            while chunk := src.read(1 << 22):
                dst.write(chunk)
        tmp.replace(FABDEM_PATH)
    print(f"saved {FABDEM_PATH} ({FABDEM_PATH.stat().st_size / 1e6:.1f} MB), transferred {remote.fetched / 1e6:.1f} MB of {remote.size / 1e9:.2f} GB")


if __name__ == "__main__":
    main()
