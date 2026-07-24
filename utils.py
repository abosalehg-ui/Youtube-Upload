#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
دوال مساعدة عامة + إعداد التسجيل (logging).

هذه الوحدة لا تعتمد على PyQt5 عمدًا حتى تبقى قابلة للاختبار بمعزل عن الواجهة.
"""

import logging
from typing import Optional

APP_LOGGER_NAME = "youtube_upload"


def setup_logging(level: int = logging.INFO, log_file: Optional[str] = None) -> logging.Logger:
    """تهيئة نظام التسجيل مرة واحدة وإرجاع مُسجّل التطبيق.

    يكتب إلى الطرفية دائمًا، وإلى ملف إن مُرِّر ``log_file``.
    """
    logger = logging.getLogger(APP_LOGGER_NAME)
    if logger.handlers:  # مُهيّأ مسبقًا — لا نكرّر المعالِجات
        return logger

    logger.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    logger.addHandler(stream)

    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(fmt)
            logger.addHandler(file_handler)
        except OSError:
            logger.warning("تعذّر إنشاء ملف السجل: %s", log_file)

    return logger


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """إرجاع مُسجّل فرعي تحت مساحة اسم التطبيق."""
    if name:
        return logging.getLogger(f"{APP_LOGGER_NAME}.{name}")
    return logging.getLogger(APP_LOGGER_NAME)


def format_number(n: int) -> str:
    """تنسيق الأرقام الكبيرة بصيغة مختصرة (K/M)."""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "0"
    sign = "-" if n < 0 else ""
    n = abs(n)
    if n >= 1_000_000:
        return f"{sign}{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{sign}{n / 1_000:.1f}K"
    return f"{sign}{n}"


def format_date(iso_str: str) -> str:
    """تحويل تاريخ ISO 8601 إلى صيغة مقروءة ``YYYY-MM-DD HH:MM``."""
    import datetime

    if not iso_str:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError, TypeError):
        return iso_str[:10] if isinstance(iso_str, str) else ""


def parse_tags(raw: str) -> list:
    """تحويل نص وسوم مفصولة بفواصل إلى قائمة نظيفة بلا فراغات أو تكرار فارغ."""
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]
