"""
dart_report_reader/vault/md_builder.py
ParsedReport / ParsedDocument → Obsidian .md 파일 생성

출력 구조
---------
단일 기업 보고서 (DS002 정형 데이터):
  {output_dir}/{corp_name}/{bsns_year}_{reprt_label}.md

배치 처리 (여러 기업 동시):
  {output_dir}/{batch_id}/{corp_name}_{bsns_year}_{reprt_label}.md
  ※ batch_id = 요청 시각 기반 고유번호 (예: 20240312_153045_a3f2)

원문 파싱 보고서 (DS001 document.xml):
  {output_dir}/{corp_name}/{rcept_no}_{doc_type}.md
  배치:
  {output_dir}/{batch_id}/{corp_name}_{rcept_no}_{doc_type}.md
"""

from __future__ import annotations

import dataclasses
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..parser.section_parser import ParsedReport, ReportSection
from ..parser.document_parser import ParsedDocument, DocumentSection
from ..config import DartConfig, SectionCode

logger = logging.getLogger(__name__)


def new_batch_id() -> str:
    """
    요청마다 고유한 배치 ID를 생성한다.
    형식: YYYYMMDD_HHMMSS_{4자리 hex}
    예)   20240312_153045_a3f2
    """
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    uid = uuid.uuid4().hex[:4]
    return f"{now}_{uid}"


