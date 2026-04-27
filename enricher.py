"""
Email & Phone Enrichment Tool
==============================
Reads any CSV that contains a website/URL column and scrapes each site
for contact email addresses AND phone numbers using two sequential passes:

  Pass 1 — Fast HTTP GET  (homepage + configured contact paths, no browser)
  Pass 2 — Playwright     (headless Chromium fallback for JS-rendered sites)

Results are written to an Excel workbook (+ CSV backup) with a Run Stats sheet.
Progress is checkpointed so any interrupted run can be resumed.
Auto-saves every N sites AND every 60 seconds in a background thread.

Column detection is fully automatic — no need to rename CSV headers.
Input file detection is automatic — no need to rename your file.

Usage
-----
  python enricher.py                          # auto-detects CSV in current dir
  python enricher.py --input my_leads.csv
  python enricher.py --input leads.csv --config my_config.yaml
  python enricher.py --fresh                  # clear checkpoint and restart
  python enricher.py --output results.xlsx

Runtime controls (while running)
---------------------------------
  P  — pause / resume
  R  — resume
  Q  — quit (saves progress first)
  S  — print current status
  Windows: single-key (no Enter needed)
  Mac/Linux: type the letter then press Enter

Requirements
------------
  pip install -r requirements.txt
  python -m playwright install chromium
"""

from __future__ import annotations

import argparse
import csv
import os
import platform
import time
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import yaml

# ── tqdm shim — graceful fallback when not installed ─────────────────────────
try:
    from tqdm import tqdm as _TqdmClass
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

    class _TqdmClass:               # type: ignore[no-redef]
        """Minimal no-op shim used when tqdm is not installed."""
        def __init__(self, *a, **kw) -> None:
            self.total = kw.get("total", 0)
            self.n     = 0
        def update(self, n: int = 1) -> None:   self.n += n
        def set_postfix(self, **kw) -> None:    pass
        def write(self, s: str) -> None:        print(s, flush=True)
        def close(self) -> None:                pass
        def __enter__(self):                    return self
        def __exit__(self, *a) -> None:         pass

# ── Core modules ──────────────────────────────────────────────────────────────
from core._log import elapsed, log, set_active_bar, set_start_time
from core.controls import (
    AutoSaver,
    ControlListener,
    State,
    check_cmd_file,
    check_disk,
    should_stop,
    wait_for_internet,
    wait_if_paused,
)
from core.http_utils import enrich_one_http
from core.storage import (
    get_output_path,
    load_checkpoint,
    load_existing_output,
    save_checkpoint,
    save_output,
)


# ===========================================================================
# Configuration
# ===========================================================================

DEFAULT_CONFIG: dict = {
    # ── Input / Output ───────────────────────────────────────────
    "input_file":            "",
    "output_file":           "",
    "checkpoint_file":       "enrich_checkpoint.json",
    "command_file":          "command.txt",
    "output_format":         "xlsx",   # "xlsx" or "csv"

    # ── Timing & Performance ─────────────────────────────────────
    "http_timeout":          [4, 6],
    "playwright_timeout":    8000,
    "browser_restart_every": 150,
    "stop_at":               "23:00",
    "autosave_interval":     60,       # background save every N seconds

    # ── Rate Limiting ────────────────────────────────────────────
    "rate_limit": {
        "min_seconds": 0.1,
        "max_seconds": 0.5,
    },

    # ── User-Agent Rotation ──────────────────────────────────────
    "user_agents": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.0; rv:109.0) Gecko/20100101 Firefox/120.0",
    ],

    # ── Scraping Behaviour ───────────────────────────────────────
    "contact_paths": [
        "/contact", "/contact-us", "/about", "/about-us",
    ],
    "locale": "en-US",

    # ── Column Names ─────────────────────────────────────────────
    "columns": {
        "company_name": "",       # auto-detect
        "website":      "",       # auto-detect
        "email":        "Email",
        "phone":        "Phone",
        "category":     "",       # auto-detect (optional)
    },

    # ── Email Filtering ──────────────────────────────────────────
    "skip_email_keywords": [
        "noreply", "no-reply", "donotreply", "privacy", "dataprotection",
        "data-protection", "gdpr", "unsubscribe", "postmaster", "webmaster",
        "bounce", "complaints", "legal", "abuse", "spam", "newsletter",
    ],
    "generic_email_keywords": [
        "info", "admin", "hello", "contact", "enquiries", "enquiry", "office",
        "mail", "email", "team", "support", "help", "sales", "lettings",
        "letting", "property", "management", "manager", "reception",
        "accounts", "finance", "general", "service", "post",
    ],
    "junk_email_domains": [
        "sentry.io", "wixpress.com", "example.com", "schema.org", "w3.org",
        "googleapis.com", "cloudflare.com", "jquery.com",
    ],

    # ── Cookie Banner Dismissal ──────────────────────────────────
    "cookie_selectors": [
        'button:has-text("Accept all")',    'button:has-text("Accept All")',
        'button:has-text("Accept cookies")', 'button:has-text("Accept")',
        'button:has-text("I Accept")',      'button:has-text("Allow all")',
        'button:has-text("OK")',            'button:has-text("Got it")',
        '[id*="accept"]',                   '[aria-label*="Accept"]',
    ],
}


