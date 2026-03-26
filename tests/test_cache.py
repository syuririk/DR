"""
tests/test_cache.py
CorpCodeCache 단위 테스트
"""

import json
import pytest

from dart_report_reader.cache.corp_code import CorpCodeCache
from tests.conftest import MOCK_CORPS, make_corp_code_zip


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

    def test_refresh_overwrites_cache(self, config, corp_json_cache, corp_zip, mock_client):
        """refresh() 는 캐시 파일이 있어도 덮어쓴다."""
        # 기존 캐시에 없는 데이터로 ZIP 재생성
        new_corps = [{"corp_code": "99999999", "corp_name": "테스트기업", "stock_code": "999999", "modify_date": "20240101"}]
        import io, zipfile
        xml = "<r><list><corp_code>99999999</corp_code><corp_name>테스트기업</corp_name><stock_code>999999</stock_code><modify_date>20240101</modify_date></list></r>"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("CORPCODE.xml", xml.encode())
        mock_client.get_zip.return_value = buf.getvalue()

        cache = CorpCodeCache(config, mock_client)
        cache.refresh()

        assert len(cache) == 1
        assert cache.get_info("99999999")["corp_name"] == "테스트기업"

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
        # "카카오" 는 목록에 1개만 있음
        assert cache.resolve("카카오") == "00400473"

    def test_resolve_by_partial_name_multi_raises(self, config, mock_client):
        """부분 검색 결과가 여러 개일 때 KeyError."""
        import io, zipfile
        xml = """<r>
        <list><corp_code>00000001</corp_code><corp_name>삼성전자</corp_name><stock_code>005930</stock_code><modify_date>20240101</modify_date></list>
        <list><corp_code>00000002</corp_code><corp_name>삼성SDI</corp_name><stock_code>006400</stock_code><modify_date>20240101</modify_date></list>
        </r>"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("CORPCODE.xml", xml.encode())
        mock_client.get_zip.return_value = buf.getvalue()

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
