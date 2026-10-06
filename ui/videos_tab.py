#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""تبويب الفيديوهات: تحميل، بحث، تعديل، حذف، تعليقات."""

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QApplication, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QMenu,
    QMessageBox, QPushButton, QTableWidgetItem,
)

from constants import PRIVACY_REVERSE
from ui.common import BaseTab, make_table, plain_label
from ui.dialogs import CommentsDialog, EditVideoDialog
from utils import format_date, format_number

COL_ID = 6


class VideosTab(BaseTab):
    def __init__(self, win):
        super().__init__(win)
        self.videos_cache = []
        layout = self.body

        toolbar = QHBoxLayout()
        self.btn_load = QPushButton("🔄 تحميل الفيديوهات")
        self.btn_load.clicked.connect(self.load)

        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("🔍 بحث في الفيديوهات...")
        self.txt_search.setAccessibleName("بحث في الفيديوهات")
        self.txt_search.textChanged.connect(self._filter)

        self.cmb_count = QComboBox()
        self.cmb_count.addItems(["25", "50", "100", "200"])
        self.cmb_count.setCurrentText("50")
        self.cmb_count.setFixedWidth(80)
        self.cmb_count.setAccessibleName("عدد الفيديوهات")

        toolbar.addWidget(self.btn_load)
        toolbar.addWidget(QLabel("عدد:"))
        toolbar.addWidget(self.cmb_count)
        toolbar.addStretch()
        toolbar.addWidget(self.txt_search)
        layout.addLayout(toolbar)

        self.table = make_table(
            ["العنوان", "المشاهدات", "الإعجابات", "التعليقات", "الخصوصية", "التاريخ", "المعرف"],
            widths={1: 100, 2: 100, 3: 100, 4: 100, 5: 140, 6: 120},
        )
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(self._open_in_browser)
        layout.addWidget(self.table)

        btns = QHBoxLayout()
        btn_edit = QPushButton("✏️ تعديل")
        btn_edit.setProperty("class", "secondary")
        btn_edit.clicked.connect(self._edit)

        self.btn_delete = QPushButton("🗑️ حذف")
        self.btn_delete.setProperty("class", "danger")
        self.btn_delete.clicked.connect(self._delete)

        btn_open = QPushButton("🌐 فتح في المتصفح")
        btn_open.setProperty("class", "flat")
        btn_open.clicked.connect(self._open_in_browser)

        btn_comments = QPushButton("💬 التعليقات")
        btn_comments.setProperty("class", "flat")
        btn_comments.clicked.connect(self._show_comments)

        self.lbl_count = plain_label("0 فيديو", "muted")

        for btn in (btn_edit, self.btn_delete, btn_open, btn_comments):
            btns.addWidget(btn)
        btns.addStretch()
        btns.addWidget(self.lbl_count)
        layout.addLayout(btns)

    # ------------------------------------------------------------
    def load(self):
        if not self.win.require_auth():
            return
        self.status("جاري تحميل الفيديوهات...")
        self.win.run_async(self.yt.get_videos, self._on_loaded,
                           int(self.cmb_count.currentText()), busy=self.btn_load)

    def _on_loaded(self, success, videos, error):
        if not success:
            self.win.report_error("خطأ في تحميل الفيديوهات", error)
            return
        self.videos_cache = videos
        self._filter(self.txt_search.text())
        self.status(f"تم تحميل {len(videos)} فيديو ✓", 3000)

    def _populate(self, videos):
        self.table.setRowCount(0)
        for v in videos:
            row = self.table.rowCount()
            self.table.insertRow(row)
            privacy = PRIVACY_REVERSE.get(v['privacy'], v['privacy'])
            if v.get('publishAt'):
                privacy = f"{privacy} (مجدول)"
            self.table.setItem(row, 0, QTableWidgetItem(v['title']))
            self.table.setItem(row, 1, QTableWidgetItem(format_number(v['views'])))
            self.table.setItem(row, 2, QTableWidgetItem(format_number(v['likes'])))
            self.table.setItem(row, 3, QTableWidgetItem(format_number(v['comments'])))
            self.table.setItem(row, 4, QTableWidgetItem(privacy))
            self.table.setItem(row, 5, QTableWidgetItem(format_date(v['publishedAt'])))
            self.table.setItem(row, COL_ID, QTableWidgetItem(v['id']))
        self.lbl_count.setText(f"{len(videos)} فيديو")

    def _filter(self, text):
        text = (text or "").lower()
        if not text:
            self._populate(self.videos_cache)
            return
        self._populate([v for v in self.videos_cache
                        if text in v['title'].lower()
                        or text in v.get('description', '').lower()])

    def _selected(self):
        row = self.table.currentRow()
        if row < 0 or self.table.item(row, COL_ID) is None:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد فيديو من الجدول")
            return None, None
        return self.table.item(row, COL_ID).text(), self.table.item(row, 0).text()

    def _open_in_browser(self):
        video_id, _ = self._selected()
        if video_id:
            QDesktopServices.openUrl(QUrl(f"https://youtube.com/watch?v={video_id}"))

    def _context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        self.table.selectRow(row)
        menu = QMenu(self)
        menu.addAction("🌐 فتح في المتصفح", self._open_in_browser)
        menu.addAction("✏️ تعديل", self._edit)
        menu.addAction("💬 التعليقات", self._show_comments)
        menu.addSeparator()
        menu.addAction("📋 نسخ الرابط", self._copy_link)
        menu.addAction("📋 نسخ المعرف", self._copy_id)
        menu.addSeparator()
        menu.addAction("🗑️ حذف", self._delete)
        menu.exec_(self.table.viewport().mapToGlobal(pos))

    def _copy_link(self):
        video_id, _ = self._selected()
        if video_id:
            QApplication.clipboard().setText(f"https://youtube.com/watch?v={video_id}")
            self.status("تم نسخ الرابط ✓", 2000)

    def _copy_id(self):
        video_id, _ = self._selected()
        if video_id:
            QApplication.clipboard().setText(video_id)
            self.status("تم نسخ المعرف ✓", 2000)

    def _edit(self):
        if not self.win.require_auth():
            return
        video_id, _ = self._selected()
        if not video_id:
            return
        video = next((v for v in self.videos_cache if v['id'] == video_id), None)
        if not video:
            return

        dialog = EditVideoDialog(video, self)
        if dialog.exec_() != QDialog.Accepted:
            return
        data = dialog.get_data()
        self.status("جاري تحديث الفيديو...")

        def _done(success, result, error):
            if success:
                QMessageBox.information(self, "نجاح", "تم تحديث الفيديو بنجاح! ✓")
                self.load()
            else:
                self.win.report_error("فشل التحديث", error)

        self.win.run_async(self.yt.update_video, _done, video_id, **data)

    def _delete(self):
        if not self.win.require_auth():
            return
        video_id, title = self._selected()
        if not video_id:
            return
        reply = QMessageBox.warning(
            self, "تأكيد الحذف",
            f"هل أنت متأكد من حذف هذا الفيديو؟\n\n{title}\n\nهذا الإجراء لا يمكن التراجع عنه!",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.status("جاري حذف الفيديو...")
            self.win.run_async(self.yt.delete_video, self._on_deleted, video_id,
                               busy=self.btn_delete)

    def _on_deleted(self, success, result, error):
        if success:
            self.status("تم حذف الفيديو بنجاح!", 3000)
            self.load()
        else:
            self.win.report_error("خطأ في الحذف", error)

    def _show_comments(self):
        if not self.win.require_auth():
            return
        video_id, title = self._selected()
        if video_id:
            CommentsDialog(self.win, video_id, title).exec_()

    def reset(self):
        self.videos_cache = []
        self.txt_search.clear()
        self.table.setRowCount(0)
        self.lbl_count.setText("0 فيديو")
