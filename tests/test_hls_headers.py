import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import app


def response(text="", content=b""):
    resp = MagicMock()
    resp.text = text
    resp.content = content
    resp.raise_for_status.return_value = None
    return resp


class HlsHeaderTests(unittest.TestCase):
    def test_resolve_m3u8_sends_referer_to_playlist_requests(self):
        page_url = "https://example.com/watch/123"
        master_url = "https://cdn.example.com/master.m3u8"
        variant_url = "https://cdn.example.com/high/video.m3u8"
        master = "\n".join([
            "#EXTM3U",
            "#EXT-X-STREAM-INF:BANDWIDTH=1000",
            "high/video.m3u8",
        ])
        variant = "\n".join([
            "#EXTM3U",
            "#EXTINF:1.0,",
            "segment0.ts",
        ])

        with patch("app.requests.get", side_effect=[response(master), response(variant)]) as get:
            content, segments = app.resolve_m3u8(master_url, referer_url=page_url)

        self.assertEqual(content, variant)
        self.assertEqual(segments, ["https://cdn.example.com/high/segment0.ts"])
        self.assertEqual(get.call_count, 2)
        for call in get.call_args_list:
            self.assertEqual(call.kwargs["headers"]["Referer"], page_url)

    def test_download_segment_sends_referer_when_provided(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "segment.ts"

            with patch("app.requests.get", return_value=response(content=b"data")) as get:
                ok = app.download_segment((
                    "https://cdn.example.com/segment.ts",
                    str(output),
                    "job123",
                    "https://example.com/watch/123",
                ))

            self.assertTrue(ok)
            self.assertEqual(output.read_bytes(), b"data")
            self.assertEqual(
                get.call_args.kwargs["headers"]["Referer"],
                "https://example.com/watch/123",
            )


if __name__ == "__main__":
    unittest.main()
