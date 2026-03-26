"""
tests/conftest.py
공통 pytest 픽스처
"""

from __future__ import annotations

import json
import zipfile
import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dart_report_reader.config import DartConfig
from dart_report_reader.api.client import DartHttpClient


# ---------------------------------------------------------------------------
# 픽스처: 기본 설정
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_dirs(tmp_path: Path):
    cache_dir  = tmp_path / "cache"
    output_dir = tmp_path / "vault"
    cache_dir.mkdir()
    output_dir.mkdir()
    return cache_dir, output_dir


@pytest.fixture
def config(tmp_dirs) -> DartConfig:
    cache_dir, output_dir = tmp_dirs
    return DartConfig(
        api_key="TEST_KEY_0000000000000000000000000000000000000000",
        cache_dir=cache_dir,
        output_dir=output_dir,
    )


# ---------------------------------------------------------------------------
# 픽스처: Mock 기업 코드 데이터
# ---------------------------------------------------------------------------

MOCK_CORPS = [
    {"corp_code": "00126380", "corp_name": "삼성전자", "stock_code": "005930", "modify_date": "20240101"},
    {"corp_code": "00164742", "corp_name": "현대자동차", "stock_code": "005380", "modify_date": "20240101"},
    {"corp_code": "00164779", "corp_name": "SK하이닉스", "stock_code": "000660", "modify_date": "20240101"},
    {"corp_code": "00400473", "corp_name": "카카오", "stock_code": "035720", "modify_date": "20240101"},
    {"corp_code": "00266961", "corp_name": "NAVER", "stock_code": "035420", "modify_date": "20240101"},
]


def make_corp_code_zip() -> bytes:
    """테스트용 기업 코드 ZIP(XML) 생성."""
    xml_lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<result>"]
    for c in MOCK_CORPS:
        xml_lines.append("<list>")
        xml_lines.append(f"<corp_code>{c['corp_code']}</corp_code>")
        xml_lines.append(f"<corp_name>{c['corp_name']}</corp_name>")
        xml_lines.append(f"<stock_code>{c['stock_code']}</stock_code>")
        xml_lines.append(f"<modify_date>{c['modify_date']}</modify_date>")
        xml_lines.append("</list>")
    xml_lines.append("</result>")
    xml_bytes = "\n".join(xml_lines).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("CORPCODE.xml", xml_bytes)
    return buf.getvalue()


@pytest.fixture
def corp_zip() -> bytes:
    return make_corp_code_zip()


@pytest.fixture
def corp_json_cache(tmp_dirs) -> Path:
    """캐시 JSON 파일을 미리 작성한 tmp 경로."""
    cache_dir, _ = tmp_dirs
    path = cache_dir / "corp_codes.json"
    path.write_text(json.dumps(MOCK_CORPS, ensure_ascii=False), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# 픽스처: Mock API 응답
# ---------------------------------------------------------------------------

MOCK_DIVIDEND_ROWS = [
    {
        "corp_code": "00126380",
        "corp_name": "삼성전자",
        "se": "주당 현금배당금(원)",
        "stock_knd": "보통주",
        "thstrm": "361",
        "frmtrm": "1444",
        "lwfr": "1444",
    }
]

MOCK_EMPLOYEE_ROWS = [
    {
        "corp_code": "00126380",
        "corp_name": "삼성전자",
        "se": "정규직",
        "fo_bbm": "사무직",
        "jan_co": "114100",
        "feb_co": "",
        "reform_bfe_emp_co_rgllbr": "114100",
        "reform_bfe_emp_co_cnttk": "5200",
        "sm": "119300",
        "avrg_cnwk_sdytrm": "12.5",
        "fyer_salary_totamt": "9850000",
        "jan_salary_am": "8250000",
    }
]

MOCK_EXECUTIVE_ROWS = [
    {
        "corp_code": "00126380",
        "corp_name": "삼성전자",
        "nm": "이재용",
        "sexdstn": "남",
        "birth_ym": "196810",
        "ofcps": "회장",
        "rgist_exctv_at": "등기임원",
        "fte_at": "상근",
        "tenure_end_on": "20260331",
        "reform_bfe_emp_yn": "N",
    }
]


@pytest.fixture
def mock_client(config: DartConfig) -> MagicMock:
    """DartHttpClient Mock."""
    client = MagicMock(spec=DartHttpClient)
    client.config = config
    return client
