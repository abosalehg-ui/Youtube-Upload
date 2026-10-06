#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
الثوابت والإعدادات - YouTube Upload.

نظام الألوان وورقة الأنماط منفصلان في styles.py.
لا يُخزَّن أي سرّ أو معرّف داخل هذا الملف؛ يُقرأ Client ID وقت التشغيل
من client_secret.json المحلي (المُستثنى من Git).
"""

import json

from utils import client_secret_path

APP_NAME = "YouTube Upload"
APP_VERSION = "1.1.0"


def load_client_id(path: str = None) -> str:
    """قراءة Client ID من ملف الاعتماد المحلي إن وُجد (وإلا سلسلة فارغة).

    تُستدعى عند الحاجة (لا مرة واحدة عند الاستيراد) حتى يظهر أثر تغيير الملف فورًا.
    """
    path = path or client_secret_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        section = data.get("installed") or data.get("web") or {}
        return section.get("client_id", "")
    except (OSError, json.JSONDecodeError, ValueError, AttributeError):
        return ""


DEVELOPER_NAME = "عبدالكريم العبود"
DEVELOPER_EMAIL = "abo.saleh.g@gmail.com"
COPYRIGHT = "© 2026 عبدالكريم العبود — MIT License"

CATEGORIES = {
    "1": "أفلام ورسوم متحركة",
    "2": "السيارات والمركبات",
    "10": "موسيقى",
    "15": "حيوانات أليفة",
    "17": "رياضة",
    "19": "سفر وأحداث",
    "20": "ألعاب فيديو",
    "22": "أشخاص ومدونات",
    "23": "كوميديا",
    "24": "ترفيه",
    "25": "أخبار وسياسة",
    "26": "أساليب وموضة",
    "27": "تعليم",
    "28": "علوم وتكنولوجيا",
    "29": "منظمات غير ربحية",
}

# التصنيف الافتراضي المستخدم عند عدم التحديد.
DEFAULT_CATEGORY_ID = "24"  # ترفيه

PRIVACY_OPTIONS = {
    "عام": "public",
    "خاص": "private",
    "غير مدرج": "unlisted",
}

PRIVACY_REVERSE = {v: k for k, v in PRIVACY_OPTIONS.items()}

VIDEO_EXTENSIONS = "ملفات فيديو (*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.m4v *.3gp *.mpeg)"
# واجهة thumbnails.set تقبل JPEG وPNG فقط، بحجم أقصى 2MB.
IMAGE_EXTENSIONS = "ملفات صور (*.jpg *.jpeg *.png)"
MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024

# كل رفع يكلّف 1600 وحدة من الحصة الافتراضية (10,000 يوميًا) ≈ 6 فيديوهات.
UPLOAD_QUOTA_COST = 1600
DEFAULT_DAILY_QUOTA = 10_000
