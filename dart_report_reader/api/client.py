"""
dart_report_reader/api/client.py
DART OpenAPI HTTP 클라이언트
"""

from __future__ import annotations

import time
import logging
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import DartConfig

logger = logging.getLogger(__name__)

BASE_URL = "https://opendart.fss.or.kr/api"


class DartHttpClient:
    """
    DART OpenAPI HTTP 클라이언트.

    - 모든 요청에 crtfc_key 자동 주입
    - 설정된 retry 횟수만큼 재시도
    - JSON / XML / binary(ZIP) 세 가지 응답 타입 지원
    """

    def __init__(self, config: DartConfig) -> None:
        self.config = config
        self._session = self._build_session()

    # ------------------------------------------------------------------
    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry_strategy = Retry(
            total=self.config.retry,
            backoff_factor=1.0,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    # ------------------------------------------------------------------
    def _base_params(self, extra: Optional[dict] = None) -> dict:
        params = {"crtfc_key": self.config.api_key}
        if extra:
            params.update(extra)
        return params

    # ------------------------------------------------------------------
    def get_json(self, endpoint: str, params: Optional[dict] = None) -> dict[str, Any]:
        """JSON 응답 반환."""
        url = f"{BASE_URL}/{endpoint}.json"
        resp = self._session.get(
            url,
            params=self._base_params(params),
            timeout=self.config.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        self._check_status(data, url)
        return data

    def get_xml(self, endpoint: str, params: Optional[dict] = None) -> bytes:
        """XML/binary 응답 원본 bytes 반환."""
        url = f"{BASE_URL}/{endpoint}.xml"
        resp = self._session.get(
            url,
            params=self._base_params(params),
            timeout=self.config.timeout,
        )
        resp.raise_for_status()
        return resp.content

    def get_zip(self, endpoint: str, params: Optional[dict] = None) -> bytes:
        """ZIP binary 반환 (고유번호 목록 등)."""
        url = f"{BASE_URL}/{endpoint}.xml"
        resp = self._session.get(
            url,
            params=self._base_params(params),
            timeout=self.config.timeout,
        )
        resp.raise_for_status()
        return resp.content

    # ------------------------------------------------------------------
    @staticmethod
    def _check_status(data: dict, url: str) -> None:
        status = data.get("status", "")
        message = data.get("message", "")
        if status != "000":
            raise DartApiError(f"DART API 오류 [{status}] {message}  (url={url})")


class DartApiError(Exception):
    """DART API 비정상 응답 예외."""
    pass
