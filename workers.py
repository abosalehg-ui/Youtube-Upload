#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
خيوط العمل في الخلفية (QThread) — تُبقي الواجهة مستجيبة أثناء نداءات الشبكة.

القاعدة المعمارية: كل نداء API بسيط (بلا تقدّم) يُنفَّذ عبر ``TaskWorker`` العام.
تبقى الخيوط المخصّصة فقط للعمليات التي تبثّ تقدّمًا مباشرًا (الرفع الفردي
والجماعي)، لأنها تحتاج إشارات ``progress``/``status`` وإلغاءً أثناء التنفيذ.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

from PyQt5.QtCore import QThread, pyqtSignal

from constants import DEFAULT_CATEGORY_ID
from utils import get_logger, humanize_error
from yt_api import UploadCancelledError

logger = get_logger("workers")


@dataclass
class UploadJob:
    """بيانات رفع فيديو واحد (فردي أو ضمن دفعة)."""
    file_path: str
    title: str
    description: str = ""
    tags: List[str] = field(default_factory=list)
    category_id: str = DEFAULT_CATEGORY_ID
    privacy: str = "private"
    scheduled_time: Optional[str] = None
    thumbnail_path: Optional[str] = None
    made_for_kids: bool = False


def _upload(yt_api, job: UploadJob, **callbacks):
    return yt_api.upload_video(
        file_path=job.file_path,
        title=job.title,
        description=job.description,
        tags=job.tags,
        category_id=job.category_id,
        privacy=job.privacy,
        scheduled_time=job.scheduled_time,
        thumbnail_path=job.thumbnail_path,
        made_for_kids=job.made_for_kids,
        **callbacks,
    )


class TaskWorker(QThread):
    """عامل عام يُنفّذ أي دالة في الخلفية ويُصدر النتيجة أو الخطأ.

    يُستخدم لكل نداءات الـAPI البسيطة (المصادقة، تحميل القناة/الفيديوهات/
    القوائم/التعليقات، الحذف، التعديل، الإنشاء...) لمنع تجمّد الواجهة.
    رسالة الخطأ المُصدرة مفهومة للمستخدم (``humanize_error``).
    """
    finished = pyqtSignal(bool, object, str)  # success, result, error

    def __init__(self, fn: Callable[..., Any], *args, **kwargs) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            result = self._fn(*self._args, **self._kwargs)
            self.finished.emit(True, result, "")
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("فشل تنفيذ المهمة %s", getattr(self._fn, "__name__", self._fn))
            self.finished.emit(False, None, humanize_error(exc))


class UploadThread(QThread):
    """خيط رفع الفيديو (يبثّ التقدّم والحالة ويدعم الإلغاء)."""
    progress = pyqtSignal(int)
    status_update = pyqtSignal(str)
    # success, message, video_id, warning, cancelled
    finished = pyqtSignal(bool, str, str, str, bool)

    def __init__(self, yt_api, job: UploadJob) -> None:
        super().__init__()
        self.yt_api = yt_api
        self.job = job
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            self.status_update.emit("جاري تحضير الفيديو للرفع...")
            result = _upload(
                self.yt_api, self.job,
                progress_callback=self.progress.emit,
                status_callback=self.status_update.emit,
                cancel_callback=lambda: self._cancelled,
            )
            self.finished.emit(
                True, f"تم رفع الفيديو بنجاح!\nمعرف الفيديو: {result.video_id}",
                result.video_id, result.warning, False,
            )
        except UploadCancelledError:
            logger.info("أُلغي الرفع بطلب المستخدم")
            self.finished.emit(False, "تم إلغاء الرفع", "", "", True)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("فشل رفع الفيديو")
            self.finished.emit(False, f"خطأ في الرفع: {humanize_error(exc)}", "", "", False)


class BatchUploadThread(QThread):
    """خيط رفع مجموعة فيديوهات.

    يأخذ **نسخة** من قائمة الانتظار حتى لا يتأثر بتعديلها من الواجهة أثناء الرفع.
    """
    progress = pyqtSignal(int)
    current_file = pyqtSignal(str)
    file_progress = pyqtSignal(int)
    item_started = pyqtSignal(int)            # index
    item_done = pyqtSignal(int, dict)         # index, result
    finished = pyqtSignal(bool, str, list)

    def __init__(self, yt_api, upload_queue: List[UploadJob]) -> None:
        super().__init__()
        self.yt_api = yt_api
        self.upload_queue = list(upload_queue)
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        results = []
        total = len(self.upload_queue)

        for i, job in enumerate(self.upload_queue):
            if self._cancelled:
                break

            self.current_file.emit(f"({i + 1}/{total}) {job.title}")
            self.progress.emit(int((i / total) * 100))
            self.file_progress.emit(0)
            self.item_started.emit(i)

            try:
                result = _upload(
                    self.yt_api, job,
                    progress_callback=self.file_progress.emit,
                    cancel_callback=lambda: self._cancelled,  # إلغاء أثناء الرفع
                )
                entry = {'title': job.title, 'video_id': result.video_id,
                         'warning': result.warning, 'success': True}
            except UploadCancelledError:
                entry = {'title': job.title, 'cancelled': True, 'success': False}
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("فشل رفع عنصر الدفعة: %s", job.title)
                entry = {'title': job.title, 'error': humanize_error(exc), 'success': False}
            results.append(entry)
            self.item_done.emit(i, entry)

        success_count = sum(1 for r in results if r['success'])
        if self._cancelled:
            self.finished.emit(False, f"تم إلغاء الرفع ({success_count} نجح قبل الإلغاء)", results)
            return
        self.progress.emit(100)
        self.finished.emit(True, f"تم رفع {success_count} من {total} فيديو بنجاح", results)
