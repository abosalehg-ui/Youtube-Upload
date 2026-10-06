#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""أدوات واجهة مشتركة بين التبويبات والنوافذ (خطوط، جداول، تمرير، وصول)."""

import unicodedata
from typing import Iterable, Sequence

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QHeaderView, QLabel, QPushButton,
    QScrollArea, QTableWidget, QVBoxLayout, QWidget,
)

from constants import CATEGORIES, DEFAULT_CATEGORY_ID, PRIVACY_OPTIONS
from styles import C


def scaled_font(point_size: int, bold: bool = False) -> QFont:
    """إنشاء خط بحجم/سماكة محدّدين مع **وراثة عائلة الخط** من خط التطبيق.

    نتفادى ترميز 'Segoe UI' في كل ودجت (لا يعرض العربية جيدًا خارج ويندوز)؛
    تُضبط العائلة مركزيًا في ``main()`` وتُطبَّق هنا تلقائيًا.
    """
    font = QFont()
    font.setPointSize(point_size)
    font.setBold(bold)
    return font


def bold_font(point_size: int) -> QFont:
    """اختصار لخط عريض بحجم محدّد."""
    return scaled_font(point_size, bold=True)


def clean_label(text: str) -> str:
    """اشتقاق اسم وصفي لقارئ الشاشة بإزالة الإيموجي/الرموز والإبقاء على الحروف والأرقام."""
    cleaned = "".join(
        ch for ch in text
        if unicodedata.category(ch)[0] in ("L", "N") or ch.isspace()
    )
    return " ".join(cleaned.split())


def apply_accessibility(root: QWidget) -> None:
    """تعيين accessibleName لكل زر يفتقده داخل ``root``، مشتقًّا من نصّه بلا إيموجي."""
    for btn in root.findChildren(QPushButton):
        if not btn.accessibleName():
            name = clean_label(btn.text())
            if name:
                btn.setAccessibleName(name)


def plain_label(text: str = "", cls: str = "") -> QLabel:
    """QLabel يعرض النص حرفيًا (PlainText) — لأي نص قادم من الـAPI أو من رسائل الخطأ."""
    label = QLabel(text)
    label.setTextFormat(Qt.PlainText)
    if cls:
        label.setProperty("class", cls)
    return label


def populate_category_combo(combo: QComboBox) -> None:
    """تعبئة قائمة منسدلة بالتصنيفات."""
    for cid, cname in sorted(CATEGORIES.items(), key=lambda x: x[1]):
        combo.addItem(cname, cid)
    default_name = CATEGORIES.get(DEFAULT_CATEGORY_ID)
    if default_name:
        combo.setCurrentText(default_name)


def populate_privacy_combo(combo: QComboBox) -> None:
    """تعبئة قائمة منسدلة بخيارات الخصوصية."""
    for label in PRIVACY_OPTIONS:
        combo.addItem(label)


def make_table(headers: Sequence[str], stretch: Iterable[int] = (0,),
               widths: dict = None) -> QTableWidget:
    """جدول للقراءة فقط بإعدادات موحّدة (تحديد صفوف، ألوان متناوبة، بلا رأس عمودي)."""
    table = QTableWidget()
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(list(headers))
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    for col in stretch:
        table.horizontalHeader().setSectionResizeMode(col, QHeaderView.Stretch)
    for col, width in (widths or {}).items():
        table.setColumnWidth(col, width)
    return table


def scrollable(inner: QWidget) -> QWidget:
    """لفّ ودجت داخل منطقة تمرير حتى لا يُقصّ المحتوى على الشاشات الصغيرة."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(inner)
    wrapper = QWidget()
    wrapper_layout = QVBoxLayout(wrapper)
    wrapper_layout.setContentsMargins(0, 0, 0, 0)
    wrapper_layout.addWidget(scroll)
    return wrapper


def create_stat_card(title, value, color=None) -> QFrame:
    """إنشاء بطاقة إحصائية."""
    card = QFrame()
    card.setMinimumHeight(130)
    card.setStyleSheet(f"""
        QFrame {{
            background: {C['card']};
            border: 1px solid {C['border']};
            border-radius: 16px;
            padding: 14px;
        }}
        QFrame:hover {{
            border-color: {color or C['accent']};
            background: {C['card_hover']};
        }}
    """)
    layout = QVBoxLayout(card)
    layout.setAlignment(Qt.AlignCenter)
    layout.setSpacing(8)

    val_label = plain_label(str(value))
    val_label.setAlignment(Qt.AlignCenter)
    val_label.setFont(bold_font(32))
    val_label.setStyleSheet(f"color: {color or C['accent']}; border: none;")

    title_label = plain_label(title)
    title_label.setAlignment(Qt.AlignCenter)
    title_label.setFont(scaled_font(12))
    title_label.setStyleSheet(f"color: {C['text2']}; border: none;")

    layout.addWidget(val_label)
    layout.addWidget(title_label)

    # مراجع مباشرة لتفادي الاقتران الهش بالوصول إلى العناصر بالفهرس.
    card.val_label = val_label
    card.title_label = title_label
    return card


class BaseTab(QWidget):
    """أساس لكل تبويب: محتوى داخل منطقة تمرير + وصول مختصر للنافذة الرئيسية.

    يبني التبويب الفرعي عناصره داخل ``self.body`` (تخطيط عمودي).
    """

    def __init__(self, win, margins: int = 16, spacing: int = 12) -> None:
        super().__init__()
        self.win = win
        inner = QWidget()
        self.body = QVBoxLayout(inner)
        self.body.setContentsMargins(margins, margins, margins, margins)
        self.body.setSpacing(spacing)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scrollable(inner))

    @property
    def yt(self):
        return self.win.yt

    def status(self, message: str, timeout: int = 0) -> None:
        self.win.statusBar().showMessage(message, timeout)

    def reset(self) -> None:
        """تصفير بيانات الحساب المعروضة (يُستدعى عند تسجيل الخروج)."""

    def running_threads(self) -> list:
        """خيوط مخصّصة يملكها التبويب (للانتظار عند إغلاق التطبيق)."""
        return []
