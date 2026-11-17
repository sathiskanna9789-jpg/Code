# CaseOps — Changelog

## New files (backend — didn't exist before)
- **`app.py`** — Flask REST API server
- **`schema.sql`** — SQLite database schema (5 tables: cases, case_notes, promises, emails, watchlist)
- **`requirements.txt`** — Python dependencies (Flask, flask-cors)

## Modified files

### `app.js` — rewritten
1. **localStorage → shared backend**
   - Removed all `localStorage` reads/writes for cases, promises, emails, notes, watchlist.
   - Added `API` constant + `api()` fetch helper pointing to the Flask server.
   - Added `loadAllExtras()` — loads all promises/emails/notes/watchlist for every case in 4 API calls at boot, instead of one call per case.
   - All mutation functions (`addPromise`, `markPromiseDone`, `deletePromise`, `addEmail`, `deleteEmail`, `saveNotes`, `watchlist.star/unstar/updateNote`) now use **optimistic UI**: update the screen instantly, sync to the server in the background, and roll back automatically if the server call fails.
   - Excel upload flow now `POST`s parsed rows to `/api/cases/bulk`, then re-fetches from the server (so everyone sees the same data after any teammate uploads).

2. **Security — XSS fix**
   - Added `escapeHtml()` helper.
   - Applied it to every place free-text (Salesforce comments, promise text/owner, email subject, watchlist notes) gets written into the page, so a stray `<script>` in a case comment can no longer execute in the browser.

3. **Bug fix — chart drill-down losing the active filter**
   - "PENDING WITH" and "PROD vs UAT" chart click handlers were filtering from `allData` (everything) instead of `data` (the already-filtered set). Selecting an Account, then clicking a chart segment, showed every client's cases instead of staying within the selected account.
   - Fixed both handlers to filter from `data` instead of `allData`.

### `index.html` — cleaned up
- Removed the unused Choices.js CSS/JS `<script>`/`<link>` tags (dead weight — the excel-style dropdown filters replaced this library, but the old `<script>` tags were never removed).

### `style.css`
- Unchanged.

## Suggested commit message

```
Add shared Flask+SQLite backend, fix XSS risk, fix chart drill-down filter bug

- Replace localStorage with a Flask/SQLite backend so all 4 teams see
  the same promises/notes/emails/watchlist data instead of per-browser copies
- Add escapeHtml() and apply it to all user-generated text rendered via innerHTML
- Fix: Pending-With/Prod-vs-UAT chart clicks ignored the active Account filter
  and showed all clients' cases instead of the filtered subset
- Remove unused Choices.js library from index.html
```
