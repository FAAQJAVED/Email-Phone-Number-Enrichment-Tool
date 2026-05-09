# Contributing to Email & Phone Number Enrichment Tool

Contributions are welcome — bug fixes, new cookie-dismiss selectors, and additional test cases especially. Please read the guidelines below before opening a pull request.

## Setting up your development environment

```bash
git clone https://github.com/FAAQJAVED/Email-Phone-Number-Enrichment-Tool.git
cd Email-Phone-Number-Enrichment-Tool
pip install -r requirements.txt -r requirements-dev.txt
python -m playwright install chromium
```

## Running the tests

```bash
pytest -v
```

With coverage:

```bash
pytest --cov=core --cov=enricher --cov-report=term-missing
```

All 78 tests are pure-function and require no browser or internet connection.

## What is open for contribution

- Additional `cookie_selectors` for common consent banner frameworks
- New `junk_email_domains` entries
- Fixes to phone regex patterns for non-UK number formats
- Bug reports with a minimal reproducible example

## Pull request checklist

- [ ] All existing tests pass (`pytest -v`)
- [ ] New behaviour is covered by a test in `tests/test_core.py`
- [ ] `config.example.yaml` updated if a new config key is added
- [ ] No secrets, scraped data, or `.env` files committed

## Code style

Follow the existing style in the file you are editing. No formatter is enforced but keep line length reasonable (~100 chars) and use descriptive variable names.
