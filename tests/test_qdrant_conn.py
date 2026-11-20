import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.qdrant_conn import qdrant_connection_kwargs  # noqa: E402


class QdrantConnectionKwargsTest(unittest.TestCase):
    def test_cloud_https_keeps_api_key(self):
        kw = qdrant_connection_kwargs("https://abc.cloud.qdrant.io", "secret", timeout=15)
        self.assertEqual(kw, {"url": "https://abc.cloud.qdrant.io", "timeout": 15, "api_key": "secret"})

    def test_local_http_drops_api_key(self):
        for url in ("http://localhost:6333", "http://127.0.0.1:6333", "http://qdrant:6333"):
            kw = qdrant_connection_kwargs(url, "secret", timeout=30)
            self.assertNotIn("api_key", kw, url)

    def test_remote_http_keeps_api_key(self):
        kw = qdrant_connection_kwargs("http://10.0.0.5:6333", "secret", timeout=30)
        self.assertEqual(kw["api_key"], "secret")

    def test_blank_api_key_omitted(self):
        self.assertNotIn("api_key", qdrant_connection_kwargs("https://x.io", "  ", timeout=5))
        self.assertNotIn("api_key", qdrant_connection_kwargs("https://x.io", None, timeout=5))


if __name__ == "__main__":
    unittest.main()
