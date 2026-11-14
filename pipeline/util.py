"""Small helpers shared by the pipeline: time parsing, JSON lists, dates in words, file writes, hashes."""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import os
import sys
from pathlib import Path

UTC = dt.timezone.utc
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December")


def ts(s):
    """Parse a Polymarket time string (rules of notes/scripts/pm_retro_yield.py).

    A time without a zone is read as UTC, and a string that cannot be parsed gives None, which the
    market rule counts as a missing time field.
    """
    if not s:
        return None
    s = str(s).replace(" ", "T").replace("+00:00:00", "+00:00")
    if s.endswith("+00"):
        s += ":00"
    s = s.replace("Z", "+00:00")
    try:
        d = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def jl(s):
    """A list stored either as a list or as a JSON string (Polymarket uses both)."""
    if isinstance(s, list):
        return s
    try:
        return json.loads(s)
    except Exception:
        return None


def utc_day(d: dt.datetime) -> str:
    return d.astimezone(UTC).date().isoformat()


def date_words(d) -> str:
    """'3 November 2026' for a date, a UTC datetime or an ISO string."""
    if isinstance(d, str):
        d = ts(d)
    if isinstance(d, dt.datetime):
        d = d.astimezone(UTC).date()
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def now_utc() -> str:
    return dt.datetime.now(UTC).isoformat(timespec="seconds")


def write_json(path, obj, gz: bool = False, indent: int | None = 1) -> None:
    """Write JSON atomically (temporary file, then rename)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(obj, ensure_ascii=False, indent=None if gz else indent).encode("utf-8")
    if gz:
        data = gzip.compress(data, mtime=0)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def read_json(path):
    path = Path(path)
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    return json.loads(raw)


def jsonl_text(recs) -> str:
    """One JSON object per line: the form of every .jsonl file of the pipeline (file hashes are taken of it)."""
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs)


def append_jsonl(path, rec) -> None:
    append_jsonl_many(path, [rec])


def append_jsonl_many(path, recs) -> None:
    """Append records with one fsync. If the file ends in a partial line (a write cut short), a newline goes
    first, so the partial line stays on a line of its own and read_jsonl skips it."""
    recs = list(recs)
    if not recs:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = jsonl_text(recs).encode("utf-8")
    with open(path, "ab+") as fh:
        fh.seek(0, os.SEEK_END)
        if fh.tell() > 0:
            fh.seek(-1, os.SEEK_END)
            if fh.read(1) != b"\n":
                data = b"\n" + data
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())


def write_jsonl(path, recs) -> None:
    """Write a whole .jsonl file atomically; gzip with a fixed mtime when the name ends in .gz."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = jsonl_text(recs).encode("utf-8")
    if path.suffix == ".gz":
        data = gzip.compress(data, mtime=0)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def read_jsonl(path, tolerant: bool = True) -> list:
    """Records of a .jsonl or .jsonl.gz file, [] if it does not exist. A line that does not decode (a write cut
    short) is skipped with a warning, or raises when tolerant is False."""
    path = Path(path)
    if not path.exists():
        return []
    opener = gzip.open if path.suffix == ".gz" else open
    out = []
    with opener(path, "rt", encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                if not tolerant:
                    raise
                print(f"warning: {path.name} line {n} does not decode and is skipped", file=sys.stderr)
    return out


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
