"""Two ways to compute idf, and the two rankings that use them.

  classic idf       log(N / df)                      -> TF-IDF with cosine similarity
  probabilistic idf log((N - df + 0.5) / (df + 0.5) + 1)  -> BM25

The classic idf is 0 for a term in every document; the probabilistic one
(Robertson-Sparck Jones, with +1 so it never goes negative) weights rare terms
more strongly and common terms less.
"""
import math
from collections import Counter, defaultdict

BM25_K1 = 1.2
BM25_B = 0.75


def idf_classic(df, n):
    return math.log(n / df)


def idf_probabilistic(df, n):
    return math.log((n - df + 0.5) / (df + 0.5) + 1)


def tf_weight(tf):
    """Sublinear tf: the 10th 'Gretzky' adds less than the 2nd."""
    return 1 + math.log(tf)


def doc_norms(postings, n_docs):
    """|d| of every document's TF-IDF vector, for cosine similarity."""
    squares = defaultdict(float)
    for df, plist in postings.values():
        idf = idf_classic(df, n_docs)
        for doc, tf in plist:
            squares[doc] += (tf_weight(tf) * idf) ** 2
    return {doc: math.sqrt(s) for doc, s in squares.items()}


def tfidf_cosine(index, terms, k=10):
    """[(score, doc)] by cosine of the query and document TF-IDF vectors."""
    n = index.n_docs
    scores = defaultdict(float)
    q_norm = 0.0
    for term, qtf in Counter(terms).items():
        if term not in index.postings:
            continue
        df, plist = index.postings[term]
        idf = idf_classic(df, n)
        wq = tf_weight(qtf) * idf
        q_norm += wq * wq
        for doc, tf in plist:
            scores[doc] += wq * tf_weight(tf) * idf
    if not scores or q_norm == 0:
        return []
    q_norm = math.sqrt(q_norm)
    ranked = ((s / (index.norms[d] * q_norm), d) for d, s in scores.items() if index.norms[d])
    return sorted(ranked, reverse=True)[:k]


def bm25(index, terms, k=10, k1=BM25_K1, b=BM25_B):
    """[(score, doc)] by Okapi BM25."""
    n, avgdl = index.n_docs, index.avgdl
    scores = defaultdict(float)
    for term in set(terms):
        if term not in index.postings:
            continue
        df, plist = index.postings[term]
        idf = idf_probabilistic(df, n)
        for doc, tf in plist:
            dl = index.lengths[doc]
            scores[doc] += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avgdl))
    return sorted(((s, d) for d, s in scores.items()), reverse=True)[:k]


METRICS = {"tfidf": tfidf_cosine, "bm25": bm25}
