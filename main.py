"""Flask app and SQLite API for the Hackathon SOS website."""

import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from flask import Flask, abort, jsonify, request, send_file, session
from werkzeug.security import check_password_hash, generate_password_hash


app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
DATABASE_PATH = Path(os.environ.get(
	"DATABASE_PATH", INSTANCE_DIR / "hackathonsos.sqlite3"
))
SAMPLE_IDEAS = {"waterwise", "rentcircle", "classpulse"}
SECTORS = {"Any", "AgriTech", "FinTech", "EdTech", "HealthTech", "Other"}
TRACKER_STAGES = {"To contact", "Contacted", "In talks", "Funded", "Passed"}
ASSET_SUFFIXES = {".html", ".htm", ".js", ".css", ".png", ".jpg", ".jpeg",
				  ".svg", ".webp", ".ico", ".woff", ".woff2"}


def load_secret_key():
	secret = os.environ.get("SECRET_KEY")
	if secret:
		return secret
	INSTANCE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
	key_path = INSTANCE_DIR / "secret_key"
	try:
		fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
	except FileExistsError:
		return key_path.read_text(encoding="utf-8").strip()
	with os.fdopen(fd, "w", encoding="utf-8") as key_file:
		secret = secrets.token_hex(32)
		key_file.write(secret)
	return secret


app.config.update(
	SECRET_KEY=load_secret_key(),
	SESSION_COOKIE_HTTPONLY=True,
	SESSION_COOKIE_SAMESITE="Lax",
)


@contextmanager
def database():
	DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
	connection = sqlite3.connect(DATABASE_PATH)
	connection.row_factory = sqlite3.Row
	try:
		with connection:
			yield connection
	finally:
		connection.close()


def initialize_database():
	with database() as connection:
		connection.executescript("""
			CREATE TABLE IF NOT EXISTS users (
				id INTEGER PRIMARY KEY,
				name TEXT NOT NULL COLLATE NOCASE UNIQUE,
				password_hash TEXT NOT NULL,
				email TEXT NOT NULL,
				phone TEXT NOT NULL,
				role TEXT NOT NULL CHECK (role IN ('developer', 'investor')),
				created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
			);
			CREATE TABLE IF NOT EXISTS pitches (
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
			);
			CREATE TABLE IF NOT EXISTS unlocks (
				investor_id INTEGER NOT NULL REFERENCES users(id),
				pitch_id TEXT NOT NULL,
				created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
				PRIMARY KEY (investor_id, pitch_id)
			);
			CREATE TABLE IF NOT EXISTS messages (
				id INTEGER PRIMARY KEY,
				pitch_id TEXT NOT NULL,
				from_user_id INTEGER NOT NULL REFERENCES users(id),
				text TEXT NOT NULL,
				created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
			);
			CREATE TABLE IF NOT EXISTS investor_profiles (
				investor_id INTEGER PRIMARY KEY REFERENCES users(id),
				sector TEXT NOT NULL,
				max_amount INTEGER NOT NULL
			);
			CREATE TABLE IF NOT EXISTS pitch_views (
				pitch_id TEXT PRIMARY KEY,
				view_count INTEGER NOT NULL DEFAULT 0
			);
			CREATE TABLE IF NOT EXISTS tracker_entries (
				id INTEGER PRIMARY KEY,
				user_id INTEGER NOT NULL REFERENCES users(id),
				name TEXT NOT NULL,
				stage TEXT NOT NULL,
				created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
			);
		""")


initialize_database()


def api_error(message, status):
	return jsonify(error=message), status


def payload():
	data = request.get_json()
	if not isinstance(data, dict):
		raise ValueError("A JSON object is required.")
	return data


def text_value(data, key, *, required=True, maximum=500):
	value = data.get(key, "")
	if not isinstance(value, str):
		raise ValueError(f"{key} must be text.")
	value = value.strip()
	if required and not value:
		raise ValueError(f"{key} is required.")
	if len(value) > maximum:
		raise ValueError(f"{key} must be {maximum} characters or fewer.")
	return value


