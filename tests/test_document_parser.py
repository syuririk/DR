"""
tests/test_document_parser.py
DocumentParser 단위 테스트

실제 삼성전자 사업보고서 XML(20240312000736.xml) 구조를 바탕으로
인메모리 미니 XML 을 만들어 테스트한다.
"""

from __future__ import annotations

import pytest
from lxml import etree

from dart_report_reader.parser.document_parser import (
    DocumentParser,
    DocumentSection,
    ParsedDocument,
)


# ---------------------------------------------------------------------------
# 테스트용 XML 빌더
# ---------------------------------------------------------------------------

def make_xml(sections_xml: str, corp_name: str = "테스트전자주식회사") -> etree._Element:
    """미니 DOCUMENT XML 생성."""
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<DOCUMENT>
  <DOCUMENT-NAME ACODE="11011">사업보고서</DOCUMENT-NAME>
  <COMPANY-NAME AREGCIK="00126380">{corp_name}</COMPANY-NAME>
  <BODY ATOCID="100">
    <TR ACOPY="N" ADELETE="N">
      <TU AUNIT="PERIODFROM" AUNITVALUE="20230101">2023년 01월 01일</TU>
    </TR>
    <TR ACOPY="N" ADELETE="N">
      <TU AUNIT="PERIODTO" AUNITVALUE="20231231">2023년 12월 31일</TU>
    </TR>
    {sections_xml}
  </BODY>
</DOCUMENT>"""
    parser = etree.XMLParser(recover=True)
    return etree.fromstring(xml.encode("utf-8"), parser)


def make_section1(title: str, tocid: str, assoc: str, body: str = "") -> str:
    return f"""
<SECTION-1 ACLASS="MANDATORY">
  <TITLE ATOC="Y" ATOCID="{tocid}" AASSOCNOTE="{assoc}">{title}</TITLE>
  {body}
</SECTION-1>"""


def make_section2(title: str, tocid: str, assoc: str, body: str = "") -> str:
    return f"""
<SECTION-2 ACLASS="MANDATORY">
  <TITLE ATOC="Y" ATOCID="{tocid}" AASSOCNOTE="{assoc}">{title}</TITLE>
  {body}
</SECTION-2>"""


def make_section3(title: str, tocid: str, body: str = "") -> str:
    return f"""
<SECTION-3 ACLASS="MANDATORY">
  <TITLE ATOC="Y" ATOCID="{tocid}">{title}</TITLE>
  {body}
</SECTION-3>"""


# ---------------------------------------------------------------------------
# fixture
# ---------------------------------------------------------------------------

SAMPLE_S2_BODY = """
<P>첫 번째 단락입니다.</P>
<P>두 번째 단락입니다.</P>
<TABLE>
  <TBODY>
    <TR><TD>항목</TD><TD>값</TD></TR>
    <TR><TD>매출액</TD><TD>300조</TD></TR>
  </TBODY>
</TABLE>
"""

SAMPLE_S3_BODY = "<P>소항목 내용입니다.</P>"

SAMPLE_S2_WITH_S3 = f"""
<P>소개 문장입니다.</P>
{make_section3("7-1. 세부항목", "101", SAMPLE_S3_BODY)}
{make_section3("7-2. 다른항목", "102", "<P>다른 내용.</P>")}
"""

# II. 사업의 내용처럼 LIBRARY 로 감싸인 구조
LIBRARY_SECTION = f"""
<SECTION-1 ACLASS="MANDATORY">
  <TITLE ATOC="Y" ATOCID="9" AASSOCNOTE="D-0-2-0-0">II. 사업의 내용</TITLE>
  <LIBRARY>
    {make_section2("1. 사업의 개요", "10", "L-0-2-1-L1", "<P>사업 개요 내용.</P>")}
    {make_section2("7. 기타 참고사항", "16", "L-0-2-7-L1", SAMPLE_S2_BODY)}
  </LIBRARY>
