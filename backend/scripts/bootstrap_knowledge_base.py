from __future__ import annotations

from backend.database import SessionLocal, init_db
from backend.services.knowledge_bootstrap import bootstrap_default_documents


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        result = bootstrap_default_documents(db)
        print(result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
