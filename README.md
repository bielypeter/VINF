# VINF – NHL crawler

Crawls nhl.com player pages (Home, Bio, Stats) for current and former players,
and the teams' coaching staff pages. Player pages and stats tables are rendered
in headless Chromium because nhl.com sends an empty HTML shell and loads the
data with JavaScript; the sitemap and coach pages are static and fetched with
plain HTTP.

| Source (`--sources`) | Path |
|---|---|
| `rosters` | `/info/teams` → `/<team>/roster` (32) → current players |
| `alltime` | all-time stats tables `/stats/skaters` (~80 pages) and `/stats/goalies` (~10 pages), 100 players each → about 8,900 former and current players |
| `coaches` | `/sitemap/sitemap.xml` → coaching staff pages of 25 teams (~95 pages); the other 7 teams have no recognisable coach URL |

A full crawl is about 27,000 pages (~6 GB) and takes 2–3 days; stop and resume as needed.

## Setup

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m playwright install chromium
```

## Run

```
.venv\Scripts\python crawl.py --teams penguins,canadiens --max-pages 50   # small sample
.venv\Scripts\python crawl.py --sources coaches                            # only coaches
.venv\Scripts\python crawl.py                                              # everything, resumes
.venv\Scripts\python crawl.py --fresh                                      # restart the queue
.venv\Scripts\python crawl.py --fresh --recrawl                            # download everything again
.venv\Scripts\python stats.py                                              # what is on disk
```

Ctrl+C stops the crawl; the next run continues from `data/frontier.json`.
`--fresh` never downloads a page that is already saved, it reads it from disk to
follow its links. `--recrawl` downloads again and stores a new version next to
the old one.

Archive the data with zip (not rar): `python -m zipfile -c nhl_data.zip data`

## Layout

| File | Purpose |
|---|---|
| `crawl.py` | main loop: frontier → robots check → render → save → extract links → sleep |
| `crawler/config.py` | User-Agent, headers, delays, timeouts, paths |
| `crawler/urls.py` | regex URL patterns, normalization, link extraction |
| `crawler/robots.py` | robots.txt parser (supports `*` and `$`) |
| `crawler/frontier.py` | URL queue + visited set, saved to JSON |
| `crawler/browser.py` | Playwright fetcher, blocks ads/images, waits for data to render |
| `crawler/http.py` | plain HTTP fetcher for static pages (sitemap, coaches) |
| `crawler/storage.py` | append-only page storage, `manifest.tsv`, `crawl_log.tsv` |
| `stats.py` | pages, players per team and MB on disk, from the manifest |

## Data

Nothing is ever overwritten or deleted. Each download is a new file named by
its timestamp; a re-crawl adds a version next to the old one.

```
data/
  manifest.tsv            one row per saved page (append-only)
  crawl_log.tsv           one row per attempt: ok, partial, failed, retry, cached, robots
  frontier.json           queue + visited set for resuming
  raw/
    teams/<ts>.html
    rosters/<team>/<ts>.html
    players/<player id>/{home,bio,stats}/<ts>.html
    statlists/{skaters,goalies}/page-NNN/<ts>.html
    sitemap/<ts>.xml
    coaches/<team>/<page>/<ts>.html      e.g. coaches/kraken/coaching-staff__lane-lambert/
```

`manifest.tsv` columns: `ts key page_type status url final_url http_status bytes sha1 render_s file`.
`key` identifies a page (`player:8483515:bio`, `roster:canadiens`); the last row
for a key is its current version. `status` is `ok`, or `partial` when the page's
data never rendered (kept, and downloaded again on the next run).
Load it with `crawler.storage.load_manifest()`.

See `docs/konzultacia-2a.txt` for the consultation write-up (DokuWiki syntax).
