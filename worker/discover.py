from .utils import *
from .adapters import *
from .egrul import *

def discover(
    query: str,
    limit: int,
    known_inns: set[str],
    refresh: bool = False,
) -> list[dict]:
    companies: list[dict] = []
    seen: set[str] = set()

    with httpx.Client(
        headers=HEADERS,
        timeout=15,
        follow_redirects=True,
    ) as client:
        fetcher = Fetcher(client, refresh)

        for adapter in ADAPTERS.values():
            urls = adapter.supplier_urls(
                fetcher,
                query,
                limit,
            )

            for url in urls:
                company = adapter.parse(fetcher, url)

                if not company:
                    continue

                inn = company["inn"]

                if inn in known_inns or inn in seen:
                    continue

                seen.add(inn)

                error = verify_company(client, company)
                if error:
                    print(f"{inn}: {error}")
                    continue

                companies.append(company)

    return companies