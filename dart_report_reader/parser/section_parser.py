"""
dart_report_reader/parser/section_parser.py
DART API 응답 데이터 → 구조화된 섹션 객체로 변환
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..config import SectionCode


# ---------------------------------------------------------------------------
# 데이터 모델
# ---------------------------------------------------------------------------

@dataclass
class ReportSection:
    """
    단일 섹션 파싱 결과.

    Attributes
    ----------
    code : str
        섹션 코드 (SectionCode 상수).
    label : str
        한글 섹션 이름.
    rows : list[dict]
        원본 API 응답 행 리스트.
    columns : list[str]
        컬럼명 리스트.
    """
    code: str
    label: str
    rows: list[dict] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.rows and not self.columns:
            self.columns = list(self.rows[0].keys())

    @property
    def is_empty(self) -> bool:
        return len(self.rows) == 0


@dataclass
class ParsedReport:
    """
    한 기업의 특정 연도·보고서 종류에 대한 전체 파싱 결과.
    """
    corp_code: str
    corp_name: str
    bsns_year: str
    reprt_code: str
    reprt_label: str
    rcept_no: str                                    # 접수번호
    sections: dict[str, ReportSection] = field(default_factory=dict)

    @property
    def available_sections(self) -> list[str]:
        return [k for k, v in self.sections.items() if not v.is_empty]


# ---------------------------------------------------------------------------
# 파서
# ---------------------------------------------------------------------------

class SectionParser:
    """
    API 응답 dict → ReportSection / ParsedReport 변환.
    """

    # 컬럼 한글 레이블 매핑 (주요 공통 컬럼)
    _COL_LABELS: dict[str, str] = {
        "corp_name":      "회사명",
        "corp_code":      "고유번호",
        "bsns_year":      "사업연도",
        "se":             "구분",
        "stock_knd":      "주식 종류",
        "thstrm":         "당기",
        "frmtrm":         "전기",
        "lwfr":           "전전기",
        "nm":             "성명",
        "sexdstn":        "성별",
        "birth_ym":       "출생연월",
        "ofcps":          "직위",
        "tenure_end_on":  "임기만료일",
        "acntng_nm":      "계정명",
        "thstrm_amount":  "당기금액",
        "frmtrm_amount":  "전기금액",
        "rcept_no":       "접수번호",
        "rpt_nm":         "보고서명",
        "flr_nm":         "제출인",
        "rcept_dt":       "접수일자",
    }

    @classmethod
    def col_label(cls, col: str) -> str:
        return cls._COL_LABELS.get(col, col)

    # ------------------------------------------------------------------

    def parse_section(
        self,
        section_code: str,
        rows: list[dict],
    ) -> ReportSection:
        """원본 행 리스트를 ReportSection 으로 변환."""
        cleaned = [self._clean_row(r) for r in rows]
        return ReportSection(
            code=section_code,
            label=SectionCode.label(section_code),
            rows=cleaned,
        )

    def parse_report(
        self,
        corp_code: str,
        corp_name: str,
        bsns_year: str,
        reprt_code: str,
        reprt_label: str,
        rcept_no: str,
        raw_sections: dict[str, list[dict]],
    ) -> ParsedReport:
        """
        여러 섹션의 원본 데이터를 ParsedReport 로 변환.

        Parameters
        ----------
        raw_sections : dict[str, list[dict]]
            {섹션코드: API 응답 행 리스트}
        """
        sections: dict[str, ReportSection] = {}
        for code, rows in raw_sections.items():
            sections[code] = self.parse_section(code, rows)

        return ParsedReport(
            corp_code=corp_code,
            corp_name=corp_name,
            bsns_year=bsns_year,
            reprt_code=reprt_code,
            reprt_label=reprt_label,
            rcept_no=rcept_no,
            sections=sections,
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _clean_row(row: dict[str, Any]) -> dict[str, Any]:
        """
        공통 노이즈 제거:
        - 앞뒤 공백 제거
        - '-' 단독 값 → None
        """
        cleaned: dict[str, Any] = {}
        for k, v in row.items():
            if isinstance(v, str):
                v = v.strip()
                if v in ("-", "–", "—", ""):
                    v = None
            cleaned[k] = v
        return cleaned
