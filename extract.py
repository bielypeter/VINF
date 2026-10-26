"""Extract players and coaches from the crawled pages into TSV documents.

    python extract.py                 # data/ -> out/extracted/*.tsv
    python extract.py --show 8483515  # one player (id) or coach (part of the name)
    python extract.py --check         # compare career totals with the stats tables

Output (UTF-8, tab-separated, header row; one row = one document):
  players.tsv   one player per row (Home + Bio + Stats merged)
  coaches.tsv   one coach / hockey staff member per row
  seasons.tsv   the players' season rows (player_id, season, team, stats)
Reads the latest 'ok' version of every page from data/manifest.tsv; data/ is
never modified, out/ is rewritten on each run.
"""
import argparse
import csv
import re
import time
from collections import defaultdict
from pathlib import Path

from crawler import storage
from crawler.urls import PLAYER_SUBPAGES
from extractor.coach import extract_coaches, is_hockey_staff, merge_people
from extractor.player import extract_player, number
from extractor.tables import CELL_RE, TABLE_RE, TR_RE
from extractor.text import clean, fold_diacritics, one_line

OUT_DIR = Path(__file__).resolve().parent / "out" / "extracted"
PLAYER_COLUMNS = [
    "doc_id", "player_id", "name", "first", "last", "number", "position", "active", "team",
    "height_in", "weight_lb", "shoots", "birth_date", "birth_city", "birth_region",
    "birth_country", "nationality", "draft_year", "draft_round", "draft_pick", "draft_overall",
    "draft_team", "draft_from", "undrafted", "teams", "awards", "career_gp", "career_g",
    "career_a", "career_p", "career_w", "career_gaa", "career_sv_pct", "about", "url"]
COACH_COLUMNS = ["doc_id", "name", "role", "team", "section", "bio", "url"]
SEASON_COLUMNS = ["player_id", "season", "team", "gp", "g", "a", "p", "plus_minus", "pim",
                  "w", "l", "t", "ot", "so", "gaa", "sv_pct"]
LIST_SEP = " ; "
STATLIST_PLAYER_RE = re.compile(r"/player/(\d+)")
SLUG_RE = re.compile(r"[^a-z0-9]+")


def saved_pages(latest):
    """({player_id: {sub: row}}, [coach page rows], [statlist rows]) of 'ok' pages."""
    players, coaches, statlists = defaultdict(dict), [], []
    for k, row in latest.items():
        if row["status"] != "ok":
            continue
        if row["page_type"] == "player":
            _, pid, sub = k.split(":")
            players[pid][sub] = row
        elif row["page_type"] == "coaches" and "/errors/" not in row["final_url"]:
            coaches.append(row)
        elif row["page_type"] == "statlist":
            statlists.append(row)
    return players, coaches, statlists


def player_record(pid, rows):
    pages = {sub: storage.read_saved(rows[sub]) for sub in PLAYER_SUBPAGES if sub in rows}
    url = next(rows[s]["final_url"] for s in ("stats", "bio", "home") if s in rows)
    return extract_player(pid, url, **pages)


def player_row(rec):
    row = {c: rec.get(c) for c in PLAYER_COLUMNS}
    row["doc_id"] = f"player:{rec['player_id']}"
    row["teams"] = LIST_SEP.join(rec["teams"])
    row["awards"] = LIST_SEP.join(f"{name} ({', '.join(years)})" if years else name
                                  for name, years in rec["awards"])
    for stat in ("gp", "g", "a", "p", "w", "gaa", "sv_pct"):
        row[f"career_{stat}"] = rec["career"].get(stat)
    return row


def coach_doc_id(person):
    return f"coach:{person['team']}:{SLUG_RE.sub('-', fold_diacritics(person['name']).lower()).strip('-')}"


def write_tsv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_NONE, quotechar=None,
                       lineterminator="\n")
        w.writerow(columns)
        for row in rows:
            w.writerow([one_line("" if row.get(c) is None else row[c]) for c in columns])


def fill_rates(rows, columns):
    n = len(rows) or 1
    return {c: sum(1 for r in rows if r.get(c) not in (None, "", [])) / n for c in columns}


