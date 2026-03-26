"""
tests/test_reader.py
DartReportReader (Facade) 통합 테스트
"""

from __future__ import annotations

import json
import io
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from dart_report_reader import DartReportReader, DartConfig, ReportCode, SectionCode
from dart_report_reader.api.client import DartApiError
from tests.conftest import (
    MOCK_CORPS,
    MOCK_DIVIDEND_ROWS,
    MOCK_EMPLOYEE_ROWS,
    MOCK_EXECUTIVE_ROWS,
    make_corp_code_root,
)

# ---------------------------------------------------------------------------
# 공통 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def reader_with_cache(config, corp_json_cache) -> DartReportReader:
    """캐시가 이미 존재하는 상태의 DartReportReader."""
    reader = DartReportReader(config)
    # 실제 HTTP 요청 없이 캐시 로드
    reader._client.get_zip = MagicMock(return_value=make_corp_code_root())
    reader.init()
    return reader


def _make_section_response(rows: list[dict]) -> dict:
    return {"status": "000", "message": "정상", "list": rows}


def _make_filing_response(corp_code: str, year: str, rcept_no: str) -> dict:
    return {
        "status": "000",
        "message": "정상",
        "list": [
            {
                "rcept_no": rcept_no,
                "corp_code": corp_code,
                "corp_name": "삼성전자",
                "report_nm": "사업보고서",
                "rcept_dt": f"{year}0310",
                "flr_nm": "삼성전자",
            }
        ],
    }


# ---------------------------------------------------------------------------
# init / 캐시
# ---------------------------------------------------------------------------

class TestInit:

    def test_init_loads_cache(self, config, corp_json_cache):
        reader = DartReportReader(config)
        reader._client.get_zip = MagicMock()
        reader.init()
        # 캐시 파일이 있으니 get_zip 은 호출되지 않아야 함
        reader._client.get_zip.assert_not_called()

    def test_init_downloads_when_no_cache(self, config):
        reader = DartReportReader(config)
        reader._client.get_zip = MagicMock(return_value=make_corp_code_root())
        reader.init()
        reader._client.get_zip.assert_called_once_with("corpCode")

    def test_refresh_corp_cache(self, config, corp_json_cache):
        reader = DartReportReader(config)
        reader._client.get_zip = MagicMock(return_value=make_corp_code_root())
        reader.init()

        reader._client.get_zip.reset_mock()
        reader.refresh_corp_cache()
        reader._client.get_zip.assert_called_once()


# ---------------------------------------------------------------------------
# resolve_corp / search_corp
# ---------------------------------------------------------------------------

class TestCorpLookup:

    def test_resolve_by_name(self, reader_with_cache):
        assert reader_with_cache.resolve_corp("삼성전자") == "00126380"

    def test_resolve_by_stock_code(self, reader_with_cache):
        assert reader_with_cache.resolve_corp("005930") == "00126380"

    def test_resolve_by_corp_code(self, reader_with_cache):
        assert reader_with_cache.resolve_corp("00126380") == "00126380"

    def test_resolve_unknown_raises(self, reader_with_cache):
        with pytest.raises(KeyError):
            reader_with_cache.resolve_corp("없는회사ZZZ")

    def test_search_corp_returns_list(self, reader_with_cache):
        results = reader_with_cache.search_corp("삼성")
        assert isinstance(results, list)
        assert any(r["corp_name"] == "삼성전자" for r in results)

    def test_search_corp_no_match(self, reader_with_cache):
        assert reader_with_cache.search_corp("없는키워드QQQQQ") == []


# ---------------------------------------------------------------------------
# fetch_report
# ---------------------------------------------------------------------------

