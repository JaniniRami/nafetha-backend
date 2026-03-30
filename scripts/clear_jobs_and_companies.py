"""Delete all rows from jobs and companies tables."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import SessionLocal
from app.models import ScrapedCompany, ScrapedJob


def main() -> None:
    db = SessionLocal()
    try:
        deleted_jobs = db.query(ScrapedJob).delete(synchronize_session=False)
        deleted_companies = db.query(ScrapedCompany).delete(synchronize_session=False)
        db.commit()
        print(f"Deleted jobs: {deleted_jobs}")
        print(f"Deleted companies: {deleted_companies}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
