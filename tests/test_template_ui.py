import unittest
from pathlib import Path


class TemplateUITests(unittest.TestCase):
    def test_new_download_button_clears_url_field(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn("resetUI({ clearUrl: true })", html)
        self.assertIn("document.getElementById('urlInput').value = ''", html)

    def test_result_ui_lists_saved_files_and_reveals_download_location(self):
        html = Path("templates/index.html").read_text(encoding="utf-8")

        self.assertIn('id="resultList"', html)
        self.assertIn("const files = job.files", html)
        self.assertIn("/api/reveal/", html)


if __name__ == "__main__":
    unittest.main()
