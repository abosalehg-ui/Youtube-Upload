#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube Upload - التطبيق الرئيسي
تطبيق شامل لإدارة قناة يوتيوب
"""

import sys
import os
import unicodedata

# ===== Fix Qt platform plugin path (MUST be before any PyQt5 import) =====
def _fix_qt_plugin_path():
    try:
        import PyQt5
        qt_dir = os.path.dirname(PyQt5.__file__)
        candidates = [
            os.path.join(qt_dir, 'Qt5', 'plugins', 'platforms'),
            os.path.join(qt_dir, 'Qt', 'plugins', 'platforms'),
            os.path.join(qt_dir, 'plugins', 'platforms'),
        ]
        for path in candidates:
            if os.path.isdir(path):
                os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = path
                break
        # Also add Qt bin to PATH for DLL loading
        qt_bin_candidates = [
            os.path.join(qt_dir, 'Qt5', 'bin'),
            os.path.join(qt_dir, 'Qt', 'bin'),
        ]
        for path in qt_bin_candidates:
            if os.path.isdir(path):
                os.environ['PATH'] = path + os.pathsep + os.environ.get('PATH', '')
                break
    except Exception:
        pass

_fix_qt_plugin_path()
# ===== End Fix =====

# ===== Fix DPI Scaling for 4K displays =====
os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '1'
os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '1'
if hasattr(os, 'add_dll_directory'):
    pass  # Python 3.8+ on Windows
# ===== End DPI Fix =====

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QPushButton, QLabel, QLineEdit, QTextEdit, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QProgressBar,
    QMessageBox, QGroupBox, QFormLayout, QDateTimeEdit, QCheckBox,
    QFrame, QDialog, QDialogButtonBox, QListWidget, QListWidgetItem,
    QInputDialog, QMenu, QAbstractItemView,
    QScrollArea, QSplitter
)
from PyQt5.QtCore import Qt, QDateTime, QUrl
from PyQt5.QtGui import QFont, QDesktopServices, QKeySequence

from constants import *
from styles import C, STYLESHEET
from utils import setup_logging, get_logger, format_number, format_date, parse_tags
from yt_api import YouTubeAPI
from workers import UploadThread, BatchUploadThread, TaskWorker

logger = get_logger("main")


def _scaled_font(point_size: int, bold: bool = False) -> QFont:
    """إنشاء خط بحجم/سماكة محدّدين مع **وراثة عائلة الخط** من خط التطبيق.

    نتفادى ترميز 'Segoe UI' في كل ودجت (لا يعرض العربية جيدًا خارج ويندوز)؛
    تُضبط العائلة مركزيًا في ``main()`` وتُطبَّق هنا تلقائيًا.
    """
    font = QFont()
    font.setPointSize(point_size)
    font.setBold(bold)
    return font


def _bold_font(point_size: int) -> QFont:
    """اختصار لخط عريض بحجم محدّد."""
    return _scaled_font(point_size, bold=True)


def _clean_label(text: str) -> str:
    """اشتقاق اسم وصفي لقارئ الشاشة بإزالة الإيموجي/الرموز والإبقاء على الحروف والأرقام."""
    cleaned = "".join(
        ch for ch in text
        if unicodedata.category(ch)[0] in ("L", "N") or ch.isspace()
    )
    return " ".join(cleaned.split())


def populate_category_combo(combo: QComboBox) -> None:
    """تعبئة قائمة منسدلة بالتصنيفات (يُزيل التكرار عبر الواجهة)."""
    for cid, cname in sorted(CATEGORIES.items(), key=lambda x: x[1]):
        combo.addItem(cname, cid)
    default_name = CATEGORIES.get(DEFAULT_CATEGORY_ID)
    if default_name:
        combo.setCurrentText(default_name)


def populate_privacy_combo(combo: QComboBox) -> None:
    """تعبئة قائمة منسدلة بخيارات الخصوصية."""
    for label in PRIVACY_OPTIONS:
        combo.addItem(label)


def create_stat_card(title, value, color=None):
    """إنشاء بطاقة إحصائية"""
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

    val_label = QLabel(str(value))
    val_label.setAlignment(Qt.AlignCenter)
    val_label.setFont(_bold_font(32))
    val_label.setStyleSheet(f"color: {color or C['accent']}; border: none;")

    title_label = QLabel(title)
    title_label.setAlignment(Qt.AlignCenter)
    title_label.setFont(_scaled_font(12))
    title_label.setStyleSheet(f"color: {C['text2']}; border: none;")

    layout.addWidget(val_label)
    layout.addWidget(title_label)

    # مراجع مباشرة لتفادي الاقتران الهش بالوصول إلى العناصر بالفهرس.
    card.val_label = val_label
    card.title_label = title_label
    return card


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.yt = YouTubeAPI()
        self.videos_cache = []
        self.playlists_cache = []
        self.channel_info = None
        self.upload_queue = []
        self._threads = []  # الاحتفاظ بمراجع الخيوط لمنع جمعها مبكرًا

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        # حد أدنى يناسب شاشات 1366×768 الشائعة
        self.setMinimumSize(1100, 700)
        self.resize(1400, 900)
        self.setLayoutDirection(Qt.RightToLeft)

        self._build_ui()
        self._check_existing_token()

    # ================================================================
    #  أدوات مساعدة عامة
    # ================================================================
    def _check_existing_token(self):
        """التحقق من وجود توكن سابق (JSON أو pickle قديم)."""
        if os.path.exists("token.json") or os.path.exists("token.pickle"):
            self.statusBar().showMessage("جاري المصادقة التلقائية...")
            self._do_auth()

    def _require_auth(self) -> bool:
        """التحقق من المصادقة وإظهار تنبيه موحّد عند غيابها. يُرجع True إذا مُصادَق."""
        if not self.yt.is_authenticated():
            QMessageBox.warning(self, "تنبيه", "يرجى تسجيل الدخول أولاً")
            return False
        return True

    def _run_async(self, fn, on_done, *args, **kwargs):
        """تشغيل نداء API في خيط خلفية عام مع تنظيف المرجع بعد الانتهاء.

        on_done: دالة بالتوقيع (success: bool, result, error: str).
        """
        worker = TaskWorker(fn, *args, **kwargs)
        self._threads.append(worker)

        def _handle(success, result, error, _w=worker):
            try:
                on_done(success, result, error)
            finally:
                if _w in self._threads:
                    self._threads.remove(_w)

        worker.finished.connect(_handle)
        worker.start()
        return worker

    @staticmethod
    def _scrollable(inner: QWidget) -> QWidget:
        """لفّ ودجت داخل منطقة تمرير حتى لا يُقصّ المحتوى على الشاشات الصغيرة."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(scroll)
        return wrapper

    def _running_threads(self):
        """كل خيوط الخلفية الحيّة (العامة + الرفع الفردي + الرفع الجماعي)."""
        threads = list(self._threads)
        for attr in ("_upload_thread", "_batch_thread"):
            t = getattr(self, attr, None)
            if t is not None:
                threads.append(t)
        return [t for t in threads if t.isRunning()]

    def closeEvent(self, event):
        """إنهاء آمن: نمنع تدمير خيوط لا تزال تعمل (تفادي تعطّل Qt)."""
        running = self._running_threads()
        if not running:
            event.accept()
            return

        reply = QMessageBox.question(
            self, "الخروج",
            "توجد عمليات قيد التنفيذ (رفع/تحميل). هل تريد الخروج وإلغاؤها؟",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            event.ignore()
            return

        # طلب الإلغاء من خيوط الرفع التي تدعمه، ثم الانتظار حتى تنتهي كلها.
        for t in running:
            if hasattr(t, "cancel"):
                t.cancel()
        for t in running:
            t.wait(5000)
        event.accept()

    # ================================================================
    #  بناء الواجهة
    # ================================================================
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---- Header ----
        header = self._build_header()
        main_layout.addWidget(header)

        # ---- Tabs ----
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        self.tab_dashboard = self._build_dashboard_tab()
        self.tab_upload = self._build_upload_tab()
        self.tab_videos = self._build_videos_tab()
        self.tab_playlists = self._build_playlists_tab()
        self.tab_batch = self._build_batch_tab()
        self.tab_settings = self._build_settings_tab()

        self.tabs.addTab(self.tab_dashboard, "📊 لوحة التحكم")
        self.tabs.addTab(self.tab_upload,    "📤 رفع فيديو")
        self.tabs.addTab(self.tab_videos,    "🎬 الفيديوهات")
        self.tabs.addTab(self.tab_playlists, "📁 قوائم التشغيل")
        self.tabs.addTab(self.tab_batch,     "📦 رفع جماعي")
        self.tabs.addTab(self.tab_settings,  "⚙️ الإعدادات")

        tabs_container = QWidget()
        tabs_layout = QVBoxLayout(tabs_container)
        tabs_layout.setContentsMargins(12, 8, 12, 12)
        tabs_layout.addWidget(self.tabs)
        main_layout.addWidget(tabs_container)

        # ---- Status Bar ----
        self.statusBar().showMessage("مرحباً بك في YouTube Upload! قم بتسجيل الدخول للبدء.")

        # أسماء وصفية لكل الأزرار (لقارئات الشاشة) دون المساس بما ضُبط يدويًا.
        self._apply_accessibility()

    def _apply_accessibility(self):
        """تعيين accessibleName لكل زر يفتقده، مشتقًّا من نصّه بلا إيموجي."""
        for btn in self.findChildren(QPushButton):
            if not btn.accessibleName():
                name = _clean_label(btn.text())
                if name:
                    btn.setAccessibleName(name)

    def _build_header(self):
        header = QFrame()
        header.setFixedHeight(80)
        header.setStyleSheet(f"""
            QFrame {{
                background: {C['bg']};
                border-bottom: 1px solid {C['border']};
            }}
        """)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 0, 20, 0)

        # Logo + Title
        title = QLabel(f"▶  {APP_NAME}")
        title.setFont(_bold_font(22))
        title.setStyleSheet(f"color: {C['accent']}; border: none;")

        version = QLabel(f"الإصدار {APP_VERSION}")
        version.setStyleSheet(f"color: {C['text2']}; font-size: 11px; border: none;")

        left = QVBoxLayout()
        left.setSpacing(0)
        left.addWidget(title)
        left.addWidget(version)

        # Auth button
        self.btn_auth = QPushButton("🔐 تسجيل الدخول")
        self.btn_auth.setFixedWidth(180)
        self.btn_auth.setToolTip("تسجيل الدخول بحساب Google (Ctrl+L)")
        self.btn_auth.setAccessibleName("زر تسجيل الدخول")
        self.btn_auth.setShortcut(QKeySequence("Ctrl+L"))
        self.btn_auth.clicked.connect(self._do_auth)

        self.lbl_auth_status = QLabel("")
        self.lbl_auth_status.setStyleSheet(f"color: {C['text2']}; border: none; font-size: 12px;")

        right = QHBoxLayout()
        right.addWidget(self.lbl_auth_status)
        right.addWidget(self.btn_auth)

        layout.addLayout(left)
        layout.addStretch()
        layout.addLayout(right)
        return header

    # ================================================================
    #  تبويب: لوحة التحكم
    # ================================================================
    def _build_dashboard_tab(self):
        tab = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(tab)

        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # Channel name
        self.lbl_channel_name = QLabel("قم بتسجيل الدخول لعرض بيانات القناة")
        self.lbl_channel_name.setFont(_bold_font(18))
        self.lbl_channel_name.setStyleSheet(f"color: {C['accent']};")
        self.lbl_channel_name.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_channel_name)

        self.lbl_channel_desc = QLabel("")
        self.lbl_channel_desc.setAlignment(Qt.AlignCenter)
        self.lbl_channel_desc.setStyleSheet(f"color: {C['text2']};")
        self.lbl_channel_desc.setWordWrap(True)
        layout.addWidget(self.lbl_channel_desc)

        # Stats cards
        self.stats_layout = QHBoxLayout()
        self.stats_layout.setSpacing(16)

        self.stat_subscribers = create_stat_card("المشتركون", "---", C['accent'])
        self.stat_views = create_stat_card("المشاهدات", "---", C['accent2'])
        self.stat_videos = create_stat_card("الفيديوهات", "---", C['success'])
        self.stat_created = create_stat_card("تاريخ الإنشاء", "---", C['warning'])

        self.stats_layout.addWidget(self.stat_subscribers)
        self.stats_layout.addWidget(self.stat_views)
        self.stats_layout.addWidget(self.stat_videos)
        self.stats_layout.addWidget(self.stat_created)
        layout.addLayout(self.stats_layout)

        # Quick actions
        actions_group = QGroupBox("إجراءات سريعة")
        actions_layout = QHBoxLayout(actions_group)
        actions_layout.setSpacing(12)

        btn_refresh = QPushButton("🔄 تحديث البيانات")
        btn_refresh.clicked.connect(self._refresh_dashboard)
        btn_refresh.setProperty("class", "secondary")

        btn_open_channel = QPushButton("🌐 فتح القناة")
        btn_open_channel.clicked.connect(self._open_channel)
        btn_open_channel.setProperty("class", "flat")

        btn_studio = QPushButton("🎬 استوديو يوتيوب")
        btn_studio.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://studio.youtube.com")))
        btn_studio.setProperty("class", "flat")

        btn_go_upload = QPushButton("📤 رفع فيديو جديد")
        btn_go_upload.clicked.connect(lambda: self.tabs.setCurrentIndex(1))

        actions_layout.addWidget(btn_refresh)
        actions_layout.addWidget(btn_open_channel)
        actions_layout.addWidget(btn_studio)
        actions_layout.addWidget(btn_go_upload)
        layout.addLayout(QHBoxLayout())
        layout.addWidget(actions_group)

        # Recent videos preview
        recent_group = QGroupBox("أحدث الفيديوهات")
        recent_layout = QVBoxLayout(recent_group)

        self.recent_table = QTableWidget()
        self.recent_table.setColumnCount(5)
        self.recent_table.setHorizontalHeaderLabels(["العنوان", "المشاهدات", "الإعجابات", "التعليقات", "التاريخ"])
        self.recent_table.horizontalHeader().setStretchLastSection(True)
        self.recent_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.recent_table.setAlternatingRowColors(True)
        self.recent_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.recent_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.recent_table.verticalHeader().setVisible(False)
        self.recent_table.setMaximumHeight(250)
        recent_layout.addWidget(self.recent_table)

        layout.addWidget(recent_group)
        layout.addStretch()

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(scroll)
        return wrapper

    # ================================================================
    #  تبويب: رفع فيديو
    # ================================================================
    def _build_upload_tab(self):
        tab = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(tab)

        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

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
        self.txt_title.setMaxLength(100)
        form.addRow("العنوان:", self.txt_title)

        self.txt_description = QTextEdit()
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

        layout.addWidget(details_group)

        # ---- الصورة المصغرة ----
        thumb_group = QGroupBox("الصورة المصغرة (اختياري)")
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
        btn_clear_thumb.clicked.connect(lambda: self.txt_thumbnail.clear())

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
        self.dt_schedule.setDisplayFormat("yyyy-MM-dd  hh:mm AP")
        self.dt_schedule.setEnabled(False)
        sched_inner.addWidget(QLabel("تاريخ ووقت النشر:"))
        sched_inner.addWidget(self.dt_schedule)
        sched_inner.addStretch()
        sched_layout.addLayout(sched_inner)

        note = QLabel("ملاحظة: عند الجدولة سيتم ضبط الخصوصية على 'خاص' تلقائياً حتى موعد النشر")
        note.setStyleSheet(f"color: {C['warning']}; font-size: 11px;")
        note.setWordWrap(True)
        sched_layout.addWidget(note)

        layout.addWidget(sched_group)

        # ---- شريط التقدم والرفع ----
        progress_group = QGroupBox("الرفع")
        progress_layout = QVBoxLayout(progress_group)

        self.progress_upload = QProgressBar()
        self.progress_upload.setValue(0)
        progress_layout.addWidget(self.progress_upload)

        self.lbl_upload_status = QLabel("جاهز للرفع")
        self.lbl_upload_status.setAlignment(Qt.AlignCenter)
        self.lbl_upload_status.setStyleSheet(f"color: {C['text2']};")
        progress_layout.addWidget(self.lbl_upload_status)

        btn_row = QHBoxLayout()
        self.btn_upload = QPushButton("🚀 رفع الفيديو")
        self.btn_upload.setFixedHeight(54)
        self.btn_upload.setFont(_bold_font(16))
        self.btn_upload.setToolTip("بدء رفع الفيديو (Ctrl+U)")
        self.btn_upload.setAccessibleName("زر رفع الفيديو")
        self.btn_upload.setShortcut(QKeySequence("Ctrl+U"))
        self.btn_upload.clicked.connect(self._start_upload)

        btn_clear_form = QPushButton("🗑️ مسح النموذج")
        btn_clear_form.setProperty("class", "flat")
        btn_clear_form.clicked.connect(self._clear_upload_form)

        btn_row.addWidget(self.btn_upload)
        btn_row.addWidget(btn_clear_form)
        progress_layout.addLayout(btn_row)

        layout.addWidget(progress_group)
        layout.addStretch()

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(scroll)
        return wrapper

    # ================================================================
    #  تبويب: الفيديوهات
    # ================================================================
    def _build_videos_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Toolbar
        toolbar = QHBoxLayout()

        btn_load = QPushButton("🔄 تحميل الفيديوهات")
        btn_load.clicked.connect(self._load_videos)

        self.txt_search_videos = QLineEdit()
        self.txt_search_videos.setPlaceholderText("🔍 بحث في الفيديوهات...")
        self.txt_search_videos.textChanged.connect(self._filter_videos)

        self.cmb_videos_count = QComboBox()
        self.cmb_videos_count.addItems(["25", "50", "100", "200"])
        self.cmb_videos_count.setCurrentText("50")
        self.cmb_videos_count.setFixedWidth(80)

        toolbar.addWidget(btn_load)
        toolbar.addWidget(QLabel("عدد:"))
        toolbar.addWidget(self.cmb_videos_count)
        toolbar.addStretch()
        toolbar.addWidget(self.txt_search_videos)
        layout.addLayout(toolbar)

        # Table
        self.videos_table = QTableWidget()
        self.videos_table.setColumnCount(7)
        self.videos_table.setHorizontalHeaderLabels([
            "العنوان", "المشاهدات", "الإعجابات", "التعليقات", "الخصوصية", "التاريخ", "المعرف"
        ])
        self.videos_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.videos_table.setAlternatingRowColors(True)
        self.videos_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.videos_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.videos_table.verticalHeader().setVisible(False)
        self.videos_table.setColumnWidth(1, 100)
        self.videos_table.setColumnWidth(2, 100)
        self.videos_table.setColumnWidth(3, 100)
        self.videos_table.setColumnWidth(4, 100)
        self.videos_table.setColumnWidth(5, 140)
        self.videos_table.setColumnWidth(6, 120)
        self.videos_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.videos_table.customContextMenuRequested.connect(self._videos_context_menu)
        self.videos_table.doubleClicked.connect(self._open_video_in_browser)
        layout.addWidget(self.videos_table)

        # Buttons
        btns = QHBoxLayout()

        btn_edit = QPushButton("✏️ تعديل")
        btn_edit.setProperty("class", "secondary")
        btn_edit.clicked.connect(self._edit_video)

        btn_delete = QPushButton("🗑️ حذف")
        btn_delete.setProperty("class", "danger")
        btn_delete.clicked.connect(self._delete_video)

        btn_open = QPushButton("🌐 فتح في المتصفح")
        btn_open.setProperty("class", "flat")
        btn_open.clicked.connect(self._open_video_in_browser)

        btn_comments = QPushButton("💬 التعليقات")
        btn_comments.setProperty("class", "flat")
        btn_comments.clicked.connect(self._show_comments)

        self.lbl_videos_count = QLabel("0 فيديو")
        self.lbl_videos_count.setStyleSheet(f"color: {C['text2']};")

        btns.addWidget(btn_edit)
        btns.addWidget(btn_delete)
        btns.addWidget(btn_open)
        btns.addWidget(btn_comments)
        btns.addStretch()
        btns.addWidget(self.lbl_videos_count)
        layout.addLayout(btns)

        return self._scrollable(tab)

    # ================================================================
    #  تبويب: قوائم التشغيل
    # ================================================================
    def _build_playlists_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Toolbar
        toolbar = QHBoxLayout()

        btn_load = QPushButton("🔄 تحميل القوائم")
        btn_load.clicked.connect(self._load_playlists)

        btn_create = QPushButton("➕ قائمة جديدة")
        btn_create.setProperty("class", "success")
        btn_create.clicked.connect(self._create_playlist)

        toolbar.addWidget(btn_load)
        toolbar.addWidget(btn_create)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Splitter: playlists list + videos
        splitter = QSplitter(Qt.Horizontal)

        # Left: playlists
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(QLabel("📁 قوائم التشغيل"))
        self.playlists_list = QListWidget()
        self.playlists_list.currentRowChanged.connect(self._playlist_selected)
        left_layout.addWidget(self.playlists_list)

        pl_btns = QHBoxLayout()
        btn_del_pl = QPushButton("🗑️ حذف")
        btn_del_pl.setProperty("class", "danger")
        btn_del_pl.clicked.connect(self._delete_playlist)
        pl_btns.addWidget(btn_del_pl)
        pl_btns.addStretch()
        left_layout.addLayout(pl_btns)

        # Right: playlist videos
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        right_layout.addWidget(QLabel("🎬 فيديوهات القائمة"))
        self.playlist_videos_table = QTableWidget()
        self.playlist_videos_table.setColumnCount(3)
        self.playlist_videos_table.setHorizontalHeaderLabels(["العنوان", "الترتيب", "معرف الفيديو"])
        self.playlist_videos_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.playlist_videos_table.setAlternatingRowColors(True)
        self.playlist_videos_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.playlist_videos_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.playlist_videos_table.verticalHeader().setVisible(False)
        right_layout.addWidget(self.playlist_videos_table)

        pv_btns = QHBoxLayout()
        btn_add_to_pl = QPushButton("➕ إضافة فيديو")
        btn_add_to_pl.setProperty("class", "secondary")
        btn_add_to_pl.clicked.connect(self._add_video_to_playlist)

        btn_remove_from_pl = QPushButton("➖ إزالة")
        btn_remove_from_pl.setProperty("class", "danger")
        btn_remove_from_pl.clicked.connect(self._remove_from_playlist)

        pv_btns.addWidget(btn_add_to_pl)
        pv_btns.addWidget(btn_remove_from_pl)
        pv_btns.addStretch()
        right_layout.addLayout(pv_btns)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([350, 650])
        layout.addWidget(splitter)

        return self._scrollable(tab)

    # ================================================================
    #  تبويب: الرفع الجماعي
    # ================================================================
    def _build_batch_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        info = QLabel("📦 الرفع الجماعي - أضف عدة فيديوهات لرفعها تلقائياً واحداً تلو الآخر")
        info.setStyleSheet(f"color: {C['text2']}; font-size: 13px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        # Queue table
        self.batch_table = QTableWidget()
        self.batch_table.setColumnCount(5)
        self.batch_table.setHorizontalHeaderLabels(["الملف", "العنوان", "التصنيف", "الخصوصية", "الحالة"])
        self.batch_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.batch_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.batch_table.setAlternatingRowColors(True)
        self.batch_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.batch_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.batch_table.verticalHeader().setVisible(False)
        layout.addWidget(self.batch_table)

        # Add / remove
        q_btns = QHBoxLayout()

        btn_add_files = QPushButton("📂 إضافة فيديوهات")
        btn_add_files.clicked.connect(self._batch_add_files)

        btn_remove_sel = QPushButton("➖ إزالة المحدد")
        btn_remove_sel.setProperty("class", "flat")
        btn_remove_sel.clicked.connect(self._batch_remove_selected)

        btn_clear_queue = QPushButton("🗑️ مسح الكل")
        btn_clear_queue.setProperty("class", "flat")
        btn_clear_queue.clicked.connect(self._batch_clear)

        q_btns.addWidget(btn_add_files)
        q_btns.addWidget(btn_remove_sel)
        q_btns.addWidget(btn_clear_queue)
        q_btns.addStretch()
        layout.addLayout(q_btns)

        # Batch settings
        batch_settings = QGroupBox("إعدادات الرفع الجماعي")
        bs_layout = QFormLayout(batch_settings)

        self.cmb_batch_privacy = QComboBox()
        populate_privacy_combo(self.cmb_batch_privacy)
        bs_layout.addRow("الخصوصية الافتراضية:", self.cmb_batch_privacy)

        self.cmb_batch_category = QComboBox()
        populate_category_combo(self.cmb_batch_category)
        bs_layout.addRow("التصنيف الافتراضي:", self.cmb_batch_category)

        layout.addWidget(batch_settings)

        # Progress
        self.batch_progress = QProgressBar()
        self.batch_progress.setValue(0)
        layout.addWidget(self.batch_progress)

        self.lbl_batch_status = QLabel("جاهز")
        self.lbl_batch_status.setAlignment(Qt.AlignCenter)
        self.lbl_batch_status.setStyleSheet(f"color: {C['text2']};")
        layout.addWidget(self.lbl_batch_status)

        self.batch_file_progress = QProgressBar()
        self.batch_file_progress.setValue(0)
        layout.addWidget(self.batch_file_progress)

        # Start
        btn_row = QHBoxLayout()
        self.btn_batch_start = QPushButton("🚀 بدء الرفع الجماعي")
        self.btn_batch_start.setFixedHeight(44)
        self.btn_batch_start.setFont(_bold_font(13))
        self.btn_batch_start.clicked.connect(self._batch_start)

        self.btn_batch_cancel = QPushButton("⏹️ إلغاء")
        self.btn_batch_cancel.setProperty("class", "danger")
        self.btn_batch_cancel.setEnabled(False)
        self.btn_batch_cancel.clicked.connect(self._batch_cancel)

        btn_row.addWidget(self.btn_batch_start)
        btn_row.addWidget(self.btn_batch_cancel)
        layout.addLayout(btn_row)

        return self._scrollable(tab)

    # ================================================================
    #  تبويب: الإعدادات
    # ================================================================
    def _build_settings_tab(self):
        tab = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(tab)

        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Auth
        auth_group = QGroupBox("المصادقة")
        auth_layout = QVBoxLayout(auth_group)

        client_id_display = (
            f"{CLIENT_ID[:30]}..." if CLIENT_ID
            else "غير محمّل — ضع ملف client_secret.json"
        )
        auth_info = QLabel(
            f"Client ID: {client_id_display}\n"
            f"ملف المصادقة: client_secret.json"
        )
        auth_info.setStyleSheet(f"color: {C['text2']}; font-size: 11px;")
        auth_info.setWordWrap(True)
        auth_layout.addWidget(auth_info)

        btn_row = QHBoxLayout()

        btn_change_secret = QPushButton("📂 تغيير ملف client_secret")
        btn_change_secret.setProperty("class", "secondary")
        btn_change_secret.clicked.connect(self._change_client_secret)

        btn_logout = QPushButton("🚪 تسجيل الخروج")
        btn_logout.setProperty("class", "danger")
        btn_logout.clicked.connect(self._logout)

        btn_row.addWidget(btn_change_secret)
        btn_row.addWidget(btn_logout)
        btn_row.addStretch()
        auth_layout.addLayout(btn_row)
        layout.addWidget(auth_group)

        # About
        about_group = QGroupBox("حول التطبيق")
        about_layout = QVBoxLayout(about_group)

        about_text = QLabel(
            f"<div style='text-align:center; padding: 20px;'>"
            f"<p style='font-size:36px;'>&#9654;</p>"
            f"<h2 style='color:{C['accent']}; font-size:24px; margin:8px;'>{APP_NAME}</h2>"
            f"<p style='color:{C['text2']}; font-size:14px;'>الإصدار {APP_VERSION}</p>"
            f"<br>"
            f"<p style='color:{C['text2']}; font-size:13px;'>"
            f"تطبيق شامل لإدارة قناة يوتيوب</p>"
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
        about_text.setAlignment(Qt.AlignCenter)
        about_layout.addWidget(about_text)
        layout.addWidget(about_group)

        # Dependencies
        deps_group = QGroupBox("المتطلبات")
        deps_layout = QVBoxLayout(deps_group)
        deps_text = QLabel(
            "pip install google-api-python-client google-auth-httplib2 "
            "google-auth-oauthlib PyQt5"
        )
        deps_text.setStyleSheet(f"""
            background: {C['input']};
            padding: 12px;
            border-radius: 8px;
            font-family: 'Consolas', 'Courier New';
            font-size: 12px;
        """)
        deps_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        deps_layout.addWidget(deps_text)
        layout.addWidget(deps_group)

        layout.addStretch()

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(scroll)
        return wrapper

    # ================================================================
    #  المصادقة
    # ================================================================
    def _do_auth(self):
        if not os.path.exists("client_secret.json"):
            QMessageBox.warning(
                self, "خطأ",
                "ملف client_secret.json غير موجود!\n"
                "يرجى وضع الملف في نفس مجلد التطبيق."
            )
            return

        self.btn_auth.setEnabled(False)
        self.btn_auth.setText("⏳ جاري المصادقة...")
        self.statusBar().showMessage("جاري المصادقة مع Google...")

        self._run_async(self.yt.authenticate, self._on_auth_done)

    def _on_auth_done(self, success, result, error):
        self.btn_auth.setEnabled(True)

        if success:
            self.btn_auth.setText("✅ متصل")
            self.btn_auth.setStyleSheet(f"background: {C['success']};")
            self.lbl_auth_status.setText("متصل")
            self.lbl_auth_status.setStyleSheet(f"color: {C['success']}; border: none; font-size: 12px;")
            self.statusBar().showMessage("تمت المصادقة بنجاح! ✓", 5000)
            self._refresh_dashboard()
        else:
            self.btn_auth.setText("🔐 تسجيل الدخول")
            self.lbl_auth_status.setText("غير متصل")
            self.lbl_auth_status.setStyleSheet(f"color: {C['error']}; border: none; font-size: 12px;")
            msg = f"خطأ في المصادقة: {error}"
            QMessageBox.critical(self, "خطأ في المصادقة", msg)
            self.statusBar().showMessage(msg, 5000)

    def _logout(self):
        reply = QMessageBox.question(
            self, "تسجيل الخروج",
            "هل تريد تسجيل الخروج وحذف بيانات الجلسة؟",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.yt.logout()
            self.btn_auth.setText("🔐 تسجيل الدخول")
            self.btn_auth.setStyleSheet("")
            self.lbl_auth_status.setText("")
            self.lbl_channel_name.setText("قم بتسجيل الدخول لعرض بيانات القناة")
            self.statusBar().showMessage("تم تسجيل الخروج بنجاح", 3000)

    # ================================================================
    #  لوحة التحكم - التحديث
    # ================================================================
    def _refresh_dashboard(self):
        if not self._require_auth():
            return

        self.statusBar().showMessage("جاري تحميل بيانات القناة...")
        # نداء واحد يجلب القناة مرة واحدة (إحصائيات + أحدث فيديوهات) — توفير في حصّة الـAPI.
        self._run_async(self.yt.get_dashboard_data, self._on_dashboard_loaded, 10)

    def _on_dashboard_loaded(self, success, data, error):
        if not (success and data):
            self.statusBar().showMessage(f"خطأ: {error}", 5000)
            return

        info = data['info']
        self.channel_info = info
        self.lbl_channel_name.setText(f"📺 {info['title']}")
        self.lbl_channel_desc.setText(info.get('description', '')[:200])

        # Update stat cards
        self._update_stat_card(self.stat_subscribers, "المشتركون",
                               format_number(info['subscribers']), C['accent'])
        self._update_stat_card(self.stat_views, "المشاهدات الكلية",
                               format_number(info['views']), C['accent2'])
        self._update_stat_card(self.stat_videos, "الفيديوهات",
                               str(info['video_count']), C['success'])
        self._update_stat_card(self.stat_created, "تاريخ الإنشاء",
                               format_date(info.get('published_at', '')), C['warning'])

        self._populate_recent_videos(data['videos'])
        self.statusBar().showMessage("تم تحميل بيانات القناة بنجاح ✓", 3000)

    def _populate_recent_videos(self, videos):
        self.recent_table.setRowCount(0)
        for v in videos[:10]:
            row = self.recent_table.rowCount()
            self.recent_table.insertRow(row)
            self.recent_table.setItem(row, 0, QTableWidgetItem(v['title']))
            self.recent_table.setItem(row, 1, QTableWidgetItem(format_number(v['views'])))
            self.recent_table.setItem(row, 2, QTableWidgetItem(format_number(v['likes'])))
            self.recent_table.setItem(row, 3, QTableWidgetItem(format_number(v['comments'])))
            self.recent_table.setItem(row, 4, QTableWidgetItem(format_date(v['publishedAt'])))

    def _update_stat_card(self, card, title, value, color):
        # مراجع مباشرة بدل الوصول بالفهرس (أكثر متانةً ضد تغيّر التخطيط).
        card.val_label.setText(str(value))
        card.val_label.setStyleSheet(f"color: {color}; border: none;")
        card.title_label.setText(title)

    def _open_channel(self):
        channel_id = (self.channel_info or {}).get('channel_id')
        if channel_id:
            QDesktopServices.openUrl(QUrl(f"https://www.youtube.com/channel/{channel_id}"))
        else:
            QDesktopServices.openUrl(QUrl("https://www.youtube.com"))

    # ================================================================
    #  رفع الفيديو
    # ================================================================
    def _browse_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "اختر ملف فيديو", "",
            VIDEO_EXTENSIONS
        )
        if path:
            self.txt_video_path.setText(path)
            if not self.txt_title.text():
                name = os.path.splitext(os.path.basename(path))[0]
                self.txt_title.setText(name)

    def _browse_thumbnail(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "اختر صورة مصغرة", "",
            IMAGE_EXTENSIONS
        )
        if path:
            self.txt_thumbnail.setText(path)

    def _toggle_schedule(self, checked):
        self.dt_schedule.setEnabled(checked)
        if checked:
            self.cmb_privacy.setCurrentText("خاص")

    def _clear_upload_form(self):
        self.txt_video_path.clear()
        self.txt_title.clear()
        self.txt_description.clear()
        self.txt_tags.clear()
        self.txt_thumbnail.clear()
        self.chk_schedule.setChecked(False)
        self.cmb_privacy.setCurrentIndex(0)
        self.progress_upload.setValue(0)
        self.lbl_upload_status.setText("جاهز للرفع")

    def _start_upload(self):
        if not self._require_auth():
            return

        file_path = self.txt_video_path.text()
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "تنبيه", "يرجى اختيار ملف فيديو صالح")
            return

        title = self.txt_title.text().strip()
        if not title:
            QMessageBox.warning(self, "تنبيه", "يرجى إدخال عنوان الفيديو")
            return

        description = self.txt_description.toPlainText()
        tags = parse_tags(self.txt_tags.text())
        category_id = self.cmb_category.currentData()
        privacy = PRIVACY_OPTIONS[self.cmb_privacy.currentText()]
        thumbnail = self.txt_thumbnail.text() or None

        scheduled_time = None
        if self.chk_schedule.isChecked():
            # QDateTimeEdit يُعطي وقتًا محليًا؛ نحوّله فعليًا إلى UTC قبل الوسم بـ Z
            # (كان الكود السابق يَسِم الوقت المحلي بـ Z فيُنشر بفارق إزاحة المنطقة).
            qdt = self.dt_schedule.dateTime()
            if qdt <= QDateTime.currentDateTime():
                QMessageBox.warning(self, "تنبيه",
                                    "وقت الجدولة يجب أن يكون في المستقبل")
                return
            dt_utc = qdt.toUTC().toPyDateTime()
            scheduled_time = dt_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            privacy = "private"

        self.btn_upload.setEnabled(False)
        self.progress_upload.setValue(0)
        self.lbl_upload_status.setText("جاري التحضير...")

        self._upload_thread = UploadThread(
            self.yt, file_path, title, description, tags,
            category_id, privacy, scheduled_time, thumbnail
        )
        self._upload_thread.progress.connect(self.progress_upload.setValue)
        self._upload_thread.status_update.connect(self.lbl_upload_status.setText)
        self._upload_thread.finished.connect(self._on_upload_done)
        self._upload_thread.start()

    def _on_upload_done(self, success, message, video_id):
        self.btn_upload.setEnabled(True)

        if success:
            self.progress_upload.setValue(100)
            self.lbl_upload_status.setText(f"✅ تم الرفع بنجاح! ({video_id})")
            self.statusBar().showMessage(message, 5000)

            reply = QMessageBox.question(
                self, "تم الرفع بنجاح! 🎉",
                f"{message}\n\nهل تريد فتح الفيديو في المتصفح؟",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                QDesktopServices.openUrl(QUrl(f"https://youtube.com/watch?v={video_id}"))

            self._clear_upload_form()
        else:
            self.progress_upload.setValue(0)
            self.lbl_upload_status.setText("❌ فشل الرفع")
            QMessageBox.critical(self, "خطأ في الرفع", message)

    # ================================================================
    #  إدارة الفيديوهات
    # ================================================================
    def _load_videos(self):
        if not self._require_auth():
            return

        max_results = int(self.cmb_videos_count.currentText())
        self.statusBar().showMessage("جاري تحميل الفيديوهات...")

        self._run_async(self.yt.get_videos, self._on_videos_loaded, max_results)

    def _on_videos_loaded(self, success, videos, error):
        if success:
            self.videos_cache = videos
            self._populate_videos_table(videos)
            self.statusBar().showMessage(f"تم تحميل {len(videos)} فيديو ✓", 3000)
        else:
            QMessageBox.critical(self, "خطأ", error)

    def _populate_videos_table(self, videos):
        self.videos_table.setRowCount(0)
        for v in videos:
            row = self.videos_table.rowCount()
            self.videos_table.insertRow(row)
            self.videos_table.setItem(row, 0, QTableWidgetItem(v['title']))
            self.videos_table.setItem(row, 1, QTableWidgetItem(format_number(v['views'])))
            self.videos_table.setItem(row, 2, QTableWidgetItem(format_number(v['likes'])))
            self.videos_table.setItem(row, 3, QTableWidgetItem(format_number(v['comments'])))
            self.videos_table.setItem(row, 4, QTableWidgetItem(
                PRIVACY_REVERSE.get(v['privacy'], v['privacy'])
            ))
            self.videos_table.setItem(row, 5, QTableWidgetItem(format_date(v['publishedAt'])))
            self.videos_table.setItem(row, 6, QTableWidgetItem(v['id']))

        self.lbl_videos_count.setText(f"{len(videos)} فيديو")

    def _filter_videos(self, text):
        if not text:
            self._populate_videos_table(self.videos_cache)
            return

        filtered = [v for v in self.videos_cache
                     if text.lower() in v['title'].lower()
                     or text.lower() in v.get('description', '').lower()]
        self._populate_videos_table(filtered)

    def _get_selected_video(self):
        row = self.videos_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد فيديو من الجدول")
            return None, None

        video_id = self.videos_table.item(row, 6).text()
        title = self.videos_table.item(row, 0).text()
        return video_id, title

    def _open_video_in_browser(self):
        video_id, _ = self._get_selected_video()
        if video_id:
            QDesktopServices.openUrl(QUrl(f"https://youtube.com/watch?v={video_id}"))

    def _videos_context_menu(self, pos):
        row = self.videos_table.rowAt(pos.y())
        if row < 0:
            return

        self.videos_table.selectRow(row)
        menu = QMenu(self)

        menu.addAction("🌐 فتح في المتصفح", self._open_video_in_browser)
        menu.addAction("✏️ تعديل", self._edit_video)
        menu.addAction("💬 التعليقات", self._show_comments)
        menu.addSeparator()
        menu.addAction("📋 نسخ الرابط", self._copy_video_link)
        menu.addAction("📋 نسخ المعرف", self._copy_video_id)
        menu.addSeparator()

        del_action = menu.addAction("🗑️ حذف")
        del_action.triggered.connect(self._delete_video)

        menu.exec_(self.videos_table.viewport().mapToGlobal(pos))

    def _copy_video_link(self):
        video_id, _ = self._get_selected_video()
        if video_id:
            QApplication.clipboard().setText(f"https://youtube.com/watch?v={video_id}")
            self.statusBar().showMessage("تم نسخ الرابط ✓", 2000)

    def _copy_video_id(self):
        video_id, _ = self._get_selected_video()
        if video_id:
            QApplication.clipboard().setText(video_id)
            self.statusBar().showMessage("تم نسخ المعرف ✓", 2000)

    def _edit_video(self):
        video_id, title = self._get_selected_video()
        if not video_id:
            return

        # Find video in cache
        video = next((v for v in self.videos_cache if v['id'] == video_id), None)
        if not video:
            return

        dialog = EditVideoDialog(video, self)
        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            self.statusBar().showMessage("جاري تحديث الفيديو...")

            def _done(success, result, error):
                if success:
                    QMessageBox.information(self, "نجاح", "تم تحديث الفيديو بنجاح! ✓")
                    self._load_videos()
                else:
                    QMessageBox.critical(self, "خطأ", f"فشل التحديث:\n{error}")

            self._run_async(
                self.yt.update_video, _done,
                video_id,
                title=data['title'],
                description=data['description'],
                tags=data['tags'],
                category_id=data['category_id'],
                privacy=data['privacy'],
            )

    def _delete_video(self):
        video_id, title = self._get_selected_video()
        if not video_id:
            return

        reply = QMessageBox.warning(
            self, "تأكيد الحذف",
            f"هل أنت متأكد من حذف هذا الفيديو؟\n\n{title}\n\nهذا الإجراء لا يمكن التراجع عنه!",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.statusBar().showMessage("جاري حذف الفيديو...")
            self._run_async(self.yt.delete_video, self._on_video_deleted, video_id)

    def _on_video_deleted(self, success, result, error):
        if success:
            self.statusBar().showMessage("تم حذف الفيديو بنجاح!", 3000)
            self._load_videos()
        else:
            QMessageBox.critical(self, "خطأ", f"خطأ في الحذف: {error}")

    def _show_comments(self):
        video_id, title = self._get_selected_video()
        if not video_id:
            return

        dialog = CommentsDialog(self.yt, video_id, title, self)
        dialog.exec_()

    # ================================================================
    #  قوائم التشغيل
    # ================================================================
    def _load_playlists(self):
        if not self._require_auth():
            return

        self.statusBar().showMessage("جاري تحميل قوائم التشغيل...")
        self._run_async(self.yt.get_playlists, self._on_playlists_loaded)

    def _on_playlists_loaded(self, success, playlists, error):
        if success:
            self.playlists_cache = playlists
            self.playlists_list.clear()
            for pl in playlists:
                item = QListWidgetItem(f"📁 {pl['title']}  ({pl['videoCount']} فيديو)")
                item.setData(Qt.UserRole, pl['id'])
                self.playlists_list.addItem(item)
            self.statusBar().showMessage(f"تم تحميل {len(playlists)} قائمة تشغيل ✓", 3000)
        else:
            QMessageBox.critical(self, "خطأ", error)

    def _playlist_selected(self, index):
        if index < 0 or index >= len(self.playlists_cache):
            return

        pl = self.playlists_cache[index]
        self.statusBar().showMessage(f"جاري تحميل فيديوهات: {pl['title']}...")

        def _done(success, items, error):
            if not success:
                QMessageBox.critical(self, "خطأ", error)
                return
            self.playlist_videos_table.setRowCount(0)
            for item in items:
                row = self.playlist_videos_table.rowCount()
                self.playlist_videos_table.insertRow(row)
                self.playlist_videos_table.setItem(row, 0, QTableWidgetItem(item['title']))
                self.playlist_videos_table.setItem(row, 1, QTableWidgetItem(str(item['position'])))
                self.playlist_videos_table.setItem(row, 2, QTableWidgetItem(item['videoId']))
                # Store playlist item id for removal
                self.playlist_videos_table.item(row, 0).setData(Qt.UserRole, item['id'])
            self.statusBar().showMessage(f"تم تحميل {len(items)} فيديو ✓", 2000)

        self._run_async(self.yt.get_playlist_items, _done, pl['id'])

    def _create_playlist(self):
        if not self._require_auth():
            return

        name, ok = QInputDialog.getText(self, "قائمة تشغيل جديدة", "اسم القائمة:")
        if not (ok and name):
            return
        desc, ok2 = QInputDialog.getText(self, "وصف القائمة", "الوصف (اختياري):")
        self.statusBar().showMessage("جاري إنشاء القائمة...")

        def _done(success, result, error):
            if success:
                QMessageBox.information(self, "نجاح", f"تم إنشاء القائمة: {name} ✓")
                self._load_playlists()
            else:
                QMessageBox.critical(self, "خطأ", error)

        self._run_async(self.yt.create_playlist, _done, name, desc if ok2 else "")

    def _delete_playlist(self):
        idx = self.playlists_list.currentRow()
        if idx < 0:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد قائمة تشغيل")
            return

        pl = self.playlists_cache[idx]
        reply = QMessageBox.warning(
            self, "تأكيد الحذف",
            f"هل تريد حذف قائمة التشغيل:\n{pl['title']}؟",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.statusBar().showMessage("جاري حذف القائمة...")

        def _done(success, result, error):
            if success:
                QMessageBox.information(self, "نجاح", "تم حذف القائمة ✓")
                self._load_playlists()
            else:
                QMessageBox.critical(self, "خطأ", error)

        self._run_async(self.yt.delete_playlist, _done, pl['id'])

    def _add_video_to_playlist(self):
        idx = self.playlists_list.currentRow()
        if idx < 0:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد قائمة تشغيل أولاً")
            return

        # منتقي من الفيديوهات المحمّلة بدل لصق المعرّف يدويًا
        if self.videos_cache:
            labels = [f"{v['title']}  —  {v['id']}" for v in self.videos_cache]
            choice, ok = QInputDialog.getItem(
                self, "إضافة فيديو", "اختر فيديو:", labels, 0, False
            )
            if not ok:
                return
            video_id = self.videos_cache[labels.index(choice)]['id']
        else:
            text, ok = QInputDialog.getText(
                self, "إضافة فيديو",
                "أدخل معرف الفيديو (Video ID):\n(حمّل تبويب الفيديوهات لاختيارها من قائمة)"
            )
            if not (ok and text):
                return
            video_id = text.strip()

        pl = self.playlists_cache[idx]
        self.statusBar().showMessage("جاري إضافة الفيديو...")

        def _done(success, result, error):
            if success:
                QMessageBox.information(self, "نجاح", "تم إضافة الفيديو ✓")
                self._playlist_selected(idx)
            else:
                QMessageBox.critical(self, "خطأ", error)

        self._run_async(self.yt.add_video_to_playlist, _done, pl['id'], video_id)

    def _remove_from_playlist(self):
        row = self.playlist_videos_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "يرجى تحديد فيديو من القائمة")
            return

        title_item = self.playlist_videos_table.item(row, 0)
        pl_item_id = title_item.data(Qt.UserRole)

        reply = QMessageBox.question(
            self, "تأكيد", f"إزالة '{title_item.text()}' من القائمة؟",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        current_idx = self.playlists_list.currentRow()
        self.statusBar().showMessage("جاري إزالة الفيديو...")

        def _done(success, result, error):
            if success:
                self._playlist_selected(current_idx)
                self.statusBar().showMessage("تم إزالة الفيديو من القائمة ✓", 2000)
            else:
                QMessageBox.critical(self, "خطأ", error)

        self._run_async(self.yt.remove_from_playlist, _done, pl_item_id)

    # ================================================================
    #  الرفع الجماعي
    # ================================================================
    def _batch_add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "اختر فيديوهات", "",
            VIDEO_EXTENSIONS
        )
        for f in files:
            name = os.path.splitext(os.path.basename(f))[0]
            self.upload_queue.append({
                'file_path': f,
                'title': name,
                'category_id': self.cmb_batch_category.currentData(),
                'privacy': PRIVACY_OPTIONS[self.cmb_batch_privacy.currentText()],
            })

        self._refresh_batch_table()

    def _refresh_batch_table(self):
        self.batch_table.setRowCount(0)
        for item in self.upload_queue:
            row = self.batch_table.rowCount()
            self.batch_table.insertRow(row)
            self.batch_table.setItem(row, 0, QTableWidgetItem(os.path.basename(item['file_path'])))
            self.batch_table.setItem(row, 1, QTableWidgetItem(item['title']))
            self.batch_table.setItem(row, 2, QTableWidgetItem(
                CATEGORIES.get(item.get('category_id', '22'), 'ترفيه')
            ))
            self.batch_table.setItem(row, 3, QTableWidgetItem(
                PRIVACY_REVERSE.get(item.get('privacy', 'private'), 'خاص')
            ))
            self.batch_table.setItem(row, 4, QTableWidgetItem("في الانتظار"))

    def _batch_remove_selected(self):
        rows = sorted(set(idx.row() for idx in self.batch_table.selectedIndexes()), reverse=True)
        for row in rows:
            if row < len(self.upload_queue):
                self.upload_queue.pop(row)
        self._refresh_batch_table()

    def _batch_clear(self):
        self.upload_queue.clear()
        self._refresh_batch_table()

    def _batch_start(self):
        if not self._require_auth():
            return

        if not self.upload_queue:
            QMessageBox.warning(self, "تنبيه", "لا توجد فيديوهات في قائمة الانتظار")
            return

        self.btn_batch_start.setEnabled(False)
        self.btn_batch_cancel.setEnabled(True)
        self.batch_progress.setValue(0)
        self.batch_file_progress.setValue(0)

        self._batch_thread = BatchUploadThread(self.yt, self.upload_queue)
        self._batch_thread.progress.connect(self.batch_progress.setValue)
        self._batch_thread.file_progress.connect(self.batch_file_progress.setValue)
        self._batch_thread.current_file.connect(self.lbl_batch_status.setText)
        self._batch_thread.finished.connect(self._on_batch_done)
        self._batch_thread.start()

    def _batch_cancel(self):
        if hasattr(self, '_batch_thread') and self._batch_thread.isRunning():
            self._batch_thread.cancel()

    def _on_batch_done(self, success, message, results):
        self.btn_batch_start.setEnabled(True)
        self.btn_batch_cancel.setEnabled(False)
        self.lbl_batch_status.setText(message)

        # Update status in table
        for i, result in enumerate(results):
            if i < self.batch_table.rowCount():
                status = "✅ نجاح" if result['success'] else "❌ فشل"
                self.batch_table.setItem(i, 4, QTableWidgetItem(status))

        QMessageBox.information(self, "انتهى الرفع الجماعي", message)

    # ================================================================
    #  الإعدادات
    # ================================================================
    def _change_client_secret(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "اختر ملف client_secret", "",
            "JSON Files (*.json)"
        )
        if path:
            import shutil
            shutil.copy2(path, "client_secret.json")
            QMessageBox.information(self, "نجاح", "تم تحديث ملف المصادقة ✓\nيرجى إعادة تسجيل الدخول")


# ================================================================
#  نافذة تعديل الفيديو
# ================================================================
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
        form.addRow("العنوان:", self.txt_title)

        self.txt_desc = QTextEdit()
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

        # Buttons
        btn_box = QDialogButtonBox()
        btn_save = btn_box.addButton("💾 حفظ", QDialogButtonBox.AcceptRole)
        btn_cancel = btn_box.addButton("إلغاء", QDialogButtonBox.RejectRole)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def get_data(self):
        return {
            'title': self.txt_title.text().strip(),
            'description': self.txt_desc.toPlainText(),
            'tags': parse_tags(self.txt_tags.text()),
            'category_id': self.cmb_category.currentData(),
            'privacy': PRIVACY_OPTIONS[self.cmb_privacy.currentText()],
        }


# ================================================================
#  نافذة التعليقات
# ================================================================
class CommentsDialog(QDialog):
    def __init__(self, yt, video_id, title, parent=None):
        super().__init__(parent)
        self.yt = yt
        self.video_id = video_id
        self.setWindowTitle(f"💬 تعليقات: {title[:50]}")
        self.setMinimumSize(600, 500)
        self.setLayoutDirection(Qt.RightToLeft)

        layout = QVBoxLayout(self)

        self.comments_table = QTableWidget()
        self.comments_table.setColumnCount(4)
        self.comments_table.setHorizontalHeaderLabels(["الكاتب", "التعليق", "الإعجابات", "التاريخ"])
        self.comments_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.comments_table.setAlternatingRowColors(True)
        self.comments_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.comments_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.comments_table.verticalHeader().setVisible(False)
        self.comments_table.setColumnWidth(0, 150)
        self.comments_table.setColumnWidth(2, 80)
        self.comments_table.setColumnWidth(3, 130)
        layout.addWidget(self.comments_table)

        self.lbl_status = QLabel("جاري التحميل...")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_status)

        btn_close = QPushButton("إغلاق")
        btn_close.setProperty("class", "flat")
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close)

        self._load_comments()

    def _load_comments(self):
        self._thread = TaskWorker(self.yt.get_video_comments, self.video_id)
        self._thread.finished.connect(self._on_loaded)
        self._thread.start()

    def _on_loaded(self, success, comments, error):
        if success:
            self.comments_table.setRowCount(0)
            for c in comments:
                row = self.comments_table.rowCount()
                self.comments_table.insertRow(row)
                self.comments_table.setItem(row, 0, QTableWidgetItem(c['author']))
                self.comments_table.setItem(row, 1, QTableWidgetItem(c['text'][:200]))
                self.comments_table.setItem(row, 2, QTableWidgetItem(str(c['likes'])))
                self.comments_table.setItem(row, 3, QTableWidgetItem(format_date(c['publishedAt'])))
            self.lbl_status.setText(f"{len(comments)} تعليق")
        else:
            self.lbl_status.setText(f"خطأ: {error}")


# ================================================================
#  التشغيل
# ================================================================
def main():
    os.environ['QT_HASH_SEED'] = '0'

    setup_logging(log_file="youtube_upload.log")
    logger.info("بدء تشغيل %s v%s", APP_NAME, APP_VERSION)

    # Enable High DPI scaling (MUST be before QApplication)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)
    app.setStyleSheet(STYLESHEET)

    # عائلة خط مركزية مع بدائل تدعم العربية عبر المنصات (Segoe UI على ويندوز،
    # Tahoma/Arial كبدائل). كل الودجت ترث هذه العائلة عبر _scaled_font.
    font = QFont()
    if hasattr(font, "setFamilies"):
        font.setFamilies(["Segoe UI", "Tahoma", "Arial", "sans-serif"])
    else:  # Qt أقدم من 5.13
        font.setFamily("Segoe UI")
    font.setPointSize(11)
    app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
