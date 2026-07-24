#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
الثوابت والإعدادات - YouTube Upload.

نظام الألوان وورقة الأنماط منفصلان في styles.py.
لا يُخزَّن أي سرّ أو معرّف داخل هذا الملف؛ يُقرأ Client ID وقت التشغيل
من client_secret.json المحلي (المُستثنى من Git).
"""

import json

APP_NAME = "YouTube Upload"
APP_VERSION = "1.1.0"


def _load_client_id(path: str = "client_secret.json") -> str:
    """قراءة Client ID من ملف الاعتماد المحلي إن وُجد (وإلا سلسلة فارغة)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        section = data.get("installed") or data.get("web") or {}
        return section.get("client_id", "")
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return ""


CLIENT_ID = _load_client_id()

DEVELOPER_NAME = "عبدالكريم العبود"
DEVELOPER_EMAIL = "abo.saleh.g@gmail.com"
COPYRIGHT = "© 2026 [Youtube Upload] - All Rights Reserved"

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
IMAGE_EXTENSIONS = "ملفات صور (*.jpg *.jpeg *.png *.bmp *.gif *.webp)"
