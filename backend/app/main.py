import os
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, jsonify, request, session
from supabase import create_client
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ["FLASK_SECRET_KEY"]

# Use the service-role key ONLY on the backend. Never expose it to the frontend.
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


# ---------- helpers ----------
def login_required(role=None):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                return jsonify(error="Login required"), 401
            if role and session.get("role") != role:
                return jsonify(error=f"Only {role}s can do this"), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def missing_fields(data, required):
    return [f for f in required if not str(data.get(f, "")).strip()]


# ---------- auth ----------
@app.post("/signup")
def signup():
    data = request.get_json(force=True)
    required = ["username", "password", "email", "phone", "role"]
    missing = missing_fields(data, required)
    if missing:
        return jsonify(error=f"Missing: {', '.join(missing)}"), 400
    if data["role"] not in ("investor", "developer"):
        return jsonify(error="role must be 'investor' or 'developer'"), 400

    existing = (
        supabase.table("users")
        .select("id")
        .or_(f"username.eq.{data['username']},email.eq.{data['email']}")
        .execute()
    )
    if existing.data:
        return jsonify(error="Username or email already taken"), 409

    res = supabase.table("users").insert({
        "role": data["role"],
        "username": data["username"],
        "password_hash": generate_password_hash(data["password"]),
        "email": data["email"],
        "phone": data["phone"],
    }).execute()
    user = res.data[0]
    return jsonify(message="Signed up", id=user["id"]), 201


@app.post("/login")
def login():
    data = request.get_json(force=True)
    missing = missing_fields(data, ["username", "password"])
    if missing:
        return jsonify(error=f"Missing: {', '.join(missing)}"), 400

    res = (
        supabase.table("users")
        .select("*")
        .eq("username", data["username"])
        .limit(1)
        .execute()
    )
    if not res.data or not check_password_hash(res.data[0]["password_hash"], data["password"]):
        return jsonify(error="Invalid username or password"), 401

    user = res.data[0]
    session["user_id"] = user["id"]
    session["role"] = user["role"]
    return jsonify(message="Logged in", role=user["role"])


@app.post("/logout")
def logout():
    session.clear()
    return jsonify(message="Logged out")


# ---------- investor: deal criteria ----------
@app.post("/criteria")
@login_required(role="investor")
def add_criteria():
    data = request.get_json(force=True)
    if missing_fields(data, ["sector"]):
        return jsonify(error="sector is required"), 400

    res = supabase.table("deal_criteria").insert({
        "investor_id": session["user_id"],
        "sector": data["sector"],
        "min_amount": data.get("min_amount"),
        "max_amount": data.get("max_amount"),
    }).execute()
    return jsonify(res.data[0]), 201


@app.get("/criteria")
@login_required(role="investor")
def my_criteria():
    res = supabase.table("deal_criteria").select("*").eq("investor_id", session["user_id"]).execute()
    return jsonify(res.data)


# ---------- developer: pitch your idea ----------
@app.post("/pitches")
@login_required(role="developer")
def create_pitch():
    data = request.get_json(force=True)
    required = ["title", "category", "problem", "solution", "fund_ask", "equity_offered"]
    missing = missing_fields(data, required)
    if missing:
        return jsonify(error=f"Missing: {', '.join(missing)}"), 400

    res = supabase.table("pitches").insert({
        "developer_id": session["user_id"],
        "title": data["title"],
        "category": data["category"],
        "problem": data["problem"],
        "solution": data["solution"],
        "fund_ask": data["fund_ask"],
        "equity_offered": data["equity_offered"],
        "creation_link": data.get("creation_link") or None,  # optional
    }).execute()
    return jsonify(res.data[0]), 201


@app.get("/pitches")
@login_required()
def list_pitches():
    """Anyone logged in can browse. Investors can filter: /pitches?category=fintech&max_ask=50000"""
    q = supabase.table("pitches").select("*")
    if request.args.get("category"):
        q = q.eq("category", request.args["category"])
    if request.args.get("max_ask"):
        q = q.lte("fund_ask", request.args["max_ask"])
    return jsonify(q.order("created_at", desc=True).execute().data)


@app.get("/pitches/matches")
@login_required(role="investor")
def matching_pitches():
    """Pitches that match the investor's saved deal criteria (sector + amount)."""
    criteria = (
        supabase.table("deal_criteria").select("*").eq("investor_id", session["user_id"]).execute().data
    )
    matches = {}
    for c in criteria:
        q = supabase.table("pitches").select("*").eq("category", c["sector"])
        if c.get("max_amount") is not None:
            q = q.lte("fund_ask", c["max_amount"])
        if c.get("min_amount") is not None:
            q = q.gte("fund_ask", c["min_amount"])
        for p in q.execute().data:
            matches[p["id"]] = p
    return jsonify(list(matches.values()))


# ---------- messages ----------
@app.post("/messages")
@login_required()
def send_message():
    data = request.get_json(force=True)
    missing = missing_fields(data, ["receiver_id", "body"])
    if missing:
        return jsonify(error=f"Missing: {', '.join(missing)}"), 400

    res = supabase.table("messages").insert({
        "sender_id": session["user_id"],
        "receiver_id": data["receiver_id"],
        "pitch_id": data.get("pitch_id"),
        "body": data["body"],
    }).execute()
    return jsonify(res.data[0]), 201


@app.get("/messages")
@login_required()
def inbox():
    uid = session["user_id"]
    res = (
        supabase.table("messages")
        .select("*")
        .or_(f"sender_id.eq.{uid},receiver_id.eq.{uid}")
        .order("created_at", desc=True)
        .execute()
    )
    return jsonify(res.data)


if __name__ == "__main__":
    app.run(debug=True)
