# CaseOps Backend (Flask + SQLite)

This is a shared backend for your CaseOps tool. Data that used to live in
`localStorage` (promises, notes, emails, watchlist, cases) is now saved in
**one central database** — so all 4 team members see the same data no
matter which browser they open it in.

## 1. Setup (one-time)

```bash
cd caseops-backend
pip install -r requirements.txt
python3 app.py
```

This will automatically create the `caseops.db` (SQLite file), and the
server will run at `http://<your-ip>:5000` — any laptop/desktop on the
office network can access it (as long as it's on the same wifi/LAN).

> Before going to production, remove `debug=True`, and use a real WSGI
> server like `gunicorn` instead of `python3 app.py`.

### Env vars (new)

| Var | Default | What it does |
|---|---|---|
| `CASEOPS_DEBUG` | off | Set to `1` to turn on Flask debug mode (for local dev only; keep it off when exposing it on the office LAN) |
| `CASEOPS_PORT` | `5000` | Server port |
| `CASEOPS_CORS_ORIGIN` | `*` (all) | For production, restrict this to your frontend's actual origin (e.g. `http://192.168.1.50:8080`) |

## 2. API Endpoints

| Method | Path | What it does |
|---|---|---|
| POST | `/api/cases/bulk` | Send the parsed Excel rows as an array — it will insert or update (upsert) them |
| GET | `/api/cases` | Returns all cases |
| GET | `/api/cases/<case_number>` | Get a single case |
| GET/PUT | `/api/cases/<case_number>/notes` | Internal notes |
| GET/POST | `/api/cases/<case_number>/promises` | Promise tracker |
| PATCH | `/api/promises/<id>/done` | Mark a promise as done |
| DELETE | `/api/promises/<id>` | Delete a promise |
| GET/POST | `/api/cases/<case_number>/emails` | Email log |
| DELETE | `/api/emails/<id>` | Delete an email |
| GET | `/api/watchlist` | All starred cases |
| POST/DELETE | `/api/watchlist/<case_number>` | Star / unstar |
| PUT | `/api/watchlist/<case_number>/note` | Update a watchlist note |

## 3. Frontend (app.js) integration — what needs to change

The current `store` object (a localStorage wrapper) needs to be replaced
with async fetch calls. Example — instead of `store.setCase` and
`store.getCase`:

```javascript
const API = "http://<server-ip>:5000/api";

async function saveNotes() {
  if (!activeDrawerCase) return;
  await fetch(`${API}/cases/${activeDrawerCase}/notes`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ notes: document.getElementById('caseNotes').value })
  });
}

async function getPromises(caseNum) {
  const res = await fetch(`${API}/cases/${caseNum}/promises`);
  return res.ok ? await res.json() : [];
}
```

The same pattern applies to `addPromise`, `addEmail`, `toggleStar`, etc —
all of these need to become `fetch` calls. For the Excel upload part, as
soon as `extractTable()` runs, send that `cleaned` array to
`POST /api/cases/bulk`, then fetch fresh data from `GET /api/cases` and
re-render.

**This is a fairly large rewrite** (everything needs to become
`async/await`, since fetch calls are asynchronous). Once you say you're
ready, I'll do a full edit of `app.js` to use this — after that you can
run and test it locally.

## 4. Next steps (later, not urgent)

- **Salesforce API integration** — to remove the daily manual Excel
  download, `/api/cases/bulk` could be called automatically by a
  scheduled script (cron / APScheduler) that fetches directly from the
  Salesforce REST API.
- **Auth** — if this gets deployed outside the office LAN, add some
  basic login/token support.
- **Deploy** — this could be hosted on a small AWS EC2 instance
  (matches your AWS learning) — `gunicorn` + `nginx`.
