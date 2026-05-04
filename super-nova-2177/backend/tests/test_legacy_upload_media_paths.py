import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
for path in (ROOT, BACKEND_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

import backend.app as backend_app  # noqa: E402


class LegacyUploadMediaPathTests(unittest.TestCase):
    def test_media_payload_does_not_double_legacy_upload_prefix(self):
        media = backend_app._media_payload(
            "uploads/legacy-image.jpg",
            "",
            "",
            "uploads/legacy-file.pdf",
        )

        self.assertEqual(media["image"], "/uploads/legacy-image.jpg")
        self.assertEqual(media["images"], ["/uploads/legacy-image.jpg"])
        self.assertEqual(media["file"], "/uploads/legacy-file.pdf")

    def test_media_payload_handles_legacy_upload_prefix_inside_image_list(self):
        media = backend_app._media_payload(
            '["uploads/one.jpg", "/uploads/two.jpg", "three.jpg"]',
        )

        self.assertEqual(
            media["images"],
            ["/uploads/one.jpg", "/uploads/two.jpg", "/uploads/three.jpg"],
        )


if __name__ == "__main__":
    unittest.main()
