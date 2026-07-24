#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
خيوط العمل في الخلفية (QThread) — تُبقي الواجهة مستجيبة أثناء نداءات الشبكة.
"""

from typing import Any, Callable, List

from PyQt5.QtCore import QThread, pyqtSignal

from utils import get_logger

logger = get_logger("workers")


class TaskWorker(QThread):
    """عامل عام يُنفّذ أي دالة في الخلفية ويُصدر النتيجة أو الخطأ.

    يُستخدم لكل نداءات الـAPI التي كانت تُنفّذ متزامنة على خيط الواجهة
    (قوائم التشغيل، التعديل، الإنشاء، الحذف...) لمنع تجمّد الواجهة.
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
            self.finished.emit(False, None, str(exc))


class AuthThread(QThread):
    """خيط المصادقة."""
    finished = pyqtSignal(bool, str)

    def __init__(self, yt_api) -> None:
        super().__init__()
        self.yt_api = yt_api

    def run(self) -> None:
        try:
            self.yt_api.authenticate()
            self.finished.emit(True, "تمت المصادقة بنجاح! ✓")
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("فشل المصادقة")
            self.finished.emit(False, f"خطأ في المصادقة: {exc}")


class UploadThread(QThread):
    """خيط رفع الفيديو."""
    progress = pyqtSignal(int)
    status_update = pyqtSignal(str)
    finished = pyqtSignal(bool, str, str)  # success, message, video_id

    def __init__(self, yt_api, file_path, title, description, tags,
                 category_id, privacy, scheduled_time=None, thumbnail_path=None) -> None:
        super().__init__()
        self.yt_api = yt_api
        self.file_path = file_path
        self.title = title
        self.description = description
        self.tags = tags
        self.category_id = category_id
        self.privacy = privacy
        self.scheduled_time = scheduled_time
        self.thumbnail_path = thumbnail_path
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            self.status_update.emit("جاري تحضير الفيديو للرفع...")
            video_id = self.yt_api.upload_video(
                file_path=self.file_path,
                title=self.title,
                description=self.description,
                tags=self.tags,
                category_id=self.category_id,
                privacy=self.privacy,
                scheduled_time=self.scheduled_time,
                thumbnail_path=self.thumbnail_path,
                progress_callback=self.progress.emit,
                status_callback=self.status_update.emit,
                cancel_callback=lambda: self._cancelled,
            )
            self.finished.emit(True, f"تم رفع الفيديو بنجاح!\nمعرف الفيديو: {video_id}", video_id)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("فشل رفع الفيديو")
            self.finished.emit(False, f"خطأ في الرفع: {exc}", "")


class LoadVideosThread(QThread):
    """خيط تحميل قائمة الفيديوهات."""
    finished = pyqtSignal(bool, object, str)

    def __init__(self, yt_api, max_results: int = 50) -> None:
        super().__init__()
        self.yt_api = yt_api
        self.max_results = max_results

    def run(self) -> None:
        try:
            videos = self.yt_api.get_videos(self.max_results)
            self.finished.emit(True, videos, "")
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("فشل تحميل الفيديوهات")
            self.finished.emit(False, [], f"خطأ: {exc}")


class LoadChannelInfoThread(QThread):
    """خيط تحميل معلومات القناة."""
    finished = pyqtSignal(bool, object, str)

    def __init__(self, yt_api) -> None:
        super().__init__()
        self.yt_api = yt_api

    def run(self) -> None:
        try:
            info = self.yt_api.get_channel_statistics()
            self.finished.emit(True, info, "")
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("فشل تحميل معلومات القناة")
            self.finished.emit(False, None, f"خطأ: {exc}")


class LoadPlaylistsThread(QThread):
    """خيط تحميل قوائم التشغيل."""
    finished = pyqtSignal(bool, object, str)

    def __init__(self, yt_api) -> None:
        super().__init__()
        self.yt_api = yt_api

    def run(self) -> None:
        try:
            playlists = self.yt_api.get_playlists()
            self.finished.emit(True, playlists, "")
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("فشل تحميل قوائم التشغيل")
            self.finished.emit(False, [], f"خطأ: {exc}")


class DeleteVideoThread(QThread):
    """خيط حذف فيديو."""
    finished = pyqtSignal(bool, str)

    def __init__(self, yt_api, video_id) -> None:
        super().__init__()
        self.yt_api = yt_api
        self.video_id = video_id

    def run(self) -> None:
        try:
            self.yt_api.delete_video(self.video_id)
            self.finished.emit(True, "تم حذف الفيديو بنجاح!")
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("فشل حذف الفيديو")
            self.finished.emit(False, f"خطأ في الحذف: {exc}")


class LoadCommentsThread(QThread):
    """خيط تحميل التعليقات."""
    finished = pyqtSignal(bool, object, str)

    def __init__(self, yt_api, video_id) -> None:
        super().__init__()
        self.yt_api = yt_api
        self.video_id = video_id

    def run(self) -> None:
        try:
            comments = self.yt_api.get_video_comments(self.video_id)
            self.finished.emit(True, comments, "")
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("فشل تحميل التعليقات")
            self.finished.emit(False, [], f"خطأ: {exc}")


class BatchUploadThread(QThread):
    """خيط رفع مجموعة فيديوهات."""
    progress = pyqtSignal(int)
    current_file = pyqtSignal(str)
    file_progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str, list)

    def __init__(self, yt_api, upload_queue: List[dict]) -> None:
        super().__init__()
        self.yt_api = yt_api
        self.upload_queue = upload_queue
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        results = []
        total = len(self.upload_queue)

        for i, item in enumerate(self.upload_queue):
            if self._cancelled:
                self.finished.emit(False, "تم إلغاء الرفع", results)
                return

            self.current_file.emit(f"({i + 1}/{total}) {item['title']}")
            self.progress.emit(int((i / total) * 100))

            try:
                video_id = self.yt_api.upload_video(
                    file_path=item['file_path'],
                    title=item['title'],
                    description=item.get('description', ''),
                    tags=item.get('tags', []),
                    category_id=item.get('category_id', '22'),
                    privacy=item.get('privacy', 'private'),
                    scheduled_time=item.get('scheduled_time'),
                    thumbnail_path=item.get('thumbnail_path'),
                    progress_callback=self.file_progress.emit,
                    cancel_callback=lambda: self._cancelled,  # إلغاء أثناء الرفع
                )
                results.append({'title': item['title'], 'video_id': video_id, 'success': True})
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("فشل رفع عنصر الدفعة: %s", item.get('title'))
                results.append({'title': item['title'], 'error': str(exc), 'success': False})

        self.progress.emit(100)
        success_count = sum(1 for r in results if r['success'])
        self.finished.emit(True, f"تم رفع {success_count} من {total} فيديو بنجاح", results)
