# Changelog

All notable changes to **email-enricher** are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versions follow [Semantic Versioning](https://semver.org/).

---

## [1.1.0] — 2026-05-11

### Fixed

* `stats["pass1_found"]` inflation on resume: snapshot `len(found)` before
  Pass 1 and subtract after, so the Run Stats sheet reports only contacts
  found in the current run rather than including the resumed cache.
* README `What Data You Get` section: removed inaccurate `user@domain.com`
  placeholder description — the tool writes an empty cell when no email is
  found, not a fake address.

### Added

* `tests/test_core.py` — 10 new tests for `http_utils` (88 total):
  * `TestFetchUrl` — 200 response, 404 response, network exception, and
    daemon-thread wall-clock timeout exit path.
  * `TestEnrichOneHttp` — email extraction from homepage, phone extraction,
    empty result on no contact, empty result on fetch failure, junk-email
    filtering, and contact sub-page fallback visit.
* `.github/ISSUE_TEMPLATE/bug_report.md` and `feature_request.md` — GitHub
  issue templates (fills the community health bar).

### Changed

* CHANGELOG [1.0.0]: corrected test count from "50+" to "78" and OS matrix
  from "2 OS" to "3 OS" to match actual state at release.
* README Tests badge and all test-count references updated: 78 → 88.

---

## [1.0.0] — 2024-12-01

### Added — Project structure

* Modular `core/` package split into focused modules:
  * `core/email_utils.py` — extraction, Cloudflare XOR decoding, scoring, best-pick
  * `core/http_utils.py`  — `fetch_url` with hard-kill daemon-thread timeout, Pass 1
  * `core/browser_utils.py` — `launch_browser`, `dismiss_cookie_banner`, Pass 2
  * `core/storage.py`     — atomic checkpoint (tmp + `os.replace`), XLSX + CSV output
  * `core/controls.py`    — `State`, `ControlListener`, `AutoSaver`, `check_cmd_file`
  * `core/_log.py`        — shared `log()` / `elapsed()` used by all modules
* `tests/test_core.py` — 78 unit tests covering all core modules
* `.github/workflows/ci.yml` — GitHub Actions: pytest on push × 3 Python versions × 3 OS
* `pyproject.toml` — PEP 517 metadata, pytest config, coverage config
* `requirements-dev.txt` — `pytest`, `pytest-cov`
* `config.example.yaml` — safe-to-commit placeholder template
* `CHANGELOG.md`, `LICENSE` (MIT, author: Afaq)

### Changed

* `enricher.py` refactored into a thin orchestrator that imports from `core/`
* `run_pass2()` now uses `sync_playwright().__enter__()` / `pw.__exit__(None, None, None)`
  instead of `with sync_playwright() as p:` (fixes Windows Python 3.12 ContextVar error)
* Atomic checkpoint: writes to `.tmp` then `os.replace()` — no partial-write corruption
* `core/_log.py` `set_active_bar()` / `set_start_time()` replace module-level globals

### Preserved (all original features retained)

* Two-pass architecture: requests GET → Playwright headless fallback
* Cloudflare email-protection XOR decoding (`data-cfemail` + `/cdn-cgi/` patterns)
* Email scoring: personal (1) > priority-generic (2) > generic (3) > junk (999)
* Phone extraction: `tel:` href priority → regex fallback
* Cookie banner dismissal (configurable selectors)
* Checkpoint / resume (`enrich_checkpoint.json`)
* Background `AutoSaver` thread (every N seconds)
* Per-site save every 10 sites (both passes)
* Cross-platform keyboard controls: P / R / Q / S
* `command.txt` remote control file
* `winsound` beeps (try/except for non-Windows)
* Disk space guard (`check_disk`)
* Auto-pause on internet loss (`wait_for_internet`)
* Wall-clock `stop_at` time
* XLSX output: Results sheet + Run Stats sheet
* User-agent rotation, configurable rate limiting
* Auto-detect input CSV, auto-detect column names
* CLI: `--input`, `--output`, `--config`, `--fresh`
* tqdm progress bar with ETA (graceful fallback shim if not installed)
* Background `AutoSaver` thread

---

## [0.1.0] — 2024-11-01

### Added

* Initial monolithic `enricher.py` — single-file two-pass enricher
* `config.yaml`, `requirements.txt`, `.gitignore`, `README.md`
