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

    # 유효한 DART XML 태그 패턴 (영문 대문자 + 숫자 + 하이픈만 허용)
    _VALID_TAG_RE = re.compile(rb"<(/?)([A-Z][A-Z0-9\-]*)([^>]*)>")

    # DART에서 실제로 사용하는 태그 화이트리스트
    _KNOWN_TAGS: frozenset[bytes] = frozenset([
        b"DOCUMENT", b"DOCUMENT-NAME", b"FORMULA-VERSION", b"COMPANY-NAME",
        b"SUMMARY", b"EXTRACTION", b"BODY", b"COVER", b"COVER-TITLE",
        b"SECTION-1", b"SECTION-2", b"SECTION-3", b"SECTION-4",
        b"LIBRARY", b"TITLE", b"P", b"SPAN", b"TABLE", b"TABLE-GROUP",
        b"COLGROUP", b"COL", b"TBODY", b"TR", b"TD", b"TH", b"TU",
        b"IMG", b"IMG-CAPTION", b"PGBRK", b"NOTE", b"ATTACH",
        b"ATTACH-LIST", b"ATTACH-ITEM", b"A",
    ])

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
    def sanitize_xml_bytes(xml_bytes: bytes) -> bytes:
        """
        DART XML 전처리: 비정상 태그처럼 쓰인 텍스트를 이스케이프한다.

        일부 보고서는 아래와 같이 텍스트를 XML 태그 형태로 작성한다:
          - <한국기업평가>      한글로 시작하는 비정상 태그
          - <NICE 신용평가>     영문+공백+한글 (속성이 아닌 공백 포함)
          - <당기말>, <표1> 등

        이런 비정상 태그가 있으면 lxml recover=True 가 DOM 트리를
        잘못 복원하여 이후 모든 섹션 계층이 뒤틀린다.

        판별 기준:
        1. 태그명이 영문 대문자+숫자+하이픈만으로 구성돼야 정상
        2. 태그명 이후 부분이 공백+한글 등 비ASCII 를 포함하면 비정상
        → 비정상이면 < > 전체를 &lt; &gt; 로 이스케이프
        """
        known    = DocumentParser._KNOWN_TAGS
        valid_re = re.compile(rb"^[A-Z][A-Z0-9\-]*$")
        # 정상 속성 형태: 공백 뒤 영문자/언더스코어/콜론으로 시작하는 속성명=값
        valid_after = re.compile(rb"^[\s/]*(>|[A-Za-z_:][A-Za-z0-9_:\-\.]*\s*=)")

        # XML 선언·주석·CDATA·일반태그 모두 매칭
        pattern = re.compile(rb"<(\?|!--|!\[CDATA\[)?(/?)([^>]{1,400})>")

        def safe_replace(m: re.Match) -> bytes:
            full    = m.group(0)
            special = m.group(1)   # ?, !--, ![CDATA[
            slash   = m.group(2)   # / (닫힘 태그)
            inner   = m.group(3)

            # XML 선언 / 주석 / CDATA → 그대로
            if special:
                return full

            # 태그명 추출 (공백·>·/ 전까지)
            name_m = re.match(rb"^[^\s>/]+", inner)
            if not name_m:
                return full

            raw_name   = name_m.group(0)
            name_upper = raw_name.upper()
            after_name = inner[len(raw_name):]

            # 태그명에 비ASCII 포함 → 한글 등 → 비정상
            if any(b > 0x7F for b in raw_name):
                return full.replace(b"<", b"&lt;").replace(b">", b"&gt;")

            # 태그명이 영문 대문자+숫자+하이픈만이 아니면 비정상
            if not valid_re.match(name_upper):
                return full.replace(b"<", b"&lt;").replace(b">", b"&gt;")

            # 화이트리스트에 있으면 정상
            if name_upper in known:
                return full

            # 태그명 이후에 비ASCII 문자 포함 → <NICE 신용평가> 등
            if any(b > 0x7F for b in after_name):
                return full.replace(b"<", b"&lt;").replace(b">", b"&gt;")

            # 태그명 이후가 정상 속성 형태 → 알 수 없는 DART 확장 태그, 그대로
            if valid_after.match(after_name):
                return full

            return full

        return pattern.sub(safe_replace, xml_bytes)

    @staticmethod
    def _extract_rcept_no(root: etree._Element) -> str:
        """COMPANY-NAME 태그의 AREGCIK 속성 → corp_code (rcept_no 는 파일명으로 대체)."""
        # rcept_no 는 XML 내부에 없고 파일명에 있으므로 빈 문자열 반환
        # 실제 사용 시 DocumentApi 에서 주입
        return ""
