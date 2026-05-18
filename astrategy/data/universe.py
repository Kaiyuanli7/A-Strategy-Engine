"""Demo universe definition for Phase 1."""

# 10 mega-cap CSI 300 names — diversified across sectors for the bootstrap demo.
# Mix of main board (60/00), ChiNext (300), and Shenzhen main (002) to exercise
# board classification + price-limit code paths.
DEMO_UNIVERSE: list[tuple[str, str]] = [
    ("600519", "贵州茅台"),      # Moutai (consumer)
    ("601318", "中国平安"),      # Ping An (financial)
    ("300750", "宁德时代"),      # CATL (new energy, ChiNext)
    ("601398", "工商银行"),      # ICBC (bank)
    ("000858", "五粮液"),         # Wuliangye (consumer, SZ main)
    ("600036", "招商银行"),      # CMB (bank)
    ("601012", "隆基绿能"),      # LONGi (solar)
    ("002594", "比亚迪"),         # BYD (auto, SZ main)
    ("600276", "恒瑞医药"),      # Hengrui (pharma)
    ("601888", "中国中免"),      # CTG Duty Free (consumer)
]
