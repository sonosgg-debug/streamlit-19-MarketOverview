# Streamlit 기반 초경량 MarketOverview 앱 설계 및 구축 계획

## 개요
기존 Next.js 기반 앱(`01 MarketOverview`)은 `node_modules`와 `.next` 빌드 캐시로 인해 수백 MB~1GB 이상의 용량을 차지하고, 지표 수정 시 프론트/백엔드/타입 정의를 모두 수정해야 하는 번거로움이 있었습니다.
본 계획은 신규 폴더인 `d:\AI Investing\01 MarketOverview2`에 **100% Python 기반의 초경량 Streamlit 앱**을 신규 구축하여, **기존의 미려한 다크모드 글래스모피즘(Glassmorphism) 카드 디자인과 콘텐츠 구성을 100% 유지**하면서도 **총 파일 크기 수십 KB 수준, 지표 추가 1줄 처리**의 극대화된 유지보수성을 제공하는 것을 목표로 합니다.

---

## 사용자 검토 및 확인 사항 (User Review Required)

> [!IMPORTANT]
> **1. 기존 프로젝트와의 격리**
> - 기존 `01 MarketOverview`는 전혀 수정하지 않고 원본 그대로 보존합니다.
> - 모든 신규 작업은 사용자가 생성한 `d:\AI Investing\01 MarketOverview2` 폴더 내에서 독립적으로 진행됩니다.

> [!TIP]
> **2. 고속 렌더링 아키텍처 (HTML/SVG 인라인 렌더링)**
> - Streamlit 기본 컴포넌트(Plotly 등)를 30~40개 띄우면 로딩 딜레이가 발생할 수 있습니다.
> - 이를 방지하기 위해 React 버전의 `IndicatorCard`와 동일한 **미니 일봉 캔들**과 **스파크라인 차트**를 **초경량 인라인 SVG/CSS 카드 컴포넌트**로 렌더링하여, 0.1초 만에 30개 이상의 카드가 부드럽게 표시되도록 구현합니다.

---

## 주요 아키텍처 및 구현 계획

### 1. 프로젝트 폴더 구조 (`01 MarketOverview2`)
```text
d:\AI Investing\01 MarketOverview2/
├── app.py                      # 메인 Streamlit 대시보드 UI (헤더, 탭, 카드 그리드)
├── market_data.py              # 데이터 수집, 가공, SKHY 프리미엄 계산 및 5분 캐시 (@st.cache_data)
├── config.py                   # 지표 목록 (US Market, K Market, Semiconductor) 및 메타데이터 정의
├── card_component.py           # 글래스모피즘 스타일 + 미니 일봉 캔들 + SVG 스파크라인 카드 렌더링
├── get_kospi_fundamentals.py   # 기존 검증된 KRX/네이버 거시지표 크롤러 엔진
├── krx_cache.json              # KRX 데이터 로컬 캐시 (초기 복사)
├── requirements.txt            # 필수 파이썬 패키지 목록
└── run.bat                     # 더블 클릭으로 브라우저 즉시 실행
```

---

### 2. 세부 컴포넌트 설계

#### [NEW] `config.py`
- 지표 리스트 정의:
  - **US Market (18개)**: `^GSPC`, `^IXIC`, `^TNX`, `CL=F`, `DX-Y.NYB`, `KRW=X`, `EWY`, `BTC-USD`, `GC=F`, `^VIX`, `FEAR_GREED`, `AAPL`, `MSFT`, `GOOGL`, `AMZN`, `META`, `TSLA`, `SPCX`
  - **K Market (13개)**: `^KS11`, `^KQ11`, `KOSPI200_FUTURES`, `KOSPI_PER`, `KOSPI_PBR`, `KOSPI_RSI`, `ADR_INFO`, `KOSPI_TRADE_VALUE`, `CUSTOMER_DEPOSITS`, `CREDIT_BALANCE`, `MARGIN_CALL`, `KOSPI200_NIGHT`, `VKOSPI`
  - **Semiconductor (15개)**: `^SOX`, `NVDA`, `MU`, `SNDK`, `DRAM`, `CCML`, `005930.KS`, `009150.KS`, `402340.KS`, `000660.KS`, `SKHY`, `SKHY_ADR_PREMIUM`, `285A.T`, `6981.T`, `688825.SS`
- 속성 설정: `name`, `negativeFavorable` (금리/환율/유가/VIX 등), `isIntegerOnly` (거래대금, 예탁금, 원화 주가 등).

#### [NEW] `market_data.py`
- **Yahoo Finance 병렬 수집**: `yfinance` 또는 고속 병렬 `requests`를 통해 시가/고가/저가/종가 및 최근 60일 히스토리 수집
- **CNN Fear & Greed 지수 수집**: CNN API 연동
- **KRX 거시지표 연동**: `krx_cache.json` 조회 및 자동 백그라운드 갱신
- **SKHY ADR Premium 계산**: SK하이닉스 본주, ADR, 환율을 결합한 괴리율 계산
- **Streamlit 캐싱**: `@st.cache_data(ttl=300)`을 적용하여 사용자 접속 및 탭 전환 시 0.1초 내 로딩

#### [NEW] `card_component.py`
- 기존 Next.js의 `IndicatorCard.tsx` 디자인 완벽 복원:
  - **다크모드 글래스모피즘**: 반투명 배경 (`rgba(24, 24, 27, 0.65)`), 미세 보더, 테두리 블러
  - **한국식 색상 코딩**: 상승(빨강 `#ef4444`), 하락(파랑 `#3b82f6`), 역방향 유리 지표(초록/빨강 반전)
  - **미니 일봉 캔들**: 윗꼬리, 몸통, 아랫꼬리가 정밀 비례하는 SVG/CSS 캔들
  - **스파크라인**: 최근 60영업일 종가 추세를 SVG 패스로 렌더링 (홀수: 옐로우 `#eab308`, 짝수: 슬레이트 `#94a3b8`)
  - **호버 효과**: 마우스 오버 시 살짝 떠오르고(`translateY(-3px)`) 그림자 강조

#### [NEW] `app.py`
- 와이드 레이아웃 (`layout="wide"`) 설정
- 헤더: 타이틀, 마지막 업데이트 시각, "🔄 새로고침" 버튼
- 탭 메뉴: `US Market`, `K Market`, `Semiconductor`
- 3열 반응형 그리드로 카드 목록 렌더링

#### [NEW] `requirements.txt` & `run.bat`
- 의존성: `streamlit`, `yfinance`, `requests`, `beautifulsoup4`, `pandas`, `pykrx`, `python-dotenv`
- 윈도우 배치 스크립트: 파이썬 가상환경 또는 기본 파이썬으로 `streamlit run app.py` 원클릭 실행

---

## 검증 계획 (Verification Plan)

### 1. 동작 및 데이터 정합성 검증
- 모든 3개 탭(미국 시장, 한국 시장, 반도체)에서 총 46개 지표가 누락 없이 정상 렌더링되는지 확인
- 신규 추가된 `CCML (Roundhill ETF)` 및 `SKHY ADR Premium`이 정확히 계산/표시되는지 검증
- 일봉 캔들(시/고/저/종)과 60일 스파크라인이 정상 출력되는지 확인

### 2. 성능 및 용량 검증
- 전체 프로젝트 폴더 용량이 수백 KB 수준으로 가벼운지 확인
- 페이지 첫 로딩 및 탭 전환 속도가 1초 이내로 즉각적인지 검증

### 3. 사용자 확인
- `run.bat` 실행을 통해 브라우저에서 직접 UI 비주얼 및 동작을 확인하실 수 있도록 안내
