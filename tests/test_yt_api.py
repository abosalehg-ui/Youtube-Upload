#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""اختبارات وحدة YouTubeAPI باستخدام محاكاة googleapiclient (بلا شبكة)."""

import os
import sys
import tempfile
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yt_api  # noqa: E402
from googleapiclient.errors import HttpError  # noqa: E402
from yt_api import YouTubeAPI, UploadCancelledError, privacy_warning, validate_thumbnail  # noqa: E402


def _make_api():
    api = YouTubeAPI()
    api.youtube = MagicMock()
    return api


def _http_error(status, content=b'{}'):
    resp = MagicMock()
    resp.status = status
    resp.reason = 'err'
    return HttpError(resp, content)


class TestChannelInfo:
    def test_neutral_keys_and_ints(self):
        stats = YouTubeAPI._map_channel_info({
            'id': 'CH123',
            'statistics': {'subscriberCount': '1500', 'viewCount': '20000', 'videoCount': '42'},
            'snippet': {'title': 'قناتي', 'description': 'وصف',
                        'publishedAt': '2020-01-01T00:00:00Z',
                        'thumbnails': {'high': {'url': 'http://x/y.jpg'}}},
        })
        assert stats['channel_id'] == 'CH123'
        assert stats['subscribers'] == 1500
        assert stats['views'] == 20000
        assert stats['video_count'] == 42
        assert stats['title'] == 'قناتي'
        # لا مفاتيح عربية في طبقة البيانات
        assert 'المشتركون' not in stats


class TestGetVideos:
    def test_no_channel_returns_empty(self):
        api = _make_api()
        api.youtube.channels.return_value.list.return_value.execute.return_value = {'items': []}
        assert api.get_videos() == []

    def test_provided_uploads_id_skips_channel_call(self):
        """تمرير uploads_playlist_id يتجنّب نداء channels().list الإضافي."""
        api = _make_api()
        api.youtube.playlistItems.return_value.list.return_value.execute.return_value = {
            'items': [], 'nextPageToken': None,
        }
        api.get_videos(max_results=10, uploads_playlist_id='UU123')
        api.youtube.channels.assert_not_called()


class TestDashboardData:
    def test_single_channel_call_returns_info_and_videos(self):
        api = _make_api()
        api.youtube.channels.return_value.list.return_value.execute.return_value = {
            'items': [{
                'id': 'CH1',
                'statistics': {'subscriberCount': '10', 'viewCount': '200', 'videoCount': '3'},
                'snippet': {'title': 'قناة', 'description': 'د',
                            'publishedAt': '2020-01-01T00:00:00Z', 'thumbnails': {}},
                'contentDetails': {'relatedPlaylists': {'uploads': 'UU1'}},
            }]
        }
        api.youtube.playlistItems.return_value.list.return_value.execute.return_value = {
            'items': [], 'nextPageToken': None,
        }
        data = api.get_dashboard_data(max_videos=5)
        assert data['info']['channel_id'] == 'CH1'
        assert data['info']['subscribers'] == 10
        assert data['videos'] == []
        # القناة تُطلب مرة واحدة فقط (لا تكرار في get_videos).
        assert api.youtube.channels.return_value.list.call_count == 1

    def test_no_channel_returns_none(self):
        api = _make_api()
        api.youtube.channels.return_value.list.return_value.execute.return_value = {'items': []}
        assert api.get_dashboard_data() is None


