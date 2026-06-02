# Thai Vocab Practice — Web App

Multiple-choice practice on top of `../thai-vocab.db`, using the Leitner SRS in
`../srs.py`. Correct answers push a word up its box (seen less); wrong answers
drop it to box 1 (seen every session) until it masters out.

## Run locally

```bash
cd webapp
pip install -r requirements.txt
python3 server.py
```

Open http://127.0.0.1:5000 (set `PORT=5050` to use another port).

## How to use

- Top toggle picks the direction: **Thai → Arti**, **Arti → Thai**, or **Campur** (mixed).
- Each card shows a prompt and 4 choices. Click one (or press keys **1–4**).
- It grades instantly, reveals romanization / tone / notes, and updates the word's box.
- It also shows an **example sentence** for the word, with a word-by-word
  **breakdown** (Thai · romanization · Indonesian) so you see it used in context.
- Press **Enter** or **Space** (or tap **Lanjut**) for the next card.
- Stat strip: words due, mastered, plus this session's correct / wrong / streak.
- **Akhiri sesi** ends the session and shows a summary: cards done, accuracy,
  best streak, and the list of words you missed (to review). **Mulai sesi baru** resets.

All progress writes straight to `thai-vocab.db`, so it persists across sessions
and is shared with anything else reading that DB.

## Structure

```
webapp/
  server.py          Flask API + serves the UI
  static/
    index.html       page
    style.css        warm "temple paper" theme — cream bg, jade-teal primary,
                     marigold accent; Mitr + IBM Plex Sans Thai; mobile-friendly
    app.js           card flow + grading calls
  requirements.txt
```

API: `GET /api/next?direction=`, `POST /api/answer`, `GET /api/progress`.

## Deploy later (e.g. to practice on your phone)

It's a standard WSGI app. On any host (Render, Railway, Fly, a VPS):

```bash
pip install -r requirements.txt
THAI_DB=/path/to/thai-vocab.db gunicorn -w 2 -b 0.0.0.0:$PORT server:app
```

- `THAI_DB` points at the database file (defaults to `../thai-vocab.db`).
- Upload the `.db` alongside the app, or mount it on a persistent volume so your
  progress survives redeploys.
- For multi-device use later, the only stateful piece is that one SQLite file.
```
