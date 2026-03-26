"""
dart_report_reader/api/document.py
공시서류 원문 파일 API (DS001 - document.xml)

DART document.xml 엔드포인트는 rcept_no 로 ZIP을 반환한다.
ZIP 안에는 1~3개의 XML 파일이 들어 있다:
  - {rcept_no}.xml          : 본문 (사업보고서 전체)
  - {rcept_no}_NNNNN.xml    : 첨부(감사보고서 등)
"""

from __future__ import annotations

import io
import logging
import zipfile
from typing import Optional

from lxml import etree

from .client import DartHttpClient, DartApiError

logger = logging.getLogger(__name__)


class DocumentApi:
    """
    공시서류 원문 XML 조회.

    rcept_no(접수번호)로 ZIP을 받아 lxml etree Element 목록으로 반환한다.
    """

    def __init__(self, client: DartHttpClient) -> None:
        self._client = client

    # ------------------------------------------------------------------

    def fetch_xml_roots(self, rcept_no: str) -> list[etree._Element]:
        """
        rcept_no 로 document.xml 을 요청하고
        ZIP 안의 모든 XML 파일을 파싱해 root Element 목록을 반환한다.

        Parameters
        ----------
        rcept_no : str
            공시 접수번호 (14자리, 예: "20240312000736").

        Returns
        -------
        list[etree._Element]
            XML 파일별 root Element 목록.
            첫 번째 원소가 본문(사업보고서), 이후는 첨부 파일.
        """
        url = self._client._build_url("document", "xml", {"rcept_no": rcept_no})
        import requests
        res = requests.get(url, timeout=self._client.config.timeout)

        if res.status_code != 200:
            raise DartApiError(f"HTTP Error: {res.status_code}  (rcept_no={rcept_no})")

        roots = self._parse_zip_bytes(res.content, rcept_no)
        logger.info("rcept_no=%s — XML 파일 %d개 파싱 완료", rcept_no, len(roots))
        return roots

    def fetch_main_xml(self, rcept_no: str) -> etree._Element:
        """
        본문 XML(첫 번째 파일)의 root Element만 반환한다.
        """
        roots = self.fetch_xml_roots(rcept_no)
        if not roots:
            raise DartApiError(f"ZIP 안에 XML 파일이 없습니다. (rcept_no={rcept_no})")
        return roots[0]

    # ------------------------------------------------------------------

    @staticmethod
    def _parse_zip_bytes(
        raw: bytes, rcept_no: str
    ) -> list[etree._Element]:
        """ZIP bytes → XML root Element 목록."""
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                xml_names = sorted(
                    n for n in zf.namelist() if n.lower().endswith(".xml")
                )
                if not xml_names:
                    raise DartApiError(
                        f"ZIP 안에 XML 파일이 없습니다. (rcept_no={rcept_no})"
                    )

                roots = []
                lxml_parser = etree.XMLParser(recover=True)
                for name in xml_names:
                    xml_bytes = zf.read(name)
                    root = etree.fromstring(xml_bytes, lxml_parser)
                    roots.append(root)
                    logger.debug("파싱: %s", name)

        except zipfile.BadZipFile as e:
            raise DartApiError(
                f"ZIP 파일 파싱 실패 (rcept_no={rcept_no}): {e}"
            ) from e

        return roots
