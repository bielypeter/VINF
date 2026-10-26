"""HTML -> text lines with regex only.

The pages' CSS classes are generated hashes (sc-gvLdPU) that change between
deploys, so nothing here looks at classes: inline tags are removed, every
other tag ends a line, and the extractors then match labels in the text
("Born", "Draft", ...).
"""
import html
import re
import unicodedata

MAIN_RE = re.compile(r"<main\b.*?</main>", re.S | re.I)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
DROP_RE = re.compile(r"<(script|style|noscript|svg|template)\b.*?</\1\s*>|<!--.*?-->", re.S | re.I)
# Tags that do not break a line: "Josh<span>&nbsp;</span>Anderson" stays one line.
INLINE_RE = re.compile(r"</?(?:a|span|b|i|em|strong|small|sup|sub|abbr|img|label|u)\b[^>]*>", re.I)
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"[ \t\r\f\v  ​]+")


def main_block(page):
    """The <main> element, or the whole page when it has none."""
    m = MAIN_RE.search(page)
    return m.group(0) if m else page


def title(page):
    m = TITLE_RE.search(page)
    return clean(m.group(1)) if m else ""


def clean(fragment):
    """Text of an HTML fragment on one line."""
    text = html.unescape(TAG_RE.sub(" ", INLINE_RE.sub("", DROP_RE.sub(" ", fragment))))
    return SPACE_RE.sub(" ", text).strip()


def html_to_lines(fragment):
    """Visible text, one line per block element, without empty lines."""
    text = INLINE_RE.sub("", DROP_RE.sub("\n", fragment))
    text = html.unescape(TAG_RE.sub("\n", text))
    lines = (SPACE_RE.sub(" ", line).strip() for line in text.split("\n"))
    return [line for line in lines if line]


def value_after(lines, label_re, start=0, end=None):
    """The line after the first line matching label_re (a compiled regex)."""
    end = len(lines) if end is None else end
    for i in range(start, min(end, len(lines) - 1)):
        if label_re.fullmatch(lines[i]):
            return lines[i + 1]
    return None


def index_of(lines, line_re, start=0):
    for i in range(start, len(lines)):
        if line_re.fullmatch(lines[i]):
            return i
    return -1


def fold_diacritics(text):
    """'Slafkovský' -> 'Slafkovsky', 'Montréal' -> 'Montreal'."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def one_line(value):
    """A cell value for TSV: no tabs or newlines."""
    if value is None:
        return ""
    return SPACE_RE.sub(" ", re.sub(r"[\t\r\n]+", " ", str(value))).strip()
