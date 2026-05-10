import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import app


class MediaDiscoveryTests(unittest.TestCase):
    def test_default_download_directory_is_app_subfolder(self):
        self.assertEqual(app.DOWNLOAD_DIR, Path.home() / "Downloads" / "HLS-Downloader")

    def test_output_name_keeps_single_file_name_and_numbers_batches(self):
        self.assertEqual(app.output_name_for_job("abc123", 1, 1), "video_abc123.mp4")
        self.assertEqual(app.output_name_for_job("abc123", 1, 12), "video_abc123_001.mp4")
        self.assertEqual(app.output_name_for_job("abc123", 12, 12), "video_abc123_012.mp4")

    def test_preferred_media_sources_use_hls_before_mp4_fallbacks(self):
        hls_sources = [("https://cdn.example.com/video.m3u8", "https://example.com/watch/1")]
        mp4_sources = [("https://cdn.example.com/video.mp4", "https://example.com/watch/1")]

        self.assertEqual(app.preferred_media_sources(hls_sources, mp4_sources), [
            ("hls", "https://cdn.example.com/video.m3u8", "https://example.com/watch/1")
        ])
        self.assertEqual(app.preferred_media_sources([], mp4_sources), [
            ("mp4", "https://cdn.example.com/video.mp4", "https://example.com/watch/1")
        ])

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

    def test_process_download_downloads_all_discovered_mp4_sources(self):
        sources = [
            ("https://cdn.example.com/one.mp4", "https://example.com/watch/1"),
            ("https://cdn.example.com/two.mp4", "https://example.com/watch/1"),
        ]

        def fake_download(job_id, media_url, referer_url, output_path):
            output_path.write_bytes(media_url.rsplit("/", 1)[-1].encode("utf-8"))
            return True

        with tempfile.TemporaryDirectory() as tmp_dir:
            download_dir = Path(tmp_dir)
            app.jobs["batch1"] = {
                "status": "starting",
                "total_segments": 0,
                "downloaded_segments": 0,
                "error": None,
                "filename": None,
                "file_size": None,
                "files": [],
            }

            with (
                patch("app.DOWNLOAD_DIR", download_dir),
                patch("app.discover_media_sources", return_value=([], sources)),
                patch("app.download_direct_media", side_effect=fake_download) as download,
                patch("app.apply_source_metadata", return_value=True) as metadata,
            ):
                app.process_download("batch1", "https://example.com/watch/1")

            job = app.jobs["batch1"]
            self.assertEqual(job["status"], "done")
            self.assertEqual(job["total_files"], 2)
            self.assertEqual(job["downloaded_files"], 2)
            self.assertEqual(job["download_dir"], str(download_dir))
            self.assertEqual([file["filename"] for file in job["files"]], [
                "video_batch1_001.mp4",
                "video_batch1_002.mp4",
            ])
            self.assertEqual(download.call_count, 2)
            self.assertEqual(metadata.call_count, 2)
            self.assertEqual(
                [call.args[1] for call in metadata.call_args_list],
                ["https://example.com/watch/1", "https://example.com/watch/1"],
            )
            self.assertTrue((download_dir / "video_batch1_001.mp4").exists())
            self.assertTrue((download_dir / "video_batch1_002.mp4").exists())

        app.jobs.pop("batch1", None)

    def test_cleanup_file_removes_file_from_batch_job(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            download_dir = Path(tmp_dir)
            first_file = download_dir / "video_batch_001.mp4"
            second_file = download_dir / "video_batch_002.mp4"
            first_file.write_bytes(b"one")
            second_file.write_bytes(b"two")
            app.jobs["batch-cleanup"] = {
                "status": "done",
                "files": [
                    {"filename": first_file.name, "file_size": first_file.stat().st_size},
                    {"filename": second_file.name, "file_size": second_file.stat().st_size},
                ],
            }

            with patch("app.DOWNLOAD_DIR", download_dir):
                response = app.app.test_client().delete(f"/api/cleanup/{first_file.name}")

            self.assertEqual(response.status_code, 200)
            self.assertFalse(first_file.exists())
            self.assertEqual(app.jobs["batch-cleanup"]["files"], [
                {"filename": second_file.name, "file_size": second_file.stat().st_size}
            ])

        app.jobs.pop("batch-cleanup", None)


if __name__ == "__main__":
    unittest.main()
