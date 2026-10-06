#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube Upload - التطبيق الرئيسي
تطبيق شامل لإدارة قناة يوتيوب.

هذا الملف يحوي النافذة الرئيسية (الترويسة، التبويبات، المصادقة، الخيوط)؛
كل تبويب في ملف مستقل داخل ``ui/``.
"""

import os
import sys
import traceback


# ===== Fix Qt platform plugin path (MUST be before any PyQt5 import) =====
def _fix_qt_plugin_path():
    try:
        import PyQt5
    except ImportError:
        return  # سيظهر خطأ الاستيراد الحقيقي لاحقًا برسالة واضحة
    qt_dir = os.path.dirname(PyQt5.__file__)
    for path in (os.path.join(qt_dir, 'Qt5', 'plugins', 'platforms'),
                 os.path.join(qt_dir, 'Qt', 'plugins', 'platforms'),
                 os.path.join(qt_dir, 'plugins', 'platforms')):
        if os.path.isdir(path):
            os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = path
            break
    # Also add Qt bin to PATH for DLL loading (Windows)
    for path in (os.path.join(qt_dir, 'Qt5', 'bin'), os.path.join(qt_dir, 'Qt', 'bin')):
        if os.path.isdir(path):
            os.environ['PATH'] = path + os.pathsep + os.environ.get('PATH', '')
            break


_fix_qt_plugin_path()

# ===== DPI Scaling for 4K displays =====
os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '1'
os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '1'

from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtGui import QFont, QKeySequence  # noqa: E402
from PyQt5.QtWidgets import (  # noqa: E402
    QApplication, QFrame, QHBoxLayout, QMainWindow, QMessageBox, QPushButton,
    QTabWidget, QVBoxLayout, QWidget,
)

from constants import APP_NAME, APP_VERSION  # noqa: E402
from styles import C, STYLESHEET  # noqa: E402
from ui.batch_tab import BatchTab  # noqa: E402
from ui.common import apply_accessibility, bold_font, plain_label  # noqa: E402
from ui.dashboard_tab import DashboardTab  # noqa: E402
from ui.playlists_tab import PlaylistsTab  # noqa: E402
from ui.settings_tab import SettingsTab  # noqa: E402
from ui.upload_tab import UploadTab  # noqa: E402
from ui.videos_tab import VideosTab  # noqa: E402
from utils import data_path, get_logger, setup_logging  # noqa: E402
from workers import TaskWorker  # noqa: E402
from yt_api import LEGACY_TOKEN_FILE, TOKEN_FILE, YouTubeAPI  # noqa: E402

logger = get_logger("main")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.yt = YouTubeAPI()
        self._threads = []  # الاحتفاظ بمراجع الخيوط لمنع جمعها مبكرًا

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        # حد أدنى يناسب شاشات 1366×768 الشائعة
        self.setMinimumSize(1100, 700)
        self.resize(1400, 900)
        self.setLayoutDirection(Qt.RightToLeft)

        self._build_ui()
        self._check_existing_token()

    # ================================================================
    #  أدوات مشتركة تستخدمها التبويبات
    # ================================================================
    def require_auth(self) -> bool:
        """التحقق من المصادقة وإظهار تنبيه موحّد عند غيابها. يُرجع True إذا مُصادَق."""
        if not self.yt.is_authenticated():
            QMessageBox.warning(self, "تنبيه", "يرجى تسجيل الدخول أولاً")
            return False
        return True

    def report_error(self, title: str, error: str, dialog: bool = True) -> None:
        """عرض خطأ موحّد: يحدّث شريط الحالة (لا يبقى عالقًا على "جاري...") ونافذة اختيارية."""
        self.statusBar().showMessage(f"❌ {title}: {error}", 8000)
        if dialog:
            QMessageBox.critical(self, title, error)

    def run_async(self, fn, on_done, *args, busy=None, **kwargs):
        """تشغيل نداء API في خيط خلفية عام مع تنظيف المرجع بعد الانتهاء.

        on_done: دالة بالتوقيع (success: bool, result, error: str).
        busy: ودجت يُعطَّل أثناء التنفيذ لمنع الطلبات المكررة بالنقر المتكرر.
        """
        worker = TaskWorker(fn, *args, **kwargs)
        self._threads.append(worker)
        if busy is not None:
            busy.setEnabled(False)

        def _handle(success, result, error, _w=worker):
            try:
                on_done(success, result, error)
            finally:
                if busy is not None:
                    busy.setEnabled(True)
                if _w in self._threads:
                    self._threads.remove(_w)

        worker.finished.connect(_handle)
        worker.start()
        return worker

    def _running_threads(self):
        """كل خيوط الخلفية الحيّة (العامة + خيوط الرفع في التبويبات)."""
        threads = list(self._threads)
        for tab in self._all_tabs:
            threads.extend(tab.running_threads())
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
        main_layout.addWidget(self._build_header())

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        self.tab_dashboard = DashboardTab(self)
        self.tab_upload = UploadTab(self)
        self.tab_videos = VideosTab(self)
        self.tab_playlists = PlaylistsTab(self)
        self.tab_batch = BatchTab(self)
        self.tab_settings = SettingsTab(self)
        self._all_tabs = (self.tab_dashboard, self.tab_upload, self.tab_videos,
                          self.tab_playlists, self.tab_batch, self.tab_settings)

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

        self.statusBar().showMessage("مرحباً بك في YouTube Upload! قم بتسجيل الدخول للبدء.")

        # أسماء وصفية لكل الأزرار (لقارئات الشاشة) دون المساس بما ضُبط يدويًا.
        apply_accessibility(self)

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

        title = plain_label(f"▶  {APP_NAME}")
        title.setFont(bold_font(22))
        title.setStyleSheet(f"color: {C['accent']}; border: none;")

        version = plain_label(f"الإصدار {APP_VERSION}", "hint")
        version.setStyleSheet("border: none;")

        left = QVBoxLayout()
        left.setSpacing(0)
        left.addWidget(title)
        left.addWidget(version)

        self.btn_auth = QPushButton("🔐 تسجيل الدخول")
        self.btn_auth.setMinimumWidth(180)
        self.btn_auth.setToolTip("تسجيل الدخول بحساب Google (Ctrl+L)")
        self.btn_auth.setAccessibleName("زر تسجيل الدخول")
        self.btn_auth.setShortcut(QKeySequence("Ctrl+L"))
        self.btn_auth.clicked.connect(self._do_auth)

        self.lbl_auth_status = plain_label("", "hint")
        self.lbl_auth_status.setStyleSheet("border: none;")

        right = QHBoxLayout()
        right.addWidget(self.lbl_auth_status)
        right.addWidget(self.btn_auth)

        layout.addLayout(left)
        layout.addStretch()
        layout.addLayout(right)
        return header

    # ================================================================
    #  المصادقة
    # ================================================================
    def _check_existing_token(self):
        """تسجيل دخول تلقائي إذا وُجد توكن محفوظ (بما فيه الموجود في المكان القديم)."""
        candidates = (TOKEN_FILE, LEGACY_TOKEN_FILE,
                      os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.json"),
                      os.path.join(os.path.dirname(os.path.abspath(__file__)), "token.pickle"))
        if any(os.path.exists(p) for p in candidates):
            self.statusBar().showMessage("جاري المصادقة التلقائية...")
            self._do_auth()

    def _do_auth(self):
        if self.yt.is_authenticated():
            self.tab_dashboard.refresh()
            return
        has_token = os.path.exists(TOKEN_FILE) or os.path.exists(LEGACY_TOKEN_FILE)
        if not has_token and not os.path.exists(self.yt.client_secret_path):
            QMessageBox.warning(
                self, "خطأ",
                "ملف client_secret.json غير موجود!\n"
                "اختره من تبويب الإعدادات ← \"تغيير ملف client_secret\"، "
                "أو ضعه في مجلد التطبيق."
            )
            return

        self.btn_auth.setText("⏳ جاري المصادقة...")
        self.statusBar().showMessage("جاري المصادقة مع Google...")
        self.run_async(self.yt.authenticate, self._on_auth_done, busy=self.btn_auth)

    def _on_auth_done(self, success, result, error):
        if success:
            self.btn_auth.setText("✅ متصل")
            self.btn_auth.setStyleSheet(f"background: {C['success']};")
            self.lbl_auth_status.setText("متصل")
            self.lbl_auth_status.setStyleSheet(f"color: {C['success']}; border: none;")
            self.statusBar().showMessage("تمت المصادقة بنجاح! ✓", 5000)
            self.tab_dashboard.refresh()
        else:
            self.btn_auth.setText("🔐 تسجيل الدخول")
            self.lbl_auth_status.setText("غير متصل")
            self.lbl_auth_status.setStyleSheet(f"color: {C['error']}; border: none;")
            self.report_error("خطأ في المصادقة", error)

    def logout(self, confirm: bool = True):
        """تسجيل الخروج وتصفير كل بيانات الحساب المعروضة في التبويبات."""
        if confirm:
            reply = QMessageBox.question(
                self, "تسجيل الخروج",
                "هل تريد تسجيل الخروج وحذف بيانات الجلسة؟",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
        self.yt.logout()
        for tab in self._all_tabs:
            tab.reset()
        self.btn_auth.setText("🔐 تسجيل الدخول")
        self.btn_auth.setStyleSheet("")
        self.lbl_auth_status.setText("")
        self.statusBar().showMessage("تم تسجيل الخروج بنجاح", 3000)


# ================================================================
#  التشغيل
# ================================================================
def _install_excepthook():
    """بديل لسلوك PyQt5 الافتراضي (qFatal ← إغلاق التطبيق) عند استثناء داخل slot.

    PyQt5 يستدعي ``sys.excepthook`` بدل الإنهاء إذا لم يكن الافتراضي، فنسجّل الخطأ
    ونعرضه للمستخدم ويستمر التطبيق.
    """
    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        logger.error("استثناء غير معالج:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        app = QApplication.instance()
        if app is not None:
            QMessageBox.critical(
                app.activeWindow(), "خطأ غير متوقع",
                f"حدث خطأ غير متوقع، والتطبيق مستمر في العمل:\n\n{exc}\n\n"
                f"التفاصيل في ملف السجل: {data_path('youtube_upload.log')}"
            )

    sys.excepthook = hook


def main():
    os.environ['QT_HASH_SEED'] = '0'

    setup_logging(log_file=data_path("youtube_upload.log"))
    logger.info("بدء تشغيل %s v%s", APP_NAME, APP_VERSION)
    _install_excepthook()

    # Enable High DPI scaling (MUST be before QApplication)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setLayoutDirection(Qt.RightToLeft)
    app.setStyleSheet(STYLESHEET)

    # عائلة خط مركزية مع بدائل تدعم العربية عبر المنصات (Segoe UI على ويندوز،
    # Tahoma/Arial كبدائل). كل الودجت ترث هذه العائلة عبر scaled_font.
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
