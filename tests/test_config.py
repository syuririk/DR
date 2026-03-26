"""
tests/test_config.py
DartConfig 단위 테스트
"""

import os
import pytest
from pathlib import Path

from dart_report_reader.config import DartConfig, ReportCode, SectionCode


class TestDartConfig:

    def test_basic_creation(self, tmp_path):
        cfg = DartConfig(
            api_key="TESTKEY",
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "vault",
        )
        assert cfg.api_key == "TESTKEY"
        assert (tmp_path / "cache").exists()
        assert (tmp_path / "vault").exists()

    def test_env_fallback(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DART_API_KEY", "ENV_KEY")
        cfg = DartConfig(
            cache_dir=tmp_path / "cache",
            output_dir=tmp_path / "vault",
        )
        assert cfg.api_key == "ENV_KEY"

    def test_missing_api_key_raises(self, tmp_path, monkeypatch):
        monkeypatch.delenv("DART_API_KEY", raising=False)
        with pytest.raises(ValueError, match="api_key"):
            DartConfig(
                cache_dir=tmp_path / "cache",
                output_dir=tmp_path / "vault",
            )

    def test_from_env_factory(self, tmp_path, monkeypatch):
        monkeypatch.setenv("DART_API_KEY", "ENV_KEY2")
        cfg = DartConfig.from_env(
            cache_dir=str(tmp_path / "c"),
            output_dir=str(tmp_path / "v"),
        )
        assert isinstance(cfg.cache_dir, Path)
        assert isinstance(cfg.output_dir, Path)

    def test_corp_code_cache_path(self, config):
        assert config.corp_code_cache_path.name == "corp_codes.json"

    def test_sections_default_all(self, config):
        assert len(config.sections) == len(SectionCode.all())


class TestReportCode:

    def test_label(self):
        assert ReportCode.label("11011") == "사업보고서"
        assert ReportCode.label("11012") == "반기보고서"
        assert ReportCode.label("11013") == "1분기보고서"
        assert ReportCode.label("11014") == "3분기보고서"

    def test_all_returns_four(self):
        assert len(ReportCode.all()) == 4


class TestSectionCode:

    def test_label_known(self):
        assert SectionCode.label("alotMatter") == "배당에 관한 사항"
        assert SectionCode.label("exctvSttus") == "임원 현황"
        assert SectionCode.label("empSttus") == "직원 현황"

    def test_label_unknown_returns_code(self):
        assert SectionCode.label("unknown_code") == "unknown_code"

    def test_all_nonempty(self):
        assert len(SectionCode.all()) > 0
