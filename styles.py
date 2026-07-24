#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
نظام الألوان وورقة الأنماط (QSS) — مفصولة عن الثوابت لتسهيل الصيانة.
ثيم ليلي OLED. رُفِع تباين ألوان النص الثانوي لتحسين إمكانية الوصول (WCAG).
"""

# ═══════════════════════════════════════════
#  نظام الألوان - ثيم ليلي OLED
# ═══════════════════════════════════════════
C = {
    "bg":           "#08080f",
    "bg2":          "#0d0d18",
    "bg3":          "#131320",
    "card":         "#161628",
    "card_hover":   "#1a1a30",
    "input":        "#12121f",
    "surface":      "#1e1e35",
    "border":       "#2a2a48",   # رُفِع قليلاً لتمييز الحدود بوضوح أكبر
    "border_focus": "#ff2d55",
    "divider":      "#1f1f38",
    "accent":       "#ff2d55",
    "accent_h":     "#ff4d6f",
    "accent_press": "#cc2444",
    "accent2":      "#5856d6",
    "accent2_h":    "#6e6ce0",
    "blue":         "#0a84ff",
    "blue_h":       "#3d9eff",
    "text":         "#f5f5f7",
    "text2":        "#b4b4c6",   # كان #8e8ea0 — رُفِع التباين
    "text3":        "#8a8aa0",   # كان #5c5c6e — رُفِع التباين بوضوح
    "text_inv":     "#08080f",
    "success":      "#30d158",
    "warning":      "#ffd60a",
    "error":        "#ff453a",
    "info":         "#64d2ff",
}


STYLESHEET = f"""
* {{
    font-family: 'Segoe UI', 'Tahoma', 'Arial', sans-serif;
    outline: none;
}}
QMainWindow {{
    background-color: {C['bg']};
}}
QWidget {{
    color: {C['text']};
    font-size: 14px;
    background: transparent;
}}

/* ── Tabs ── */
QTabWidget::pane {{
    border: 1px solid {C['border']};
    background: {C['bg2']};
    border-radius: 12px;
    margin-top: -1px;
}}
QTabBar {{
    qproperty-drawBase: 0;
}}
QTabBar::tab {{
    background: transparent;
    color: {C['text2']};
    padding: 14px 28px;
    margin: 0 2px;
    border: none;
    border-bottom: 3px solid transparent;
    font-size: 15px;
    font-weight: 600;
    min-width: 140px;
}}
QTabBar::tab:selected {{
    color: {C['accent']};
    border-bottom: 3px solid {C['accent']};
    background: {C['bg2']};
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
}}
QTabBar::tab:hover:!selected {{
    color: {C['text']};
    background: {C['bg3']};
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
}}

/* ── Buttons ── */
QPushButton {{
    background: {C['accent']};
    color: white;
    border: none;
    padding: 11px 28px;
    border-radius: 10px;
    font-weight: 700;
    font-size: 14px;
    min-height: 22px;
}}
QPushButton:hover {{
    background: {C['accent_h']};
}}
QPushButton:pressed {{
    background: {C['accent_press']};
}}
QPushButton:focus {{
    border: 2px solid {C['text']};
}}
QPushButton:disabled {{
    background: {C['border']};
    color: {C['text3']};
}}
QPushButton[class="danger"] {{
    background: {C['error']};
}}
QPushButton[class="danger"]:hover {{
    background: #ff6961;
}}
QPushButton[class="success"] {{
    background: {C['success']};
    color: {C['text_inv']};
}}
QPushButton[class="success"]:hover {{
    background: #4ddb72;
}}
QPushButton[class="secondary"] {{
    background: {C['accent2']};
}}
QPushButton[class="secondary"]:hover {{
    background: {C['accent2_h']};
}}
QPushButton[class="flat"] {{
    background: transparent;
    border: 1px solid {C['border']};
    color: {C['text2']};
}}
QPushButton[class="flat"]:hover {{
    border-color: {C['accent']};
    color: {C['accent']};
    background: rgba(255,45,85,0.08);
}}
QPushButton[class="blue"] {{
    background: {C['blue']};
}}
QPushButton[class="blue"]:hover {{
    background: {C['blue_h']};
}}

/* ── Inputs ── */
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDateTimeEdit {{
    background: {C['input']};
    border: 1px solid {C['border']};
    border-radius: 10px;
    padding: 10px 16px;
    color: {C['text']};
    font-size: 14px;
    selection-background-color: {C['accent']};
    selection-color: white;
}}
QLineEdit:focus, QTextEdit:focus {{
    border: 1px solid {C['accent']};
    background: {C['bg3']};
}}
QLineEdit:hover, QTextEdit:hover {{
    border-color: {C['text3']};
}}
QComboBox::drop-down {{
    border: none;
    width: 34px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {C['text2']};
    margin-right: 12px;
}}
QComboBox QAbstractItemView {{
    background: {C['card']};
    border: 1px solid {C['border']};
    border-radius: 10px;
    color: {C['text']};
    selection-background-color: {C['accent']};
    selection-color: white;
    outline: none;
    padding: 4px;
}}
QComboBox QAbstractItemView::item {{
    padding: 8px 12px;
    min-height: 28px;
    border-radius: 6px;
}}
QDateTimeEdit::up-button, QDateTimeEdit::down-button,
QSpinBox::up-button, QSpinBox::down-button {{
    width: 28px;
    background: {C['bg3']};
    border: none;
    border-radius: 6px;
    margin: 2px;
}}
QDateTimeEdit::up-button:hover, QDateTimeEdit::down-button:hover,
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: {C['accent']};
}}

