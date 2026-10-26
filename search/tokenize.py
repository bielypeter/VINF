"""The same tokenizer for documents and queries."""
import re

from extractor.text import fold_diacritics

TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset("""
a an and are as at be been but by for from had has have he her his i in into is it its
of on or our she that the their them they this to was were which who will with
""".split())


def tokenize(text):
    """'Košice, Slovakia' -> ['kosice', 'slovakia']: lowercase, no diacritics, no stopwords."""
    return [t for t in TOKEN_RE.findall(fold_diacritics(text or "").lower()) if t not in STOPWORDS]
