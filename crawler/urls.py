"""URL patterns (regex), page classification, canonical keys and link extraction."""
import html
import re
from urllib.parse import quote, unquote, urljoin, urlsplit

from .config import BASE_URL

# https://www.nhl.com/info/teams
TEAMS_RE = re.compile(r"^https://www\.nhl\.com/info/teams/?$")
# https://www.nhl.com/penguins/roster
ROSTER_RE = re.compile(r"^https://www\.nhl\.com/([a-z]+)/roster/?$")
# https://www.nhl.com/player/8471675  (roster/stats links; redirects to .../stats)
PLAYER_SHORT_RE = re.compile(r"^https://www\.nhl\.com/player/(\d+)/?$")
# https://www.nhl.com/canadiens/player/juraj-slafkovský-8483515/bio
# https://www.nhl.com/player/tom-barrasso-8445275/stats   (former players: no team)
PLAYER_RE = re.compile(
    r"^https://www\.nhl\.com/(?:([a-z]+)/)?player/([^/]+)-(\d+)(?:/(home|bio|stats))?/?$"
)
# All-time stats tables, 100 players per page; they list every former player.
# https://www.nhl.com/stats/skaters?reportType=allSeasons&...&page=0&pageSize=100
STATLIST_RE = re.compile(r"^https://www\.nhl\.com/stats/(skaters|goalies)\?.*\bpage=(\d+)")
STATLIST_SORT = {"skaters": "points", "goalies": "wins"}
STATLIST_PAGE_SIZE = 100
# The sitemap lists the teams' coaching staff pages (their URLs differ per team).
SITEMAP_URL = BASE_URL + "/sitemap/sitemap.xml"
SITEMAP_RE = re.compile(r"^https://www\.nhl\.com/sitemap/sitemap\.xml$")
LOC_RE = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>")
# https://www.nhl.com/stars/team/coaching-staff
# https://www.nhl.com/kraken/team/coaching-staff/lane-lambert   (one coach)
COACHES_RE = re.compile(
    r"^https://www\.nhl\.com/([a-z]+)/(?:team|equipe)/("
    # one person's page; not e.g. hockey-ops/scouting-staff
    r"(?:coaching-staff|hockey-operations|hockey-ops)(?:/(?![a-z0-9-]*-staff$)[a-z0-9-]+)?"
    r"|coaches|head-coach|captains-and-coaches|coaches-and-training-staff"
    r"|hockey-operations-staff|hockey-staff|staff|staff-listing|staff/hockey-personnel"
    r"|team-operations-staff"
    r")/?$"
)

HREF_RE = re.compile(r"""<a\b[^>]*?\bhref\s*=\s*["']([^"'#]+)""", re.I)
# Team sites are linked as absolute https://www.nhl.com/<slug> on the teams page;
# language editions (/fr, /sk, ...) are 2 letters, so {3,} skips them.
TEAM_LINK_RE = re.compile(r"""href=["']https://www\.nhl\.com/([a-z]{3,})/?["']""")
NOT_TEAMS = {"stats", "info", "news", "video", "scores", "standings", "schedule"}

PLAYER_SUBPAGES = ("home", "bio", "stats")
# Fetched with plain HTTP; everything else is rendered in the browser.
STATIC_TYPES = {"sitemap", "coaches"}


def statlist_url(kind, page):
    return (f"{BASE_URL}/stats/{kind}?reportType=allSeasons&seasonFrom=19171918"
            f"&seasonTo=20262027&gameType=2&sort={STATLIST_SORT[kind]}"
            f"&page={page}&pageSize={STATLIST_PAGE_SIZE}")


def normalize(url, base=BASE_URL):
    """Absolute URL, path decoded so 'ý' and '%C3%BD' match, no fragment.

    The query is dropped except on stats tables, where it selects the page.
    """
    url = urljoin(base, html.unescape(url).strip())
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return None
    path = unquote(parts.path)
    if len(path) > 1:
        path = path.rstrip("/")
    query = f"?{parts.query}" if parts.query and path.startswith("/stats/") else ""
    return f"https://{parts.netloc.lower()}{path}{query}"


def to_request_url(url):
    """Percent-encode the path for the actual HTTP request."""
    parts = urlsplit(url)
    query = f"?{parts.query}" if parts.query else ""
    return f"{parts.scheme}://{parts.netloc}{quote(parts.path, safe='/-_.~')}{query}"


def classify(url):
    """Return (page_type, info) for in-scope URLs, or (None, None)."""
    if TEAMS_RE.match(url):
        return "teams", {}
    m = ROSTER_RE.match(url)
    if m:
        return "roster", {"team": m.group(1)}
    m = PLAYER_SHORT_RE.match(url)
    if m:
        return "player", {"id": m.group(1), "sub": "stats", "team": None, "slug": None}
    m = PLAYER_RE.match(url)
    if m:
        # bare /<team>/player/<slug>-<id> redirects to /stats
        return "player", {"team": m.group(1), "slug": m.group(2),
                          "id": m.group(3), "sub": m.group(4) or "stats"}
    m = STATLIST_RE.match(url)
    if m:
        return "statlist", {"kind": m.group(1), "page": int(m.group(2))}
    if SITEMAP_RE.match(url):
        return "sitemap", {}
    m = COACHES_RE.match(url)
    if m:
        return "coaches", {"team": m.group(1), "path": m.group(2)}
    return None, None


def key(url):
    """Canonical identity of a page, used for the visited set.

    A player is identified by id + subpage, so /player/<id>, the bare player URL
    and /<team>/player/<slug>-<id>/stats are the same page, and a traded
    player's old-team URL does not get crawled twice.
    """
    page_type, info = classify(url)
    if page_type == "roster":
        return f"roster:{info['team']}"
    if page_type == "player":
        return f"player:{info['id']}:{info['sub']}"
    if page_type == "statlist":
        return f"statlist:{info['kind']}:{info['page']}"
    if page_type == "coaches":
        return f"coaches:{info['team']}:{info['path']}"
    return url


def extract_links(page_html, page_url, page_type):
    """In-scope links worth following from a page."""
    if page_type == "teams":
        slugs = sorted(set(TEAM_LINK_RE.findall(page_html)) - NOT_TEAMS)
        return [f"{BASE_URL}/{slug}/roster" for slug in slugs]
    if page_type == "sitemap":
        locs = (normalize(loc) for loc in LOC_RE.findall(page_html))
        return [url for url in locs if url and classify(url)[0] == "coaches"]

    links = []
    for href in HREF_RE.findall(page_html):
        url = normalize(href, page_url)
        if url is None:
            continue
        link_type, info = classify(url)
        if link_type == "player":
            links.append(url)
            # From a full player URL we know the other two subpages too.
            if info["slug"]:
                team = f"/{info['team']}" if info["team"] else ""
                stem = f"{BASE_URL}{team}/player/{info['slug']}-{info['id']}"
                links.extend(f"{stem}/{sub}" for sub in PLAYER_SUBPAGES)
        elif link_type in ("roster", "coaches"):
            links.append(url)

    if page_type == "statlist":
        # The "next page" control is a button, not a link: a full page means
        # there is probably another one.
        info = classify(page_url)[1]
        players = {classify(link)[1]["id"] for link in links if classify(link)[0] == "player"}
        if len(players) >= STATLIST_PAGE_SIZE:
            links.append(statlist_url(info["kind"], info["page"] + 1))
    return links
