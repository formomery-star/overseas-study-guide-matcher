import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from subprocess import CompletedProcess, TimeoutExpired
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from werkzeug.security import generate_password_hash

WEBAPP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEBAPP))
os.environ.setdefault("WORK_PACKAGE_ROOT", str(WEBAPP.parent))
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="study-intake-test-"))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-" + "x" * 48)
os.environ.setdefault("DATA_ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("ADMIN_PASSWORD_HASH", generate_password_hash("test-password-long-enough", method="scrypt"))
os.environ.setdefault("COOKIE_SECURE", "0")

import app as web


class WebAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="study-intake-tests-")
        web.DATA_DIR = Path(cls.tmp.name)
        web.DB_PATH = web.DATA_DIR / "intake.sqlite3"
        web.REPORTS_DIR = web.DATA_DIR / "reports"
        web.QUEUE_DIR = web.DATA_DIR / "queue"
        web.ATTACHMENTS_DIR = web.DATA_DIR / "attachments"
        web.METRICS_DIR = web.DATA_DIR / "metrics"
        web.GENERATION_TMP = web.DATA_DIR / "tmp"
        for p in (web.DATA_DIR, web.REPORTS_DIR, web.QUEUE_DIR, web.ATTACHMENTS_DIR, web.METRICS_DIR, web.GENERATION_TMP):
            p.mkdir(parents=True, exist_ok=True)
        web.init_db()
        cls.queue_put = web.WORK.put
        web.WORK.put = lambda *_args, **_kwargs: None
        web.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)

    @classmethod
    def tearDownClass(cls):
        web.WORK.put = cls.queue_put
        cls.tmp.cleanup()

    def setUp(self):
        web.RATE_LIMIT.clear()
        self.client = web.app.test_client()

    def submit(self, name="样本学生", attachments=None, extra=None):
        answers = {"姓名": name, "课程体系": "AP", "意向专业职业": "机械工程", "活动状态": "无"}
        answers.update(extra or {})
        data = {"answers": json.dumps(answers, ensure_ascii=False)}
        if attachments:
            data["attachments"] = attachments
        return self.client.post("/api/submissions", data=data, content_type="multipart/form-data")

    def login(self):
        response = self.client.post("/api/admin/login", json={"password": "test-password-long-enough"})
        self.assertEqual(response.status_code, 200)
        return response.json["csrf"]

    def test_public_receipt_does_not_expose_report_download(self):
        response = self.submit()
        self.assertEqual(response.status_code, 202)
        receipt = response.json["receipt"]
        status = self.client.get("/api/status/" + receipt)
        self.assertEqual(status.status_code, 200)
        self.assertFalse(status.json["download_available"])
        self.assertEqual(self.client.get("/api/admin/submissions").status_code, 401)

    def test_payload_encrypted_and_admin_required_for_answers(self):
        response = self.submit(name="私密姓名测试")
        submission_id = None
        with web.db() as c:
            rows = c.execute("SELECT id,payload FROM submissions").fetchall()
            row = next(r for r in rows if web.decrypt_payload(r["payload"]).get("answers", {}).get("姓名") == "私密姓名测试")
            submission_id = row["id"]
            self.assertNotIn("私密姓名测试".encode(), row["payload"])
        self.assertEqual(self.client.get(f"/api/admin/submissions/{submission_id}").status_code, 401)
        csrf = self.login()
        detail = self.client.get(f"/api/admin/submissions/{submission_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json["answers"]["姓名"], "私密姓名测试")
        self.assertEqual(self.client.post("/api/admin/logout", headers={"X-CSRF-Token": "bad"}).status_code, 403)
        self.assertTrue(csrf)

    def test_attachment_is_encrypted_and_admin_download_only(self):
        blob = b"%PDF-1.4 minimal private score sample"
        response = self.submit(attachments=(io.BytesIO(blob), "grades.pdf"))
        self.assertEqual(response.status_code, 202)
        with web.db() as c:
            row = c.execute("SELECT id,payload FROM submissions ORDER BY created_at DESC LIMIT 1").fetchone()
        submission_id = row["id"]
        payload = web.decrypt_payload(row["payload"])
        item = payload["attachments"][0]
        encrypted_path = web.ATTACHMENTS_DIR / submission_id / (item["id"] + ".enc")
        self.assertNotEqual(encrypted_path.read_bytes(), blob)
        self.assertEqual(hashlib.sha256(web.CIPHER.decrypt(encrypted_path.read_bytes())).hexdigest(), item["sha256"])
        self.assertEqual(self.client.get(f"/api/admin/submissions/{submission_id}/attachments/{item['id']}").status_code, 401)
        self.login()
        download = self.client.get(f"/api/admin/submissions/{submission_id}/attachments/{item['id']}")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.data, blob)

    def test_report_archive_is_encrypted_and_admin_only(self):
        response = self.submit()
        self.assertEqual(response.status_code, 202)
        with web.db() as c:
            row = c.execute("SELECT id FROM submissions ORDER BY created_at DESC LIMIT 1").fetchone()
            submission_id = row["id"]
            c.execute("UPDATE submissions SET status='preview_ready',report_relpath=? WHERE id=?",
                      (f"{submission_id}.zip.enc", submission_id))
        archive = b"PK\x03\x04synthetic internal guide archive"
        encrypted = web.CIPHER.encrypt(archive)
        path = web.REPORTS_DIR / f"{submission_id}.zip.enc"
        path.write_bytes(encrypted)
        self.assertNotIn(archive, path.read_bytes())
        self.assertEqual(self.client.get(f"/api/admin/submissions/{submission_id}/report").status_code, 401)
        self.login()
        download = self.client.get(f"/api/admin/submissions/{submission_id}/report")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.data, archive)

    def test_database_snapshot_requires_admin_and_returns_stable_digest(self):
        self.assertEqual(self.client.get("/api/admin/database-snapshot").status_code, 401)
        self.login()
        response = self.client.get("/api/admin/database-snapshot")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["snapshot_sha256"]), 64)
        self.assertGreaterEqual(len(response.json["database_snapshot_sha256"]), 9)

    def test_admin_can_delete_submission_and_encrypted_attachments(self):
        response = self.submit(attachments=(io.BytesIO(b"secret"), "notes.pdf"))
        with web.db() as c:
            row = c.execute("SELECT id,payload FROM submissions ORDER BY created_at DESC LIMIT 1").fetchone()
        submission_id = row["id"]
        payload = web.decrypt_payload(row["payload"])
        attachment_path = web.ATTACHMENTS_DIR / submission_id / (payload["attachments"][0]["id"] + ".enc")
        self.assertTrue(attachment_path.exists())
        self.assertEqual(self.client.delete(f"/api/admin/submissions/{submission_id}").status_code, 401)
        csrf = self.login()
        deleted = self.client.delete(f"/api/admin/submissions/{submission_id}", headers={"X-CSRF-Token": csrf})
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(attachment_path.exists())
        self.assertEqual(self.client.get(f"/api/admin/submissions/{submission_id}").status_code, 404)

    def test_rejects_unknown_fields_and_forbidden_file_types(self):
        bad = self.client.post("/api/submissions", data={"answers": json.dumps({"姓名":"甲","课程体系":"AP","意向专业职业":"CS","未知":"x"})}, content_type="multipart/form-data")
        self.assertEqual(bad.status_code, 422)
        wrong_file = self.submit(attachments=(io.BytesIO(b"no"), "script.exe"))
        self.assertEqual(wrong_file.status_code, 422)

    def test_rejects_invalid_numeric_fields_without_storing_submission(self):
        invalid_values = ["文字", "-1", "1e12", True, float("nan"), 10 ** 1000]
        numeric_fields = ("年预算万元", "总预算万元", "每月支持小时", "最长培养年数")
        with web.db() as c:
            before = c.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
        for field in numeric_fields:
            for value in invalid_values:
                with self.subTest(field=field, value_type=type(value).__name__):
                    web.RATE_LIMIT.clear()
                    response = self.submit(extra={field: value})
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json["error"], "invalid_numeric_field")
                    self.assertEqual(response.json["field"], field)
                    self.assertIn("留空", response.json["message"])
        with web.db() as c:
            after = c.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
        self.assertEqual(after, before)
        for field in numeric_fields:
            web.RATE_LIMIT.clear()
            self.assertEqual(self.submit(extra={field: "12.5"}).status_code, 202)
        web.RATE_LIMIT.clear()
        self.assertEqual(self.submit(extra={"年预算万元": ""}).status_code, 202)

    def test_renderer_timeout_is_isolated_and_logged(self):
        self.submit(name="合成超时场景")
        with web.db() as c:
            submission_id = c.execute("SELECT id FROM submissions ORDER BY created_at DESC LIMIT 1").fetchone()[0]
        with self.assertLogs("app", level="WARNING") as logs:
            with patch.object(web.subprocess, "run", side_effect=TimeoutExpired(cmd=["synthetic renderer"], timeout=900)):
                web.run_preview(submission_id)
        with web.db() as c:
            row = c.execute("SELECT status,error_code FROM submissions WHERE id=?", (submission_id,)).fetchone()
        self.assertEqual((row["status"], row["error_code"]), ("failed", "generation_timeout"))
        self.assertTrue(any(submission_id in line and "generation_timeout" in line for line in logs.output))
        self.assertNotIn("合成超时场景", "\n".join(logs.output))
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        self.assertEqual(list(web.GENERATION_TMP.iterdir()), [])

    def test_renderer_failure_is_isolated_and_logged(self):
        self.submit(name="合成检索失败场景")
        with web.db() as c:
            submission_id = c.execute("SELECT id FROM submissions ORDER BY created_at DESC LIMIT 1").fetchone()[0]
        failure = CompletedProcess(args=["synthetic renderer"], returncode=1, stdout="", stderr="synthetic database unavailable")
        with self.assertLogs("app", level="ERROR") as logs:
            with patch.object(web.subprocess, "run", return_value=failure):
                web.run_preview(submission_id)
        with web.db() as c:
            row = c.execute("SELECT status,error_code FROM submissions WHERE id=?", (submission_id,)).fetchone()
        self.assertEqual((row["status"], row["error_code"]), ("failed", "renderer_failed"))
        self.assertTrue(any(submission_id in line and "renderer_failed" in line for line in logs.output))
        self.assertNotIn("合成检索失败场景", "\n".join(logs.output))
        self.assertNotIn("database unavailable", "\n".join(logs.output))
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        self.assertEqual(list(web.GENERATION_TMP.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
