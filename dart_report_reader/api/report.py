"""
dart_report_reader/api/report.py
정기보고서 항목별 API (DS002)
"""

from __future__ import annotations

import logging
from typing import Optional

from .client import DartHttpClient, DartApiError
from ..config import SectionCode

logger = logging.getLogger(__name__)

# 섹션 코드 → DART endpoint 매핑
_ENDPOINT_MAP: dict[str, str] = {
    SectionCode.CAPITAL:              "irdsSttus",
    SectionCode.DIVIDEND:             "alotMatter",
    SectionCode.TREASURY_STOCK:       "tesstkAcqsDspsSttus",
    SectionCode.MAJOR_HOLDER:         "hyslrSttus",
    SectionCode.MAJOR_HOLDER_CHANGE:  "hyslrChgSttus",
    SectionCode.MINOR_HOLDER:         "mrhlSttus",
    SectionCode.EXECUTIVE:            "exctvSttus",
    SectionCode.EMPLOYEE:             "empSttus",
    SectionCode.EXEC_PAY_APPROVAL:    "drctrAdtAllMendngSttusGmtsckConfmAmount",
    SectionCode.EXEC_PAY_ALL:         "hmvAuditAllSttus",
    SectionCode.EXEC_PAY_INDIVIDUAL:  "hmvAuditIndvdlBySttus",
    SectionCode.TOP5_PAY:             "indvdlByPay",
    SectionCode.OUTSIDE_DIRECTOR:     "outcmpnyMgmtrNmsttus",
    SectionCode.AUDIT_CONTRACT:       "adtServcCnclsSttus",
    SectionCode.NON_AUDIT_CONTRACT:   "accnutAdtorNonAdtServcCnclsSttus",
    SectionCode.STOCK_TOTAL:          "stockTotqySttus",
    SectionCode.BONDS:                "cprndNrdmpBlce",
    SectionCode.CP:                   "entrprsBilScritsNrdmpBlce",
    SectionCode.SHORT_BOND:           "shrtpdScitsNrdmpBlce",
    SectionCode.COND_CAPITAL:         "cndlCaplScritsNrdmpBlce",
    SectionCode.HYBRID:               "newCaplScritsNrdmpBlce",
    SectionCode.DEBT_ISSUANCE:        "detScritsIsuAcmslt",
    SectionCode.PUBLIC_FUND:          "pssrpCptalUseDtls",
    SectionCode.PRIVATE_FUND:         "prvsrpCptalUseDtls",
    SectionCode.INVESTMENT:           "otrCprInvstmntSttus",
}


class ReportApi:
    """
    정기보고서 항목별 API.

    각 섹션 코드에 해당하는 DART DS002 엔드포인트를 호출하고
    결과 list 를 반환한다.
    """

    def __init__(self, client: DartHttpClient) -> None:
        self._client = client

    # ------------------------------------------------------------------
    def fetch_section(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str,
        section_code: str,
    ) -> list[dict]:
        """
        단일 섹션 데이터를 조회한다.

        Parameters
        ----------
        corp_code : str
            기업 고유번호 (8자리).
        bsns_year : str
            사업연도 (예: "2023").
        reprt_code : str
            보고서 코드 (ReportCode 상수).
        section_code : str
            섹션 코드 (SectionCode 상수).

        Returns
        -------
        list[dict]
            항목 데이터 리스트.  데이터 없을 경우 빈 리스트.
        """
        endpoint = _ENDPOINT_MAP.get(section_code)
        if not endpoint:
            logger.warning("알 수 없는 섹션 코드: %s", section_code)
            return []

        params = {
            "corp_code":  corp_code,
            "bsns_year":  bsns_year,
            "reprt_code": reprt_code,
        }

        try:
            data = self._client.get_json(endpoint, params)
            return data.get("list", [])
        except DartApiError as e:
            # 데이터 없음(013) 등은 빈 리스트로 처리
            logger.debug("섹션 %s 데이터 없음: %s", section_code, e)
            return []
        except Exception as e:
            logger.error("섹션 %s 조회 실패: %s", section_code, e)
            return []

    # ------------------------------------------------------------------
    def fetch_all_sections(
        self,
        corp_code: str,
        bsns_year: str,
        reprt_code: str,
        sections: Optional[list[str]] = None,
    ) -> dict[str, list[dict]]:
        """
        여러 섹션을 한 번에 조회한다.

        Parameters
        ----------
        sections : list[str], optional
            조회할 섹션 코드 목록.  None 이면 SectionCode.all() 전부.

        Returns
        -------
        dict[str, list[dict]]
            {섹션코드: 데이터리스트}
        """
        if sections is None:
            sections = SectionCode.all()

        result: dict[str, list[dict]] = {}
        for sec in sections:
            rows = self.fetch_section(corp_code, bsns_year, reprt_code, sec)
            if rows:
                result[sec] = rows
            logger.debug("섹션 %s: %d 행", sec, len(rows))

        return result
