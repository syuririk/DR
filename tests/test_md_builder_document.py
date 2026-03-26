"""
tests/test_md_builder_document.py
MarkdownBuilder — ParsedDocument 저장 및 배치 ID 폴더 구조 테스트
"""

from __future__ import annotations

import re
import pytest
from pathlib import Path
from lxml import etree

from dart_report_reader.config import DartConfig, SectionCode, ReportCode
from dart_report_reader.parser.document_parser import DocumentParser, ParsedDocument
from dart_report_reader.parser.section_parser import SectionParser
from dart_report_reader.vault.md_builder import MarkdownBuilder, new_batch_id
from tests.conftest import MOCK_DIVIDEND_ROWS


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def make_mini_xml(corp_name: str = "삼성전자주식회사") -> etree._Element:
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<DOCUMENT>
  <DOCUMENT-NAME>사업보고서</DOCUMENT-NAME>
  <COMPANY-NAME AREGCIK="00126380">{corp_name}</COMPANY-NAME>
  <BODY>
    <TR><TU AUNIT="PERIODFROM" AUNITVALUE="20230101">2023-01-01</TU></TR>
    <TR><TU AUNIT="PERIODTO"   AUNITVALUE="20231231">2023-12-31</TU></TR>
    <SECTION-1>
      <TITLE ATOC="Y" ATOCID="9" AASSOCNOTE="D-0-2-0-0">II. 사업의 내용</TITLE>
      <LIBRARY>
        <SECTION-2>
          <TITLE ATOC="Y" ATOCID="10">1. 사업의 개요</TITLE>
          <P>사업 개요 내용입니다.</P>
        </SECTION-2>
        <SECTION-2>
          <TITLE ATOC="Y" ATOCID="16">7. 기타 참고사항</TITLE>
          <P>기타 참고 내용.</P>
          <TABLE>
            <TBODY>
              <TR><TD>구분</TD><TD>2023년</TD></TR>
              <TR><TD>특허등록</TD><TD>244731건</TD></TR>
            </TBODY>
          </TABLE>
        </SECTION-2>
      </LIBRARY>
    </SECTION-1>
    <SECTION-1>
      <TITLE ATOC="Y" ATOCID="17">III. 재무에 관한 사항</TITLE>
      <SECTION-2>
        <TITLE ATOC="Y" ATOCID="18">1. 요약재무정보</TITLE>
        <P>재무 내용.</P>
      </SECTION-2>
    </SECTION-1>
  </BODY>
