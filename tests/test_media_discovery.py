import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import app


class MediaDiscoveryTests(unittest.TestCase):
    def test_finds_iframe_urls(self):
        html = '<iframe src="//player.example.com/embed/abc"></iframe><iframe src="/local/embed"></iframe>'

        urls = app.find_iframe_urls(html, "https://example.com/watch/1")

        self.assertEqual(urls, [
            "https://player.example.com/embed/abc",
            "https://example.com/local/embed",
        ])

    def test_finds_mp4_source_urls(self):
        html = '<video><source src="/media/video.mp4?token=abc" type="video/mp4"></video>'

        urls = app.find_mp4_urls(html, "https://example.com/watch/1")

        self.assertEqual(urls, ["https://example.com/media/video.mp4?token=abc"])

    def test_discovers_mp4_inside_iframe(self):
        outer_html = '<iframe src="https://player.example.com/embed/abc"></iframe>'
        iframe_html = '<video><source src="https://cdn.example.com/video.mp4?token=abc"></video>'

        with patch("app.fetch_page", side_effect=[outer_html, iframe_html]) as fetch_page:
            m3u8_urls, mp4_urls = app.discover_media_sources("https://example.com/watch/1")

        self.assertEqual(m3u8_urls, [])
        self.assertEqual(mp4_urls, [
            ("https://cdn.example.com/video.mp4?token=abc", "https://player.example.com/embed/abc")
        ])
        self.assertEqual(fetch_page.call_args_list[1].kwargs["referer_url"], "https://example.com/watch/1")

    def test_download_direct_media_writes_streamed_response(self):
        response = MagicMock()
        response.status_code = 200
        response.headers = {"Content-Length": "8"}
        response.iter_content.return_value = [b"abcd", b"efgh"]
        response.__enter__.return_value = response
        response.__exit__.return_value = None

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "video.mp4"
            app.jobs["job1"] = {"downloaded_segments": 0, "total_segments": 0}

            with patch("app.requests.get", return_value=response) as get:
                app.download_direct_media(
                    "job1",
                    "https://cdn.example.com/video.mp4",
                    "https://player.example.com/embed/abc",
                    output_path,
                )

            self.assertEqual(output_path.read_bytes(), b"abcdefgh")
            self.assertEqual(app.jobs["job1"]["downloaded_segments"], 1)
            self.assertEqual(get.call_args.kwargs["headers"]["Referer"], "https://player.example.com/embed/abc")
            self.assertEqual(get.call_args.kwargs["headers"]["Range"], f"bytes=0-{app.DIRECT_MEDIA_RANGE_SIZE - 1}")

        app.jobs.pop("job1", None)

    def test_download_direct_media_uses_followup_range_requests(self):
        first = MagicMock()
        first.status_code = 206
        first.headers = {"Content-Range": "bytes 0-3/8", "Content-Length": "4"}
        first.iter_content.return_value = [b"abcd"]
        first.__enter__.return_value = first
        first.__exit__.return_value = None

        second = MagicMock()
        second.status_code = 206
        second.headers = {"Content-Range": "bytes 4-7/8", "Content-Length": "4"}
        second.iter_content.return_value = [b"efgh"]
        second.__enter__.return_value = second
        second.__exit__.return_value = None

        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "video.mp4"
            app.jobs["job2"] = {"downloaded_segments": 0, "total_segments": 0}

            with patch("app.requests.get", side_effect=[first, second]) as get:
                app.download_direct_media(
                    "job2",
                    "https://cdn.example.com/video.mp4",
                    "https://player.example.com/embed/abc",
                    output_path,
                    range_size=4,
                )

            self.assertEqual(output_path.read_bytes(), b"abcdefgh")
            self.assertEqual(app.jobs["job2"]["total_segments"], 2)
            self.assertEqual(app.jobs["job2"]["downloaded_segments"], 2)
            self.assertEqual(
                [call.kwargs["headers"]["Range"] for call in get.call_args_list],
                ["bytes=0-3", "bytes=4-7"],
            )

        app.jobs.pop("job2", None)


if __name__ == "__main__":
    unittest.main()
