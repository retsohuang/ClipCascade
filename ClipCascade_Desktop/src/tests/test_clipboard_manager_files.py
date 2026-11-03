"""Unit tests for the macOS received-files branch of ClipboardManager.paste.

Run from ClipCascade_Desktop/src/:
    python3 -m unittest tests.test_clipboard_manager_files -v
"""
import io
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

from clipboard.clipboard_manager import ClipboardManager

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def make_image_bytes(fmt):
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), (200, 30, 30)).save(buffer, format=fmt)
    return buffer.getvalue()


class FakeClipboardMonitor:
    def __init__(self):
        self.writes = []

    def enable_block_files_once(self):
        pass

    def write_file_urls_to_pasteboard(self, file_paths, png_data_by_path=None):
        self.writes.append((list(file_paths), dict(png_data_by_path or {})))


class TestReceivedImageFiles(unittest.TestCase):
    def setUp(self):
        self.download_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.download_dir.cleanup)
        config = MagicMock()
        config.data = {"default_file_download_location": self.download_dir.name}
        self.manager = ClipboardManager(config)
        self.fake = FakeClipboardMonitor()
        patcher = patch("clipboard.clipboard_manager.clipboard_monitor", self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def receive(self, files):
        self.manager.paste(
            {name: io.BytesIO(data) for name, data in files.items()}, "files"
        )
        self.assertEqual(len(self.fake.writes), 1)
        paths, png_by_path = self.fake.writes[0]
        return paths, png_by_path

    def path_of(self, name):
        return os.path.join(self.download_dir.name, name)

    def test_png_file_is_written_with_its_own_bytes(self):
        png = make_image_bytes("PNG")
        paths, png_by_path = self.receive({"shot.png": png})
        self.assertEqual(paths, [self.path_of("shot.png")])
        self.assertEqual(png_by_path, {self.path_of("shot.png"): png})

    def test_jpg_file_is_converted_to_png(self):
        paths, png_by_path = self.receive({"photo.jpg": make_image_bytes("JPEG")})
        self.assertEqual(paths, [self.path_of("photo.jpg")])
        self.assertTrue(
            png_by_path[self.path_of("photo.jpg")].startswith(PNG_SIGNATURE)
        )

    def test_uppercase_extension_is_matched(self):
        _, png_by_path = self.receive({"PHOTO.JPEG": make_image_bytes("JPEG")})
        self.assertIn(self.path_of("PHOTO.JPEG"), png_by_path)

    def test_gif_and_webp_files_are_converted_to_png(self):
        _, png_by_path = self.receive(
            {"a.gif": make_image_bytes("GIF"), "b.webp": make_image_bytes("WEBP")}
        )
        self.assertTrue(png_by_path[self.path_of("a.gif")].startswith(PNG_SIGNATURE))
        self.assertTrue(png_by_path[self.path_of("b.webp")].startswith(PNG_SIGNATURE))

    def test_txt_file_has_no_png_data(self):
        paths, png_by_path = self.receive({"notes.txt": b"hello"})
        self.assertEqual(paths, [self.path_of("notes.txt")])
        self.assertEqual(png_by_path, {})

    def test_png_data_only_for_the_image_in_a_mixed_batch(self):
        png = make_image_bytes("PNG")
        paths, png_by_path = self.receive({"notes.txt": b"hello", "shot.png": png})
        self.assertCountEqual(
            paths, [self.path_of("notes.txt"), self.path_of("shot.png")]
        )
        self.assertEqual(png_by_path, {self.path_of("shot.png"): png})

    def test_undecodable_jpg_is_written_as_file_url_only(self):
        paths, png_by_path = self.receive(
            {"broken.jpg": b"not an image", "good.png": make_image_bytes("PNG")}
        )
        self.assertCountEqual(
            paths, [self.path_of("broken.jpg"), self.path_of("good.png")]
        )
        self.assertNotIn(self.path_of("broken.jpg"), png_by_path)
        self.assertIn(self.path_of("good.png"), png_by_path)


if __name__ == "__main__":
    unittest.main()
