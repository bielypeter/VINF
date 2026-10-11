"""Append-only storage of crawled pages.

Every download is written to a new timestamped file and never overwritten
(course rule: never delete anything). manifest.tsv lists every saved page and
is loaded into memory when needed; crawl_log.tsv records every attempt.
"""
import hashlib
import time

from .config import DATA_DIR, LOG_FILE, MANIFEST_FILE, RAW_DIR

LOG_COLUMNS = ["timestamp", "status", "page_type", "key", "url", "final_url",
               "bytes", "render_s", "file", "error"]
MANIFEST_COLUMNS = ["ts", "key", "page_type", "status", "url", "final_url",
                    "http_status", "bytes", "sha1", "render_s", "file"]
TS_FORMAT = "%Y-%m-%dT%H-%M-%S"  # no ':' so it is a valid Windows file name


def page_dir(page_type, info):
    if page_type == "teams":
        return RAW_DIR / "teams"
    if page_type == "roster":
        return RAW_DIR / "rosters" / info["team"]
    if page_type == "player":
        return RAW_DIR / "players" / info["id"] / info["sub"]
    if page_type == "statlist":
        return RAW_DIR / "statlists" / info["kind"] / f"page-{info['page']:03d}"
    if page_type == "sitemap":
        return RAW_DIR / "sitemap"
    if page_type == "coaches":
        return RAW_DIR / "coaches" / info["team"] / info["path"].replace("/", "__")
    raise ValueError(page_type)


def save_html(page_type, info, html, ts=None):
    """Write a new version of a page; returns (path, ts, sha1, bytes).

    Files are opened in exclusive mode, so an existing file is never overwritten;
    two saves in the same second get <ts>.html and <ts>-1.html.
    """
    ts = ts or time.strftime(TS_FORMAT)
    data = html.encode("utf-8")
    folder = page_dir(page_type, info)
    folder.mkdir(parents=True, exist_ok=True)
    ext = ".xml" if page_type == "sitemap" else ".html"
    n = 0
    while True:
        path = folder / (f"{ts}{ext}" if n == 0 else f"{ts}-{n}{ext}")
        try:
            with path.open("xb") as f:
                f.write(data)
            return path, ts, hashlib.sha1(data).hexdigest(), len(data)
        except FileExistsError:
            n += 1


def _append_tsv(file, columns, fields):
    file.parent.mkdir(parents=True, exist_ok=True)
    new = not file.exists()
    row = [str(fields.get(c, "")).replace("\t", " ").replace("\n", " ") for c in columns]
    with file.open("a", encoding="utf-8") as f:
        if new:
            f.write("\t".join(columns) + "\n")
        f.write("\t".join(row) + "\n")


def log(**fields):
    fields.setdefault("timestamp", time.strftime("%Y-%m-%dT%H:%M:%S"))
    _append_tsv(LOG_FILE, LOG_COLUMNS, fields)


def append_manifest(**fields):
    _append_tsv(MANIFEST_FILE, MANIFEST_COLUMNS, fields)


def load_manifest():
    """Return ({key: latest row}, {key: [rows oldest first]}) from manifest.tsv."""
    latest, history = {}, {}
    if not MANIFEST_FILE.exists():
        return latest, history
    with MANIFEST_FILE.open(encoding="utf-8") as f:
        header = f.readline().rstrip("\n").split("\t")
        for line in f:
            row = dict(zip(header, line.rstrip("\n").split("\t")))
            history.setdefault(row["key"], []).append(row)
            latest[row["key"]] = row  # rows are appended in time order
    return latest, history


def read_saved(row):
    """HTML of a page listed in the manifest."""
    return (DATA_DIR / row["file"]).read_text(encoding="utf-8")
