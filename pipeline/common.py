"""Paths, seasons and a polite HTTP client shared by the fetch scripts."""
import gzip
import json
import random
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"
OUT = DATA / "out"
SEASONS = (2025, 2026)
UA = "release-point research script (personal, non-commercial)"


class RateLimiter:
    """At most `rate` requests per second across all threads (a simple spaced schedule)."""

    def __init__(self, rate):
        self.gap = 1.0 / rate
        self.lock = threading.Lock()
        self.next = time.monotonic()

    def wait(self):
        with self.lock:
            now = time.monotonic()
            slot = max(now, self.next)
            self.next = slot + self.gap
        time.sleep(max(0.0, slot - now))


def get(url, limiter=None, tries=8, timeout=120, accept="application/json"):
    """GET with gzip, retries and backoff. Honors Retry-After on 429. Returns the decoded body as bytes."""
    for i in range(tries):
        if limiter:
            limiter.wait()
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return body
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise
            wait = float(e.headers.get("Retry-After") or 0) or min(120, 2 ** i + random.random())
            print(f"  HTTP {e.code}, retry {i + 1}/{tries} in {wait:.0f}s: {url[:120]}", flush=True)
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            wait = min(120, 2 ** i + random.random())
            print(f"  {type(e).__name__}, retry {i + 1}/{tries} in {wait:.0f}s: {url[:120]}", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"failed after {tries} tries: {url}")


def get_json(url, limiter=None, **kw):
    return json.loads(get(url, limiter, **kw))


def write_atomic(path, data: bytes):
    """Write to a temporary name and rename, so an interrupted run never leaves a partial file behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)
