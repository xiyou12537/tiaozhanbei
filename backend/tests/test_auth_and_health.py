from __future__ import annotations

import unittest
import hashlib

from fastapi.testclient import TestClient

from backend.database import SessionLocal, init_db
from backend.main import APP_VERSION, app
from backend.models_db import (
    DeploymentStudyRecord,
    MolecularProblemRecord,
    User,
)


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

    def test_login_with_damaged_password_hash_returns_401_without_exception(self):
        username = f"damaged_hash_user_{id(self)}"
        self.created_usernames.append(username)
        self.db.add(User(username=username, password_hash="damagedhash"))
        self.db.commit()

        response = self.client.post("/api/auth/login", json={"username": username, "password": "secret123"})

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "用户名或密码错误。")

    def test_login_with_empty_or_invalid_length_password_hash_returns_401(self):
        for suffix, password_hash in (("empty", ""), ("short", "a$" + "b" * 64)):
            with self.subTest(suffix=suffix):
                username = f"invalid_hash_{suffix}_{id(self)}"
                self.created_usernames.append(username)
                self.db.add(User(username=username, password_hash=password_hash))
                self.db.commit()

                response = self.client.post("/api/auth/login", json={"username": username, "password": "secret123"})

                self.assertEqual(response.status_code, 401)

    def test_historical_salt_sha256_hash_logs_in_and_upgrades(self):
        username = f"legacy_hash_user_{id(self)}"
        password = "secret123"
        self.created_usernames.append(username)
        legacy_salt = "a" * 64
        legacy_digest = hashlib.sha256((legacy_salt + password).encode()).hexdigest()
        historical_hash = f"{legacy_salt}${legacy_digest}"
        user = User(username=username, password_hash=historical_hash)
        self.db.add(user)
        self.db.commit()

        successful_login = self.client.post("/api/auth/login", json={"username": username, "password": password})

        self.assertEqual(successful_login.status_code, 200)
        self.db.refresh(user)
        self.assertNotEqual(user.password_hash, historical_hash)
        self.assertTrue(user.password_hash.startswith("v2$"))

        subsequent_login = self.client.post("/api/auth/login", json={"username": username, "password": password})
        wrong_password = self.client.post("/api/auth/login", json={"username": username, "password": "wrong-password"})
        self.assertEqual(subsequent_login.status_code, 200)
        self.assertEqual(wrong_password.status_code, 401)

    def test_hash_compatibility_keeps_bearer_and_study_user_isolation(self):
        owner_name = f"study_owner_{id(self)}"
        other_name = f"study_other_{id(self)}"
        self.created_usernames.extend([owner_name, other_name])
        owner_register = self.client.post("/api/auth/register", json={"username": owner_name, "password": "secret123"})
        other_register = self.client.post("/api/auth/register", json={"username": other_name, "password": "secret123"})
        self.assertEqual(owner_register.status_code, 200)
        self.assertEqual(other_register.status_code, 200)
        owner = self.db.query(User).filter_by(username=owner_name).one()
        self.db.add(MolecularProblemRecord(
            problem_id=f"mprob_auth_{id(self)}", user_id=owner.id, molecule_name="H2", status="completed", request_json={}, result_json=None,
        ))
        self.db.add(DeploymentStudyRecord(
            study_id=f"study_auth_{id(self)}", user_id=owner.id, problem_id=f"mprob_auth_{id(self)}", status="completed", request_json={}, result_json=None,
        ))
        self.db.commit()

        own_response = self.client.get(
            f"/api/molecular-studies/study_auth_{id(self)}",
            headers={"Authorization": f"Bearer {owner_register.json()['token']}"},
        )
        other_response = self.client.get(
            f"/api/molecular-studies/study_auth_{id(self)}",
            headers={"Authorization": f"Bearer {other_register.json()['token']}"},
        )
        self.assertEqual(own_response.status_code, 200)
        self.assertEqual(other_response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
