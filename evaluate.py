"""Precision / recall of TF-IDF cosine and BM25 on the test queries.

    python evaluate.py            # table per query + averages
    python evaluate.py --errors   # also the non-relevant documents in each top 10

eval/queries.tsv: qid, query, relevant, note. 'relevant' is a filter on the
extracted fields that defines the relevant documents, conditions joined by '&':
  field=value   equal            field~text   contains
(case and diacritics ignored; type=player|coach selects the document file).
"""
import argparse
import re
from pathlib import Path

from extractor.text import fold_diacritics
from search.indexer import EXTRACTED_DIR, Index, read_tsv
from search.rank import METRICS
from search.tokenize import tokenize

QUERIES_FILE = Path(__file__).resolve().parent / "eval" / "queries.tsv"
DEPTH = 100  # documents retrieved per query
CONDITION_RE = re.compile(r"\s*(\w+)\s*([=~])\s*(.+?)\s*")


def norm(text):
    return fold_diacritics(text or "").lower()


def relevant_docs(rule, rows):
    conditions = [CONDITION_RE.fullmatch(c).groups() for c in rule.split("&")]
    return {r["doc_id"] for r in rows
            if all((norm(r.get(f)) == norm(v)) if op == "=" else (norm(v) in norm(r.get(f)))
                   for f, op, v in conditions)}


def average_precision(ranked, relevant):
    hits, total = 0, 0.0
    for i, doc_id in enumerate(ranked, 1):
        if doc_id in relevant:
            hits += 1
            total += hits / i
    return total / len(relevant) if relevant else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--errors", action="store_true", help="list non-relevant documents in each top 10")
    args = ap.parse_args()

    rows = [{**r, "type": "player"} for r in read_tsv(EXTRACTED_DIR / "players.tsv")]
    rows += [{**r, "type": "coach"} for r in read_tsv(EXTRACTED_DIR / "coaches.tsv")]
    names = {r["doc_id"]: r["name"] for r in rows}
    index = Index.load()
    queries = list(read_tsv(QUERIES_FILE))

    print(f"{len(queries)} queries, {index.n_docs} documents, top {DEPTH} retrieved\n")
    header = f"{'qid':<4} {'query':<34}{'|R|':>4}"
    for m in METRICS:
        header += f" | {m.upper() + ' P@10':>11} {'R@100':>6} {'AP':>6}"
    print(header)
    print("-" * len(header))
    totals = {m: [0.0, 0.0, 0.0] for m in METRICS}
    errors = []
    for q in queries:
        relevant = relevant_docs(q["relevant"], rows)
        line = f"{q['qid']:<4} {q['query'][:33]:<34}{len(relevant):>4}"
        for m, rank in METRICS.items():
            ranked = [index.docs[d][0] for _, d in rank(index, tokenize(q["query"]), DEPTH)]
            p10 = sum(d in relevant for d in ranked[:10]) / 10
            r100 = sum(d in relevant for d in ranked) / len(relevant) if relevant else 0.0
            ap_ = average_precision(ranked, relevant)
            for i, v in enumerate((p10, r100, ap_)):
                totals[m][i] += v
            line += f" | {p10:>11.2f} {r100:>6.2f} {ap_:>6.2f}"
            errors.append((q["qid"], m, [names[d] for d in ranked[:10] if d not in relevant]))
        print(line)
    print("-" * len(header))
    line = f"{'mean (MAP)':<39}"
    for m in METRICS:
        p10, r100, map_ = (v / len(queries) for v in totals[m])
        line += f" | {p10:>11.2f} {r100:>6.2f} {map_:>6.2f}"
    print(line)

    if args.errors:
        print("\nnon-relevant documents in the top 10:")
        for qid, m, wrong in errors:
            print(f"  {qid} {m:<6} {', '.join(wrong) or '-'}")


if __name__ == "__main__":
    main()
