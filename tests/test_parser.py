"""
tests/test_parser.py
SectionParser 단위 테스트
"""

import pytest

from dart_report_reader.config import SectionCode, ReportCode
from dart_report_reader.parser.section_parser import SectionParser, ReportSection, ParsedReport
from tests.conftest import MOCK_DIVIDEND_ROWS, MOCK_EMPLOYEE_ROWS, MOCK_EXECUTIVE_ROWS


@pytest.fixture
def parser() -> SectionParser:
    return SectionParser()


class TestSectionParser:

    def test_parse_section_basic(self, parser):
        section = parser.parse_section(SectionCode.DIVIDEND, MOCK_DIVIDEND_ROWS)
        assert section.code == SectionCode.DIVIDEND
        assert section.label == "배당에 관한 사항"
        assert len(section.rows) == 1
        assert not section.is_empty

    def test_parse_section_empty(self, parser):
        section = parser.parse_section(SectionCode.DIVIDEND, [])
        assert section.is_empty

    def test_clean_row_strips_whitespace(self, parser):
        raw = [{"nm": "  이재용  ", "ofcps": " 회장 "}]
        section = parser.parse_section(SectionCode.EXECUTIVE, raw)
        assert section.rows[0]["nm"] == "이재용"
        assert section.rows[0]["ofcps"] == "회장"

    def test_clean_row_dash_to_none(self, parser):
        raw = [{"thstrm": "-", "frmtrm": "1444"}]
        section = parser.parse_section(SectionCode.DIVIDEND, raw)
        assert section.rows[0]["thstrm"] is None
        assert section.rows[0]["frmtrm"] == "1444"

    def test_clean_row_empty_string_to_none(self, parser):
        raw = [{"jan_co": "", "feb_co": "100"}]
        section = parser.parse_section(SectionCode.EMPLOYEE, raw)
        assert section.rows[0]["jan_co"] is None

    def test_columns_auto_detected(self, parser):
        section = parser.parse_section(SectionCode.EXECUTIVE, MOCK_EXECUTIVE_ROWS)
        assert "nm" in section.columns
        assert "ofcps" in section.columns

    # ------------------------------------------------------------------
    # parse_report
    # ------------------------------------------------------------------

    def test_parse_report_structure(self, parser):
        raw = {
            SectionCode.DIVIDEND:  MOCK_DIVIDEND_ROWS,
            SectionCode.EMPLOYEE:  MOCK_EMPLOYEE_ROWS,
            SectionCode.EXECUTIVE: MOCK_EXECUTIVE_ROWS,
        }
        report = parser.parse_report(
            corp_code="00126380",
            corp_name="삼성전자",
            bsns_year="2023",
            reprt_code=ReportCode.ANNUAL,
            reprt_label=ReportCode.label(ReportCode.ANNUAL),
            rcept_no="20240101000001",
            raw_sections=raw,
        )

        assert isinstance(report, ParsedReport)
        assert report.corp_name == "삼성전자"
        assert report.bsns_year == "2023"
        assert report.reprt_label == "사업보고서"
        assert len(report.sections) == 3

    def test_parse_report_available_sections(self, parser):
        raw = {
            SectionCode.DIVIDEND: MOCK_DIVIDEND_ROWS,
            SectionCode.EMPLOYEE: [],                   # 빈 섹션
        }
        report = parser.parse_report(
            corp_code="00126380",
            corp_name="삼성전자",
            bsns_year="2023",
            reprt_code=ReportCode.ANNUAL,
            reprt_label="사업보고서",
            rcept_no="20240101000001",
            raw_sections=raw,
        )
        assert SectionCode.DIVIDEND in report.available_sections
        assert SectionCode.EMPLOYEE not in report.available_sections