</DOCUMENT>"""
    parser = etree.XMLParser(recover=True)
    return etree.fromstring(xml.encode("utf-8"), parser)


def make_doc(corp_name: str = "삼성전자주식회사", rcept_no: str = "20240312000736") -> ParsedDocument:
    root = make_mini_xml(corp_name)
    doc  = DocumentParser().parse(root)
    doc.rcept_no = rcept_no
    return doc


def make_report(corp_name: str = "삼성전자", bsns_year: str = "2023") -> object:
    parser = SectionParser()
    return parser.parse_report(
        corp_code="00126380", corp_name=corp_name,
        bsns_year=bsns_year, reprt_code=ReportCode.ANNUAL,
        reprt_label="사업보고서", rcept_no="20240312000736",
        raw_sections={SectionCode.DIVIDEND: MOCK_DIVIDEND_ROWS},
    )


# ---------------------------------------------------------------------------
# new_batch_id
# ---------------------------------------------------------------------------

class TestNewBatchId:

    def test_format(self):
        bid = new_batch_id()
        assert re.match(r"^\d{8}_\d{6}_[0-9a-f]{4}$", bid), f"형식 불일치: {bid}"

    def test_uniqueness(self):
        ids = {new_batch_id() for _ in range(20)}
        assert len(ids) == 20


# ---------------------------------------------------------------------------
# ParsedDocument 저장
# ---------------------------------------------------------------------------

class TestSaveDocument:

    def test_creates_file(self, config):
        builder = MarkdownBuilder(config)
        doc  = make_doc()
        path = builder.save_document(doc)
        assert path.exists()
        assert path.suffix == ".md"

    def test_path_structure_no_batch(self, config):
        """batch_id 없으면: output_dir / corp_name / rcept_no_doctype.md"""
        builder = MarkdownBuilder(config)
        doc  = make_doc(corp_name="삼성전자주식회사", rcept_no="20240312000736")
        path = builder.save_document(doc)
        assert path.parent.name == "삼성전자주식회사"
        assert "20240312000736" in path.name

    def test_path_structure_with_batch(self, config):
        """batch_id 있으면: output_dir / batch_id / corp_name_rcept_no_doctype.md"""
        builder  = MarkdownBuilder(config)
        doc      = make_doc(corp_name="삼성전자주식회사", rcept_no="20240312000736")
        batch_id = "20240312_153045_a3f2"
        path     = builder.save_document(doc, batch_id=batch_id)
        assert path.parent.name == batch_id
        assert "삼성전자주식회사" in path.name
        assert "20240312000736" in path.name

    def test_frontmatter_present(self, config):
        builder = MarkdownBuilder(config)
        doc  = make_doc()
        path = builder.save_document(doc)
        content = path.read_text(encoding="utf-8")
        assert "---" in content
        assert "corp_name:" in content
        assert "rcept_no:" in content
        assert "tags:" in content

    def test_info_table_present(self, config):
        builder = MarkdownBuilder(config)
        path    = builder.save_document(make_doc())
        content = path.read_text(encoding="utf-8")
        assert "## 기본 정보" in content
        assert "dart.fss.or.kr" in content

    def test_all_sections_in_file(self, config):
        builder = MarkdownBuilder(config)
        path    = builder.save_document(make_doc())
        content = path.read_text(encoding="utf-8")
        assert "II. 사업의 내용" in content
        assert "7. 기타 참고사항" in content
        assert "III. 재무에 관한 사항" in content

    def test_section_filter(self, config):
        """section_filter 지정 시 해당 섹션만 포함된다."""
        builder = MarkdownBuilder(config)
        path    = builder.save_document(
            make_doc(), section_filter=["사업의 내용"]
        )
        content = path.read_text(encoding="utf-8")
        assert "II. 사업의 내용" in content
        assert "III. 재무에 관한 사항" not in content

    def test_section_filter_sub(self, config):
        """하위 섹션 키워드로도 필터링 가능하다."""
        builder = MarkdownBuilder(config)
        path    = builder.save_document(
            make_doc(), section_filter=["기타 참고사항"]
        )
        content = path.read_text(encoding="utf-8")
        assert "기타 참고사항" in content
        # 같은 상위 아래 다른 SECTION-2 는 제외
        assert "1. 사업의 개요" not in content

    def test_table_in_content(self, config):
        builder = MarkdownBuilder(config)
        path    = builder.save_document(make_doc())
        content = path.read_text(encoding="utf-8")
        assert "244731건" in content
        assert "| 구분 |" in content


# ---------------------------------------------------------------------------
# save_document_batch — 배치 ID 공유
# ---------------------------------------------------------------------------

class TestSaveDocumentBatch:

    def test_same_batch_folder(self, config):
        builder  = MarkdownBuilder(config)
        batch_id = new_batch_id()
        docs = [
            make_doc("삼성전자주식회사",  "20240312000736"),
            make_doc("현대자동차주식회사", "20240315000001"),
        ]
        paths = builder.save_document_batch(docs, batch_id=batch_id)
        assert len(paths) == 2
        # 모두 같은 배치 폴더 안에 있어야 함
        assert all(p.parent.name == batch_id for p in paths)

    def test_auto_batch_id_generated(self, config):
        builder = MarkdownBuilder(config)
        docs    = [make_doc("삼성전자주식회사", "20240312000736")]
        paths   = builder.save_document_batch(docs)   # batch_id 미지정
        # 자동 생성된 batch_id 형식이어야 함
        assert re.match(r"^\d{8}_\d{6}_[0-9a-f]{4}$", paths[0].parent.name)

    def test_different_corps_different_files(self, config):
        builder  = MarkdownBuilder(config)
        batch_id = new_batch_id()
        docs = [
            make_doc("삼성전자주식회사",  "R001"),
            make_doc("현대자동차주식회사", "R002"),
        ]
        paths = builder.save_document_batch(docs, batch_id=batch_id)
        names = [p.name for p in paths]
        assert names[0] != names[1]


# ---------------------------------------------------------------------------
# DS002 ParsedReport — 배치 ID 폴더 구조
# ---------------------------------------------------------------------------

class TestSaveReportBatchId:

    def test_no_batch_id_uses_corp_folder(self, config):
        """batch_id 없으면 output_dir/corp_name/year_label.md"""
        builder = MarkdownBuilder(config)
        report  = make_report("삼성전자", "2023")
        path    = builder.save(report)
        assert path.parent.name == "삼성전자"
        assert path.name == "2023_사업보고서.md"

    def test_with_batch_id_uses_batch_folder(self, config):
        """batch_id 있으면 output_dir/batch_id/corp_year_label.md"""
        builder  = MarkdownBuilder(config)
        batch_id = "20240312_153045_a3f2"
        report   = make_report("삼성전자", "2023")
        path     = builder.save(report, batch_id=batch_id)
        assert path.parent.name == batch_id
        assert "삼성전자" in path.name

    def test_save_batch_same_folder(self, config):
        """save_batch: 여러 기업이 같은 batch_id 폴더에 모인다."""
        builder  = MarkdownBuilder(config)
        batch_id = new_batch_id()
        reports  = [
            make_report("삼성전자",   "2023"),
            make_report("현대자동차", "2023"),
            make_report("카카오",     "2023"),
        ]
        paths = builder.save_batch(reports, batch_id=batch_id)
        assert len(paths) == 3
        assert all(p.parent.name == batch_id for p in paths)

    def test_save_batch_auto_batch_id(self, config):
        """batch_id 미지정 시 자동 생성된다."""
        builder = MarkdownBuilder(config)
        reports = [make_report("삼성전자", "2022"), make_report("삼성전자", "2023")]
        paths   = builder.save_batch(reports)
        # 두 파일이 같은 자동 생성 폴더에 있어야 함
        assert paths[0].parent == paths[1].parent
        assert re.match(r"^\d{8}_\d{6}_[0-9a-f]{4}$", paths[0].parent.name)
