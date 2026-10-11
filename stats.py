"""Summary of the crawled data, read from data/manifest.tsv.

    python stats.py
"""
import re
from collections import Counter, defaultdict

from crawler import config, storage
from crawler.urls import PLAYER_SUBPAGES

TARGET_MB = 500  # course minimum
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

    size = sum((config.DATA_DIR / row["file"]).stat().st_size for row in rows)
    mb = size / 1024 / 1024
    print(f"\nraw HTML on disk: {mb:.1f} MB ({mb / TARGET_MB:.0%} of the {TARGET_MB} MB minimum)")


if __name__ == "__main__":
    main()
