#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""تبويب الرفع الجماعي.

قواعد مهمة:
- الخيط يأخذ نسخة من قائمة الانتظار، وأزرار تعديل القائمة تتعطل أثناء الرفع.
- بعد انتهاء الدفعة تُحذف العناصر الناجحة من القائمة حتى لا تُرفع مرة ثانية.
"""

import os

from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QMessageBox, QProgressBar, QPushButton, QTableWidgetItem,
)

from constants import (
    CATEGORIES, DEFAULT_DAILY_QUOTA, PRIVACY_OPTIONS, PRIVACY_REVERSE,
    UPLOAD_QUOTA_COST, VIDEO_EXTENSIONS,
)
from ui.common import (
    BaseTab, bold_font, make_table, plain_label, populate_category_combo,
    populate_privacy_combo,
)
from ui.upload_tab import MADE_FOR_KIDS_TEXT
from utils import sanitize_title
from workers import BatchUploadThread, UploadJob

STATUS_PENDING = "في الانتظار"
COL_STATUS = 4


class BatchTab(BaseTab):
    def __init__(self, win):
        super().__init__(win)
        self.thread = None
        self.queue = []      # List[UploadJob]
        self.statuses = {}   # id(job) -> نص الحالة
        self._running_jobs = []
        layout = self.body

        info = plain_label(
            "📦 الرفع الجماعي - أضف عدة فيديوهات لرفعها تلقائياً واحداً تلو الآخر. "
            f"تنبيه: كل رفع يستهلك {UPLOAD_QUOTA_COST} وحدة من حصة YouTube API "
            f"(الافتراضي {DEFAULT_DAILY_QUOTA:,} يوميًا ≈ "
            f"{DEFAULT_DAILY_QUOTA // UPLOAD_QUOTA_COST} فيديوهات).",
            "hint",
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.table = make_table(["الملف", "العنوان", "التصنيف", "الخصوصية", "الحالة"],
                                stretch=(0, 1))
        layout.addWidget(self.table)

        q_btns = QHBoxLayout()
        self.btn_add = QPushButton("📂 إضافة فيديوهات")
        self.btn_add.clicked.connect(self._add_files)
        self.btn_remove = QPushButton("➖ إزالة المحدد")
        self.btn_remove.setProperty("class", "flat")
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_clear = QPushButton("🗑️ مسح الكل")
        self.btn_clear.setProperty("class", "flat")
        self.btn_clear.clicked.connect(self._clear)
        for btn in (self.btn_add, self.btn_remove, self.btn_clear):
            q_btns.addWidget(btn)
        q_btns.addStretch()
        layout.addLayout(q_btns)

        self.settings_group = QGroupBox("إعدادات الرفع الجماعي (تُطبَّق على الملفات المضافة بعدها)")
        bs_layout = QFormLayout(self.settings_group)
        self.cmb_privacy = QComboBox()
        populate_privacy_combo(self.cmb_privacy)
        bs_layout.addRow("الخصوصية الافتراضية:", self.cmb_privacy)
        self.cmb_category = QComboBox()
        populate_category_combo(self.cmb_category)
        bs_layout.addRow("التصنيف الافتراضي:", self.cmb_category)
        self.chk_kids = QCheckBox(MADE_FOR_KIDS_TEXT)
        bs_layout.addRow("الجمهور:", self.chk_kids)
        layout.addWidget(self.settings_group)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.lbl_status = plain_label("جاهز", "muted")
        layout.addWidget(self.lbl_status)

        self.file_progress = QProgressBar()
        self.file_progress.setValue(0)
        layout.addWidget(self.file_progress)

        btn_row = QHBoxLayout()
        self.btn_start = QPushButton("🚀 بدء الرفع الجماعي")
        self.btn_start.setFixedHeight(44)
        self.btn_start.setFont(bold_font(13))
        self.btn_start.clicked.connect(self._start)
        self.btn_cancel = QPushButton("⏹️ إلغاء")
        self.btn_cancel.setProperty("class", "danger")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)
        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_cancel)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------
    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "اختر فيديوهات", "", VIDEO_EXTENSIONS)
        for f in files:
            name = sanitize_title(os.path.splitext(os.path.basename(f))[0]) or "فيديو"
            job = UploadJob(
                file_path=f,
                title=name,
                category_id=self.cmb_category.currentData(),
                privacy=PRIVACY_OPTIONS[self.cmb_privacy.currentText()],
                made_for_kids=self.chk_kids.isChecked(),
            )
            self.queue.append(job)
            self.statuses[id(job)] = STATUS_PENDING
        self._refresh_table()

    def _refresh_table(self):
        self.table.setRowCount(0)
        for job in self.queue:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(os.path.basename(job.file_path)))
            self.table.setItem(row, 1, QTableWidgetItem(job.title))
            self.table.setItem(row, 2, QTableWidgetItem(CATEGORIES.get(job.category_id, job.category_id)))
            self.table.setItem(row, 3, QTableWidgetItem(PRIVACY_REVERSE.get(job.privacy, job.privacy)))
            self.table.setItem(row, COL_STATUS, QTableWidgetItem(
                self.statuses.get(id(job), STATUS_PENDING)))

    def _remove_selected(self):
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        for row in rows:
            if row < len(self.queue):
                self.statuses.pop(id(self.queue[row]), None)
                self.queue.pop(row)
        self._refresh_table()

    def _clear(self):
        self.queue.clear()
        self.statuses.clear()
        self._refresh_table()

    def _set_running(self, running: bool):
        for widget in (self.btn_add, self.btn_remove, self.btn_clear, self.settings_group,
                       self.btn_start):
            widget.setEnabled(not running)
        self.btn_cancel.setEnabled(running)

    def _set_row_status(self, index: int, text: str):
        if index < len(self._running_jobs):
            self.statuses[id(self._running_jobs[index])] = text
        if index < self.table.rowCount():
            self.table.setItem(index, COL_STATUS, QTableWidgetItem(text))

    def _start(self):
        if not self.win.require_auth():
            return
        if not self.queue:
            QMessageBox.warning(self, "تنبيه", "لا توجد فيديوهات في قائمة الانتظار")
            return

        cost = len(self.queue) * UPLOAD_QUOTA_COST
        if cost > DEFAULT_DAILY_QUOTA:
            reply = QMessageBox.question(
                self, "تنبيه الحصة",
                f"رفع {len(self.queue)} فيديو يحتاج حوالي {cost:,} وحدة، والحصة الافتراضية "
                f"{DEFAULT_DAILY_QUOTA:,} يوميًا. غالبًا ستفشل الفيديوهات الأخيرة بخطأ "
                "تجاوز الحصة.\n\nهل تريد المتابعة؟",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        self._running_jobs = list(self.queue)
        for job in self._running_jobs:
            self.statuses[id(job)] = STATUS_PENDING
        self._refresh_table()
        self._set_running(True)
        self.progress.setValue(0)
        self.file_progress.setValue(0)

        self.thread = BatchUploadThread(self.yt, self._running_jobs)
        self.thread.progress.connect(self.progress.setValue)
        self.thread.file_progress.connect(self.file_progress.setValue)
        self.thread.current_file.connect(self.lbl_status.setText)
        self.thread.item_started.connect(lambda i: self._set_row_status(i, "⏳ جاري الرفع..."))
        self.thread.item_done.connect(self._on_item_done)
        self.thread.finished.connect(self._on_done)
        self.thread.start()

    def _on_item_done(self, index, result):
        if result.get('success'):
            text = "✅ نجاح"
            if result.get('warning'):
                text += " (⚠️ خاص)" if "خاص" in result['warning'] else " (⚠️)"
        elif result.get('cancelled'):
            text = "⏹️ أُلغي"
        else:
            text = f"❌ فشل: {result.get('error', '')}"
        self._set_row_status(index, text)

    def _cancel(self):
        if self.thread is not None and self.thread.isRunning():
            self.thread.cancel()
            self.btn_cancel.setEnabled(False)
            self.lbl_status.setText("جاري الإلغاء بعد الجزء الحالي...")

    def _on_done(self, success, message, results):
        self._set_running(False)
        self.lbl_status.setText(message)

        # احذف الناجحة من القائمة حتى لا يُعاد رفعها؛ الفاشلة تبقى بحالتها لإعادة المحاولة.
        done_ids = {id(self._running_jobs[i]) for i, r in enumerate(results) if r['success']}
        self.queue = [job for job in self.queue if id(job) not in done_ids]
        for job_id in done_ids:
            self.statuses.pop(job_id, None)
        self._running_jobs = []
        self._refresh_table()

        warnings = {r['warning'] for r in results if r.get('success') and r.get('warning')}
        details = f"{message}"
        if warnings:
            details += "\n\n" + "\n".join(warnings)
        if self.queue:
            details += f"\n\nبقي {len(self.queue)} عنصر في القائمة (فشل أو لم يُرفع)."
        QMessageBox.information(self, "انتهى الرفع الجماعي", details)

    def running_threads(self):
        return [self.thread] if self.thread is not None else []
