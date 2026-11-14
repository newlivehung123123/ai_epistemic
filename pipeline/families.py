"""Event families, secondary events and template tags (PLAN 3.3 rules 2, 7 and 9).

The constants and the functions labels, fine_family, derived and coarse_family are copied from
design/notes/scripts/pm_fine_families.py, pm_families.py and pm_retro_yield.py, which the feasibility
counts of PLAN 3.4 used. On 11 November 2026 the dates in three family labels of RULES were corrected to the
election days that the electoral authorities give (British Columbia municipal elections on 17 Oct, not 18 Oct,
the Charlottetown municipal election on 2 Nov, not 3 Nov, and the close of poll of the Tasmania municipal
elections on 27 Oct, not 28 Oct). The patterns, their order and the grouping are unchanged.
office() is new: it splits US races by office for the stratified US quota.
"""
from __future__ import annotations

import re

# pm_retro_yield.py
TEMPLATE_TAGS = {"Tweet Markets", "Finance Updown", "Pyth Finance", "Hide From New", "Recurring",
                 "Up or Down", "Daily", "Weekly", "Mention Markets", "Mentions", "Daily Close",
                 "Daily-Close", "Hit Price", "Equity Daily Pyth", "Monthly"}

# pm_fine_families.py
US = "United States general election, 3 Nov"
US_TAGS = {"Midterms", "Nov 4 Elections", "US Election", "Down Ballot", "Mayoral Races", "Ballot Measures",
           "California Midterm", "referendums midterms"}
DERIVED_TAGS = {"Derivatives", "Midterm Combos", "Margin of Victory", "Midterm MOV"}
DERIVED = re.compile(r"margin of victory|vote share|# of seats|lose seats|turnout|most votes ever|hung parliament|"
                     r"coalition wins a majority|\b(2nd|3rd) place|1st place (in|abroad)|combo|odds leader|flips|"
                     r"lose a seat|win by", re.I)
RULES = [  # (family, title regex or None, required tag or None); first match wins
    ("British Columbia municipal elections, 17 Oct",r", BC Mayoral|^(Kelowna|Nanaimo|Richmond|Surrey|Vancouver) Mayoral", None),
    ("British Columbia general election, 24 Oct", r"British Columbia General|Premier of British Columbia", None),
    ("Ontario municipal elections, 26 Oct", r", ON Mayoral|^(Hamilton|Mississauga|Ottawa|Toronto) Mayoral", None),
    ("Manitoba municipal elections, 28 Oct", r", MB Mayoral|^Winnipeg Mayoral", None),
    ("Charlottetown municipal election, 2 Nov",r"PEI Mayoral", None),
    ("Alberta independence referendum, 19 Oct", r"Alberta vote for independence", None),
    ("Yokohama mayoral election, 18 Oct", r"Yokohama", None),
    ("Fukushima governor election, 25 Oct", r"Fukushima", None),
    ("Slovakia regional and municipal elections, 24 Oct", None, "slovakia"),
    ("Bulgaria presidential election, 25 Oct", r"Bulgaria", None),
    ("Serbia parliamentary election, 25 Oct", r"Serbia", None),
    ("Brazil general election second round, 25 Oct", None, "Brazil"),
    ("Israel legislative election, 27 Oct", None, "Israel Election"),
    ("Israel legislative election, 27 Oct", r"Prime Minister of Israel", None),
    ("Tasmania municipal elections, 27 Oct",r"Mayor", "Australia"),
    ("South Africa municipal elections, 4 Nov", None, "South Africa Municipal Elections"),
    ("New Zealand general election, 7 Nov", None, "New Zealand Election"),
    ("AI lab training pause and vetting", r"training pause|resumes training|third party vetting", None),
    ("Google Gemini releases", r"Gemini", None),
    ("Meta model releases", r"Watermelon|Muse Spark", None),
    ("Atlantic hurricane season", r"Isaias|first hurricane form in the Atlantic", None),
    ("Central European river drought", r"Rhine|Danube", None),
    ("Russia-Ukraine front line", r"^Will Russia capture", None),
    ("Israel-Iran incidents", r"stabbing|FlyDubai|Israeli airspace", None),
    ("Kanye West in Russia", r"Kanye West", None),
    ("US fuel prices and policy", r"gas be below|diesel|gas tax", None),
]

# pm_families.py
MIDTERM_TAGS = {"Midterms", "Nov 4 Elections"}
ELECTION = re.compile(r"election|elections|electoral|vote|voting|referendum|ballot|primary|runoff|mayor|senate|governor|"
                      r"house race|parliament|prime minister|president of|presidential|candidate|seats|win the", re.I)
AI = re.compile(r"\bAI\b|OpenAI|Anthropic|Claude|Gemini|Google|DeepMind|Meta\b|Meta's|xAI|Grok|DeepSeek|Qwen|Mistral|"
                r"\bSSI\b|Muse|GPT|LLM|model|training pause|third party vetting|SpaceXAI|Situational Awareness", re.I)


def labels(e):
    return {t.get("label") or "" for t in (e.get("tags") or [])}


def series(e):
    """pm_retro_yield.py: a Polymarket series event (rule 2)."""
    return bool(e.get("seriesSlug") or e.get("series"))


def template(e):
    """pm_retro_yield.py: an event with a template tag (rule 2)."""
    return bool(labels(e) & TEMPLATE_TAGS)


def coarse_family(e):
    """pm_families.family: us_midterms, other_elections, ai_companies or other."""
    lab = labels(e)
    title = e.get("title") or ""
    if lab & MIDTERM_TAGS:
        return "us_midterms"
    if ELECTION.search(title) or any(ELECTION.search(x) for x in lab):
        return "other_elections"
    if AI.search(title):
        return "ai_companies"
    return "other"


def fine_family(e, coarse):
    lab, title = labels(e), e.get("title") or ""
    if coarse == "us_midterms" or lab & US_TAGS:
        return US
    for fam, rx, tag in RULES:
        if (rx is None or re.search(rx, title, re.I)) and (tag is None or tag in lab):
            return fam
    return "event: " + title


def derived(e):
    return bool(labels(e) & DERIVED_TAGS) or bool(DERIVED.search(e.get("title") or ""))


OFFICE_TAGS = (("Senate Elections", "Senate"), ("Governor Elections", "Governor"), ("House Elections", "House"))


def office(e):
    """Office of a US race, for the stratified US quota: Senate, House, Governor or other."""
    lab = labels(e)
    for tag, name in OFFICE_TAGS:
        if tag in lab:
            return name
    title = e.get("title") or ""
    if re.search(r"\bsenate\b", title, re.I):
        return "Senate"
    if re.search(r"\bgovernor|\bgubernatorial", title, re.I):
        return "Governor"
    if re.search(r"\bhouse\b|\bdistrict\b", title, re.I) or re.search(r"\b[A-Z]{2}-\d{1,2}\b", title):
        return "House"
    return "other"