class MarkdownBuilder:
    """
    ParsedReport / ParsedDocument 를 Obsidian Markdown 파일로 변환·저장한다.

    배치 저장 시 build_vault_multi() 등에서 batch_id 를 공유하여
    같은 폴더에 여러 기업의 .md 파일을 모은다.
    """

    def __init__(self, config: DartConfig) -> None:
        self._config = config

    # =========================================================================
    # DS002 정형 보고서 (ParsedReport)
    # =========================================================================

    def save(self, report: ParsedReport, batch_id: Optional[str] = None) -> Path:
        content = self._build_report_content(report)
        path = self._resolve_report_path(report, batch_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.info("저장: %s", path)
        return path

    def save_batch(
        self, reports: list[ParsedReport], batch_id: Optional[str] = None
    ) -> list[Path]:
        if batch_id is None:
            batch_id = new_batch_id()
        paths: list[Path] = []
        for report in reports:
            try:
                paths.append(self.save(report, batch_id=batch_id))
            except Exception as e:
                logger.error(
                    "저장 실패 [%s %s %s]: %s",
                    report.corp_name, report.bsns_year, report.reprt_label, e,
                )
        return paths

    # =========================================================================
    # DS001 원문 파싱 보고서 (ParsedDocument)
    # =========================================================================

    def save_document(
        self,
        doc: ParsedDocument,
        batch_id: Optional[str] = None,
        section_filter: Optional[list[str]] = None,
    ) -> Path:
        """
        ParsedDocument 를 .md 파일로 저장한다.

        Parameters
        ----------
        section_filter : list[str], optional
            저장할 섹션 제목 키워드.  None 이면 전체.
            예) ["사업의 내용"] → II. 사업의 내용만 저장
        """
        content = self._build_document_content(doc, section_filter)
        path = self._resolve_document_path(doc, batch_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.info("저장: %s", path)
        return path

    def save_document_batch(
        self,
        docs: list[ParsedDocument],
        batch_id: Optional[str] = None,
        section_filter: Optional[list[str]] = None,
    ) -> list[Path]:
        if batch_id is None:
            batch_id = new_batch_id()
        paths: list[Path] = []
        for doc in docs:
            try:
                paths.append(
                    self.save_document(doc, batch_id=batch_id, section_filter=section_filter)
                )
            except Exception as e:
                logger.error("저장 실패 [%s %s]: %s", doc.corp_name, doc.rcept_no, e)
        return paths

    # =========================================================================
    # 경로 결정
    # =========================================================================

    def _resolve_report_path(self, report: ParsedReport, batch_id: Optional[str]) -> Path:
        safe_corp = self._safe(report.corp_name)
        filename  = f"{report.bsns_year}_{report.reprt_label}.md"
        if batch_id:
            # {output_dir}/{batch_id}/{corp_name}_{filename}
            return self._config.output_dir / batch_id / f"{safe_corp}_{filename}"
        # {output_dir}/{corp_name}/{filename}
        return self._config.output_dir / safe_corp / filename

    def _resolve_document_path(self, doc: ParsedDocument, batch_id: Optional[str]) -> Path:
        safe_corp = self._safe(doc.corp_name)
        safe_type = self._safe(doc.doc_type)
        filename  = f"{doc.rcept_no}_{safe_type}.md"
        if batch_id:
            return self._config.output_dir / batch_id / f"{safe_corp}_{filename}"
        return self._config.output_dir / safe_corp / filename

    @staticmethod
    def _safe(name: str) -> str:
        for ch in r'\/:*?"<>|':
            name = name.replace(ch, "_")
        return name.strip()

    # =========================================================================
    # DS002 Markdown 빌드
    # =========================================================================

    def _build_report_content(self, report: ParsedReport) -> str:
        lines: list[str] = []
        lines += self._report_frontmatter(report)
        lines.append(f"# {report.corp_name} {report.bsns_year} {report.reprt_label}\n")
        lines += self._report_info_table(report)
        for section_code in SectionCode.all():
            section = report.sections.get(section_code)
            if section is None or section.is_empty:
                continue
            lines += self._section_block(section)
        lines.append("\n---")
        lines.append(f"*생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")
        return "\n".join(lines)

    def _report_frontmatter(self, report: ParsedReport) -> list[str]:
        available = ", ".join(
            f'"{SectionCode.label(s)}"' for s in report.available_sections
        )
        return [
            "---",
            f"corp_code: {report.corp_code}",
            f"corp_name: {report.corp_name}",
            f"bsns_year: {report.bsns_year}",
            f"reprt_code: {report.reprt_code}",
            f"reprt_label: {report.reprt_label}",
            f"rcept_no: {report.rcept_no}",
            f"tags: [DART, {report.corp_name}, {report.reprt_label}, {report.bsns_year}]",
            f"sections: [{available}]",
            "---\n",
        ]

    def _report_info_table(self, report: ParsedReport) -> list[str]:
        dart_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={report.rcept_no}"
        return [
            "## 기본 정보\n",
            "| 항목 | 내용 |",
            "| --- | --- |",
            f"| 회사명 | {report.corp_name} |",
            f"| 고유번호 | {report.corp_code} |",
            f"| 사업연도 | {report.bsns_year} |",
            f"| 보고서 종류 | {report.reprt_label} |",
            f"| 접수번호 | [{report.rcept_no}]({dart_url}) |",
            f"| 데이터 섹션 수 | {len(report.available_sections)} |",
            "",
        ]

    def _section_block(self, section: ReportSection) -> list[str]:
        lines: list[str] = [f"\n## {section.label}\n"]
        if not section.rows:
            lines.append("*데이터 없음*\n")
            return lines
        cols = section.columns
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("| " + " | ".join(["---"] * len(cols)) + " |")
        for row in section.rows:
            cells = [
                str(row.get(c, "")) if row.get(c) is not None else "" for c in cols
            ]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
        return lines

    # =========================================================================
    # DS001 원문 Markdown 빌드
    # =========================================================================

    def _build_document_content(
        self, doc: ParsedDocument, section_filter: Optional[list[str]]
    ) -> str:
        lines: list[str] = []
        lines += self._document_frontmatter(doc)

        year = doc.period_from[:4] if doc.period_from else ""
        title_str = f"{doc.corp_name} {year} {doc.doc_type}".strip()
        lines.append(f"# {title_str}\n")
        lines += self._document_info_table(doc)

        target_sections = (
            self._filter_sections(doc.sections, section_filter)
            if section_filter
            else doc.sections
        )

        for sec in target_sections:
            lines.append(sec.full_md)
            lines.append("")

        lines.append("\n---")
        lines.append(f"*생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")
        return "\n".join(lines)

    def _document_frontmatter(self, doc: ParsedDocument) -> list[str]:
        year = doc.period_from[:4] if doc.period_from else ""
        tags_str = ", ".join(t for t in [doc.corp_name, doc.doc_type, year] if t)
        return [
            "---",
            f"corp_name: {doc.corp_name}",
            f"doc_type: {doc.doc_type}",
            f"rcept_no: {doc.rcept_no}",
            f"period_from: {doc.period_from}",
            f"period_to: {doc.period_to}",
            f"tags: [DART, {tags_str}]",
            f"section_count: {len(doc.sections)}",
            "---\n",
        ]

    def _document_info_table(self, doc: ParsedDocument) -> list[str]:
        dart_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={doc.rcept_no}"
        period = (
            f"{doc.period_from} ~ {doc.period_to}" if doc.period_from else "-"
        )
        return [
            "## 기본 정보\n",
            "| 항목 | 내용 |",
            "| --- | --- |",
            f"| 회사명 | {doc.corp_name} |",
            f"| 보고서 종류 | {doc.doc_type} |",
            f"| 접수번호 | [{doc.rcept_no}]({dart_url}) |",
            f"| 사업연도 | {period} |",
            f"| 섹션 수 | {len(doc.sections)} |",
            "",
        ]

    @staticmethod
    def _filter_sections(
        sections: list[DocumentSection], keywords: list[str]
    ) -> list[DocumentSection]:
        """
        키워드가 포함된 섹션만 반환한다.

        매칭 전략 — 세 단계:
        ① 자식 섹션 중 키워드 매칭이 있으면 → 해당 자식만 추출, 현재는 컨테이너
        ② 자식 매칭 없고 현재 섹션이 리프(자식 없음) → 제목 매칭 시 포함
        ③ 자식 매칭 없고 현재 섹션이 컨테이너(자식 있음) → 포함하지 않음
           (자식들 중 아무것도 매칭 안 됐으므로, 현재 제목이 매칭돼도 관련 없는
            자식이 딸려오지 않도록 차단)

        ※ 하위 섹션 없이 챕터 전체를 가져오려면 챕터 고유 키워드 사용:
           "II. 사업의 내용" 전체 원할 때 → section_filter=["II."] or ["사업의 내용"]
           → 단, 자식 중 매칭이 먼저 일어나므로 자식 제목과 겹치지 않는 표현 권장
        """
        result: list[DocumentSection] = []
        for sec in sections:
            # ① 자식 먼저 재귀 탐색
            if sec.children:
                matched_children = MarkdownBuilder._filter_sections(
                    sec.children, keywords
                )
                if matched_children:
                    shallow = dataclasses.replace(sec, children=matched_children)
                    result.append(shallow)
                # ③ 자식 있는데 매칭 없음 → 현재 제목이 매칭돼도 포함하지 않음
            else:
                # ② 리프 섹션: 제목 매칭 시 포함
                if any(kw in sec.title for kw in keywords):
                    result.append(sec)
        return result
