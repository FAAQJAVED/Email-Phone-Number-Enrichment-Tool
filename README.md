# Email & Phone Enrichment Tool

> Automatically scrape **contact email addresses and phone numbers** from a list of company websites — with zero column-name requirements, automatic file detection, a live progress bar, two-pass architecture, background auto-save, and Excel output.

---

## Overview

This tool takes any CSV that contains a website/URL column and attempts to extract a valid contact email and phone number from each site. It runs two sequential passes: a fast HTTP pass for straightforward sites, followed by a Playwright headless-browser pass for JavaScript-rendered pages.

**No file renaming, no column renaming.** Drop your CSV in the folder, run the script, and it figures out the rest.

Results are written to a formatted Excel workbook with a Run Stats sheet, plus a CSV backup. Progress is continuously saved — every 10 sites and every 60 seconds in a background thread — so interruptions lose almost nothing.

---

## Features

- **Zero column-name requirements** — automatically detects website, company name, category, and phone columns from whatever headers your CSV uses
- **Zero filename requirements** — auto-detects your CSV from the current directory; prompts you to choose if multiple are found
- **Email + phone scraping** — extracts both contact emails and phone numbers from every page visited
- **Two-pass architecture** — fast `requests` pass first, Playwright fallback for JS-heavy sites
- **Live tqdm progress bar** — shows count, hit rate, and ETA for both passes
- **Background auto-save** — saves every 10 sites AND every 60 seconds in a daemon thread, so you never lose progress
- **Cloudflare email-protection decoder** — recovers emails obfuscated by Cloudflare's CDN
- **Phone number extraction** — prioritises `tel:` href links (highest confidence), falls back to regex pattern matching
- **Email quality scoring** — prefers personal names over generic addresses (info@, contact@), discards junk
- **Checkpoint & resume** — safe to interrupt at any time; re-run to continue where you left off
- **Excel output with Run Stats** — Sheet 1 = results (including Phone column), Sheet 2 = summary metrics
- **User-agent rotation** — randomised from a configurable pool on every request
- **Configurable rate limiting** — random jitter between requests for ethical, sustainable scraping
- **Cross-platform controls** — P/R/Q/S keys on Windows; typed commands on Mac/Linux
- **Auto-pause on internet loss** — polls every 30 s and resumes automatically
- **Disk space guard** — pauses before the disk fills up on long runs
- **Fully config-driven** — `config.yaml` controls everything; CLI args override at runtime

---

## Tech Stack

| Library | Purpose |
|---|---|
| `requests` | Pass 1 — fast, lightweight HTTP GET with threading-based timeout |
| `playwright` | Pass 2 — headless Chromium for JavaScript-rendered pages |
| `openpyxl` | Excel output with styled headers and Run Stats sheet |
| `pyyaml` | YAML config loading with default fallback |
| `tqdm` | Live terminal progress bar with ETA |
| `urllib3` | SSL warning suppression for sites with invalid certificates |

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/email-enrichment-tool.git
cd email-enrichment-tool
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install the Playwright browser

```bash
python -m playwright install chromium
```

### 4. Prepare your input file

Place any CSV containing website URLs in the project folder. **No renaming required.** Example:

```csv
Business Name,Site,Segment
Acme Corp,https://acmecorp.com,Technology
Globex,https://globex.com,Manufacturing
```

The tool auto-detects the URL column (looks for headers containing *website*, *url*, *domain*, *site*, *link*, etc.) and the company-name column (looks for *company*, *name*, *business*, *firm*, etc.).

---

## Column Auto-Detection

The tool automatically maps your CSV headers using keyword matching. You never need to rename columns.

| Field | Detected by keywords | Required? |
|---|---|---|
| Website / URL | `website` `url` `domain` `site` `web` `link` `homepage` | ✅ Yes |
| Company Name | `company` `name` `organisation` `organization` `business` `firm` `client` `brand` `title` | No — falls back to first column |
| Category | `category` `type` `sector` `industry` `segment` `group` `vertical` | No — omitted if absent |
| Pre-existing Phone | `phone` `tel` `mobile` `cell` `number` `contact number` | No — carried through to output |

If auto-detection picks the wrong column, you can override it in `config.yaml` under `columns:`.

---

## Configuration

Edit `config.yaml` to customise behaviour:

```yaml
input_file: ""             # blank = auto-detect CSV in current directory
output_format: "xlsx"      # "xlsx" or "csv"
stop_at: "23:00"           # auto-stop time (blank to disable)
autosave_interval: 60      # background save every N seconds

rate_limit:
  min_seconds: 0.1
  max_seconds: 0.5

columns:
  company_name: ""   # blank = auto-detect
  website:      ""   # blank = auto-detect
  email:        "Email"
  phone:        "Phone"
  category:     ""   # blank = auto-detect (optional)
```

