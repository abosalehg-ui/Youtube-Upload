#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""تبويب رفع فيديو مفرد (تفاصيل + صورة مصغّرة + جدولة + إلغاء)."""

import os

from PyQt5.QtCore import QDateTime, Qt, QUrl
from PyQt5.QtGui import QDesktopServices, QKeySequence
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDateTimeEdit, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton,
    QTextEdit, QVBoxLayout,
)

from constants import IMAGE_EXTENSIONS, PRIVACY_OPTIONS, VIDEO_EXTENSIONS
from ui.common import (
    BaseTab, bold_font, plain_label, populate_category_combo, populate_privacy_combo,
)
from utils import MAX_TITLE_LENGTH, parse_tags, sanitize_title, validate_tags
from workers import UploadJob, UploadThread
from yt_api import validate_thumbnail

MADE_FOR_KIDS_TEXT = "هذا الفيديو موجّه للأطفال (مطلوب من يوتيوب وفق قانون COPPA)"


class UploadTab(BaseTab):
    def __init__(self, win):
        super().__init__(win, margins=20, spacing=16)
        self.thread = None
        layout = self.body

        # ---- ملف الفيديو ----
        file_group = QGroupBox("ملف الفيديو")
        file_layout = QHBoxLayout(file_group)
        self.txt_video_path = QLineEdit()
        self.txt_video_path.setPlaceholderText("اختر ملف الفيديو...")
        self.txt_video_path.setReadOnly(True)
        btn_browse = QPushButton("📂 اختيار")
        btn_browse.setFixedWidth(120)
        btn_browse.clicked.connect(self._browse_video)
        file_layout.addWidget(self.txt_video_path)
        file_layout.addWidget(btn_browse)
        layout.addWidget(file_group)

        # ---- التفاصيل ----
        details_group = QGroupBox("تفاصيل الفيديو")
        form = QFormLayout(details_group)
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight)

        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText("عنوان الفيديو")
        self.txt_title.setMaxLength(MAX_TITLE_LENGTH)
        form.addRow("العنوان:", self.txt_title)

        self.txt_description = QTextEdit()
        self.txt_description.setAcceptRichText(False)
        self.txt_description.setPlaceholderText("وصف الفيديو...")
        self.txt_description.setMaximumHeight(120)
        form.addRow("الوصف:", self.txt_description)

        self.txt_tags = QLineEdit()
        self.txt_tags.setPlaceholderText("الوسوم مفصولة بفواصل (مثال: تقنية, ألعاب, ترفيه)")
        form.addRow("الوسوم:", self.txt_tags)

        self.cmb_category = QComboBox()
        populate_category_combo(self.cmb_category)
        form.addRow("التصنيف:", self.cmb_category)

        self.cmb_privacy = QComboBox()
        populate_privacy_combo(self.cmb_privacy)
        form.addRow("الخصوصية:", self.cmb_privacy)

        self.chk_kids = QCheckBox(MADE_FOR_KIDS_TEXT)
        form.addRow("الجمهور:", self.chk_kids)
        layout.addWidget(details_group)

        # ---- الصورة المصغرة ----
        thumb_group = QGroupBox("الصورة المصغرة (اختياري — JPG/PNG حتى 2MB)")
        thumb_layout = QHBoxLayout(thumb_group)
        self.txt_thumbnail = QLineEdit()
        self.txt_thumbnail.setPlaceholderText("اختر صورة مصغرة...")
        self.txt_thumbnail.setReadOnly(True)
        btn_thumb = QPushButton("🖼️ اختيار")
        btn_thumb.setFixedWidth(120)
        btn_thumb.clicked.connect(self._browse_thumbnail)
        btn_clear_thumb = QPushButton("✕")
        btn_clear_thumb.setFixedWidth(40)
        btn_clear_thumb.setProperty("class", "flat")
        btn_clear_thumb.setToolTip("مسح الصورة المصغرة")
        btn_clear_thumb.setAccessibleName("مسح الصورة المصغرة")
        btn_clear_thumb.clicked.connect(self.txt_thumbnail.clear)
        thumb_layout.addWidget(self.txt_thumbnail)
        thumb_layout.addWidget(btn_thumb)
        thumb_layout.addWidget(btn_clear_thumb)
        layout.addWidget(thumb_group)

        # ---- الجدولة ----
        sched_group = QGroupBox("جدولة النشر (اختياري)")
        sched_layout = QVBoxLayout(sched_group)
        self.chk_schedule = QCheckBox("جدولة الفيديو للنشر في وقت محدد")
        self.chk_schedule.toggled.connect(self._toggle_schedule)
        sched_layout.addWidget(self.chk_schedule)

        sched_inner = QHBoxLayout()
        self.dt_schedule = QDateTimeEdit()
        self.dt_schedule.setCalendarPopup(True)
        self.dt_schedule.setDateTime(QDateTime.currentDateTime().addSecs(3600))
        # 24 ساعة: يتفادى AM/PM الإنجليزية في واجهة عربية.
        self.dt_schedule.setDisplayFormat("yyyy-MM-dd  HH:mm")
        self.dt_schedule.setEnabled(False)
        sched_inner.addWidget(QLabel("تاريخ ووقت النشر (بتوقيت جهازك):"))
        sched_inner.addWidget(self.dt_schedule)
        sched_inner.addStretch()
        sched_layout.addLayout(sched_inner)

        note = plain_label(
            "ملاحظة: عند الجدولة سيتم ضبط الخصوصية على 'خاص' تلقائياً حتى موعد النشر", "warning")
        note.setWordWrap(True)
        sched_layout.addWidget(note)
        layout.addWidget(sched_group)

        # ---- شريط التقدم والرفع ----
        progress_group = QGroupBox("الرفع")
        progress_layout = QVBoxLayout(progress_group)
        self.progress_upload = QProgressBar()
        self.progress_upload.setValue(0)
        progress_layout.addWidget(self.progress_upload)

        self.lbl_upload_status = plain_label("جاهز للرفع", "muted")
        self.lbl_upload_status.setAlignment(Qt.AlignCenter)
        progress_layout.addWidget(self.lbl_upload_status)

        btn_row = QHBoxLayout()
        self.btn_upload = QPushButton("🚀 رفع الفيديو")
        self.btn_upload.setFixedHeight(54)
        self.btn_upload.setFont(bold_font(16))
        self.btn_upload.setToolTip("بدء رفع الفيديو (Ctrl+U)")
        self.btn_upload.setAccessibleName("زر رفع الفيديو")
        self.btn_upload.setShortcut(QKeySequence("Ctrl+U"))
        self.btn_upload.clicked.connect(self._start_upload)

        self.btn_cancel = QPushButton("⏹️ إلغاء الرفع")
        self.btn_cancel.setProperty("class", "danger")
        self.btn_cancel.setFixedHeight(54)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_upload)

        self.btn_clear_form = QPushButton("🗑️ مسح النموذج")
        self.btn_clear_form.setProperty("class", "flat")
        self.btn_clear_form.clicked.connect(self._clear_form)

        btn_row.addWidget(self.btn_upload)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_clear_form)
        progress_layout.addLayout(btn_row)
        layout.addWidget(progress_group)
        layout.addStretch()

    # ------------------------------------------------------------
    def _browse_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "اختر ملف فيديو", "", VIDEO_EXTENSIONS)
        if path:
            self.txt_video_path.setText(path)
            if not self.txt_title.text():
                name = os.path.splitext(os.path.basename(path))[0]
                self.txt_title.setText(sanitize_title(name))

    def _browse_thumbnail(self):
        path, _ = QFileDialog.getOpenFileName(self, "اختر صورة مصغرة", "", IMAGE_EXTENSIONS)
        if not path:
            return
        try:
            validate_thumbnail(path)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "صورة غير صالحة", str(exc))
            return
        self.txt_thumbnail.setText(path)

    def _toggle_schedule(self, checked):
        self.dt_schedule.setEnabled(checked)
        if checked:
            self.cmb_privacy.setCurrentText("خاص")

    def _clear_form(self):
        self.txt_video_path.clear()
        self.txt_title.clear()
        self.txt_description.clear()
        self.txt_tags.clear()
        self.txt_thumbnail.clear()
        self.chk_schedule.setChecked(False)
        self.chk_kids.setChecked(False)
        self.cmb_privacy.setCurrentIndex(0)
        self.progress_upload.setValue(0)
        self.lbl_upload_status.setText("جاهز للرفع")

    def _set_uploading(self, uploading: bool):
        self.btn_upload.setEnabled(not uploading)
        self.btn_clear_form.setEnabled(not uploading)
        self.btn_cancel.setEnabled(uploading)

    def _build_job(self):
        """تجميع بيانات النموذج والتحقق منها. يُرجع UploadJob أو None مع تنبيه."""
        file_path = self.txt_video_path.text()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار ملف فيديو صالح")
            return None

        title = sanitize_title(self.txt_title.text())
        if not title:
            QMessageBox.warning(self, "تنبيه", "يرجى إدخال عنوان الفيديو")
            return None

        tags = parse_tags(self.txt_tags.text())
        tags_error = validate_tags(tags)
        if tags_error:
            QMessageBox.warning(self, "تنبيه", tags_error)
            return None

        thumbnail = self.txt_thumbnail.text() or None
        if thumbnail:
            try:
                validate_thumbnail(thumbnail)
            except (ValueError, OSError) as exc:
                QMessageBox.warning(self, "صورة غير صالحة", str(exc))
                return None

        privacy = PRIVACY_OPTIONS[self.cmb_privacy.currentText()]
        scheduled_time = None
        if self.chk_schedule.isChecked():
            # QDateTimeEdit يُعطي وقتًا محليًا؛ نحوّله فعليًا إلى UTC قبل الوسم بـ Z.
            qdt = self.dt_schedule.dateTime()
            if qdt <= QDateTime.currentDateTime():
                QMessageBox.warning(self, "تنبيه", "وقت الجدولة يجب أن يكون في المستقبل")
                return None
            scheduled_time = qdt.toUTC().toPyDateTime().strftime("%Y-%m-%dT%H:%M:%S.000Z")
            privacy = "private"

        return UploadJob(
            file_path=file_path,
            title=title,
            description=self.txt_description.toPlainText(),
            tags=tags,
            category_id=self.cmb_category.currentData(),
            privacy=privacy,
            scheduled_time=scheduled_time,
            thumbnail_path=thumbnail,
            made_for_kids=self.chk_kids.isChecked(),
        )

    def _start_upload(self):
        if not self.win.require_auth():
            return
        job = self._build_job()
        if job is None:
            return

        self._set_uploading(True)
        self.progress_upload.setValue(0)
        self.lbl_upload_status.setText("جاري التحضير...")

        self.thread = UploadThread(self.yt, job)
        self.thread.progress.connect(self.progress_upload.setValue)
        self.thread.status_update.connect(self.lbl_upload_status.setText)
        self.thread.finished.connect(self._on_done)
        self.thread.start()

    def _cancel_upload(self):
        if self.thread is not None and self.thread.isRunning():
            self.thread.cancel()
            self.btn_cancel.setEnabled(False)
            self.lbl_upload_status.setText("جاري الإلغاء بعد الجزء الحالي...")

    def _on_done(self, success, message, video_id, warning, cancelled):
        self._set_uploading(False)

        if cancelled:
            self.progress_upload.setValue(0)
            self.lbl_upload_status.setText("⏹️ تم إلغاء الرفع")
            self.status("تم إلغاء الرفع", 3000)
            return

        if not success:
            self.progress_upload.setValue(0)
            self.lbl_upload_status.setText("❌ فشل الرفع")
            self.win.report_error("خطأ في الرفع", message)
            return

        self.progress_upload.setValue(100)
        self.lbl_upload_status.setText(f"✅ تم الرفع بنجاح! ({video_id})")
        self.status(message.replace("\n", " "), 5000)
        if warning:
            QMessageBox.warning(self, "تنبيه بعد الرفع", warning)

        reply = QMessageBox.question(
            self, "تم الرفع بنجاح! 🎉",
            f"{message}\n\nهل تريد فتح الفيديو في المتصفح؟",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            QDesktopServices.openUrl(QUrl(f"https://youtube.com/watch?v={video_id}"))
        self._clear_form()

    def running_threads(self):
        return [self.thread] if self.thread is not None else []
