# Email & Phone Number Enrichment Tool

> **Production-grade Python pipeline — converts any CSV of business websites into a verified contact database of emails and phone numbers. Dual-pass architecture: fast HTTP first, Playwright fallback for the rest. ~80–95% hit rate on real UK business datasets.**

> **⚠️ Input required.** This tool enriches an *existing* list of websites — it does not generate leads from scratch. You need a CSV with a website/URL column. To generate the list first, see [Google Maps Business Scraper](https://github.com/FAAQJAVED/Google-Maps-Business-Scraper) or [LeadHunter Pro](https://github.com/FAAQJAVED/Leadhunter_Pro).

[![CI](https://github.com/FAAQJAVED/Email-Phone-Number-Enrichment-Tool/actions/workflows/ci.yml/badge.svg)](https://github.com/FAAQJAVED/Email-Phone-Number-Enrichment-Tool/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)
[![Tests](https://img.shields.io/badge/tests-78%20passing-brightgreen)](tests/test_core.py)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)

---

> Found this useful? A ⭐ on GitHub helps other developers find it.

---

## Table of Contents

[Preview](#preview) · [What It Does](#what-it-does) · [Use Cases](#use-cases) · [How It Works](#how-it-works) · [Features](#features) · [Real Results](#real-results) · [What Data You Get](#what-data-you-get) · [Quick Start](#quick-start) · [Input Format](#input-format) · [Configuration](#configuration) · [Output Format](#output-format) · [Runtime Controls](#runtime-controls) · [Tech Stack](#tech-stack) · [Project Structure](#project-structure) · [Running Tests](#running-tests) · [Troubleshooting](#troubleshooting) · [B2B Lead Toolkit](#b2b-lead-toolkit) · [Notes](#notes) · [License](#license)

---

## Preview

| Terminal — dual-pass progress | Excel Output |
|---|---|
| ![Terminal progress bar showing Pass 1 and Pass 2 running with live hit% and ETA](Assets/terminal_progress.png) | ![Excel output — Results sheet with company name, website, email, phone, category columns](Assets/output_preview.png) |

---

## What It Does

1. **Ingests any CSV** with a website/URL column — auto-detects the column name, no header renaming required.
2. **Pass 1 (HTTP):** fires lightweight `requests` GET calls at the homepage and up to 4 contact sub-pages per site, extracting plaintext and Cloudflare-obfuscated emails and phone numbers.
3. **Pass 2 (Browser):** runs headless Chromium via Playwright on every site that Pass 1 missed — handles JavaScript-rendered pages, SPAs, and React/Next.js frontends.
4. **Scores each email** — personal name emails score 1 (best), priority generics score 2, standard generics score 3, junk filtered entirely.
5. **Outputs** a styled Excel workbook (Results sheet + Run Stats sheet) plus a CSV backup, with one row per input website.

---

## Use Cases

| Who uses it | What they do |
|---|---|
| **Sales teams** | Take a Maps or Trustpilot lead list and add direct email + phone to every row before outreach |
| **Marketing agencies** | Enrich client-supplied company lists with verified contact data in under an hour |
| **CRM admins** | Validate and fill gaps in existing contact databases against live website data |
| **Recruiters** | Extract HR or management contact emails from a list of target employers |
| **Lead gen freelancers** | Deliver enriched Excel files to clients — website list in, email+phone out |
| **Market researchers** | Measure contact data coverage and email hit rates across an industry segment |

---

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│  INPUT                                                          │
│  any CSV with a website/URL column                             │
│  auto-detected header — no renaming required                    │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│  PASS 1 — HTTP (requests · parallel threads)                   │
│                                                                 │
│  homepage + up to 4 contact sub-pages per site                 │
│  ├── plaintext email regex                                      │
│  ├── Cloudflare XOR decode (data-cfemail)                      │
│  └── UK + international phone regex                            │
│                                                                 │
│  ~80% hit rate on standard UK business websites                │
└──────────────────────────────┬──────────────────────────────────┘
                               │  sites with no result from Pass 1
┌──────────────────────────────▼──────────────────────────────────┐
│  PASS 2 — BROWSER (Playwright · headless Chromium)             │
│                                                                 │
│  JS-rendered pages · SPAs · React/Next.js frontends            │
│  same extraction logic as Pass 1, after JS execution           │
│                                                                 │
│  Additional ~10–15% recovered from JS-heavy sites              │
└──────────────────────────────┬──────────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────────┐
│  OUTPUT                                                         │
│  found_contacts_YYYYMMDD.xlsx  (Results + Run Stats sheets)    │
│  found_contacts_YYYYMMDD.csv   (CSV backup, always written)    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Features

| Feature | Detail |
|---|---|
| **Dual-pass architecture** | Fast `requests` first (~80% hit rate), Playwright fallback for the rest |
| **Cloudflare email decoding** | Decodes `data-cfemail` and `/cdn-cgi/l/email-protection#` XOR-obfuscated emails |
| **Email quality scoring** | Personal names score 1 (best), generic addresses 2–3, junk filtered entirely |
| **Smart contact page discovery** | Tries /contact, /about, /team, /staff before giving up |
| **Phone extraction** | `tel:` href links (highest confidence) → regex fallback for UK + international formats |
| **Auto-detects CSV headers** | No renaming of "Website", "URL", "Site", "Domain" — all accepted |
| **Parallel processing** | Configurable thread count — 10 threads by default |
| **Junk email filtering** | Configurable list of domains and keywords to exclude (noreply@, gdpr@, etc.) |
| **Excel output + Run Stats** | Styled workbook with hit rate percentages, run duration, and coverage breakdown |
| **CSV backup** | Always written alongside Excel — safe for large datasets and resume on next run |
| **78 pure-function tests** | Full test suite runs offline in under 3 seconds — no browser or network required |
| **Cookie banner dismissal** | 10 configurable Playwright selectors, silently ignored on failure |
| **Atomic checkpoint** | Writes to `.tmp` then `os.replace()` — no data loss on crash or kill |
| **Resume anywhere** | Re-run the same command to continue; already-processed sites are never re-scraped |
| **Background auto-save** | Saves every 60 s (configurable) + every 10 sites in both passes |
| **Cross-platform controls** | P / R / Q / S keys (Windows: no Enter; Mac/Linux: type + Enter) |
| **Remote command file** | `echo pause > command.txt` controls a running process without killing it |
| **Disk space guard** | Pauses before the output volume fills up during long runs |
| **Auto-pause on outage** | Polls every 30 s and resumes automatically when internet is restored |
| **Wall-clock stop time** | `stop_at: "23:00"` halts the run and saves a resumable checkpoint |
| **User-agent rotation** | Randomised from a configurable pool on every request |
| **tqdm progress bar** | Live count, hit%, and ETA for both passes (graceful shim if tqdm is absent) |
| **winsound beeps** | Audio feedback for start, pause, resume, done — silently skipped on non-Windows |

---

## Real Results

> **Tested against 7,000+ UK property-sector websites** (letting agents, block managers, HMO landlords) scraped via Google Maps Business Scraper.
>
> - **~80% hit rate on Pass 1** (plain HTTP) — most sites serve contact emails in static HTML
> - **Additional ~10–15%** recovered by Pass 2 (Playwright) on JS-heavy property portals
> - **Cloudflare-protected sites** decoded correctly — XOR key extracted and applied per address
> - Full run of **1,200 sites completes in ~35–45 minutes** on standard UK broadband

---

## What Data You Get

Every input row produces one output row. The actual columns written to the Excel file and CSV backup are:

| Field | Example (real output) |
|---|---|
| **Company Name** | 1 Click Properties |
| **Website** | https://www.1clickproperties.co.uk/ |
| **Email** | info@1clickproperties.co.uk |
| **Phone** | 0208 752 1800 |

> Sites where no email was found are written with `user@domain.com` as a placeholder — these are easy to filter out in Excel. Category is included as an extra column when it is present in your input CSV.

See [`Assets/sample_output.csv`](Assets/sample_output.csv) for 15 rows of real output from an actual run against UK property-sector websites.

---

## Quick Start

### 1. Clone

```bash
git clone https://github.com/FAAQJAVED/Email-Phone-Number-Enrichment-Tool.git
cd Email-Phone-Number-Enrichment-Tool
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Install Playwright Chromium

```bash
python -m playwright install chromium
```

### 4. Run

```bash
# Auto-detects your CSV and column names
python enricher.py

# Or specify explicitly
python enricher.py --input leads.csv --output results.xlsx
```

---

## Input Format

Drop **any CSV** with a website/URL column into the project folder. The tool auto-detects headers — no renaming needed.

```csv
Company Name,Website,Category
Acme Lettings,https://acmelettings.co.uk,Letting Agent
City Block Mgmt,https://cityblock.co.uk,Block Manager
Prime HMO Ltd,https://primehmo.com,HMO Landlord
```

**Detected automatically by keyword matching:**

| Field | Detected by keywords | Required? |
|---|---|---|
| Website / URL | `website` `url` `domain` `site` `web` `link` `homepage` | ✅ Yes |
| Company Name | `company` `name` `organisation` `organization` `business` `firm` `client` `brand` `title` | No — falls back to first column |
| Category | `category` `type` `sector` `industry` `segment` `group` `vertical` | No — omitted silently |
| Pre-existing Phone | `phone` `tel` `mobile` `cell` `number` `contact number` | No — carried through to output |

Override auto-detection in `config.yaml` under `columns:` if needed.

---

## Configuration

Edit `config.yaml` — every option is documented inline. Key settings:

| Key | Default | Description |
|---|---|---|
| `input_file` | `""` | Blank = auto-detect CSV in current directory |
| `output_file` | `""` | Blank = auto-generate `found_contacts_YYYYMMDD.xlsx` |
| `output_format` | `"xlsx"` | `"xlsx"` or `"csv"` |
| `http_timeout` | `[4, 6]` | `[connect_timeout, read_timeout]` in seconds |
| `playwright_timeout` | `8000` | Page load timeout in ms (Pass 2) |
| `browser_restart_every` | `150` | Restart Chromium every N sites (prevents memory leak) |
| `stop_at` | `"23:00"` | Wall-clock auto-stop time (blank to disable) |
| `autosave_interval` | `60` | Background save every N seconds |
| `rate_limit.min_seconds` | `0.1` | Minimum delay between requests |
| `rate_limit.max_seconds` | `0.5` | Maximum delay between requests |
| `contact_paths` | `["/contact", ...]` | Sub-pages visited per site |
| `skip_email_keywords` | `[noreply, gdpr, ...]` | Emails matching these are discarded |
| `generic_email_keywords` | `[info, hello, ...]` | Emails matching these are scored lower |
| `junk_email_domains` | `[sentry.io, ...]` | Emails from these domains are discarded |
| `cookie_selectors` | `[button:has-text(...)]` | Playwright cookie-dismiss selectors |

Copy `config.example.yaml` → `config.yaml` to get started.

---

## Output Format

### Excel workbook — `found_contacts_YYYYMMDD.xlsx`

**Sheet 1 — Results**

| Company Name | Website | Email | Phone | Category |
|---|---|---|---|---|
| Acme Lettings | https://acmelettings.co.uk | james@acmelettings.co.uk | +44 20 7946 0123 | Letting Agent |
| City Block Mgmt | https://cityblock.co.uk | info@cityblock.co.uk | (020) 3456 7890 | Block Manager |

**Sheet 2 — Run Stats**

| Metric | Value |
|---|---|
| Run Timestamp | 2024-12-01 22:14:03 |
| Input File | leads.csv |
| Companies Input | 1,200 |
| Contacts Found | 960 |
| — Emails Found | 912 |
| — Phones Found | 690 |
| Email Success Rate | 76% |
| Phone Success Rate | 57% |
| Any Contact Rate | 80% |
| Still Missing | 240 |
| Pass 1 Found | 720 |
| Pass 2 Found | 240 |
| Time Elapsed | [42m18s] |

A **CSV backup** is always written alongside the Excel file (used for resume on next run).

---

## Runtime Controls

| Key | Action |
|---|---|
| `P` | Pause / Resume |
| `R` | Resume (if paused) |
| `Q` | Quit and save progress |
| `S` | Print current status |

> **Windows:** single keypress — no Enter required (uses `msvcrt`).
> **Mac / Linux:** type the letter then press **Enter** (uses `select` + stdin).

**Remote control via file** (works while the script is running in a terminal or scheduled task):

```bash
echo pause   > command.txt   # pause after current site
echo resume  > command.txt   # resume
echo stop    > command.txt   # save and exit
echo fresh   > command.txt   # delete checkpoint (restart on next run)
```

---

## Tech Stack

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-2EAD33?style=for-the-badge&logo=playwright&logoColor=white)
![Requests](https://img.shields.io/badge/Requests-FF6B35?style=for-the-badge)
![OpenPyXL](https://img.shields.io/badge/OpenPyXL-217346?style=for-the-badge&logo=microsoft-excel&logoColor=white)
![pytest](https://img.shields.io/badge/pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-2088FF?style=for-the-badge&logo=github-actions&logoColor=white)

| Library | Role |
|---|---|
| `requests` | Pass 1 — fast, lightweight HTTP GET with threading-based hard timeout |
| `playwright` | Pass 2 — headless Chromium for JavaScript-rendered pages |
| `openpyxl` | Excel output with styled headers and Run Stats sheet |
| `pyyaml` | YAML config loading with default fallback |
| `tqdm` | Live terminal progress bar with ETA for both passes |
| `urllib3` | SSL warning suppression for sites with invalid certificates |

---

## Project Structure

```
Email-Phone-Number-Enrichment-Tool/
├── enricher.py              ← Orchestrator — two-pass pipeline, CLI, banners
├── core/
│   ├── __init__.py          ← Public re-exports
│   ├── email_utils.py       ← extract_emails, decode_cloudflare, score_email, best_email
│   ├── http_utils.py        ← fetch_url (hard-kill thread timeout), enrich_one_http
│   ├── browser_utils.py     ← launch_browser, dismiss_cookie_banner, enrich_one_browser
│   ├── storage.py           ← Atomic checkpoint, XLSX/CSV output
│   └── controls.py          ← State, ControlListener, AutoSaver, check_cmd_file
├── tests/
│   ├── __init__.py
│   └── test_core.py         ← 78 unit tests
├── Assets/
│   ├── terminal_progress.png
│   ├── output_preview.png
│   └── sample_output.csv
├── .github/
│   └── workflows/
│       └── ci.yml           ← pytest on push × 3 Python × 3 OS (Ubuntu, Windows, macOS)
├── config.yaml              ← Full annotated config
├── config.example.yaml      ← Safe-to-commit placeholder template
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE                  ← MIT
└── README.md
```

---

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest -v
```

With coverage:

```bash
pytest --cov=core --cov=enricher --cov-report=term-missing
```

---

## Troubleshooting

**Email column empty after Pass 1:**
The target site renders contact details with JavaScript. Pass 1 cannot execute JavaScript — this is expected. Pass 2 (Playwright) picks up where Pass 1 left off. If Pass 2 also returns nothing, the site hides contact details behind a login wall or has no publicly listed contact.

**Pass 2 not running:**
Playwright must be installed separately. Run: `python -m playwright install chromium`
Pass 2 only activates for rows where Pass 1 found nothing.

**Returning wrong or generic emails (info@, admin@):**
Extend `generic_email_keywords` in your `config.yaml`. Also check `junk_email_domains` to exclude bulk-mail providers.

**No output file created:**
The script writes output only after processing all rows. Check the terminal progress bar — if it is moving, the script is working. A `PermissionError` means Excel has the previous output file open — close it first.

**Crashes on Windows with Python 3.12:**
Known asyncio/ContextVar issue. The script applies the `WindowsSelectorEventLoopPolicy` fix automatically. Run directly with `python enricher.py` — not via a test runner or wrapper.

---

## B2B Lead Toolkit

This enricher is one component of a broader B2B lead generation pipeline targeting UK property management companies, letting agents, block managers, and HMO landlords.

| Repo | What it does |
|---|---|
| **[Email-Phone-Number-Enrichment-Tool](https://github.com/FAAQJAVED/Email-Phone-Number-Enrichment-Tool)** ← *you are here* | Scrapes contact emails + phones from company websites |
| **[Google Maps Business Scraper](https://github.com/FAAQJAVED/Google-Maps-Business-Scraper)** | Extracts and enriches business listings from Google Maps |
| **[Leadhunter Pro](https://github.com/FAAQJAVED/Leadhunter_Pro)** | Multi-engine search scraper with HOT/WARM/COLD lead scoring |
| **[Trustpilot Business Scraper](https://github.com/FAAQJAVED/trustpilot-business-scraper)** | Extracts business listings from Trustpilot search results |
| **[JSON Directory Harvester](https://github.com/FAAQJAVED/json-directory-harvester)** | Configurable harvester for any JSON directory API with geo-filtering |

---

## Notes

* `robots.txt` is **not** enforced automatically — ensure your use case complies with each site's terms of service and applicable law.
* SSL certificate errors are suppressed to handle sites with expired or self-signed certificates.
* No data is stored or transmitted externally — all output is written locally.
* The `sync_playwright().__enter__()` pattern is used instead of `with sync_playwright() as p:` to avoid a Windows + Python 3.12 ContextVar incompatibility.

---

## License

MIT © 2026 [FAAQJAVED](https://github.com/FAAQJAVED) — see [LICENSE](LICENSE)