def load_config(config_path: Optional[str] = None) -> dict:
    """
    Load configuration from a YAML file merged on top of hard-coded defaults.

    Nested dicts (e.g. ``rate_limit``, ``columns``) are shallow-merged so
    partial YAML overrides do not wipe unmentioned sub-keys.
    """
    cfg = {k: (v.copy() if isinstance(v, dict) else v) for k, v in DEFAULT_CONFIG.items()}
    if config_path and os.path.exists(config_path):
        with open(config_path, encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        for key, val in user_cfg.items():
            if isinstance(val, dict) and isinstance(cfg.get(key), dict):
                cfg[key].update(val)
            else:
                cfg[key] = val
    return cfg


# ===========================================================================
# Input loading / column detection
# ===========================================================================

def _detect_column(headers: List[str], *keywords: str) -> Optional[str]:
    """Return the first header containing any keyword (case-insensitive)."""
    for h in headers:
        h_lower = h.lower()
        if any(kw in h_lower for kw in keywords):
            return h
    return None


def find_input_file() -> Optional[str]:
    """
    Auto-detect the input CSV from the current working directory.

    - Exactly one CSV → use it automatically.
    - Multiple CSVs   → prompt the user to choose.
    - None found      → return ``None``.
    """
    csv_files = sorted(Path(".").glob("*.csv"))

    if not csv_files:
        return None

    if len(csv_files) == 1:
        return str(csv_files[0])

    print("\nMultiple CSV files found. Please choose one:")
    for i, f in enumerate(csv_files, 1):
        print(f"  {i}. {f.name}")
    print()
    while True:
        try:
            raw = input("Enter number (or full path to another file): ").strip()
            if raw.isdigit():
                idx = int(raw) - 1
                if 0 <= idx < len(csv_files):
                    return str(csv_files[idx])
            elif os.path.exists(raw):
                return raw
            print("  Invalid choice — try again.")
        except (EOFError, KeyboardInterrupt):
            return None


def load_input(cfg: dict) -> List[dict]:
    """
    Load and validate the input CSV with fully automatic column detection.

    Detection priority
    ------------------
    Website  (REQUIRED) : website · url · domain · site · web · link · homepage
    Company name (opt)  : company · name · organisation · organization · business
                          firm · client · account · brand · title
                          → falls back to the first column if nothing matches
    Category (opt)      : category · type · sector · industry · segment · group · vertical
    Phone (opt)         : phone · tel · mobile · cell · number · contact number

    Raises
    ------
    FileNotFoundError  — input file does not exist.
    ValueError         — file is empty, or no website column can be identified.

    Returns
    -------
    List of target dicts with keys: key, name, website, phone, category.
    """
    input_file = cfg["input_file"]
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")

    with open(input_file, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise ValueError("Input file is empty.")

    headers: List[str] = list(rows[0].keys())
    cols = cfg.get("columns", {})

    # ── Website column (required) ──────────────────────────────
    col_web = cols.get("website") or ""
    if not col_web or col_web not in headers:
        col_web = _detect_column(
            headers,
            "website", "url", "domain", "site", "web", "link", "homepage",
        )
    if not col_web:
        raise ValueError(
            f"Cannot find a website/URL column.\n"
            f"Columns found: {headers}\n"
            f"Please add a column named 'Website', 'URL', or 'Domain'."
        )

    # ── Company name (optional — falls back to first column) ───
    col_name = cols.get("company_name") or ""
    if not col_name or col_name not in headers:
        col_name = _detect_column(
            headers,
            "company", "name", "organisation", "organization",
            "business", "firm", "client", "account", "brand", "title",
        )
    if not col_name:
        col_name = headers[0]
        log(f"No company-name column detected — using first column: '{col_name}'", "warn")

    # ── Category (optional) ────────────────────────────────────
    col_cat = cols.get("category") or ""
    if not col_cat or col_cat not in headers:
        col_cat = _detect_column(
            headers,
            "category", "type", "sector", "industry",
            "segment", "group", "vertical",
        )

    # ── Pre-existing phone (optional) ──────────────────────────
    col_phone_in = _detect_column(
        headers,
        "phone", "tel", "mobile", "cell", "number", "contact number",
    )

    log(
        f"Columns → name='{col_name}'  website='{col_web}'"
        + (f"  category='{col_cat}'" if col_cat else "")
        + (f"  phone_in='{col_phone_in}'" if col_phone_in else "")
    )

    return [
        {
            "key":      row[col_name].strip().lower(),
            "name":     row[col_name].strip(),
            "website":  row[col_web].strip(),
            "phone":    row.get(col_phone_in, "").strip() if col_phone_in else "",
            "category": row.get(col_cat,      "").strip() if col_cat      else "",
        }
        for row in rows
        if row.get(col_web, "").strip()
    ]


# ===========================================================================
# Pass runners
# ===========================================================================

def run_pass1(
    targets:  List[dict],
    done:     Set[str],
    found:    dict,
    out_file: str,
    state:    State,
    ctx:      dict,
    cfg:      dict,
) -> List[dict]:
    """
    Execute Pass 1: fast HTTP enrichment for all targets not yet in ``found``.

    Behaviour
    ---------
    - Skips targets whose key is already in ``found`` (resume support).
    - Saves checkpoint + output every 10 sites.
    - Checks ``command.txt``, respects pause/stop, and checks internet
      connectivity every 3 consecutive failures.
    - Returns targets that yielded no contacts (queued for Pass 2).
    """
    todo     = [t for t in targets if t["key"] not in found]
    stop_at  = cfg.get("stop_at", "")
    ckpt     = cfg["checkpoint_file"]
    cmd_file = cfg["command_file"]

    log(
        f"Pass 1 — {len(todo)} sites → requests GET "
        f"(homepage + {len(cfg.get('contact_paths', []))} contact paths)"
    )

    if not todo:
        log("Pass 1: nothing to process")
        return []

    needs_pw:    List[dict] = []
    pass1_found: int        = 0
    fail_streak: int        = 0

    bar = _TqdmClass(
        total=len(todo),
        desc="  Pass 1 (HTTP)   ",
        unit="site",
        dynamic_ncols=True,
        colour="cyan" if TQDM_AVAILABLE else None,
    )
    set_active_bar(bar)

    try:
        for count, target in enumerate(todo, 1):
            check_cmd_file(state, cmd_file, ckpt)
            if should_stop(state, stop_at):
                break
            wait_if_paused(state, ctx, cmd_file, ckpt)
            if should_stop(state, stop_at):
                break

            email, phone = enrich_one_http(target, cfg)
            done.add(target["key"])
            ctx["done"] = len(done)

            if email or phone:
                found[target["key"]] = {
                    "name":     target["name"],
                    "website":  target["website"],
                    "email":    email,
                    "phone":    phone or target.get("phone", ""),
                    "category": target["category"],
                }
                pass1_found += 1
                ctx["found"]  = pass1_found
                fail_streak   = 0
            else:
                # Carry over any pre-existing phone from the input CSV
                if target.get("phone"):
                    found[target["key"]] = {
                        "name":     target["name"],
                        "website":  target["website"],
                        "email":    "",
                        "phone":    target["phone"],
                        "category": target["category"],
                    }
                    pass1_found += 1
                    ctx["found"] = pass1_found
                needs_pw.append(target)
                fail_streak += 1
                if fail_streak > 0 and fail_streak % 3 == 0:
                    wait_for_internet(state)
                    if should_stop(state, stop_at):
                        break
                    fail_streak = 0

            # Save every 10 sites
            if count % 10 == 0:
                save_checkpoint(done, found, ckpt)
                save_output(found, out_file, cfg)
                check_disk()

            pct   = round(pass1_found / count * 100)
            rem   = len(todo) - count
            eta   = int(rem * (time.time() - _start_time_ref()) / max(count, 1) / 60)
            eta_s = f"~{eta // 60}h{eta % 60:02d}m" if eta >= 60 else f"~{eta}m"
            bar.set_postfix(found=pass1_found, hit=f"{pct}%", eta=eta_s)
            bar.update(1)

    finally:
        set_active_bar(None)
        bar.close()

    print()
    save_checkpoint(done, found, ckpt)
    save_output(found, out_file, cfg)
    log(
        f"Pass 1 done — {pass1_found} contacts found, "
        f"{len(needs_pw)} sites queued for Playwright",
        "good",
    )
    return needs_pw


def run_pass2(
    needs_pw: List[dict],
    done:     Set[str],
    found:    dict,
    out_file: str,
    state:    State,
    ctx:      dict,
    cfg:      dict,
    stats:    dict,
) -> None:
    """
    Execute Pass 2: Playwright-based enrichment for JS-heavy sites.

    **Critical invariant**: ``sync_playwright().__enter__()`` is used instead
    of ``with sync_playwright() as p:`` to avoid a Windows/Python 3.12
    ContextVar incompatibility.

    Behaviour
    ---------
    - The browser is restarted every ``browser_restart_every`` sites to
      prevent memory accumulation on large runs.
    - Saves checkpoint + output every 10 sites.
    - Checks ``command.txt``, respects pause/stop, and verifies disk space.
    """
    todo          = [t for t in needs_pw if t["key"] not in found]
    stop_at       = cfg.get("stop_at", "")
    ckpt          = cfg["checkpoint_file"]
    cmd_file      = cfg["command_file"]
    restart_every = cfg.get("browser_restart_every", 150)

    log(f"Pass 2 — {len(todo)} sites → Playwright headless browser")

    if not todo:
        log("Pass 2: nothing to process")
        return

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log(
            "playwright not installed — "
            "run: pip install playwright && python -m playwright install chromium",
            "error",
        )
        return

    from core.browser_utils import enrich_one_browser, launch_browser

    pass2_found: int = 0
    pw_count:    int = 0

    bar = _TqdmClass(
        total=len(todo),
        desc="  Pass 2 (Browser)",
        unit="site",
        dynamic_ncols=True,
        colour="green" if TQDM_AVAILABLE else None,
    )
    set_active_bar(bar)

    # ── CRITICAL: use __enter__() / __exit__() — never `with sync_playwright()` ──
    _pw_ctx = sync_playwright()   # PlaywrightContextManager — owns __exit__
    pw      = _pw_ctx.__enter__()  # Playwright object — passed to launch_browser
    try:
        browser, page = launch_browser(pw, cfg)

        for count, target in enumerate(todo, 1):
            check_cmd_file(state, cmd_file, ckpt)
            if should_stop(state, stop_at):
                break
            wait_if_paused(state, ctx, cmd_file, ckpt)
            if should_stop(state, stop_at):
                break

            # Periodic browser restart prevents memory accumulation
            if pw_count > 0 and pw_count % restart_every == 0:
                log(f"Restarting browser after {pw_count} sites …", "dim")
                try:
                    browser.close()
                except Exception:
                    pass
                time.sleep(2)
                browser, page = launch_browser(pw, cfg)

            email, phone = enrich_one_browser(page, target, cfg)
            done.add(target["key"])
            pw_count    += 1
            ctx["done"]  = len(done)

            if email or phone:
                found[target["key"]] = {
                    "name":     target["name"],
                    "website":  target["website"],
                    "email":    email,
                    "phone":    phone or target.get("phone", ""),
                    "category": target["category"],
                }
                pass2_found          += 1
                ctx["found"]          = pass2_found
                stats["pass2_found"]  = pass2_found

            # Save every 10 sites
            if count % 10 == 0:
                if not check_disk():
                    break
                save_checkpoint(done, found, ckpt)
                save_output(found, out_file, cfg, stats)
                wait_for_internet(state)
                if should_stop(state, stop_at):
                    break

            rem   = len(todo) - count
            eta   = int(rem * 3 / 60)
            eta_s = f"~{eta // 60}h{eta % 60:02d}m" if eta >= 60 else f"~{eta}m"
            pct   = round(pass2_found / count * 100)
            bar.set_postfix(found=pass2_found, hit=f"{pct}%", eta=eta_s)
            bar.update(1)
            time.sleep(0.1)

        try:
            browser.close()
        except Exception:
            pass

    finally:
        _pw_ctx.__exit__(None, None, None)   # closes Chromium + cleans up IPC
        set_active_bar(None)
        bar.close()

    print()
    save_checkpoint(done, found, ckpt)
    save_output(found, out_file, cfg, stats)
    log(f"Pass 2 done — {pass2_found} additional contacts found via Playwright", "good")


# ===========================================================================
# Helpers to expose _start_time for ETA calculations
# ===========================================================================

_GLOBAL_START: float = 0.0


def _start_time_ref() -> float:
    return _GLOBAL_START


# ===========================================================================
# CLI
# ===========================================================================

def parse_args() -> argparse.Namespace:
    """Define and parse CLI arguments."""
    parser = argparse.ArgumentParser(
        prog="enricher",
        description=(
            "Email & Phone Enrichment Tool — "
            "scrape contact emails and phone numbers from company websites."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  python enricher.py                          # auto-detect CSV in current directory
  python enricher.py --input companies.csv
  python enricher.py --input leads.csv --config my_config.yaml
  python enricher.py --fresh                  # ignore checkpoint, start over
  python enricher.py --output results.xlsx    # override output path
        """,
    )
    parser.add_argument("--input",  "-i", help="Path to input CSV")
    parser.add_argument("--output", "-o", help="Path to output file")
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="Path to YAML config file (default: config.yaml)",
    )
    parser.add_argument(
        "--fresh", "-f",
        action="store_true",
        help="Clear existing checkpoint and start from scratch",
    )
    return parser.parse_args()


# ===========================================================================
# Pretty-print helpers
# ===========================================================================

def _print_banner() -> None:
    os_name = platform.system()
    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║   Email & Phone Enrichment Tool                  ║")
    print("║   Pass 1: HTTP  →  Pass 2: Playwright fallback   ║")
    print("╚══════════════════════════════════════════════════╝")
    if os_name == "Windows":
        print("  Controls: P=pause  R=resume  Q=quit  S=status")
    else:
        print("  Controls: type P / R / Q / S  then  Enter")
    if not TQDM_AVAILABLE:
        print("  Tip: pip install tqdm  for a richer progress bar")
    print()


def _print_summary(
    targets:  List[dict],
    found:    dict,
    out_file: str,
    stats:    dict,
    partial:  bool = False,
) -> None:
    total   = len(targets)
    n_email = sum(1 for v in found.values() if v.get("email"))
    n_phone = sum(1 for v in found.values() if v.get("phone"))
    n_any   = len(found)
    print()
    print("╔══════════════════════════════════════════════════╗")
    log(f"  {'PARTIAL — re-run to continue' if partial else 'COMPLETE'}")
    log(f"  Companies input  : {total}")
    log(f"  Contacts found   : {n_any}  ({round(n_any / total * 100) if total else 0}%)")
    log(f"    — Emails       : {n_email}  ({round(n_email / total * 100) if total else 0}%)")
    log(f"    — Phones       : {n_phone}  ({round(n_phone / total * 100) if total else 0}%)")
    log(f"  Still missing    : {total - n_any}")
    log(f"  Pass 1 found     : {stats.get('pass1_found', 0)}")
    log(f"  Pass 2 found     : {stats.get('pass2_found', 0)}")
    log(f"  Time elapsed     : {elapsed()}")
    log(f"  Output           : {os.path.abspath(out_file)}", "good")
    print("╚══════════════════════════════════════════════════╝")
    print()


# ===========================================================================
# main()
# ===========================================================================

def main() -> None:
    """
    Orchestrate the two-pass email & phone enrichment pipeline.

    Steps
    -----
    1. Load config (YAML merged with CLI overrides).
    2. Auto-detect or validate input CSV.
    3. Auto-detect columns (website, name, category, pre-existing phone).
    4. Resume from checkpoint / existing output if available.
    5. Pass 1 — fast HTTP requests with background auto-save.
    6. Pass 2 — Playwright fallback with background auto-save.
    7. Write final Excel + CSV output with run statistics.
    8. Clean up checkpoint on successful full completion.
    """
    global _GLOBAL_START
    _GLOBAL_START = time.time()
    set_start_time(_GLOBAL_START)

    args = parse_args()
    cfg  = load_config(args.config)

    # CLI args override config
    if args.input:  cfg["input_file"]  = args.input
    if args.output: cfg["output_file"] = args.output

    # Work relative to the script's own directory so paths in config are stable
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    _print_banner()

    # ── Auto-detect input file ─────────────────────────────────────────────
    if not cfg.get("input_file"):
        detected = find_input_file()
        if not detected:
            log("No input CSV found in current directory.", "error")
            log("Usage: python enricher.py --input path/to/file.csv", "info")
            return
        cfg["input_file"] = detected
        log(f"Auto-detected input: {detected}", "good")

    # ── State and statistics ───────────────────────────────────────────────
    state = State()
    ctx:   dict = {"found": 0, "done": 0}
    stats: dict = {
        "pass1_found": 0,
        "pass2_found": 0,
        "total":       0,
        "elapsed":     "",
        "input_file":  cfg["input_file"],
    }

    ckpt = cfg["checkpoint_file"]

    if args.fresh and os.path.exists(ckpt):
        os.remove(ckpt)
        log("Checkpoint cleared — starting fresh", "warn")

    log(f"Config : {args.config}")
    log(f"Input  : {cfg['input_file']}")
    out_file = get_output_path(cfg)
    log(f"Output : {out_file}  [{cfg.get('output_format', 'xlsx').upper()}]")
    print()

    # Start keyboard listener (background daemon thread)
    ControlListener(state, ctx)

    try:
        targets = load_input(cfg)
    except (FileNotFoundError, ValueError) as exc:
        log(str(exc), "error")
        return

    stats["total"] = len(targets)
    log(f"Loaded {len(targets)} rows from CSV")

    if not targets:
        log("Nothing to process.", "warn")
        return

    # Category distribution summary
    cats = Counter(t["category"] for t in targets if t.get("category"))
    if cats:
        log("Category breakdown:")
        for cat, n in sorted(cats.items(), key=lambda x: -x[1]):
            log(f"  {cat:<42} {n}", "dim")
    print()

    # Resume from checkpoint + any existing output CSV
    _, found = load_checkpoint(ckpt)
    found.update(load_existing_output(out_file, cfg))
    done: Set[str] = set()

    if found:
        log(f"Resuming — {len(found)} contacts already in cache", "good")
        try:
            import winsound as _ws
            _ws.Beep(600, 150); _ws.Beep(900, 250)
        except Exception:
            print("\a", end="", flush=True)
    else:
        log("Fresh start", "good")
        try:
            import winsound as _ws
            _ws.Beep(500, 100); _ws.Beep(700, 100); _ws.Beep(900, 200)
        except Exception:
            print("\a", end="", flush=True)

    ctx["done"] = len(found)
    autosave_interval = cfg.get("autosave_interval", 60)

    # ── Pass 1 ─────────────────────────────────────────────────────────────
    auto_saver1 = AutoSaver(found, out_file, cfg, stats, interval=autosave_interval)
    needs_pw    = run_pass1(targets, done, found, out_file, state, ctx, cfg)
    stats["pass1_found"] = len(found)
    auto_saver1.stop()

    if should_stop(state, cfg.get("stop_at", "")):
        save_checkpoint(done, found, ckpt)
        save_output(found, out_file, cfg, stats)
        _print_summary(targets, found, out_file, stats, partial=True)
        return

    print()

    # ── Pass 2 ─────────────────────────────────────────────────────────────
    auto_saver2 = AutoSaver(found, out_file, cfg, stats, interval=autosave_interval)
    run_pass2(needs_pw, done, found, out_file, state, ctx, cfg, stats)
    auto_saver2.stop()

    # ── Final save ─────────────────────────────────────────────────────────
    stats["elapsed"] = elapsed()
    save_checkpoint(done, found, ckpt)
    save_output(found, out_file, cfg, stats)

    all_done = not state.stop
    if all_done and os.path.exists(ckpt):
        os.remove(ckpt)   # clean run — no need to keep checkpoint

    # Completion beep
    try:
        import winsound as _ws
        if all_done:
            for f, d in [(600, 100), (800, 100), (1000, 100), (1200, 300)]:
                _ws.Beep(f, d)
        else:
            _ws.Beep(900, 200); _ws.Beep(600, 400)
    except Exception:
        print("\a", end="", flush=True)

    _print_summary(targets, found, out_file, stats, partial=not all_done)


if __name__ == "__main__":
    main()
