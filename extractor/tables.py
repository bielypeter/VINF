"""Generic HTML table parsing with regex: header cells + rows of cell texts."""
import re

from .text import clean

TABLE_RE = re.compile(r"<table\b[^>]*>(.*?)</table>", re.S | re.I)
TR_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S | re.I)
# th and td in document order: rows use <th> for row headers (season, team)
CELL_RE = re.compile(r"<(th|td)\b[^>]*>(.*?)</\1>", re.S | re.I)


def tables(page):
    """[(header, rows)] for every table. header is the first row made only of
    <th> cells; rows are the other rows as lists of cell texts."""
    result = []
    for m in TABLE_RE.finditer(page):
        header, rows = [], []
        for tr in TR_RE.findall(m.group(1)):
            cells = CELL_RE.findall(tr)
            if not cells:
                continue
            texts = [clean(text) for _, text in cells]
            if not header and all(tag.lower() == "th" for tag, _ in cells):
                header = texts
            else:
                rows.append(texts)
        result.append((header, rows))
    return result


def find_table(page, first_columns):
    """The first table whose header starts with first_columns, e.g. ("Season", "Team")."""
    n = len(first_columns)
    for header, rows in tables(page):
        if tuple(header[:n]) == tuple(first_columns):
            return header, rows
    return None, []
