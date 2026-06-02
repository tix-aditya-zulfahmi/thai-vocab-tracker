#!/usr/bin/env python3
"""
Load example sentences + breakdowns from data/examples/*.json into the DB.

Each JSON file is a list of records keyed by vocab id:
  [
    {"id": 1,
     "thai": "ไปก่อนนะ",
     "roman": "bpai kòn ná",
     "arti": "Aku pergi duluan ya",
     "breakdown": [
        {"thai": "ไป",   "roman": "bpai", "arti": "pergi"},
        {"thai": "ก่อน", "roman": "kòn",  "arti": "duluan"},
        {"thai": "นะ",   "roman": "ná",   "arti": "partikel pelembut"}
     ]}
  ]

Idempotent: re-running upserts by vocab id. Safe to run repeatedly as batches land.
"""

import glob
import json
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "thai-vocab.db")
EX_DIR = os.path.join(HERE, "data", "examples")


def main():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    valid_ids = {r[0] for r in cur.execute("SELECT id FROM vocab")}

    files = sorted(glob.glob(os.path.join(EX_DIR, "*.json")))
    if not files:
        print(f"No example files in {EX_DIR}")
        return

    loaded, skipped = 0, 0
    for fp in files:
        records = json.load(open(fp, encoding="utf-8"))
        for rec in records:
            vid = rec["id"]
            if vid not in valid_ids:
                skipped += 1
                continue
            cur.execute(
                """INSERT INTO examples (vocab_id, thai, romanization, meaning, breakdown)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(vocab_id) DO UPDATE SET
                     thai=excluded.thai, romanization=excluded.romanization,
                     meaning=excluded.meaning, breakdown=excluded.breakdown""",
                (vid, rec["thai"], rec.get("roman"), rec.get("arti"),
                 json.dumps(rec.get("breakdown", []), ensure_ascii=False)),
            )
            loaded += 1
    con.commit()

    total = cur.execute("SELECT COUNT(*) FROM examples").fetchone()[0]
    vocab = cur.execute("SELECT COUNT(*) FROM vocab").fetchone()[0]
    con.close()
    print(f"Loaded/updated {loaded} examples (skipped {skipped} unknown ids).")
    print(f"Coverage: {total}/{vocab} vocab entries have an example.")


if __name__ == "__main__":
    main()
