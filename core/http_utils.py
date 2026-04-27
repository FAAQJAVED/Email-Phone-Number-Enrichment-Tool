"""
core.http_utils — Lightweight HTTP fetching and Pass 1 enrichment.

All network calls go through ``fetch_url``, which enforces a hard
wall-clock timeout via a daemon thread (not just a socket timeout).
The daemon thread is abandoned — not killed — once the limit expires;
because it is a daemon it will not prevent process exit.

Public API
----------
fetch_url(url, cfg, wall_clock_limit)  — GET a URL, return HTML or None.
enrich_one_http(target, cfg)           — Pass 1: scrape email + phone via requests.
"""

from __future__ import annotations

import random
import re
import threading
import time
from typing import List, Optional, Tuple

import requests
import urllib3

from core.email_utils import (
    extract_emails_full,
    extract_phones,
    score_email,
    best_email,
)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ── User-agent helpers ─────────────────────────────────────────────────────────

def random_ua(cfg: dict) -> str:
    """Pick a random User-Agent string from the configured pool."""
    pool = cfg.get("user_agents", [])
    return random.choice(pool) if pool else "Mozilla/5.0"


def _rate_limit(cfg: dict) -> None:
    """Sleep for a random duration within the configured [min, max] range."""
    rl  = cfg.get("rate_limit", {})
    lo  = float(rl.get("min_seconds", 0.0))
    hi  = float(rl.get("max_seconds", 0.3))
    if hi > 0:
        time.sleep(random.uniform(lo, hi))


# ── Single-URL fetch with hard wall-clock timeout ─────────────────────────────

def _fetch_worker(url: str, ua: str, timeout: tuple, result: list) -> None:
    """
    Daemon-thread target: GET a single URL and append the response HTML
    to *result*.  Any exception is silently swallowed — the caller checks
    whether *result* is empty.
    """
    try:
        headers = {
            "User-Agent":      ua,
            "Accept":          "text/html,*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        r = requests.get(
            url,
            headers=headers,
            timeout=timeout,
            verify=False,
            allow_redirects=True,
        )
        if r.status_code < 400:
            result.append(r.text)
    except Exception:
        pass


def fetch_url(
    url: str,
    cfg: dict,
    wall_clock_limit: int = 10,
) -> Optional[str]:
    """
    Fetch *url* and return the response HTML, or ``None`` on failure/timeout.

    A daemon thread performs the actual network call so a truly stuck
    connection (e.g. a server that accepts but never responds) cannot
    block the main loop indefinitely regardless of the socket-level timeout.

    Parameters
    ----------
    url             : Fully-qualified URL to fetch.
    cfg             : Config dict — reads ``http_timeout`` and ``user_agents``.
    wall_clock_limit: Maximum seconds to wait for the thread (default 10).

    Returns
    -------
    HTML string, or ``None`` if the request failed, timed out, or returned
    an HTTP 4xx/5xx status.
    """
    result: list = []
    t = threading.Thread(
        target=_fetch_worker,
        args=(url, random_ua(cfg), tuple(cfg.get("http_timeout", [4, 6])), result),
        daemon=True,
    )
    t.start()
    try:
        t.join(timeout=wall_clock_limit)
    except KeyboardInterrupt:
        return None
    return result[0] if result else None


# ── Pass 1: HTTP-only enrichment ───────────────────────────────────────────────

def enrich_one_http(target: dict, cfg: dict) -> Tuple[str, str]:
    """
    Pass 1: attempt to find a contact email **and** phone via plain HTTP GET.

    Visit sequence
    --------------
    1. Homepage (``target["website"]``).
    2. Each path in ``cfg["contact_paths"]`` in order.

    Early exit: stops fetching additional pages as soon as a high-quality
    email (score ≤ 2) is found — personal names and top-tier generics are
    good enough; no need to keep visiting pages.

    Rate limiting and UA rotation are applied on every request.

    Parameters
    ----------
    target : Dict with keys ``"website"``, ``"name"``, ``"category"``, ``"phone"``.
    cfg    : Full config dict.

    Returns
    -------
    ``(best_email_str, best_phone_str)`` — either may be ``""``.
    """
    base          = target["website"].rstrip("/")
    contact_paths = cfg.get("contact_paths", ["/contact", "/about"])
    emails: List[str] = []
    phones: List[str] = []

    # ── Homepage ──────────────────────────────────────────────────
    html = fetch_url(base, cfg)
    if html:
        emails.extend(extract_emails_full(html))
        phones.extend(extract_phones(html))
    _rate_limit(cfg)

    # Early exit if a top-quality email is already found
    if any(score_email(e, cfg) <= 2 for e in emails):
        return best_email(emails, cfg), phones[0] if phones else ""

    # ── Contact / about sub-pages ─────────────────────────────────
    for path in contact_paths:
        html = fetch_url(base + path, cfg)
        if html:
            found_emails = extract_emails_full(html)
            found_phones = extract_phones(html)
            emails.extend(found_emails)
            phones.extend(found_phones)
            if any(score_email(e, cfg) <= 2 for e in found_emails):
                break
        _rate_limit(cfg)

    return best_email(emails, cfg), phones[0] if phones else ""
