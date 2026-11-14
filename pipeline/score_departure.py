"""Score the sprint run with the retro outcomes opened on 13 November 2026 (departure of 13 November 2026).

PLAN Section 12.1 and OUTCOME_OPEN in analysis.py open the retro outcomes on 14 November 2026. After round 2 was
collected, Jason Hung asked on 13 November 2026 for the scoring to be done that day. analysis.py is frozen and is not
edited, so its hash in the README still holds. This script

1. checks the README hashes of the two retro outcome files and of analysis.py before any outcome file is opened,
2. moves the retro opening date in memory from 14 to 13 November 2026 and leaves the prospective date unchanged,
3. runs the score stage as `python3 -I pipeline/analysis.py score --run sprint` would, and
4. writes the real opening time and the checked hashes to data/runs/sprint/departure_retro_opening.json.

Nothing here prints an outcome.

  python3 -I pipeline/score_departure.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import analysis  # noqa: E402
from pipeline import run as runner  # noqa: E402
from pipeline.util import write_json  # noqa: E402

FROZEN_OPEN = "2026-11-14T00:00:00+00:00"
DEPARTURE_OPEN = "2026-11-13T00:00:00+00:00"
CHECKED = ("data/outcomes/retro_withheld_fields.json.gz", "data/outcomes/retro_deleted_paragraphs.json",
           "pipeline/analysis.py")


def readme_hashes() -> dict:
    sec = (ROOT / "README.md").read_text(encoding="utf-8").split("## Freeze hashes", 1)[1].split("\n## ", 1)[0]
    return dict(re.findall(r"^\| `([^`]+)` \| [^|]+ \| `([0-9a-f]{64})` \|", sec, flags=re.M))


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    if analysis.OUTCOME_OPEN.get("retro") != FROZEN_OPEN:
        print("analysis.py no longer holds the frozen retro date, nothing opened")
        return 1
    want = readme_hashes()
    got = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in CHECKED}
    bad = [p for p in CHECKED if want.get(p) != got[p]]
    if bad:
        print("hash mismatch, nothing opened:", ", ".join(bad))
        return 1
    rdir = runner.run_dir("sprint", False)
    record = {"departure": "retro outcomes opened on 13 November 2026, a day before PLAN Section 12.1",
              "frozen_open": FROZEN_OPEN, "departure_open": DEPARTURE_OPEN,
              "prospective_open": analysis.OUTCOME_OPEN.get("prospective"),
              "hashes_checked_against_readme": got, "opened_at_utc": utc_now(), "finished_at_utc": None}
    write_json(rdir / "departure_retro_opening.json", record)
    analysis.OUTCOME_OPEN["retro"] = DEPARTURE_OPEN
    rc = analysis.main(["score", "--run", "sprint"])
    record["finished_at_utc"] = utc_now()
    record["exit_code"] = rc
    write_json(rdir / "departure_retro_opening.json", record)
    return rc


if __name__ == "__main__":
    sys.exit(main())
