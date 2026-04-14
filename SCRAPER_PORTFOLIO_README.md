# Zee's Scraper Portfolio — Full Analysis & README
**By Afaq | 360 Safety Checks | London Property Lead Generation**

---

## Table of Contents
1. [Project Overview Table](#1-project-overview-table)
2. [Critical Issues — Fix These First](#2-critical-issues--fix-these-first)
3. [Environment Setup](#3-environment-setup)
4. [Project-by-Project Analysis](#4-project-by-project-analysis)
5. [Per-Project README](#5-per-project-readme)
6. [GitHub Publishing Guide](#6-github-publishing-guide)
7. [Testing Checklist](#7-testing-checklist)

---

## 1. Project Overview Table

| # | Folder | Original File | What It Does | Status |
|---|--------|--------------|--------------|--------|
| 1 | `searchpy/` | `search.py` | Search-driven lead scraper (Bing → email/phone) | ⚠️ Needs fix |
| 2 | `Search___Verify/` | `search.py` | Search + verify existing leads pipeline | ⚠️ Needs fix |
| 3 | `TPOscraper/` | `TPOscrapper.py` | WordPress AJAX directory scraper | ✅ Ready |
| 4 | `Ukala/` | `ukala.py` | JSON API directory harvester | ✅ Ready |
| 5 | `PMScrapper/` | `PMscrapper.py` | Paginated member directory (listing→profile) | ⚠️ Needs fix |
| 6 | `TrustPilot/` | `TPcc.py` | Next.js site scraper via Selenium+HTTP | ✅ Ready |
| 7 | `Google_Maps_Business_Scraper/` | `googlemaps.py` | Google Maps scraper (single file) | ⚠️ Needs fix |
| 8 | `Google_Maps_Search/` | `googlemaps.py` | Google Maps scraper (modular, 7 files) | ⚠️ Needs fix |
| 9 | `Enrich_Emails/` | `Enrich_emails_final.py` | Email enricher from websites | ✅ Ready |
| 10 | `websirefinder/` | `websitefinder_final.py` | Website finder (email domain + Bing) | ✅ Ready |
| 11 | `Hyperlink/` | `hyperlink.py` | Excel URL → hyperlink converter | ✅ Ready |
| 12 | `Portfolio/` | `index.html` | Portfolio website | ✅ Ready |

---

## 2. Critical Issues — Fix These First

### Issue 1 — `with sync_playwright()` Pattern (MOST CRITICAL)

Every generalized scraper that uses Playwright uses `with sync_playwright() as p:`, which **causes crashes on your Windows setup**. You must replace it everywhere.

**Find this pattern in ALL scraper files:**
```python
# ❌ BREAKS on your Windows machine
with sync_playwright() as p:
    browser = p.chromium.launch(...)
    ...
```

**Replace with this pattern:**
```python
# ✅ Works on your Windows machine
pw = sync_playwright().__enter__()
try:
    browser = pw.chromium.launch(...)
    ...
finally:
    pw.__exit__(None, None, None)
```

**Files that need this fix:**
- `searchpy/fetcher.py` → `launch_browser()` function
- `searchpy/scrape_passes.py` → `run_pass3()` function
- `searchpy/search.py` → `_bing_playwright_fallback()` function
- `Search___Verify/search_runner.py` → `_bing_playwright_fallback()` and `run_pass3()`
- `Google_Maps_Business_Scraper/maps_scraper.py` → `run()` function
- `Google_Maps_Search/main.py` → `run()` function
- `Enrich_Emails/enricher.py` → `run_pass2()` function
- `websirefinder/website_finder.py` → `run_pass2()` function

---

### Issue 2 — Missing `config.yaml` Files

All generalized tools require a `config.yaml` but none was included in the zips. Each project folder needs its own `config.yaml`. Templates are provided below in each project's README section.

---

### Issue 3 — Missing `__init__.py` in Package Projects

`searchpy` and `Google_Maps_Search` are structured as Python packages but are missing `__init__.py` files. The scraper uses relative imports like `from .controls import ...` which only works if Python treats the folder as a package.

**Fix — create empty `__init__.py` in:**
- `searchpy/modules/__init__.py` (if `modules/` subfolder exists; otherwise in `searchpy/`)
- `Google_Maps_Search/scraper/` (if organized as a package)

Actually, looking at the code more carefully: `searchpy/scraper.py` does `from modules.config_loader import ...` — so you need a `modules/` subfolder inside `searchpy/` and to move the module files there. Or rename all the imports to direct imports. **Simplest fix:** run scraper.py from the `searchpy/` directory and rename imports to non-relative.

---

### Issue 4 — Missing Dependencies

These packages are used but not in `requirements.txt`:

| Project | Missing Package | Install Command |
|---------|----------------|-----------------|
| `PMScrapper/` | `python-dotenv` | `pip install python-dotenv` |
| `Search___Verify/` | `pandas`, `openpyxl` | `pip install pandas openpyxl` |
| `TPOscraper/` | `pyyaml` | `pip install pyyaml` |
| `Ukala/` | `pyyaml` | `pip install pyyaml` |
| `TrustPilot/` | `selenium`, `webdriver-manager` | `pip install selenium webdriver-manager` |
| All | `pyyaml` | `pip install pyyaml` |

---

### Issue 5 — Windows-Only Audio (Minor)

Your originals used `import winsound` and `import msvcrt` at the top level, which crashes on Linux/Mac. The generalized versions handle this correctly with try/except. Leave as-is — this is already fixed in the generalized versions.

---

## 3. Environment Setup

All projects share your existing venv at `D:\AFAQ DATA\`.

```bash
# Activate your venv first
cd "D:\AFAQ DATA"
Scripts\activate

# Install all missing packages at once
pip install pyyaml python-dotenv pandas openpyxl requests beautifulsoup4 httpx playwright selenium webdriver-manager --break-system-packages

# Install Playwright browsers (if not done)
playwright install chromium
```

**VS Code settings** — in each project folder's `.vscode/settings.json`:
```json
{
    "python.defaultInterpreterPath": "D:\\AFAQ DATA\\Scripts\\python.exe"
}
```

---

## 4. Project-by-Project Analysis

### What Changed: Original → Generalized

#### `search.py` → `searchpy/` and `Search___Verify/`
| Aspect | Original | Generalized |
|--------|----------|-------------|
| Target | Hardcoded: "commercial and residential property managers" in London | Any search query in any city |
| Phone format | UK-specific regex | Configurable via config.yaml |
| Skip domains | Hardcoded list of 30+ UK domains | Config-driven list |
| Output | Single CSV | CSV or Excel, configurable prefix |
| Cross-platform | Windows only (msvcrt, winsound) | Works on Windows/Mac/Linux |
| Architecture | 1 file, ~600 lines | Modular package (5+ files) |

The `Search___Verify` version adds a **verify pipeline** — it can re-scrape an existing Excel leads database and update/verify contact details. This is a completely new capability the original didn't have.

#### `TPOscrapper.py` → `TPOscraper/scraper.py`
| Aspect | Original | Generalized |
|--------|----------|-------------|
| Target | Hardcoded: tpos.co.uk, London bounding box | Any WordPress AJAX directory via config.yaml |
| Sectors | Hardcoded 5 property sectors | Configurable list of sectors |
| Geographic filter | London lat/lng hardcoded | Optional `geo_bounds` in config |
| Nonce handling | Same logic | Same logic, better documented |
| Output | CSV + Excel | Excel only (configurable columns/colors) |

**Works on general sites?** Yes — any WordPress site using `admin-ajax.php` for search (like TPO) can be targeted by just changing `base_url`, `register_path`, `ajax_path`, and `sectors` in config.yaml.

#### `ukala.py` → `Ukala/` (6 files)
| Aspect | Original | Generalized |
|--------|----------|-------------|
| Target | Hardcoded UKALA API URL | Any REST/POST JSON API via config |
| Field mapping | Hardcoded field names | config.yaml `field_mapping` |
| Geo filter | London lat/lng hardcoded | Optional `geo_filter` section |
| Audio | Windows-only inline | Cross-platform `controls.py` |
| Output | CSV only | Excel with Data + Flagged + Summary sheets |

**Works on general sites?** Yes — any directory that returns JSON from a POST/GET API. Just change `api.url` and `field_mapping` in config.yaml.

#### `PMscrapper.py` → `PMScrapper/directory_scraper.py`
| Aspect | Original | Generalized |
|--------|----------|-------------|
| Target | Hardcoded: propertymark.co.uk | Any listing→profile directory pattern |
| Cookies | Hardcoded session cookie | config.yaml or `SCRAPER_COOKIES` env var |
| London filter | London postcode regex hardcoded | `location_filter_regex` in config |
| Categories | Service badges specific to Propertymark | Configurable `badge_image_keywords` |
| Output | Per-category CSVs | Single Excel workbook (one sheet per category + Summary) |

**Works on general sites?** Yes — any site with a paginated member listing page and individual profile pages. Requires updating the CSS selectors in config.yaml.

#### `TPcc.py` → `TrustPilot/` (8 files)
This is the most impressive transformation. Original was one 700-line file. Generalized splits into:
- `browser.py` — Chrome launch + Selenium connection
- `checkpoint.py` — atomic JSON checkpointing
- `controls.py` — keyboard + command file controls (pynput-based, cross-platform)
- `extractor.py` — config-driven `__NEXT_DATA__` JSON path resolver
- `fetcher.py` — parallel HTTP profile fetcher with retry
- `logger.py` — rotating log file setup
- `output.py` — Excel Data + Summary sheets
- `parser.py` — phone/postcode/category cleaning
- `scraper.py` — main entry point

**Works on general sites?** Yes — any Next.js site that embeds data in `__NEXT_DATA__` script tag. Configure field paths in `config.json` under `data_paths`.

#### `googlemaps.py` → `Google_Maps_Business_Scraper/maps_scraper.py`
| Aspect | Original | Generalized |
|--------|----------|-------------|
| Search zones | London postcodes hardcoded (80+ entries) | `region_zones` list in config.yaml |
| Categories | 5 London property categories hardcoded | `search.queries` list in config |
| Geographic filter | London lat/lng hardcoded | `geography` bounding box in config |
| Email scraping | Optional flag | Same, configurable |
| Mode | Always iterates all postcodes | `city` or `mega` mode via CLI flag |

#### `googlemaps.py` → `Google_Maps_Search/` (7 files)
This is an even more modular version of the same original. Uses a package structure:
- `browser.py` — BrowserManager context manager
- `config.py` — YAML config loader
- `controls.py` — ControlHandler with stdin + Windows key listener
- `extractor.py` — scroll, click, extract place data
- `filters.py` — geographic and category filters
- `storage.py` — Excel/CSV I/O, checkpoint, done-queries log
- `main.py` — orchestrator

**Note:** You have two different generalizations of `googlemaps.py`. The `Google_Maps_Business_Scraper` version is a single-file tool (easier to run). The `Google_Maps_Search` version is a proper multi-file package (more professional for GitHub).

#### `Enrich_emails_final.py` → `Enrich_Emails/enricher.py`
| Aspect | Original | Generalized |
|--------|----------|-------------|
| Column names | Hardcoded "Company Name", "Website" | Configurable via config.yaml `columns` |
| Output | CSV only | Excel with Run Stats sheet + CSV backup |
| Contact paths | Hardcoded /contact, /about | Configurable list |
| User agents | Single UA string | Rotating pool of 5 UAs |
| Rate limit | Fixed 0.1s sleep | Configurable min/max range |

#### `websitefinder_final.py` → `websirefinder/website_finder.py`
| Aspect | Original | Generalized |
|--------|----------|-------------|
| Input file | Hardcoded filename | Auto-detect or CLI `--input` |
| Skip domains | Hardcoded UK-specific list | Configurable in config.yaml |
| Category hints | Property-specific hints | Configurable `category_hints` map |
| Controls | Windows only (msvcrt) | Cross-platform stdin thread |
| Log | None | Rotating log file |

#### `hyperlink.py` → `Hyperlink/hyperlink_tool.py`
Most dramatic simplification → expansion. Original was 10 lines. Generalized adds:
- CLI with `--col` flag for specifying columns by name or number
- Auto-detection of URL columns by header keyword and content scan
- Multi-column support
- Timestamped output filenames
- YAML config support
- Full run summary

---

## 5. Per-Project README

---

### 📁 `searchpy/` — Search-Driven Contact Scraper

**What it does:** Queries Bing for any search term, collects business website URLs, then scrapes each for email and phone number.

**Architecture:** 3-pass pipeline
- Pass 1: Bing via requests (fast) → Playwright fallback if blocked
- Pass 2: Concurrent requests (thread pool, 10 workers)
- Pass 3: Playwright headless browser (JS-heavy sites)

**Setup:**
```bash
# 1. Create config.yaml in the searchpy/ folder:
```

```yaml
# searchpy/config.yaml
search:
  query: "property management companies in london"
  pages: 10
  locale: "en-GB"
  country_code: "GB"
  pause_seconds: 2.0

output:
  category: "Property Management"
  format: "csv"           # or "excel"
  directory: "."
  filename_prefix: "PropertySearch"

phone:
  regex: '(?:(?:\+44|0044)\s?|0)(?:\d[\s\-]?){9,10}\d'
  min_digits: 10
  max_digits: 11
  preferred_prefix: "020"

email:
  skip_keywords: ["noreply", "no-reply", "privacy", "gdpr", "spam"]
  generic_keywords: ["info", "contact", "hello", "enquiries", "admin"]
  junk_domains: ["sentry.io", "example.com", "schema.org", "w3.org"]

skip_domains:
  - "facebook.com"
  - "twitter.com"
  - "linkedin.com"
  - "rightmove.co.uk"
  - "zoopla.co.uk"
  - "google.com"
  - "bing.com"
  - "wikipedia.org"

http:
  timeout_connect: 4
  timeout_read: 6
  hard_timeout: 8
  max_workers: 10
  playwright_restart_every: 100

schedule:
  stop_at: "23:00"
  min_disk_mb: 500

playwright:
  headless: true
  timeout_ms: 8000
  restart_every: 100
```

```bash
# 2. Fix the Playwright pattern (REQUIRED on your machine)
# In fetcher.py, scrape_passes.py, and search.py:
# Replace: with sync_playwright() as p:
# With the __enter__() pattern

# 3. Fix the package structure - run from searchpy/ directory:
cd searchpy/
# Create modules/ folder if the imports break:
mkdir modules
# Move all .py files except scraper.py into modules/
# Add __init__.py:
echo "" > modules/__init__.py

# 4. Run:
python scraper.py
python scraper.py --query "letting agents london" --pages 5
python scraper.py --fresh   # clear checkpoint
python scraper.py --no-pass3  # skip Playwright
```

**Runtime controls:**
```
Keyboard: P=pause  R=resume  Q=quit  S=status
File:     echo pause > command.txt
```

**Output:** `PropertySearch_YYYYMMDD.csv` with columns: Company Name, Email, Phone, Website, Category

---

### 📁 `Search___Verify/` — Lead Search + Verify Pipeline

**What it does:** Two tools in one:
- `search` mode: Same as searchpy — finds leads via Bing
- `verify` mode: Reads an existing Excel leads database, re-visits each website, and updates/validates contact info

**Setup:**
```bash
# Create config.yaml:
```
```yaml
# Search___Verify/config.yaml
search:
  query: "property management companies in london"
  pages: 10
  locale: "en-GB"
  country_code: "GB"
  category: "Property Management"
  pause_between_pages: 2.0

verify:
  input_file: "Master_Leads.xlsx"
  sheets:
    - "Letting Agents"
    - "Property Management"
  columns:
    name: "Company Name"
    website: "Website"
    email: "Email"
    phone: "Phone"
  output_header_color: "F06623"

output:
  directory: "."
  search_prefix: "SearchResults"
  verify_prefix: "Verified"

phone:
  regex: '(?:(?:\+44|0044)\s?|0)(?:\d[\s\-]?){9,10}\d'
  normalizations:
    - {prefix: "+44", replace_with: "0", strip_chars: 3}
    - {prefix: "0044", replace_with: "0", strip_chars: 4}
  valid_lengths: [10, 11]
  preferred_prefixes: ["020"]

email:
  skip_keywords: ["noreply", "no-reply", "privacy", "gdpr"]
  generic_keywords: ["info", "contact", "hello", "enquiries"]
  junk_domains: ["sentry.io", "example.com", "w3.org"]

skip_domains:
  - "facebook.com"
  - "linkedin.com"
  - "rightmove.co.uk"
  - "zoopla.co.uk"
  - "google.com"

http:
  timeout_connect: 4
  timeout_read: 6
  hard_timeout: 8
  threads: 10
  verify_threads: 30
  playwright_restart_every: 100

runtime:
  stop_at: "23:00"
  disk_min_mb: 500
  save_every: 50
  command_file: "command.txt"

headers:
  User-Agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
```

```bash
# Run search pipeline:
python pipeline.py search

# Run verify pipeline (against your Master_Leads.xlsx):
python pipeline.py verify

# With custom config:
python pipeline.py search --config my_config.yaml
```

**Extra dependency:** Install pandas: `pip install pandas`

---

### 📁 `TPOscraper/` — WordPress AJAX Directory Scraper

**What it does:** Scrapes any WordPress directory that uses `admin-ajax.php` for search. Originally built for TPO (The Property Ombudsman), now works for any similar site.

**Setup:**
```bash
# Create config.yaml in TPOscraper/ folder:
```
```yaml
# TPOscraper/config.yaml
base_url: "https://www.tpos.co.uk"
register_path: "/register-of-businesses/"
ajax_path: "/wp-admin/admin-ajax.php"
ajax_action: "business_search"
ajax_location: "london"
ajax_status: "Membership"

sectors:
  - name: "Lettings"
    category: "Letting Agents"
  - name: "Block & Estate Management"
    category: "Block Managers"
  - name: "Residential Property Management"
    category: "Property Management"
  - name: "Sales"
    category: "Estate Agents"

geo_bounds:
  lat_min: 51.28
  lat_max: 51.70
  lng_min: -0.55
  lng_max: 0.35

crawl_websites: true
contact_paths:
  - "/contact"
  - "/contact-us"
  - "/about"
  - "/about-us"

delay_min: 1.0
delay_max: 2.0
max_pages: 9999

output:
  sheet_name: "Results"
  header_color: "F06623"
  columns: ["Company", "Email", "Phone", "Website", "Address", "Postcode", "Category", "Source"]
  column_widths: [40, 35, 16, 42, 50, 12, 26, 8]

output_prefix: "TPO_Results"
checkpoint_file: "tpo_checkpoint.json"
source_label: "TPO"

skip_domains:
  - "tpos.co.uk"
  - "facebook.com"
  - "instagram.com"
  - "linkedin.com"
  - "twitter.com"

junk_domains:
  - "example.com"
  - "google.com"
  - "w3.org"
  - "sentry.io"
```

```bash
# Run:
python scraper.py
python scraper.py --fresh    # ignore checkpoint, start fresh
python scraper.py --config my_other_directory.yaml   # target a different site
```

**To target a different WordPress AJAX directory:**
1. Find the `ajax_action` name in the site's JavaScript (look for `action:` in network requests)
2. Update `base_url`, `register_path`, `ajax_path`
3. Update `sectors` with the new site's categories
4. Adjust `geo_bounds` for your target city

**Resume:** Just re-run — it picks up from the checkpoint automatically.

---

### 📁 `Ukala/` — JSON API Directory Harvester

**What it does:** Fetches records from any REST/POST JSON API, filters by geo bounds, deduplicates, validates, and exports to Excel with Data + Flagged + Summary sheets.

**Setup:**
```bash
# Create config.yaml:
```
```yaml
# Ukala/config.yaml
api:
  url: "https://www.ukala.org.uk/wp-json/ukala/agents/by-location"
  method: "POST"
  headers:
    User-Agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/145.0.0.0 Safari/537.36"
    Content-Type: "application/x-www-form-urlencoded"
    Referer: "https://www.ukala.org.uk/agent-search/ukala-agent-directory/"
    Origin: "https://www.ukala.org.uk"
  payload:
    name: "london"
    search_type: "location"
    page: 1
    first_char: ""
    distance: 20
  response_path:
    - "data"
    - "agents"
  pagination:
    enabled: false
    max_pages: 1
    page_param: "page"

field_mapping:
  id: "id"
  name: "name"
  phone: "phone"
  website: "website"
  postcode: "post_code"

geo_filter:
  enabled: true
  lat_min: 51.28
  lat_max: 51.70
  lng_min: -0.55
  lng_max: 0.35
  lat_field: "coordinates.latitude"
  lng_field: "coordinates.longitude"

validation:
  min_name_length: 3
  require_postcode: true
  postcode_regex: "^[A-Z]{1,2}\\d"

output:
  directory: "output"
  filename_prefix: "UKALA_LettingAgents"
  category: "Letting Agent"
  source: "UKALA"

runtime:
  stop_at: "23:00"
  request_timeout: 15
  save_every: 10
  progress_every: 10
  low_disk_mb: 500
  max_consec_fail: 3
```

```bash
# Run:
python scraper.py
python scraper.py --reset     # clear checkpoint, start fresh
python scraper.py --dry-run   # just count records, don't write files
python scraper.py --config another_api.yaml
```

**To target a different JSON API:**
1. Update `api.url`, `api.method`, `api.payload`
2. Update `response_path` to navigate to the records list in the JSON
3. Update `field_mapping` to match the API's field names
4. Adjust `geo_filter` for your target city

---

### 📁 `PMScrapper/` — Member Directory Scraper (Listing→Profile Pattern)

**What it does:** Scrapes paginated member directories where you first see a list of companies, then click into each profile. Originally for Propertymark, now works for any similar site.

**Fix required:**
```bash
pip install python-dotenv
```

**Setup:**
```yaml
# PMScrapper/config.yaml
tool_name: "Propertymark Scraper"
base_url: "https://www.propertymark.co.uk"
list_path: "/find-an-expert.html"

categories:
  - name: "Residential Lettings"
  - name: "Block Management"
  - name: "Residential Sales"

all_services:
  - "block-management"
  - "residential-lettings"
  - "residential-sales"
  - "commercial-lettings"
  - "commercial-property-management"

selectors:
  card_container: ".member-item"
  profile_link: "a[href*='/company/']"
  member_name: ".member-name"
  badge_images: ".division-logos img"
  detail_section: ".member-directory-detail"

badge_image_keywords:
  "residential-lettings": "Residential Lettings"
  "residential-sales": "Residential Sales"
  "block": "Block Management"
  "commercial-lettings": "Commercial Lettings"
  "commercial-property": "Commercial Property Management"

location_filter_regex: '\b(EC[0-9]|WC[0-9]|E[0-9]|N[0-9]|NW[0-9]|SE[0-9]|SW[0-9]|W[0-9]|BR[0-9]|CR[0-9]|HA[0-9]|IG[0-9]|KT[0-9]|TW[0-9]|UB[0-9])[0-9A-Z]?\s*[0-9][A-Z]{2}\b'

verify_email: false
delay_min: 1.0
delay_max: 2.5
stop_at: "23:00"
page_size: 10

output_prefix: "Propertymark"
checkpoint_file: "pm_checkpoint.json"
log_file: "scraper.log"

base_params:
  q: "london"
  orderBy: ""
  itemclass: ".member-item"

service_param_name: "company_service"

headers:
  User-Agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/145.0.0.0 Safari/537.36"
  Accept: "text/html,application/xhtml+xml,*/*;q=0.8"
  Accept-Language: "en-US,en;q=0.9"
  Accept-Encoding: "identity"
  Connection: "close"

cookies_raw: ""  # Paste session cookie here if needed
```

```bash
# Run:
python directory_scraper.py
```

**Note:** If the site requires session cookies, paste them into `cookies_raw` in config.yaml, or set environment variable:
```bash
set SCRAPER_COOKIES=your_cookie_string_here
python directory_scraper.py
```

---

### 📁 `TrustPilot/` — Next.js Directory Scraper

**What it does:** Scrapes any Next.js website that stores data in `__NEXT_DATA__` JSON. Uses a clean Chrome profile via Selenium to avoid personalised results, then fetches profiles in parallel via HTTP.

**Dependencies:**
```bash
pip install selenium webdriver-manager openpyxl pynput
```

**Setup:**
```json
// TrustPilot/config.json
{
  "platform": {
    "name": "Trustpilot",
    "base_url": "https://www.trustpilot.com",
    "search_path": "/search",
    "profile_path": "/review",
    "source_label": "Trustpilot"
  },
  "query": {
    "search_query": "property management companies in london",
    "search_param": "query",
    "extra_params": {
      "experiment": "semantic_search_enabled"
    }
  },
  "data_paths": {
    "listing": {
      "business_units": "props.pageProps.businessUnits",
      "pagination_results": "props.pageProps.pagination.totalResults",
      "pagination_pages": "props.pageProps.pagination.totalPages",
      "slug_field": "identifyingName",
      "display_name": "displayName"
    },
    "profile": {
      "root": "props.pageProps",
      "contact_info_root": "businessUnit.contactInfo",
      "email": "businessUnit.email",
      "phone": "businessUnit.contactInfo.phone",
      "website": "businessUnit.websiteUrl",
      "postcode": "businessUnit.contactInfo.zipCode",
      "city": "businessUnit.contactInfo.city",
      "trust_score": "businessUnit.trustScore",
      "reviews": "businessUnit.numberOfReviews",
      "categories": "businessUnit.categories"
    }
  },
  "scraping": {
    "profile_threads": 10,
    "page_delay": 2.5,
    "http_timeout_connect": 5,
    "http_timeout_read": 8,
    "hard_timeout": 12,
    "retry_attempts": 3,
    "retry_base_delay": 2.0,
    "disk_min_mb": 500,
    "stop_at": "23:00"
  },
  "browser": {
    "debug_port": 9222,
    "chrome_paths": [
      "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
      "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
      "C:\\Users\\Laptop\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe"
    ]
  },
  "output": {
    "filename_prefix": "Trustpilot",
    "header_color": "F06623",
    "columns": ["Company Name", "Email", "Phone", "Website", "Postcode", "City", "Trust Score", "Reviews", "Category", "Source"],
    "column_widths": [40, 35, 14, 42, 14, 20, 12, 10, 25, 12]
  },
  "cleaning": {
    "phone_country_code": "+44",
    "phone_country_code_alt": "0044",
    "phone_local_prefix": "0",
    "phone_min_digits": 10,
    "phone_max_digits": 11,
    "postcode_pattern": "[A-Z]{1,2}[0-9]{1,2}[A-Z]?\\s+[0-9][A-Z]{2}"
  },
  "http_headers": {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://www.trustpilot.com/"
  }
}
```

```bash
# Run:
python scraper.py
python scraper.py --fresh      # clear checkpoint
python scraper.py --query "letting agents london" --threads 15
python scraper.py --stop-at 22:30
```

**How it runs:**
1. Chrome opens automatically with a clean profile
2. You confirm it's showing results in the terminal
3. Selenium connects and starts scraping
4. Profiles are fetched in parallel via HTTP (10x faster than browser)

**To target a different Next.js site:**
- Update `platform.base_url`, `platform.search_path`, `platform.profile_path`
- Update `data_paths` to match the site's JSON structure (inspect `__NEXT_DATA__` in browser DevTools)

---

### 📁 `Google_Maps_Business_Scraper/` — Google Maps Scraper (Single File)

**What it does:** Searches Google Maps for any business type across any set of location zones. Single-file version, easier to run.

**Fix required — Playwright pattern** in `maps_scraper.py` around line ~780 in the `run()` function.

**Setup:**
```yaml
# Google_Maps_Business_Scraper/config.yaml
search:
  query: "property management company"
  location: "London"

geography:
  lat_min: 51.28
  lat_max: 51.70
  lng_min: -0.55
  lng_max: 0.35
  postcode_pattern: '\b([A-Z]{1,2}\d{1,2}[A-Z]?)\s*\d[A-Z]{2}\b'
  valid_postcode_prefixes:
    - "EC" - "WC" - "E" - "N" - "NW" - "SE" - "SW" - "W"
    - "BR" - "CR" - "DA" - "EN" - "HA" - "IG" - "KT" - "RM" - "SM" - "TW" - "UB" - "WD"
  region_zones:
    - "EC1" - "EC2" - "N1" - "NW1" - "SE1" - "SW1" - "W1" - "WC1"
    # Add all your postcodes here

classification:
  keywords:
    "Property Management":
      - "property management"
      - "managing agent"
    "Letting Agent":
      - "letting"
      - "lettings"
    "Block Manager":
      - "block management"
      - "leasehold"

filters:
  skip_domains: []
  junk_emails: []
  junk_email_domains: ["sentry.io", "example.com", "w3.org"]

phone:
  country_code: "44"
  valid_prefixes: ["020", "07"]
  valid_lengths: [10, 11]
  preferred_prefix: "020"

performance:
  headless: true
  scroll_pause: 0.8
  request_delay: 0.3
  browser_restart_every: 150
  fetch_threads: 5
  http_timeout: [4, 6]
  hard_timeout: 8

output:
  directory: "output"
  filename_prefix: "GoogleMaps"
  format: "csv"

scheduling:
  stop_at: "23:00"
  disk_min_mb: 500
```

```bash
python maps_scraper.py --mode city   # single query
python maps_scraper.py --mode mega   # iterate all region_zones
```

---

### 📁 `Google_Maps_Search/` — Google Maps Scraper (Modular)

More professional version of the same scraper. Run from `main.py`.

**Fix required:** In `main.py` around line ~220, fix the `with sync_playwright()` pattern.

**Setup:** Create the same `config.yaml` as above but inside the `Google_Maps_Search/` folder. Then also update selectors in `config.py`.

```bash
python main.py
python main.py --config custom.yaml
python main.py --fresh
```

---

### 📁 `Enrich_Emails/` — Email Enricher

**What it does:** Takes a CSV of companies + websites, visits each site, and extracts contact emails. Two-pass: fast HTTP first, then Playwright for JS-heavy sites.

**Setup:**
```yaml
# Enrich_Emails/config.yaml
input_file: "Missing_Emails_ForEnricher.csv"
output_file: ""    # auto-generates Found_Emails_YYYYMMDD.xlsx
checkpoint_file: "enrich_checkpoint.json"
command_file: "command.txt"

contact_paths:
  - "/contact"
  - "/contact-us"
  - "/about"
  - "/about-us"

http_timeout: [4, 6]
playwright_timeout: 8000
browser_restart_every: 150
stop_at: "23:00"

rate_limit:
  min_seconds: 0.1
  max_seconds: 0.5

output_format: "xlsx"

columns:
  company_name: "Company Name"
  website: "Website"
  email: "Email"
  category: "Category"

skip_email_keywords:
  - "noreply" - "no-reply" - "privacy" - "gdpr" - "spam" - "donotreply"

generic_email_keywords:
  - "info" - "contact" - "hello" - "enquiries" - "admin" - "office"

junk_email_domains:
  - "sentry.io" - "example.com" - "schema.org" - "w3.org"
```

**Input CSV format:**
```
Company Name,Website,Category
Smith & Jones Property,https://smithjones.co.uk,Property Management
```

**Fix required:** In `enricher.py`, fix the `with sync_playwright()` pattern in `run_pass2()`.

```bash
python enricher.py
python enricher.py --input companies.csv --fresh
python enricher.py --config my_config.yaml
```

**Output:** Excel file with two sheets — "Results" (emails found) and "Run Stats" (summary).

---

### 📁 `websirefinder/` — Website Finder

**What it does:** Given a CSV of companies with no website, finds each one using two methods:
- Pass 1: If the company has an email, verify the email domain as a website
- Pass 2: Use Playwright/Bing to search for the company and find its website

**Setup:**
```yaml
# websirefinder/config.yaml
input_file: ""    # auto-detect Missing_Websites_*.csv
input_pattern: "Missing_Websites_*.csv"
output_prefix: "Found_Websites"
checkpoint_file: "website_finder_checkpoint.json"
cmd_file: "command.txt"
log_file: "website_finder.log"
log_level: "INFO"

http_timeout: [4, 6]
thread_timeout: 8
search_pause: 2.0
stop_at: "23:00"
min_disk_mb: 500
checkpoint_interval: 100

search_engine_url: "https://www.bing.com/search?q={query}"
results_selector: "#b_results"
search_location_hint: "official website"

category_hints:
  "letting": "letting agent"
  "estate": "estate agent"
  "block": "block management"
  "property": "property management"
  "facilities": "facilities management"

skip_email_domains:
  - "gmail.com" - "hotmail.com" - "yahoo.com" - "outlook.com"
  - "icloud.com" - "live.com" - "protonmail.com"

skip_result_domains:
  - "facebook.com" - "linkedin.com" - "twitter.com"
  - "rightmove.co.uk" - "zoopla.co.uk" - "google.com"
  - "bing.com" - "wikipedia.org" - "trustpilot.com"

col_name: "Company Name"
col_email: "Email"
col_phone: "Contact Number"
col_category: "Category"
```

**Fix required:** In `website_finder.py`, fix the `with sync_playwright()` pattern in `run_pass2()`.

**Input CSV format:**
```
Company Name,Email,Contact Number,Category
ABC Lettings,,02071234567,Letting Agent
```

```bash
python website_finder.py
python website_finder.py --input my_companies.csv --fresh
python website_finder.py --no-browser   # skip Pass 2
```

---

### 📁 `Hyperlink/` — Excel Hyperlink Tool

**What it does:** Converts plain-text URLs in Excel to clickable hyperlinks with standard blue underline style. Auto-detects URL columns or you can specify them.

**No config.yaml needed for basic use.**

```bash
# Basic use — auto-detect URL columns:
python hyperlink_tool.py my_leads.xlsx

# Specify column by name:
python hyperlink_tool.py my_leads.xlsx --col Website

# Multiple columns:
python hyperlink_tool.py my_leads.xlsx --col Website --col LinkedIn

# Specify column by number (1-based):
python hyperlink_tool.py my_leads.xlsx --col 4

# With config.yaml:
python hyperlink_tool.py
```

**config.yaml (optional):**
```yaml
# Hyperlink/config.yaml
input_file: "Trustpilot_20260406.xlsx"
url_columns:
  - "Website"
  - "Profile URL"
header_row: 1
hyperlink_color: "0563C1"
auto_detect: true
```

**Output:** Creates a new file `<original_name>_hyperlinked_YYYYMMDD_HHMMSS.xlsx` — never overwrites the original.

---

## 6. GitHub Publishing Guide

### What to Include

```
your-repo/
├── README.md                    ← Main portfolio description
├── searchpy/
│   ├── scraper.py
│   ├── config.yaml.example      ← Rename from config.yaml, blank out secrets
│   ├── requirements.txt
│   └── README.md
├── TPOscraper/
│   ├── scraper.py
│   ├── config.yaml.example
│   ├── requirements.txt
│   └── README.md
... (same pattern for each project)
```

### What to EXCLUDE — Add to `.gitignore`

```gitignore
# Output files — don't share scraped data
*.csv
*.xlsx
*.xls

# Checkpoints — user-specific state
*checkpoint*.json
*_checkpoint.json
gmaps_checkpoint.json
gmaps_done_queries.json

# Cookies and credentials — NEVER commit these
config.yaml          ← Use config.yaml.example instead
.env
*.env

# Chrome profiles
chrome_clean_profile/
scraper_clean_profile/

# Logs
*.log
logs/

# Progress files
*_progress.txt

# Python cache
__pycache__/
*.pyc
*.pyo
.venv/

# VS Code
.vscode/
```

### How to Create Safe Config Examples

For each project, create `config.yaml.example` with sensitive values replaced:

```yaml
# config.yaml.example — copy to config.yaml and fill in your values

api:
  url: "https://example.com/api/agents"      # ← Replace with real URL
  headers:
    Authorization: "Bearer YOUR_API_KEY_HERE" # ← Never commit real keys

cookies_raw: ""   # ← Paste your session cookie here (from browser DevTools)
```

### Repository Structure Suggestion

Create one repo per project (cleaner) or one mono-repo with all projects in subfolders. For a portfolio, one repo works well:

**Repo name:** `lead-generation-scrapers` or `b2b-lead-tools`

**GitHub Description:** "A collection of configurable, resumable B2B lead generation scrapers — Google Maps, TPO, UKALA, Trustpilot, and more. Built for the UK property management sector."

**Topics/Tags to add:** `python`, `playwright`, `web-scraping`, `lead-generation`, `b2b`, `uk-property`, `google-maps`

---

## 7. Testing Checklist

Run each project in this order to test on general websites.

### Quick Smoke Tests (5 minutes each)

#### `TPOscraper/` Test
```bash
# Test with a different WordPress directory — e.g., a church finder or business directory
# Change config.yaml: base_url, sectors (1 sector only), max_pages: 2
python scraper.py
# Expected: Should fetch 2 pages, extract some names/emails
```

#### `Ukala/` Test
```bash
# Use --dry-run to test API connection without writing files
python scraper.py --dry-run
# Expected: Prints record count from API, shows geo filter results
```

#### `Hyperlink/` Test (easiest — no Playwright needed)
```bash
# Create a test Excel file with a Website column containing URLs
python hyperlink_tool.py test.xlsx --col Website
# Expected: Creates test_hyperlinked_YYYYMMDD.xlsx with clickable links
```

#### `websitefinder/` Test
```bash
# Create a tiny test CSV:
# Company Name,Email,Category
# RICS,info@rics.org,Property
# Pass --no-browser to skip Playwright:
python website_finder.py --input test.csv --no-browser --fresh
# Expected: Finds rics.org from the email domain
```

#### `Enrich_Emails/` Test
```bash
# Create a tiny test CSV:
# Company Name,Website,Category
# RICS,https://www.rics.org,Property
python enricher.py --input test.csv --fresh
# Expected: Visits rics.org and extracts email if available
```

### Common Errors & Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| `ModuleNotFoundError: No module named 'playwright'` | Not installed | `pip install playwright && playwright install chromium` |
| `ModuleNotFoundError: No module named 'yaml'` | PyYAML not installed | `pip install pyyaml` |
| `ModuleNotFoundError: No module named 'dotenv'` | python-dotenv not installed | `pip install python-dotenv` |
| `FileNotFoundError: config.yaml` | Config file missing | Copy `config.yaml.example` to `config.yaml` and fill in values |
| `with sync_playwright()` crash | Windows compatibility | Replace with `sync_playwright().__enter__()` + `finally` block |
| `ImportError: cannot import name 'msvcrt'` | Running on non-Windows | Already handled in generalized versions via try/except |
| `ConnectionResetError (10054)` | Server closed connection | Normal — the scraper retries automatically |
| `playwright._impl._errors.TargetClosedError` | Browser closed unexpectedly | Google Maps scraper handles this — restarts browser automatically |
| `Checkpoint is empty` | Corrupt checkpoint file | Delete the checkpoint JSON file and restart |
| `CAPTCHA / blocked by site` | Too many requests | Increase `delay_min`/`delay_max` in config |

---

*Generated by Claude | For use with Afaq's 360 Safety Checks lead pipeline*
