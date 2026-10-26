"""Inverted index built from the extracted TSV documents, saved as TSV files.

out/index/
  docs.tsv      doc (number), doc_id, type, name, length (tokens), norm (|d| for cosine)
  postings.tsv  term, df, postings as "doc:tf,doc:tf,..." sorted by doc
  meta.tsv      key, value: documents, terms, avgdl, build time, sources
"""
import csv
import time
from collections import Counter, defaultdict
from pathlib import Path

from .rank import doc_norms
from .tokenize import tokenize

ROOT = Path(__file__).resolve().parent.parent
EXTRACTED_DIR = ROOT / "out" / "extracted"
INDEX_DIR = ROOT / "out" / "index"

POSITIONS = {"C": "center", "LW": "left wing winger", "RW": "right wing winger",
             "L": "left wing winger", "R": "right wing winger",
             "D": "defenseman defense", "G": "goalie goaltender", "F": "forward"}


def read_tsv(path):
    with path.open(encoding="utf-8", newline="") as f:
        yield from csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)


def write_tsv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", quoting=csv.QUOTE_NONE, quotechar=None,
                       lineterminator="\n")
        w.writerow(columns)
        w.writerows(rows)


def player_text(r):
    """The searchable text of a player document (numbers from tables are left out)."""
    if r["undrafted"] == "True":
        draft = "undrafted"
    elif r["draft_year"]:
        draft = (f"drafted {r['draft_year']} draft round {r['draft_round']} pick {r['draft_pick']} "
                 f"overall {r['draft_overall']} {r['draft_team']} from {r['draft_from']}")
    else:
        draft = ""
    return " ".join([
        r["name"], r["position"], POSITIONS.get(r["position"], ""), r["team"],
        "active" if r["active"] == "True" else "former", r["teams"],
        "born", r["birth_date"][:4], r["birth_city"], r["birth_region"], r["birth_country"],
        r["nationality"], draft, r["awards"], r["about"]])


def coach_text(r):
    return " ".join([r["name"], r["role"], r["team"], r["section"], "staff", r["bio"]])


def documents(extracted_dir=EXTRACTED_DIR):
    """(doc_id, type, name, text) for every row of players.tsv and coaches.tsv."""
    for r in read_tsv(extracted_dir / "players.tsv"):
        yield r["doc_id"], "player", r["name"], player_text(r)
    for r in read_tsv(extracted_dir / "coaches.tsv"):
        yield r["doc_id"], "coach", r["name"], coach_text(r)


class Index:
    def __init__(self):
        self.docs = []  # doc number -> (doc_id, type, name)
        self.lengths = []  # doc number -> tokens in the document
        self.postings = {}  # term -> (df, [(doc, tf), ...])
        self.norms = {}  # doc number -> |d| of its TF-IDF vector

    @property
    def n_docs(self):
        return len(self.docs)

    @property
    def avgdl(self):
        return sum(self.lengths) / max(len(self.lengths), 1)

    @classmethod
    def build(cls, docs):
        index = cls()
        plists = defaultdict(list)
        for doc_id, kind, name, text in docs:
            tokens = tokenize(text)
            doc = len(index.docs)
            index.docs.append((doc_id, kind, name))
            index.lengths.append(len(tokens))
            for term, tf in Counter(tokens).items():
                plists[term].append((doc, tf))
        index.postings = {t: (len(p), p) for t, p in plists.items()}
        index.norms = doc_norms(index.postings, index.n_docs)
        return index

    def save(self, folder=INDEX_DIR, **meta):
        write_tsv(folder / "docs.tsv", ["doc", "doc_id", "type", "name", "length", "norm"],
                  [(d, *self.docs[d], self.lengths[d], f"{self.norms.get(d, 0):.6f}")
                   for d in range(self.n_docs)])
        write_tsv(folder / "postings.tsv", ["term", "df", "postings"],
                  [(t, df, ",".join(f"{d}:{tf}" for d, tf in plist))
                   for t, (df, plist) in sorted(self.postings.items())])
        meta = {"documents": self.n_docs, "terms": len(self.postings),
                "avgdl": f"{self.avgdl:.2f}", "built": time.strftime("%Y-%m-%dT%H:%M:%S"), **meta}
        write_tsv(folder / "meta.tsv", ["key", "value"], meta.items())

    @classmethod
    def load(cls, folder=INDEX_DIR):
        index = cls()
        for r in read_tsv(folder / "docs.tsv"):
            index.docs.append((r["doc_id"], r["type"], r["name"]))
            index.lengths.append(int(r["length"]))
            index.norms[int(r["doc"])] = float(r["norm"])
        for r in read_tsv(folder / "postings.tsv"):
            plist = [tuple(map(int, p.split(":"))) for p in r["postings"].split(",")]
            index.postings[r["term"]] = (int(r["df"]), plist)
        return index
