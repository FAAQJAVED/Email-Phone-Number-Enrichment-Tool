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
import sys

import pytest

# Make sure the project root is on the path so we can import enricher directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from enricher import (
    DEFAULT_CONFIG,
    best_email,
    decode_cloudflare_email,
    extract_emails_full,
    load_checkpoint,
    load_config,
    save_checkpoint,
    score_email,
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