def current_user(connection):
	user_id = session.get("user_id")
	if not user_id:
		return None
	return connection.execute(
		"SELECT id, name, role, email, phone FROM users WHERE id = ?",
		(user_id,),
	).fetchone()


def public_user(user):
	return {"name": user["name"], "role": user["role"]}


@app.get("/")
def index():
	index_file = BASE_DIR / "index.html"
	if not index_file.is_file():
		abort(404)
	return send_file(index_file)


@app.get("/<path:asset>")
def serve_asset(asset):
	requested = (BASE_DIR / asset).resolve()
	if (not requested.is_relative_to(BASE_DIR) or
			requested.suffix.lower() not in ASSET_SUFFIXES or
			not requested.is_file()):
		abort(404)
	return send_file(requested)


@app.get("/api/state")
def get_state():
	with database() as connection:
		user = current_user(connection)
		user_id = user["id"] if user else None
		ideas = connection.execute("""
			SELECT p.id, p.owner_id, u.name AS owner, p.title,
				   p.category AS cat, p.problem, p.solution,
				   p.funding_ask AS ask, p.equity, p.link,
				   u.email, u.phone
			FROM pitches p JOIN users u ON u.id = p.owner_id
			ORDER BY p.created_at, p.id
		""").fetchall()
		unlocked_ids = set()
		unlocks = []
		if user:
			if user["role"] == "investor":
				rows = connection.execute("""
					SELECT pitch_id AS id, ? AS by
					FROM unlocks WHERE investor_id = ?
				""", (user["name"], user_id)).fetchall()
			else:
				rows = connection.execute("""
					SELECT x.pitch_id AS id, u.name AS by
					FROM unlocks x
					JOIN pitches p ON p.id = x.pitch_id
					JOIN users u ON u.id = x.investor_id
					WHERE p.owner_id = ?
				""", (user_id,)).fetchall()
			unlocks = [dict(row) for row in rows]
			unlocked_ids = {row["id"] for row in rows}

		idea_data = []
		for idea in ideas:
			item = {key: idea[key] for key in
					("id", "owner", "title", "cat", "problem", "solution",
					 "ask", "equity", "link")}
			if user and user["role"] == "investor" and idea["id"] in unlocked_ids:
				item.update(email=idea["email"], phone=idea["phone"])
			idea_data.append(item)

		messages = []
		views = {}
		profile = None
		tracker = []
		if user and user["role"] == "developer":
			messages = [dict(row) for row in connection.execute("""
				SELECT m.pitch_id AS id, u.name AS 'from', m.text
				FROM messages m
				JOIN users u ON u.id = m.from_user_id
				JOIN pitches p ON p.id = m.pitch_id
				WHERE p.owner_id = ? ORDER BY m.id
			""", (user_id,))]
			views = {
				row["pitch_id"]: row["view_count"]
				for row in connection.execute("""
					SELECT v.pitch_id, v.view_count FROM pitch_views v
					JOIN pitches p ON p.id = v.pitch_id WHERE p.owner_id = ?
				""", (user_id,))
			}
			tracker = [dict(row) for row in connection.execute("""
				SELECT id, name, stage FROM tracker_entries
				WHERE user_id = ? ORDER BY id
			""", (user_id,))]
		elif user and user["role"] == "investor":
			row = connection.execute("""
				SELECT sector, max_amount AS max FROM investor_profiles
				WHERE investor_id = ?
			""", (user_id,)).fetchone()
			profile = dict(row) if row else None

		return jsonify(
			user=public_user(user) if user else None,
			ideas=idea_data,
			unlocks=unlocks,
			messages=messages,
			views=views,
			profile=profile,
			tracker=tracker,
		)


