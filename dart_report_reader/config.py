"""
dart_report_reader/config.py
DART OpenAPI 라이브러리 전역 설정 클래스
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# 보고서 코드 상수
# ---------------------------------------------------------------------------
class ReportCode:
    """DART reprt_code 상수."""
    ANNUAL      = "11011"  # 사업보고서
    HALF_YEAR   = "11012"  # 반기보고서
    Q1          = "11013"  # 1분기보고서
    Q3          = "11014"  # 3분기보고서

    _LABEL: dict[str, str] = {
        "11011": "사업보고서",
        "11012": "반기보고서",
        "11013": "1분기보고서",
        "11014": "3분기보고서",
    }

    @classmethod
    def label(cls, code: str) -> str:
        return cls._LABEL.get(code, code)

    @classmethod
    def all(cls) -> list[str]:
        return list(cls._LABEL.keys())


# ---------------------------------------------------------------------------
# 섹션(항목) 코드 상수
# ---------------------------------------------------------------------------
class SectionCode:
    """DART 사업보고서 내 항목 → API endpoint 매핑."""

    CAPITAL             = "irdsSttus"                        # 증자(감자)
    DIVIDEND            = "alotMatter"                       # 배당
    TREASURY_STOCK      = "tesstkAcqsDspsSttus"              # 자기주식
    MAJOR_HOLDER        = "hyslrSttus"                       # 최대주주 현황
    MAJOR_HOLDER_CHANGE = "hyslrChgSttus"                    # 최대주주 변동
    MINOR_HOLDER        = "mrhlSttus"                        # 소액주주
    EXECUTIVE           = "exctvSttus"                       # 임원 현황
    EMPLOYEE            = "empSttus"                         # 직원 현황
    EXEC_PAY_APPROVAL   = "drctrAdtAllMendngSttusGmtsckConfmAmount"  # 임원보수 주총 승인
    EXEC_PAY_ALL        = "hmvAuditAllSttus"                 # 임원·감사 전체 보수
    EXEC_PAY_INDIVIDUAL = "hmvAuditIndvdlBySttus"            # 임원·감사 개인별 보수
    TOP5_PAY            = "indvdlByPay"                      # 5억 이상 상위 5인
    NON_REG_EXEC_PAY    = "otrCprInvstmntSttus"              # 미등기임원 보수
    OUTSIDE_DIRECTOR    = "outcmpnyMgmtrNmsttus"             # 사외이사 현황
    AUDIT_OPINION       = "accnutAdtor"                      # 회계감사인 명칭·의견
    AUDIT_CONTRACT      = "adtServcCnclsSttus"               # 감사용역 계약
    NON_AUDIT_CONTRACT  = "accnutAdtorNonAdtServcCnclsSttus" # 비감사용역 계약
    STOCK_TOTAL         = "stockTotqySttus"                  # 주식 총수
    BONDS               = "cprndNrdmpBlce"                   # 회사채 미상환
    CP                  = "entrprsBilScritsNrdmpBlce"         # 기업어음 미상환
    SHORT_BOND          = "shrtpdScitsNrdmpBlce"             # 단기사채 미상환
    COND_CAPITAL        = "cndlCaplScritsNrdmpBlce"          # 조건부자본증권 미상환
    HYBRID              = "newCaplScritsNrdmpBlce"           # 신종자본증권 미상환
    DEBT_ISSUANCE       = "detScritsIsuAcmslt"               # 채무증권 발행실적
    PUBLIC_FUND         = "pssrpCptalUseDtls"                # 공모자금 사용내역
    PRIVATE_FUND        = "prvsrpCptalUseDtls"               # 사모자금 사용내역
    INVESTMENT          = "otrCprInvstmntSttus"              # 타법인 출자현황

    _LABEL: dict[str, str] = {
        "irdsSttus":                            "증자(감자) 현황",
        "alotMatter":                           "배당에 관한 사항",
        "tesstkAcqsDspsSttus":                  "자기주식 취득·처분",
        "hyslrSttus":                           "최대주주 현황",
        "hyslrChgSttus":                        "최대주주 변동",
        "mrhlSttus":                            "소액주주 현황",
        "exctvSttus":                           "임원 현황",
        "empSttus":                             "직원 현황",
        "drctrAdtAllMendngSttusGmtsckConfmAmount": "임원보수 주총 승인금액",
        "hmvAuditAllSttus":                     "임원·감사 전체 보수",
        "hmvAuditIndvdlBySttus":                "임원·감사 개인별 보수",
        "indvdlByPay":                          "개인별 보수(5억 이상 상위 5인)",
        "outcmpnyMgmtrNmsttus":                 "사외이사 현황",
        "accnutAdtor":                          "회계감사인",
        "adtServcCnclsSttus":                   "감사용역 계약",
        "accnutAdtorNonAdtServcCnclsSttus":     "비감사용역 계약",
        "stockTotqySttus":                      "주식 총수",
        "cprndNrdmpBlce":                       "회사채 미상환 잔액",
        "entrprsBilScritsNrdmpBlce":            "기업어음 미상환 잔액",
        "shrtpdScitsNrdmpBlce":                 "단기사채 미상환 잔액",
        "cndlCaplScritsNrdmpBlce":              "조건부자본증권 미상환 잔액",
        "newCaplScritsNrdmpBlce":               "신종자본증권 미상환 잔액",
        "detScritsIsuAcmslt":                   "채무증권 발행실적",
        "pssrpCptalUseDtls":                    "공모자금 사용내역",
        "prvsrpCptalUseDtls":                   "사모자금 사용내역",
        "otrCprInvstmntSttus":                  "타법인 출자현황",
    }

    @classmethod
    def label(cls, code: str) -> str:
        return cls._LABEL.get(code, code)

    @classmethod
    def all(cls) -> list[str]:
        return list(cls._LABEL.keys())


# ---------------------------------------------------------------------------
# DartConfig
# ---------------------------------------------------------------------------
@dataclass
class DartConfig:
    """
    DART 라이브러리 전역 설정.

    Parameters
    ----------
    api_key : str
        DART OpenAPI 인증키.  환경변수 ``DART_API_KEY`` 로도 지정 가능.
    cache_dir : str | Path
        기업 고유번호 캐시 파일을 저장할 디렉터리.
        기본값: ``~/.dart_cache``
    output_dir : str | Path
        생성된 .md 파일(Obsidian Vault)을 저장할 디렉터리.
        기본값: ``./dart_vault``
    sections : list[str]
        파싱할 섹션 코드 목록.  기본값: SectionCode.all() 전부.
    timeout : int
        HTTP 요청 타임아웃(초).  기본값: 30.
    retry : int
        실패 시 재시도 횟수.  기본값: 3.
    encoding : str
        응답 인코딩.  기본값: ``utf-8``.
    """

    api_key: str = field(default="")
    cache_dir: Path = field(default_factory=lambda: Path.home() / ".dart_cache")
    output_dir: Path = field(default_factory=lambda: Path("./dart_vault"))
    sections: list[str] = field(default_factory=SectionCode.all)
    timeout: int = 30
    retry: int = 3
    encoding: str = "utf-8"

    # ------------------------------------------------------------------
    def __post_init__(self) -> None:
        # 환경변수 폴백
        if not self.api_key:
            self.api_key = os.environ.get("DART_API_KEY", "")
        if not self.api_key:
            raise ValueError(
                "api_key 가 비어 있습니다. "
                "DartConfig(api_key='...') 또는 환경변수 DART_API_KEY 를 설정하세요."
            )

        # Path 타입 보장
        self.cache_dir = Path(self.cache_dir)
        self.output_dir = Path(self.output_dir)

        # 디렉터리 생성
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    @classmethod
    def from_env(
        cls,
        cache_dir: Optional[str] = None,
        output_dir: Optional[str] = None,
        **kwargs,
    ) -> "DartConfig":
        """
        환경변수 ``DART_API_KEY`` 를 사용해 Config 를 생성하는 팩토리.

        Examples
        --------
        >>> cfg = DartConfig.from_env(cache_dir="/data/cache", output_dir="/data/vault")
        """
        init_kwargs: dict = {}
        if cache_dir:
            init_kwargs["cache_dir"] = Path(cache_dir)
        if output_dir:
            init_kwargs["output_dir"] = Path(output_dir)
        init_kwargs.update(kwargs)
        return cls(**init_kwargs)

    # ------------------------------------------------------------------
    @property
    def corp_code_cache_path(self) -> Path:
        """기업 고유번호 캐시 파일 경로."""
        return self.cache_dir / "corp_codes.json"

    @property
    def corp_code_zip_path(self) -> Path:
        """원본 ZIP 파일 경로."""
        return self.cache_dir / "corp_code.zip"
