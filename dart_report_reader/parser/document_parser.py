"""
dart_report_reader/parser/document_parser.py
DART 공시서류 원문 파싱 — HTML 뷰어 방식 (v5)

접근 전략 (dart-fss 라이브러리와 동일):
  1. document.xml ZIP → regex로 ATOCID 목록 추출 (목차 파싱)
     - XML 파싱을 사용하지 않으므로 태그 오염 문제 완전 우회
  2. ZIP 파일명에서 dcmNo 추출
  3. DART 뷰어 HTML 요청:
       https://dart.fss.or.kr/report/viewer.do
         ?rcpNo={rcept_no}&dcmNo={dcmNo}&eleId={atocid}
         &offset=0&length=0&dtd=dart3.xsd
  4. BeautifulSoup으로 렌더링된 HTML 파싱 → 텍스트 추출
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 데이터 모델
# ---------------------------------------------------------------------------

@dataclass
class TocEntry:
    """목차 항목 하나."""
    ele_id: int        # ATOCID (= eleId)
    title:  str        # 섹션 제목
    level:  int = 0    # 계층 깊이 (1=챕터, 2=소항목, ...)


@dataclass
class DocumentSection:
    """파싱된 단일 섹션."""
    tocid:      int
    title:      str
    level:      int
    content_md: str = ""
    children:   list["DocumentSection"] = field(default_factory=list)
    assoc_note: str = ""

    @property
    def is_empty(self) -> bool:
        return not self.content_md.strip() and not self.children

    @property
    def full_md(self) -> str:
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
    """공시서류 전체 파싱 결과."""
    rcept_no:    str
    corp_name:   str
    doc_type:    str
    period_from: str
    period_to:   str
    dcm_no:      str = ""
    sections:    list[DocumentSection] = field(default_factory=list)

    def find_section(
        self,
        title_keywords:  list[str],
        parent_keywords: Optional[list[str]] = None,
    ) -> Optional[DocumentSection]:
        def _match(sec, kws):
            return all(kw in sec.title for kw in kws)

        def _search(secs, parent_matched):
            for sec in secs:
                in_scope = parent_matched or parent_keywords is None
                if in_scope and _match(sec, title_keywords):
                    return sec
                child_scope = in_scope or (
                    parent_keywords is not None and _match(sec, parent_keywords)
                )
                result = _search(sec.children, child_scope)
                if result:
                    return result
            return None

        return _search(self.sections, parent_keywords is None)

    def all_sections_flat(self) -> list[DocumentSection]:
        result: list[DocumentSection] = []
        def _collect(secs):
            for s in secs:
                result.append(s)
                _collect(s.children)
        _collect(self.sections)
        return result


# ---------------------------------------------------------------------------
# TOC 파서 (regex 기반, XML 파싱 없음)
# ---------------------------------------------------------------------------

class TocParser:
    """
    XML bytes 에서 목차(ATOCID + TITLE) 를 regex 로 추출.
    XML이 깨져 있어도 동작한다.
    """

    # TITLE 태그의 두 가지 속성 순서 모두 처리
    _PAT1 = re.compile(
        rb'<TITLE\s[^>]*ATOC="Y"[^>]*ATOCID="(\d+)"[^>]*>([^<]{1,150})<'
    )
    _PAT2 = re.compile(
        rb'<TITLE\s[^>]*ATOCID="(\d+)"[^>]*ATOC="Y"[^>]*>([^<]{1,150})<'
    )
    # 챕터 제목 판별 (로마숫자로 시작하거나 【로 시작)
    _CHAPTER_RE = re.compile(
        r'^(I{1,3}V?|VI{0,3}|IX|X{1,3}|XI{1,3}|XIV|XV|XVI|【|대표이사)'
    )

    def extract_toc(self, xml_bytes: bytes) -> list[TocEntry]:
        seen:    set[int]      = set()
        entries: list[TocEntry] = []

        for m in self._PAT1.finditer(xml_bytes):
            tocid = int(m.group(1))
            title = m.group(2).decode("utf-8", "replace").strip()
            if tocid not in seen:
                seen.add(tocid)
                entries.append(TocEntry(ele_id=tocid, title=title,
                                        level=self._guess_level(title)))

        for m in self._PAT2.finditer(xml_bytes):
            tocid = int(m.group(1))
            title = m.group(2).decode("utf-8", "replace").strip()
            if tocid not in seen:
                seen.add(tocid)
                entries.append(TocEntry(ele_id=tocid, title=title,
                                        level=self._guess_level(title)))

        return entries

    def _guess_level(self, title: str) -> int:
        """제목 형식으로 계층 깊이 추측."""
        if self._CHAPTER_RE.match(title):
            return 1
        # "1.", "2." 등으로 시작하면 level 2
        if re.match(r'^\d+[\.\-]', title):
            return 2
        # "1-1.", "7-1." 등
        if re.match(r'^\d+[\-\.]\d+', title):
            return 3
        return 2

    @staticmethod
    def extract_meta(xml_bytes: bytes) -> dict:
        """기업명, 보고서명, 사업연도 추출."""
        corp = re.search(rb'<COMPANY-NAME[^>]*>([^<]+)<', xml_bytes)
        doc  = re.search(rb'<DOCUMENT-NAME[^>]*>([^<]+)<', xml_bytes)
        pfrom = re.search(rb'AUNIT="PERIODFROM"\s+AUNITVALUE="(\d+)"', xml_bytes)
        pto   = re.search(rb'AUNIT="PERIODTO"\s+AUNITVALUE="(\d+)"', xml_bytes)
        # 역순 패턴도
        pfrom2 = re.search(rb'AUNITVALUE="(\d+)"\s+AUNIT="PERIODFROM"', xml_bytes)
        pto2   = re.search(rb'AUNITVALUE="(\d+)"\s+AUNIT="PERIODTO"', xml_bytes)
        return {
            "corp_name":   (corp.group(1)  if corp  else b"").decode("utf-8","replace").strip(),
            "doc_type":    (doc.group(1)   if doc   else b"").decode("utf-8","replace").strip(),
            "period_from": (pfrom or pfrom2).group(1).decode() if (pfrom or pfrom2) else "",
            "period_to":   (pto   or pto2  ).group(1).decode() if (pto   or pto2  ) else "",
        }


# ---------------------------------------------------------------------------
# HTML 뷰어 파서
# ---------------------------------------------------------------------------

class ViewerParser:
    """
    DART 뷰어 HTML → Markdown 텍스트 변환.
    dart-fss 와 동일하게 BeautifulSoup(html, 'html.parser') 사용.
    """

    VIEWER_URL = (
        "https://dart.fss.or.kr/report/viewer.do"
        "?rcpNo={rcept_no}&dcmNo={dcm_no}"
        "&eleId={ele_id}&offset=0&length=0&dtd=dart3.xsd"
    )

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://dart.fss.or.kr/",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }

    def __init__(self, timeout: int = 30) -> None:
        self.timeout = timeout

    def fetch_html(self, rcept_no: str, dcm_no: str, ele_id: int) -> str:
        """뷰어 HTML 가져오기."""
        url = self.VIEWER_URL.format(
            rcept_no=rcept_no, dcm_no=dcm_no, ele_id=ele_id
        )
        logger.debug("뷰어 요청: %s", url)
        res = requests.get(url, headers=self.HEADERS, timeout=self.timeout)
        res.raise_for_status()
        return res.text

    def html_to_markdown(self, html: str) -> str:
        """렌더링된 HTML → Markdown 텍스트."""
        # dart-fss 방식: non-break space 처리
        html = html.replace("\u00a0", " ")
        soup = BeautifulSoup(html, "html.parser")

        # 본문 영역 추출 (dart 뷰어는 body 또는 .view_doc div)
        body = soup.find("div", class_="view_doc") or soup.body or soup

        lines: list[str] = []
        self._process_element(body, lines)
        # 연속 빈 줄 제거
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
        return text.strip()

    def _process_element(self, el, lines: list[str]) -> None:
        tag = el.name if el.name else ""

        if tag in ("script", "style", "head"):
            return

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            text  = el.get_text(separator=" ", strip=True)
            if text:
                lines.append(f"\n{'#' * level} {text}\n")
            return

        if tag == "table":
            self._table_to_md(el, lines)
            return

        if tag in ("p", "div", "span", "td", "th", "li"):
            text = el.get_text(separator=" ", strip=True)
            if text:
                lines.append(text)
            return

        if tag == "br":
            lines.append("")
            return

        # 그 외: 자식 순회
        for child in el.children:
            if hasattr(child, "name"):
                self._process_element(child, lines)
            else:
                t = str(child).strip()
                if t:
                    lines.append(t)

    def _table_to_md(self, table_el, lines: list[str]) -> None:
        rows = table_el.find_all("tr")
        if not rows:
            return

        md_rows: list[str] = []
        header_done = False

        for row in rows:
            cells = row.find_all(["th", "td"])
            if not cells:
                continue
            cell_texts = [
                c.get_text(separator=" ", strip=True).replace("|", "\\|")
                for c in cells
            ]
            md_rows.append("| " + " | ".join(cell_texts) + " |")
            if not header_done:
                md_rows.append("| " + " | ".join(["---"] * len(cells)) + " |")
                header_done = True

        if md_rows:
            lines.append("")
            lines.extend(md_rows)
            lines.append("")


# ---------------------------------------------------------------------------
# 메인 파서 (Facade)
# ---------------------------------------------------------------------------

class DocumentParser:
    """
    ZIP bytes → ParsedDocument.

    XML 파싱을 하지 않고:
    1. regex로 목차(ATOCID) 추출
    2. DART 뷰어 HTML로 각 섹션 내용 조회
    """

    def __init__(self, timeout: int = 30) -> None:
        self._toc_parser    = TocParser()
        self._viewer_parser = ViewerParser(timeout=timeout)

    # ------------------------------------------------------------------
    # XML bytes → ParsedDocument (목차만 구성, 내용은 lazy 로딩)
    # ------------------------------------------------------------------

    def parse_toc(self, xml_bytes: bytes, rcept_no: str) -> ParsedDocument:
        """
        ZIP 본문 XML 에서 목차만 추출한 ParsedDocument 반환.
        각 섹션의 content_md 는 비어 있음 (fetch_sections 로 채움).
        """
        meta    = self._toc_parser.extract_meta(xml_bytes)
        entries = self._toc_parser.extract_toc(xml_bytes)

        # dcmNo: 파일명에서 추출 — 호출자가 주입
        sections = self._build_tree(entries)

        return ParsedDocument(
            rcept_no=rcept_no,
            corp_name=meta["corp_name"],
            doc_type=meta["doc_type"],
            period_from=meta["period_from"],
            period_to=meta["period_to"],
            sections=sections,
        )

    # ------------------------------------------------------------------
    # 섹션 내용 로딩 (HTML 뷰어)
    # ------------------------------------------------------------------

    def fetch_section_content(
        self,
        rcept_no: str,
        dcm_no:   str,
        ele_id:   int,
    ) -> str:
        """단일 섹션의 뷰어 HTML → Markdown 텍스트."""
        html = self._viewer_parser.fetch_html(rcept_no, dcm_no, ele_id)
        return self._viewer_parser.html_to_markdown(html)

    def fetch_sections(
        self,
        doc:         ParsedDocument,
        dcm_no:      str,
        title_filter: Optional[list[str]] = None,
    ) -> ParsedDocument:
        """
        ParsedDocument 의 각 섹션 content_md 를 HTML 뷰어로 채운다.

        Parameters
        ----------
        title_filter : list[str], optional
            특정 키워드 포함 섹션만 로딩. None 이면 전체.
        """
        doc.dcm_no = dcm_no

        flat = doc.all_sections_flat()
        for sec in flat:
            if title_filter and not any(kw in sec.title for kw in title_filter):
                continue
            try:
                sec.content_md = self.fetch_section_content(
                    doc.rcept_no, dcm_no, sec.tocid
                )
                logger.info("섹션 로딩: [%d] %s (%d chars)",
                            sec.tocid, sec.title, len(sec.content_md))
            except Exception as e:
                logger.warning("섹션 로딩 실패 [%d] %s: %s", sec.tocid, sec.title, e)

        return doc

    # ------------------------------------------------------------------
    # 편의 메서드: ZIP bytes 에서 한 번에 ParsedDocument 완성
    # ------------------------------------------------------------------

    def parse(
        self,
        xml_bytes:    bytes,
        rcept_no:     str,
        dcm_no:       str,
        title_filter: Optional[list[str]] = None,
    ) -> ParsedDocument:
        """
        ZIP 본문 XML bytes → 섹션 내용까지 완성된 ParsedDocument.

        Parameters
        ----------
        xml_bytes    : ZIP 내 본문 XML의 bytes
        rcept_no     : 접수번호
        dcm_no       : ZIP 파일명에서 추출한 문서번호
        title_filter : 로딩할 섹션 제목 키워드 (None=전체)
        """
        doc = self.parse_toc(xml_bytes, rcept_no)
        self.fetch_sections(doc, dcm_no, title_filter)
        return doc

    # ------------------------------------------------------------------
    # 내부: 목차 트리 구성
    # ------------------------------------------------------------------

    @staticmethod
    def _build_tree(entries: list[TocEntry]) -> list[DocumentSection]:
        """
        TocEntry 리스트 → DocumentSection 계층 트리.
        level=1 은 최상위, level=2 는 그 하위.
        """
        roots:   list[DocumentSection] = []
        stack:   list[DocumentSection] = []   # (level, section)

        for entry in entries:
            sec = DocumentSection(
                tocid=entry.ele_id,
                title=entry.title,
                level=entry.level,
            )
            # 스택에서 현재보다 같거나 높은 레벨 제거
            while stack and stack[-1].level >= entry.level:
                stack.pop()

            if stack:
                stack[-1].children.append(sec)
            else:
                roots.append(sec)

            stack.append(sec)

        return roots

    # ------------------------------------------------------------------
    # 하위 호환: 기존 코드가 sanitize_xml_bytes 를 호출하는 경우 대비
    # ------------------------------------------------------------------

    @staticmethod
    def sanitize_xml_bytes(xml_bytes: bytes) -> bytes:
        """하위 호환 stub — HTML 뷰어 방식에서는 불필요."""
        return xml_bytes
