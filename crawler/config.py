"""Crawler settings: identity, politeness, timeouts and storage paths."""
from pathlib import Path

BASE_URL = "https://www.nhl.com"
SEED_URL = BASE_URL + "/info/teams"  # static page linking all 32 team sites
ROBOTS_URL = BASE_URL + "/robots.txt"

# --- HTTP identity ---------------------------------------------------------
# A normal browser UA (the site serves bots a different/blocked page) with a
# token that identifies the crawler as a school project.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 "
    "VINF-NHL-crawler/0.1"
)
ROBOTS_AGENT = "VINF-NHL-crawler"  # token matched against robots.txt groups
EXTRA_HEADERS = {
    "Accept-Language": "en-US,en;q=0.9",
}

# --- Politeness ------------------------------------------------------------
DELAY_MIN_S = 2.0  # random sleep between two page loads
DELAY_MAX_S = 4.0
MAX_RETRIES = 3  # per URL, on timeout / 429 / 5xx
BACKOFF_BASE_S = 10.0  # 10 s, 20 s, 40 s (or Retry-After if larger)

# The rendered page pulls its data from these hosts; everything else
# (ads, trackers, analytics) is blocked, as are images, media and fonts.
ALLOWED_RESOURCE_HOSTS = ("nhl.com", "nhle.com")
BLOCKED_RESOURCE_TYPES = {"image", "media", "font"}

# --- Timeouts --------------------------------------------------------------
NAV_TIMEOUT_MS = 30_000  # page.goto (server response + DOM ready)
CONTENT_TIMEOUT_MS = 20_000  # waiting for JS to fill in the data

# --- Storage ---------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
LOG_FILE = DATA_DIR / "crawl_log.tsv"  # every attempt (ok, retry, failed, cached, robots)
MANIFEST_FILE = DATA_DIR / "manifest.tsv"  # every page saved on disk
STATE_FILE = DATA_DIR / "frontier.json"
OLD_STATE_FILE = DATA_DIR / "state.json"  # name used before the storage change
