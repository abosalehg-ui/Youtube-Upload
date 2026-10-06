#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""تبويب الإعدادات: ملف المصادقة، تسجيل الخروج، حول التطبيق."""

import os
import shutil

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFileDialog, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout,
)

from constants import (
    APP_NAME, APP_VERSION, COPYRIGHT, DEVELOPER_EMAIL, DEVELOPER_NAME, load_client_id,
)
from styles import C
from ui.common import BaseTab, plain_label
from utils import app_data_dir, data_path


class SettingsTab(BaseTab):
    def __init__(self, win):
        super().__init__(win, margins=20, spacing=16)
        layout = self.body

        auth_group = QGroupBox("المصادقة")
        auth_layout = QVBoxLayout(auth_group)
        self.lbl_auth_info = plain_label("", "hint")
        self.lbl_auth_info.setWordWrap(True)
        self.lbl_auth_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        auth_layout.addWidget(self.lbl_auth_info)
        self.refresh_client_info()

        btn_row = QHBoxLayout()
        btn_change_secret = QPushButton("📂 تغيير ملف client_secret")
        btn_change_secret.setProperty("class", "secondary")
        btn_change_secret.clicked.connect(self._change_client_secret)
        btn_logout = QPushButton("🚪 تسجيل الخروج")
        btn_logout.setProperty("class", "danger")
        btn_logout.clicked.connect(lambda: win.logout(confirm=True))
        btn_row.addWidget(btn_change_secret)
        btn_row.addWidget(btn_logout)
        btn_row.addStretch()
        auth_layout.addLayout(btn_row)
        layout.addWidget(auth_group)

        # حول التطبيق — نص HTML ثابت من ثوابت التطبيق فقط (لا مدخلات خارجية).
        about_group = QGroupBox("حول التطبيق")
        about_layout = QVBoxLayout(about_group)
        about_text = QLabel(
            f"<div style='text-align:center; padding: 20px;'>"
            f"<p style='font-size:36px;'>&#9654;</p>"
            f"<h2 style='color:{C['accent']}; font-size:24px; margin:8px;'>{APP_NAME}</h2>"
            f"<p style='color:{C['text2']}; font-size:14px;'>الإصدار {APP_VERSION}</p>"
            f"<br>"
            f"<p style='color:{C['text2']}; font-size:13px;'>تطبيق شامل لإدارة قناة يوتيوب</p>"
            f"<p style='color:{C['text3']}; font-size:12px;'>"
            f"رفع الفيديوهات &bull; الجدولة &bull; الإحصائيات &bull; قوائم التشغيل</p>"
            f"<br><br>"
            f"<p style='color:{C['accent']}; font-size:15px; font-weight:bold;'>"
            f"تطوير: {DEVELOPER_NAME}</p>"
            f"<p style='color:{C['blue']}; font-size:13px;'>{DEVELOPER_EMAIL}</p>"
            f"<br>"
            f"<p style='color:{C['text3']}; font-size:12px;'>{COPYRIGHT}</p>"
            f"</div>"
        )
        about_text.setTextFormat(Qt.RichText)
        about_text.setAlignment(Qt.AlignCenter)
        about_layout.addWidget(about_text)
        layout.addWidget(about_group)

        deps_group = QGroupBox("المتطلبات")
        deps_layout = QVBoxLayout(deps_group)
        deps_text = plain_label("pip install -r requirements.txt")
        deps_text.setStyleSheet(f"""
            background: {C['input']};
            padding: 12px;
            border-radius: 8px;
            font-family: 'Consolas', 'Courier New';
            font-size: 13px;
        """)
        deps_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        deps_layout.addWidget(deps_text)
        layout.addWidget(deps_group)
        layout.addStretch()

    # ------------------------------------------------------------
    def refresh_client_info(self):
        client_id = load_client_id()
        display = f"{client_id[:30]}..." if client_id else "غير محمّل — ضع ملف client_secret.json"
        self.lbl_auth_info.setText(
            f"Client ID: {display}\n"
            f"ملف المصادقة: {self.win.yt.client_secret_path}\n"
            f"مجلد بيانات التطبيق: {app_data_dir()}"
        )

    def _change_client_secret(self):
        path, _ = QFileDialog.getOpenFileName(self, "اختر ملف client_secret", "", "JSON Files (*.json)")
        if not path:
            return
        target = data_path("client_secret.json")
        try:
            if not os.path.exists(target) or not os.path.samefile(path, target):
                shutil.copy2(path, target)
        except OSError as exc:
            QMessageBox.critical(self, "خطأ", f"تعذّر نسخ ملف المصادقة:\n{exc}")
            return

        # التوكن القديم مرتبط بالعميل القديم — بدون حذفه لن يُستخدم الملف الجديد.
        self.win.logout(confirm=False)
        self.refresh_client_info()
        QMessageBox.information(self, "نجاح", "تم تحديث ملف المصادقة ✓\nسجّل الدخول من جديد.")