/* ── Tables ── */
QTableWidget {{
    background: {C['bg2']};
    border: 1px solid {C['border']};
    border-radius: 12px;
    gridline-color: {C['divider']};
    selection-background-color: rgba(255,45,85,0.2);
    selection-color: {C['text']};
    alternate-background-color: {C['bg3']};
    outline: none;
}}
QTableWidget::item {{
    padding: 12px 10px;
    border-bottom: 1px solid {C['divider']};
}}
QTableWidget::item:selected {{
    background: rgba(255,45,85,0.18);
    color: {C['text']};
}}
QTableWidget::item:hover {{
    background: rgba(255,255,255,0.03);
}}
QHeaderView::section {{
    background: {C['bg3']};
    color: {C['text2']};
    padding: 14px 12px;
    border: none;
    border-bottom: 2px solid {C['accent']};
    font-weight: 700;
    font-size: 13px;
}}

/* ── GroupBox ── */
QGroupBox {{
    border: 1px solid {C['border']};
    border-radius: 14px;
    margin-top: 16px;
    padding: 24px 16px 16px 16px;
    font-weight: 700;
    font-size: 15px;
    background: {C['bg2']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    padding: 4px 16px;
    color: {C['accent']};
    background: {C['bg2']};
    border-radius: 8px;
}}

/* ── Progress ── */
QProgressBar {{
    border: none;
    border-radius: 10px;
    text-align: center;
    background: {C['input']};
    height: 32px;
    font-weight: 700;
    font-size: 13px;
    color: white;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {C['accent']}, stop:1 {C['accent_h']});
    border-radius: 10px;
}}

/* ── ScrollBar ── */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: {C['border']};
    border-radius: 4px;
    min-height: 40px;
}}
QScrollBar::handle:vertical:hover {{
    background: {C['text3']};
}}
QScrollBar::handle:vertical:pressed {{
    background: {C['accent']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    height: 0;
    background: transparent;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 2px 4px;
}}
QScrollBar::handle:horizontal {{
    background: {C['border']};
    border-radius: 4px;
    min-width: 40px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    width: 0;
    background: transparent;
}}

/* ── ListWidget ── */
QListWidget {{
    background: {C['bg2']};
    border: 1px solid {C['border']};
    border-radius: 12px;
    outline: none;
    padding: 4px;
}}
QListWidget::item {{
    padding: 12px 14px;
    border-bottom: 1px solid {C['divider']};
    border-radius: 8px;
    margin: 2px 4px;
}}
QListWidget::item:selected {{
    background: rgba(255,45,85,0.18);
    color: {C['text']};
}}
QListWidget::item:hover:!selected {{
    background: rgba(255,255,255,0.03);
}}

/* ── CheckBox ── */
QCheckBox {{
    spacing: 12px;
    font-size: 14px;
}}
QCheckBox::indicator {{
    width: 24px;
    height: 24px;
    border-radius: 7px;
    border: 2px solid {C['border']};
    background: {C['input']};
}}
QCheckBox::indicator:hover {{
    border-color: {C['text3']};
}}
QCheckBox::indicator:checked {{
    background: {C['accent']};
    border-color: {C['accent']};
}}

/* ── StatusBar ── */
QStatusBar {{
    background: {C['bg']};
    color: {C['text2']};
    border-top: 1px solid {C['border']};
    padding: 6px 16px;
    font-size: 13px;
}}
QStatusBar QLabel {{
    color: {C['text2']};
}}

/* ── Dialog ── */
QDialog {{
    background: {C['bg']};
}}

/* ── Menu ── */
QMenu {{
    background: {C['card']};
    border: 1px solid {C['border']};
    border-radius: 12px;
    padding: 8px;
}}
QMenu::item {{
    padding: 10px 28px;
    border-radius: 8px;
    margin: 2px 4px;
}}
QMenu::item:selected {{
    background: rgba(255,45,85,0.18);
    color: {C['text']};
}}
QMenu::separator {{
    height: 1px;
    background: {C['divider']};
    margin: 6px 12px;
}}

/* ── ToolTip ── */
QToolTip {{
    background: {C['card']};
    border: 1px solid {C['border']};
    color: {C['text']};
    padding: 8px 14px;
    border-radius: 10px;
    font-size: 13px;
}}

/* ── Splitter ── */
QSplitter::handle {{
    background: {C['border']};
    width: 2px;
    margin: 4px;
    border-radius: 1px;
}}
QSplitter::handle:hover {{
    background: {C['accent']};
}}

/* ── Labels ── */
QLabel {{
    background: transparent;
}}

QDialogButtonBox QPushButton {{
    min-width: 100px;
}}
"""
