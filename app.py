# ═══════════════════════════════════════════════
#  CASEOPS BACKEND — Flask + SQLite
#  Replaces the browser localStorage in app.js with
#  a real shared database, so all 4 teams see the
#  same data instead of each browser having its own copy.
# ═══════════════════════════════════════════════

import os
import sqlite3
import json
import requests
from pathlib import Path
from flask import Flask, request, jsonify, g
from flask_cors import CORS

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "caseops.db"
SCHEMA_PATH = BASE_DIR / "schema.sql"

app = Flask(__name__)

# CORS — restrict this in production. By default we allow everything so
# local/office-LAN usage keeps working out of the box, but once this is
# reachable outside your LAN, set CASEOPS_CORS_ORIGIN to your frontend's
# actual origin, e.g.:
#   export CASEOPS_CORS_ORIGIN="http://192.168.1.50:8080"
CORS_ORIGIN = os.environ.get("CASEOPS_CORS_ORIGIN", "*")
CORS(app, origins=CORS_ORIGIN)

# Teams webhook — set this to the URL you get from the Teams Workflow
# ("When a Teams webhook request is received" trigger). Keep it as an
# env var, never hardcode/commit it — anyone with this URL can post to
# your channel.
#   export TEAMS_WEBHOOK_URL="https://prod-xx.westus.logic.azure.com/..."
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")


# ─── DB HELPERS ─────────────────────────────────
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        db.executescript(f.read())
    db.commit()
    db.close()


def row_to_dict(row):
    return dict(row) if row else None


# ─── CASES ──────────────────────────────────────

# Frontend sends the parsed Excel rows here (the `cleaned` array
# that app.js currently just does store.set('cases', cleaned) with).
# We UPSERT every row: insert new cases, update existing ones.
@app.route("/api/cases/bulk", methods=["POST"])
def upload_cases():
    rows = request.get_json(force=True)
    if not isinstance(rows, list):
        return jsonify({"error": "Expected a JSON array of case rows"}), 400

    db = get_db()
    params = []
    for r in rows:
        case_number = str(r.get("Case Number", "")).strip()
        if not case_number:
            continue

        params.append((
            case_number,
            r.get("Status", ""),
            r.get("Account Name: Account Name") or r.get("Account Name") or r.get("Account", "Unknown"),
            r.get("Case Owner: Full Name") or r.get("Case Owner", "Unknown"),
            _safe_int(r.get("Case Age(in number)") or r.get("Age")),
            r.get("Cases pending with", "Unknown"),
            r.get("Related Issue: Incident Number", ""),
            _safe_int(r.get("INC Age") or r.get("Incident Age")),
            r.get("INC Owner") or r.get("Incident owner", "—"),
            r.get("INC Owner Queue") or r.get("Incident Owner Queue", "—"),
            r.get("Server (UAT/PROD)", "Unknown"),
            r.get("Actual Delivery Date", ""),
            r.get("Next Update") or r.get("Next Update Date", ""),
            r.get("JIRA Ticket Status", ""),
            r.get("Latest Comments", ""),
            r.get("Latest Comments Modified By: Full Name", ""),
            r.get("Latest Comments Modified Date", ""),
            r.get("Client Email Last Sent Date and Time", ""),
            r.get("Email Last Sent Date and Time", ""),
            json.dumps(r),
        ))

    if not params:
        return jsonify({"upserted": 0})

    # executemany in one transaction — a single Excel sheet is 800+ rows,
    # and calling db.execute() per row (with a Python-level commit at the
    # end) is far slower than handing SQLite the whole batch at once.
    db.executemany(
        """
        INSERT INTO cases (
            case_number, status, account, owner, age, pending_with,
            inc, inc_age, inc_owner, inc_owner_queue, server,
            delivery_date, next_update, jira_status, latest_comment,
            modified_by, modified_date, email_last_sent, last_email_sent,
            raw_json, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(case_number) DO UPDATE SET
            status=excluded.status, account=excluded.account, owner=excluded.owner,
            age=excluded.age, pending_with=excluded.pending_with, inc=excluded.inc,
            inc_age=excluded.inc_age, inc_owner=excluded.inc_owner,
            inc_owner_queue=excluded.inc_owner_queue, server=excluded.server,
            delivery_date=excluded.delivery_date, next_update=excluded.next_update,
            jira_status=excluded.jira_status, latest_comment=excluded.latest_comment,
            modified_by=excluded.modified_by, modified_date=excluded.modified_date,
            email_last_sent=excluded.email_last_sent, last_email_sent=excluded.last_email_sent,
            raw_json=excluded.raw_json, updated_at=datetime('now')
        """,
        params,
    )

    db.commit()
    return jsonify({"upserted": len(params)})