class TestFetchReport:

    def _setup_mocks(self, reader: DartReportReader, rcept_no: str = "20230310000001") -> None:
        """filing + 각 섹션 API mock 설정."""
        reader._client.get_json = MagicMock(side_effect=self._json_side_effect(rcept_no))

    @staticmethod
    def _json_side_effect(rcept_no: str):
        def side_effect(endpoint, params=None):
            if endpoint == "list":
                return _make_filing_response("00126380", "2023", rcept_no)
            # 배당
            if endpoint == "alotMatter":
                return _make_section_response(MOCK_DIVIDEND_ROWS)
            # 직원
            if endpoint == "empSttus":
                return _make_section_response(MOCK_EMPLOYEE_ROWS)
            # 임원
            if endpoint == "exctvSttus":
                return _make_section_response(MOCK_EXECUTIVE_ROWS)
            # 나머지 섹션은 빈 데이터 반환 (status 013 처럼 처리)
            raise DartApiError("[013] 조회된 데이터가 없습니다.")
        return side_effect

    def test_fetch_report_returns_parsed_report(self, reader_with_cache):
        self._setup_mocks(reader_with_cache)
        report = reader_with_cache.fetch_report(
            "삼성전자", 2023, ReportCode.ANNUAL,
            sections=[SectionCode.DIVIDEND, SectionCode.EMPLOYEE, SectionCode.EXECUTIVE],
        )
        assert report.corp_name == "삼성전자"
        assert report.bsns_year == "2023"
        assert report.reprt_label == "사업보고서"
        assert report.rcept_no == "20230310000001"

    def test_fetch_report_sections_populated(self, reader_with_cache):
        self._setup_mocks(reader_with_cache)
        report = reader_with_cache.fetch_report(
            "삼성전자", 2023, ReportCode.ANNUAL,
            sections=[SectionCode.DIVIDEND, SectionCode.EMPLOYEE, SectionCode.EXECUTIVE],
        )
        assert SectionCode.DIVIDEND in report.available_sections
        assert SectionCode.EMPLOYEE in report.available_sections
        assert SectionCode.EXECUTIVE in report.available_sections

    def test_fetch_report_by_stock_code(self, reader_with_cache):
        self._setup_mocks(reader_with_cache)
        report = reader_with_cache.fetch_report(
            "005930", 2023, ReportCode.ANNUAL,
            sections=[SectionCode.DIVIDEND],
        )
        assert report.corp_code == "00126380"

    def test_fetch_report_empty_sections_skipped(self, reader_with_cache):
        """데이터 없는 섹션은 available_sections 에 포함되지 않는다."""
        self._setup_mocks(reader_with_cache)
        report = reader_with_cache.fetch_report(
            "삼성전자", 2023, ReportCode.ANNUAL,
            sections=[SectionCode.DIVIDEND, SectionCode.BONDS],  # BONDS → DartApiError
        )
        assert SectionCode.DIVIDEND in report.available_sections
        assert SectionCode.BONDS not in report.available_sections

    def test_fetch_report_year_as_string(self, reader_with_cache):
        self._setup_mocks(reader_with_cache)
        report = reader_with_cache.fetch_report(
            "삼성전자", "2023", ReportCode.ANNUAL,
            sections=[SectionCode.DIVIDEND],
        )
        assert report.bsns_year == "2023"


# ---------------------------------------------------------------------------
# build_vault
# ---------------------------------------------------------------------------

class TestBuildVault:

    def _mock_fetch(self, reader: DartReportReader, corp_name="삼성전자"):
        """fetch_report 를 Mock 으로 교체."""
        from dart_report_reader.parser.section_parser import SectionParser
        parser = SectionParser()

        def fake_fetch(corp, bsns_year, reprt_code=ReportCode.ANNUAL, sections=None):
            return parser.parse_report(
                corp_code="00126380",
                corp_name=corp_name,
                bsns_year=str(bsns_year),
                reprt_code=reprt_code,
                reprt_label=ReportCode.label(reprt_code),
                rcept_no=f"{bsns_year}0101000001",
                raw_sections={SectionCode.DIVIDEND: MOCK_DIVIDEND_ROWS},
            )

        reader.fetch_report = MagicMock(side_effect=fake_fetch)

    def test_build_vault_creates_md_files(self, reader_with_cache, config):
        self._mock_fetch(reader_with_cache)
        paths = reader_with_cache.build_vault("삼성전자", years=[2022, 2023])

        assert len(paths) == 2
        assert all(p.exists() for p in paths)
        assert all(p.suffix == ".md" for p in paths)

    def test_build_vault_multiple_report_codes(self, reader_with_cache):
        self._mock_fetch(reader_with_cache)
        paths = reader_with_cache.build_vault(
            "삼성전자",
            years=[2023],
            reprt_codes=[ReportCode.ANNUAL, ReportCode.HALF_YEAR],
        )
        assert len(paths) == 2

    def test_build_vault_multi_corp(self, reader_with_cache):
        self._mock_fetch(reader_with_cache)
        result = reader_with_cache.build_vault_multi(
            corps=["삼성전자", "현대자동차"],
            years=[2023],
        )
        assert "삼성전자" in result
        assert "현대자동차" in result
        assert len(result["삼성전자"]) == 1
        assert len(result["현대자동차"]) == 1

    def test_build_vault_skips_on_error(self, reader_with_cache):
        """fetch_report 실패 시 건너뛰고 나머지는 처리한다."""
        from dart_report_reader.parser.section_parser import SectionParser
        parser = SectionParser()
        call_count = 0

        def fake_fetch(corp, bsns_year, reprt_code=ReportCode.ANNUAL, sections=None):
            nonlocal call_count
            call_count += 1
            if bsns_year == 2022:
                raise Exception("API 오류 시뮬레이션")
            return parser.parse_report(
                corp_code="00126380",
                corp_name="삼성전자",
                bsns_year=str(bsns_year),
                reprt_code=reprt_code,
                reprt_label="사업보고서",
                rcept_no="20230101000001",
                raw_sections={SectionCode.DIVIDEND: MOCK_DIVIDEND_ROWS},
            )

        reader_with_cache.fetch_report = MagicMock(side_effect=fake_fetch)
        paths = reader_with_cache.build_vault("삼성전자", years=[2022, 2023])

        # 2023 년만 성공
        assert len(paths) == 1
        assert "2023" in str(paths[0])

    def test_build_vault_output_dir_structure(self, reader_with_cache, config):
        self._mock_fetch(reader_with_cache)
        paths = reader_with_cache.build_vault("삼성전자", years=[2023])

        path = paths[0]
        # output_dir / 삼성전자 / 2023_사업보고서.md
        assert path.parent.parent == config.output_dir
        assert path.parent.name == "삼성전자"
        assert path.name == "2023_사업보고서.md"
