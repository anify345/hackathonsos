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

	def test_pitch_contact_is_private_until_unlocked_and_messages_persist(self):
		self.assertEqual(self.signup("founder", "developer").status_code, 201)
		pitch_response = self.client.post("/api/pitches", json={
			"title": "Water-saving tool",
			"cat": "AgriTech",
			"problem": "Water is wasted.",
			"solution": "Measure soil moisture.",
			"ask": 10000,
			"equity": 10,
			"link": "",
		})
		self.assertEqual(pitch_response.status_code, 201)
		pitch_id = pitch_response.json["id"]
		self.client.post("/api/logout")

		self.assertEqual(self.signup("investor", "investor").status_code, 201)
		idea = self.client.get("/api/state").json["ideas"][0]
		self.assertNotIn("email", idea)
		self.assertEqual(self.client.post("/api/messages", json={
			"id": pitch_id, "text": "Interested"
		}).status_code, 403)
		self.assertEqual(self.client.post(
			"/api/unlocks", json={"id": pitch_id}
		).status_code, 200)
		idea = self.client.get("/api/state").json["ideas"][0]
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

	def test_pages_and_assets_are_served_without_exposing_instance_files(self):
		for path in ("/", "/app.js"):
			response = self.client.get(path)
			self.assertEqual(response.status_code, 200)
			response.close()
		self.assertEqual(self.client.get("/instance/secret_key").status_code, 404)


if __name__ == "__main__":
	unittest.main()
