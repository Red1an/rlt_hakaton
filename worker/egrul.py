import json
from .utils import *


def egrul(client: httpx.Client, inn: str) -> dict | None:
    path = CACHE_DIR / "egrul" / f"{inn}.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    try:
        response = client.post(
            EGRUL_URL,
            data={"query": inn},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        response.raise_for_status()

        payload = response.json()

        if "t" not in payload:
            return None

        response = client.get(
            f"{EGRUL_URL}search-result/{payload['t']}"
        )
        response.raise_for_status()

        rows = response.json().get("rows", [])

    except httpx.HTTPError:
        return None

    row = next(
        (row for row in rows if row.get("i") == inn),
        None,
    )

    if not row:
        return None

    result = {
        "name": row.get("c") or row.get("n"),
        "ogrn": row.get("o"),
        "kpp": row.get("p"),
        "region_name": row.get("rn"),
        "terminated": row.get("e"),
    }

    path.write_text(
        json.dumps(result, ensure_ascii=False),
        encoding="utf-8",
    )

    return result


def verify_company(
    client: httpx.Client,
    company: dict,
) -> str | None:
    record = egrul(client, company["inn"])

    if not record:
        return "не найдена в ЕГРЮЛ"

    if record["terminated"]:
        return f"деятельность прекращена: {record['terminated']}"

    company.update(
        name=record["name"],
        kpp=record["kpp"],
        ogrn=record["ogrn"],
        region=(
            record["kpp"][:2]
            if record["kpp"]
            else company["region"]
        ),
        region_name=record["region_name"],
    )

    if company["region"] not in ALLOWED_REGIONS:
        return f"регион: {record['region_name']}"

    return None