class TestUpdateVideo:
    def test_merges_existing_fields(self):
        api = _make_api()
        api.youtube.videos.return_value.list.return_value.execute.return_value = {
            'items': [{
                'snippet': {'title': 'قديم', 'description': 'وصف قديم',
                            'tags': ['t1'], 'categoryId': '24'},
                'status': {'privacyStatus': 'public'},
            }]
        }
        api.youtube.videos.return_value.update.return_value.execute.return_value = {'id': 'V1'}

        api.update_video('V1', title='جديد')  # نُغيّر العنوان فقط

        body = api.youtube.videos.return_value.update.call_args.kwargs['body']
        assert body['snippet']['title'] == 'جديد'
        assert body['snippet']['description'] == 'وصف قديم'   # محفوظ
        assert body['snippet']['tags'] == ['t1']              # محفوظ
        assert body['status']['privacyStatus'] == 'public'    # محفوظ

    def test_keeps_publish_at_and_other_status_fields(self):
        """videos.update يحذف أي خاصية لا تُرسل — يجب نسخ status كاملًا."""
        api = _make_api()
        api.youtube.videos.return_value.list.return_value.execute.return_value = {
            'items': [{
                'snippet': {'title': 'قديم', 'categoryId': '24', 'defaultLanguage': 'ar',
                            'publishedAt': '2020-01-01T00:00:00Z', 'channelId': 'CH'},
                'status': {'privacyStatus': 'private', 'publishAt': '2030-01-01T10:00:00Z',
                           'embeddable': False, 'license': 'creativeCommon',
                           'selfDeclaredMadeForKids': True, 'uploadStatus': 'processed'},
            }]
        }
        api.update_video('V1', description='وصف جديد', privacy='private')

        body = api.youtube.videos.return_value.update.call_args.kwargs['body']
        assert body['status']['publishAt'] == '2030-01-01T10:00:00Z'
        assert body['status']['embeddable'] is False
        assert body['status']['license'] == 'creativeCommon'
        assert body['status']['selfDeclaredMadeForKids'] is True
        assert 'uploadStatus' not in body['status']          # حقل للقراءة فقط
        assert body['snippet']['defaultLanguage'] == 'ar'
        assert 'publishedAt' not in body['snippet']
        assert body['snippet']['description'] == 'وصف جديد'

    def test_making_public_drops_schedule(self):
        api = _make_api()
        api.youtube.videos.return_value.list.return_value.execute.return_value = {
            'items': [{'snippet': {'title': 't'},
                       'status': {'privacyStatus': 'private', 'publishAt': '2030-01-01T10:00:00Z'}}]
        }
        api.update_video('V1', privacy='public')
        body = api.youtube.videos.return_value.update.call_args.kwargs['body']
        assert body['status']['privacyStatus'] == 'public'
        assert 'publishAt' not in body['status']

    def test_missing_video_raises(self):
        api = _make_api()
        api.youtube.videos.return_value.list.return_value.execute.return_value = {'items': []}
        with pytest.raises(ValueError):
            api.update_video('nope', title='x')


class TestUploadCancel:
    def test_cancel_before_first_chunk(self):
        api = _make_api()
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as fh:
            fh.write(b'0' * 1024)
            path = fh.name
        try:
            with pytest.raises(UploadCancelledError):
                api.upload_video(
                    file_path=path, title='t', description='', tags=[],
                    category_id='24', privacy='private',
                    cancel_callback=lambda: True,   # مُلغى فورًا
                )
        finally:
            os.remove(path)

    def test_missing_file_raises(self):
        api = _make_api()
        with pytest.raises(FileNotFoundError):
            api.upload_video(file_path='/no/such/file.mp4', title='t',
                             description='', tags=[], category_id='24', privacy='private')


def _video_file(tmp_path, name='v.mp4'):
    path = tmp_path / name
    path.write_bytes(b'0' * 1024)
    return str(path)


class TestUploadRetries:
    def _api_with_chunks(self, chunks):
        api = _make_api()
        request = MagicMock()
        request.next_chunk.side_effect = chunks
        api.youtube.videos.return_value.insert.return_value = request
        return api, request

    def test_retries_transient_5xx_then_succeeds(self, tmp_path, monkeypatch):
        monkeypatch.setattr(yt_api.time, 'sleep', lambda s: None)
        done = (None, {'id': 'V9', 'status': {'privacyStatus': 'public'}})
        api, request = self._api_with_chunks([_http_error(503), _http_error(503), done])
        result = api.upload_video(_video_file(tmp_path), 't', '', [], '24', 'public')
        assert result.video_id == 'V9'
        assert result.warning == ''
        assert request.next_chunk.call_count == 3

    def test_retries_network_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(yt_api.time, 'sleep', lambda s: None)
        done = (None, {'id': 'V1', 'status': {'privacyStatus': 'private'}})
        api, _ = self._api_with_chunks([ConnectionResetError(), done])
        assert api.upload_video(_video_file(tmp_path), 't', '', [], '24', 'private').video_id == 'V1'

    def test_non_retriable_error_raises_immediately(self, tmp_path, monkeypatch):
        monkeypatch.setattr(yt_api.time, 'sleep', lambda s: None)
        api, request = self._api_with_chunks([_http_error(400)])
        with pytest.raises(HttpError):
            api.upload_video(_video_file(tmp_path), 't', '', [], '24', 'public')
        assert request.next_chunk.call_count == 1

    def test_gives_up_after_max_retries(self, tmp_path, monkeypatch):
        monkeypatch.setattr(yt_api.time, 'sleep', lambda s: None)
        api, request = self._api_with_chunks([_http_error(500)] * (yt_api.MAX_UPLOAD_RETRIES + 1))
        with pytest.raises(HttpError):
            api.upload_video(_video_file(tmp_path), 't', '', [], '24', 'public')
        assert request.next_chunk.call_count == yt_api.MAX_UPLOAD_RETRIES + 1

    def test_made_for_kids_and_schedule_in_body(self, tmp_path):
        done = (None, {'id': 'V1', 'status': {'privacyStatus': 'private'}})
        api, _ = self._api_with_chunks([done])
        api.upload_video(_video_file(tmp_path), 't', '', [], '24', 'public',
                         scheduled_time='2030-01-01T00:00:00.000Z', made_for_kids=True)
        body = api.youtube.videos.return_value.insert.call_args.kwargs['body']
        assert body['status']['selfDeclaredMadeForKids'] is True
        assert body['status']['privacyStatus'] == 'private'
        assert body['status']['publishAt'] == '2030-01-01T00:00:00.000Z'

    def test_warns_when_youtube_locks_upload_private(self, tmp_path):
        done = (None, {'id': 'V1', 'status': {'privacyStatus': 'private'}})
        api, _ = self._api_with_chunks([done])
        result = api.upload_video(_video_file(tmp_path), 't', '', [], '24', 'public')
        assert 'unverified' in result.warning


