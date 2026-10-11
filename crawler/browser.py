"""Headless Chromium fetcher.

nhl.com sends an empty HTML shell and fills in player data with JavaScript, so
each page is rendered and the resulting DOM is saved.
"""
import time
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from . import config

# Element that only exists once the JavaScript has filled in the data.
CONTENT_MARKERS = {
    "teams": None,  # static page
    "roster": 'a[href*="/player/"]',
    "statlist": 'a[href*="/player/"]',
    ("player", "home"): 'main a[href*="/bio"]',  # Home/Bio/Stats tabs in the player header
    ("player", "bio"): "text=Birthplace",
    ("player", "stats"): "main table",
}


class FetchResult:
    def __init__(self, status, final_url, html, render_s, error=None, retry_after=None):
        self.status = status
        self.final_url = final_url
        self.html = html
        self.render_s = render_s
        self.error = error
        self.retry_after = retry_after


class Browser:
    def __init__(self, headless=True):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=headless)
        self._context = self._browser.new_context(
            user_agent=config.USER_AGENT,
            extra_http_headers=config.EXTRA_HEADERS,
            locale="en-US",
            viewport={"width": 1366, "height": 900},
        )
        self._context.route("**/*", self._filter_request)
        self._page = self._context.new_page()
        self._page.set_default_navigation_timeout(config.NAV_TIMEOUT_MS)

    @staticmethod
    def _filter_request(route):
        req = route.request
        host = urlsplit(req.url).hostname or ""
        if req.resource_type in config.BLOCKED_RESOURCE_TYPES or not host.endswith(
            config.ALLOWED_RESOURCE_HOSTS
        ):
            return route.abort()
        return route.continue_()

    def fetch(self, url, marker_key):
        page = self._page
        start = time.time()
        try:
            response = page.goto(url, wait_until="domcontentloaded")
        except (PlaywrightTimeout, PlaywrightError) as e:
            return FetchResult(None, url, None, time.time() - start, error=f"goto: {e}".split("\n")[0])

        status = response.status if response else None
        retry_after = response.headers.get("retry-after") if response else None
        if status is None or status >= 400:
            return FetchResult(status, page.url, None, time.time() - start,
                               error=f"HTTP {status}", retry_after=retry_after)

        marker = CONTENT_MARKERS.get(marker_key)
        error = None
        if marker:
            try:
                page.wait_for_selector(marker, timeout=config.CONTENT_TIMEOUT_MS)
            except PlaywrightTimeout:
                error = f"content not rendered ({marker})"
        if error is None:
            try:  # let the remaining API calls (e.g. more stats tables) finish
                page.wait_for_load_state("networkidle", timeout=5_000)
            except PlaywrightTimeout:
                pass
        return FetchResult(status, page.url, page.content(), time.time() - start, error=error)

    def close(self):
        self._context.close()
        self._browser.close()
        self._pw.stop()
