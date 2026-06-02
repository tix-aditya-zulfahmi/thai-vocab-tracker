#!/usr/bin/env python3
"""
Spaced-repetition scoring for the Thai vocab tracker (Leitner boxes).

The web app calls record_answer() once per guess. It does three things atomically:
  1. logs the raw guess in `attempts`
  2. moves the word between Leitner boxes (correct -> up, wrong -> back to box 1)
  3. recomputes next_due from the box interval, and the mastered flag

Box logic
---------
  correct -> box = min(box + 1, 5); streak += 1
  wrong   -> box = 1;               streak = 0   (drops straight back so it
                                                  reappears every session)
  next_due = today + leitner_intervals[box] days
  is_mastered = (box == 5 and current_streak >= 3)  -> drops out of v_due_today

This file is runnable as a quick self-test:  python3 srs.py
"""

import sqlite3
from datetime import date, timedelta

MAX_BOX = 5
MASTERY_STREAK = 3  # consecutive correct answers at box 5 to count as "familiar"


def _intervals(con):
    return {b: d for b, d in con.execute("SELECT box, interval_days FROM leitner_intervals")}


def record_answer(con, vocab_id, direction, is_correct, response_ms=None, today=None):
    """Apply one guess. Returns the updated review_state row as a dict.

    con          : sqlite3.Connection (caller commits, or pass and commit here)
    direction    : 'th2id' or 'id2th'
    is_correct   : bool / 0|1
    response_ms  : optional latency for analytics
    today        : optional date override (for testing); defaults to date.today()
    """
    today = today or date.today()
    is_correct = 1 if is_correct else 0
    intervals = _intervals(con)

    row = con.execute(
        """SELECT box, correct_count, wrong_count, current_streak, total_seen
           FROM review_state WHERE vocab_id=? AND direction=?""",
        (vocab_id, direction),
    ).fetchone()
    if row is None:
        raise ValueError(f"no review_state for vocab_id={vocab_id} direction={direction}")
    box, correct, wrong, streak, seen = row
    box_before = box

    if is_correct:
        box = min(box + 1, MAX_BOX)
        correct += 1
        streak += 1
    else:
        box = 1
        wrong += 1
        streak = 0

    seen += 1
    next_due = (today + timedelta(days=intervals.get(box, 0))).isoformat()
    mastered = 1 if (box == MAX_BOX and streak >= MASTERY_STREAK) else 0

    con.execute(
        """UPDATE review_state
           SET box=?, correct_count=?, wrong_count=?, current_streak=?,
               total_seen=?, last_reviewed=?, next_due=?, is_mastered=?
           WHERE vocab_id=? AND direction=?""",
        (box, correct, wrong, streak, seen, today.isoformat(), next_due,
         mastered, vocab_id, direction),
    )
    con.execute(
        """INSERT INTO attempts
           (vocab_id, direction, is_correct, box_before, box_after, response_ms)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (vocab_id, direction, is_correct, box_before, box, response_ms),
    )
    con.commit()
    return {
        "vocab_id": vocab_id, "direction": direction, "box": box,
        "correct_count": correct, "wrong_count": wrong, "current_streak": streak,
        "total_seen": seen, "next_due": next_due, "is_mastered": bool(mastered),
    }


def next_word(con, direction, today=None):
    """Return the single most-due word for a direction, or None if all caught up."""
    today = (today or date.today()).isoformat()
    return con.execute(
        """SELECT v.id, v.thai, v.romanization, v.tone, v.meaning, v.category, r.box
           FROM review_state r JOIN vocab v ON v.id=r.vocab_id
           WHERE r.direction=? AND r.is_mastered=0
             AND (r.next_due IS NULL OR r.next_due<=?)
           ORDER BY r.box ASC, r.wrong_count DESC, v.legacy_frequency DESC
           LIMIT 1""",
        (direction, today),
    ).fetchone()


if __name__ == "__main__":
    # Self-test on an in-memory CLONE so the real DB is never touched:
    #   a wrong answer drops the word to box 1; 5 corrects in a row master it out.
    import os
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "thai-vocab.db")
    disk = sqlite3.connect(src)
    con = sqlite3.connect(":memory:")
    disk.backup(con)
    disk.close()

    vid = con.execute("SELECT id FROM vocab WHERE thai='นะ'").fetchone()[0]
    print("wrong ->", record_answer(con, vid, "th2id", False))
    for i in range(5):
        print(f"correct {i+1} ->", record_answer(con, vid, "th2id", True))
    con.close()
    print("(ran on in-memory clone, real DB unchanged)")
