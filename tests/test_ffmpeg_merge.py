import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

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


if __name__ == "__main__":
    unittest.main()
