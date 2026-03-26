"""
tests/test_cache.py
CorpCodeCache 단위 테스트
"""

import json
import pytest
from lxml import etree

from dart_report_reader.cache.corp_code import CorpCodeCache
from tests.conftest import MOCK_CORPS, make_corp_code_root


def make_single_corp_root(corp_code, corp_name, stock_code="", modify_date="20240101"):
    """단일 기업 etree root 생성 헬퍼."""
    xml = (
        f'<r><list>'
        f'<corp_code>{corp_code}</corp_code>'
        f'<corp_name>{corp_name}</corp_name>'
        f'<stock_code>{stock_code}</stock_code>'
        f'<modify_date>{modify_date}</modify_date>'
        f'</list></r>'
    )
    parser = etree.XMLParser(recover=True)
    return etree.fromstring(xml.encode(), parser)


class TestCorpCodeCache:

    # ------------------------------------------------------------------
    # load() — 캐시 파일 있을 때
    # ------------------------------------------------------------------

    def test_load_from_existing_cache(self, config, corp_json_cache, mock_client):
        """캐시 JSON 파일이 있으면 서버를 호출하지 않고 로드한다."""
        cache = CorpCodeCache(config, mock_client)
        cache.load()

        mock_client.get_zip.assert_not_called()
        assert len(cache) == len(MOCK_CORPS)

    # ------------------------------------------------------------------
    # load() — 캐시 파일 없을 때
    # ------------------------------------------------------------------

    def test_load_downloads_when_no_cache(self, config, corp_zip, mock_client):
        """캐시 파일이 없으면 DART 서버에서 다운로드한다."""
        mock_client.get_zip.return_value = corp_zip
        cache = CorpCodeCache(config, mock_client)
        cache.load()

        mock_client.get_zip.assert_called_once_with("corpCode")
        assert len(cache) == len(MOCK_CORPS)
        assert config.corp_code_cache_path.exists()

    # ------------------------------------------------------------------
    # refresh()
    # ------------------------------------------------------------------

    def test_refresh_overwrites_cache(self, config, corp_json_cache, mock_client):
        """refresh() 는 캐시 파일이 있어도 덮어쓴다."""
        new_root = make_single_corp_root("99999999", "테스트기업", "999999")
        mock_client.get_zip.return_value = new_root

        cache = CorpCodeCache(config, mock_client)
        cache.refresh()

        assert len(cache) == 1
        assert cache.get_info("99999999")["corp_name"] == "테스트기업"

    def test_refresh_saves_json_cache(self, config, mock_client, corp_zip):
        """refresh() 후 JSON 캐시 파일이 생성되어야 한다."""
        mock_client.get_zip.return_value = corp_zip
        cache = CorpCodeCache(config, mock_client)
        cache.refresh()

        assert config.corp_code_cache_path.exists()
        saved = json.loads(config.corp_code_cache_path.read_text(encoding="utf-8"))
        assert len(saved) == len(MOCK_CORPS)

    # ------------------------------------------------------------------
    # resolve()
    # ------------------------------------------------------------------

    def test_resolve_by_corp_code(self, config, corp_json_cache, mock_client):
        cache = CorpCodeCache(config, mock_client)
        cache.load()
        assert cache.resolve("00126380") == "00126380"

    def test_resolve_by_stock_code(self, config, corp_json_cache, mock_client):
        cache = CorpCodeCache(config, mock_client)
        cache.load()
        assert cache.resolve("005930") == "00126380"

    def test_resolve_by_exact_name(self, config, corp_json_cache, mock_client):
        cache = CorpCodeCache(config, mock_client)
        cache.load()
        assert cache.resolve("삼성전자") == "00126380"

    def test_resolve_by_partial_name_single_match(self, config, corp_json_cache, mock_client):
        cache = CorpCodeCache(config, mock_client)
        cache.load()
        assert cache.resolve("카카오") == "00400473"

    def test_resolve_by_partial_name_multi_raises(self, config, mock_client):
        """부분 검색 결과가 여러 개일 때 KeyError."""
        two_corps = [
            {"corp_code": "00000001", "corp_name": "삼성전자",  "stock_code": "005930", "modify_date": "20240101"},
            {"corp_code": "00000002", "corp_name": "삼성SDI",   "stock_code": "006400", "modify_date": "20240101"},
        ]
        mock_client.get_zip.return_value = make_corp_code_root(two_corps)

        cache = CorpCodeCache(config, mock_client)
        cache.refresh()

        with pytest.raises(KeyError, match="2개"):
            cache.resolve("삼성")

    def test_resolve_unknown_raises(self, config, corp_json_cache, mock_client):
        cache = CorpCodeCache(config, mock_client)
        cache.load()
        with pytest.raises(KeyError):
            cache.resolve("존재하지않는회사XYZ")

    # ------------------------------------------------------------------
    # search_name()
    # ------------------------------------------------------------------

    def test_search_name(self, config, corp_json_cache, mock_client):
        cache = CorpCodeCache(config, mock_client)
        cache.load()
        results = cache.search_name("삼성")
        assert any(r["corp_name"] == "삼성전자" for r in results)

    def test_search_name_no_result(self, config, corp_json_cache, mock_client):
        cache = CorpCodeCache(config, mock_client)
        cache.load()
        assert cache.search_name("존재하지않는키워드ZZZZZ") == []

    # ------------------------------------------------------------------
    # get_info()
    # ------------------------------------------------------------------

    def test_get_info(self, config, corp_json_cache, mock_client):
        cache = CorpCodeCache(config, mock_client)
        cache.load()
        info = cache.get_info("00126380")
        assert info["corp_name"] == "삼성전자"
        assert info["stock_code"] == "005930"

    def test_get_info_missing_returns_none(self, config, corp_json_cache, mock_client):
        cache = CorpCodeCache(config, mock_client)
        cache.load()
        assert cache.get_info("99999999") is None

    # ------------------------------------------------------------------
    # _parse_root() — XML 파싱 정확성
    # ------------------------------------------------------------------

    def test_parse_root_extracts_all_fields(self, config, mock_client):
        root = make_single_corp_root("00126380", "삼성전자", "005930", "20240101")
        mock_client.get_zip.return_value = root

        cache = CorpCodeCache(config, mock_client)
        cache.refresh()

        info = cache.get_info("00126380")
        assert info["corp_code"]   == "00126380"
        assert info["corp_name"]   == "삼성전자"
        assert info["stock_code"]  == "005930"
        assert info["modify_date"] == "20240101"

    def test_parse_root_skips_empty_corp_code(self, config, mock_client):
        """corp_code 가 비어 있는 행은 스킵되어야 한다."""
        xml = (
            "<r>"
            "<list><corp_code></corp_code><corp_name>빈코드기업</corp_name>"
            "<stock_code></stock_code><modify_date>20240101</modify_date></list>"
            "<list><corp_code>00126380</corp_code><corp_name>삼성전자</corp_name>"
            "<stock_code>005930</stock_code><modify_date>20240101</modify_date></list>"
            "</r>"
        )
        parser = etree.XMLParser(recover=True)
        root = etree.fromstring(xml.encode(), parser)
        mock_client.get_zip.return_value = root

        cache = CorpCodeCache(config, mock_client)
        cache.refresh()

        assert len(cache) == 1
        assert cache.get_info("00126380") is not None
