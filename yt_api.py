#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
وحدة التعامل مع YouTube Data API v3.

ملاحظات أمنية:
- تُخزَّن بيانات اعتماد المستخدم في ملف JSON (لا pickle) داخل مجلد بيانات
  التطبيق، ويُنشأ الملف بصلاحيات 0600 من اللحظة الأولى.
- لا يُخزَّن أي سرّ داخل الكود؛ تُقرأ الأسرار من client_secret.json محليًا.
"""

import mimetypes
import os
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from constants import MAX_THUMBNAIL_BYTES
from utils import client_secret_path, data_path, get_logger, migrate_legacy_file

logger = get_logger("yt_api")

# ``youtube`` يغطي الرفع والإدارة، و``youtube.force-ssl`` مطلوب لقراءة التعليقات.
SCOPES = [
    'https://www.googleapis.com/auth/youtube',
    'https://www.googleapis.com/auth/youtube.force-ssl',
]

TOKEN_FILE = data_path("token.json")
# ملف التوكن القديم (pickle) — يُهاجَر تلقائيًا ثم يُحذف.
LEGACY_TOKEN_FILE = data_path("token.pickle")

# أكواد HTTP القابلة لإعادة المحاولة (أخطاء خادم/شبكة عابرة).
RETRIABLE_STATUS_CODES = {500, 502, 503, 504}
MAX_UPLOAD_RETRIES = 5

ALLOWED_THUMBNAIL_TYPES = {"image/jpeg", "image/png"}


class UploadCancelledError(Exception):
    """يُرفع عند إلغاء المستخدم لعملية الرفع أثناء تنفيذها."""


@dataclass
class UploadResult:
    """نتيجة رفع فيديو: المعرّف + الخصوصية الفعلية + تحذير اختياري للمستخدم."""
    video_id: str
    privacy_status: str = ""
    warning: str = ""


def backoff_seconds(retries: int) -> int:
    """زمن الانتظار قبل إعادة المحاولة رقم ``retries`` (أُسّي بحد أقصى 30 ثانية)."""
    return min(2 ** retries, 30)


def validate_thumbnail(path: str) -> str:
    """التحقق من الصورة المصغّرة وإرجاع نوع MIME الصحيح، أو رفع ValueError."""
    mime, _ = mimetypes.guess_type(path)
    if mime not in ALLOWED_THUMBNAIL_TYPES:
        raise ValueError("الصورة المصغّرة يجب أن تكون JPG أو PNG")
    size = os.path.getsize(path)
    if size > MAX_THUMBNAIL_BYTES:
        raise ValueError(
            f"حجم الصورة المصغّرة {size / 1024 / 1024:.1f}MB والحد الأقصى 2MB"
        )
    return mime


def privacy_warning(requested: str, actual: str, scheduled: bool) -> str:
    """تحذير إذا قفل يوتيوب الفيديو على "خاص" رغم طلب غير ذلك.

    يحدث هذا مع مشاريع Google Cloud غير المدقّقة (unverified) المنشأة بعد 28/7/2020.
    """
    if scheduled or requested == "private" or not actual or actual == requested:
        return ""
    if actual == "private":
        return ("رُفع الفيديو لكن يوتيوب قفله على \"خاص\". غالبًا مشروع Google Cloud "
                "غير مدقّق (unverified)؛ راجع قسم \"ملاحظات مهمة\" في README.")
    return ""


class YouTubeAPI:
    """فئة إدارة YouTube API."""

    def __init__(self, client_secret_file: Optional[str] = None) -> None:
        self._client_secret_file = client_secret_file
        self.credentials: Optional[Credentials] = None
        self.youtube = None

    @property
    def client_secret_path(self) -> str:
        return self._client_secret_file or client_secret_path()

    # ============ المصادقة ============
    def _load_saved_credentials(self) -> Optional[Credentials]:
        """تحميل بيانات الاعتماد المحفوظة، مع ترحيل ملف pickle القديم إن وُجد."""
        migrate_legacy_file("token.json")
        migrate_legacy_file("token.pickle")

        if os.path.exists(TOKEN_FILE):
            try:
                return Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            except (ValueError, OSError) as exc:
                logger.warning("تعذّر قراءة %s: %s", TOKEN_FILE, exc)
                return None

        # ترحيل من التوكن القديم (pickle) مرة واحدة فقط.
        if os.path.exists(LEGACY_TOKEN_FILE):
            logger.info("العثور على توكن pickle قديم — محاولة الترحيل إلى JSON")
            try:
                import pickle  # يُستورد هنا فقط لغرض الترحيل لمرة واحدة
                with open(LEGACY_TOKEN_FILE, "rb") as fh:
                    creds = pickle.load(fh)  # noqa: S301 - ملف محلي للمستخدم فقط
                self._save_credentials(creds)
                logger.info("تم ترحيل التوكن القديم")
                return creds
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("فشل ترحيل التوكن القديم: %s", exc)
            finally:
                try:
                    os.remove(LEGACY_TOKEN_FILE)
                except OSError:
                    pass
        return None

    @staticmethod
    def _save_credentials(creds: Credentials) -> None:
        """حفظ بيانات الاعتماد كـ JSON، والملف يُنشأ بصلاحيات 0600 مباشرة (بلا نافذة زمنية)."""
        fd = os.open(TOKEN_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(creds.to_json())
        try:  # لو كان الملف موجودًا مسبقًا بصلاحيات أوسع
            os.chmod(TOKEN_FILE, 0o600)
        except OSError:
            pass

    def _run_login_flow(self) -> Credentials:
        if not os.path.exists(self.client_secret_path):
            raise FileNotFoundError(
                f"ملف الاعتماد غير موجود: {self.client_secret_path}"
            )
        logger.info("بدء تدفّق تسجيل الدخول عبر المتصفح")
        flow = InstalledAppFlow.from_client_secrets_file(self.client_secret_path, SCOPES)
        return flow.run_local_server(port=0)

    def authenticate(self) -> bool:
        """المصادقة مع Google OAuth2 (تحديث التوكن أو تدفّق تسجيل دخول جديد)."""
        creds = self._load_saved_credentials()

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("تحديث التوكن منتهي الصلاحية")
                try:
                    creds.refresh(Request())
                except RefreshError as exc:
                    # توكن ملغي أو منتهي (يحدث كل 7 أيام لمشاريع OAuth في وضع Testing)
                    logger.warning("فشل تحديث التوكن (%s) — إعادة تسجيل الدخول", exc)
                    self._remove_token_files()
                    creds = self._run_login_flow()
            else:
                creds = self._run_login_flow()
            self._save_credentials(creds)

        self.credentials = creds
        self.youtube = build('youtube', 'v3', credentials=creds)
        logger.info("تمت المصادقة وبناء عميل YouTube")
        return True

    def is_authenticated(self) -> bool:
        return self.youtube is not None

    @staticmethod
    def _remove_token_files() -> None:
        for path in (TOKEN_FILE, LEGACY_TOKEN_FILE):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError as exc:
                    logger.warning("تعذّر حذف %s: %s", path, exc)

    def logout(self) -> None:
        """تسجيل الخروج وحذف بيانات الاعتماد المحفوظة."""
        self._remove_token_files()
        self.credentials = None
        self.youtube = None
        logger.info("تم تسجيل الخروج")

    # ============ أدوات داخلية ============
    @staticmethod
    def _paginate(request_fn: Callable[..., Dict], max_results: int,
                  handle_page: Callable[[Dict], List[Dict]]) -> List[Dict]:
        """حلقة ترقيم موحّدة: تستدعي ``request_fn(maxResults=..., pageToken=...)``
        وتمرّر كل صفحة إلى ``handle_page`` الذي يُرجع العناصر المحوّلة."""
        results: List[Dict] = []
        next_page = None
        while True:
            response = request_fn(
                maxResults=min(max(max_results - len(results), 1), 50),
                pageToken=next_page,
            ).execute()
            results.extend(handle_page(response))
            next_page = response.get('nextPageToken')
            if not next_page or len(results) >= max_results:
                break
        return results[:max_results]

    # ============ معلومات القناة ============
    def get_channel_info(self) -> Optional[Dict]:
        """جلب معلومات القناة الكاملة."""
        response = self.youtube.channels().list(
            part='snippet,contentDetails,statistics,brandingSettings',
            mine=True
        ).execute()
        items = response.get('items')
        return items[0] if items else None

    @staticmethod
    def _map_channel_info(channel: Dict) -> Dict:
        """تحويل استجابة القناة الخام إلى قاموس بمفاتيح محايدة لغويًا."""
        stats = channel.get('statistics', {})
        snippet = channel.get('snippet', {})
        return {
            'channel_id': channel['id'],
            'subscribers': int(stats.get('subscriberCount', 0)),
            'views': int(stats.get('viewCount', 0)),
            'video_count': int(stats.get('videoCount', 0)),
            'title': snippet.get('title', ''),
            'description': snippet.get('description', ''),
            'thumbnail': snippet.get('thumbnails', {}).get('high', {}).get('url', ''),
            'published_at': snippet.get('publishedAt', ''),
        }

    def get_dashboard_data(self, max_videos: int = 10) -> Optional[Dict]:
        """جلب بيانات لوحة التحكم (إحصائيات + أحدث فيديوهات) بنداء قناة واحد."""
        channel = self.get_channel_info()
        if not channel:
            return None

        info = self._map_channel_info(channel)
        uploads_playlist_id = channel['contentDetails']['relatedPlaylists']['uploads']
        videos = self.get_videos(max_videos, uploads_playlist_id=uploads_playlist_id)
        return {'info': info, 'videos': videos}

    # ============ الفيديوهات ============
    def get_videos(self, max_results: int = 50,
                   uploads_playlist_id: Optional[str] = None) -> List[Dict]:
        """جلب قائمة فيديوهات القناة.

        يمكن تمرير ``uploads_playlist_id`` معروفًا مسبقًا لتفادي نداء
        ``channels().list`` إضافي (توفير في حصّة الـAPI).
        """
        if uploads_playlist_id is None:
            channel = self.get_channel_info()
            if not channel:
                return []
            uploads_playlist_id = channel['contentDetails']['relatedPlaylists']['uploads']

        def handle_page(response: Dict) -> List[Dict]:
            video_ids = [item['contentDetails']['videoId']
                         for item in response.get('items', [])]
            if not video_ids:
                return []
            details = self.youtube.videos().list(
                part='snippet,statistics,status,contentDetails',
                id=','.join(video_ids)
            ).execute()
            page = []
            for item in details.get('items', []):
                snippet = item['snippet']
                stats = item.get('statistics', {})
                page.append({
                    'id': item['id'],
                    'title': snippet['title'],
                    'description': snippet.get('description', ''),
                    'publishedAt': snippet['publishedAt'],
                    'thumbnail': snippet.get('thumbnails', {}).get('medium', {}).get('url', ''),
                    'views': int(stats.get('viewCount', 0)),
                    'likes': int(stats.get('likeCount', 0)),
                    'comments': int(stats.get('commentCount', 0)),
                    'duration': item.get('contentDetails', {}).get('duration', ''),
                    'privacy': item['status']['privacyStatus'],
                    'publishAt': item['status'].get('publishAt', ''),
                    'tags': snippet.get('tags', []),
                    'categoryId': snippet.get('categoryId', ''),
                })
            return page

        return self._paginate(
            lambda **kw: self.youtube.playlistItems().list(
                part='snippet,contentDetails', playlistId=uploads_playlist_id, **kw),
            max_results, handle_page,
        )

    def upload_video(self, file_path: str, title: str, description: str,
                     tags: Optional[List[str]], category_id, privacy: str,
                     scheduled_time: Optional[str] = None,
                     thumbnail_path: Optional[str] = None,
                     made_for_kids: bool = False,
                     progress_callback: Optional[Callable[[int], None]] = None,
                     status_callback: Optional[Callable[[str], None]] = None,
                     cancel_callback: Optional[Callable[[], bool]] = None) -> UploadResult:
        """رفع فيديو إلى يوتيوب مع إعادة محاولة للأخطاء العابرة ودعم الإلغاء."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"ملف الفيديو غير موجود: {file_path}")

        # نتحقق من المصغّرة قبل الرفع حتى لا نكتشف الخطأ بعد رفع جيجابايتات.
        thumb_mime = None
        if thumbnail_path:
            if not os.path.exists(thumbnail_path):
                raise FileNotFoundError(f"الصورة المصغّرة غير موجودة: {thumbnail_path}")
            thumb_mime = validate_thumbnail(thumbnail_path)

        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags or [],
                'categoryId': str(category_id),
            },
            'status': {
                'privacyStatus': privacy,
                'selfDeclaredMadeForKids': bool(made_for_kids),
            }
        }

        if scheduled_time:
            body['status']['privacyStatus'] = 'private'
            body['status']['publishAt'] = scheduled_time

        media = MediaFileUpload(
            file_path,
            mimetype='video/*',
            resumable=True,
            chunksize=1024 * 1024 * 5  # 5MB
        )

        request = self.youtube.videos().insert(
            part='snippet,status',
            body=body,
            media_body=media
        )

        response = None
        retries = 0
        while response is None:
            if cancel_callback and cancel_callback():
                raise UploadCancelledError("أُلغيت عملية الرفع")
            try:
                status, response = request.next_chunk()
                retries = 0  # إعادة تصفير العدّاد بعد نجاح جزء
                if status:
                    percent = int(status.progress() * 100)
                    if progress_callback:
                        progress_callback(percent)
                    if status_callback:
                        status_callback(f"جاري الرفع... {percent}%")
            except (HttpError, OSError) as exc:
                # OSError تشمل socket.error وConnectionError.
                transient = (not isinstance(exc, HttpError)
                             or exc.resp.status in RETRIABLE_STATUS_CODES)
                if not transient or retries >= MAX_UPLOAD_RETRIES:
                    raise
                retries += 1
                sleep_s = backoff_seconds(retries)
                logger.warning("خطأ عابر (%s) — إعادة المحاولة %d بعد %ss",
                               exc, retries, sleep_s)
                time.sleep(sleep_s)

        video_id = response['id']
        actual_privacy = response.get('status', {}).get('privacyStatus', '')
        logger.info("تم رفع الفيديو: %s (%s)", video_id, actual_privacy)
        result = UploadResult(
            video_id=video_id,
            privacy_status=actual_privacy,
            warning=privacy_warning(privacy, actual_privacy, bool(scheduled_time)),
        )

        if thumbnail_path:
            try:
                self.youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(thumbnail_path, mimetype=thumb_mime)
                ).execute()
                logger.info("تم رفع الصورة المصغّرة للفيديو %s", video_id)
            except HttpError as exc:
                # لا نُفشل الرفع كله بسبب المصغّرة، لكن لا نبتلع الخطأ بصمت.
                logger.warning("تعذّر رفع الصورة المصغّرة (قد تتطلب قناة موثّقة): %s", exc)
                note = "تم الرفع، لكن تعذّر ضبط الصورة المصغّرة (قد تتطلب قناة موثّقة)"
                result.warning = f"{result.warning}\n{note}".strip()
                if status_callback:
                    status_callback(note)

        return result

    def delete_video(self, video_id: str) -> bool:
        """حذف فيديو."""
        self.youtube.videos().delete(id=video_id).execute()
        logger.info("تم حذف الفيديو: %s", video_id)
        return True

    def update_video(self, video_id: str, title: Optional[str] = None,
                     description: Optional[str] = None,
                     tags: Optional[List[str]] = None, category_id=None,
                     privacy: Optional[str] = None) -> Dict:
        """تحديث بيانات فيديو.

        ``videos.update`` يستبدل الجزء (part) كاملًا ويحذف أي خاصية لا تُرسل،
        لذلك ننسخ ``snippet`` و``status`` الحاليين بالكامل ثم نعدّل عليهما فقط.
        بدون هذا يُمسح ``publishAt`` فيبقى الفيديو المجدول خاصًا للأبد.
        """
        current = self.youtube.videos().list(
            part='snippet,status',
            id=video_id
        ).execute()

        if not current.get('items'):
            raise ValueError("الفيديو غير موجود")

        item = current['items'][0]
        snippet = dict(item['snippet'])
        status = dict(item['status'])

        # حقول للقراءة فقط يرفضها videos.update أو يتجاهلها.
        for key in ('publishedAt', 'channelId', 'channelTitle', 'thumbnails',
                    'localized', 'liveBroadcastContent'):
            snippet.pop(key, None)
        for key in ('uploadStatus', 'failureReason', 'rejectionReason', 'madeForKids'):
            status.pop(key, None)

        if title:
            snippet['title'] = title
        if description is not None:
            snippet['description'] = description
        if tags is not None:
            snippet['tags'] = tags
        if category_id:
            snippet['categoryId'] = str(category_id)
        if privacy:
            status['privacyStatus'] = privacy
            # publishAt مسموح فقط مع "خاص"؛ تغيير الخصوصية يدويًا يلغي الجدولة.
            if privacy != 'private':
                status.pop('publishAt', None)

        body = {'id': video_id, 'snippet': snippet, 'status': status}
        result = self.youtube.videos().update(
            part='snippet,status',
            body=body
        ).execute()
        logger.info("تم تحديث الفيديو: %s", video_id)
        return result

    # ============ قوائم التشغيل ============
    def get_playlists(self, max_results: int = 50) -> List[Dict]:
        """جلب قوائم التشغيل."""
        def handle_page(response: Dict) -> List[Dict]:
            return [{
                'id': item['id'],
                'title': item['snippet']['title'],
                'description': item['snippet'].get('description', ''),
                'videoCount': item['contentDetails']['itemCount'],
                'privacy': item['status']['privacyStatus'],
                'thumbnail': item['snippet'].get('thumbnails', {}).get('medium', {}).get('url', ''),
                'publishedAt': item['snippet']['publishedAt'],
            } for item in response.get('items', [])]

        return self._paginate(
            lambda **kw: self.youtube.playlists().list(
                part='snippet,contentDetails,status', mine=True, **kw),
            max_results, handle_page,
        )

    def create_playlist(self, title: str, description: str = "",
                        privacy: str = "public") -> Dict:
        """إنشاء قائمة تشغيل جديدة."""
        body = {
            'snippet': {'title': title, 'description': description},
            'status': {'privacyStatus': privacy},
        }
        result = self.youtube.playlists().insert(
            part='snippet,status', body=body
        ).execute()
        logger.info("تم إنشاء قائمة تشغيل: %s", title)
        return result

    def delete_playlist(self, playlist_id: str) -> bool:
        """حذف قائمة تشغيل."""
        self.youtube.playlists().delete(id=playlist_id).execute()
        logger.info("تم حذف قائمة التشغيل: %s", playlist_id)
        return True

    def add_video_to_playlist(self, playlist_id: str, video_id: str) -> Dict:
        """إضافة فيديو لقائمة تشغيل."""
        body = {
            'snippet': {
                'playlistId': playlist_id,
                'resourceId': {'kind': 'youtube#video', 'videoId': video_id},
            }
        }
        return self.youtube.playlistItems().insert(
            part='snippet', body=body
        ).execute()

    def get_playlist_items(self, playlist_id: str,
                           max_results: int = 50) -> List[Dict]:
        """جلب عناصر قائمة التشغيل."""
        def handle_page(response: Dict) -> List[Dict]:
            return [{
                'id': item['id'],
                'videoId': item['contentDetails']['videoId'],
                'title': item['snippet']['title'],
                'thumbnail': item['snippet'].get('thumbnails', {}).get('medium', {}).get('url', ''),
                'position': item['snippet']['position'],
            } for item in response.get('items', [])]

        return self._paginate(
            lambda **kw: self.youtube.playlistItems().list(
                part='snippet,contentDetails', playlistId=playlist_id, **kw),
            max_results, handle_page,
        )

    def remove_from_playlist(self, playlist_item_id: str) -> bool:
        """حذف عنصر من قائمة تشغيل."""
        self.youtube.playlistItems().delete(id=playlist_item_id).execute()
        return True

    # ============ التعليقات ============
    def get_video_comments(self, video_id: str,
                           max_results: int = 20) -> List[Dict]:
        """جلب تعليقات فيديو (نصًا خامًا ``textOriginal`` لا HTML)."""
        try:
            response = self.youtube.commentThreads().list(
                part='snippet',
                videoId=video_id,
                maxResults=min(max_results, 100),
                order='time',
                textFormat='plainText',
            ).execute()
        except HttpError as exc:
            # التعليقات قد تكون معطّلة على الفيديو — نُسجّل ونُرجع قائمة فارغة.
            logger.info("تعذّر جلب التعليقات لـ %s: %s", video_id, exc)
            return []

        comments = []
        for item in response.get('items', []):
            top = item['snippet']['topLevelComment']['snippet']
            comments.append({
                'id': item['id'],
                'author': top['authorDisplayName'],
                'text': top.get('textOriginal') or top.get('textDisplay', ''),
                'likes': top['likeCount'],
                'publishedAt': top['publishedAt'],
                'replies': item['snippet']['totalReplyCount'],
            })
        return comments
