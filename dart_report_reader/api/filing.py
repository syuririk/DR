"""
dart_report_reader/api/filing.py
공시 목록 조회 API (DS001)
"""

from __future__ import annotations

from typing import Optional
from .client import DartHttpClient


class FilingApi:
    """
    공시 목록 조회.

    DART DS001 그룹 — 공시검색 API 래퍼.
    """

    def __init__(self, client: DartHttpClient) -> None:
        self._client = client

    # ------------------------------------------------------------------
    def list(
        self,
        corp_code: Optional[str] = None,
        bgn_de: Optional[str] = None,
        end_de: Optional[str] = None,
        pblntf_ty: str = "A",          # A=정기공시
        pblntf_detail_ty: Optional[str] = None,
        last_reprt_at: str = "Y",       # 최종보고서만
        page_no: int = 1,
        page_count: int = 40,
    ) -> list[dict]:
        """
        공시 목록을 반환한다.

        Parameters
        ----------
        corp_code : str, optional
            기업 고유번호.  None 이면 전체 기업.
        bgn_de : str
            검색 시작일 (YYYYMMDD).
        end_de : str
            검색 종료일 (YYYYMMDD).
        pblntf_ty : str
            공시 유형.  A=정기공시, B=주요사항, C=발행공시, D=지분공시.
        last_reprt_at : str
            Y=최종보고서만, N=정정 포함.
        """
        params: dict = {
            "pblntf_ty": pblntf_ty,
            "last_reprt_at": last_reprt_at,
            "page_no": str(page_no),
            "page_count": str(page_count),
        }
        if corp_code:
            params["corp_code"] = corp_code
        if bgn_de:
            params["bgn_de"] = bgn_de
        if end_de:
            params["end_de"] = end_de
        if pblntf_detail_ty:
            params["pblntf_detail_ty"] = pblntf_detail_ty

        data = self._client.get_json("list", params)
        return data.get("list", [])

    # ------------------------------------------------------------------
    def get_annual_reports(
        self,
        corp_code: str,
        start_year: int,
        end_year: int,
    ) -> list[dict]:
        """
        특정 기업의 연도 범위 내 사업보고서(11011) 목록을 반환한다.
        """
        results = self.list(
            corp_code=corp_code,
            bgn_de=f"{start_year}0101",
            end_de=f"{end_year}1231",
            pblntf_ty="A",
        )
        # 사업보고서만 필터
        return [r for r in results if r.get("report_nm", "").startswith("사업보고서")]