def _safe_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


@app.route("/api/cases", methods=["GET"])
def get_cases():
    db = get_db()
    rows = db.execute("SELECT * FROM cases ORDER BY updated_at DESC").fetchall()
    cases = []
    for row in rows:
        d = row_to_dict(row)
        raw = json.loads(d.pop("raw_json") or "{}")
        # merge: raw excel columns first, then our normalized columns on top
        merged = {**raw, **d}
        cases.append(merged)
    return jsonify(cases)


@app.route("/api/cases/<case_number>", methods=["GET"])
def get_case(case_number):
    db = get_db()
    row = db.execute("SELECT * FROM cases WHERE case_number = ?", (case_number,)).fetchone()
    if not row:
        return jsonify({"error": "Case not found"}), 404
    d = row_to_dict(row)
    raw = json.loads(d.pop("raw_json") or "{}")
    return jsonify({**raw, **d})


# ─── NOTES ──────────────────────────────────────
@app.route("/api/cases/<case_number>/notes", methods=["GET"])
def get_notes(case_number):
    db = get_db()
    row = db.execute("SELECT notes FROM case_notes WHERE case_number = ?", (case_number,)).fetchone()
    return jsonify({"notes": row["notes"] if row else ""})


@app.route("/api/cases/<case_number>/notes", methods=["PUT"])
def set_notes(case_number):
    notes = request.get_json(force=True).get("notes", "")
    db = get_db()
    db.execute(
        """
        INSERT INTO case_notes (case_number, notes, updated_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(case_number) DO UPDATE SET notes=excluded.notes, updated_at=datetime('now')
        """,
        (case_number, notes),
    )
    db.commit()
    return jsonify({"ok": True})


# ─── PROMISES ───────────────────────────────────
@app.route("/api/cases/<case_number>/promises", methods=["GET"])
def get_promises(case_number):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM promises WHERE case_number = ? ORDER BY date ASC", (case_number,)
    ).fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/api/cases/<case_number>/promises", methods=["POST"])
def add_promise(case_number):
    body = request.get_json(force=True)
    db = get_db()
    cur = db.execute(
        "INSERT INTO promises (case_number, text, date, owner, done) VALUES (?, ?, ?, ?, 0)",
        (case_number, body["text"], body["date"], body.get("owner", "Us")),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid}), 201


@app.route("/api/promises/<int:promise_id>/done", methods=["PATCH"])
def mark_promise_done(promise_id):
    db = get_db()
    db.execute("UPDATE promises SET done = 1 WHERE id = ?", (promise_id,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/promises/<int:promise_id>", methods=["DELETE"])
def delete_promise(promise_id):
    db = get_db()
    db.execute("DELETE FROM promises WHERE id = ?", (promise_id,))
    db.commit()
    return jsonify({"ok": True})


# ─── EMAILS ─────────────────────────────────────
@app.route("/api/cases/<case_number>/emails", methods=["GET"])
def get_emails(case_number):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM emails WHERE case_number = ? ORDER BY timestamp ASC", (case_number,)
    ).fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/api/cases/<case_number>/emails", methods=["POST"])
def add_email(case_number):
    body = request.get_json(force=True)
    db = get_db()
    cur = db.execute(
        "INSERT INTO emails (case_number, subject, direction, delivery_date) VALUES (?, ?, ?, ?)",
        (case_number, body["subject"], body.get("direction", "sent"), body.get("deliveryDate", "")),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid}), 201


@app.route("/api/emails/<int:email_id>", methods=["DELETE"])
def delete_email(email_id):
    db = get_db()
    db.execute("DELETE FROM emails WHERE id = ?", (email_id,))
    db.commit()
    return jsonify({"ok": True})


# ─── BULK FETCH (so frontend doesn't call once per case) ──
@app.route("/api/promises", methods=["GET"])
def get_all_promises():
    db = get_db()
    rows = db.execute("SELECT * FROM promises ORDER BY date ASC").fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/api/emails", methods=["GET"])
def get_all_emails():
    db = get_db()
    rows = db.execute("SELECT * FROM emails ORDER BY timestamp ASC").fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/api/notes", methods=["GET"])
