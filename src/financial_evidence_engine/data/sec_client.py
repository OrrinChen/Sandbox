"""Small SEC EDGAR client for public submissions and company facts endpoints."""

from __future__ import annotations

import gzip
import json
import zlib
from typing import Callable, Dict, Optional
from urllib.request import Request, urlopen


Headers = Dict[str, str]
Transport = Callable[[str, Headers], object]


class SecClient:
    """Fetch SEC submissions and XBRL company facts with a required User-Agent."""

    def __init__(
        self,
        user_agent: str,
        submissions_base_url: str = "https://data.sec.gov/submissions/",
        companyfacts_base_url: str = "https://data.sec.gov/api/xbrl/companyfacts/",
        transport: Optional[Transport] = None,
    ):
        if not user_agent or not user_agent.strip():
            raise ValueError("SEC user_agent is required")
        self.user_agent = user_agent.strip()
        self.submissions_base_url = submissions_base_url.rstrip("/") + "/"
        self.companyfacts_base_url = companyfacts_base_url.rstrip("/") + "/"
        self.transport = transport or _default_json_transport

    def fetch_submissions(self, cik: str) -> object:
        url = f"{self.submissions_base_url}CIK{_normalize_cik(cik)}.json"
        return self.transport(url, self._headers())

    def fetch_companyfacts(self, cik: str) -> object:
        url = f"{self.companyfacts_base_url}CIK{_normalize_cik(cik)}.json"
        return self.transport(url, self._headers())

    def _headers(self) -> Headers:
        return {"User-Agent": self.user_agent, "Accept-Encoding": "gzip, deflate"}


def _normalize_cik(cik: str) -> str:
    digits = "".join(character for character in str(cik) if character.isdigit())
    if not digits:
        raise ValueError("CIK must contain digits")
    return digits.zfill(10)


def _default_json_transport(url: str, headers: Headers) -> object:
    request = Request(url, headers=headers)
    with urlopen(request, timeout=30) as response:
        body = response.read()
        encoding = response.headers.get("Content-Encoding", "").lower()
        if encoding == "gzip":
            body = gzip.decompress(body)
        elif encoding == "deflate":
            body = zlib.decompress(body)
        return json.loads(body.decode("utf-8"))
