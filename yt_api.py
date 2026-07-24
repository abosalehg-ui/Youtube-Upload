#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
وحدة التعامل مع YouTube Data API v3.

ملاحظات أمنية:
- تُخزَّن بيانات اعتماد المستخدم في ملف JSON (لا pickle) لتجنّب مخاطر
  تفكيك pickle غير الآمن (إمكانية تنفيذ كود عند استبدال الملف).
- لا يُخزَّن أي سرّ داخل الكود؛ تُقرأ الأسرار من client_secret.json محليًا.
"""

import os
import socket
import time
from typing import Callable, Dict, List, Optional

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from utils import get_logger

logger = get_logger("yt_api")

SCOPES = [
    'https://www.googleapis.com/auth/youtube',
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.force-ssl',
]

TOKEN_FILE = "token.json"
# ملف التوكن القديم (pickle) — يُهاجَر تلقائيًا ثم يُحذف.
LEGACY_TOKEN_FILE = "token.pickle"

# أكواد HTTP القابلة لإعادة المحاولة (أخطاء خادم/شبكة عابرة).
RETRIABLE_STATUS_CODES = {500, 502, 503, 504}
MAX_UPLOAD_RETRIES = 5


class UploadCancelledError(Exception):
    """يُرفع عند إلغاء المستخدم لعملية الرفع أثناء تنفيذها."""


class YouTubeAPI:
    """فئة إدارة YouTube API."""

    def __init__(self, client_secret_path: str = "client_secret.json") -> None:
        self.client_secret_path = client_secret_path
        self.credentials: Optional[Credentials] = None
        self.youtube = None

    # ============ المصادقة ============
    def _load_saved_credentials(self) -> Optional[Credentials]:
        """تحميل بيانات الاعتماد المحفوظة، مع ترحيل ملف pickle القديم إن وُجد."""
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
                os.remove(LEGACY_TOKEN_FILE)
                logger.info("تم ترحيل التوكن القديم وحذفه")
                return creds
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("فشل ترحيل التوكن القديم: %s", exc)
        return None

    @staticmethod
    def _save_credentials(creds: Credentials) -> None:
        """حفظ بيانات الاعتماد كـ JSON بصلاحيات مقيّدة قدر الإمكان."""
        with open(TOKEN_FILE, "w", encoding="utf-8") as fh:
            fh.write(creds.to_json())
        try:  # تقييد الصلاحيات على أنظمة POSIX (قراءة/كتابة للمالك فقط)
            os.chmod(TOKEN_FILE, 0o600)
        except OSError:
            pass

    def authenticate(self) -> bool:
        """المصادقة مع Google OAuth2 (تحديث التوكن أو تدفّق تسجيل دخول جديد)."""
        creds = self._load_saved_credentials()

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("تحديث التوكن منتهي الصلاحية")
                creds.refresh(Request())
            else:
                if not os.path.exists(self.client_secret_path):
                    raise FileNotFoundError(
                        f"ملف الاعتماد غير موجود: {self.client_secret_path}"
                    )
                logger.info("بدء تدفّق تسجيل الدخول عبر المتصفح")
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.client_secret_path, SCOPES
                )
                creds = flow.run_local_server(port=0)
            self._save_credentials(creds)

        self.credentials = creds
        self.youtube = build('youtube', 'v3', credentials=creds)
        logger.info("تمت المصادقة وبناء عميل YouTube")
        return True

    def is_authenticated(self) -> bool:
        return self.youtube is not None

    def logout(self) -> None:
        """تسجيل الخروج وحذف بيانات الاعتماد المحفوظة."""
        for path in (TOKEN_FILE, LEGACY_TOKEN_FILE):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError as exc:
                    logger.warning("تعذّر حذف %s: %s", path, exc)
        self.credentials = None
        self.youtube = None
        logger.info("تم تسجيل الخروج")

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

    def get_channel_statistics(self) -> Optional[Dict]:
        """جلب إحصائيات القناة بمفاتيح محايدة (غير مرتبطة بلغة الواجهة)."""
        info = self.get_channel_info()
        if not info:
            return None
        return self._map_channel_info(info)

    def get_dashboard_data(self, max_videos: int = 10) -> Optional[Dict]:
        """جلب بيانات لوحة التحكم (إحصائيات + أحدث فيديوهات) بنداء قناة واحد.

        يتجنّب استدعاء ``channels().list`` مرتين (مرة للإحصائيات ومرة داخل
        ``get_videos``) بجلب معلومات القناة مرة واحدة وإعادة استخدامها.
        """
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

        videos: List[Dict] = []
        next_page = None

        while True:
            response = self.youtube.playlistItems().list(
                part='snippet,contentDetails',
                playlistId=uploads_playlist_id,
                maxResults=min(max(max_results - len(videos), 1), 50),
                pageToken=next_page
            ).execute()

            video_ids = [item['contentDetails']['videoId']
                         for item in response.get('items', [])]

            if video_ids:
                details = self.youtube.videos().list(
                    part='snippet,statistics,status,contentDetails',
                    id=','.join(video_ids)
                ).execute()

                for item in details.get('items', []):
                    snippet = item['snippet']
                    videos.append({
                        'id': item['id'],
                        'title': snippet['title'],
                        'description': snippet.get('description', ''),
                        'publishedAt': snippet['publishedAt'],
                        'thumbnail': snippet['thumbnails'].get('medium', {}).get('url', ''),
                        'views': int(item['statistics'].get('viewCount', 0)),
                        'likes': int(item['statistics'].get('likeCount', 0)),
                        'comments': int(item['statistics'].get('commentCount', 0)),
                        'duration': item['contentDetails'].get('duration', ''),
                        'privacy': item['status']['privacyStatus'],
                        'tags': snippet.get('tags', []),
                        'categoryId': snippet.get('categoryId', ''),
                    })

            next_page = response.get('nextPageToken')
            if not next_page or len(videos) >= max_results:
                break

        return videos

    def upload_video(self, file_path: str, title: str, description: str,
                     tags: Optional[List[str]], category_id, privacy: str,
                     scheduled_time: Optional[str] = None,
                     thumbnail_path: Optional[str] = None,
                     progress_callback: Optional[Callable[[int], None]] = None,
                     status_callback: Optional[Callable[[str], None]] = None,
                     cancel_callback: Optional[Callable[[], bool]] = None) -> str:
        """رفع فيديو إلى يوتيوب مع إعادة محاولة للأخطاء العابرة ودعم الإلغاء."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"ملف الفيديو غير موجود: {file_path}")

        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags or [],
                'categoryId': str(category_id),
            },
            'status': {
                'privacyStatus': privacy,
                'selfDeclaredMadeForKids': False,
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
            except HttpError as exc:
                if exc.resp.status in RETRIABLE_STATUS_CODES and retries < MAX_UPLOAD_RETRIES:
                    retries += 1
                    sleep_s = min(2 ** retries, 30)
                    logger.warning("خطأ عابر %s — إعادة المحاولة %d بعد %ss",
                                   exc.resp.status, retries, sleep_s)
                    time.sleep(sleep_s)
                    continue
                raise
            except (socket.error, ConnectionError, OSError) as exc:
                if retries < MAX_UPLOAD_RETRIES:
                    retries += 1
                    sleep_s = min(2 ** retries, 30)
                    logger.warning("خطأ شبكة (%s) — إعادة المحاولة %d بعد %ss",
                                   exc, retries, sleep_s)
                    time.sleep(sleep_s)
                    continue
                raise

        video_id = response['id']
        logger.info("تم رفع الفيديو: %s", video_id)

        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                self.youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(thumbnail_path, mimetype='image/jpeg')
                ).execute()
                logger.info("تم رفع الصورة المصغّرة للفيديو %s", video_id)
            except HttpError as exc:
                # لا نُفشل الرفع كله بسبب المصغّرة، لكن لا نبتلع الخطأ بصمت.
                logger.warning("تعذّر رفع الصورة المصغّرة (قد تتطلب قناة موثّقة): %s", exc)
                if status_callback:
                    status_callback("تم الرفع، لكن تعذّر ضبط الصورة المصغّرة")

        return video_id

    def delete_video(self, video_id: str) -> bool:
        """حذف فيديو."""
        self.youtube.videos().delete(id=video_id).execute()
        logger.info("تم حذف الفيديو: %s", video_id)
        return True

    def update_video(self, video_id: str, title: Optional[str] = None,
                     description: Optional[str] = None,
                     tags: Optional[List[str]] = None, category_id=None,
                     privacy: Optional[str] = None) -> Dict:
        """تحديث بيانات فيديو (يدمج القيم الجديدة مع الحالية)."""
        current = self.youtube.videos().list(
            part='snippet,status',
            id=video_id
        ).execute()

        if not current.get('items'):
            raise ValueError("الفيديو غير موجود")

        item = current['items'][0]
        snippet = item['snippet']
        status = item['status']

        body = {
            'id': video_id,
            'snippet': {
                'title': title or snippet['title'],
                'description': description if description is not None else snippet.get('description', ''),
                'tags': tags if tags is not None else snippet.get('tags', []),
                'categoryId': str(category_id) if category_id else snippet.get('categoryId', '22'),
            },
            'status': {
                'privacyStatus': privacy or status['privacyStatus'],
            }
        }

        result = self.youtube.videos().update(
            part='snippet,status',
            body=body
        ).execute()
        logger.info("تم تحديث الفيديو: %s", video_id)
        return result

    # ============ قوائم التشغيل ============
    def get_playlists(self, max_results: int = 50) -> List[Dict]:
        """جلب قوائم التشغيل."""
        playlists: List[Dict] = []
        next_page = None

        while True:
            response = self.youtube.playlists().list(
                part='snippet,contentDetails,status',
                mine=True,
                maxResults=min(max(max_results - len(playlists), 1), 50),
                pageToken=next_page
            ).execute()

            for item in response.get('items', []):
                playlists.append({
                    'id': item['id'],
                    'title': item['snippet']['title'],
                    'description': item['snippet'].get('description', ''),
                    'videoCount': item['contentDetails']['itemCount'],
                    'privacy': item['status']['privacyStatus'],
                    'thumbnail': item['snippet']['thumbnails'].get('medium', {}).get('url', ''),
                    'publishedAt': item['snippet']['publishedAt'],
                })

            next_page = response.get('nextPageToken')
            if not next_page or len(playlists) >= max_results:
                break

        return playlists

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
        items: List[Dict] = []
        next_page = None

        while True:
            response = self.youtube.playlistItems().list(
                part='snippet,contentDetails',
                playlistId=playlist_id,
                maxResults=min(max(max_results - len(items), 1), 50),
                pageToken=next_page
            ).execute()

            for item in response.get('items', []):
                items.append({
                    'id': item['id'],
                    'videoId': item['contentDetails']['videoId'],
                    'title': item['snippet']['title'],
                    'thumbnail': item['snippet']['thumbnails'].get('medium', {}).get('url', ''),
                    'position': item['snippet']['position'],
                })

            next_page = response.get('nextPageToken')
            if not next_page or len(items) >= max_results:
                break

        return items

    def remove_from_playlist(self, playlist_item_id: str) -> bool:
        """حذف عنصر من قائمة تشغيل."""
        self.youtube.playlistItems().delete(id=playlist_item_id).execute()
        return True

    # ============ التعليقات ============
    def get_video_comments(self, video_id: str,
                           max_results: int = 20) -> List[Dict]:
        """جلب تعليقات فيديو."""
        try:
            response = self.youtube.commentThreads().list(
                part='snippet',
                videoId=video_id,
                maxResults=max_results,
                order='time'
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
                'text': top['textDisplay'],
                'likes': top['likeCount'],
                'publishedAt': top['publishedAt'],
                'replies': item['snippet']['totalReplyCount'],
            })
        return comments

    # ============ البحث ============
    def search_my_videos(self, query: str, max_results: int = 25) -> List[Dict]:
        """البحث في فيديوهات القناة."""
        channel = self.get_channel_info()
        if not channel:
            return []

        response = self.youtube.search().list(
            part='snippet',
            channelId=channel['id'],
            q=query,
            type='video',
            maxResults=max_results,
            order='date'
        ).execute()

        results = []
        for item in response.get('items', []):
            results.append({
                'id': item['id']['videoId'],
                'title': item['snippet']['title'],
                'description': item['snippet'].get('description', ''),
                'publishedAt': item['snippet']['publishedAt'],
                'thumbnail': item['snippet']['thumbnails'].get('medium', {}).get('url', ''),
            })
        return results
