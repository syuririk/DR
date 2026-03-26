"""
dart_report_reader
==================
DART OpenAPI 정기보고서 파싱 & Obsidian Vault 생성 라이브러리.

Quick Start
-----------
>>> from dart_report_reader import DartReportReader, DartConfig
>>> cfg = DartConfig(
...     api_key="YOUR_API_KEY",
...     cache_dir="/content/cache",
...     output_dir="/content/vault",
... )
>>> reader = DartReportReader(cfg)
>>> reader.init()                         # 기업 코드 캐시 로드
>>> paths = reader.build_vault(
...     corp="삼성전자",
...     years=[2022, 2023],
...     reprt_codes=["11011"],
... )
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Union

from .config import DartConfig, ReportCode, SectionCode
from .api.client import DartHttpClient
from .api.filing import FilingApi
from .api.report import ReportApi
from .cache.corp_code import CorpCodeCache
from .parser.section_parser import SectionParser, ParsedReport
from .vault.md_builder import MarkdownBuilder

logger = logging.getLogger(__name__)

__version__ = "0.1.0"
__all__ = [
    "DartReportReader",
    "DartConfig",
    "ReportCode",
    "SectionCode",
    "ParsedReport",
]


class DartReportReader:
    """
    DART OpenAPI 정기보고서 읽기·파싱·Vault 생성 Facade.

    Parameters
    ----------
    config : DartConfig
        라이브러리 설정 객체.

    Examples
    --------
    기본 사용:

    >>> cfg = DartConfig(api_key="...", cache_dir="/cache", output_dir="/vault")
    >>> reader = DartReportReader(cfg)
    >>> reader.init()
    >>> paths = reader.build_vault("삼성전자", years=[2023])

    캐시 갱신:

    >>> reader.refresh_corp_cache()
    """

    def __init__(self, config: DartConfig) -> None:
        self.config = config
        self._client  = DartHttpClient(config)
        self._cache   = CorpCodeCache(config, self._client)
        self._filing  = FilingApi(self._client)
        self._report  = ReportApi(self._client)
        self._parser  = SectionParser()
        self._builder = MarkdownBuilder(config)

    # ------------------------------------------------------------------
    # 초기화
    # ------------------------------------------------------------------

    def init(self) -> None:
        """
        캐시를 로드한다 (캐시 없으면 자동 다운로드).
        라이브러리 사용 전 반드시 1회 호출해야 한다.
        """
        self._cache.load()
        logger.info("DartReportReader 초기화 완료 (기업 수: %d)", len(self._cache))

    def refresh_corp_cache(self) -> None:
        """
        DART 서버에서 기업 코드 최신 목록을 다운로드하고
        캐시를 덮어쓴다.
        """
        self._cache.refresh()

    # ------------------------------------------------------------------
    # 기업 정보
    # ------------------------------------------------------------------

    def resolve_corp(self, identifier: str) -> str:
        """
        회사명 / 종목코드 / corp_code → corp_code 변환.

        Examples
        --------
        >>> reader.resolve_corp("삼성전자")   # → "00126380"
        >>> reader.resolve_corp("005930")      # → "00126380"
        """
        return self._cache.resolve(identifier)

    def search_corp(self, keyword: str) -> list[dict]:
        """회사명에 keyword 가 포함된 기업 목록 반환."""
        return self._cache.search_name(keyword)

    # ------------------------------------------------------------------
    # 보고서 파싱
    # ------------------------------------------------------------------

    def fetch_report(
        self,
        corp: str,
        bsns_year: Union[int, str],
        reprt_code: str = ReportCode.ANNUAL,
        sections: Optional[list[str]] = None,
    ) -> ParsedReport:
        """
        단일 보고서를 조회·파싱하여 ParsedReport 를 반환한다.

        Parameters
        ----------
        corp : str
            회사명, 종목코드, 또는 corp_code.
        bsns_year : int | str
            사업연도.
        reprt_code : str
            보고서 코드 (ReportCode 상수).  기본값: 사업보고서(11011).
        sections : list[str], optional
            조회할 섹션 코드 목록.  None 이면 config.sections 사용.
        """
        corp_code = self._cache.resolve(corp)
        corp_info = self._cache.get_info(corp_code) or {}
        corp_name = corp_info.get("corp_name", corp_code)
        bsns_year = str(bsns_year)

        # 공시 목록에서 접수번호 조회
        rcept_no = self._get_rcept_no(corp_code, bsns_year, reprt_code)

        # 섹션 데이터 조회
        target_sections = sections or self.config.sections
        raw = self._report.fetch_all_sections(
            corp_code, bsns_year, reprt_code, target_sections
        )

        return self._parser.parse_report(
            corp_code=corp_code,
            corp_name=corp_name,
            bsns_year=bsns_year,
            reprt_code=reprt_code,
            reprt_label=ReportCode.label(reprt_code),
            rcept_no=rcept_no,
            raw_sections=raw,
        )

    # ------------------------------------------------------------------
    # Vault 생성
    # ------------------------------------------------------------------

    def build_vault(
        self,
        corp: str,
        years: list[int],
        reprt_codes: Optional[list[str]] = None,
        sections: Optional[list[str]] = None,
    ) -> list[Path]:
        """
        특정 기업의 여러 연도·보고서 종류를 일괄 처리하여
        Obsidian Vault (.md 파일)를 생성한다.

        Parameters
        ----------
        corp : str
            회사명, 종목코드, 또는 corp_code.
        years : list[int]
            처리할 사업연도 리스트.  예: [2021, 2022, 2023]
        reprt_codes : list[str], optional
            보고서 종류 코드 리스트.  기본값: [ReportCode.ANNUAL]
        sections : list[str], optional
            조회할 섹션.  None 이면 config.sections 전부.

        Returns
        -------
        list[Path]
            저장된 .md 파일 경로 리스트.
        """
        if reprt_codes is None:
            reprt_codes = [ReportCode.ANNUAL]

        saved_paths: list[Path] = []

        for year in years:
            for rcode in reprt_codes:
                logger.info(
                    "[%s] %d년 %s 처리 중...", corp, year, ReportCode.label(rcode)
                )
                try:
                    report = self.fetch_report(corp, year, rcode, sections)
                    path = self._builder.save(report)
                    saved_paths.append(path)
                except KeyError as e:
                    logger.warning("기업 조회 실패: %s", e)
                except Exception as e:
                    logger.error(
                        "[%s] %d %s 처리 실패: %s",
                        corp, year, ReportCode.label(rcode), e,
                    )

        return saved_paths

    def build_vault_multi(
        self,
        corps: list[str],
        years: list[int],
        reprt_codes: Optional[list[str]] = None,
        sections: Optional[list[str]] = None,
    ) -> dict[str, list[Path]]:
        """
        여러 기업을 일괄 처리한다.

        Returns
        -------
        dict[str, list[Path]]
            {corp_identifier: [저장된 파일 경로 리스트]}
        """
        result: dict[str, list[Path]] = {}
        for corp in corps:
            result[corp] = self.build_vault(corp, years, reprt_codes, sections)
        return result

    # ------------------------------------------------------------------
    # 내부 유틸
    # ------------------------------------------------------------------

    def _get_rcept_no(
        self, corp_code: str, bsns_year: str, reprt_code: str
    ) -> str:
        """공시 목록에서 해당 보고서의 접수번호를 반환한다."""
        label = ReportCode.label(reprt_code)
        filings = self._filing.list(
            corp_code=corp_code,
            bgn_de=f"{bsns_year}0101",
            end_de=f"{int(bsns_year)+1}0630",
            pblntf_ty="A",
        )
        for f in filings:
            if label in f.get("report_nm", ""):
                return f.get("rcept_no", "")
        return ""
