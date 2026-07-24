#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""اختبارات وحدة YouTubeAPI باستخدام محاكاة googleapiclient (بلا شبكة)."""

import os
import sys
import tempfile
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from yt_api import YouTubeAPI, UploadCancelledError  # noqa: E402


def _make_api():
    api = YouTubeAPI()
    api.youtube = MagicMock()
    return api


class TestChannelStatistics:
    def test_neutral_keys_and_ints(self):
        api = _make_api()
        api.youtube.channels.return_value.list.return_value.execute.return_value = {
            'items': [{
                'id': 'CH123',
                'statistics': {'subscriberCount': '1500', 'viewCount': '20000', 'videoCount': '42'},
                'snippet': {'title': 'قناتي', 'description': 'وصف',
                            'publishedAt': '2020-01-01T00:00:00Z',
                            'thumbnails': {'high': {'url': 'http://x/y.jpg'}}},
            }]
        }
        stats = api.get_channel_statistics()
        assert stats['channel_id'] == 'CH123'
        assert stats['subscribers'] == 1500
        assert stats['views'] == 20000
        assert stats['video_count'] == 42
        assert stats['title'] == 'قناتي'
        # لا مفاتيح عربية في طبقة البيانات
        assert 'المشتركون' not in stats

    def test_no_channel_returns_none(self):
        api = _make_api()
        api.youtube.channels.return_value.list.return_value.execute.return_value = {'items': []}
        assert api.get_channel_statistics() is None


class TestGetVideos:
    def test_no_channel_returns_empty(self):
        api = _make_api()
        api.youtube.channels.return_value.list.return_value.execute.return_value = {'items': []}
        assert api.get_videos() == []


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
