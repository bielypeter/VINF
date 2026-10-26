"""NHL.com player crawler.

    python crawl.py --max-pages 30 --teams penguins,canadiens
    python crawl.py              # resume from data/frontier.json, crawl everything
    python crawl.py --fresh      # restart the queue; saved pages are read from disk
    python crawl.py --recrawl    # download again, keeping the old versions

Sources (--sources):
  rosters  teams page -> team rosters -> player pages (home, bio, stats)
  alltime  all-time stats tables (skaters, goalies) -> former player pages
  coaches  sitemap -> coaching staff pages of each team (static, plain HTTP)
Saved pages are never overwritten; see crawler/storage.py.
"""
import argparse
import random
import time
from urllib.parse import urlsplit

from crawler import config, storage
from crawler.browser import Browser
from crawler.frontier import Frontier
from crawler.http import Http
from crawler.robots import Robots
from crawler.urls import (SITEMAP_URL, STATIC_TYPES, classify, extract_links, key,
                          normalize, statlist_url, to_request_url)

RETRY_STATUSES = {429, 500, 502, 503, 504}

# Where players and coaches are found. Player pages are in scope for every source.
SOURCES = {
    "rosters": {"seeds": [config.SEED_URL], "types": {"teams", "roster"}},  # current players
    "alltime": {"seeds": [statlist_url("skaters", 0), statlist_url("goalies", 0)],
                "types": {"statlist"}},  # former players, from the all-time stats tables
    "coaches": {"seeds": [SITEMAP_URL], "types": {"sitemap", "coaches"}},  # coaching staff
}


def in_scope(url, teams, sources):
    page_type, info = classify(url)
    if page_type is None:
        return False
    if page_type != "player" and not any(page_type in SOURCES[s]["types"] for s in sources):
        return False
    if page_type in ("roster", "coaches") and teams:
        return info["team"] in teams
    return True


def backoff_seconds(attempt, retry_after):
    wait = config.BACKOFF_BASE_S * 2 ** (attempt - 1)
    if retry_after and retry_after.isdigit():
        wait = max(wait, int(retry_after))
    return wait


def enqueue_links(frontier, html, page_url, page_type, info, teams, sources):
    """Add the page's in-scope links to the frontier; returns how many were new."""
    links = [link for link in extract_links(html, page_url, page_type)
             if in_scope(link, teams, sources)]
    # the current player's other subpages go first, so a player's
    # home/bio/stats are downloaded together
    same_player = info["id"] if page_type == "player" else None
    return sum(frontier.add(link, front=same_player is not None
                            and classify(link)[1].get("id") == same_player)
               for link in links)


