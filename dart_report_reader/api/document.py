"""
dart_report_reader/api/document.py
공시서류 원문 파일 API (DS001 - document.xml)

v5 변경: ZIP 처리 후 dcmNo 추출까지 담당
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from typing import Optional

import requests

from .client import DartHttpClient, DartApiError

logger = logging.getLogger(__name__)


class DocumentApi:
    """공시서류 원문 ZIP 조회."""

    def __init__(self, client: DartHttpClient) -> None:
        self._client = client

    # ------------------------------------------------------------------

    def fetch_zip_info(self, rcept_no: str) -> dict:
        """
        document.xml ZIP 을 다운로드하고 파싱에 필요한 정보를 반환한다.

        Returns
        -------
        dict with keys:
            rcept_no  : str
            main_xml  : bytes   — 본문 XML ({rcept_no}.xml)
            dcm_no    : str     — 첫 번째 첨부 파일에서 추출한 문서번호
            all_files : list[str] — ZIP 내 전체 파일명
        """
        url = self._client._build_url("document", "xml", {"rcept_no": rcept_no})
        res = requests.get(url, timeout=self._client.config.timeout)

        if res.status_code != 200:
            raise DartApiError(f"HTTP {res.status_code}  (rcept_no={rcept_no})")

        return self._parse_zip(res.content, rcept_no)

    # ------------------------------------------------------------------

    @staticmethod
    def _parse_zip(raw: bytes, rcept_no: str) -> dict:
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                names = zf.namelist()

                # 본문 XML: {rcept_no}.xml
                main_name = next(
                    (n for n in names if re.match(rf'^{re.escape(rcept_no)}\.xml$', n)),
                    None
                )
                if main_name is None:
                    # 폴백: 가장 큰 파일
                    main_name = max(names, key=lambda n: zf.getinfo(n).file_size)

                main_xml = zf.read(main_name)

                # dcmNo: 첨부 파일명 {rcept_no}_{dcmNo}.xml 에서 추출
                dcm_no = ""
                for n in sorted(names):
                    m = re.match(rf'^{re.escape(rcept_no)}_(\d+)\.xml$', n)
                    if m:
                        dcm_no = m.group(1)
                        break

        except zipfile.BadZipFile as e:
            raise DartApiError(f"ZIP 파싱 실패 (rcept_no={rcept_no}): {e}") from e

        return {
            "rcept_no":  rcept_no,
            "main_xml":  main_xml,
            "dcm_no":    dcm_no,
            "all_files": names,
        }