</SECTION-1>"""

FULL_XML = make_xml(
    make_section1(
        "I. 회사의 개요", "3", "",
        make_section2("1. 회사의 개요", "4", "D-0-1-1-0", "<P>회사 소개.</P>")
        + make_section2("2. 회사의 연혁", "5", "D-0-1-2-0", "<P>연혁 내용.</P>"),
    )
    + LIBRARY_SECTION
    + make_section1(
        "III. 재무에 관한 사항", "17", "D-0-3-0-0",
        make_section2(
            "7. 증권의 발행을 통한 자금조달에 관한 사항", "24", "D-0-3-7-0",
            SAMPLE_S2_WITH_S3,
        ),
    )
)


@pytest.fixture
def parser() -> DocumentParser:
    return DocumentParser()


@pytest.fixture
def parsed(parser: DocumentParser) -> ParsedDocument:
    return parser.parse(FULL_XML)


# ---------------------------------------------------------------------------
# 테스트
# ---------------------------------------------------------------------------

class TestDocumentParserMeta:

    def test_corp_name(self, parsed):
        assert parsed.corp_name == "테스트전자주식회사"

    def test_doc_type(self, parsed):
        assert parsed.doc_type == "사업보고서"

    def test_period_from(self, parsed):
        assert parsed.period_from == "20230101"

    def test_period_to(self, parsed):
        assert parsed.period_to == "20231231"


class TestSectionTree:

    def test_top_level_section_count(self, parsed):
        """SECTION-1 이 3개여야 한다."""
        assert len(parsed.sections) == 3

    def test_section1_titles(self, parsed):
        titles = [s.title for s in parsed.sections]
        assert "I. 회사의 개요" in titles
        assert "II. 사업의 내용" in titles
        assert "III. 재무에 관한 사항" in titles

    def test_section1_level(self, parsed):
        for sec in parsed.sections:
            assert sec.level == 1

    def test_section2_children_direct(self, parsed):
        """I. 회사의 개요는 SECTION-2 를 직계 자식으로 가진다."""
        s1 = next(s for s in parsed.sections if s.title == "I. 회사의 개요")
        assert len(s1.children) == 2
        assert s1.children[0].title == "1. 회사의 개요"
        assert s1.children[1].title == "2. 회사의 연혁"

    def test_library_transparent(self, parsed):
        """II. 사업의 내용: LIBRARY 안의 SECTION-2 가 직접 children 으로 파싱된다."""
        s1 = next(s for s in parsed.sections if "사업의 내용" in s.title)
        assert len(s1.children) == 2
        assert s1.children[0].title == "1. 사업의 개요"
        assert s1.children[1].title == "7. 기타 참고사항"

    def test_section3_nested(self, parsed):
        """SECTION-3 은 SECTION-2 의 children 에 들어가야 한다."""
        s1 = next(s for s in parsed.sections if "재무에 관한 사항" in s.title)
        s2 = s1.children[0]
        assert s2.title == "7. 증권의 발행을 통한 자금조달에 관한 사항"
        assert len(s2.children) == 2
        assert s2.children[0].title == "7-1. 세부항목"
        assert s2.children[1].title == "7-2. 다른항목"

    def test_section_level_values(self, parsed):
        """SECTION-2 level=2, SECTION-3 level=3 이어야 한다."""
        s1 = next(s for s in parsed.sections if "재무에 관한 사항" in s.title)
        s2 = s1.children[0]
        assert s2.level == 2
        assert s2.children[0].level == 3

    def test_tocid_captured(self, parsed):
        s1 = next(s for s in parsed.sections if "사업의 내용" in s.title)
        assert s1.tocid == "9"

    def test_assoc_note_captured(self, parsed):
        s1 = next(s for s in parsed.sections if "사업의 내용" in s.title)
        assert s1.assoc_note == "D-0-2-0-0"


class TestContentParsing:

    def test_p_tag_to_text(self, parsed):
        s1 = next(s for s in parsed.sections if "사업의 내용" in s.title)
        s2 = next(c for c in s1.children if "기타 참고사항" in c.title)
        assert "첫 번째 단락입니다" in s2.content_md
        assert "두 번째 단락입니다" in s2.content_md

    def test_table_to_markdown_pipe(self, parsed):
        s1 = next(s for s in parsed.sections if "사업의 내용" in s.title)
        s2 = next(c for c in s1.children if "기타 참고사항" in c.title)
        assert "| 항목 | 값 |" in s2.content_md
        assert "| 매출액 | 300조 |" in s2.content_md
        assert "| --- |" in s2.content_md

    def test_table_separator_row(self, parsed):
        """헤더 바로 아래에 구분선 행이 있어야 한다."""
        s1 = next(s for s in parsed.sections if "사업의 내용" in s.title)
        s2 = next(c for c in s1.children if "기타 참고사항" in c.title)
        lines = s2.content_md.splitlines()
        header_idx = next(i for i, l in enumerate(lines) if "항목" in l)
        assert "---" in lines[header_idx + 1]


class TestFindSection:

    def test_find_by_exact_keyword(self, parsed):
        sec = parsed.find_section(["기타 참고사항"])
        assert sec is not None
        assert "기타 참고사항" in sec.title

    def test_find_by_multiple_keywords(self, parsed):
        sec = parsed.find_section(["사업의 개요"])
        assert sec is not None

    def test_find_with_parent_filter(self, parsed):
        """상위 섹션 필터로 범위를 좁혀 찾는다."""
        sec = parsed.find_section(
            title_keywords=["기타 참고사항"],
            parent_keywords=["사업의 내용"],
        )
        assert sec is not None
        assert "기타 참고사항" in sec.title

    def test_find_nonexistent_returns_none(self, parsed):
        sec = parsed.find_section(["존재하지않는섹션ZZZZ"])
        assert sec is None

    def test_find_wrong_parent_returns_none(self, parsed):
        """올바른 섹션이라도 상위 필터가 맞지 않으면 None."""
        sec = parsed.find_section(
            title_keywords=["기타 참고사항"],
            parent_keywords=["재무에 관한 사항"],
        )
        assert sec is None


class TestAllSectionsFlat:

    def test_flat_includes_all_levels(self, parsed):
        all_secs = parsed.all_sections_flat()
        titles = [s.title for s in all_secs]
        assert "I. 회사의 개요" in titles          # level 1
        assert "1. 회사의 개요" in titles           # level 2
        assert "7-1. 세부항목" in titles            # level 3

    def test_flat_count(self, parsed):
        """
        SECTION-1: 3, SECTION-2: I(2)+II(2)+III(1)=5,
        SECTION-3: III>7번(2) = 2  → 합계 10
        """
        all_secs = parsed.all_sections_flat()
        assert len(all_secs) == 10


class TestFullMd:

    def test_full_md_contains_header(self, parsed):
        s1 = next(s for s in parsed.sections if "사업의 내용" in s.title)
        s2 = next(c for c in s1.children if "기타 참고사항" in c.title)
        md = s2.full_md
        assert "## 7. 기타 참고사항" in md or "### 7. 기타 참고사항" in md

    def test_full_md_includes_children(self, parsed):
        """full_md 는 하위 섹션 내용도 포함해야 한다."""
        s1 = next(s for s in parsed.sections if "재무에 관한 사항" in s.title)
        s2 = s1.children[0]
        md = s2.full_md
        assert "7-1. 세부항목" in md
        assert "소항목 내용입니다" in md
