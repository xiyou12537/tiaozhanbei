from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from backend.database import SessionLocal, init_db
from backend.main import APP_VERSION, app
from backend.models_db import User


class AuthAndHealthTests(unittest.TestCase):
    def setUp(self):
        init_db()
        self.client = TestClient(app)
        self.db = SessionLocal()
        self.created_usernames: list[str] = []

    def tearDown(self):
        for username in self.created_usernames:
            self.db.query(User).filter(User.username == username).delete(synchronize_session=False)
        self.db.commit()
        self.db.close()

    def test_health_endpoint_reports_runtime_status(self):
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn(payload["status"], {"ok", "degraded"})
        self.assertEqual(payload["version"], APP_VERSION)
        self.assertEqual(payload["docs_url"], "/docs")
        self.assertEqual(payload["services"]["api"]["status"], "ok")
        self.assertEqual(payload["services"]["legacy_database"]["status"], "ok")
        self.assertIn("platform_database", payload["services"])
        self.assertIn("workflow_queue", payload["services"])
        self.assertEqual(payload["services"]["authentication"]["status"], "ok")
        self.assertIn("circuit_parser", payload["services"])
        self.assertIn("partitioning", payload["services"])

    def test_register_login_and_get_current_user(self):
        username = f"auth_user_{id(self)}"
        self.created_usernames.append(username)

        register_response = self.client.post(
            "/api/auth/register",
            json={"username": username, "password": "secret123"},
        )
        self.assertEqual(register_response.status_code, 200)

        register_payload = register_response.json()
        self.assertEqual(register_payload["username"], username)
        self.assertEqual(register_payload["message"], "注册成功")
        self.assertTrue(register_payload["token"])

        login_response = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": "secret123"},
        )
        self.assertEqual(login_response.status_code, 200)
        login_payload = login_response.json()
        self.assertEqual(login_payload["username"], username)
        self.assertEqual(login_payload["message"], "登录成功")

        me_response = self.client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {login_payload['token']}"},
        )
        self.assertEqual(me_response.status_code, 200)
        me_payload = me_response.json()
        self.assertEqual(me_payload["username"], username)
        self.assertTrue(me_payload["created_at"])

    def test_register_duplicate_username_returns_409(self):
        username = f"duplicate_user_{id(self)}"
        self.created_usernames.append(username)

        first_response = self.client.post(
            "/api/auth/register",
            json={"username": username, "password": "secret123"},
        )
        self.assertEqual(first_response.status_code, 200)

        duplicate_response = self.client.post(
            "/api/auth/register",
            json={"username": username, "password": "another123"},
        )
        self.assertEqual(duplicate_response.status_code, 409)
        self.assertEqual(duplicate_response.json()["detail"], "用户名已存在。")

    def test_login_with_wrong_password_returns_401(self):
        username = f"wrong_password_user_{id(self)}"
        self.created_usernames.append(username)

        register_response = self.client.post(
            "/api/auth/register",
            json={"username": username, "password": "secret123"},
        )
        self.assertEqual(register_response.status_code, 200)

        login_response = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": "bad-password"},
        )
        self.assertEqual(login_response.status_code, 401)
        self.assertEqual(login_response.json()["detail"], "用户名或密码错误。")


if __name__ == "__main__":
    unittest.main()
