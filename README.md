# Email Enrichment Tool

> Automatically scrape contact email addresses from a list of company websites — with a two-pass architecture, checkpoint/resume, Excel output, and cross-platform controls.

---

## Overview

This tool takes a CSV of companies and their websites and attempts to extract a valid contact email address from each site. It runs two sequential passes: a fast HTTP pass for straightforward sites, followed by a Playwright headless-browser pass for JavaScript-rendered pages. Results are written to a formatted Excel workbook with a Run Stats sheet, plus a CSV backup for easy resume support.

Designed for large-scale runs (hundreds to thousands of sites), it includes auto-pause on internet loss, disk-space monitoring, periodic checkpointing, configurable rate limiting, and user-agent rotation out of the box.

---

## Features

- **Two-pass architecture** — fast `requests` pass first, Playwright fallback for JS-heavy sites
- **Cloudflare email-protection decoder** — recovers emails obfuscated by Cloudflare's CDN
- **Email quality scoring** — prefers personal names over generic addresses (info@, contact@), discards junk
- **Checkpoint & resume** — safe to interrupt at any time; re-run to continue where you left off
- **Excel output with Run Stats** — Sheet 1 = results, Sheet 2 = summary metrics
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

Create a `companies.csv` in the project folder (or specify a custom path):

```csv
Company Name,Website,Category
Acme Corp,https://acmecorp.com,Technology
Globex,https://globex.com,Manufacturing
```

The `Company Name` and `Website` columns are required. `Category` is optional. Column names are configurable in `config.yaml`.

---

## Configuration

Copy and edit `config.yaml`:

```yaml
input_file: "companies.csv"    # your input CSV
output_format: "xlsx"          # "xlsx" or "csv"
stop_at: "23:00"               # auto-stop time (blank to disable)

rate_limit:
  min_seconds: 0.1
  max_seconds: 0.5

columns:
  company_name: "Company Name"  # match your CSV header exactly
  website: "Website"
```

Every field is commented — see `config.yaml` for the full reference.

---

## Usage

```bash
# Run with defaults (reads config.yaml + companies.csv)
python enricher.py

# Specify a custom input file
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

### Excel workbook (`found_emails_YYYYMMDD.xlsx`)

**Sheet 1 — Results**

| Company Name | Website | Email | Category |
|---|---|---|---|
| Acme Corp | https://acmecorp.com | john.doe@acmecorp.com | Technology |

**Sheet 2 — Run Stats**

| Metric | Value |
|---|---|
| Run Timestamp | 2024-01-15 22:14:03 |
| Companies Input | 1,200 |
| Emails Found | 847 |
| Success Rate | 71% |
| Pass 1 Found | 623 |
| Pass 2 Found | 224 |
| Time Elapsed | [38m42s] |

A CSV backup (`found_emails_YYYYMMDD.csv`) is always written alongside the Excel file and is used by the resume system.

---

## Checkpoint & Resume

Progress is saved automatically every 50 sites (Pass 1) and every 25 sites (Pass 2).  
If interrupted, simply re-run the same command — already-found emails are never re-scraped.

To start completely fresh:
```bash
python enricher.py --fresh
```

Or write `fresh` to `command.txt` while running to clear the checkpoint on the next restart.

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
└── companies.csv        # Your input file (not committed)
```

---

## Notes

- Respects `robots.txt` is **not** enforced automatically — ensure your use case complies with each site's terms of service.
- SSL certificate errors are suppressed to handle sites with expired or self-signed certificates.
- The tool does not store or transmit data externally — all output is written locally.
