"""Shared settings: folders, the three item sets, the item-rule constants and every seed.

Every seed lives in this file, so the hash taken at the freeze fixes every random draw of the study.
"""
from __future__ import annotations

import datetime as dt
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESIGN = ROOT / "design"
DATA = ROOT / "data"
RAW = DATA / "raw"
ITEMS = DATA / "items"
RUNS = DATA / "runs"
OUTCOMES = DATA / "outcomes"

USER_AGENT = "research-client/0.1"
GAMMA_EVENTS = "https://gamma-api.polymarket.com/events/pagination"
CLOB_HISTORY = "https://clob.polymarket.com/prices-history"
DATA_TRADES = "https://data-api.polymarket.com/v2/trades"  # Data API v1 retired on 2 November 2026

# PLAN 3.3 item rule
EXCLUDE_TAG_IDS = ("1", "21", "64", "101757")   # rule 1: Sports, Crypto, Esports, Recurring
BAND = (5, 95)          # rule 5, in whole percent, applied to the rounded price (PLAN 4.3 rounding)
WIDE_BAND = (3, 97)     # rule 5, only if rule 8 allows fewer items than the target
FAMILY_CAP = 0.25       # rule 8 (R1)
MAX_PASSES = 3          # rule 8
PRICE_LOOKBACK_S = 86_400   # rule 4: last hourly point in the 24 hours before F
PRICE_FIDELITY = 60         # rule 4: hourly points
RULE_VERSION = "PLAN 3.3 item rule, 7 November 2026"
# PLAN 6.8 mirror pair, DECIDED by Jason Hung on 11 November 2026: the two prices at F sum to at least 90 points
MIRROR_RULE = "PLAN 6.8 mirror pair, 11 November 2026"
MIRROR_MIN_SUM = 90

# PLAN 4.2 cost-loss thresholds; the cost shown is 100 t dollars
T_VALUES = (0.2, 0.35, 0.5, 0.65, 0.8)

# Scheduled end-date windows, UTC dates with both ends included. The W of a set is a tuple of such windows:
# one for each scored set, two for the pilot (PLAN 3.2; 16 to 31 December added on 7 November 2026).
RETRO_W = ("2026-10-15", "2026-11-08")
PROSPECTIVE_W = ("2026-11-19", "2026-12-15")
PILOT_W = (("2026-11-09", "2026-11-18"), ("2026-12-16", "2026-12-31"))

# PLAN 3.2. F is 00:00 UTC on the stated day. closed_values lists the Gamma event states fetched.
# fetch_days lists the UTC dates on which the Gamma fetch may run (PLAN 3.2 freeze; PLAN 10.1 for the
# pilot, whose F is the day of its fetch). If the pilot fetch slips a day, change its F and fetch_days
# together.
SETS = {
    "pilot": {
        "F": "2026-11-07T00:00:00+00:00",   # the day of the pilot fetch (PLAN 10.1)
        "fetch_days": ("2026-11-07",),
        "W": PILOT_W,
        "N": 50,
        "closed_values": ("false",),
        "open_at_fetch": True,               # PLAN 4.6: every pilot market is still open at the fetch
        "seed": 20261107,
        "forbidden_windows": (RETRO_W, PROSPECTIVE_W),   # PLAN 3.2 disjointness
        "exclude_event_sets": (),
        "subsets": (("sub10", 10), ("sub20", 20)),        # nested pilot subsets (PLAN 3.2 table)
    },
    "retro": {
        "F": "2026-10-08T00:00:00+00:00",
        "fetch_days": ("2026-11-10", "2026-11-11"),
        "W": (RETRO_W,),
        "N": 400,
        "closed_values": ("true", "false"),
        "open_at_fetch": False,
        "seed": 20261008,
        "forbidden_windows": (),
        "exclude_event_sets": ("pilot",),
        "subsets": (),
    },
    "prospective": {
        "F": "2026-11-12T00:00:00+00:00",
        "fetch_days": ("2026-11-12",),
        "W": (PROSPECTIVE_W,),
        "N": 400,
        "closed_values": ("true", "false"),
        "open_at_fetch": False,
        "seed": 20261112,
        "forbidden_windows": (),
        "exclude_event_sets": ("pilot", "retro"),
        "subsets": (),
    },
}

# Seed for every draw made when requests are built (chains, arm order, resamples): PLAN 4 and 7.
RUN_SEED = 20261113
RESAMPLES = 10_000


def f_datetime(name: str) -> dt.datetime:
    return dt.datetime.fromisoformat(SETS[name]["F"])


def f_unix(name: str) -> int:
    return int(f_datetime(name).timestamp())


def rng(seed: int, purpose: str) -> random.Random:
    """A generator for one named purpose. A string seed is hashed with SHA-512 by random.Random, so the
    draws do not depend on PYTHONHASHSEED or on the order in which purposes are used."""
    return random.Random(f"{seed}-{purpose}")
