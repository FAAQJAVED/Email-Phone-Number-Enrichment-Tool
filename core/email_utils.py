"""
core.email_utils — Email and phone extraction, decoding, and scoring.

Public API
----------
extract_emails_raw(html)              — regex-only email extraction.
decode_cloudflare_email(encoded)      — decode a Cloudflare XOR-encoded hex string.
extract_emails_full(html)             — regex + Cloudflare decoding combined.
extract_phones(html)                  — phone number extraction (tel: hrefs + regex).
score_email(email, cfg)               — quality score: 1=personal, 2=priority-generic,
                                        3=generic, 999=junk/skip.
best_email(emails, cfg)               — pick the single best email from a list.
"""

from __future__ import annotations

import re
from typing import List, Set


# ── Raw regex extraction ───────────────────────────────────────────────────────

def extract_emails_raw(html: str) -> List[str]:
    """
    Extract plaintext email addresses from HTML using a permissive regex.

    False-positive reduction:
      - Strip leading/trailing punctuation.
      - Reject addresses that contain asset-file extensions (.png, .js, …).
      - Reject addresses longer than 80 characters.
      - Validate final structure with a stricter pattern.

    Returns a deduplicated list of lowercased email strings.
    """
    raw = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", html)
    result: List[str] = []
    for e in raw:
        e = e.lower().strip().strip('.,;"\'')
        if not re.match(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$", e):
            continue
        if any(ext in e for ext in [".png", ".jpg", ".svg", ".gif", ".css", ".js"]):
            continue
        if len(e) > 80:
            continue
        result.append(e)
    return list(set(result))


# ── Cloudflare email-protection decoding ──────────────────────────────────────

def decode_cloudflare_email(encoded: str) -> str:
    """
    Decode a Cloudflare email-protection hex string.

    Cloudflare's cdn-cgi email-protection scheme XORs every byte of the
    plaintext email against the first byte of the ciphertext (the key),
    then hex-encodes the entire result (key byte first).

    Parameters
    ----------
    encoded : Hex string, e.g. ``"1a727f7676755a7f627b776a767f34797577"``

    Returns
    -------
    Decoded email string, or ``""`` if decoding fails.

    Example
    -------
    >>> decode_cloudflare_email("1a727f7676755a7f627b776a767f34797577")
    'hello@example.com'
    """
    try:
        enc = bytes.fromhex(encoded)
        key = enc[0]
        return "".join(chr(b ^ key) for b in enc[1:])
    except Exception:
        return ""


# ── Combined extraction (regex + Cloudflare) ──────────────────────────────────

def extract_emails_full(html: str) -> List[str]:
    """
    Extract all email addresses from HTML, including Cloudflare-obfuscated ones.

    Two Cloudflare patterns are handled:
      1. ``/cdn-cgi/l/email-protection#<hex>``   (href-based)
      2. ``data-cfemail="<hex>"``                 (attribute-based)

    Returns a deduplicated list of lowercased email strings.
    """
    emails = extract_emails_raw(html)

    cloudflare_patterns = (
        r"/cdn-cgi/l/email-protection#([a-f0-9]+)",
        r'data-cfemail="([a-f0-9]+)"',
    )
    for pattern in cloudflare_patterns:
        for m in re.finditer(pattern, html):
            decoded = decode_cloudflare_email(m.group(1))
            if "@" in decoded:
                emails.append(decoded.lower().strip())

    return list(set(emails))


# ── Phone number extraction ────────────────────────────────────────────────────

def extract_phones(html: str) -> List[str]:
    """
    Extract phone numbers from HTML.

    Strategy (priority order):
      1. ``tel:`` href attributes — highest confidence, very low false-positive rate.
         Example: ``<a href="tel:+441234567890">``
      2. Regex pattern matching — broader sweep filtered by digit count (7–15).
         Three sub-patterns cover international, bracketed, and plain formats.

    Returns a deduplicated list of raw phone strings ordered most-reliable first.
    Digit sequences are deduplicated (same number expressed differently appears once).
    """
    seen_digits: Set[str] = set()
    phones: List[str] = []

    def _add(raw: str) -> None:
        raw = raw.strip()
        digits = re.sub(r"\D", "", raw)
        if 7 <= len(digits) <= 15 and digits not in seen_digits:
            seen_digits.add(digits)
            phones.append(raw)

    # 1. tel: href links — best source
    for m in re.finditer(r'href=["\'`]tel:([^"\'`]{4,25})["\'`]', html, re.I):
        _add(m.group(1).replace("%20", " "))

    # 2. Regex fallback when no tel: links are present
    if not phones:
        patterns = [
            # International: +44 20 7123 4567, +1-800-555-5555
            r"\+\d{1,3}[\s\-\.]?\(?\d{1,4}\)?[\s\-\.]?\d{3,4}[\s\-\.]?\d{3,4}",
            # Bracketed area code: (020) 7123 4567
            r"\(\d{2,5}\)[\s\-\.]?\d{3,4}[\s\-\.]?\d{3,4}",
            # Plain runs with separators: 020 7123 4567, 555-555-5555
            r"\b\d{3,5}[\s\-\.]\d{3,4}[\s\-\.]\d{3,4}\b",
        ]
        for pat in patterns:
            for m in re.finditer(pat, html):
                _add(m.group(0))

    return phones


# ── Email scoring ──────────────────────────────────────────────────────────────

def score_email(email: str, cfg: dict) -> int:
    """
    Score an email address by contact quality. **Lower score = better.**

    Score   Meaning
    -----   -------
      1     Personal name address  (e.g. john.smith@company.com)  — most valuable
      2     High-priority generic  (info@, hello@, contact@, enquiries@, enquiry@)
      3     Other generic          (support@, accounts@, sales@, manager@, …)
    999     Junk / skip-list       — filtered out entirely

    Junk detection:
      - Local part contains any ``skip_email_keywords`` entry.
      - Domain contains any ``junk_email_domains`` entry.

    Parameters
    ----------
    email : Email address to score.
    cfg   : Config dict (keys: skip_email_keywords, generic_email_keywords,
            junk_email_domains).

    Returns
    -------
    Integer score (1, 2, 3, or 999).
    """
    if not email or "@" not in email:
        return 999

    parts  = email.lower().split("@", 1)
    local  = parts[0]
    domain = parts[1]

    skip_kws     = set(cfg.get("skip_email_keywords",   []))
    generic_kws  = set(cfg.get("generic_email_keywords", []))
    junk_domains = set(cfg.get("junk_email_domains",     []))

    if any(k in local  for k in skip_kws):     return 999
    if any(j in domain for j in junk_domains): return 999
    if not any(k in local for k in generic_kws): return 1   # personal name
    if local in {"info", "hello", "contact", "enquiries", "enquiry"}: return 2
    return 3


# ── Best email selector ────────────────────────────────────────────────────────

def best_email(emails: List[str], cfg: dict) -> str:
    """
    Return the single highest-quality email from a list.

    Emails scored 999 (junk/skip) are excluded entirely.
    Among the remaining candidates the one with the lowest score is returned.
    Ties are broken arbitrarily (first encountered after sorting by score).

    Returns ``""`` if the list is empty or all candidates are junk.
    """
    scored = [
        (e.lower().strip(), score_email(e, cfg))
        for e in emails
        if e and "@" in e
    ]
    valid = [(e, s) for e, s in scored if s < 999]
    if not valid:
        return ""
    return min(valid, key=lambda x: x[1])[0]
