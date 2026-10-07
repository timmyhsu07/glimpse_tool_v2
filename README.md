# GLIMPSE

An interactive tool for seeing model multiplicity. For most datasets many
models fit the data equally well but disagree about individual people. GLIMPSE
puts that whole set of equally-good models on one 2D map (using the ECLIPSE
projection) so you can see who is a genuine close call and the smallest change
that would flip a prediction.

Pick a dataset and a map (simple, flexible, or both). Click a person, click any
empty spot to see exactly who would be there, or enter your own data. Signed-in
users can save the values they choose under a name and load them later.

## This repository

`glimpse_tool_v2` is the current working version of GLIMPSE, live at
https://glimpse-dev-hazel.vercel.app. It grew out of the original `glimpse_tool`
(commit `768ad79`) and adds the frontend/backend split, accounts, saved values,
the map toggle and exact map clicks. Research code that uses the same engine is
in `testing/`.

```bash
cd glimpse_tool_v2
uv sync                                       # once; pinned env from pyproject.toml
PORT=8010 .venv/bin/python backend/server.py  # http://127.0.0.1:8010
.venv/bin/python -m unittest discover -s backend/tests
```

## Layout

```
frontend/            the site: served as-is, no build step
  index.html app.js    the map
  login.html auth.js   sign in / create account
  style.css            shared by both pages
backend/
  server.py            local server: API + frontend on one port
  api/index.py         HTTP routes
  api/auth.py          accounts, sessions, saved values
  api/db.py            SQLite locally, Postgres when DATABASE_URL is set
  engine/              models, Rashomon sets, ECLIPSE lens; cached fits in precomputed/
  precompute.py        refits the models into engine/precomputed/ (needs pandas)
  tests/
  data/glimpse.db      created on first use; not committed or deployed
api/index.py         Vercel entry point; loads backend/api/index.py
testing/             research on the same engine (benchmark, tradeoff, write-ups)
```

## API

| Method | Path | |
|---|---|---|
| GET | `/api/datasets` | dataset list |
| GET | `/api/scene?dataset=&query=` | scene for a person in the data |
| POST | `/api/scene` | `{dataset, custom}` entered values, or `{dataset, point: [x, y]}` a map spot |
| GET | `/api/me` | the signed-in user, or `null` |
| POST | `/api/register`, `/api/login`, `/api/logout` | accounts (no email verification) |
| GET | `/api/saved?dataset=` | the user's named saves for a dataset, newest first |
| POST | `/api/saved` | `{dataset, name, values}`; replaces a save with the same name (max 50) |
| DELETE | `/api/saved?id=` | delete one save |

## Deploying to Vercel

Live at **https://glimpse-dev-hazel.vercel.app** (Vercel project `glimpse-dev`, separate
from the `glimpse-tool` site). `vercel.json` uses the Python preset: Vercel builds one
function from pyproject's entrypoint, `api/index.py`, which loads `backend/api/index.py`
and serves both the API and `frontend/`.

Accounts live in a Neon Postgres database (free plan, `glimpse-dev-db`) connected to the
project, which sets `DATABASE_URL`; the tables are created on first use. Without a
database the maps still work and sign-in reports that accounts are not set up.

```bash
vercel deploy --prod      # or push to main: the glimpse-dev project deploys from this repo
```

Passwords are stored as scrypt hashes. Sessions are 30-day HttpOnly cookies (Secure
over HTTPS), and repeated failed sign-ins are throttled per email and per IP.

## Datasets

Pima diabetes, FICO HELOC, breast cancer (WDBC).
