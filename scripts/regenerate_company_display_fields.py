from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

# Ensure `app` package imports work when running this file directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.company_display_ai import generate_display_fields_from_about, keywords_to_stored_string
from app.database import SessionLocal
from app.models import ScrapedCompany


def main() -> None:
    db = SessionLocal()
    processed = 0
    updated = 0
    skipped = 0
    failed = 0
    failed_titles: list[str] = []

    try:
        rows = list(db.scalars(select(ScrapedCompany).order_by(ScrapedCompany.scraped_at.desc())).all())
        print(f"[companies-ai] start total={len(rows)}", flush=True)

        for row in rows:
            processed += 1
            title = (row.company_name or "").strip() or "<unknown>"
            about = (row.about_us or "").strip()

            if not about:
                skipped += 1
                print(f"[companies-ai] skip title={title} reason=missing_about_us", flush=True)
                continue

            try:
                parsed = generate_display_fields_from_about(about)
            except Exception as exc:
                failed += 1
                failed_titles.append(title)
                print(f"[companies-ai] fail title={title} reason=ai_exception error={exc}", flush=True)
                continue

            if not parsed.get("success"):
                failed += 1
                failed_titles.append(title)
                print(f"[companies-ai] fail title={title} reason=model_success_false", flush=True)
                continue

            description = (parsed.get("description") or "").strip()
            keywords = list(parsed.get("keywords") or [])[:3]
            keywords_str = keywords_to_stored_string(keywords) or None

            row.displayed_description = description or None
            row.displayed_keywords = keywords_str
            print(
                f"[companies-ai] prepared title={title} "
                f"add_keywords_count={len(keywords)} keywords={keywords_str or ''}",
                flush=True,
            )

            try:
                db.commit()
                updated += 1
                print(f"[companies-ai] updated title={title}", flush=True)
            except IntegrityError as exc:
                db.rollback()
                failed += 1
                failed_titles.append(title)
                print(f"[companies-ai] fail title={title} reason=db_integrity_error error={exc}", flush=True)

        print(
            f"[companies-ai] summary processed={processed} updated={updated} skipped={skipped} failed={failed}",
            flush=True,
        )
        if failed_titles:
            print("[companies-ai] failed_titles:", flush=True)
            for name in failed_titles:
                print(f"- {name}", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()

