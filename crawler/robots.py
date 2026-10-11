"""Minimal robots.txt parser with '*' and '$' wildcard support.

urllib.robotparser treats '*' inside paths literally, so rules like
'Disallow: /_*' from nhl.com would never match.
"""
import re
import urllib.request


class Robots:
    def __init__(self, rules=(), crawl_delay=None):
        self.rules = list(rules)  # (allow: bool, compiled regex, pattern length)
        self.crawl_delay = crawl_delay

    @classmethod
    def fetch(cls, url, agent, user_agent, timeout=15):
        req = urllib.request.Request(url, headers={"User-Agent": user_agent})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8", "replace")
        except Exception as e:  # unreachable robots.txt -> allow everything
            print(f"[robots] could not fetch {url}: {e}")
            return cls()
        return cls.parse(text, agent)

    @classmethod
    def parse(cls, text, agent):
        groups = {}  # user-agent token -> list of (field, value)
        current, last_was_ua = [], False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            m = re.match(r"^([A-Za-z-]+)\s*:\s*(.*)$", line)
            if not m:
                continue
            field, value = m.group(1).lower(), m.group(2).strip()
            if field == "user-agent":
                if not last_was_ua:
                    current = []
                groups.setdefault(value.lower(), current)
                last_was_ua = True
            else:
                last_was_ua = False
                current.append((field, value))

        lines = groups.get(agent.lower(), groups.get("*", []))
        rules, delay = [], None
        for field, value in lines:
            if field in ("allow", "disallow") and value:
                pattern = re.escape(value).replace(r"\*", ".*")
                if pattern.endswith(r"\$"):
                    pattern = pattern[:-2] + "$"
                rules.append((field == "allow", re.compile(pattern), len(value)))
            elif field == "crawl-delay":
                try:
                    delay = float(value)
                except ValueError:
                    pass
        return cls(rules, delay)

    def allowed(self, path):
        """Longest matching rule wins; Allow wins a tie."""
        best = None
        for allow, regex, length in self.rules:
            if regex.match(path):
                if best is None or length > best[1] or (length == best[1] and allow):
                    best = (allow, length)
        return True if best is None else best[0]
