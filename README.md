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
the map toggle and exact map clicks.

```bash
cd glimpse_tool_v2
uv sync                                       # once; pinned env from pyproject.toml
PORT=8010 .venv/bin/python backend/server.py  # http://127.0.0.1:8010
.venv/bin/python -m unittest discover -s backend/tests
```

## Layout

```
frontend/            the site: served as-is, no build step
  index.html home.js   home: pick a topic
  app.html app.js      the map, verdict, "how you compare", what would change it
  login.html auth.js   sign in, create account, forgot / reset password
  account.html account.js   my account: save cards, timeline, change password, delete account
  compare.html compare.js   compare two people: you, a save, or a typical person
  how.html             how it works: reading the map, close calls, the changes it suggests
  common.js            shared: theme, navigation, topic names, "?" tips
  style.css            shared by every page
backend/
  server.py            local server: API + frontend on one port
  api/index.py         HTTP routes
  api/auth.py          accounts, sessions, saved values
  api/db.py            SQLite locally, Postgres when DATABASE_URL is set
  api/mailer.py        sends password-reset emails (Resend)
  engine/              models, Rashomon sets, ECLIPSE lens; cached fits in precomputed/
  precompute.py        refits the models into engine/precomputed/ (needs pandas)
  tests/
  data/glimpse.db      created on first use; not committed or deployed
api/index.py         Vercel entry point; loads backend/api/index.py
```

## API

| Method | Path | |
|---|---|---|
| GET | `/api/datasets` | dataset list |
| GET | `/api/scene?dataset=&query=` | scene for a person in the data |
| POST | `/api/scene` | `{dataset, custom}` entered values, or `{dataset, point: [x, y]}` a map spot |
| GET | `/api/me` | the signed-in user, or `null` |
| POST | `/api/register`, `/api/login`, `/api/logout` | accounts (no email verification) |
| POST | `/api/people` | `{dataset, people: [{feature: value}, ...]}` predictions and map spots, no map (max 60) |
| GET | `/api/saved?dataset=` | the user's named saves for a dataset (all topics without `dataset`) |
| POST | `/api/saved/rename` | `{id, name}` |
| POST | `/api/saved` | `{dataset, name, values}`; replaces a save with the same name (max 50) |
| DELETE | `/api/saved?id=` | delete one save |
| GET | `/api/account` | email, member since, saves per topic |
| POST | `/api/account/password` | `{current, new}`; signs out other browsers |
| POST | `/api/account/delete` | `{password}`; removes the account and every save |
| POST | `/api/forgot` | `{email}`; emails a one-time reset link (1 hour) |
| POST | `/api/reset` | `{token, password}`; sets the new password and signs in |

## The map

The site draws a PCA map (`MAP_LENS = "pca"` in `backend/engine/cf_core.py`); set it to
`"eclipse"` and re-run `precompute.py` to go back to ECLIPSE. PCA ignores the model, so it shows
less of it (Diabetes 65% vs 99%, Breast cancer 76% vs 97%) and draws suggested changes on the
correct side of their line less often (Diabetes 55% vs 64%, Breast cancer 34% vs 43%). The
suggestions themselves are the same either way.

## How suggested changes work

- Every value has a rule: can't change, only up, only down, or free. The defaults lock each
  topic's `IMMUTABLE` values; people change any rule in "What can you change?" on the map page,
  and requests send them as `rules` (`{name: "fixed" | "up" | "down" | "free"}`).
- Values in the locked list per topic (`IMMUTABLE` in `backend/engine/cf_core.py`) never change
  unless the person unlocks them.
- Every other value stays within the lowest and highest seen in the data (widened to include
  where the person starts), so there are no negative counts or percentages over 100.
- Each model reports `quick_ok` (the quickest change flips it) and `safe_ok` (the safest change
  convinces every model that fits the data about as well). When one is false, the page says so
  instead of showing it. (On the old Credit topic the simple model never had a safe change:
  with the external risk score and account ages locked, nothing else convinced every model.)
- Each change also reports how much of it lands on the flat map (`quick_on_map`,
  `safe_on_map`); under 50% the page notes that the arrow may look short of the line.

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

**Reset emails.** "Forgot password" sends a one-time link by email. Set
`RESEND_API_KEY` (a free key from resend.com) and `MAIL_FROM` (an address on a domain
you have verified with Resend) in the Vercel project. Until then the live site says
reset by email isn't set up. Locally the link is printed in the server window.
`APP_URL` can pin the address used in the links.

Passwords are stored as scrypt hashes. Sessions are 30-day HttpOnly cookies (Secure
over HTTPS), and repeated failed sign-ins are throttled per email and per IP.

## Datasets

Pima diabetes and breast cancer (WDBC). Taiwan credit card default ("Credit card") is off
the site for now; its data and saved model are kept, so adding `"taiwan"` back to `APP_TOPICS`
brings it back. The topics are listed in `APP_TOPICS` in `backend/engine/cf_core.py`; each needs a saved
model in `backend/engine/precomputed/` (`uv run --with pandas python backend/precompute.py
<key>`, so the saved model uses the same pinned versions as the site).

FICO HELOC ("Credit") was taken off the site on 2026-10-14. Its two inquiry counts are
near-duplicates (r = 0.99), so the model's main direction was their difference, which
the map can't show: the map showed 40% of the model and drew suggested changes on the
correct side of the strictest model's line only 12% of the time. Dropping the duplicate
helped (47%) but the simple model still had no safe change for anyone. Taiwan scored
best of the remaining datasets; `testing/dataset_fit.py` compares them.

Heart disease (Statlog) was also checked. With honest locks (age, sex, chest-pain type, thal,
major vessels) a safe change exists for only 10% / 38% of people and the map draws changes
on the correct side 52% of the time; locking only age and sex scores well (60%, 100% / 100%)
but then suggests changing test results people can't change. Its category codes (chest-pain
type, thal, slope, ECG result) would also need one-hot encoding before it could be used.
