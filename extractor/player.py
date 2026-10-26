"""One player = one document, from the Home, Bio and Stats pages.

Facts are found by their label in the page text ("Born" -> next line), tables by
their header row ("Season", "Team", ...). Every regex is a named constant here.
"""
import re

from .tables import find_table
from .text import html_to_lines, index_of, main_block, title, value_after

# --- page title: "Juraj Slafkovský Bio, Awards & Draft Info | NHL.com" -------
TITLE_NAME_RE = re.compile(r"(.+?) (?:Home|Stats|Bio\b.*) \| NHL\.com")
# --- header shown on every subpage: "#20 • LW • Age: 22 • 6′3″ • 225 lbs" ----
TABS_RE = re.compile(r"Home")  # the Home | Bio | Stats tabs end the header
NUMBER_RE = re.compile(r"#(\d{1,2})")
POSITION_RE = re.compile(r"C|LW|RW|L|R|D|G|F")
# --- Bio facts: label line, then value line ----------------------------------
HEIGHT_LABEL = re.compile(r"Height")
HEIGHT_RE = re.compile(r"(\d)\s*[′']\s*(\d{1,2})\s*[″\"]?")  # 6′3″ -> 75 in
WEIGHT_LABEL = re.compile(r"Weight")
WEIGHT_RE = re.compile(r"(\d{2,3})(?:\s*lbs)?")
HAND_LABEL = re.compile(r"Shoots|Catches")
HAND_RE = re.compile(r"[LR]")
BORN_LABEL = re.compile(r"Born")
BORN_RE = re.compile(r"(?P<mon>[A-Z][a-z]{2}) (?P<day>\d{1,2}), (?P<year>\d{4})")
BIRTHPLACE_LABEL = re.compile(r"Birthplace(?: • Nationality)?")
# "Kosice, SVK • Slovakia", "Brantford, Ontario, CAN • Canada"
BIRTHPLACE_RE = re.compile(
    r"(?P<city>[^,•]+?)(?:, (?P<region>[^,•]+?))?, (?P<country>[A-Z]{3})(?: • (?P<nationality>.+))?")
DRAFT_LABEL = re.compile(r"Draft")
# "2022 - Round 1, Pick 1 • MTL" or "Undrafted"
DRAFT_RE = re.compile(
    r"(?P<year>\d{4}) - Round (?P<round>\d+), Pick (?P<pick>\d+)(?: • (?P<team>[A-Z]{2,3}))?")
UNDRAFTED_RE = re.compile(r"Undrafted")
# "Drafted from TPS, FINLAND (1st overall)"
DRAFTED_FROM_RE = re.compile(r"Drafted from (?P<club>.+?)(?: \((?P<overall>\d+)(?:st|nd|rd|th) overall\))?")
# --- "About <name>" text, until one of the sections that follow it ----------
ABOUT_RE = re.compile(r"About .+")
ABOUT_END_RE = re.compile(r"Show More|Awards|Notes & Transactions|Height")
READ_MORE_RE = re.compile(r"Read more about .*|No Bio available")
# --- Awards: "<trophy> / <description> / More Info / <seasons...>" -----------
AWARDS_RE = re.compile(r"Awards")
AWARDS_END_RE = re.compile(r"Notes & Transactions|Height")
MORE_INFO_RE = re.compile(r"More Info")
AWARD_YEAR_RE = re.compile(r"\d{4}(?:-\d{2})?")
# --- Stats: the "Career Stats" table (Season, Team, GP, ...) ----------------
SEASON_RE = re.compile(r"\d{4}-\d{2}")
CAREER_ROW_RE = re.compile(r"Career.*")
INT_RE = re.compile(r"[+-]?\d+")
# --- current team from the URL: /canadiens/player/... (former players: none) -
TEAM_URL_RE = re.compile(r"^https://www\.nhl\.com/([a-z]+)/player/")

