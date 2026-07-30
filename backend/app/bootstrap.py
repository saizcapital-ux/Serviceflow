"""Production bootstrap: seed demo data once, without dropping anything.

Run after ``alembic upgrade head`` on a fresh deploy:

    python -m app.bootstrap

Unlike ``python -m app.seed`` (which drops and recreates every table for a
clean dev slate), this is safe to run on every deploy: it inspects the
already-migrated database and only populates the demo tenant when no users
exist yet. On subsequent deploys it finds data and exits without touching it.
"""
from app.core.database import SessionLocal
from app.models import User
from app.seed import seed


def main() -> None:
    db = SessionLocal()
    try:
        already_seeded = db.query(User).first() is not None
    finally:
        db.close()

    if already_seeded:
        print("Bootstrap: users already present — skipping demo seed.")
        return

    print("Bootstrap: empty database — seeding demo tenant…")
    seed(reset_first=False)


if __name__ == "__main__":
    main()