def get_all_notes():
    db = get_db()
    rows = db.execute("SELECT * FROM case_notes").fetchall()
    return jsonify({r["case_number"]: r["notes"] for r in rows})


# ─── WATCHLIST ──────────────────────────────────
@app.route("/api/watchlist", methods=["GET"])
def get_watchlist():
    db = get_db()
    rows = db.execute("SELECT * FROM watchlist ORDER BY starred_at ASC").fetchall()
    return jsonify([row_to_dict(r) for r in rows])


@app.route("/api/watchlist/<case_number>", methods=["POST"])
def star_case(case_number):
    note = request.get_json(silent=True) or {}
    db = get_db()
    db.execute(
        """
        INSERT INTO watchlist (case_number, note, starred_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(case_number) DO NOTHING
        """,
        (case_number, note.get("note", "")),
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/watchlist/<case_number>", methods=["DELETE"])
def unstar_case(case_number):
    db = get_db()
    db.execute("DELETE FROM watchlist WHERE case_number = ?", (case_number,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/watchlist/<case_number>/note", methods=["PUT"])
def update_watchlist_note(case_number):
    note = request.get_json(force=True).get("note", "")
    db = get_db()
    db.execute("UPDATE watchlist SET note = ? WHERE case_number = ?", (note, case_number))
    db.commit()
    return jsonify({"ok": True})


# ─── TEAMS DAILY SUMMARY ────────────────────────
def _build_daily_summary_text():
    db = get_db()
    open_cases = db.execute(
        "SELECT * FROM cases WHERE status IS NULL OR status != 'Closed'"
    ).fetchall()

    inc_open = [c for c in open_cases if c["inc"]]
    overdue_promises = db.execute(
        "SELECT * FROM promises WHERE done = 0 AND date(date) < date('now')"
    ).fetchall()
    due_today_promises = db.execute(
        "SELECT * FROM promises WHERE done = 0 AND date(date) = date('now')"
    ).fetchall()
    watch_rows = db.execute("SELECT * FROM watchlist").fetchall()

    lines = [f"**📋 CaseOps Daily Summary — {request.host}**", ""]
    lines.append(f"🗂️ Open cases: **{len(open_cases)}**")
    lines.append(f"🔥 Active INC cases: **{len(inc_open)}**")
    lines.append(f"⭐ Watchlist: **{len(watch_rows)}**")
    lines.append("")

    if overdue_promises:
        lines.append(f"🔴 **{len(overdue_promises)} overdue promise(s):**")
        for p in overdue_promises[:10]:
            lines.append(f"- Case {p['case_number']}: {p['text']} (was due {p['date']}, owner: {p['owner']})")
        if len(overdue_promises) > 10:
            lines.append(f"- ...and {len(overdue_promises) - 10} more")
        lines.append("")

    if due_today_promises:
        lines.append(f"🟡 **{len(due_today_promises)} promise(s) due today:**")
        for p in due_today_promises[:10]:
            lines.append(f"- Case {p['case_number']}: {p['text']} (owner: {p['owner']})")
        lines.append("")

    if not overdue_promises and not due_today_promises:
        lines.append("✅ No overdue or due-today promises.")

    return "\n\n".join(lines)


@app.route("/api/teams/send-daily", methods=["POST"])
def send_daily_to_teams():
    if not TEAMS_WEBHOOK_URL:
        return jsonify({"error": "TEAMS_WEBHOOK_URL is not set on the server. See README."}), 400

    text = _build_daily_summary_text()
    try:
        resp = requests.post(TEAMS_WEBHOOK_URL, json={"text": text}, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as e:
        return jsonify({"error": f"Teams webhook call failed: {e}"}), 502

    return jsonify({"ok": True})


# ─── HEALTH CHECK ───────────────────────────────
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    if not DB_PATH.exists():
        print("Database not found, creating it from schema.sql ...")
    init_db()  # safe to call every time — CREATE TABLE IF NOT EXISTS

    # Debug mode is OFF by default now — Flask's debugger lets anyone who
    # can reach this port execute arbitrary Python, which is fine on your
    # own laptop but not once this is reachable on the office LAN/internet.
    # For local dev, run: CASEOPS_DEBUG=1 python3 app.py
    debug_mode = os.environ.get("CASEOPS_DEBUG", "0") == "1"
    port = int(os.environ.get("CASEOPS_PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
