"""
dart_report_reader/api/client.py
DART OpenAPI HTTP 클라이언트

레거시 방식과 동일하게:
- URL 파라미터를 직접 문자열로 조립 (requests params= 미사용)
- ZIP 응답은 lxml.etree 로 파싱한 root Element 반환
- JSON 응답은 dict 반환, status != '000' 이면 DartApiError 발생
"""

from __future__ import annotations

import io
import logging
import zipfile
from typing import Any, Optional

import requests
from lxml import etree

from ..config import DartConfig

logger = logging.getLogger(__name__)

BASE_URL = "https://opendart.fss.or.kr/api"

# DART 공식 에러 코드표
ERR_DICT: dict[str, str] = {
    "010": "등록되지 않은 키입니다.",
    "011": "사용할 수 없는 키입니다. (일시적으로 사용 중지된 키)",
    "012": "접근할 수 없는 IP입니다.",
    "013": "조회된 데이터가 없습니다.",
    "014": "파일이 존재하지 않습니다.",
    "020": "요청 제한을 초과하였습니다. (일반적으로 20,000건 이상)",
    "021": "조회 가능한 회사 개수가 초과하였습니다. (최대 100건)",
    "100": "필드의 부적절한 값입니다.",
    "101": "부적절한 접근입니다.",
    "800": "시스템 점검으로 인한 서비스가 중지 중입니다.",
    "900": "정의되지 않은 오류가 발생하였습니다.",
    "901": "개인정보 보유기간 만료로 사용할 수 없는 키입니다.",
}


class DartApiError(Exception):
    """DART API 비정상 응답 예외."""
    pass


class DartHttpClient:
    """
    DART OpenAPI HTTP 클라이언트.

    레거시 코드의 getRequest / getZipRequest 를 클래스로 통합.
    - URL 파라미터를 직접 문자열로 조립 (레거시 방식 그대로)
    - crtfc_key 는 모든 요청에 자동 주입
    - ZIP 응답은 lxml.etree root Element 로 반환
    - JSON 응답은 status 검증 후 dict 반환
    """

    def __init__(self, config: DartConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # 내부: URL 조립
    # ------------------------------------------------------------------

    def _build_url(self, endpoint: str, ext: str, params: Optional[dict]) -> str:
        """
        레거시 getRequest 방식과 동일하게 URL 문자열을 직접 조립한다.

        예) https://opendart.fss.or.kr/api/list.json?crtfc_key=XXX&corp_code=00126380&
        """
        base = f"{BASE_URL}/{endpoint}.{ext}"
        # crtfc_key 를 맨 앞에 추가
        all_params: dict[str, str] = {"crtfc_key": self.config.api_key}
        if params:
            all_params.update(params)

        query = "?" + "".join(f"{k}={v}&" for k, v in all_params.items())
        url = base + query
        logger.debug("요청 URL: %s", url)
        return url

    # ------------------------------------------------------------------
    # 공개 메서드
    # ------------------------------------------------------------------

    def get_json(self, endpoint: str, params: Optional[dict] = None) -> dict[str, Any]:
        """
        JSON 엔드포인트 호출.

        Parameters
        ----------
        endpoint : str
            예) "list", "alotMatter", "exctvSttus"
        params : dict, optional
            추가 쿼리 파라미터 (crtfc_key 제외).

        Returns
        -------
        dict
            DART API 응답 전체 dict.

        Raises
        ------
        DartApiError
            HTTP 오류 또는 status != '000' 일 때.
        """
        url = self._build_url(endpoint, "json", params)
        res = requests.get(url, timeout=self.config.timeout)

        if res.status_code != 200:
            raise DartApiError(f"HTTP Error: {res.status_code}  (url={url})")

        data = res.json()
        status = data.get("status", "")
        if status != "000":
            msg = ERR_DICT.get(status, "API Error")
            raise DartApiError(f"[{status}] {msg}")

        return data

    def get_zip(self, endpoint: str, params: Optional[dict] = None) -> "etree._Element":
        """
        ZIP 엔드포인트 호출 → lxml etree root Element 반환.

        레거시 getZipRequest 와 동일한 방식:
        1. GET 요청으로 ZIP bytes 수신
        2. ZIP 내 .xml 파일 추출
        3. lxml.etree.fromstring 으로 파싱 (recover=True)

        Parameters
        ----------
        endpoint : str
            예) "corpCode"
        params : dict, optional
            추가 쿼리 파라미터.

        Returns
        -------
        lxml.etree._Element
            XML 루트 엘리먼트.

        Raises
        ------
        DartApiError
            HTTP 오류 또는 ZIP/XML 파싱 실패 시.
        """
        url = self._build_url(endpoint, "xml", params)
        res = requests.get(url, timeout=self.config.timeout)

        if res.status_code != 200:
            raise DartApiError(f"HTTP Error: {res.status_code}  (url={url})")

        # ZIP → XML bytes 추출
        try:
            with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
                xml_name = next(
                    (f for f in zf.namelist() if f.lower().endswith(".xml")), None
                )
                if xml_name is None:
                    raise DartApiError("ZIP 내에 XML 파일이 없습니다.")
                xml_bytes = zf.read(xml_name)
        except zipfile.BadZipFile as e:
            raise DartApiError(f"ZIP 파일 파싱 실패: {e}") from e

        # lxml 파싱 (recover=True — 레거시와 동일)
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(xml_bytes, parser)
        return root
