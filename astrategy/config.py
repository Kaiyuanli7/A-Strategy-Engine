"""Constants and stock classification for A-share markets."""

from __future__ import annotations

# Board identifiers
BOARD_MAIN_SH = "main_sh"        # 60xxxx (Shanghai main)
BOARD_MAIN_SZ = "main_sz"        # 00xxxx (Shenzhen main)
BOARD_CHINEXT = "chinext"        # 300xxx, 301xxx (创业板)
BOARD_STAR = "star"              # 688xxx (科创板)
BOARD_BJ = "beijing"             # 8xxxxx, 4xxxxx, 92xxxx (北交所)
BOARD_UNKNOWN = "unknown"

# Daily price limit (pct of prior close)
PRICE_LIMIT_PCT = {
    BOARD_MAIN_SH: 0.10,
    BOARD_MAIN_SZ: 0.10,
    BOARD_CHINEXT: 0.20,
    BOARD_STAR: 0.20,
    BOARD_BJ: 0.30,
}
ST_PRICE_LIMIT_PCT = 0.05

# Trade mechanics
LOT_SIZE = 100

# Transaction costs (current rules; stamp tax was 0.1% before Aug 2023)
STAMP_TAX_SELL = 0.0005          # 0.05% on sells only
COMMISSION_RATE = 0.00025        # 0.025% each way
COMMISSION_MIN = 5.0             # ¥5 minimum per trade
TRANSFER_FEE = 0.00001           # 0.001% both sides

# Behavioral assumption for limit-hit fills
LIMIT_HIT_FILL_PROB = 0.20       # 20% chance of fill when stock closes at limit

# Convention
TRADING_DAYS_PER_YEAR = 252
DEFAULT_RISK_FREE_RATE = 0.02    # 2% annualized


def classify_board(code: str) -> str:
    """Classify an A-share code into its board by prefix."""
    code = code.strip()
    if len(code) != 6 or not code.isdigit():
        return BOARD_UNKNOWN
    if code.startswith("60"):
        return BOARD_MAIN_SH
    if code.startswith(("000", "001", "002", "003")):
        return BOARD_MAIN_SZ
    if code.startswith(("300", "301")):
        return BOARD_CHINEXT
    if code.startswith("688"):
        return BOARD_STAR
    if code.startswith(("8", "4", "92")):
        return BOARD_BJ
    return BOARD_UNKNOWN


def is_st_name(name: str) -> bool:
    """Detect ST status from the stock name."""
    if not name:
        return False
    upper = name.upper()
    return "ST" in upper or "*ST" in upper or "退" in name