@app.post("/api/signup")
def signup():
	try:
		data = payload()
		name = text_value(data, "name", maximum=40)
		password = text_value(data, "password", maximum=256)
		email = text_value(data, "email", maximum=254)
		phone = text_value(data, "phone", maximum=40)
		role = text_value(data, "role", maximum=20)
		if len(password) < 4:
			return api_error("Password must be at least 4 characters.", 400)
		if role not in {"developer", "investor"}:
			return api_error("Role must be developer or investor.", 400)
		if name.lower().startswith("demo_"):
			return api_error("That username is reserved.", 409)
		with database() as connection:
			cursor = connection.execute("""
				INSERT INTO users (name, password_hash, email, phone, role)
				VALUES (?, ?, ?, ?, ?)
			""", (name, generate_password_hash(password), email, phone, role))
			session.clear()
			session["user_id"] = cursor.lastrowid
		return jsonify(user={"name": name, "role": role}), 201
	except ValueError as error:
		return api_error(str(error), 400)
	except sqlite3.IntegrityError:
		return api_error("That username is taken.", 409)


@app.post("/api/login")
def login():
	try:
		data = payload()
		name = text_value(data, "name", maximum=40)
		password = text_value(data, "password", maximum=256)
		role = text_value(data, "role", maximum=20)
		if role not in {"developer", "investor"}:
			return api_error("Role must be developer or investor.", 400)
		with database() as connection:
			user = connection.execute("""
				SELECT id, name, role, password_hash FROM users
				WHERE name = ? COLLATE NOCASE AND role = ?
			""", (name, role)).fetchone()
			if not user or not check_password_hash(user["password_hash"], password):
				return api_error(f"Wrong username or password for a {role} account.", 401)
			session.clear()
			session["user_id"] = user["id"]
		return jsonify(user=public_user(user))
	except ValueError as error:
		return api_error(str(error), 400)


@app.post("/api/logout")
def logout():
	session.clear()
	return jsonify(ok=True)


@app.post("/api/pitches")
def create_pitch():
	try:
		data = payload()
		title = text_value(data, "title", maximum=100)
		category = text_value(data, "cat", maximum=40)
		problem = text_value(data, "problem", maximum=500)
		solution = text_value(data, "solution", maximum=500)
		link = text_value(data, "link", required=False, maximum=2048)
		try:
			ask = int(data.get("ask"))
			equity = float(data.get("equity"))
		except (TypeError, ValueError):
			return api_error("Funding ask and equity must be numbers.", 400)
		if category not in SECTORS - {"Any"} or ask < 1000 or not 1 <= equity <= 100:
			return api_error("Invalid category, funding ask, or equity amount.", 400)
		if link and not link.lower().startswith(("http://", "https://")):
			return api_error("The link must start with http:// or https://.", 400)
		with database() as connection:
			user = current_user(connection)
			if not user or user["role"] != "developer":
				return api_error("A developer account is required.", 401)
			pitch_id = "i" + secrets.token_urlsafe(12)
			connection.execute("""
				INSERT INTO pitches
					(id, owner_id, title, category, problem, solution,
					 funding_ask, equity, link)
				VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
			""", (pitch_id, user["id"], title, category, problem, solution,
				  ask, equity, link))
		return jsonify(id=pitch_id), 201
	except ValueError as error:
		return api_error(str(error), 400)


@app.post("/api/unlocks")
def create_unlock():
	try:
		data = payload()
		pitch_id = text_value(data, "id", maximum=100)
		with database() as connection:
			user = current_user(connection)
			if not user or user["role"] != "investor":
				return api_error("An investor account is required.", 401)
			pitch = connection.execute(
				"SELECT owner_id FROM pitches WHERE id = ?", (pitch_id,)
			).fetchone()
			if not pitch and pitch_id not in SAMPLE_IDEAS:
				return api_error("Pitch not found.", 404)
			if pitch and pitch["owner_id"] == user["id"]:
				return api_error("You cannot unlock your own pitch.", 403)
			connection.execute("""
				INSERT OR IGNORE INTO unlocks (investor_id, pitch_id)
				VALUES (?, ?)
			""", (user["id"], pitch_id))
		return jsonify(ok=True)
	except ValueError as error:
		return api_error(str(error), 400)


