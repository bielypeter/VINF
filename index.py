"""Build the inverted index from the extracted documents.

    python extract.py   # first: data/ -> out/extracted/*.tsv
    python index.py     # out/extracted/{players,coaches}.tsv -> out/index/*.tsv

Each row of players.tsv and coaches.tsv is one document.
"""
import time

from search.indexer import EXTRACTED_DIR, INDEX_DIR, Index, documents


def main():
    start = time.time()
    index = Index.build(documents())
    index.save(sources="players.tsv, coaches.tsv")
    types = {}
    for _, kind, _ in index.docs:
        types[kind] = types.get(kind, 0) + 1
    postings = sum(df for df, _ in index.postings.values())
    print(f"documents: {index.n_docs} ({', '.join(f'{k}={n}' for k, n in types.items())})")
    print(f"terms: {len(index.postings)}   postings: {postings}   avg doc length: {index.avgdl:.1f} tokens")
    print(f"read {EXTRACTED_DIR}, written to {INDEX_DIR} in {time.time() - start:.1f}s")


if __name__ == "__main__":
    main()
