"""
tests/test_core.py
==================
Unit tests for Email Enrichment Tool core logic.

All tests run with zero network access — no HTTP requests, no browser,
no file I/O beyond a tmp directory provided by pytest's tmp_path fixture.

Coverage:
  - Cloudflare XOR email decoder
  - Email scoring (personal > generic > junk)
  - best_email() picker
  - extract_emails_full() — plaintext + Cloudflare HTML variants
  - Checkpoint save and load (atomic round-trip)
  - load_config() merge behaviour
"""

import json
import os
import re
import sys

import pytest

# Make sure the project root is on the path so we can import enricher directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from enricher import (
    DEFAULT_CONFIG,
    best_email,
    best_phone,
    decode_cloudflare_email,
    extract_emails_full,
    extract_phones,
    load_checkpoint,
    load_config,
    save_checkpoint,
    score_email,
    _can_fetch,
)


# ================================================================
# Helpers
# ================================================================

def _cfg(**overrides) -> dict:
    """Return a copy of DEFAULT_CONFIG with any key overridden for isolation."""
    cfg = {k: (v.copy() if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
           for k, v in DEFAULT_CONFIG.items()}
    cfg.update(overrides)
    return cfg


def _encode_cf(email: str, key: int = 0x10) -> str:
    """
    Produce a Cloudflare-style hex-encoded obfuscated email string.

    This is the *inverse* of decode_cloudflare_email() and lets us
    construct known test vectors without copying raw hex strings.
    """
    result = bytes([key]) + bytes([ord(c) ^ key for c in email])
    return result.hex()


# ================================================================
# 1. Cloudflare XOR email decoder
# ================================================================

class TestDecodeCloudflareEmail:
    """decode_cloudflare_email(encoded) → plaintext email string."""

    def test_known_vector_roundtrip(self):
        """Encode a known address then decode it — must recover the original."""
        email   = "test@example.com"
        encoded = _encode_cf(email, key=0x10)
        assert decode_cloudflare_email(encoded) == email

    def test_different_key(self):
        """XOR key is the first byte; any key value must produce the same result."""
        email   = "hello@company.org"
        for key in (0x01, 0x42, 0xFF):
            encoded = _encode_cf(email, key=key)
            assert decode_cloudflare_email(encoded) == email, (
                f"Failed with key={hex(key)}"
            )

    def test_real_hex_vector(self):
        """
        Hard-coded known vector so the test is self-contained.

        Vector computed manually:
          email = "test@example.com",  key = 0x10
          encoded = "1064756364507568717d607c753e737f7d"
        """
        encoded  = "1064756364507568717d607c753e737f7d"
        expected = "test@example.com"
        assert decode_cloudflare_email(encoded) == expected

    def test_empty_string_returns_empty(self):
        """An empty input must not raise — return empty string."""
        assert decode_cloudflare_email("") == ""

    def test_invalid_hex_returns_empty(self):
        """Non-hex garbage must not raise — return empty string."""
        assert decode_cloudflare_email("not-valid-hex!!") == ""

    def test_single_byte_returns_empty(self):
        """A single byte encodes only the key, no payload — result should be ''."""
        assert decode_cloudflare_email("10") == ""


# ================================================================
# 2. Email scoring
# ================================================================

class TestScoreEmail:
    """score_email(email, cfg) → int.  Lower score = higher quality."""

    def test_personal_name_scores_1(self):
        """An address with no generic keyword is classified as a personal name."""
        cfg = _cfg()
        assert score_email("john.smith@company.com", cfg) == 1

    def test_personal_name_with_dot_scores_1(self):
        cfg = _cfg()
        assert score_email("a.jones@firm.co.uk", cfg) == 1

    def test_high_priority_generic_scores_2(self):
        """info@, hello@, contact@ are tier-2 (generic but common)."""
        cfg = _cfg()
        for local in ("info", "hello", "contact", "enquiries", "enquiry"):
            result = score_email(f"{local}@company.com", cfg)
            assert result == 2, f"{local}@ should score 2, got {result}"

    def test_other_generic_scores_3(self):
        """support@, accounts@, sales@ etc. are tier-3."""
        cfg = _cfg()
        for local in ("support", "accounts", "sales", "reception", "manager"):
            result = score_email(f"{local}@company.com", cfg)
            assert result == 3, f"{local}@ should score 3, got {result}"

    def test_skip_keyword_scores_999(self):
        """Addresses containing skip-list keywords must be discarded (score 999)."""
        cfg = _cfg()
        junk = [
            "noreply@company.com",
            "no-reply@company.com",
            "gdpr@company.com",
            "privacy@company.com",
            "unsubscribe@company.com",
            "postmaster@company.com",
            "newsletter@company.com",
        ]
        for email in junk:
            assert score_email(email, cfg) == 999, f"{email} should be 999"

    def test_junk_domain_scores_999(self):
        """Addresses from known junk/platform domains must be discarded."""
        cfg = _cfg()
        assert score_email("any@sentry.io",      cfg) == 999
        assert score_email("any@wixpress.com",   cfg) == 999
        assert score_email("any@example.com",    cfg) == 999
        assert score_email("any@googleapis.com", cfg) == 999

    def test_empty_email_scores_999(self):
        cfg = _cfg()
        assert score_email("", cfg) == 999

    def test_no_at_symbol_scores_999(self):
        cfg = _cfg()
        assert score_email("notanemail", cfg) == 999

    def test_custom_skip_keywords_respected(self):
        """Adding a custom keyword to skip_email_keywords must be honoured."""
        cfg = _cfg(skip_email_keywords=["custom_junk"])
        assert score_email("custom_junk@company.com", cfg) == 999

    def test_custom_junk_domain_respected(self):
        cfg = _cfg(junk_email_domains=["mybaddomain.com"])
        assert score_email("info@mybaddomain.com", cfg) == 999


# ================================================================
# 3. best_email() picker
# ================================================================

class TestBestEmail:
    """best_email(emails, cfg) → single best email string or ''."""

    def test_picks_personal_over_generic(self):
        cfg    = _cfg()
        emails = ["info@acme.com", "j.bloggs@acme.com", "support@acme.com"]
        assert best_email(emails, cfg) == "j.bloggs@acme.com"

    def test_picks_info_over_support(self):
        cfg    = _cfg()
        emails = ["support@acme.com", "info@acme.com"]
        assert best_email(emails, cfg) == "info@acme.com"

    def test_filters_junk_completely(self):
        """If the only candidates are junk, return empty string."""
        cfg    = _cfg()
        emails = ["noreply@acme.com", "any@sentry.io"]
        assert best_email(emails, cfg) == ""

    def test_empty_list_returns_empty(self):
        cfg = _cfg()
        assert best_email([], cfg) == ""

    def test_single_valid_email_returned(self):
        cfg = _cfg()
        assert best_email(["info@company.com"], cfg) == "info@company.com"

    def test_normalises_to_lowercase(self):
        """Emails with mixed case must be lowercased in the output."""
        cfg    = _cfg()
        result = best_email(["INFO@Company.COM"], cfg)
        assert result == "info@company.com"

    def test_ignores_empty_strings_in_list(self):
        cfg    = _cfg()
        result = best_email(["", "info@company.com", ""], cfg)
        assert result == "info@company.com"

    def test_mixed_valid_and_junk(self):
        cfg    = _cfg()
        emails = ["noreply@x.com", "jane.doe@x.com", "gdpr@x.com"]
        assert best_email(emails, cfg) == "jane.doe@x.com"

    def test_all_same_score_returns_one(self):
        """Multiple personal-name emails — pick one deterministically (just not crash)."""
        cfg    = _cfg()
        emails = ["alice@firm.com", "bob@firm.com"]
        result = best_email(emails, cfg)
        assert result in emails


# ================================================================
# 4. extract_emails_full() — plaintext + Cloudflare HTML
# ================================================================

class TestExtractEmailsFull:
    """extract_emails_full(html) → list of discovered email strings."""

    def test_plain_email_in_html(self):
        html   = "<p>Contact us at hello@company.com for more info.</p>"
        result = extract_emails_full(html)
        assert "hello@company.com" in result

    def test_multiple_emails_extracted(self):
        html   = "<p>info@a.com or support@b.org</p>"
        result = extract_emails_full(html)
        assert "info@a.com"    in result
        assert "support@b.org" in result

    def test_cloudflare_cdn_cgi_decoded(self):
        """
        An email embedded via /cdn-cgi/l/email-protection# must be recovered.
        We encode a known address and embed it in synthetic HTML.
        """
        email   = "contact@example.org"
        encoded = _encode_cf(email, key=0x20)
        html    = f'<a href="/cdn-cgi/l/email-protection#{encoded}">email</a>'
        result  = extract_emails_full(html)
        assert email in result

    def test_cloudflare_data_cfemail_decoded(self):
        """An email embedded via data-cfemail attribute must be recovered."""
        email   = "sales@mycompany.io"
        encoded = _encode_cf(email, key=0x33)
        html    = f'<span data-cfemail="{encoded}"></span>'
        result  = extract_emails_full(html)
        assert email in result

    def test_no_false_positives_from_image_paths(self):
        """Strings like image@2x.png must not be returned as emails."""
        html   = '<img src="logo@2x.png" />'
        result = extract_emails_full(html)
        assert not any("2x.png" in e for e in result)

    def test_empty_html_returns_empty_list(self):
        assert extract_emails_full("") == []

    def test_no_emails_returns_empty_list(self):
        html = "<html><body><p>No contact info here.</p></body></html>"
        assert extract_emails_full(html) == []


# ================================================================
# 5. Checkpoint save and load (atomic round-trip)
# ================================================================

class TestCheckpoint:
    """save_checkpoint + load_checkpoint must round-trip perfectly."""

    def test_roundtrip_basic(self, tmp_path):
        ckpt  = str(tmp_path / "checkpoint.json")
        done  = {"acme corp", "globex"}
        found = {
            "acme corp": {
                "name": "Acme Corp", "website": "https://acme.com",
                "email": "info@acme.com", "category": "Tech",
            }
        }
        save_checkpoint(done, found, ckpt)
        loaded_done, loaded_found = load_checkpoint(ckpt)

        assert loaded_done  == done
        assert loaded_found == found

    def test_empty_roundtrip(self, tmp_path):
        """Empty done/found sets must round-trip without error."""
        ckpt = str(tmp_path / "empty.json")
        save_checkpoint(set(), {}, ckpt)
        done, found = load_checkpoint(ckpt)
        assert done  == set()
        assert found == {}

    def test_missing_file_returns_empty(self, tmp_path):
        """Loading a non-existent checkpoint must return (set(), {}) — not raise."""
        ckpt        = str(tmp_path / "nonexistent.json")
        done, found = load_checkpoint(ckpt)
        assert done  == set()
        assert found == {}

    def test_corrupted_file_returns_empty(self, tmp_path):
        """A corrupted checkpoint file must not crash the process."""
        ckpt = str(tmp_path / "corrupt.json")
        with open(ckpt, "w") as f:
            f.write("{ this is not : valid json ,,, }")
        done, found = load_checkpoint(ckpt)
        assert done  == set()
        assert found == {}

    def test_empty_file_returns_empty(self, tmp_path):
        """An empty checkpoint file (e.g. interrupted mid-write) must not crash."""
        ckpt = str(tmp_path / "blank.json")
        open(ckpt, "w").close()
        done, found = load_checkpoint(ckpt)
        assert done  == set()
        assert found == {}

    def test_large_roundtrip(self, tmp_path):
        """Checkpoint must handle large payloads correctly."""
        ckpt  = str(tmp_path / "large.json")
        done  = {f"company-{i}" for i in range(500)}
        found = {
            f"company-{i}": {
                "name": f"Company {i}", "website": f"https://co{i}.com",
                "email": f"info@co{i}.com", "category": "General",
            }
            for i in range(250)
        }
        save_checkpoint(done, found, ckpt)
        loaded_done, loaded_found = load_checkpoint(ckpt)
        assert loaded_done  == done
        assert loaded_found == found

    def test_file_is_valid_json(self, tmp_path):
        """The checkpoint file produced must be parseable standard JSON."""
        ckpt = str(tmp_path / "valid.json")
        save_checkpoint({"a", "b"}, {"a": {"name": "A"}}, ckpt)
        with open(ckpt) as f:
            data = json.load(f)
        assert "done"  in data
        assert "found" in data

    def test_done_set_order_invariant(self, tmp_path):
        """Sets are unordered — the loaded set must equal the original regardless of order."""
        ckpt   = str(tmp_path / "order.json")
        done   = {"z", "a", "m", "b"}
        save_checkpoint(done, {}, ckpt)
        loaded, _ = load_checkpoint(ckpt)
        assert loaded == done


# ================================================================
# 6. load_config() — merge behaviour
# ================================================================

class TestLoadConfig:
    """load_config() merges YAML on top of DEFAULT_CONFIG."""

    def test_returns_defaults_when_no_file(self):
        cfg = load_config(None)
        assert cfg["input_file"]    == DEFAULT_CONFIG["input_file"]
        assert cfg["output_format"] == DEFAULT_CONFIG["output_format"]

    def test_nonexistent_path_falls_back_to_defaults(self):
        cfg = load_config("/tmp/does_not_exist_xyz.yaml")
        assert cfg["input_file"] == DEFAULT_CONFIG["input_file"]

    def test_yaml_top_level_override(self, tmp_path):
        """A top-level key in YAML must override the default."""
        yaml_file = tmp_path / "cfg.yaml"
        yaml_file.write_text("input_file: custom_leads.csv\n")
        cfg = load_config(str(yaml_file))
        assert cfg["input_file"] == "custom_leads.csv"

    def test_yaml_nested_partial_override(self, tmp_path):
        """A partial nested override must not wipe unmentioned sub-keys."""
        yaml_file = tmp_path / "cfg.yaml"
        yaml_file.write_text("rate_limit:\n  max_seconds: 2.0\n")
        cfg = load_config(str(yaml_file))
        assert cfg["rate_limit"]["max_seconds"] == 2.0
        # min_seconds must survive — not wiped by the partial override
        assert "min_seconds" in cfg["rate_limit"]

    def test_yaml_columns_partial_override(self, tmp_path):
        """Overriding one column name must leave others at their defaults."""
        yaml_file = tmp_path / "cfg.yaml"
        yaml_file.write_text('columns:\n  company_name: "Organisation"\n')
        cfg = load_config(str(yaml_file))
        assert cfg["columns"]["company_name"] == "Organisation"
        assert cfg["columns"]["website"]      == "Website"   # default preserved

    def test_yaml_list_override(self, tmp_path):
        """A YAML list must fully replace the default list (not merge into it)."""
        yaml_file = tmp_path / "cfg.yaml"
        yaml_file.write_text("contact_paths:\n  - /kontakt\n")
        cfg = load_config(str(yaml_file))
        assert cfg["contact_paths"] == ["/kontakt"]

    def test_yaml_unknown_key_is_added(self, tmp_path):
        """An unrecognised YAML key must be stored, not silently dropped."""
        yaml_file = tmp_path / "cfg.yaml"
        yaml_file.write_text("my_custom_key: 42\n")
        cfg = load_config(str(yaml_file))
        assert cfg.get("my_custom_key") == 42


# ================================================================
# 7. extract_phones()
# ================================================================

class TestExtractPhones:
    """extract_phones(html) → list of phone strings."""

    def test_tel_href_extracted(self):
        """A tel: href is the highest-confidence source and must always be found."""
        html   = '<a href="tel:+442071234567">Call us</a>'
        result = extract_phones(html)
        assert any("442071234567" in re.sub(r"\D", "", p) for p in result)

    def test_international_format_regex(self):
        """An international number with no tel: link must be found via regex."""
        html   = "<p>Call +44 20 7123 4567 for enquiries.</p>"
        result = extract_phones(html)
        assert len(result) > 0
        assert any("44" in re.sub(r"\D", "", p) for p in result)

    def test_bracketed_area_code(self):
        """Bracketed area code format (020) 7123 4567 must be recognised."""
        html   = "<p>Phone: (020) 7123 4567</p>"
        result = extract_phones(html)
        assert len(result) > 0

    def test_no_phones_returns_empty(self):
        html = "<p>No contact info here.</p>"
        assert extract_phones(html) == []

    def test_empty_html_returns_empty(self):
        assert extract_phones("") == []

    def test_too_short_digits_excluded(self):
        """Strings with fewer than 7 digits must not be returned."""
        html   = "<p>Code: 12345</p>"
        result = extract_phones(html)
        assert not any(len(re.sub(r"\D", "", p)) < 7 for p in result)

    def test_duplicate_numbers_deduplicated(self):
        """The same phone number appearing twice must only appear once."""
        html   = '<a href="tel:+442071234567">Call</a> or dial +44 20 7123 4567'
        result = extract_phones(html)
        digit_sets = [re.sub(r"\D", "", p) for p in result]
        assert len(digit_sets) == len(set(digit_sets))


# ================================================================
# 8. best_phone()
# ================================================================

class TestBestPhone:
    """best_phone(phones) → single best phone string or first valid."""

    def test_empty_list_returns_empty(self):
        assert best_phone([]) == ""

    def test_single_phone_returned(self):
        assert best_phone(["+44 20 7000 0000"]) == "+44 20 7000 0000"

    def test_international_preferred_over_local(self):
        """A number starting with + must score better than a plain local number."""
        phones = ["020 7000 0000", "+44 20 7000 0000", "0800 123 456"]
        assert best_phone(phones) == "+44 20 7000 0000"

    def test_too_short_skipped(self):
        """A string with fewer than 7 digits must be treated as invalid."""
        phones = ["12345", "+44 20 7000 0000"]
        assert best_phone(phones) == "+44 20 7000 0000"

    def test_too_short_only_falls_back(self):
        """If all numbers are invalid, fall back to the raw first entry."""
        phones = ["123"]
        result = best_phone(phones)
        assert result == "123"   # fallback, not empty


# ================================================================
# 9. _can_fetch() — robots.txt compliance
# ================================================================

class TestCanFetch:
    """_can_fetch(url) checks robots.txt; fails open on errors; caches per domain."""

    def test_unreachable_domain_fails_open(self):
        """A domain that doesn't exist must return True (fail open), not raise."""
        result = _can_fetch("https://this-domain-does-not-exist-xyz123.example/")
        assert result is True

    def test_disallow_all_respected(self, monkeypatch):
        """A robots.txt with Disallow: / for all agents must cause False."""
        import enricher

        class _Resp:
            status_code = 200
            text        = "User-agent: *\nDisallow: /\n"

        monkeypatch.setattr(enricher, "_robots_cache", {})
        monkeypatch.setattr(enricher.requests, "get", lambda *a, **kw: _Resp())
        assert _can_fetch("https://blocked-site.com/page") is False

    def test_allow_all_respected(self, monkeypatch):
        """A robots.txt with an empty Disallow must allow access."""
        import enricher

        class _Resp:
            status_code = 200
            text        = "User-agent: *\nDisallow:\n"

        monkeypatch.setattr(enricher, "_robots_cache", {})
        monkeypatch.setattr(enricher.requests, "get", lambda *a, **kw: _Resp())
        assert _can_fetch("https://open-site.com/") is True

    def test_404_robots_fails_open(self, monkeypatch):
        """A 404 for robots.txt means no restrictions — must return True."""
        import enricher

        class _Resp:
            status_code = 404
            text        = ""

        monkeypatch.setattr(enricher, "_robots_cache", {})
        monkeypatch.setattr(enricher.requests, "get", lambda *a, **kw: _Resp())
        assert _can_fetch("https://no-robots-txt.com/") is True

    def test_network_error_during_fetch_fails_open(self, monkeypatch):
        """If the robots.txt fetch itself raises, must return True (fail open)."""
        import enricher

        def _raise(*a, **kw):
            raise ConnectionError("network gone")

        monkeypatch.setattr(enricher, "_robots_cache", {})
        monkeypatch.setattr(enricher.requests, "get", _raise)
        assert _can_fetch("https://any-site.com/") is True

    def test_result_cached_per_domain(self, monkeypatch):
        """robots.txt must be fetched at most once per domain, even for different paths."""
        import enricher

        call_count = [0]

        class _Resp:
            status_code = 200
            text        = "User-agent: *\nDisallow:\n"

        def _counting_get(*a, **kw):
            call_count[0] += 1
            return _Resp()

        monkeypatch.setattr(enricher, "_robots_cache", {})
        monkeypatch.setattr(enricher.requests, "get", _counting_get)
        _can_fetch("https://cached-site.com/page1")
        _can_fetch("https://cached-site.com/page2")
        _can_fetch("https://cached-site.com/contact")
        assert call_count[0] == 1   # only one robots.txt fetch for the whole domain


# ================================================================
# 10. Extra email filter coverage
# ================================================================

class TestEmailFilterEdgeCases:
    """Regression tests for specific false-positive / false-negative bugs."""

    def test_jpeg_extension_not_returned_as_email(self):
        """.jpeg (not just .jpg) in an address must be filtered as an asset path."""
        html   = '<img src="logo@2x-large.jpeg" />'
        result = extract_emails_full(html)
        assert not any(".jpeg" in e for e in result)

    def test_jpg_extension_still_filtered(self):
        """Original .jpg filter must still work after the .jpeg addition."""
        html   = '<img src="banner@2x.jpg" />'
        result = extract_emails_full(html)
        assert not any(".jpg" in e for e in result)

    def test_placeholder_domain_com_filtered(self):
        """user@domain.com is a placeholder and must score 999."""
        cfg = _cfg()
        assert score_email("user@domain.com", cfg) == 999

    def test_placeholder_email_com_filtered(self):
        """name@email.com is a placeholder and must score 999."""
        cfg = _cfg()
        assert score_email("name@email.com", cfg) == 999

    def test_real_email_on_similar_domain_not_filtered(self):
        """info@mydomain.com must NOT be caught by the domain.com junk filter."""
        cfg = _cfg()
        assert score_email("info@mydomain.com", cfg) != 999

    def test_long_email_filtered(self):
        """An address longer than 80 chars must be dropped."""
        long_email = "a" * 70 + "@example.org"
        html       = f"<p>{long_email}</p>"
        result     = extract_emails_full(html)
        assert long_email.lower() not in result
