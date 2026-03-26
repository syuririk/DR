"""
dart_report_reader/vault/md_builder.py
ParsedReport → Obsidian .md 파일 생성

출력 구조
---------
{output_dir}/
    {corp_name}/
        {bsns_year}_{reprt_label}.md
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..parser.section_parser import ParsedReport, ReportSection
from ..config import DartConfig, SectionCode

logger = logging.getLogger(__name__)


class MarkdownBuilder:
    """
    ParsedReport 객체를 Obsidian Markdown 파일로 변환·저장한다.
    """

    def __init__(self, config: DartConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def save(self, report: ParsedReport) -> Path:
        """
        ParsedReport 를 .md 파일로 저장하고 경로를 반환한다.

        출력 경로: {output_dir}/{corp_name}/{bsns_year}_{reprt_label}.md
        """
        content = self._build_content(report)
        path = self._resolve_path(report)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.info("저장 완료: %s", path)
        return path

    def save_batch(self, reports: list[ParsedReport]) -> list[Path]:
        """여러 보고서를 일괄 저장한다."""
        paths = []
        for report in reports:
            try:
                paths.append(self.save(report))
            except Exception as e:
                logger.error(
                    "저장 실패 [%s %s %s]: %s",
                    report.corp_name, report.bsns_year, report.reprt_label, e,
                )
        return paths

    # ------------------------------------------------------------------
    # 내부: 경로
    # ------------------------------------------------------------------

    def _resolve_path(self, report: ParsedReport) -> Path:
        safe_name = self._safe_filename(report.corp_name)
        filename = f"{report.bsns_year}_{report.reprt_label}.md"
        return self._config.output_dir / safe_name / filename

    @staticmethod
    def _safe_filename(name: str) -> str:
        """파일·디렉터리명에 쓸 수 없는 문자 제거."""
        for ch in r'\/:*?"<>|':
            name = name.replace(ch, "_")
        return name.strip()

    # ------------------------------------------------------------------
    # 내부: 콘텐츠 빌드
    # ------------------------------------------------------------------

    def _build_content(self, report: ParsedReport) -> str:
        lines: list[str] = []

        # --- YAML Frontmatter (Obsidian 태그/메타) ---
        lines += self._frontmatter(report)

        # --- 제목 ---
        lines.append(f"# {report.corp_name} {report.bsns_year} {report.reprt_label}\n")

        # --- 기본 정보 테이블 ---
        lines += self._info_table(report)

        # --- 섹션별 내용 ---
        for section_code in SectionCode.all():
            section = report.sections.get(section_code)
            if section is None or section.is_empty:
                continue
            lines += self._section_block(section)

        # --- 푸터 ---
        lines.append("\n---")
        lines.append(f"*생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")

        return "\n".join(lines)

    # ------------------------------------------------------------------

    def _frontmatter(self, report: ParsedReport) -> list[str]:
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

    def _info_table(self, report: ParsedReport) -> list[str]:
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
        """섹션 1개를 Markdown 블록으로 변환한다."""
        lines: list[str] = [f"\n## {section.label}\n"]

        if not section.rows:
            lines.append("*데이터 없음*\n")
            return lines

        # 컬럼 헤더
        cols = section.columns
        header = "| " + " | ".join(cols) + " |"
        separator = "| " + " | ".join(["---"] * len(cols)) + " |"
        lines.append(header)
        lines.append(separator)

        # 데이터 행
        for row in section.rows:
            cells = [str(row.get(c, "")) if row.get(c) is not None else "" for c in cols]
            lines.append("| " + " | ".join(cells) + " |")

        lines.append("")
        return lines
