"""Summary of the crawled data, read from data/manifest.tsv.

    python stats.py
"""
import re
from collections import Counter, defaultdict
from datetime import datetime

from crawler import config, storage
from crawler.urls import PLAYER_SUBPAGES

TARGET_MB = 500  # course minimum
MAX_GAP_S = 600  # a longer pause between two log rows means the crawler was stopped
TEAM_RE = re.compile(r"^https://www\.nhl\.com/([a-z]+)/player/")


def main():
    latest, history = storage.load_manifest()
    if not latest:
        print("manifest is empty")
        return
    rows = [row for rows in history.values() for row in rows]

    pages = Counter(row["page_type"] for row in latest.values())
    statuses = Counter(row["status"] for row in latest.values())
    print(f"pages (latest versions): {len(latest)}   all versions: {len(rows)}")
    print("  by type:   " + ", ".join(f"{t}={n}" for t, n in sorted(pages.items())))
    print("  by status: " + ", ".join(f"{s}={n}" for s, n in sorted(statuses.items())))

    # player id -> team slug (from the latest saved URL) and saved subpages
    team_of, subpages = {}, defaultdict(set)
    for k, row in latest.items():
        if row["page_type"] != "player" or row["status"] != "ok":
            continue
        _, pid, sub = k.split(":")
        subpages[pid].add(sub)
        m = TEAM_RE.match(row["final_url"])
        if m:
            team_of[pid] = m.group(1)

    per_team = defaultdict(lambda: [0, 0])
    for pid, subs in subpages.items():
        team = team_of.get(pid, "(former)")  # retired players' URLs have no team
        per_team[team][0] += 1
        per_team[team][1] += subs >= set(PLAYER_SUBPAGES)
    print(f"\nplayers: {len(subpages)}   complete (home+bio+stats): "
          f"{sum(c for _, c in per_team.values())}")
    print(f"  {'team':<15}{'players':>8}{'complete':>10}")
    for team, (n, complete) in sorted(per_team.items()):
        print(f"  {team:<15}{n:>8}{complete:>10}")

    coaches = Counter(k.split(":")[1] for k, row in latest.items()
                      if row["page_type"] == "coaches" and row["status"] == "ok")
    if coaches:
        print(f"\ncoach pages: {sum(coaches.values())} from {len(coaches)} teams: "
              + ", ".join(f"{t}={n}" for t, n in sorted(coaches.items())))

    sizes = defaultdict(list)  # page type -> file sizes of all versions
    for row in rows:
        sizes[row["page_type"]].append((config.DATA_DIR / row["file"]).stat().st_size)
    print(f"\n  {'type':<10}{'files':>7}{'MB':>10}{'avg KB':>9}")
    for t, s in sorted(sizes.items()):
        print(f"  {t:<10}{len(s):>7}{sum(s) / 2**20:>10.1f}{sum(s) / len(s) / 1024:>9.0f}")
    mb = sum(map(sum, sizes.values())) / 2**20
    print(f"\nraw HTML on disk: {mb:.1f} MB ({mb / TARGET_MB:.0%} of the {TARGET_MB} MB minimum)")
    crawl_log_summary()


def crawl_log_summary():
    """Attempts by status and crawl time, from data/crawl_log.tsv."""
    if not config.LOG_FILE.exists():
        return
    statuses, times = Counter(), []
    with config.LOG_FILE.open(encoding="utf-8") as f:
        header = f.readline().rstrip("\n").split("\t")
        for line in f:
            row = dict(zip(header, line.rstrip("\n").split("\t")))
            statuses[row["status"]] += 1
            if row["status"] != "cached":  # cached pages are read from disk, not downloaded
                times.append(datetime.fromisoformat(row["timestamp"]))
    print("\ncrawl attempts: " + ", ".join(f"{s}={n}" for s, n in statuses.most_common()))
    if len(times) < 2:
        return
    # time actually crawling: gaps longer than MAX_GAP are breaks between runs
    busy = sum((b - a).total_seconds() for a, b in zip(times, times[1:])
               if (b - a).total_seconds() < MAX_GAP_S)
    print(f"crawled from {times[0]:%Y-%m-%d %H:%M} to {times[-1]:%Y-%m-%d %H:%M}, "
          f"{busy / 3600:.1f} h of crawling, {statuses['ok'] / max(busy / 3600, 1e-9):.0f} pages/h")


if __name__ == "__main__":
    main()
