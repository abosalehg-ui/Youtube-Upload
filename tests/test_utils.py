#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""اختبارات وحدة الدوال المساعدة (لا تعتمد على PyQt5 أو الشبكة)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import format_number, format_date, parse_tags  # noqa: E402


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
