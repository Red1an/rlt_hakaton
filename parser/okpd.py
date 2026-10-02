import json
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from database import OKPDModel

CLASSIFIER_PATH = Path(__file__).resolve().parent / "data" / "okpd2.json"


def load_classifier(session: Session) -> int:
    rows = [{"code": code, "name": name} for code, name in json.loads(CLASSIFIER_PATH.read_text(encoding="utf-8"))]
    stmt = pg_insert(OKPDModel).values(rows)
    session.execute(
        stmt.on_conflict_do_update(index_elements=[OKPDModel.code], set_={"name": stmt.excluded.name})
    )
    return len(rows)


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from database import database

    database.init()
    with database.session() as session:
        print(f"Справочник ОКПД2: {load_classifier(session)} кодов")