class TestPrivacyWarning:
    def test_no_warning_when_matching_or_scheduled(self):
        assert privacy_warning('public', 'public', False) == ''
        assert privacy_warning('private', 'private', False) == ''
        assert privacy_warning('public', 'private', True) == ''

    def test_warning_when_locked(self):
        assert privacy_warning('unlisted', 'private', False)


class TestThumbnail:
    def test_rejects_unsupported_type(self, tmp_path):
        path = tmp_path / 'a.webp'
        path.write_bytes(b'x')
        with pytest.raises(ValueError):
            validate_thumbnail(str(path))

    def test_rejects_too_large(self, tmp_path):
        path = tmp_path / 'a.png'
        path.write_bytes(b'0' * (2 * 1024 * 1024 + 1))
        with pytest.raises(ValueError):
            validate_thumbnail(str(path))

    def test_png_gets_png_mimetype(self, tmp_path):
        path = tmp_path / 'a.png'
        path.write_bytes(b'0' * 10)
        assert validate_thumbnail(str(path)) == 'image/png'

    def test_invalid_thumbnail_fails_before_upload(self, tmp_path):
        api = _make_api()
        bad = tmp_path / 'a.gif'
        bad.write_bytes(b'x')
        with pytest.raises(ValueError):
            api.upload_video(_video_file(tmp_path), 't', '', [], '24', 'public',
                             thumbnail_path=str(bad))
        api.youtube.videos.return_value.insert.assert_not_called()


class TestComments:
    def test_uses_plain_text(self):
        api = _make_api()
        api.youtube.commentThreads.return_value.list.return_value.execute.return_value = {
            'items': [{'id': 'C1', 'snippet': {'totalReplyCount': 0, 'topLevelComment': {'snippet': {
                'authorDisplayName': 'a', 'textDisplay': 'it&#39;s<br>ok',
                'textOriginal': "it's\nok", 'likeCount': 1, 'publishedAt': 'x'}}}}]
        }
        comments = api.get_video_comments('V1')
        assert comments[0]['text'] == "it's\nok"


class TestAuthenticate:
    def test_refresh_error_falls_back_to_login(self, tmp_path, monkeypatch):
        from google.auth.exceptions import RefreshError
        token = tmp_path / 'token.json'
        token.write_text('{}')
        monkeypatch.setattr(yt_api, 'TOKEN_FILE', str(token))
        monkeypatch.setattr(yt_api, 'LEGACY_TOKEN_FILE', str(tmp_path / 'token.pickle'))
        monkeypatch.setattr(yt_api, 'build', lambda *a, **k: MagicMock())

        stale = MagicMock(valid=False, expired=True, refresh_token='r')
        stale.refresh.side_effect = RefreshError('invalid_grant')
        fresh = MagicMock(valid=True)
        fresh.to_json.return_value = '{"new": true}'

        api = YouTubeAPI()
        monkeypatch.setattr(api, '_load_saved_credentials', lambda: stale)
        monkeypatch.setattr(api, '_run_login_flow', lambda: fresh)
        assert api.authenticate() is True
        assert api.credentials is fresh
        assert token.read_text() == '{"new": true}'

    @pytest.mark.skipif(os.name == 'nt', reason='صلاحيات POSIX')
    def test_token_written_with_0600(self, tmp_path, monkeypatch):
        token = tmp_path / 'token.json'
        monkeypatch.setattr(yt_api, 'TOKEN_FILE', str(token))
        creds = MagicMock()
        creds.to_json.return_value = '{}'
        YouTubeAPI._save_credentials(creds)
        assert (token.stat().st_mode & 0o777) == 0o600


class TestAuthState:
    def test_is_authenticated(self):
        api = YouTubeAPI()
        assert api.is_authenticated() is False
        api.youtube = MagicMock()
        assert api.is_authenticated() is True

    def test_logout_removes_token(self, tmp_path, monkeypatch):
        import yt_api
        token = tmp_path / "token.json"
        token.write_text("{}")
        monkeypatch.setattr(yt_api, "TOKEN_FILE", str(token))
        api = _make_api()
        api.logout()
        assert not token.exists()
        assert api.is_authenticated() is False
