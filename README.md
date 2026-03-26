# dart-report-reader

DART(금융감독원 전자공시시스템) OpenAPI를 통해 **정기보고서를 파싱**하고
**Obsidian Vault(.md 파일)** 로 저장하는 Python 라이브러리입니다.

[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org)
[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/YOUR_GITHUB_ID/dart-report-reader/blob/main/notebooks/dart_report_reader_colab.ipynb)

---

## 주요 기능

| 기능 | 설명 |
|---|---|
| **기업 코드 캐싱** | 전체 기업 고유번호 목록을 로컬 JSON으로 캐싱, 회사명/종목코드로 자동 변환 |
| **정기보고서 파싱** | 배당·임원·직원·최대주주·감사·증권 등 25개 항목 자동 파싱 |
| **Vault 생성** | 파싱 결과를 Obsidian 호환 `.md` 파일로 저장 (YAML Frontmatter + 테이블) |
| **일괄 처리** | 여러 기업 × 여러 연도 × 여러 보고서 종류를 한 번에 처리 |

---

## 설치

### pip (GitHub)
```bash
pip install git+https://github.com/YOUR_GITHUB_ID/dart-report-reader.git
```

### 개발 모드 (Poetry)
```bash
git clone https://github.com/YOUR_GITHUB_ID/dart-report-reader.git
cd dart-report-reader
poetry install
```

---

## 빠른 시작

```python
from dart_report_reader import DartReportReader, DartConfig, ReportCode, SectionCode

# 1. 설정
cfg = DartConfig(
    api_key="YOUR_DART_API_KEY",
    cache_dir="./cache",      # 기업 코드 캐시 저장 위치
    output_dir="./vault",     # .md 파일 출력 위치
)

# 2. 초기화 (기업 코드 캐시 로드 — 최초 1회 다운로드)
reader = DartReportReader(cfg)
reader.init()

# 3. 기업 검색
results = reader.search_corp("삼성")
# → [{"corp_name": "삼성전자", "stock_code": "005930", ...}, ...]

# 4. 단일 보고서 파싱
report = reader.fetch_report(
    corp="삼성전자",       # 회사명 / 종목코드 / corp_code 모두 가능
    bsns_year=2023,
    reprt_code=ReportCode.ANNUAL,
    sections=[SectionCode.DIVIDEND, SectionCode.EXECUTIVE, SectionCode.EMPLOYEE],
)

# 5. Vault 생성 (여러 연도 일괄)
paths = reader.build_vault(
    corp="삼성전자",
    years=[2021, 2022, 2023],
    reprt_codes=[ReportCode.ANNUAL],
)
```

---

## 출력 구조

```
vault/
└── 삼성전자/
    ├── 2021_사업보고서.md
    ├── 2022_사업보고서.md
    └── 2023_사업보고서.md
```

각 `.md` 파일은 **YAML Frontmatter + 섹션별 Markdown 테이블** 형식입니다.

```markdown
---
corp_code: 00126380
corp_name: 삼성전자
bsns_year: 2023
reprt_label: 사업보고서
tags: [DART, 삼성전자, 사업보고서, 2023]
---

# 삼성전자 2023 사업보고서

## 기본 정보
| 항목 | 내용 |
| --- | --- |
| 회사명 | 삼성전자 |
...

## 배당에 관한 사항
| corp_name | se | stock_knd | thstrm | frmtrm |
| --- | --- | --- | --- | --- |
| 삼성전자 | 주당 현금배당금(원) | 보통주 | 361 | 1444 |
```

---

## 설정 옵션 (`DartConfig`)

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `api_key` | str | `$DART_API_KEY` | DART OpenAPI 인증키 |
| `cache_dir` | Path | `~/.dart_cache` | 기업 코드 캐시 디렉터리 |
| `output_dir` | Path | `./dart_vault` | .md 파일 출력 디렉터리 |
| `sections` | list[str] | 전체 25개 | 파싱할 섹션 코드 목록 |
| `timeout` | int | 30 | HTTP 타임아웃(초) |
| `retry` | int | 3 | 실패 시 재시도 횟수 |

---

## 보고서 종류 (`ReportCode`)

| 상수 | 코드 | 설명 |
|---|---|---|
| `ReportCode.ANNUAL` | 11011 | 사업보고서 |
| `ReportCode.HALF_YEAR` | 11012 | 반기보고서 |
| `ReportCode.Q1` | 11013 | 1분기보고서 |
| `ReportCode.Q3` | 11014 | 3분기보고서 |

---

## 테스트

```bash
poetry run pytest tests/ -v
```

---

## Colab에서 실행

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/YOUR_GITHUB_ID/dart-report-reader/blob/main/notebooks/dart_report_reader_colab.ipynb)

노트북에서 `YOUR_DART_API_KEY_HERE` 부분만 본인 API 키로 교체하면 바로 실행됩니다.

---

## DART API 인증키 발급

1. [DART OpenAPI](https://opendart.fss.or.kr) 회원가입
2. 인증키 신청/관리 → 인증키 신청
3. 발급받은 키를 `DartConfig(api_key=...)` 에 입력

---

## 라이선스

MIT
