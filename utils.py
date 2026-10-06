#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
دوال مساعدة عامة + إعداد التسجيل (logging) + مسارات بيانات التطبيق.

هذه الوحدة لا تعتمد على PyQt5 عمدًا حتى تبقى قابلة للاختبار بمعزل عن الواجهة.
"""

import datetime
import logging
import os
import shutil
import sys
from typing import Optional

APP_LOGGER_NAME = "youtube_upload"
APP_DIR_NAME = "YouTubeUpload"

# حدود YouTube Data API للبيانات الوصفية.
MAX_TITLE_LENGTH = 100
MAX_TAGS_TOTAL_LENGTH = 500

# مجلد التطبيق (حيث main.py) — لا يعتمد على مجلد التشغيل الحالي (CWD).
APP_ROOT = os.path.dirname(os.path.abspath(__file__))


# ============ المسارات ============
def app_data_dir() -> str:
    """مجلد بيانات المستخدم الخاص بالتطبيق (يُنشأ عند الحاجة).

    Windows: ``%APPDATA%/YouTubeUpload``، macOS: ``~/Library/Application Support/YouTubeUpload``،
    Linux: ``$XDG_CONFIG_HOME/YouTubeUpload`` (افتراضيًا ``~/.config``).
    """
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    path = os.path.join(base, APP_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def data_path(filename: str) -> str:
    """مسار ملف داخل مجلد بيانات التطبيق."""
    return os.path.join(app_data_dir(), filename)


def client_secret_path() -> str:
    """مسار client_secret.json: مجلد البيانات أولًا ثم مجلد التطبيق (للتوافق مع الإعداد القديم)."""
    preferred = data_path("client_secret.json")
    if os.path.exists(preferred):
        return preferred
    legacy = os.path.join(APP_ROOT, "client_secret.json")
    if os.path.exists(legacy):
        return legacy
    return preferred


def migrate_legacy_file(filename: str) -> None:
    """نقل ملف قديم (token.json/token.pickle) من مجلد التطبيق إلى مجلد البيانات مرة واحدة."""
    target = data_path(filename)
    if os.path.exists(target):
        return
    for folder in (APP_ROOT, os.getcwd()):
        legacy = os.path.join(folder, filename)
        if os.path.exists(legacy):
            try:
                shutil.move(legacy, target)
            except OSError:
                pass
            return


# ============ التسجيل ============
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


# ============ التنسيق ============
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
    if not iso_str:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError, TypeError):
        return iso_str[:10] if isinstance(iso_str, str) else ""


# ============ التحقق من البيانات الوصفية ============
def parse_tags(raw: str) -> list:
    """تحويل نص وسوم مفصولة بفواصل إلى قائمة نظيفة بلا فراغات أو تكرار فارغ."""
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]


def sanitize_title(title: str) -> str:
    """تنظيف عنوان الفيديو: يوتيوب يرفض ``<`` و``>`` ويحدّ الطول بـ 100 حرف."""
    cleaned = (title or "").replace("<", "").replace(">", "")
    return " ".join(cleaned.split())[:MAX_TITLE_LENGTH]


def tags_total_length(tags: list) -> int:
    """الطول الذي يحسبه يوتيوب للوسوم: مجموع الأحرف + فاصلة بين كل وسمين،
    والوسم الذي فيه مسافة يُحسب بعلامتي تنصيص."""
    total = 0
    for tag in tags:
        total += len(tag) + (2 if " " in tag else 0)
    return total + max(len(tags) - 1, 0)


def validate_tags(tags: list) -> Optional[str]:
    """إرجاع رسالة خطأ إذا تجاوزت الوسوم حد يوتيوب، وإلا None."""
    length = tags_total_length(tags)
    if length > MAX_TAGS_TOTAL_LENGTH:
        return f"مجموع الوسوم {length} حرفًا، والحد الأقصى {MAX_TAGS_TOTAL_LENGTH}"
    return None


# ============ رسائل الخطأ ============
def humanize_error(exc: BaseException) -> str:
    """تحويل الاستثناءات الشائعة (HttpError وأخطاء الشبكة) إلى رسالة مفهومة.

    يتعامل مع ``googleapiclient.errors.HttpError`` بالـ duck typing حتى لا تعتمد
    هذه الوحدة على مكتبة Google.
    """
    resp = getattr(exc, "resp", None)
    status = getattr(resp, "status", None)
    detail = str(exc)
    reason = ""
    content = getattr(exc, "content", b"")
    if isinstance(content, bytes):
        reason = content.decode("utf-8", "ignore")

    if status is not None:
        if "quotaExceeded" in reason or "quotaExceeded" in detail:
            return ("تجاوزت حصة YouTube API اليومية. حاول مجددًا بعد منتصف الليل "
                    "بتوقيت المحيط الهادئ، أو اطلب زيادة الحصة من Google Cloud.")
        if "uploadLimitExceeded" in reason:
            return "تجاوزت القناة حد الرفع اليومي في يوتيوب. حاول لاحقًا."
        if status == 401:
            return "انتهت صلاحية الجلسة. سجّل الدخول من جديد."
        if status == 403:
            return "ليس لديك صلاحية لهذا الإجراء (403). تحقق من الحساب والصلاحيات."
        if status == 404:
            return "العنصر المطلوب غير موجود (ربما حُذف)."
        if status == 400:
            return "رفض يوتيوب البيانات المُرسلة (400). تحقق من العنوان والوسوم والوصف."
        if int(status) >= 500:
            return "خطأ مؤقت في خوادم يوتيوب. حاول مجددًا بعد قليل."
        return f"خطأ من يوتيوب ({status})."

    if isinstance(exc, FileNotFoundError):
        return f"الملف غير موجود: {exc.filename or detail}"
    if isinstance(exc, (ConnectionError, TimeoutError)) or exc.__class__.__name__ in (
            "ServerNotFoundError", "TransportError"):
        return "تعذّر الاتصال بالإنترنت. تحقق من الشبكة وحاول مجددًا."
    return detail or exc.__class__.__name__
