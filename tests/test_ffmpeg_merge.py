import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import app


class FfmpegMergeTests(unittest.TestCase):
    def test_ffmpeg_output_is_invalid_when_file_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "video.mp4"
            output.write_bytes(b"")
            result = MagicMock(returncode=0)

            self.assertFalse(app.has_valid_output(result, output))

    def test_ffmpeg_output_is_valid_when_command_succeeds_and_file_has_data(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "video.mp4"
            output.write_bytes(b"data")
            result = MagicMock(returncode=0)

            self.assertTrue(app.has_valid_output(result, output))

    def test_ffmpeg_output_is_invalid_when_command_fails(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "video.mp4"
            output.write_bytes(b"data")
            result = MagicMock(returncode=1)

            self.assertFalse(app.has_valid_output(result, output))

    def test_source_metadata_args_include_page_url(self):
        args = app.source_metadata_args("https://example.com/watch/1")

        self.assertEqual(args, [
            "-metadata",
            "comment=Source URL: https://example.com/watch/1",
            "-metadata",
            "description=Source URL: https://example.com/watch/1",
        ])

    def test_apply_source_metadata_remuxes_file_with_page_url(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "video.mp4"
            output.write_bytes(b"original")

            def fake_run(cmd, **kwargs):
                Path(cmd[-2]).write_bytes(b"with metadata")
                return MagicMock(returncode=0)

            with patch("app.subprocess.run", side_effect=fake_run) as run:
                written = app.apply_source_metadata(output, "https://example.com/watch/1")

            self.assertTrue(written)
            self.assertEqual(output.read_bytes(), b"with metadata")
            cmd = run.call_args.args[0]
            self.assertIn("comment=Source URL: https://example.com/watch/1", cmd)
            self.assertIn("description=Source URL: https://example.com/watch/1", cmd)

    def test_hls_merge_includes_page_url_metadata(self):
        playlist = "#EXTM3U\n#EXTINF:1,\nsegment.ts\n"

        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "video.mp4"
            app.jobs["hls-meta"] = {"downloaded_segments": 0, "total_segments": 0}

            def fake_run(cmd, **kwargs):
                Path(cmd[-2]).write_bytes(b"merged")
                return MagicMock(returncode=0)

            with (
                patch("app.resolve_m3u8", return_value=(playlist, ["https://cdn.example.com/segment.ts"], "https://cdn.example.com/video.m3u8")),
                patch("app.download_segment", return_value=True),
                patch("app.subprocess.run", side_effect=fake_run) as run,
            ):
                app.download_hls_source(
                    "hls-meta",
                    "https://cdn.example.com/video.m3u8",
                    "https://example.com/embed/1",
                    output,
                    "1/1",
                    "https://example.com/watch/1",
                )

            cmd = run.call_args.args[0]
            self.assertIn("comment=Source URL: https://example.com/watch/1", cmd)
            self.assertIn("description=Source URL: https://example.com/watch/1", cmd)

        app.jobs.pop("hls-meta", None)


if __name__ == "__main__":
    unittest.main()
