# 📈 Daily Market Overview (Streamlit)

초경량 Python Streamlit 기반의 글로벌 매크로, 한국 시장, 반도체 공급망 대시보드입니다.

## ✨ 주요 기능
- **초경량 순수 Python 아키텍처**: Node.js/빌드 없이 100% Python으로 동작 (프로젝트 전체 크기 수백 KB 수준)
- **다크모드 글래스모피즘 UI**: 반투명 카드, 테두리 블러 및 호버 효과
- **실시간 데이터 수집**: Yahoo Finance 병렬 크롤링, KRX 지표 캐싱, CNN Fear & Greed, SKHY ADR Premium 실시간 계산
- **미니 일봉 캔들 & 60일 스파크라인**: 인라인 SVG 기반의 고속 렌더링
- **50% 반투명 인터랙티브 툴팁**: 스파크라인 마우스 호버 시 날짜 및 가격 정보와 세로 점선 커서 표시
- **좌측 사이드바 & 접기(<<) 기능**: '00 Bookmarks' 스타일의 시인성 높은 사이드바 접기/펼치기 버튼 및 시장/섹터 선택

## 🚀 실행 방법

### 1. 패키지 설치
`ash
pip install -r requirements.txt
`

### 2. 앱 실행
`ash
streamlit run app.py
`
또는 un.bat 파일을 더블 클릭하여 실행합니다.
