from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

# Ensure `app` package imports work when running this file directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.company_display_ai import keywords_to_stored_string
from app.community_display_ai import generate_display_fields_from_community
from app.database import SessionLocal
from app.models import Community


def main() -> None:
    db = SessionLocal()
    processed = 0
    updated = 0
    skipped = 0
    failed = 0
    failed_names: list[str] = []

    try:
        rows = list(db.scalars(select(Community).order_by(Community.created_at.desc())).all())
        print(f"[community-keywords] start total={len(rows)}", flush=True)

        for row in rows:
            processed += 1
            name = (row.name or "").strip() or "<unknown>"
            description = (row.description or "").strip()

            if not name and not description:
                skipped += 1
                print(f"[community-keywords] skip name={name} reason=empty_name_and_description", flush=True)
                continue

            try:
                parsed = generate_display_fields_from_community(name, description)
            except Exception as exc:
                failed += 1
                failed_names.append(name)
                print(f"[community-keywords] fail name={name} reason=ai_exception error={exc}", flush=True)
                continue

            if not parsed.get("success"):
                failed += 1
                failed_names.append(name)
                print(f"[community-keywords] fail name={name} reason=model_success_false", flush=True)
                continue

            keywords = list(parsed.get("keywords") or [])[:3]
            if len(keywords) < 3:
                failed += 1
                failed_names.append(name)
                print(
                    f"[community-keywords] fail name={name} reason=insufficient_keywords count={len(keywords)}",
                    flush=True,
                )
                continue

            row.keywords = keywords_to_stored_string(keywords) or None
            print(
                f"[community-keywords] prepared name={name} add_keywords_count={len(keywords)} keywords={row.keywords or ''}",
                flush=True,
            )
            try:
                db.commit()
                updated += 1
                print(f"[community-keywords] updated name={name}", flush=True)
            except IntegrityError as exc:
                db.rollback()
                failed += 1
                failed_names.append(name)
                print(f"[community-keywords] fail name={name} reason=db_integrity_error error={exc}", flush=True)

        print(
            f"[community-keywords] summary processed={processed} updated={updated} skipped={skipped} failed={failed}",
            flush=True,
        )
        if failed_names:
            print("[community-keywords] failed_names:", flush=True)
            for n in failed_names:
                print(f"- {n}", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()

