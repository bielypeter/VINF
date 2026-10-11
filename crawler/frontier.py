"""URL frontier: FIFO queue + visited set, persisted to JSON so a crawl can resume."""
import json
from collections import deque

from .urls import key


class Frontier:
    def __init__(self, state_file):
        self.state_file = state_file
        self.queue = deque()
        self.seen = set()  # keys that are queued or done
        self.done = set()  # keys fetched successfully or permanently failed
        self.retries = {}  # key -> attempts so far

    def add(self, url, front=False):
        k = key(url)
        if k in self.seen:
            return False
        self.seen.add(k)
        if front:
            self.queue.appendleft(url)
        else:
            self.queue.append(url)
        return True

    def pop(self):
        return self.queue.popleft() if self.queue else None

    def mark_done(self, *urls):
        for url in urls:
            k = key(url)
            self.seen.add(k)
            self.done.add(k)

    def requeue(self, url):
        k = key(url)
        self.retries[k] = self.retries.get(k, 0) + 1
        self.queue.append(url)
        return self.retries[k]

    def __len__(self):
        return len(self.queue)

    def save(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps({
            "queue": list(self.queue),
            "seen": sorted(self.seen),
            "done": sorted(self.done),
            "retries": self.retries,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.state_file)

    def load(self, old_state_file=None):
        if old_state_file and old_state_file.exists() and not self.state_file.exists():
            old_state_file.rename(self.state_file)
        if not self.state_file.exists():
            return False
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.queue = deque(state["queue"])
        self.seen = set(state["seen"])
        self.done = set(state["done"])
        self.retries = state.get("retries", {})
        return True
