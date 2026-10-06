#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""اختبارات خيوط الرفع — تستدعي run() مباشرة في نفس الخيط (بلا حلقة أحداث)."""

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workers import BatchUploadThread, UploadJob, UploadThread  # noqa: E402
from yt_api import UploadCancelledError, UploadResult  # noqa: E402


def _collect(signal):
    received = []
    signal.connect(lambda *args: received.append(args))
    return received


class TestBatchUploadThread:
    def test_copies_queue(self):
        queue = [UploadJob('a.mp4', 'a')]
        thread = BatchUploadThread(MagicMock(), queue)
        queue.clear()  # تعديل الواجهة للقائمة لا يؤثر على الخيط
        assert len(thread.upload_queue) == 1

    def test_reports_each_item_and_summary(self):
        yt = MagicMock()
        yt.upload_video.side_effect = [UploadResult('V1'), RuntimeError('boom')]
        thread = BatchUploadThread(yt, [UploadJob('a.mp4', 'a'), UploadJob('b.mp4', 'b')])
        items = _collect(thread.item_done)
        finished = _collect(thread.finished)
        thread.run()

        assert [i for i, _ in items] == [0, 1]
        assert items[0][1]['success'] is True
        assert items[1][1]['success'] is False and items[1][1]['error'] == 'boom'
        ok, message, results = finished[0]
        assert ok is True and "1 من 2" in message and len(results) == 2

    def test_cancel_stops_remaining(self):
        yt = MagicMock()
        thread = BatchUploadThread(yt, [UploadJob('a.mp4', 'a'), UploadJob('b.mp4', 'b')])

        def upload(**kwargs):
            thread.cancel()
            raise UploadCancelledError()

        yt.upload_video.side_effect = upload
        finished = _collect(thread.finished)
        thread.run()
        assert yt.upload_video.call_count == 1
        assert finished[0][0] is False

    def test_passes_made_for_kids(self):
        yt = MagicMock()
        yt.upload_video.return_value = UploadResult('V1')
        BatchUploadThread(yt, [UploadJob('a.mp4', 'a', made_for_kids=True)]).run()
        assert yt.upload_video.call_args.kwargs['made_for_kids'] is True


class TestUploadThread:
    def test_success_carries_warning(self):
        yt = MagicMock()
        yt.upload_video.return_value = UploadResult('V1', 'private', 'تحذير')
        thread = UploadThread(yt, UploadJob('a.mp4', 'a', privacy='public'))
        finished = _collect(thread.finished)
        thread.run()
        assert finished[0] == (True, finished[0][1], 'V1', 'تحذير', False)

    def test_cancel_is_not_an_error(self):
        yt = MagicMock()
        yt.upload_video.side_effect = UploadCancelledError()
        thread = UploadThread(yt, UploadJob('a.mp4', 'a'))
        finished = _collect(thread.finished)
        thread.run()
        success, _, _, _, cancelled = finished[0]
        assert success is False and cancelled is True
