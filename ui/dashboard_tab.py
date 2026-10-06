#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""تبويب لوحة التحكم: إحصائيات القناة + أحدث الفيديوهات + إجراءات سريعة."""

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QGroupBox, QHBoxLayout, QPushButton, QTableWidgetItem, QVBoxLayout

from styles import C
from ui.common import BaseTab, bold_font, create_stat_card, make_table, plain_label
from utils import format_date, format_number

PLACEHOLDER = "---"
SIGNED_OUT_TEXT = "قم بتسجيل الدخول لعرض بيانات القناة"


class DashboardTab(BaseTab):
    def __init__(self, win):
        super().__init__(win, margins=20, spacing=20)
        self.channel_info = None
        layout = self.body

        self.lbl_channel_name = plain_label(SIGNED_OUT_TEXT)
        self.lbl_channel_name.setFont(bold_font(18))
        self.lbl_channel_name.setStyleSheet(f"color: {C['accent']};")
        self.lbl_channel_name.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_channel_name)

        self.lbl_channel_desc = plain_label("", "muted")
        self.lbl_channel_desc.setAlignment(Qt.AlignCenter)
        self.lbl_channel_desc.setWordWrap(True)
        layout.addWidget(self.lbl_channel_desc)

        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(16)
        self.stat_subscribers = create_stat_card("المشتركون", PLACEHOLDER, C['accent'])
        self.stat_views = create_stat_card("المشاهدات الكلية", PLACEHOLDER, C['accent2'])
        self.stat_videos = create_stat_card("الفيديوهات", PLACEHOLDER, C['success'])
        self.stat_created = create_stat_card("تاريخ الإنشاء", PLACEHOLDER, C['warning'])
        self._cards = (self.stat_subscribers, self.stat_views, self.stat_videos, self.stat_created)
        for card in self._cards:
            stats_layout.addWidget(card)
        layout.addLayout(stats_layout)

        actions_group = QGroupBox("إجراءات سريعة")
        actions_layout = QHBoxLayout(actions_group)
        actions_layout.setSpacing(12)

        self.btn_refresh = QPushButton("🔄 تحديث البيانات")
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_refresh.setProperty("class", "secondary")

        btn_open_channel = QPushButton("🌐 فتح القناة")
        btn_open_channel.clicked.connect(self._open_channel)
        btn_open_channel.setProperty("class", "flat")

        btn_studio = QPushButton("🎬 استوديو يوتيوب")
        btn_studio.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://studio.youtube.com")))
        btn_studio.setProperty("class", "flat")

        btn_go_upload = QPushButton("📤 رفع فيديو جديد")
        btn_go_upload.clicked.connect(lambda: win.tabs.setCurrentWidget(win.tab_upload))

        for btn in (self.btn_refresh, btn_open_channel, btn_studio, btn_go_upload):
            actions_layout.addWidget(btn)
        layout.addWidget(actions_group)

        recent_group = QGroupBox("أحدث الفيديوهات")
        recent_layout = QVBoxLayout(recent_group)
        self.recent_table = make_table(["العنوان", "المشاهدات", "الإعجابات", "التعليقات", "التاريخ"])
        self.recent_table.horizontalHeader().setStretchLastSection(True)
        self.recent_table.setMaximumHeight(250)
        recent_layout.addWidget(self.recent_table)
        layout.addWidget(recent_group)
        layout.addStretch()

    # ------------------------------------------------------------
    def refresh(self):
        if not self.win.require_auth():
            return
        self.status("جاري تحميل بيانات القناة...")
        # نداء واحد يجلب القناة مرة واحدة (إحصائيات + أحدث فيديوهات) — توفير في حصّة الـAPI.
        self.win.run_async(self.yt.get_dashboard_data, self._on_loaded, 10,
                           busy=self.btn_refresh)

    def _on_loaded(self, success, data, error):
        if not success:
            self.win.report_error("خطأ في تحميل القناة", error, dialog=False)
            return
        if not data:
            self.status("لا توجد قناة مرتبطة بهذا الحساب", 5000)
            return

        info = data['info']
        self.channel_info = info
        self.lbl_channel_name.setText(f"📺 {info['title']}")
        self.lbl_channel_desc.setText(info.get('description', '')[:200])

        self.stat_subscribers.val_label.setText(format_number(info['subscribers']))
        self.stat_views.val_label.setText(format_number(info['views']))
        self.stat_videos.val_label.setText(str(info['video_count']))
        self.stat_created.val_label.setText(format_date(info.get("published_at", "")))

        self._populate_recent(data['videos'])
        self.status("تم تحميل بيانات القناة بنجاح ✓", 3000)

    def _populate_recent(self, videos):
        self.recent_table.setRowCount(0)
        for v in videos[:10]:
            row = self.recent_table.rowCount()
            self.recent_table.insertRow(row)
            self.recent_table.setItem(row, 0, QTableWidgetItem(v['title']))
            self.recent_table.setItem(row, 1, QTableWidgetItem(format_number(v['views'])))
            self.recent_table.setItem(row, 2, QTableWidgetItem(format_number(v['likes'])))
            self.recent_table.setItem(row, 3, QTableWidgetItem(format_number(v['comments'])))
            self.recent_table.setItem(row, 4, QTableWidgetItem(format_date(v['publishedAt'])))

    def _open_channel(self):
        channel_id = (self.channel_info or {}).get('channel_id')
        if channel_id:
            QDesktopServices.openUrl(QUrl(f"https://www.youtube.com/channel/{channel_id}"))
        else:
            QDesktopServices.openUrl(QUrl("https://www.youtube.com"))

    def reset(self):
        self.channel_info = None
        self.lbl_channel_name.setText(SIGNED_OUT_TEXT)
        self.lbl_channel_desc.setText("")
        for card in self._cards:
            card.val_label.setText(PLACEHOLDER)
        self.recent_table.setRowCount(0)
