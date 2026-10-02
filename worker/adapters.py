from abc import ABC, abstractmethod
from urllib.parse import urlencode, urljoin

from bs4 import BeautifulSoup

from .utils import *


class SiteAdapter(ABC):
    @abstractmethod
    def supplier_urls(
        self,
        fetcher: Fetcher,
        query: str,
        limit: int,
    ) -> list[str]:
        raise NotImplementedError

    def parse(
        self,
        fetcher: Fetcher,
        url: str,
    ) -> dict | None:
        html = fetcher.get(url)

        if not html:
            return None

        text = page_text(html)
        inn = extract_inn(text)

        if not inn:
            return None

        soup = BeautifulSoup(html, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else None
        role, reason = detect_role(text)

        return {
            "inn": inn,
            "kpp": None,
            "name": title,
            "site": url,
            "region": inn[:2],
            "role": role,
            "role_reason": reason,
            "contacts": extract_contacts(text),
        }


class ZakupkiAdapter(SiteAdapter):
    SEARCH_URL = "https://zakupki.gov.ru/epz/contract/search/results.html"

    def supplier_urls(
        self,
        fetcher: Fetcher,
        query: str,
        limit: int,
    ) -> list[str]:
        url = self.SEARCH_URL + "?" + urlencode(
            {
                "searchString": query,
                "morphology": "on",
            }
        )

        html = fetcher.get(url)
        if not html:
            return []

        soup = BeautifulSoup(html, "html.parser")
        result: list[str] = []

        for link in soup.select("a[href]"):
            href = link.get("href")
            if not href:
                continue

            target = urljoin(url, href)

            if "/epz/contract/" not in target:
                continue

            if target not in result:
                result.append(target)

            if len(result) >= limit:
                break

        return result


ADAPTERS: dict[str, SiteAdapter] = {
    "zakupki.gov.ru": ZakupkiAdapter(),
}