MONTHS = {m: i for i, m in enumerate(
    "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), start=1)}
# table column -> field name; skater and goalie tables share GP/G/A/PIM
STAT_COLUMNS = {"GP": "gp", "G": "g", "A": "a", "P": "p", "PIM": "pim", "+/-": "plus_minus",
                "W": "w", "L": "l", "T": "t", "OT": "ot", "SO": "so", "GAA": "gaa", "SV%": "sv_pct"}


def number(text):
    """'1,266' -> 1266, '+14' -> 14; '--' or '' -> None."""
    text = (text or "").replace(",", "").strip()
    return int(text) if INT_RE.fullmatch(text) else None


def decimal(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def stat_value(column, text):
    return decimal(text) if column in ("gaa", "sv_pct") else number(text)


def parse_header(lines, name):
    """first, last, number, position from the lines above the Home | Bio | Stats tabs."""
    end = index_of(lines, TABS_RE)
    head = lines[:end] if end > 0 else lines[:15]
    first = last = None
    for a, b in zip(head, head[1:]):
        if f"{a} {b}" == name:
            first, last = a, b
            break
    if first is None and name and " " in name:
        first, last = name.split(" ", 1)
    num = next((NUMBER_RE.fullmatch(x).group(1) for x in head if NUMBER_RE.fullmatch(x)), None)
    pos = next((x for x in head if POSITION_RE.fullmatch(x)), None)
    return first, last, number(num), pos


def parse_facts(lines):
    rec = {}
    m = HEIGHT_RE.fullmatch(value_after(lines, HEIGHT_LABEL) or "")
    rec["height_in"] = int(m.group(1)) * 12 + int(m.group(2)) if m else None
    m = WEIGHT_RE.fullmatch(value_after(lines, WEIGHT_LABEL) or "")
    rec["weight_lb"] = int(m.group(1)) if m else None
    m = HAND_RE.fullmatch(value_after(lines, HAND_LABEL) or "")
    rec["shoots"] = m.group(0) if m else None

    m = BORN_RE.match(value_after(lines, BORN_LABEL) or "")
    rec["birth_date"] = (f"{m['year']}-{MONTHS[m['mon']]:02d}-{int(m['day']):02d}"
                         if m and m["mon"] in MONTHS else None)
    m = BIRTHPLACE_RE.fullmatch(value_after(lines, BIRTHPLACE_LABEL) or "")
    for field in ("city", "region", "country"):
        rec[f"birth_{field}"] = m[field] if m else None
    rec["nationality"] = m["nationality"].strip() if m and m["nationality"] else None

    rec.update(draft_year=None, draft_round=None, draft_pick=None, draft_overall=None,
               draft_team=None, draft_from=None, undrafted=None)
    i = index_of(lines, DRAFT_LABEL)
    if 0 <= i < len(lines) - 1:
        value = lines[i + 1]
        m = DRAFT_RE.fullmatch(value)
        if m:
            rec.update(draft_year=int(m["year"]), draft_round=int(m["round"]),
                       draft_pick=int(m["pick"]), draft_team=m["team"], undrafted=False)
            if i + 2 < len(lines):
                f = DRAFTED_FROM_RE.fullmatch(lines[i + 2])
                if f:
                    rec["draft_from"] = f["club"]
                    rec["draft_overall"] = number(f["overall"])
        elif UNDRAFTED_RE.fullmatch(value):
            rec["undrafted"] = True
    return rec


def parse_about(lines):
    start = index_of(lines, ABOUT_RE)
    if start < 0:
        return None
    end = index_of(lines, ABOUT_END_RE, start + 1)
    body = lines[start + 1:end if end > 0 else len(lines)]
    return " ".join(x for x in body if not READ_MORE_RE.fullmatch(x)) or None


def parse_awards(lines):
    """[(trophy, [seasons])]: a trophy is the line two above "More Info"."""
    start = index_of(lines, AWARDS_RE)
    if start < 0:
        return []
    end = index_of(lines, AWARDS_END_RE, start + 1)
    block = lines[start + 1:end if end > 0 else len(lines)]
    marks = [i for i, x in enumerate(block) if MORE_INFO_RE.fullmatch(x) and i >= 2]
    awards = []
    for n, i in enumerate(marks):
        stop = marks[n + 1] - 2 if n + 1 < len(marks) else len(block)
        years = [x for x in block[i + 1:stop] if AWARD_YEAR_RE.fullmatch(x)]
        awards.append((block[i - 2], sorted(set(years))))
    return awards


def parse_stats(page):
    """(seasons, career): rows of the Career Stats table as dicts."""
    header, rows = find_table(page, ("Season", "Team"))
    if not header:
        return [], {}
    seasons, career = [], {}
    for cells in rows:
        # totals rows can have fewer cells; numbers are right-aligned to the header
        values = dict(zip(header[len(header) - len(cells):], cells))
        stats = {STAT_COLUMNS[c]: stat_value(STAT_COLUMNS[c], v)
                 for c, v in values.items() if c in STAT_COLUMNS}
        if SEASON_RE.fullmatch(cells[0]):
            seasons.append({"season": cells[0], "team": cells[1] if len(cells) > 1 else None,
                            **stats})
        elif CAREER_ROW_RE.fullmatch(cells[0]) and not career:
            career = stats
    return seasons, career


def extract_player(player_id, url, home=None, bio=None, stats=None):
    """Dict with the player's fields; missing pages or facts give None."""
    pages = [p for p in (stats, bio, home) if p]
    name = None
    for page in pages:
        m = TITLE_NAME_RE.fullmatch(title(page))
        if m:
            name = m.group(1)
            break
    head_lines = html_to_lines(main_block(pages[0])) if pages else []
    first, last, num, pos = parse_header(head_lines, name)

    bio_lines = html_to_lines(main_block(bio)) if bio else []
    seasons, career = parse_stats(stats) if stats else ([], {})
    teams = list(dict.fromkeys(s["team"] for s in seasons if s.get("team")))
    m = TEAM_URL_RE.match(url or "")

    rec = {"player_id": player_id, "name": name, "first": first, "last": last,
           "number": num, "position": pos, "active": bool(m), "team": m.group(1) if m else None}
    rec.update(parse_facts(bio_lines))
    rec["teams"] = teams
    rec["awards"] = parse_awards(bio_lines)
    rec["career"] = career
    rec["seasons"] = seasons
    rec["about"] = parse_about(bio_lines)
    rec["url"] = url
    return rec
