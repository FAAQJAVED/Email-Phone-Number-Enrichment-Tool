"""
tests/test_core.py — Unit tests for the email-enricher core modules.

Coverage
--------
email_utils
  - decode_cloudflare_email() with a known encoded/expected pair
  - extract_emails_raw()       basic regex extraction
  - extract_emails_full()      includes Cloudflare-protected addresses
  - extract_phones()           tel: href and regex fallback
  - score_email()              personal (1), priority-generic (2), generic (3), junk (999)
  - best_email()               picks the highest-scoring valid address

storage
  - save_checkpoint() / load_checkpoint() round-trip (atomic write verified)
  - Corrupt / missing checkpoint returns safe defaults
  - load_existing_output()     reads a pre-existing CSV into found-dict format

controls
  - check_cmd_file()           reads and clears command.txt
  - should_stop()              respects state.stop and wall-clock time
  - has_internet()             returns a bool (smoke test — does not assert value)
  - check_disk()               returns True when disk is fine (smoke test)

Run with:
    pytest -v tests/test_core.py
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Set
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# We import from core directly (not the package __init__) so individual
# module failures are easier to diagnose.
# ---------------------------------------------------------------------------
from core.email_utils import (
    best_email,
    decode_cloudflare_email,
    extract_emails_full,
    extract_emails_raw,
    extract_phones,
    score_email,
)
from core.controls import (
    State,
    check_cmd_file,
    check_disk,
    has_internet,
    should_stop,
)
from core.storage import (
    load_checkpoint,
    load_existing_output,
    save_checkpoint,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture()
def tmp_dir(tmp_path: Path):
    """Yield a fresh temporary directory (provided by pytest)."""
    return tmp_path


@pytest.fixture()
def minimal_cfg() -> dict:
    """Minimal config dict covering email-filtering keys."""
    return {
        "skip_email_keywords": [
            "noreply", "no-reply", "donotreply", "privacy",
            "gdpr", "unsubscribe", "postmaster", "webmaster",
            "bounce", "complaints", "legal", "abuse", "spam", "newsletter",
        ],
        "generic_email_keywords": [
            "info", "admin", "hello", "contact", "enquiries", "enquiry",
            "office", "mail", "email", "team", "support", "help", "sales",
            "lettings", "letting", "property", "management", "manager",
            "reception", "accounts", "finance", "general", "service", "post",
        ],
        "junk_email_domains": [
            "sentry.io", "wixpress.com", "example.com", "schema.org",
            "w3.org", "googleapis.com", "cloudflare.com", "jquery.com",
        ],
    }


# ===========================================================================
# email_utils — decode_cloudflare_email
# ===========================================================================

class TestDecodeCloudflareEmail:
    """
    Cloudflare XOR decoding tests.

    The encoded string is produced by XOR-ing each byte of the plaintext
    with a key byte (the first byte of the hex sequence), then hex-encoding.

    Verified pair (key=0x1a):
        plaintext  : hello@example.com
        hex encoded: 1a727f7676755a7f627b776a767f34797577
    """

    ENCODED = "1a727f7676755a7f627b776a767f34797577"
    EXPECTED = "hello@example.com"

    def test_known_pair(self):
        assert decode_cloudflare_email(self.ENCODED) == self.EXPECTED

    def test_empty_string_returns_empty(self):
        assert decode_cloudflare_email("") == ""

    def test_invalid_hex_returns_empty(self):
        assert decode_cloudflare_email("zzznothex") == ""

    def test_single_byte_key_only_returns_empty(self):
        # Only one byte → key with nothing to XOR → empty decoded string
        result = decode_cloudflare_email("1a")
        assert result == ""

    def test_result_contains_at_sign(self):
        result = decode_cloudflare_email(self.ENCODED)
        assert "@" in result

    def test_roundtrip_custom_pair(self):
        """Encode 'test@domain.org' with key=0x42 and verify decode."""
        key = 0x42
        plaintext = "test@domain.org"
        encoded_bytes = bytes([key] + [ord(c) ^ key for c in plaintext])
        encoded_hex = encoded_bytes.hex()
        assert decode_cloudflare_email(encoded_hex) == plaintext


# ===========================================================================
# email_utils — extract_emails_raw
# ===========================================================================

class TestExtractEmailsRaw:

    def test_finds_plain_email(self):
        html = "Contact us at info@company.co.uk for more."
        emails = extract_emails_raw(html)
        assert "info@company.co.uk" in emails

    def test_lowercases_result(self):
        html = "Send to HELLO@DOMAIN.COM"
        emails = extract_emails_raw(html)
        assert "hello@domain.com" in emails

    def test_strips_trailing_punctuation(self):
        html = "Email: john@firm.com."
        emails = extract_emails_raw(html)
        assert "john@firm.com" in emails

    def test_rejects_asset_false_positives(self):
        html = "url: image@2x.png"
        emails = extract_emails_raw(html)
        assert not any(".png" in e for e in emails)

    def test_rejects_long_address(self):
        long_email = "a" * 70 + "@example.com"   # > 80 chars
        html = f"Email: {long_email}"
        emails = extract_emails_raw(html)
        assert long_email not in emails

    def test_deduplicates(self):
        html = "info@co.com info@co.com info@co.com"
        emails = extract_emails_raw(html)
        assert emails.count("info@co.com") == 1

    def test_empty_html_returns_empty_list(self):
        assert extract_emails_raw("") == []


# ===========================================================================
# email_utils — extract_emails_full (Cloudflare)
# ===========================================================================

class TestExtractEmailsFull:

    def test_plain_email_still_found(self):
        html = "Contact: admin@firm.com"
        assert "admin@firm.com" in extract_emails_full(html)

    def test_cdn_cgi_pattern_decoded(self):
        # Encode "info@test.org" with key 0x10
        key = 0x10
        pt  = "info@test.org"
        enc = bytes([key] + [ord(c) ^ key for c in pt]).hex()
        html = f'<a href="/cdn-cgi/l/email-protection#{enc}">email</a>'
        emails = extract_emails_full(html)
        assert "info@test.org" in emails

    def test_data_cfemail_pattern_decoded(self):
        key = 0x20
        pt  = "sales@example.org"
        enc = bytes([key] + [ord(c) ^ key for c in pt]).hex()
        html = f'<span data-cfemail="{enc}"></span>'
        emails = extract_emails_full(html)
        assert "sales@example.org" in emails

    def test_both_patterns_in_same_html(self):
        key = 0x05
        pt1, pt2 = "one@site.com", "two@site.com"
        enc1 = bytes([key] + [ord(c) ^ key for c in pt1]).hex()
        enc2 = bytes([key] + [ord(c) ^ key for c in pt2]).hex()
        html = (
            f'/cdn-cgi/l/email-protection#{enc1} '
            f'data-cfemail="{enc2}"'
        )
        emails = extract_emails_full(html)
        assert "one@site.com" in emails
        assert "two@site.com" in emails


# ===========================================================================
# email_utils — extract_phones
# ===========================================================================

class TestExtractPhones:

    def test_tel_href_extracted(self):
        html = '<a href="tel:+441234567890">Call us</a>'
        phones = extract_phones(html)
        assert any("441234567890" in p.replace(" ", "").replace("+", "") for p in phones)

    def test_tel_href_preferred_over_regex(self):
        """When a tel: href is present the regex fallback should not fire."""
        html = '<a href="tel:+442071234567">020 7123 4567</a>'
        phones = extract_phones(html)
        # Deduplicated by digit run — should only appear once
        digit_runs = set()
        for p in phones:
            digits = "".join(c for c in p if c.isdigit())
            digit_runs.add(digits)
        assert len(digit_runs) == 1

    def test_regex_fallback_international(self):
        html = "Call +44 20 7123 4567 today"
        phones = extract_phones(html)
        assert phones

    def test_regex_fallback_bracketed(self):
        html = "Ring us on (020) 7123 4567"
        phones = extract_phones(html)
        assert phones

    def test_deduplicates_same_number_different_format(self):
        html = (
            '<a href="tel:+441234567890">+44 1234 567890</a>'
        )
        phones = extract_phones(html)
        digit_runs = ["".join(c for c in p if c.isdigit()) for p in phones]
        assert len(set(digit_runs)) == len(digit_runs)

    def test_empty_html(self):
        assert extract_phones("") == []


# ===========================================================================
# email_utils — score_email
# ===========================================================================

class TestScoreEmail:

    def test_personal_name_scores_1(self, minimal_cfg):
        assert score_email("john.smith@company.com", minimal_cfg) == 1

    def test_personal_name_with_dot_scores_1(self, minimal_cfg):
        assert score_email("a.b@firm.co.uk", minimal_cfg) == 1

    def test_priority_generic_info_scores_2(self, minimal_cfg):
        assert score_email("info@company.com", minimal_cfg) == 2

    def test_priority_generic_hello_scores_2(self, minimal_cfg):
        assert score_email("hello@company.com", minimal_cfg) == 2

    def test_priority_generic_contact_scores_2(self, minimal_cfg):
        assert score_email("contact@company.com", minimal_cfg) == 2

    def test_priority_generic_enquiries_scores_2(self, minimal_cfg):
        assert score_email("enquiries@company.com", minimal_cfg) == 2

    def test_other_generic_support_scores_3(self, minimal_cfg):
        assert score_email("support@company.com", minimal_cfg) == 3

    def test_other_generic_accounts_scores_3(self, minimal_cfg):
        assert score_email("accounts@company.com", minimal_cfg) == 3

    def test_other_generic_sales_scores_3(self, minimal_cfg):
        assert score_email("sales@company.com", minimal_cfg) == 3

    def test_noreply_scores_999(self, minimal_cfg):
        assert score_email("noreply@company.com", minimal_cfg) == 999

    def test_gdpr_scores_999(self, minimal_cfg):
        assert score_email("gdpr@company.com", minimal_cfg) == 999

    def test_junk_domain_scores_999(self, minimal_cfg):
        assert score_email("info@sentry.io", minimal_cfg) == 999

    def test_example_com_scores_999(self, minimal_cfg):
        assert score_email("test@example.com", minimal_cfg) == 999

    def test_empty_string_scores_999(self, minimal_cfg):
        assert score_email("", minimal_cfg) == 999

    def test_no_at_sign_scores_999(self, minimal_cfg):
        assert score_email("notanemail", minimal_cfg) == 999

    def test_uppercase_input_handled(self, minimal_cfg):
        # score_email lowercases internally
        assert score_email("NOREPLY@COMPANY.COM", minimal_cfg) == 999


# ===========================================================================
# email_utils — best_email
# ===========================================================================

class TestBestEmail:

    def test_picks_personal_over_generic(self, minimal_cfg):
        emails = ["info@firm.com", "j.doe@firm.com"]
        assert best_email(emails, minimal_cfg) == "j.doe@firm.com"

    def test_picks_priority_generic_over_plain_generic(self, minimal_cfg):
        emails = ["accounts@firm.com", "info@firm.com"]
        assert best_email(emails, minimal_cfg) == "info@firm.com"

    def test_filters_out_all_junk_returns_empty(self, minimal_cfg):
        emails = ["noreply@firm.com", "test@example.com"]
        assert best_email(emails, minimal_cfg) == ""

    def test_empty_list_returns_empty(self, minimal_cfg):
        assert best_email([], minimal_cfg) == ""

    def test_single_personal_email(self, minimal_cfg):
        assert best_email(["james@company.co.uk"], minimal_cfg) == "james@company.co.uk"

    def test_lowercases_result(self, minimal_cfg):
        result = best_email(["INFO@FIRM.COM"], minimal_cfg)
        assert result == result.lower()

    def test_mix_of_all_tiers(self, minimal_cfg):
        emails = [
            "noreply@firm.com",      # 999 — junk
            "sales@firm.com",        # 3   — generic
            "hello@firm.com",        # 2   — priority generic
            "jane.doe@firm.com",     # 1   — personal
        ]
        assert best_email(emails, minimal_cfg) == "jane.doe@firm.com"

    def test_non_email_strings_ignored(self, minimal_cfg):
        emails = ["not-an-email", "", "info@firm.com"]
        assert best_email(emails, minimal_cfg) == "info@firm.com"


# ===========================================================================
# storage — save_checkpoint / load_checkpoint
# ===========================================================================

class TestCheckpoint:

    def test_roundtrip(self, tmp_dir):
        ckpt = str(tmp_dir / "test_checkpoint.json")
        done: Set[str] = {"acme corp", "globex ltd"}
        found = {
            "acme corp": {
                "name": "Acme Corp", "website": "https://acme.com",
                "email": "info@acme.com", "phone": "+44123", "category": "Tech",
            }
        }
        save_checkpoint(done, found, ckpt)
        loaded_done, loaded_found = load_checkpoint(ckpt)

        assert loaded_done == done
        assert loaded_found["acme corp"]["email"] == "info@acme.com"

    def test_atomic_write_creates_file(self, tmp_dir):
        ckpt = str(tmp_dir / "atomic.json")
        save_checkpoint({"a"}, {"a": {}}, ckpt)
        # tmp file should be cleaned up
        assert os.path.exists(ckpt)
        assert not os.path.exists(ckpt + ".tmp")

    def test_atomic_write_no_tmp_on_disk_after(self, tmp_dir):
        ckpt = str(tmp_dir / "no_tmp.json")
        save_checkpoint(set(), {}, ckpt)
        assert not os.path.exists(ckpt + ".tmp")

    def test_file_content_is_valid_json(self, tmp_dir):
        ckpt = str(tmp_dir / "valid.json")
        save_checkpoint({"x"}, {}, ckpt)
        with open(ckpt) as f:
            data = json.load(f)
        assert "done" in data
        assert "found" in data

    def test_missing_file_returns_defaults(self, tmp_dir):
        ckpt = str(tmp_dir / "nonexistent.json")
        done, found = load_checkpoint(ckpt)
        assert done == set()
        assert found == {}

    def test_empty_file_returns_defaults(self, tmp_dir):
        ckpt = str(tmp_dir / "empty.json")
        Path(ckpt).write_text("", encoding="utf-8")
        done, found = load_checkpoint(ckpt)
        assert done == set()
        assert found == {}

    def test_corrupt_file_returns_defaults(self, tmp_dir):
        ckpt = str(tmp_dir / "corrupt.json")
        Path(ckpt).write_text("{{{not json", encoding="utf-8")
        done, found = load_checkpoint(ckpt)
        assert done == set()
        assert found == {}

    def test_empty_done_and_found(self, tmp_dir):
        ckpt = str(tmp_dir / "empty_sets.json")
        save_checkpoint(set(), {}, ckpt)
        done, found = load_checkpoint(ckpt)
        assert done == set()
        assert found == {}

    def test_large_checkpoint(self, tmp_dir):
        ckpt = str(tmp_dir / "large.json")
        done  = {f"company_{i}" for i in range(500)}
        found = {f"company_{i}": {"name": f"Co {i}", "email": f"e{i}@x.com",
                                   "website": "", "phone": "", "category": ""}
                 for i in range(250)}
        save_checkpoint(done, found, ckpt)
        loaded_done, loaded_found = load_checkpoint(ckpt)
        assert len(loaded_done) == 500
        assert len(loaded_found) == 250


# ===========================================================================
# storage — load_existing_output
# ===========================================================================

class TestLoadExistingOutput:

    def _write_csv(self, path: Path, rows: list[dict]) -> None:
        import csv
        if not rows:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    def test_loads_rows_with_email(self, tmp_dir):
        csv_path = tmp_dir / "found_contacts.csv"
        self._write_csv(csv_path, [
            {"Company Name": "Acme", "Website": "https://acme.com",
             "Email": "info@acme.com", "Phone": "", "Category": "Tech"},
        ])
        cfg = {"output_file": str(tmp_dir / "found_contacts.xlsx"),
               "columns": {}}
        found = load_existing_output(str(tmp_dir / "found_contacts.xlsx"), cfg)
        assert "acme" in found
        assert found["acme"]["email"] == "info@acme.com"

    def test_skips_rows_with_no_email_and_no_phone(self, tmp_dir):
        csv_path = tmp_dir / "found_contacts.csv"
        self._write_csv(csv_path, [
            {"Company Name": "Empty Co", "Website": "https://empty.com",
             "Email": "", "Phone": "", "Category": ""},
        ])
        cfg = {"output_file": str(tmp_dir / "found_contacts.xlsx"),
               "columns": {}}
        found = load_existing_output(str(tmp_dir / "found_contacts.xlsx"), cfg)
        assert "empty co" not in found

    def test_loads_rows_with_phone_only(self, tmp_dir):
        csv_path = tmp_dir / "found_contacts.csv"
        self._write_csv(csv_path, [
            {"Company Name": "Phone Co", "Website": "https://phone.com",
             "Email": "", "Phone": "+441234567890", "Category": ""},
        ])
        cfg = {"output_file": str(tmp_dir / "found_contacts.xlsx"),
               "columns": {}}
        found = load_existing_output(str(tmp_dir / "found_contacts.xlsx"), cfg)
        assert "phone co" in found

    def test_missing_csv_returns_empty(self, tmp_dir):
        cfg = {"output_file": str(tmp_dir / "notexist.xlsx"), "columns": {}}
        assert load_existing_output(str(tmp_dir / "notexist.xlsx"), cfg) == {}


# ===========================================================================
# controls — check_cmd_file
# ===========================================================================

class TestCheckCmdFile:

    def test_pause_command_sets_state(self, tmp_dir):
        cmd_file = str(tmp_dir / "command.txt")
        ckpt     = str(tmp_dir / "ckpt.json")
        Path(cmd_file).write_text("pause", encoding="utf-8")
        state = State()
        check_cmd_file(state, cmd_file, ckpt)
        assert state.paused is True

    def test_resume_command_clears_paused(self, tmp_dir):
        cmd_file = str(tmp_dir / "command.txt")
        ckpt     = str(tmp_dir / "ckpt.json")
        Path(cmd_file).write_text("resume", encoding="utf-8")
        state = State()
        state.paused = True
        check_cmd_file(state, cmd_file, ckpt)
        assert state.paused is False

    def test_r_alias_for_resume(self, tmp_dir):
        cmd_file = str(tmp_dir / "command.txt")
        ckpt     = str(tmp_dir / "ckpt.json")
        Path(cmd_file).write_text("r", encoding="utf-8")
        state = State()
        state.paused = True
        check_cmd_file(state, cmd_file, ckpt)
        assert state.paused is False

    def test_stop_command_sets_stop(self, tmp_dir):
        cmd_file = str(tmp_dir / "command.txt")
        ckpt     = str(tmp_dir / "ckpt.json")
        Path(cmd_file).write_text("stop", encoding="utf-8")
        state = State()
        check_cmd_file(state, cmd_file, ckpt)
        assert state.stop is True

    def test_q_alias_for_stop(self, tmp_dir):
        cmd_file = str(tmp_dir / "command.txt")
        ckpt     = str(tmp_dir / "ckpt.json")
        Path(cmd_file).write_text("q", encoding="utf-8")
        state = State()
        check_cmd_file(state, cmd_file, ckpt)
        assert state.stop is True

    def test_file_cleared_after_read(self, tmp_dir):
        cmd_file = str(tmp_dir / "command.txt")
        ckpt     = str(tmp_dir / "ckpt.json")
        Path(cmd_file).write_text("pause", encoding="utf-8")
        state = State()
        check_cmd_file(state, cmd_file, ckpt)
        assert Path(cmd_file).read_text() == ""

    def test_fresh_removes_checkpoint(self, tmp_dir):
        cmd_file = str(tmp_dir / "command.txt")
        ckpt     = str(tmp_dir / "ckpt.json")
        Path(cmd_file).write_text("fresh", encoding="utf-8")
        Path(ckpt).write_text('{"done":[],"found":{}}', encoding="utf-8")
        state = State()
        check_cmd_file(state, cmd_file, ckpt)
        assert not os.path.exists(ckpt)

    def test_missing_file_is_noop(self, tmp_dir):
        cmd_file = str(tmp_dir / "no_command.txt")
        ckpt     = str(tmp_dir / "ckpt.json")
        state = State()
        check_cmd_file(state, cmd_file, ckpt)  # must not raise
        assert state.paused is False
        assert state.stop   is False

    def test_empty_file_is_noop(self, tmp_dir):
        cmd_file = str(tmp_dir / "command.txt")
        ckpt     = str(tmp_dir / "ckpt.json")
        Path(cmd_file).write_text("", encoding="utf-8")
        state = State()
        check_cmd_file(state, cmd_file, ckpt)
        assert state.paused is False
        assert state.stop   is False

    def test_unknown_command_is_noop(self, tmp_dir):
        cmd_file = str(tmp_dir / "command.txt")
        ckpt     = str(tmp_dir / "ckpt.json")
        Path(cmd_file).write_text("gibberish", encoding="utf-8")
        state = State()
        check_cmd_file(state, cmd_file, ckpt)
        assert state.paused is False
        assert state.stop   is False


# ===========================================================================
# controls — should_stop
# ===========================================================================

class TestShouldStop:

    def test_stop_flag_true_returns_true(self):
        state = State()
        state.stop = True
        assert should_stop(state, "") is True

    def test_stop_flag_false_no_time_returns_false(self):
        state = State()
        assert should_stop(state, "") is False

    def test_past_stop_time_returns_true(self):
        state = State()
        # "00:00" is always in the past for any current time ≥ midnight
        assert should_stop(state, "00:00") is True

    def test_future_stop_time_returns_false(self):
        state = State()
        assert should_stop(state, "23:59") is False

    def test_empty_stop_at_returns_false(self):
        state = State()
        assert should_stop(state, "") is False


# ===========================================================================
# controls — has_internet (smoke test)
# ===========================================================================

class TestHasInternet:

    def test_returns_bool(self):
        result = has_internet()
        assert isinstance(result, bool)


# ===========================================================================
# controls — check_disk (smoke test)
# ===========================================================================

class TestCheckDisk:

    def test_returns_true_when_enough_space(self):
        # Assume the test machine has at least 1 MB free
        assert check_disk(min_mb=1) is True

    def test_returns_false_when_threshold_absurdly_high(self):
        # No machine has 10 TB free
        result = check_disk(min_mb=10_000_000)
        assert result is False


# ===========================================================================
# http_utils — fetch_url
# ===========================================================================

from unittest.mock import MagicMock
from core.http_utils import fetch_url, enrich_one_http


class TestFetchUrl:
    """
    fetch_url wraps _fetch_worker in a daemon thread.
    requests.get is mocked so no real network calls are made.
    """

    _cfg = {
        "http_timeout": [2, 4],
        "user_agents": ["Mozilla/5.0 (test)"],
        "rate_limit": {"min_seconds": 0, "max_seconds": 0},
    }

    def test_returns_html_on_200(self):
        fake = MagicMock()
        fake.status_code = 200
        fake.text = "<html><body>contact@acme.co.uk</body></html>"
        with patch("core.http_utils.requests.get", return_value=fake):
            result = fetch_url("https://acme.co.uk", self._cfg)
        assert result == "<html><body>contact@acme.co.uk</body></html>"

    def test_returns_none_on_404(self):
        fake = MagicMock()
        fake.status_code = 404
        with patch("core.http_utils.requests.get", return_value=fake):
            result = fetch_url("https://acme.co.uk", self._cfg)
        assert result is None

    def test_returns_none_on_network_exception(self):
        with patch("core.http_utils.requests.get", side_effect=ConnectionError("refused")):
            result = fetch_url("https://acme.co.uk", self._cfg)
        assert result is None

    def test_returns_none_when_daemon_thread_times_out(self):
        """
        Hard-kill timeout path: requests.get blocks longer than wall_clock_limit
        so fetch_url abandons the daemon thread and returns None.
        """
        def slow_get(*args, **kwargs):
            time.sleep(5)  # far longer than wall_clock_limit below
            return MagicMock(status_code=200, text="never reached")

        with patch("core.http_utils.requests.get", side_effect=slow_get):
            result = fetch_url("https://acme.co.uk", self._cfg, wall_clock_limit=0.05)
        assert result is None


# ===========================================================================
# http_utils — enrich_one_http  (Pass 1)
# ===========================================================================

class TestEnrichOneHttp:
    """
    enrich_one_http is the Pass 1 entry point.
    fetch_url is mocked — no network calls, no rate-limit sleep.
    """

    @pytest.fixture()
    def http_cfg(self, minimal_cfg) -> dict:
        return {
            **minimal_cfg,
            "http_timeout": [2, 4],
            "user_agents": ["Mozilla/5.0 (test)"],
            "contact_paths": ["/contact"],
            "rate_limit": {"min_seconds": 0, "max_seconds": 0},
        }

    @staticmethod
    def _target(url: str = "https://acmelettings.co.uk") -> dict:
        return {"website": url, "name": "Acme Lettings", "category": "", "phone": ""}

    def test_extracts_email_from_homepage(self, http_cfg):
        html = "<a href='mailto:james@acmelettings.co.uk'>Email us</a>"
        with patch("core.http_utils.fetch_url", return_value=html):
            email, _ = enrich_one_http(self._target(), http_cfg)
        assert email == "james@acmelettings.co.uk"

    def test_extracts_phone_from_homepage(self, http_cfg):
        html = "<a href='tel:02079460123'>Call us</a>"
        with patch("core.http_utils.fetch_url", return_value=html):
            _, phone = enrich_one_http(self._target(), http_cfg)
        assert phone != ""

    def test_returns_empty_strings_when_no_contact_on_any_page(self, http_cfg):
        with patch("core.http_utils.fetch_url", return_value="<p>Nothing here.</p>"):
            email, phone = enrich_one_http(self._target(), http_cfg)
        assert email == "" and phone == ""

    def test_returns_empty_strings_when_all_fetches_fail(self, http_cfg):
        with patch("core.http_utils.fetch_url", return_value=None):
            email, phone = enrich_one_http(self._target(), http_cfg)
        assert email == "" and phone == ""

    def test_junk_email_is_filtered_out(self, http_cfg):
        html = "<a href='mailto:noreply@acmelettings.co.uk'>x</a>"
        with patch("core.http_utils.fetch_url", return_value=html):
            email, _ = enrich_one_http(self._target(), http_cfg)
        assert email == ""

    def test_falls_back_to_contact_subpage_when_homepage_empty(self, http_cfg):
        def fake_fetch(url, cfg, wall_clock_limit=10):
            if url.endswith("/contact"):
                return "<a href='mailto:info@acmelettings.co.uk'>Contact</a>"
            return "<p>No email on homepage.</p>"

        with patch("core.http_utils.fetch_url", side_effect=fake_fetch):
            email, _ = enrich_one_http(self._target(), http_cfg)
        assert email == "info@acmelettings.co.uk"