def crawl(max_pages, teams, sources, fresh, recrawl, headless):
    robots = Robots.fetch(config.ROBOTS_URL, config.ROBOTS_AGENT, config.USER_AGENT)
    delay_min = max(config.DELAY_MIN_S, robots.crawl_delay or 0)
    delay_max = max(config.DELAY_MAX_S, delay_min)

    manifest, _ = storage.load_manifest()  # key -> latest saved version
    frontier = Frontier(config.STATE_FILE)
    if not frontier.load(config.OLD_STATE_FILE) or fresh:
        frontier = Frontier(config.STATE_FILE)
    for source in sources:  # seeds already seen are ignored by the frontier
        for seed in SOURCES[source]["seeds"]:
            frontier.add(seed)
    print(f"[start] queue={len(frontier)} done={len(frontier.done)} saved={len(manifest)} "
          f"delay={delay_min}-{delay_max}s sources={','.join(sources)} "
          f"teams={','.join(sorted(teams)) or 'all'}" + (" recrawl" if recrawl else ""))

    browser, http = Browser(headless=headless), Http()
    fetched, url = 0, None
    try:
        while fetched < max_pages:
            url = frontier.pop()
            if url is None:
                print("[done] frontier is empty")
                break
            page_type, info = classify(url)
            if page_type is None:
                continue

            # Already on disk: no request, follow its links from the saved copy.
            saved = manifest.get(key(url))
            if saved and saved["status"] == "ok" and not recrawl:
                saved_type, saved_info = classify(saved["final_url"])
                added = enqueue_links(frontier, storage.read_saved(saved), saved["final_url"],
                                      saved_type, saved_info, teams, sources)
                frontier.mark_done(url, saved["final_url"])
                storage.log(status="cached", page_type=saved_type, key=key(url), url=url,
                            final_url=saved["final_url"], file=saved["file"])
                print(f"[cached] {saved_type:<8} +{added:<3} queue={len(frontier):<5} {saved['final_url']}")
                continue

            if not robots.allowed(urlsplit(url).path):
                frontier.mark_done(url)
                storage.log(status="robots", page_type=page_type, key=url, url=url)
                print(f"[skip] robots.txt disallows {url}")
                continue

            marker_key = ("player", info["sub"]) if page_type == "player" else page_type
            fetcher = http if page_type in STATIC_TYPES else browser
            res = fetcher.fetch(to_request_url(url), marker_key)
            fetched += 1
            final_url = normalize(res.final_url) or url
            final_type, final_info = classify(final_url)
            if final_type is None:  # redirected out of scope; keep original identity
                final_type, final_info = page_type, info

            # timeouts, 429/5xx and pages whose data never rendered are retried
            retriable = res.error and (res.status is None or res.status in RETRY_STATUSES
                                       or res.html is not None)
            if retriable and frontier.retries.get(key(url), 0) < config.MAX_RETRIES:
                attempt = frontier.requeue(url)
                wait = backoff_seconds(attempt, res.retry_after)
                storage.log(status="retry", page_type=page_type, key=key(url), url=url,
                            final_url=final_url, render_s=f"{res.render_s:.1f}", error=res.error)
                print(f"[retry {attempt}/{config.MAX_RETRIES}] {url}: {res.error} (waiting {wait:.0f}s)")
                frontier.save()
                time.sleep(wait)
                continue

            # ok: saved with data; partial: saved, but the data never rendered
            # (kept, and downloaded again next run); failed: nothing to save
            status = "ok" if not res.error else "partial" if res.html is not None else "failed"
            file, added = "", 0
            if res.html is not None:
                path, ts, sha1, size = storage.save_html(final_type, final_info, res.html)
                file = path.relative_to(config.DATA_DIR).as_posix()
                row = dict(ts=ts, key=key(final_url), page_type=final_type, status=status,
                           url=url, final_url=final_url, http_status=res.status, bytes=size,
                           sha1=sha1, render_s=f"{res.render_s:.1f}", file=file)
                storage.append_manifest(**row)
                manifest[row["key"]] = row
                added = enqueue_links(frontier, res.html, final_url, final_type, final_info,
                                      teams, sources)
            frontier.mark_done(url, final_url)

            storage.log(status=status, page_type=final_type, key=key(final_url), url=url,
                        final_url=final_url, bytes=len(res.html or ""),
                        render_s=f"{res.render_s:.1f}", file=file, error=res.error or "")
            print(f"[{status} {fetched}/{max_pages}] {final_type:<8} {res.render_s:4.1f}s "
                  f"+{added:<3} queue={len(frontier):<5} {final_url}"
                  + (f"  ({res.error})" if res.error else ""))
            frontier.save()
            time.sleep(random.uniform(delay_min, delay_max))
    except KeyboardInterrupt:
        # the page being downloaded was already popped; put it back for the next run
        if url and key(url) not in frontier.done and url not in frontier.queue:
            frontier.queue.appendleft(url)
        print("\n[stop] interrupted, state saved")
    finally:
        frontier.save()
        browser.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-pages", type=int, default=10**9, help="stop after N page loads")
    ap.add_argument("--teams", default="",
                    help="comma-separated team slugs for rosters and coaches, e.g. penguins,canadiens")
    ap.add_argument("--sources", default=",".join(SOURCES),
                    help=f"comma-separated subset of: {', '.join(SOURCES)} (default: all)")
    ap.add_argument("--fresh", action="store_true",
                    help="start the queue again from the seed (pages already saved are not downloaded again)")
    ap.add_argument("--recrawl", action="store_true",
                    help="download pages again even if saved; the new version is stored next to the old one")
    ap.add_argument("--headful", action="store_true", help="show the browser window")
    args = ap.parse_args()
    teams = {t.strip() for t in args.teams.split(",") if t.strip()}
    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    unknown = set(sources) - set(SOURCES)
    if unknown:
        ap.error(f"unknown source(s): {', '.join(sorted(unknown))}")
    crawl(args.max_pages, teams, sources, args.fresh, args.recrawl, not args.headful)


if __name__ == "__main__":
    main()