Every field is documented — see `config.yaml` for the full reference.

---

## Usage

```bash
# Run with auto-detection (finds CSV in current directory)
python enricher.py

# Specify a CSV explicitly
python enricher.py --input leads.csv

# Use a different config file
python enricher.py --config production.yaml

# Override the output path
python enricher.py --output results_2024.xlsx

# Clear checkpoint and start completely fresh
python enricher.py --fresh

# Combine options
python enricher.py --input leads.csv --config production.yaml --fresh
```

### Runtime controls

| Key | Action |
|---|---|
| `P` | Pause / Resume |
| `R` | Resume (if paused) |
| `Q` | Quit and save progress |
| `S` | Print current status |

> **Mac/Linux:** type the letter then press **Enter**.  
> **Windows:** single keypress, no Enter required.

You can also write a command to `command.txt` while the script runs:  
`echo pause > command.txt`

---

## Output

### Excel workbook (`found_contacts_YYYYMMDD.xlsx`)

**Sheet 1 — Results**

| Company Name | Website | Email | Phone | Category |
|---|---|---|---|---|
| Acme Corp | https://acmecorp.com | john.doe@acmecorp.com | +44 20 7123 4567 | Technology |

**Sheet 2 — Run Stats**

| Metric | Value |
|---|---|
| Run Timestamp | 2024-01-15 22:14:03 |
| Input File | leads.csv |
| Companies Input | 1,200 |
| Contacts Found | 891 |
| — Emails Found | 847 |
| — Phones Found | 612 |
| Email Success Rate | 71% |
| Phone Success Rate | 51% |
| Any Contact Rate | 74% |
| Pass 1 Found | 623 |
| Pass 2 Found | 268 |
| Time Elapsed | [38m42s] |

A CSV backup (`found_contacts_YYYYMMDD.csv`) is always written alongside the Excel file.

---

## Progress Bar

The tool uses `tqdm` to show a live progress bar for both passes:

```
  Pass 1 (HTTP)    |████████████████    | 420/600 [04:12<01:50] found=298, hit=71%, eta=~2m
  Pass 2 (Browser) |████████░░░░░░░░░░░ |  62/180 [03:05<08:45] found=41,  hit=66%, eta=~9m
```

---

## Auto-Save Behaviour

Progress is never lost. The tool saves in two ways:

1. **Per-site saves** — every 10 sites processed (Pass 1 and Pass 2)
2. **Background thread** — every 60 seconds (configurable via `autosave_interval`)

To resume an interrupted run, simply re-run the same command. Already-processed sites are never re-scraped.

To start completely fresh:
```bash
python enricher.py --fresh
```

---

## Phone Number Extraction

The tool extracts phone numbers using a two-stage approach:

1. **`tel:` href links** — scraped from anchor tags (`<a href="tel:+441234567890">`). Very high confidence, almost no false positives.
2. **Regex pattern matching** — used as fallback when no `tel:` links are found. Covers international format (`+44 20 7123 4567`), bracketed area codes (`(020) 7123 4567`), and plain hyphenated formats (`555-555-5555`). Filtered by digit count (7–15 digits).

---

## Email Scoring

The tool ranks emails by quality and picks the best one per site:

| Score | Type | Example |
|---|---|---|
| 1 | Personal name *(best)* | `j.smith@company.com` |
| 2 | High-priority generic | `info@`, `hello@`, `contact@` |
| 3 | Other generic | `support@`, `accounts@`, `sales@` |
| 999 | Junk / filtered | `noreply@`, `gdpr@`, platform domains |

All keyword lists are configurable in `config.yaml`.

---

## Project Structure

```
email-enrichment-tool/
├── enricher.py          # Main script — all logic
├── config.yaml          # Full configuration with comments
├── requirements.txt     # Python dependencies
├── README.md
└── .gitignore
```

Your input CSV can be named anything and placed in the same directory. It will be auto-detected.

---

## Notes

- `robots.txt` is **not** enforced automatically — ensure your use case complies with each site's terms of service.
- SSL certificate errors are suppressed to handle sites with expired or self-signed certificates.
- The tool does not store or transmit data externally — all output is written locally.
- Phone extraction targets contact pages; internal tool UIs, CMS pages, and admin dashboards may produce false positives that are filtered by the 7–15 digit rule.
