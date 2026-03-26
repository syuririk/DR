"""
tests/test_vault.py
MarkdownBuilder 단위 테스트
"""

import pytest
from pathlib import Path

from dart_report_reader.config import ReportCode, SectionCode
from dart_report_reader.parser.section_parser import SectionParser, ParsedReport
from dart_report_reader.vault.md_builder import MarkdownBuilder
from tests.conftest import MOCK_DIVIDEND_ROWS, MOCK_EMPLOYEE_ROWS, MOCK_EXECUTIVE_ROWS


@pytest.fixture
def sample_report() -> ParsedReport:
    parser = SectionParser()
    raw = {
        SectionCode.DIVIDEND:  MOCK_DIVIDEND_ROWS,
        SectionCode.EMPLOYEE:  MOCK_EMPLOYEE_ROWS,
        SectionCode.EXECUTIVE: MOCK_EXECUTIVE_ROWS,
    }
    return parser.parse_report(
        corp_code="00126380",
        corp_name="삼성전자",
        bsns_year="2023",
        reprt_code=ReportCode.ANNUAL,
        reprt_label="사업보고서",
        rcept_no="20230308000001",
        raw_sections=raw,
    )


class TestMarkdownBuilder:

    def test_save_creates_file(self, config, sample_report):
        builder = MarkdownBuilder(config)
        path = builder.save(sample_report)

        assert path.exists()
        assert path.suffix == ".md"

    def test_save_path_structure(self, config, sample_report):
        """출력 경로: output_dir / corp_name / year_label.md"""
        builder = MarkdownBuilder(config)
        path = builder.save(sample_report)

        assert path.parent.name == "삼성전자"
        assert path.name == "2023_사업보고서.md"

    def test_md_contains_frontmatter(self, config, sample_report):
        builder = MarkdownBuilder(config)
        path = builder.save(sample_report)
        content = path.read_text(encoding="utf-8")

        assert "---" in content
        assert "corp_name: 삼성전자" in content
        assert "bsns_year: 2023" in content
        assert "tags:" in content

    def test_md_contains_title(self, config, sample_report):
        builder = MarkdownBuilder(config)
        path = builder.save(sample_report)
        content = path.read_text(encoding="utf-8")

        assert "# 삼성전자 2023 사업보고서" in content

    def test_md_contains_info_table(self, config, sample_report):
        builder = MarkdownBuilder(config)
        path = builder.save(sample_report)
        content = path.read_text(encoding="utf-8")

        assert "## 기본 정보" in content
        assert "20230308000001" in content

    def test_md_contains_section_headers(self, config, sample_report):
        builder = MarkdownBuilder(config)
        path = builder.save(sample_report)
        content = path.read_text(encoding="utf-8")

        assert "## 배당에 관한 사항" in content
        assert "## 직원 현황" in content
        assert "## 임원 현황" in content

    def test_md_contains_table_data(self, config, sample_report):
        builder = MarkdownBuilder(config)
        path = builder.save(sample_report)
        content = path.read_text(encoding="utf-8")

        # 배당 데이터
        assert "361" in content
        # 임원 데이터
        assert "이재용" in content

    def test_md_dart_link(self, config, sample_report):
        """접수번호가 DART 링크로 변환되어야 한다."""
        builder = MarkdownBuilder(config)
        path = builder.save(sample_report)
        content = path.read_text(encoding="utf-8")

        assert "dart.fss.or.kr" in content
        assert "20230308000001" in content

    def test_save_batch(self, config):
        """save_batch: 복수 보고서 일괄 저장."""
        parser = SectionParser()
        reports = []
        for year in ["2021", "2022", "2023"]:
            r = parser.parse_report(
                corp_code="00126380",
                corp_name="삼성전자",
                bsns_year=year,
                reprt_code=ReportCode.ANNUAL,
                reprt_label="사업보고서",
                rcept_no=f"{year}0101000001",
                raw_sections={SectionCode.DIVIDEND: MOCK_DIVIDEND_ROWS},
            )
            reports.append(r)

        builder = MarkdownBuilder(config)
        paths = builder.save_batch(reports)

        assert len(paths) == 3
        assert all(p.exists() for p in paths)

    def test_safe_filename_special_chars(self, config):
        """회사명에 특수문자가 있어도 저장되어야 한다."""
        parser = SectionParser()
        report = parser.parse_report(
            corp_code="12345678",
            corp_name='테스트/기업:회사',
            bsns_year="2023",
            reprt_code=ReportCode.ANNUAL,
            reprt_label="사업보고서",
            rcept_no="20230101000099",
            raw_sections={},
        )
        builder = MarkdownBuilder(config)
        path = builder.save(report)
        assert path.exists()
