#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""تبويب قوائم التشغيل: عرض، إنشاء، حذف، إضافة/إزالة فيديوهات."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QHBoxLayout, QInputDialog, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QSplitter, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ui.common import BaseTab, make_table, plain_label


class PlaylistsTab(BaseTab):
    def __init__(self, win):
        super().__init__(win)
        self.playlists_cache = []
        layout = self.body

        toolbar = QHBoxLayout()
        self.btn_load = QPushButton("🔄 تحميل القوائم")
        self.btn_load.clicked.connect(self.load)
        btn_create = QPushButton("➕ قائمة جديدة")
        btn_create.setProperty("class", "success")
        btn_create.clicked.connect(self._create)
        toolbar.addWidget(self.btn_load)
        toolbar.addWidget(btn_create)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # التخطيط RTL: القوائم تظهر يمينًا والفيديوهات يسارًا.
        splitter = QSplitter(Qt.Horizontal)

        lists_widget = QWidget()
        lists_layout = QVBoxLayout(lists_widget)
        lists_layout.setContentsMargins(0, 0, 0, 0)
        lists_layout.addWidget(plain_label("📁 قوائم التشغيل"))
        self.playlists_list = QListWidget()
        self.playlists_list.setAccessibleName("قوائم التشغيل")
        self.playlists_list.currentRowChanged.connect(self._selected)
        lists_layout.addWidget(self.playlists_list)
        pl_btns = QHBoxLayout()
        btn_del_pl = QPushButton("🗑️ حذف")
        btn_del_pl.setProperty("class", "danger")
        btn_del_pl.clicked.connect(self._delete)
        pl_btns.addWidget(btn_del_pl)
        pl_btns.addStretch()
        lists_layout.addLayout(pl_btns)

        items_widget = QWidget()
        items_layout = QVBoxLayout(items_widget)
        items_layout.setContentsMargins(0, 0, 0, 0)
        items_layout.addWidget(plain_label("🎬 فيديوهات القائمة"))
        self.items_table = make_table(["العنوان", "الترتيب", "معرف الفيديو"])
        items_layout.addWidget(self.items_table)
        pv_btns = QHBoxLayout()
        btn_add = QPushButton("➕ إضافة فيديو")
        btn_add.setProperty("class", "secondary")
        btn_add.clicked.connect(self._add_video)
        btn_remove = QPushButton("➖ إزالة")
        btn_remove.setProperty("class", "danger")
        btn_remove.clicked.connect(self._remove_video)
        pv_btns.addWidget(btn_add)
        pv_btns.addWidget(btn_remove)
        pv_btns.addStretch()
        items_layout.addLayout(pv_btns)

        splitter.addWidget(lists_widget)
        splitter.addWidget(items_widget)
        splitter.setSizes([350, 650])
        layout.addWidget(splitter)

    # ------------------------------------------------------------
    def load(self):
        if not self.win.require_auth():
            return
        self.status("جاري تحميل قوائم التشغيل...")
        self.win.run_async(self.yt.get_playlists, self._on_loaded, busy=self.btn_load)

    def _on_loaded(self, success, playlists, error):
        if not success:
            self.win.report_error("خطأ في تحميل القوائم", error)
            return
        self.playlists_cache = playlists
        self.playlists_list.clear()
        self.items_table.setRowCount(0)
        for pl in playlists:
            item = QListWidgetItem(f"📁 {pl['title']}  ({pl['videoCount']} فيديو)")
            item.setData(Qt.UserRole, pl['id'])
            self.playlists_list.addItem(item)
        self.status(f"تم تحميل {len(playlists)} قائمة تشغيل ✓", 3000)

    def _current_playlist(self):
        idx = self.playlists_list.currentRow()
        if 0 <= idx < len(self.playlists_cache):
            return self.playlists_cache[idx]
        return None

    def _selected(self, index):
        if index < 0 or index >= len(self.playlists_cache):
            return
        pl = self.playlists_cache[index]
        self.status(f"جاري تحميل فيديوهات: {pl['title']}...")

        def _done(success, items, error):
            # تجاهل الرد المتأخر إذا انتقل المستخدم لقائمة أخرى قبل وصوله.
            current = self._current_playlist()
            if current is None or current['id'] != pl['id']:
                return
            if not success:
                self.win.report_error("خطأ في تحميل القائمة", error)
                return
            self.items_table.setRowCount(0)
            for item in items:
                row = self.items_table.rowCount()
                self.items_table.insertRow(row)
                title_item = QTableWidgetItem(item['title'])
                title_item.setData(Qt.UserRole, item['id'])  # معرّف العنصر للإزالة
                self.items_table.setItem(row, 0, title_item)
                self.items_table.setItem(row, 1, QTableWidgetItem(str(item['position'])))
                self.items_table.setItem(row, 2, QTableWidgetItem(item['videoId']))
            self.status(f"تم تحميل {len(items)} فيديو ✓", 2000)

        self.win.run_async(self.yt.get_playlist_items, _done, pl['id'])

    def _create(self):
        if not self.win.require_auth():
            return
        name, ok = QInputDialog.getText(self, "قائمة تشغيل جديدة", "اسم القائمة:")
        name = name.strip()
        if not (ok and name):
            return
        desc, ok2 = QInputDialog.getText(self, "وصف القائمة", "الوصف (اختياري):")
        self.status("جاري إنشاء القائمة...")

        def _done(success, result, error):
            if success:
                QMessageBox.information(self, "نجاح", f"تم إنشاء القائمة: {name} ✓")
                self.load()
            else:
                self.win.report_error("خطأ في إنشاء القائمة", error)

        self.win.run_async(self.yt.create_playlist, _done, name, desc if ok2 else "")

    def _delete(self):
        if not self.win.require_auth():
            return
        pl = self._current_playlist()
        if pl is None:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد قائمة تشغيل")
            return
        reply = QMessageBox.warning(
            self, "تأكيد الحذف",
            f"هل تريد حذف قائمة التشغيل:\n{pl['title']}؟",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.status("جاري حذف القائمة...")

        def _done(success, result, error):
            if success:
                QMessageBox.information(self, "نجاح", "تم حذف القائمة ✓")
                self.load()
            else:
                self.win.report_error("خطأ في حذف القائمة", error)

        self.win.run_async(self.yt.delete_playlist, _done, pl['id'])

    def _add_video(self):
        if not self.win.require_auth():
            return
        pl = self._current_playlist()
        if pl is None:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد قائمة تشغيل أولاً")
            return

        # منتقي من الفيديوهات المحمّلة بدل لصق المعرّف يدويًا
        videos = self.win.tab_videos.videos_cache
        if videos:
            labels = [f"{v['title']}  —  {v['id']}" for v in videos]
            choice, ok = QInputDialog.getItem(self, "إضافة فيديو", "اختر فيديو:", labels, 0, False)
            if not ok:
                return
            video_id = videos[labels.index(choice)]['id']
        else:
            text, ok = QInputDialog.getText(
                self, "إضافة فيديو",
                "أدخل معرف الفيديو (Video ID):\n(حمّل تبويب الفيديوهات لاختيارها من قائمة)"
            )
            if not (ok and text.strip()):
                return
            video_id = text.strip()

        self.status("جاري إضافة الفيديو...")
        idx = self.playlists_list.currentRow()

        def _done(success, result, error):
            if success:
                QMessageBox.information(self, "نجاح", "تم إضافة الفيديو ✓")
                self._selected(idx)
            else:
                self.win.report_error("خطأ في الإضافة", error)

        self.win.run_async(self.yt.add_video_to_playlist, _done, pl['id'], video_id)

    def _remove_video(self):
        if not self.win.require_auth():
            return
        row = self.items_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد فيديو من القائمة")
            return
        title_item = self.items_table.item(row, 0)
        reply = QMessageBox.question(
            self, "تأكيد", f"إزالة '{title_item.text()}' من القائمة؟",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        current_idx = self.playlists_list.currentRow()
        self.status("جاري إزالة الفيديو...")

        def _done(success, result, error):
            if success:
                self._selected(current_idx)
                self.status("تم إزالة الفيديو من القائمة ✓", 2000)
            else:
                self.win.report_error("خطأ في الإزالة", error)

        self.win.run_async(self.yt.remove_from_playlist, _done, title_item.data(Qt.UserRole))

    def reset(self):
        self.playlists_cache = []
        self.playlists_list.clear()
        self.items_table.setRowCount(0)
