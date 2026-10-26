"""Coaches and hockey staff, one record per person.

The 25 team sites use different layouts: a staff list (name, role), a list in
the other order (role, name; Lightning), both on one line ("Head Coach - Joel
Quenneville", "Spencer Carbery - Head Coach") or one person's page (name, role,
bio). So people are found in the page text, not the markup: a line that looks
like a person's name next to a line with a role word. The longer paragraphs
after a pair are that person's bio.
"""
import re

from .text import fold_diacritics, html_to_lines, main_block

# "Martin St-Louis", "Dr. David Scott", "Pierre-Edouard Bellemare", "J.P. Cote"
NAME_WORD = r"(?:[A-ZÀ-ſ][\w'’.\-]*|de|van|von|der|di|da|le|la)"
NAME_RE = re.compile(rf"(?:Dr\. )?{NAME_WORD}(?: {NAME_WORD}){{1,4}}")
# section headings and team names that also look like names ("Training Staff")
NOT_NAME_RE = re.compile(
    r".*\b(?:staff|ops|hockey|department|team|member|season|ticket|captains?|coaches"
    r"|operations|development|scouting|training|equipment|medical|management"
    r"|administration|executive|personnel|owners(?:hip)?|group|foundation|sports"
    r"|entertainment|checkers|moose|wolves|bears|penguins|roster)\b.*", re.I)
ROLE_RE = re.compile(
    r".*\b(?:coach\w*|manager|general manager|director|president|scout\w*|trainer|therapist"
    r"|physiotherapist|analyst|advis[oe]r|consultant|coordinator|owner|chairman|governor"
    r"|assistant|officer|captain|physician|specialist|head of|chief|executive|analytics"
    r"|operations|development|equipment|video|strength|conditioning|performance|developer"
    r"|engineer)\b.*", re.I)
# a sentence or a section heading, not a role: "... is entering his third season.",
# "Coaching Staff"
SENTENCE_RE = re.compile(
    r".*(?:\b[a-z]{3,}\.(?:\s|$)|\b(?:is|was|has|had|joined|served|spent)\b)"
    r".*|.*\b[Ss]taff")
# "Named Head Coach on May 23, 2024" (Devils) -> "Head Coach"
NAMED_RE = re.compile(r"Named (.+?) on .*")
# "Spencer Carbery - Head Coach", "Head Coach - Joel Quenneville", "Goaltending Coach: Patrick Dalpe"
ONE_LINE_RE = re.compile(r"(.+?) [-–—:] (.+)")
# roles kept: coaches and hockey operations, not ticketing or marketing staff
HOCKEY_ROLE_RE = re.compile(
    r".*\b(?:coach\w*|general manager|hockey|scout\w*|player (?:development|personnel)"
    r"|goaltend\w*|video|equipment|captain)\b.*", re.I)
NOISE_RE = re.compile(r"Read (?:More|Bio)|Show (?:More|Less)|Previous|Next|More Info|Bio|remove|add",
                      re.I)
BIO_RE = re.compile(r".{60,}")  # a paragraph, not a name or role
TEAM_PAGE_RE = re.compile(r"^https://www\.nhl\.com/([a-z]+)/")


def is_name(line):
    return (len(line) <= 40 and NAME_RE.fullmatch(line) is not None
            and not ROLE_RE.fullmatch(line) and not NOT_NAME_RE.fullmatch(line))


def is_role(line):
    return (len(line) <= 100 and ROLE_RE.fullmatch(line) is not None
            and not SENTENCE_RE.fullmatch(line))


def one_line_pair(line):
    """(name, role) from "Name - Role" or "Role - Name", else None."""
    m = ONE_LINE_RE.fullmatch(line)
    if not m:
        return None
    a, b = m.group(1).strip(), m.group(2).strip()
    if is_name(a) and is_role(b):
        return a, b
    if is_role(a) and is_name(b):
        return b, a
    return None


def find_pairs(lines, role_first):
    """[(index, lines used, name, role)] for the people on the page."""
    pairs, i = [], 0
    while i < len(lines):
        both = one_line_pair(lines[i])
        if both:
            pairs.append((i, 1, *both))
            i += 1
            continue
        if i + 1 < len(lines):
            name, role = (lines[i + 1], lines[i]) if role_first else (lines[i], lines[i + 1])
            if is_name(name) and is_role(role):
                pairs.append((i, 2, name, role))
                i += 2
                continue
        i += 1
    return pairs


def tidy(text):
    """'GOALTENDING COACH' -> 'Goaltending Coach'; drop 'Named ... on <date>'."""
    m = NAMED_RE.fullmatch(text)
    text = (m.group(1) if m else text).strip(" ,")
    return text.title() if text.isupper() else text


def extract_coaches(page, url):
    """[{name, role, team, section, bio, url}] for the people on one staff page."""
    m = TEAM_PAGE_RE.match(url or "")
    team = m.group(1) if m else None
    lines = [x for x in html_to_lines(main_block(page)) if not NOISE_RE.fullmatch(x)]
    # name then role on most sites, role then name on some: keep the order that finds more
    pairs = max(find_pairs(lines, False), find_pairs(lines, True), key=len)
    people = []
    for n, (i, used, name, role) in enumerate(pairs):
        end = pairs[n + 1][0] if n + 1 < len(pairs) else len(lines)
        bio = " ".join(x for x in lines[i + used:end] if BIO_RE.fullmatch(x))
        # section: the last short line between the previous pair and this one
        prev_end = pairs[n - 1][0] + pairs[n - 1][1] if n else 0
        heads = [x for x in lines[prev_end:i] if not BIO_RE.fullmatch(x)]
        people.append({"name": tidy(name), "role": tidy(role), "team": team,
                       "section": heads[-1] if heads else None, "bio": bio or None, "url": url})
    return people


def merge_people(people):
    """One record per (team, name): the first role seen (staff lists come first),
    the longest bio (usually from the person's own page), the first section."""
    merged = {}
    for p in people:
        k = (p["team"], fold_diacritics(p["name"]).lower())
        if k not in merged:
            merged[k] = dict(p)
            continue
        q = merged[k]
        if len(p["bio"] or "") > len(q["bio"] or ""):
            q["bio"], q["url"] = p["bio"], p["url"]
        q["section"] = q["section"] or p["section"]
    return list(merged.values())


def is_hockey_staff(person):
    return HOCKEY_ROLE_RE.fullmatch(person["role"]) is not None
