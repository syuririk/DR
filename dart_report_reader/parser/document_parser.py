"""
dart_report_reader/parser/document_parser.py
DART 공시서류 원문 XML → 섹션별 구조화 데이터

실제 XML 구조 (삼성전자 사업보고서 20240312000736 기준):

DOCUMENT
└── BODY
    ├── COVER
    ├── SECTION-1  (예: I. 회사의 개요)
    │   ├── TITLE
    │   ├── SECTION-2  (직계 자식, 예: III. 재무에 관한 사항 하위)
    │   └── LIBRARY    (간접 자식, 예: II. 사업의 내용 하위)
    │       └── SECTION-2
    │           ├── TITLE
    │           ├── SECTION-3
    │           └── (P, TABLE, TABLE-GROUP, IMG-CAPTION, PGBRK ...)
    └── SECTION-1 ...

컨텐츠 변환 규칙:
  TITLE        → Markdown 헤더 (depth 에 따라 # ~ ####)
  P            → 단락 텍스트 (itertext() 로 SPAN 포함)
  TABLE        → Markdown 파이프 테이블
  TABLE-GROUP  → 내부 TABLE 처리
  IMG-CAPTION  → 이탤릭 캡션
  PGBRK        → 무시
  그 외         → 재귀 처리
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

from lxml import etree

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 데이터 모델
# ---------------------------------------------------------------------------

@dataclass
class DocumentSection:
    """
    파싱된 단일 섹션.

    Attributes
    ----------
    tocid : str
        DART 목차 ID (ATOCID 속성).
    title : str
        섹션 제목.
    level : int
        계층 깊이 (1=SECTION-1, 2=SECTION-2, 3=SECTION-3, 4=SECTION-4).
    content_md : str
        섹션 내용을 Markdown 으로 변환한 텍스트 (하위 섹션 제외).
    children : list[DocumentSection]
        하위 섹션 목록.
    assoc_note : str
        AASSOCNOTE 속성값 (예: "D-0-2-0-0").
    """
    tocid: str
    title: str
    level: int
    content_md: str = ""
    children: list["DocumentSection"] = field(default_factory=list)
    assoc_note: str = ""

    @property
    def full_md(self) -> str:
        """헤더 + 내용 + 하위 섹션을 합친 전체 Markdown."""
        hdr = "#" * min(self.level + 1, 6)
        lines = [f"{hdr} {self.title}", ""]
        if self.content_md.strip():
            lines.append(self.content_md.strip())
            lines.append("")
        for child in self.children:
            lines.append(child.full_md)
            lines.append("")
        return "\n".join(lines)


@dataclass
class ParsedDocument:
    """
    공시서류 원문 전체 파싱 결과.
    """
    rcept_no: str
    corp_name: str
    doc_type: str                                     # 예: "사업보고서"
    period_from: str                                  # 예: "20230101"
    period_to: str                                    # 예: "20231231"
    sections: list[DocumentSection] = field(default_factory=list)

    def find_section(
        self,
        title_keywords: list[str],
        parent_keywords: Optional[list[str]] = None,
    ) -> Optional[DocumentSection]:
        """
        제목에 keywords 가 모두 포함된 섹션을 반환한다.

        Parameters
        ----------
        title_keywords : list[str]
            찾을 섹션 제목에 포함되어야 할 키워드 목록.
        parent_keywords : list[str], optional
            상위 섹션 제목 필터. 지정하면 해당 상위 섹션 안에서만 탐색.

        Returns
        -------
        DocumentSection | None
        """
        def _match(sec: DocumentSection, keywords: list[str]) -> bool:
            return all(kw in sec.title for kw in keywords)

        def _search(
            sections: list[DocumentSection],
            parent_matched: bool,
        ) -> Optional[DocumentSection]:
            for sec in sections:
                in_scope = parent_matched or parent_keywords is None
                if in_scope and _match(sec, title_keywords):
                    return sec
                # 하위 탐색
                child_scope = in_scope or (
                    parent_keywords is not None and _match(sec, parent_keywords)
                )
                result = _search(sec.children, child_scope)
                if result:
                    return result
            return None

        return _search(self.sections, parent_keywords is None)

    def all_sections_flat(self) -> list[DocumentSection]:
        """모든 섹션을 flat 리스트로 반환."""
        result: list[DocumentSection] = []
        def _collect(secs: list[DocumentSection]) -> None:
            for s in secs:
                result.append(s)
                _collect(s.children)
        _collect(self.sections)
        return result


# ---------------------------------------------------------------------------
# 파서
# ---------------------------------------------------------------------------

class DocumentParser:
    """
    DART 공시서류 원문 XML root Element → ParsedDocument 변환.
    """

    # SECTION 태그 이름 → 깊이 매핑
    _SECTION_TAGS = {
        "SECTION-1": 1,
        "SECTION-2": 2,
        "SECTION-3": 3,
        "SECTION-4": 4,
    }

    # 콘텐츠 변환 시 무시할 태그
    _SKIP_TAGS = {"PGBRK", "EXTRACTION", "LIBRARY"}

    # ---------------------------------------------------------------------------

    def parse(self, root: etree._Element) -> ParsedDocument:
        """
        XML root → ParsedDocument.

        Parameters
        ----------
        root : etree._Element
            DocumentApi.fetch_main_xml() 의 반환값.
        """
        corp_name  = self._get_text(root.find("COMPANY-NAME")) or ""
        doc_type   = self._get_text(root.find("DOCUMENT-NAME")) or ""
        period_from, period_to = self._extract_period(root)
        rcept_no   = self._extract_rcept_no(root)

        body = root.find("BODY")
        sections: list[DocumentSection] = []
        if body is not None:
            sections = self._parse_children(body, depth=0)

        return ParsedDocument(
            rcept_no=rcept_no,
            corp_name=corp_name,
            doc_type=doc_type,
            period_from=period_from,
            period_to=period_to,
            sections=sections,
        )

    # ---------------------------------------------------------------------------
    # 내부: 섹션 트리 구성
    # ---------------------------------------------------------------------------

    def _parse_children(
        self, parent: etree._Element, depth: int
    ) -> list[DocumentSection]:
        """parent 의 직계 + LIBRARY 를 통해 섹션을 수집한다."""
        sections: list[DocumentSection] = []
        for child in parent:
            tag = child.tag if isinstance(child.tag, str) else ""
            if tag in self._SECTION_TAGS:
                sec = self._parse_section(child, self._SECTION_TAGS[tag])
                sections.append(sec)
            elif tag == "LIBRARY":
                # LIBRARY 는 SECTION-2 들을 감싸는 컨테이너 — 투명하게 처리
                sections.extend(self._parse_children(child, depth + 1))
        return sections

    def _parse_section(
        self, el: etree._Element, level: int
    ) -> DocumentSection:
        """단일 SECTION-N 엘리먼트 → DocumentSection."""
        title_el   = el.find("TITLE")
        title      = self._get_text(title_el) or "(제목 없음)"
        tocid      = (
            (title_el.get("ATOCID", "") if title_el is not None else "")
            or el.get("ATOCID", "")
        )
        assoc_note = title_el.get("AASSOCNOTE", "") if title_el is not None else ""

        content_parts: list[str] = []
        children:      list[DocumentSection] = []

        for child in el:
            tag = child.tag if isinstance(child.tag, str) else ""
            if tag == "TITLE":
                continue                            # 이미 처리
            elif tag in self._SECTION_TAGS:
                children.append(
                    self._parse_section(child, self._SECTION_TAGS[tag])
                )
            elif tag == "LIBRARY":
                # LIBRARY 안의 SECTION-N 은 자식으로
                children.extend(self._parse_children(child, level))
            elif tag not in self._SKIP_TAGS:
                md = self._element_to_md(child)
                if md:
                    content_parts.append(md)

        return DocumentSection(
            tocid=tocid,
            title=title,
            level=level,
            content_md="\n\n".join(content_parts),
            children=children,
            assoc_note=assoc_note,
        )

    # ---------------------------------------------------------------------------
    # 내부: 엘리먼트 → Markdown 변환
    # ---------------------------------------------------------------------------

    def _element_to_md(self, el: etree._Element) -> str:
        tag = el.tag if isinstance(el.tag, str) else ""

        if tag == "P":
            return self._p_to_md(el)
        elif tag in ("TABLE", "TABLE-GROUP"):
            return self._table_to_md(el)
        elif tag == "IMG-CAPTION":
            text = self._get_text(el)
            return f"*[이미지: {text}]*" if text else ""
        elif tag == "TITLE":
            return ""   # 섹션 TITLE 은 헤더에서 처리됨
        elif tag in self._SKIP_TAGS:
            return ""
        else:
            # 기타 태그 — 재귀로 자식 처리
            parts = []
            for child in el:
                md = self._element_to_md(child)
                if md:
                    parts.append(md)
            return "\n\n".join(parts)

    def _p_to_md(self, el: etree._Element) -> str:
        """P 태그 → 텍스트 (SPAN 등 인라인 태그 포함)."""
        text = " ".join(
            t.strip() for t in el.itertext() if t.strip()
        )
        return self._clean_text(text)

    def _table_to_md(self, el: etree._Element) -> str:
        """TABLE / TABLE-GROUP → Markdown 파이프 테이블."""
        # TABLE-GROUP 은 TABLE 을 감싸는 컨테이너
        if el.tag == "TABLE-GROUP":
            tables = el.findall(".//TABLE")
        else:
            tables = [el]

        md_blocks: list[str] = []
        for table in tables:
            rows = table.findall(".//TR")
            if not rows:
                continue

            md_rows: list[str] = []
            header_written = False
            for row in rows:
                cells: list[str] = []
                for td in row:
                    if td.tag not in ("TD", "TH", "TU"):
                        continue
                    cell_text = " ".join(
                        t.strip() for t in td.itertext() if t.strip()
                    )
                    cell_text = self._clean_text(cell_text).replace("|", "\\|")
                    cells.append(cell_text)

                if not cells:
                    continue

                md_rows.append("| " + " | ".join(cells) + " |")
                if not header_written:
                    md_rows.append("| " + " | ".join(["---"] * len(cells)) + " |")
                    header_written = True

            if md_rows:
                md_blocks.append("\n".join(md_rows))

        return "\n\n".join(md_blocks)

    # ---------------------------------------------------------------------------
    # 내부: 유틸
    # ---------------------------------------------------------------------------

    @staticmethod
    def _get_text(el: Optional[etree._Element]) -> str:
        if el is None:
            return ""
        return " ".join(t.strip() for t in el.itertext() if t.strip())

    @staticmethod
    def _clean_text(text: str) -> str:
        """연속 공백 정리, 불필요한 공백 제거."""
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _extract_period(
        self, root: etree._Element
    ) -> tuple[str, str]:
        """사업연도 시작/종료일 추출 (AUNITVALUE 속성)."""
        from_el = root.find('.//*[@AUNIT="PERIODFROM"]')
        to_el   = root.find('.//*[@AUNIT="PERIODTO"]')
        period_from = (from_el.get("AUNITVALUE", "") if from_el is not None else "")
        period_to   = (to_el.get("AUNITVALUE", "")   if to_el   is not None else "")
        return period_from, period_to

    @staticmethod
    def _extract_rcept_no(root: etree._Element) -> str:
        """COMPANY-NAME 태그의 AREGCIK 속성 → corp_code (rcept_no 는 파일명으로 대체)."""
        # rcept_no 는 XML 내부에 없고 파일명에 있으므로 빈 문자열 반환
        # 실제 사용 시 DocumentApi 에서 주입
        return ""
