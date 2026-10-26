"""Search the index with TF-IDF cosine and/or BM25.

    python search.py "slovak left wing"              # both rankings side by side
    python search.py "conn smythe" --metric bm25 -k 20
    python search.py                                 # interactive, empty line quits
"""
import argparse

from search.indexer import Index
from search.rank import METRICS
from search.tokenize import tokenize


def results(index, query, metric, k):
    return [(score, *index.docs[doc]) for score, doc in METRICS[metric](index, tokenize(query), k)]


def show(index, query, metric, k):
    print(f"query: {query!r}   tokens: {tokenize(query)}")
    metrics = list(METRICS) if metric == "both" else [metric]
    columns = [results(index, query, m, k) for m in metrics]
    width = 46
    print("     " + "".join(f"{m.upper():<{width}}" for m in metrics))
    for i in range(max(map(len, columns), default=0)):
        cells = []
        for col in columns:
            if i < len(col):
                score, doc_id, kind, name = col[i]
                cells.append(f"{score:7.3f}  {name[:26]:<26} {kind[0]}".ljust(width))
            else:
                cells.append(" " * width)
        print(f"{i + 1:>3}  " + "".join(cells))
    if not any(columns):
        print("  no results")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("query", nargs="?", help="search text; without it, ask in a loop")
    ap.add_argument("--metric", choices=[*METRICS, "both"], default="both")
    ap.add_argument("-k", type=int, default=10, help="results per ranking")
    args = ap.parse_args()
    index = Index.load()
    if args.query:
        show(index, args.query, args.metric, args.k)
        return
    while True:
        try:
            query = input("\nsearch> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not query:
            break
        show(index, query, args.metric, args.k)


if __name__ == "__main__":
    main()
