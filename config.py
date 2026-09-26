"""
Market Overview Dashboard Configuration
All ticker definitions, tab categories, and indicator metadata.
"""

CATEGORIES = ["US Market", "K Market", "Semiconductor"]

US_MARKET_TICKERS = [
    '^GSPC', '^IXIC', '^TNX', 'CL=F', 'DX-Y.NYB', 'KRW=X', 'EWY', 'BTC-USD', 'GC=F', '^VIX', 'FEAR_GREED',
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'SPCX'
]

K_MARKET_TICKERS = [
    '^KS11', '^KQ11', 'KOSPI200_FUTURES', 'KOSPI_PER', 'KOSPI_PBR', 'KOSPI_RSI', 'ADR_INFO', 'KOSPI_TRADE_VALUE',
    'CUSTOMER_DEPOSITS', 'CREDIT_BALANCE', 'MARGIN_CALL', 'KOSPI200_NIGHT', 'VKOSPI'
]

SEMI_MARKET_TICKERS = [
    '^SOX', 'NVDA', 'MU', 'SNDK', 'INTC', 'AMD', 'DRAM', 'CCML',
    '005930.KS', '009150.KS', '402340.KS', '000660.KS', 'SKHY', '285A.T', '6981.T', '688825.SS'
]

# 한국거래소(KRX) 정규 휴장일 및 법정 공휴일 (2024~2027)
KRX_HOLIDAYS = {
    # 2024
    '20240101', '20240209', '20240212', '20240301', '20240410', '20240501', '20240506',
    '20240515', '20240606', '20240815', '20240916', '20240917', '20240918', '20241001',
    '20241003', '20241009', '20241225', '20241231',
    # 2025
    '20250101', '20250128', '20250129', '20250130', '20250303', '20250501', '20250505',
    '20250506', '20250606', '20250815', '20251003', '20251006', '20251007', '20251008',
    '20251009', '20251225', '20251231',
    # 2026
    '20260101', '20260216', '20260217', '20260218', '20260302', '20260501', '20260505',
    '20260525', '20260603', '20260606', '20260817', '20260924', '20260925', '20261005',
    '20261009', '20261225', '20261231',
    # 2027
    '20270101', '20270208', '20270209', '20270210', '20270301', '20270503', '20270505',
    '20270513', '20270607', '20270816', '20270914', '20270915', '20270916', '20271004',
    '20271011', '20271225', '20271231'
}

# Indicator metadata dictionary keyed by ticker
INDICATORS_META = {
    # US Market / Macro
    '^GSPC': {'name': '미국 S&P 500 지수', 'negative_favorable': False},
    '^IXIC': {'name': '미국 나스닥 지수', 'negative_favorable': False},
    '^TNX': {'name': '미국 국채 10년물 금리(TNX)', 'negative_favorable': True},
    'CL=F': {'name': 'Crude Oil WTI (NYMEX)', 'negative_favorable': True},
    'DX-Y.NYB': {'name': '미국 달러 지수(USD Index)', 'negative_favorable': True},
    'KRW=X': {'name': 'USD/KRW 환율', 'negative_favorable': True},
    'EWY': {'name': 'EWY (MSCI South Korea ETF)', 'negative_favorable': False},
    'BTC-USD': {'name': '비트코인(BTC-USD) 가격', 'negative_favorable': False},
    'GC=F': {'name': '금(GOLD) 가격', 'negative_favorable': False},
    '^VIX': {'name': 'CBOE VIX', 'negative_favorable': True},
    'FEAR_GREED': {'name': 'CNN Fear & Greed Index', 'negative_favorable': False},
    'AAPL': {'name': '애플(AAPL)', 'negative_favorable': False},
    'MSFT': {'name': '마이크로소프트(MSFT)', 'negative_favorable': False},
    'GOOGL': {'name': '구글(GOOGL)', 'negative_favorable': False},
    'AMZN': {'name': '아마존(AMZN)', 'negative_favorable': False},
    'META': {'name': '메타(META)', 'negative_favorable': False},
    'TSLA': {'name': '테슬라(TSLA)', 'negative_favorable': False},
    'SPCX': {'name': '스페이스X(SPCX)', 'negative_favorable': False},

    # K Market
    '^KS11': {'name': 'KOSPI 지수', 'negative_favorable': False},
    '^KQ11': {'name': 'KOSDAQ 지수', 'negative_favorable': False},
    'KOSPI200_FUTURES': {'name': 'KOSPI200 선물 지수', 'negative_favorable': False},
    'KOSPI_PER': {'name': 'KOSPI PER', 'negative_favorable': False},
    'KOSPI_PBR': {'name': 'KOSPI PBR', 'negative_favorable': False},
    'KOSPI_RSI': {'name': 'KOSPI RSI(14, %)', 'negative_favorable': False},
    'ADR_INFO': {'name': 'KOSPI ADR(20, %)', 'negative_favorable': False},
    'KOSPI_TRADE_VALUE': {'name': 'KOSPI 거래대금 (단위:억원)', 'negative_favorable': False, 'integer_only': True},
    'CUSTOMER_DEPOSITS': {'name': '고객예탁금 (단위:억원)', 'negative_favorable': False, 'integer_only': True},
    'CREDIT_BALANCE': {'name': '신용공여 잔고 (단위:억원)', 'negative_favorable': False, 'integer_only': True},
    'MARGIN_CALL': {'name': '반대매매금액 (단위:억원)', 'negative_favorable': True, 'integer_only': True},
    'KOSPI200_NIGHT': {'name': 'KOSPI200 야간 선물 지수', 'negative_favorable': False},
    'VKOSPI': {'name': 'KOSPI200 변동성지수', 'negative_favorable': True},

    # Semiconductor
    '^SOX': {'name': '필라델피아 반도체 지수(SOX)', 'negative_favorable': False},
    'NVDA': {'name': '엔비디아(NVDA)', 'negative_favorable': False},
    'MU': {'name': '마이크론(MU)', 'negative_favorable': False},
    'SNDK': {'name': '샌디스크(SNDK)', 'negative_favorable': False},
    'INTC': {'name': '인텔(INTC)', 'negative_favorable': False},
    'AMD': {'name': 'AMD(AMD)', 'negative_favorable': False},
    'DRAM': {'name': 'DRAM (Roundhill ETF)', 'negative_favorable': False},
    'CCML': {'name': 'CCML (Roundhill ETF)', 'negative_favorable': False},
    '005930.KS': {'name': '삼성전자', 'negative_favorable': False, 'integer_only': True},
    '009150.KS': {'name': '삼성전기', 'negative_favorable': False, 'integer_only': True},
    '402340.KS': {'name': 'SK스퀘어', 'negative_favorable': False, 'integer_only': True},
    '000660.KS': {'name': 'SK하이닉스', 'negative_favorable': False, 'integer_only': True},
    'SKHY': {'name': 'SKHY (ADR)', 'negative_favorable': False},
    '285A.T': {'name': '키옥시아', 'negative_favorable': False, 'integer_only': True},
    '6981.T': {'name': '무라타', 'negative_favorable': False, 'integer_only': True},
    '688825.SS': {'name': 'CXMT', 'negative_favorable': False},
}

# Tickers that should be formatted as integers (no decimals)
INTEGER_ONLY_TICKERS = {
    'KOSPI_TRADE_VALUE', 'CUSTOMER_DEPOSITS', 'CREDIT_BALANCE', 'MARGIN_CALL',
    '005930.KS', '009150.KS', '402340.KS', '000660.KS', '285A.T', '6981.T'
}
