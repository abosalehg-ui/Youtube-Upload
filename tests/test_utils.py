#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""اختبارات وحدة الدوال المساعدة (لا تعتمد على PyQt5 أو الشبكة)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import (  # noqa: E402
    app_data_dir, format_date, format_number, humanize_error, parse_tags,
    sanitize_title, tags_total_length, validate_tags,
)


class TestFormatNumber:
    def test_small(self):
        assert format_number(0) == "0"
        assert format_number(999) == "999"

    def test_thousands(self):
        assert format_number(1000) == "1.0K"
        assert format_number(1500) == "1.5K"
        assert format_number(12345) == "12.3K"

    def test_millions(self):
        assert format_number(1_000_000) == "1.0M"
        assert format_number(2_500_000) == "2.5M"

    def test_negative(self):
        assert format_number(-1500) == "-1.5K"

    def test_invalid(self):
        assert format_number(None) == "0"
        assert format_number("abc") == "0"


class TestFormatDate:
    def test_valid_iso(self):
        assert format_date("2024-01-15T10:30:00Z") == "2024-01-15 10:30"

    def test_empty(self):
        assert format_date("") == ""
        assert format_date(None) == ""

    def test_invalid_falls_back_to_prefix(self):
        assert format_date("2024-01-15garbage") == "2024-01-15"


class TestParseTags:
    def test_basic(self):
        assert parse_tags("a, b, c") == ["a", "b", "c"]

    def test_strips_and_drops_empty(self):
        assert parse_tags(" a ,, b , ") == ["a", "b"]

    def test_empty(self):
        assert parse_tags("") == []
        assert parse_tags(None) == []


class TestSanitizeTitle:
    def test_strips_angle_brackets_and_truncates(self):
        assert sanitize_title("a <b> c") == "a b c"
        assert len(sanitize_title("x" * 150)) == 100

    def test_empty(self):
        assert sanitize_title("") == ""
        assert sanitize_title(None) == ""


class TestTags:
    def test_length_counts_commas_and_quotes(self):
        assert tags_total_length(["ab", "cd"]) == 5          # ab,cd
        assert tags_total_length(["a b"]) == 5               # "a b"

    def test_validate(self):
        assert validate_tags(["ok"]) is None
        assert validate_tags(["x" * 501]) is not None


class _FakeResp:
    def __init__(self, status):
        self.status = status


class _FakeHttpError(Exception):
    def __init__(self, status, content=b""):
        super().__init__("raw http error")
        self.resp = _FakeResp(status)
        self.content = content


class TestHumanizeError:
    def test_quota(self):
        msg = humanize_error(_FakeHttpError(403, b'{"reason": "quotaExceeded"}'))
        assert "حصة" in msg

    def test_status_codes(self):
        assert "الجلسة" in humanize_error(_FakeHttpError(401))
        assert "مؤقت" in humanize_error(_FakeHttpError(503))

    def test_network_and_fallback(self):
        assert "الاتصال" in humanize_error(ConnectionError())
        assert humanize_error(ValueError("x")) == "x"


class TestDataPaths:
    def test_app_data_dir_respects_xdg(self, tmp_path, monkeypatch):
        if sys.platform.startswith("win") or sys.platform == "darwin":
            return
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        assert app_data_dir() == str(tmp_path / "YouTubeUpload")
        assert os.path.isdir(app_data_dir())
