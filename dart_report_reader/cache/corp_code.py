"""
dart_report_reader/cache/corp_code.py
기업 고유번호 캐시 관리

DART는 모든 API 조회에 8자리 corp_code 를 사용한다.
사용자가 종목코드(6자리) or 회사명으로 조회할 수 있도록
전체 목록 ZIP 을 받아 JSON 으로 캐싱한다.

캐시 파일 위치: DartConfig.cache_dir / corp_codes.json

변경 이력
---------
- XML 파싱을 BeautifulSoup → lxml.etree 로 교체 (레거시 방식 통일)
- get_zip() 이 이미 etree root 를 반환하므로 별도 ZIP 처리 불필요
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from lxml import etree

from ..config import DartConfig
from ..api.client import DartHttpClient

logger = logging.getLogger(__name__)


class CorpCodeCache:
    """
    기업 고유번호 캐시.

    사용 흐름
    ---------
    1. ``load()``         — 캐시 파일이 있으면 로드, 없으면 자동 갱신
    2. ``refresh()``      — DART 서버에서 최신 ZIP 다운로드 후 캐시 덮어쓰기
    3. ``resolve()``      — 회사명 / 종목코드 / corp_code → corp_code 변환
    4. ``search_name()``  — 회사명 부분 검색
    """

    def __init__(self, config: DartConfig, client: DartHttpClient) -> None:
        self._config = config
        self._client = client

        # {corp_code: {corp_name, stock_code, modify_date}}
        self._by_code:  dict[str, dict] = {}
        # {stock_code(6자리): corp_code}
        self._by_stock: dict[str, str]  = {}
        # {corp_name: corp_code}  (정확히 일치)
        self._by_name:  dict[str, str]  = {}

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def load(self) -> None:
        """
        캐시를 로드한다.

        캐시 파일이 존재하면 읽고,
        존재하지 않으면 DART 서버에서 자동 다운로드한다.
        """
        path = self._config.corp_code_cache_path
        if path.exists():
            logger.info("기업 코드 캐시 로드: %s", path)
            self._load_from_file(path)
        else:
            logger.info("캐시 파일 없음 — DART 서버에서 다운로드합니다.")
            self.refresh()

    def refresh(self) -> None:
        """
        DART 서버에서 최신 기업 코드 ZIP 을 다운로드하고
        캐시를 덮어쓴다.

        client.get_zip() 이 lxml etree root 를 반환하므로
        별도 ZIP/XML 파싱 없이 바로 사용한다.
        """
        logger.info("기업 코드 목록 다운로드 중...")
        root = self._client.get_zip("corpCode")

        records = self._parse_root(root)
        self._build_indexes(records)
        self._save_to_file(self._config.corp_code_cache_path, records)
        logger.info("기업 코드 캐시 저장 완료 (%d 개)", len(records))

    def resolve(self, identifier: str) -> str:
        """
        회사명 / 종목코드(6자리) / corp_code(8자리) → corp_code 반환.

        Raises
        ------
        KeyError
            해당 기업을 찾을 수 없을 때.
        """
        identifier = identifier.strip()

        # 8자리 숫자 → corp_code 로 간주
        if len(identifier) == 8 and identifier.isdigit():
            if identifier in self._by_code:
                return identifier
            raise KeyError(f"corp_code 를 찾을 수 없습니다: {identifier}")

        # 6자리 숫자 → 종목코드
        if len(identifier) == 6 and identifier.isdigit():
            code = self._by_stock.get(identifier)
            if code:
                return code
            raise KeyError(f"종목코드를 찾을 수 없습니다: {identifier}")

        # 회사명 정확 일치
        code = self._by_name.get(identifier)
        if code:
            return code

        # 회사명 부분 일치 (단일 결과일 때만)
        matches = self.search_name(identifier)
        if len(matches) == 1:
            return matches[0]["corp_code"]
        if len(matches) > 1:
            names = [m["corp_name"] for m in matches[:5]]
            raise KeyError(
                f"'{identifier}' 에 해당하는 기업이 {len(matches)}개입니다. "
                f"더 구체적인 이름을 사용하세요: {names}"
            )

        raise KeyError(f"기업을 찾을 수 없습니다: {identifier}")

    def search_name(self, keyword: str) -> list[dict]:
        """회사명에 keyword 가 포함된 기업 목록 반환."""
        keyword = keyword.strip().lower()
        return [
            info
            for info in self._by_code.values()
            if keyword in info["corp_name"].lower()
        ]

    def get_info(self, corp_code: str) -> Optional[dict]:
        """corp_code 로 기업 정보 반환."""
        return self._by_code.get(corp_code)

    def __len__(self) -> int:
        return len(self._by_code)

    # ------------------------------------------------------------------
    # 내부 메서드
    # ------------------------------------------------------------------

    @staticmethod
    def _text(element: "etree._Element", tag: str) -> str:
        """
        element 의 자식 태그 텍스트를 반환한다.
        태그가 없거나 텍스트가 None 이면 빈 문자열 반환.
        """
        child = element.find(tag)
        if child is None:
            return ""
        return (child.text or "").strip()

    def _parse_root(self, root: "etree._Element") -> list[dict]:
        """
        lxml etree root → 레코드 리스트 변환.

        DART corpCode.xml 구조:
            <result>
              <list>
                <corp_code>00126380</corp_code>
                <corp_name>삼성전자</corp_name>
                <stock_code>005930</stock_code>
                <modify_date>20240101</modify_date>
              </list>
              ...
            </result>
        """
        records: list[dict] = []
        for item in root.findall("list"):
            corp_code   = self._text(item, "corp_code")
            corp_name   = self._text(item, "corp_name")
            stock_code  = self._text(item, "stock_code")
            modify_date = self._text(item, "modify_date")

            if not corp_code:          # 코드가 없는 행은 스킵
                continue

            records.append({
                "corp_code":   corp_code,
                "corp_name":   corp_name,
                "stock_code":  stock_code,
                "modify_date": modify_date,
            })

        return records

    def _build_indexes(self, records: list[dict]) -> None:
        """레코드 리스트로 인덱스 딕셔너리를 구성한다."""
        self._by_code.clear()
        self._by_stock.clear()
        self._by_name.clear()

        for r in records:
            cc = r["corp_code"]
            self._by_code[cc] = r
            self._by_name[r["corp_name"]] = cc
            if r["stock_code"]:
                self._by_stock[r["stock_code"]] = cc

    def _save_to_file(self, path: Path, records: list[dict]) -> None:
        path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_from_file(self, path: Path) -> None:
        records = json.loads(path.read_text(encoding="utf-8"))
        self._build_indexes(records)
