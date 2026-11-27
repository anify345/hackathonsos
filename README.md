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

Run the backend tests with:

```sh
python -m unittest discover -s tests -v
```
