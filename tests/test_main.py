import tempfile
import unittest
from pathlib import Path

import main


class WebsiteDatabaseTests(unittest.TestCase):
	def setUp(self):
		self.temp_dir = tempfile.TemporaryDirectory()
		self.original_database_path = main.DATABASE_PATH
		main.DATABASE_PATH = Path(self.temp_dir.name) / "test.sqlite3"
		main.initialize_database()
		main.app.config.update(TESTING=True, SECRET_KEY="test-secret")
		self.client = main.app.test_client()

	def tearDown(self):
		main.DATABASE_PATH = self.original_database_path
		self.temp_dir.cleanup()

	def signup(self, name, role):
		return self.client.post("/api/signup", json={
			"name": name,
			"password": "pass1234",
			"email": name + "@example.com",
			"phone": "555-0100",
			"role": role,
		})

	def create_pitch(self, title="Water-saving tool"):
		return self.client.post("/api/pitches", json={
			"title": title,
			"cat": "AgriTech",
			"problem": "Water is wasted.",
			"solution": "Measure soil moisture.",
			"ask": 10000,
			"equity": 10,
			"link": "",
		})

	def test_accounts_keep_independent_sessions_and_reject_duplicate_names(self):
		alice_client = main.app.test_client()
		self.assertEqual(alice_client.post("/api/signup", json={
			"name": "alice",
			"password": "pass1234",
			"email": "alice@example.com",
			"phone": "555-0100",
			"role": "developer",
		}).status_code, 201)
		alice_client.post("/api/logout")
		self.assertEqual(self.signup("ALICE", "investor").status_code, 409)
		self.assertEqual(self.signup("bob", "investor").status_code, 201)
		self.client.post("/api/logout")

		self.assertEqual(alice_client.post("/api/login", json={
			"name": "ALICE",
			"password": "pass1234",
			"role": "developer",
		}).status_code, 200)
		self.assertEqual(self.client.post("/api/login", json={
			"name": "bob",
			"password": "pass1234",
			"role": "investor",
		}).status_code, 200)
		self.assertEqual(alice_client.get("/api/state").json["user"], {
			"name": "alice", "role": "developer",
		})
		self.assertEqual(self.client.get("/api/state").json["user"], {
			"name": "bob", "role": "investor",
		})

	def test_custom_pitch_contact_and_messages_require_demo_unlock(self):
		self.assertEqual(self.signup("founder", "developer").status_code, 201)
		pitch_response = self.create_pitch()
		self.assertEqual(pitch_response.status_code, 201)
		pitch_id = pitch_response.json["id"]
		self.client.post("/api/logout")

		self.assertEqual(self.signup("investor", "investor").status_code, 201)
		idea = self.client.get("/api/state").json["ideas"][0]
		self.assertNotIn("owner", idea)
		self.assertNotIn("email", idea)
		self.assertNotIn("phone", idea)
		self.assertEqual(self.client.post("/api/messages", json={
			"id": pitch_id, "text": "Interested"
		}).status_code, 403)

		unlock = self.client.post("/api/unlocks", json={"id": pitch_id})
		self.assertEqual(unlock.status_code, 200)
		self.assertTrue(unlock.json["demo"])
		self.assertEqual(
			self.client.post("/api/unlocks", json={"id": pitch_id}).status_code,
			200,
		)
		idea = self.client.get("/api/state").json["ideas"][0]
		self.assertEqual(idea["owner"], "founder")
		self.assertEqual(idea["email"], "founder@example.com")
		self.assertEqual(self.client.post("/api/messages", json={
			"id": pitch_id, "text": "Interested"
		}).status_code, 201)
		self.client.post("/api/logout")

		self.assertEqual(self.client.post("/api/login", json={
			"name": "founder", "password": "pass1234", "role": "developer"
		}).status_code, 200)
		state = self.client.get("/api/state").json
		self.assertEqual(state["messages"], [{
			"id": pitch_id, "from": "investor", "text": "Interested"
		}])
		self.assertEqual(state["unlocks"][0]["by"], "investor")

	def test_demo_unlock_requires_investor_and_existing_pitch(self):
		self.assertEqual(self.client.post(
			"/api/unlocks", json={"id": "waterwise"}
		).status_code, 401)
		self.assertEqual(self.signup("founder", "developer").status_code, 201)
		pitch_id = self.create_pitch().json["id"]
		self.assertEqual(self.client.post(
			"/api/unlocks", json={"id": pitch_id}
		).status_code, 401)
		self.client.post("/api/logout")
		self.assertEqual(self.signup("investor", "investor").status_code, 201)
		self.assertEqual(self.client.post(
			"/api/unlocks", json={"id": "not-a-pitch"}
		).status_code, 404)
		with main.database() as connection:
			table_names = {
				row["name"] for row in connection.execute(
					"SELECT name FROM sqlite_master WHERE type = 'table'"
				)
			}
		self.assertNotIn("payment_transactions", table_names)

	def test_sample_contact_is_absent_until_demo_unlock(self):
		self.assertEqual(self.signup("investor", "investor").status_code, 201)
		for pitch_id, contact in main.SAMPLE_CONTACTS.items():
			chat_html = self.client.get(f"/chat-{pitch_id}.html")
			self.assertNotIn(contact["name"].encode(), chat_html.data)
			self.assertNotIn(contact["email"].encode(), chat_html.data)
			chat_html.close()
			pitch_html = self.client.get(f"/pitch-{pitch_id}.html")
			self.assertNotIn(contact["name"].encode(), pitch_html.data)
			pitch_html.close()
		self.assertEqual(self.client.get(
			"/api/state"
		).json["sample_contacts"], {})

		self.assertEqual(self.client.post(
			"/api/unlocks", json={"id": "waterwise"}
		).status_code, 200)
		self.assertEqual(
			self.client.get("/api/state").json["sample_contacts"]["waterwise"],
			{"name": "demo_farmer", "email": "demo_farmer@example.com"},
		)

	def test_profile_and_tracker_are_saved_per_account(self):
		self.assertEqual(self.signup("founder", "developer").status_code, 201)
		entry = self.client.post("/api/tracker", json={"name": "Investor A"})
		self.assertEqual(entry.status_code, 201)
		entry_id = entry.json["id"]
		self.assertEqual(self.client.patch(
			f"/api/tracker/{entry_id}", json={"stage": "In talks"}
		).status_code, 200)
		self.client.post("/api/logout")

		self.assertEqual(self.signup("investor", "investor").status_code, 201)
		self.assertEqual(self.client.put("/api/profile", json={
			"sector": "FinTech", "max": 50000
		}).status_code, 200)
		state = self.client.get("/api/state").json
		self.assertEqual(state["profile"], {"sector": "FinTech", "max": 50000})
		self.assertEqual(state["tracker"], [])

		self.client.post("/api/logout")
		self.client.post("/api/login", json={
			"name": "founder", "password": "pass1234", "role": "developer"
		})
		self.assertEqual(
			self.client.get("/api/state").json["tracker"][0]["stage"], "In talks"
		)

	def test_assets_work_and_esewa_routes_are_removed(self):
		for path in ("/", "/app.js"):
			response = self.client.get(path)
			self.assertEqual(response.status_code, 200)
			response.close()
		self.assertEqual(self.client.get("/instance/secret_key").status_code, 404)
		registered_routes = {rule.rule for rule in main.app.url_map.iter_rules()}
		self.assertNotIn("/api/payments/esewa", registered_routes)
		self.assertNotIn("/payments/esewa/success", registered_routes)
		self.assertEqual(self.client.post(
			"/api/payments/esewa", json={"id": "waterwise"}
		).status_code, 405)
		self.assertEqual(
			self.client.get("/payments/esewa/success").status_code, 404
		)


if __name__ == "__main__":
	unittest.main()
