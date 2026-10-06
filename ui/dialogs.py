#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""نوافذ الحوار: تعديل الفيديو، والتعليقات."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QMessageBox,
    QPushButton, QTableWidgetItem, QTextEdit, QVBoxLayout,
)

from constants import PRIVACY_OPTIONS, PRIVACY_REVERSE
from ui.common import (
    apply_accessibility, make_table, plain_label, populate_category_combo,
    populate_privacy_combo,
)
from utils import (
    MAX_TITLE_LENGTH, format_date, parse_tags, sanitize_title, validate_tags,
)


class EditVideoDialog(QDialog):
    def __init__(self, video, parent=None):
        super().__init__(parent)
        self.video = video
        self.setWindowTitle(f"تعديل: {video['title'][:50]}")
        self.setMinimumSize(550, 500)
        self.setLayoutDirection(Qt.RightToLeft)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(12)

        self.txt_title = QLineEdit(video['title'])
        self.txt_title.setMaxLength(MAX_TITLE_LENGTH)
        form.addRow("العنوان:", self.txt_title)

        self.txt_desc = QTextEdit()
        self.txt_desc.setAcceptRichText(False)
        self.txt_desc.setPlainText(video.get('description', ''))
        self.txt_desc.setMaximumHeight(150)
        form.addRow("الوصف:", self.txt_desc)

        self.txt_tags = QLineEdit(", ".join(video.get('tags', [])))
        form.addRow("الوسوم:", self.txt_tags)

        self.cmb_category = QComboBox()
        populate_category_combo(self.cmb_category)
        if video.get('categoryId'):
            idx = self.cmb_category.findData(video['categoryId'])
            if idx >= 0:
                self.cmb_category.setCurrentIndex(idx)
        form.addRow("التصنيف:", self.cmb_category)

        self.cmb_privacy = QComboBox()
        populate_privacy_combo(self.cmb_privacy)
        current_privacy = PRIVACY_REVERSE.get(video.get('privacy', 'public'), 'عام')
        self.cmb_privacy.setCurrentText(current_privacy)
        form.addRow("الخصوصية:", self.cmb_privacy)

        layout.addLayout(form)

        if video.get('publishAt'):
            note = plain_label(
                f"هذا الفيديو مجدول للنشر في {format_date(video['publishAt'])} (UTC). "
                "إبقاء الخصوصية \"خاص\" يحافظ على الجدولة، وتغييرها يلغيها.",
                "warning",
            )
            note.setWordWrap(True)
            layout.addWidget(note)

        btn_box = QDialogButtonBox()
        btn_box.addButton("💾 حفظ", QDialogButtonBox.AcceptRole)
        btn_box.addButton("إلغاء", QDialogButtonBox.RejectRole)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        apply_accessibility(self)

    def accept(self):
        error = validate_tags(parse_tags(self.txt_tags.text()))
        if error:
            QMessageBox.warning(self, "تنبيه", error)
            return
        if not sanitize_title(self.txt_title.text()):
            QMessageBox.warning(self, "تنبيه", "العنوان لا يمكن أن يكون فارغًا")
            return
        super().accept()

    def get_data(self):
        return {
            'title': sanitize_title(self.txt_title.text()),
            'description': self.txt_desc.toPlainText(),
            'tags': parse_tags(self.txt_tags.text()),
            'category_id': self.cmb_category.currentData(),
            'privacy': PRIVACY_OPTIONS[self.cmb_privacy.currentText()],
        }


class CommentsDialog(QDialog):
    """نافذة التعليقات — تُحذف عند الإغلاق، وخيط التحميل مسجّل لدى النافذة الرئيسية."""

    def __init__(self, win, video_id, title):
        super().__init__(win)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self._closed = False
        self.setWindowTitle(f"💬 تعليقات: {title[:50]}")
        self.setMinimumSize(600, 500)
        self.setLayoutDirection(Qt.RightToLeft)

        layout = QVBoxLayout(self)

        self.comments_table = make_table(
            ["الكاتب", "التعليق", "الإعجابات", "التاريخ"],
            stretch=(1,), widths={0: 150, 2: 80, 3: 130},
        )
        self.comments_table.setWordWrap(True)
        layout.addWidget(self.comments_table)

        self.lbl_status = plain_label("جاري التحميل...")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_status)

        btn_close = QPushButton("إغلاق")
        btn_close.setProperty("class", "flat")
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close)

        apply_accessibility(self)
        # run_async يسجّل الخيط لدى النافذة الرئيسية فينتظره closeEvent عند الخروج.
        win.run_async(win.yt.get_video_comments, self._on_loaded, video_id)

    def done(self, result):
        self._closed = True
        super().done(result)

    def _on_loaded(self, success, comments, error):
        if self._closed:  # أُغلقت النافذة قبل وصول الرد
            return
        if success:
            self.comments_table.setRowCount(0)
            for c in comments:
                row = self.comments_table.rowCount()
                self.comments_table.insertRow(row)
                self.comments_table.setItem(row, 0, QTableWidgetItem(c['author']))
                self.comments_table.setItem(row, 1, QTableWidgetItem(c['text'][:500]))
                self.comments_table.setItem(row, 2, QTableWidgetItem(str(c['likes'])))
                self.comments_table.setItem(row, 3, QTableWidgetItem(format_date(c['publishedAt'])))
            self.comments_table.resizeRowsToContents()
            self.lbl_status.setText(f"{len(comments)} تعليق")
        else:
            self.lbl_status.setText(f"خطأ: {error}")
