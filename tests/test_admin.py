import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from werkzeug.security import generate_password_hash

_bootstrap_dir = tempfile.TemporaryDirectory()
_database_path = os.environ.get("DATABASE_PATH")
os.environ["DATABASE_PATH"] = str(Path(_bootstrap_dir.name) / "bootstrap.sqlite3")
try:
    import main
finally:
    if _database_path is None:
        os.environ.pop("DATABASE_PATH", None)
    else:
        os.environ["DATABASE_PATH"] = _database_path


class AdminPanelTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_database_path = main.DATABASE_PATH
        self.original_testing = main.app.config["TESTING"]
        main.DATABASE_PATH = Path(self.temp_dir.name) / "test.sqlite3"
        main.initialize_database()
        main.app.config["TESTING"] = True

    def tearDown(self):
        main.DATABASE_PATH = self.original_database_path
        main.app.config["TESTING"] = self.original_testing
        self.temp_dir.cleanup()

    def add_user(self, name, role):
        with main.database() as connection:
            cursor = connection.execute("""
                INSERT INTO users (name, password_hash, email, phone, role)
                VALUES (?, ?, ?, ?, ?)
            """, (
                name,
                generate_password_hash("test-password", method="pbkdf2:sha256"),
                f"{name}@example.com",
                "555-0100",
                role,
            ))
            return cursor.lastrowid

    def client_as(self, user_id):
        client = main.app.test_client()
        with client.session_transaction() as session:
            session["user_id"] = user_id
        return client

    def add_pitch(self, owner_id, pitch_id="pitch-one"):
        with main.database() as connection:
            connection.execute("""
                INSERT INTO pitches (
                    id, owner_id, title, category, problem, solution,
                    funding_ask, equity
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pitch_id, owner_id, "Sample pitch", "Other",
                "A problem", "A solution", 5000, 10,
            ))
        return pitch_id

    def test_public_signup_and_non_admin_access_are_rejected(self):
        response = main.app.test_client().post("/api/signup", json={
            "name": "attempted-admin",
            "password": "password",
            "email": "attempt@example.com",
            "phone": "555-0100",
            "role": "admin",
        })
        self.assertEqual(response.status_code, 400)
        self.assertEqual(main.app.test_client().get("/admin.html").status_code, 403)
        self.assertEqual(
            main.app.test_client().patch("/api/admin/users/1", json={
                "role": "admin",
            }).status_code,
            403,
        )
        self.assertEqual(
            main.app.test_client().delete("/api/admin/users/1").status_code, 403
        )

        for role in ("developer", "investor"):
            client = self.client_as(self.add_user(f"user-{role}", role))
            self.assertEqual(client.get("/admin.html").status_code, 403)
            self.assertEqual(client.get("/api/admin").status_code, 403)
            self.assertEqual(
                client.patch("/api/admin/users/1", json={
                    "role": "admin",
                }).status_code,
                403,
            )
            self.assertEqual(client.delete("/api/admin/users/1").status_code, 403)
            self.assertEqual(
                client.delete("/api/admin/pitches/pitch-one").status_code, 403
            )

    def test_admin_can_manage_roles_and_delete_pitches_and_users(self):
        admin_id = self.add_user("admin-user", "admin")
        developer_id = self.add_user("pitch-owner", "developer")
        investor_id = self.add_user("investor-user", "investor")
        pitch_id = self.add_pitch(developer_id)
        with main.database() as connection:
            connection.execute(
                "INSERT INTO pitch_views (pitch_id, view_count) VALUES (?, 4)",
                (pitch_id,),
            )
            connection.execute(
                "INSERT INTO unlocks (investor_id, pitch_id) VALUES (?, ?)",
                (investor_id, pitch_id),
            )
            connection.execute(
                "INSERT INTO messages (pitch_id, from_user_id, text) VALUES (?, ?, ?)",
                (pitch_id, investor_id, "Sample message"),
            )

        client = self.client_as(admin_id)
        admin_page = client.get("/admin.html")
        self.assertEqual(admin_page.status_code, 200)
        admin_page.close()
        login = main.app.test_client().post("/api/login", json={
            "name": "admin-user",
            "password": "test-password",
            "role": "admin",
        })
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.get_json()["user"]["role"], "admin")
        admin_data = client.get("/api/admin").get_json()
        self.assertEqual(len(admin_data["users"]), 3)
        self.assertEqual(admin_data["pitches"][0]["id"], pitch_id)

        response = client.patch(f"/api/admin/users/{investor_id}", json={
            "role": "admin",
        })
        self.assertEqual(response.status_code, 200)
        with main.database() as connection:
            role = connection.execute(
                "SELECT role FROM users WHERE id = ?", (investor_id,)
            ).fetchone()["role"]
        self.assertEqual(role, "admin")

        response = client.delete(f"/api/admin/pitches/{pitch_id}")
        self.assertEqual(response.status_code, 200)
        with main.database() as connection:
            for table in ("pitches", "pitch_views", "unlocks", "messages"):
                count = connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE " +
                    ("id = ?" if table == "pitches" else "pitch_id = ?"),
                    (pitch_id,),
                ).fetchone()[0]
                self.assertEqual(count, 0, table)

        user_pitch_id = self.add_pitch(developer_id, "pitch-two")
        with main.database() as connection:
            connection.execute(
                "INSERT INTO pitch_views (pitch_id, view_count) VALUES (?, 2)",
                (user_pitch_id,),
            )
            connection.execute(
                "INSERT INTO unlocks (investor_id, pitch_id) VALUES (?, ?)",
                (investor_id, user_pitch_id),
            )
            connection.execute(
                "INSERT INTO messages (pitch_id, from_user_id, text) VALUES (?, ?, ?)",
                (user_pitch_id, investor_id, "Another message"),
            )
            connection.execute(
                "INSERT INTO oauth_accounts (provider, provider_user_id, user_id) " +
                "VALUES ('github', 'developer-oauth-id', ?)",
                (developer_id,),
            )
        response = client.delete(f"/api/admin/users/{developer_id}")
        self.assertEqual(response.status_code, 200)
        with main.database() as connection:
            self.assertIsNone(connection.execute(
                "SELECT id FROM users WHERE id = ?", (developer_id,)
            ).fetchone())
            self.assertIsNone(connection.execute(
                "SELECT id FROM pitches WHERE id = ?", (user_pitch_id,)
            ).fetchone())
            for table, column in (
                ("pitch_views", "pitch_id"),
                ("unlocks", "pitch_id"),
                ("messages", "pitch_id"),
                ("oauth_accounts", "user_id"),
            ):
                count = connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {column} = ?",
                    (user_pitch_id if column == "pitch_id" else developer_id,),
                ).fetchone()[0]
                self.assertEqual(count, 0, table)

    def test_admin_cannot_delete_or_demote_self_or_last_admin(self):
        admin_id = self.add_user("only-admin", "admin")
        client = self.client_as(admin_id)

        self.assertEqual(client.delete(f"/api/admin/users/{admin_id}").status_code, 409)
        response = client.patch(f"/api/admin/users/{admin_id}", json={
            "role": "developer",
        })
        self.assertEqual(response.status_code, 409)

    def test_existing_database_migrates_to_admin_role(self):
        legacy_path = Path(self.temp_dir.name) / "legacy.sqlite3"
        connection = sqlite3.connect(legacy_path)
        connection.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('developer', 'investor')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.execute("""
            CREATE TABLE pitches (
                id TEXT PRIMARY KEY,
                owner_id INTEGER NOT NULL REFERENCES users(id),
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                problem TEXT NOT NULL,
                solution TEXT NOT NULL,
                funding_ask INTEGER NOT NULL,
                equity REAL NOT NULL,
                link TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.execute("""
            INSERT INTO users (name, password_hash, email, phone, role)
            VALUES ('legacy-user', 'hash', 'legacy@example.com', '', 'developer')
        """)
        connection.execute("""
            INSERT INTO pitches (
                id, owner_id, title, category, problem, solution, funding_ask, equity
            ) VALUES ('legacy-pitch', 1, 'Legacy pitch', 'Other', 'Problem', 'Solution', 5000, 10)
        """)
        connection.commit()
        connection.close()

        main.DATABASE_PATH = legacy_path
        main.initialize_database()
        with main.database() as connection:
            connection.execute(
                "UPDATE users SET role = 'admin' WHERE id = 1"
            )
            self.assertEqual(connection.execute(
                "SELECT COUNT(*) FROM pitches WHERE id = 'legacy-pitch'"
            ).fetchone()[0], 1)
            self.assertEqual(connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall(), [])
