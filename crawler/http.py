"""Plain HTTP fetcher for static pages (sitemap, coaching staff pages)."""
import re
import time
import urllib.error
import urllib.request

from . import config
from .browser import FetchResult

CHARSET_RE = re.compile(r"charset=([\w-]+)", re.I)


class Http:
    def fetch(self, url, marker_key=None):
        headers = {"User-Agent": config.USER_AGENT,
                   "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                   **config.EXTRA_HEADERS}
        start = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers),
                                        timeout=config.NAV_TIMEOUT_MS / 1000) as resp:
                body = resp.read()
                m = CHARSET_RE.search(resp.headers.get("Content-Type", ""))
                text = body.decode(m.group(1) if m else "utf-8", "replace")
                return FetchResult(resp.status, resp.geturl(), text, time.time() - start)
        except urllib.error.HTTPError as e:
            return FetchResult(e.code, url, None, time.time() - start,
                               error=f"HTTP {e.code}", retry_after=e.headers.get("Retry-After"))
        except Exception as e:  # timeout, connection reset, DNS ...
            return FetchResult(None, url, None, time.time() - start, error=f"http: {e}")

    def close(self):
        pass
