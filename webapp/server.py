#!/usr/bin/env python3
"""
Thai vocab practice — Flask API + static web UI.

Multiple-choice practice on top of thai-vocab.db, reusing the Leitner SRS logic
in srs.py. Cards are picked "most due, hardest first"; a correct answer pushes a
word up its Leitner box (seen less often), a wrong answer drops it to box 1
(seen every session) until it masters out.

Run locally:
    pip install -r requirements.txt
    python3 server.py
    open http://127.0.0.1:5000

Deploy: it's a standard WSGI app (`app`). Point THAI_DB at the database file and
serve with gunicorn, e.g.  gunicorn -w 2 server:app
"""

import json
import os
import random
import sqlite3
import sys

from flask import Flask, jsonify, request, send_from_directory

# Reuse the SRS scoring + the DB that build_db.py produced (one dir up by default).
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import srs  # noqa: E402

DB_PATH = os.environ.get("THAI_DB", os.path.join(ROOT, "thai-vocab.db"))
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

DIRECTIONS = ("th2id", "id2th")
PROMPT_FIELD = {"th2id": "thai", "id2th": "meaning"}   # what the card shows
ANSWER_FIELD = {"th2id": "meaning", "id2th": "thai"}   # what the options show

app = Flask(__name__, static_folder=None)


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def build_options(con, target, direction):
    """Return 4 shuffled option dicts (1 correct + 3 distractors).

    Distractors prefer the same category so choices are plausible, and must have
    a display text distinct from the correct answer.
    """
    afield = ANSWER_FIELD[direction]
    correct_text = target[afield]
    chosen, seen_texts = [], {correct_text}

    # Pass 1: same category. Pass 2: anything. Both exclude the target + dup texts.
    for same_cat in (True, False):
        if len(chosen) >= 3:
            break
        q = f"""SELECT id, {afield} AS text FROM vocab
                WHERE id != ? AND {afield} IS NOT NULL AND {afield} != ''
                {"AND category = ?" if same_cat else ""}
                ORDER BY RANDOM() LIMIT 40"""
        params = [target["id"]] + ([target["category"]] if same_cat else [])
        for row in con.execute(q, params):
            if len(chosen) >= 3:
                break
            if row["text"] in seen_texts:
                continue
            seen_texts.add(row["text"])
            chosen.append({"vocab_id": row["id"], "text": row["text"]})

    options = chosen + [{"vocab_id": target["id"], "text": correct_text}]
    random.shuffle(options)
    return options


@app.route("/api/next")
def api_next():
    direction = request.args.get("direction", "th2id")
    if direction == "mixed":
        direction = random.choice(DIRECTIONS)
    if direction not in DIRECTIONS:
        return jsonify(error="bad direction"), 400

    con = db()
    row = srs.next_word(con, direction)  # (id, thai, roman, tone, meaning, category, box)
    if row is None:
        con.close()
        return jsonify(done=True, direction=direction)

    target = con.execute(
        "SELECT id, thai, romanization, tone, meaning, category, notes FROM vocab WHERE id=?",
        (row[0],),
    ).fetchone()
    options = build_options(con, target, direction)
    con.close()

    return jsonify(
        done=False,
        direction=direction,
        vocab_id=target["id"],
        prompt=target[PROMPT_FIELD[direction]],
        box=row[6],
        options=options,
    )


@app.route("/api/answer", methods=["POST"])
def api_answer():
    data = request.get_json(force=True)
    vocab_id = int(data["vocab_id"])
    direction = data["direction"]
    chosen_id = int(data["chosen_vocab_id"])
    response_ms = data.get("response_ms")
    if direction not in DIRECTIONS:
        return jsonify(error="bad direction"), 400

    is_correct = chosen_id == vocab_id
    con = db()
    state = srs.record_answer(con, vocab_id, direction, is_correct, response_ms)
    reveal = con.execute(
        "SELECT thai, romanization, tone, meaning, category, notes FROM vocab WHERE id=?",
        (vocab_id,),
    ).fetchone()
    ex_row = con.execute(
        "SELECT thai, romanization, meaning, breakdown FROM examples WHERE vocab_id=?",
        (vocab_id,),
    ).fetchone()
    con.close()

    example = None
    if ex_row:
        example = dict(ex_row)
        try:
            example["breakdown"] = json.loads(example["breakdown"] or "[]")
        except (ValueError, TypeError):
            example["breakdown"] = []

    return jsonify(
        is_correct=is_correct,
        correct_vocab_id=vocab_id,
        reveal=dict(reveal),
        example=example,
        state=state,
    )


@app.route("/api/progress")
def api_progress():
    con = db()
    prog = {r["direction"]: dict(r) for r in con.execute("SELECT * FROM v_progress")}
    due = {
        d: con.execute(
            """SELECT COUNT(*) FROM review_state
               WHERE direction=? AND is_mastered=0
                 AND (next_due IS NULL OR next_due <= date('now'))""",
            (d,),
        ).fetchone()[0]
        for d in DIRECTIONS
    }
    con.close()
    return jsonify(progress=prog, due=due)


@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(STATIC_DIR, path)


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        sys.exit(f"DB not found at {DB_PATH}. Run build_db.py first (one dir up).")
    # Default 5050: macOS uses port 5000 for AirPlay Receiver, which 403s.
    # HOST=127.0.0.1 (default) is localhost-only. Set HOST to your Tailscale IP
    # (100.x.y.z) to reach it from your phone over the tailnet, or 0.0.0.0 for all
    # interfaces. Debugger auto-disables when not on localhost (safer when exposed).
    host = os.environ.get("HOST", "127.0.0.1")
    debug = os.environ.get("DEBUG", "1" if host == "127.0.0.1" else "0") == "1"
    app.run(host=host, port=int(os.environ.get("PORT", 5050)), debug=debug)