@app.post("/api/messages")
def create_message():
	try:
		data = payload()
		pitch_id = text_value(data, "id", maximum=100)
		text = text_value(data, "text", maximum=500)
		with database() as connection:
			user = current_user(connection)
			if not user or user["role"] != "investor":
				return api_error("An investor account is required.", 401)
			unlocked = connection.execute("""
				SELECT 1 FROM unlocks WHERE investor_id = ? AND pitch_id = ?
			""", (user["id"], pitch_id)).fetchone()
			if not unlocked:
				return api_error("Unlock this pitch before sending a message.", 403)
			connection.execute("""
				INSERT INTO messages (pitch_id, from_user_id, text)
				VALUES (?, ?, ?)
			""", (pitch_id, user["id"], text))
		return jsonify(ok=True), 201
	except ValueError as error:
		return api_error(str(error), 400)


@app.post("/api/views")
def record_view():
	try:
		data = payload()
		pitch_id = text_value(data, "id", maximum=100)
		with database() as connection:
			user = current_user(connection)
			if pitch_id not in SAMPLE_IDEAS:
				pitch = connection.execute(
					"SELECT owner_id FROM pitches WHERE id = ?", (pitch_id,)
				).fetchone()
				if not pitch:
					return api_error("Pitch not found.", 404)
				if user and user["id"] == pitch["owner_id"]:
					return jsonify(ok=True)
			connection.execute("""
				INSERT INTO pitch_views (pitch_id, view_count) VALUES (?, 1)
				ON CONFLICT(pitch_id) DO UPDATE
				SET view_count = view_count + 1
			""", (pitch_id,))
		return jsonify(ok=True)
	except ValueError as error:
		return api_error(str(error), 400)


@app.put("/api/profile")
def save_profile():
	try:
		data = payload()
		sector = text_value(data, "sector", maximum=40)
		try:
			max_amount = int(data.get("max"))
		except (TypeError, ValueError):
			return api_error("Maximum investment must be a number.", 400)
		if sector not in SECTORS or max_amount < 1000:
			return api_error("Invalid sector or maximum investment.", 400)
		with database() as connection:
			user = current_user(connection)
			if not user or user["role"] != "investor":
				return api_error("An investor account is required.", 401)
			connection.execute("""
				INSERT INTO investor_profiles (investor_id, sector, max_amount)
				VALUES (?, ?, ?)
				ON CONFLICT(investor_id) DO UPDATE
				SET sector = excluded.sector, max_amount = excluded.max_amount
			""", (user["id"], sector, max_amount))
		return jsonify(ok=True)
	except ValueError as error:
		return api_error(str(error), 400)


@app.post("/api/tracker")
def create_tracker_entry():
	try:
		data = payload()
		name = text_value(data, "name", maximum=40)
		with database() as connection:
			user = current_user(connection)
			if not user or user["role"] != "developer":
				return api_error("A developer account is required.", 401)
			cursor = connection.execute("""
				INSERT INTO tracker_entries (user_id, name, stage)
				VALUES (?, ?, 'To contact')
			""", (user["id"], name))
		return jsonify(id=cursor.lastrowid, name=name, stage="To contact"), 201
	except ValueError as error:
		return api_error(str(error), 400)


@app.patch("/api/tracker/<int:entry_id>")
def update_tracker_entry(entry_id):
	try:
		data = payload()
		stage = text_value(data, "stage", maximum=40)
		if stage not in TRACKER_STAGES:
			return api_error("Invalid tracker stage.", 400)
		with database() as connection:
			user = current_user(connection)
			if not user or user["role"] != "developer":
				return api_error("A developer account is required.", 401)
			result = connection.execute("""
				UPDATE tracker_entries SET stage = ?
				WHERE id = ? AND user_id = ?
			""", (stage, entry_id, user["id"]))
			if result.rowcount == 0:
				return api_error("Tracker entry not found.", 404)
		return jsonify(ok=True)
	except ValueError as error:
		return api_error(str(error), 400)


@app.delete("/api/tracker/<int:entry_id>")
def delete_tracker_entry(entry_id):
	with database() as connection:
		user = current_user(connection)
		if not user or user["role"] != "developer":
			return api_error("A developer account is required.", 401)
		connection.execute("""
			DELETE FROM tracker_entries WHERE id = ? AND user_id = ?
		""", (entry_id, user["id"]))
	return jsonify(ok=True)


if __name__ == "__main__":
	app.run(debug=True)
