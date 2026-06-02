# Thai Vocabulary Tracker

A SQLite database + spaced-repetition logic for practicing Thai vocab, built from
`vocabulary-tracker.xlsx`. Designed as the data layer for a future practice web app.

## Files

| File | What it is |
|------|------------|
| `vocabulary-tracker.xlsx` | Original source. Hand-maintained study log (542 words, 6 phrases, 13 grammar notes). |
| `thai-vocab.db` | The SQLite database the web app reads/writes. **Source of truth for practice.** |
| `build_db.py` | Builds/refreshes `thai-vocab.db` from the spreadsheet. Idempotent. |
| `srs.py` | Spaced-repetition scoring. The web app calls `record_answer()` on each guess. |
| `load_examples.py` | Loads example sentences + breakdowns from `data/examples/*.json` into the DB. Idempotent. |
| `data/examples/` | Per-word example sentences (one JSON batch per file). One example for all 548 entries. |
| `webapp/` | Flask practice app (multiple-choice, examples, session summary). See `webapp/README.md`. |

## How practice works

- Two **directions**, tracked separately per word:
  - `th2id` — see the Thai script, guess the Indonesian meaning (reading)
  - `id2th` — see the meaning, recall the Thai word (production)
- **Leitner boxes 1..5** decide how often a word reappears:
  - Correct → box moves up (you see it less often).
  - Wrong → box drops to 1 (you see it every session until it sticks).
  - A word is **mastered** (drops out of the queue) at box 5 with 3 correct in a row.
- `next_due` is set from the box interval below. The queue shows words whose
  `next_due` has passed, hardest first.

| Box | Meaning | Days until due again |
|-----|---------|----------------------|
| 1 | just learned / recently wrong | 0 (same session) |
| 2 | | 1 |
| 3 | | 3 |
| 4 | | 7 |
| 5 | nearly mastered | 16 |

Intervals live in the `leitner_intervals` table, so you can tune them without code.

## Schema

- **`vocab`** — one row per word/phrase. `entry_type` = `word` | `phrase`.
  Columns: `thai`, `romanization`, `tone`, `meaning` (Indonesian), `category`,
  `context` (phrases), `legacy_frequency` (original study count, used as a
  tie-breaker so already-familiar words surface less), `first_learned_date`,
  `first_learned_source`, `notes`.
- **`review_state`** — one row per `(vocab_id, direction)`. Holds `box`,
  `correct_count`, `wrong_count`, `current_streak`, `total_seen`, `last_reviewed`,
  `next_due`, `is_mastered`.
- **`attempts`** — append-only log of every guess (`is_correct`, `box_before`,
  `box_after`, `response_ms`, `answered_at`). Lets you recompute any stat or chart
  progress over time.
- **`grammar_notes`** — the grammar reference sheet.
- **`leitner_intervals`** — box → interval-in-days lookup (tunable).
- **`examples`** — one example sentence per word: `thai`, `romanization`,
  `meaning` (Indonesian), and `breakdown` (JSON array of `{thai, roman, arti}`
  tokens). Loaded from `data/examples/` by `load_examples.py`.

### Views (for the app)

- **`v_due_today`** — words due now, hardest first. Drive the practice queue from this.
- **`v_progress`** — per-direction totals: count, mastered, in box 1, total correct/wrong.

## Using it from the web app

The whole answer flow is one function. Example (Python):

```python
import sqlite3, srs
con = sqlite3.connect("thai-vocab.db")

# pull the next card to show
card = srs.next_word(con, "th2id")          # (id, thai, roman, tone, meaning, category, box)

# user guesses -> record it (handles box move, next_due, mastery, and the log)
srs.record_answer(con, vocab_id=card[0], direction="th2id", is_correct=True, response_ms=1840)
```

For a JS/Node backend, port the same rule from `srs.py` (it is ~30 lines) or call
the Python directly. The logic: `correct → box=min(box+1,5), streak+1`;
`wrong → box=1, streak=0`; `next_due = today + interval[box]`;
`mastered = box==5 and streak>=3`.

## Rebuilding

`python3 build_db.py` refreshes vocab/phrase/grammar content from the spreadsheet
and adds review rows for any new words. It does **not** wipe `attempts` or
`review_state` progress, so it is safe to re-run after you add words to the xlsx.

Requires `openpyxl` (`pip install openpyxl`).
