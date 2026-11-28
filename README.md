# Hackathon SOS

## Run locally

Install the Python dependency and start the Flask app:

```sh
python -m pip install -r requirements.txt
python main.py
```

Open `http://127.0.0.1:5000`. The app creates its SQLite database at
`instance/hackathonsos.sqlite3` on startup. Set `DATABASE_PATH` to use a
different database file. A persistent Flask session key is generated in
`instance/secret_key`; set `SECRET_KEY` to provide one explicitly.

## Admin panel

Admin access is not available through public sign-up. After updating the app,
restart it once so the database schema migration can enable the admin role.
Promote an existing account in the same SQLite database:

```sql
UPDATE users SET role = 'admin' WHERE name = 'your-existing-username';
```

Sign in at `/login-admin.html` with that account's existing credentials. The
admin panel can manage account roles, delete accounts, and delete pitches.
Accounts cannot delete themselves or remove the last admin. To change the
database role manually, use `developer` or `investor` instead of `admin`.

Run the backend tests with:

```sh
python -m unittest discover -s tests -v
```

## Demo unlocks

The unlock button is a prototype-only demo action. It does not process a
payment or move money; it reveals the sample contact details and enables
messaging within the demo. Do not treat demo pitches, identities, or amounts as
real investment opportunities.
