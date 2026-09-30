"""Back up and remove duplicate/rehearsal cases from an explicit demo database."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3


def question_key(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold().rstrip(".!? ")


def prepare(database: Path, *, apply: bool = False) -> dict:
    database = database.resolve(strict=True)
    with sqlite3.connect(database) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=10000")
        rows = db.execute("""SELECT c.*,
            (SELECT COUNT(*) FROM advisories a WHERE a.source_case_id=c.id) AS publication_count,
            (SELECT COUNT(*) FROM reviews r WHERE r.case_id=c.id) AS review_count
            FROM cases c""").fetchall()
        groups = defaultdict(list)
        remove = set()
        for row in rows:
            text = question_key(row["question"])
            # Known judge/browser rehearsal markers; real unique questions stay.
            if text.startswith("judge rehearsal") or re.search(r"\bref [a-z0-9]+$", text):
                remove.add(row["id"])
            else:
                groups[(row["owner_id"], row["field_id"], text)].append(row)
        for group in groups.values():
            keep = max(group, key=lambda row: (
                row["provider"] == "Google Gemini API", row["publication_count"],
                row["review_count"], row["created_at"], row["id"],
            ))
            remove.update(row["id"] for row in group if row["id"] != keep["id"])
        report = {"before": len(rows), "after": len(rows) - len(remove), "removed_case_ids": sorted(remove), "applied": apply, "backup": None}
        if not apply or not remove:
            return report
        backup_dir = database.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = backup_dir / f"{database.stem}-before-pitch-{timestamp}.sqlite3"
        with sqlite3.connect(backup) as destination:
            db.backup(destination)
        db.execute("BEGIN IMMEDIATE")
        # Avoid applying a stale cleanup plan if the app received a new case.
        current = {tuple(row) for row in db.execute("""SELECT c.id, c.version,
            (SELECT COUNT(*) FROM advisories a WHERE a.source_case_id=c.id),
            (SELECT COUNT(*) FROM reviews r WHERE r.case_id=c.id) FROM cases c""")}
        if current != {(row["id"], row["version"], row["publication_count"], row["review_count"]) for row in rows}:
            raise RuntimeError("Case history changed; run the cleanup again.")
        for case_id in sorted(remove):
            db.execute("DELETE FROM exchange_receipts WHERE advisory_id IN (SELECT id FROM advisories WHERE source_case_id=?)", (case_id,))
            db.execute("DELETE FROM advisories WHERE source_case_id=?", (case_id,))
            db.execute("DELETE FROM reviews WHERE case_id=?", (case_id,))
            db.execute("DELETE FROM case_messages WHERE case_id=?", (case_id,))
            db.execute("DELETE FROM cases WHERE id=?", (case_id,))
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Cleanup would leave broken references.")
        report["backup"] = str(backup)
        return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Delete the planned records after saving a SQLite backup.")
    args = parser.parse_args()
    print(json.dumps(prepare(args.database, apply=args.apply), indent=2))


if __name__ == "__main__":
    main()