def extract_all():
    latest, _ = storage.load_manifest()
    players, coach_pages, _ = saved_pages(latest)
    start = time.time()

    player_rows, season_rows = [], []
    for n, (pid, rows) in enumerate(sorted(players.items()), 1):
        rec = player_record(pid, rows)
        player_rows.append(player_row(rec))
        season_rows += [{"player_id": pid, **s} for s in rec["seasons"]]
        if n % 1000 == 0:
            print(f"  {n}/{len(players)} players  {time.time() - start:.0f}s")

    people = []
    for row in coach_pages:
        people += extract_coaches(storage.read_saved(row), row["final_url"])
    staff = [p for p in merge_people(people) if is_hockey_staff(p)]
    for p in staff:
        p["doc_id"] = coach_doc_id(p)

    write_tsv(OUT_DIR / "players.tsv", PLAYER_COLUMNS, player_rows)
    write_tsv(OUT_DIR / "seasons.tsv", SEASON_COLUMNS, season_rows)
    write_tsv(OUT_DIR / "coaches.tsv", COACH_COLUMNS, staff)

    print(f"players: {len(player_rows)}   seasons: {len(season_rows)}   coaches: {len(staff)} "
          f"(from {len(people)} people on {len(coach_pages)} staff pages)   {time.time() - start:.0f}s")
    print(f"written to {OUT_DIR}")
    print("\nfill rate per column (players):")
    for c, rate in fill_rates(player_rows, PLAYER_COLUMNS).items():
        print(f"  {c:<15}{rate:7.1%}")
    print("\nfill rate per column (coaches):")
    for c, rate in fill_rates(staff, COACH_COLUMNS).items():
        print(f"  {c:<15}{rate:7.1%}")


def show(query):
    latest, _ = storage.load_manifest()
    players, coach_pages, _ = saved_pages(latest)
    if query.isdigit():
        if query not in players:
            print(f"player {query} not found")
            return
        rec = player_record(query, players[query])
        seasons = rec.pop("seasons")
        for k, v in player_row(rec).items():
            print(f"{k:<15}{v}")
        print(f"{'seasons':<15}{len(seasons)} rows, e.g. {seasons[:2]}")
        return
    q = fold_diacritics(query).lower()
    for row in coach_pages:
        for p in extract_coaches(storage.read_saved(row), row["final_url"]):
            if q in fold_diacritics(p["name"]).lower():
                print("\n".join(f"{k:<10}{v}" for k, v in p.items()), end="\n\n")


def statlist_totals(page):
    """{player_id: {gp, g, a, p, w}} from one all-time stats table page."""
    m = TABLE_RE.search(page)
    if not m:
        return {}
    header, totals = None, {}
    for tr in TR_RE.findall(m.group(1)):
        cells = [clean(text) for _, text in CELL_RE.findall(tr)]
        if header is None:
            header = cells
            continue
        link = STATLIST_PLAYER_RE.search(tr)
        if link:
            values = dict(zip(header, cells))
            totals[link.group(1)] = {k.lower(): number(values.get(k)) for k in ("GP", "G", "A", "P", "W")
                                     if k in values}
    return totals


def check():
    """Career totals from the player's Stats page vs. the all-time stats tables.

    Only former players are compared: active players' pages were saved days after
    the tables, so their totals legitimately differ. Goalie pages have no P column.
    """
    latest, _ = storage.load_manifest()
    players, _, statlists = saved_pages(latest)
    expected = {}
    # skaters who also played a few games in goal are in both tables; their
    # Stats page shows the skater totals, so the skater tables are read last
    for row in sorted(statlists, key=lambda r: ":skaters:" in r["key"]):
        expected.update(statlist_totals(storage.read_saved(row)))
    compared = matched = active = other_kind = 0
    mismatches = []
    for pid, want in expected.items():
        if "stats" not in players.get(pid, {}):
            continue
        rec = player_record(pid, {"stats": players[pid]["stats"]})
        if rec["active"]:
            active += 1
            continue
        if "w" in want:  # goalie table
            if "w" not in rec["career"]:  # a skater whose skater row is not crawled yet
                other_kind += 1
                continue
            want = {k: v for k, v in want.items() if k != "p"}
        got = {k: rec["career"].get(k) for k in want}
        compared += 1
        # the page shows '--' where the table shows 0 (a goalie without a decision)
        if all(got[k] == v or (got[k] is None and v == 0) for k, v in want.items()):
            matched += 1
        else:
            mismatches.append((pid, want, got))
    print(f"players in stats tables: {len(expected)}   with a saved Stats page: "
          f"{compared + active + other_kind}   skipped: {active} active, "
          f"{other_kind} skaters found only in the goalie table")
    print(f"former players, career totals equal: {matched}/{compared} ({matched / max(compared, 1):.1%})")
    for pid, want, got in mismatches[:15]:
        print(f"  {pid}: table {want}  page {got}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", metavar="ID_OR_NAME", help="print one player (id) or coach (name)")
    ap.add_argument("--check", action="store_true", help="compare career totals with the stats tables")
    args = ap.parse_args()
    if args.show:
        show(args.show)
    elif args.check:
        check()
    else:
        extract_all()


if __name__ == "__main__":
    main()
