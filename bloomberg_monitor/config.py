import os
from pathlib import Path

# Base directory
BASE_DIR = Path(__file__).resolve().parent

# Database configuration
DB_PATH = os.environ.get("BLOOMBERG_DB_PATH", str(BASE_DIR / "bloomberg_news.db"))

# Proxy settings: auto-detect or manual
DEFAULT_PROXY = os.environ.get("HTTP_PROXY", "http://127.0.0.1:7897")

# Category keywords mapping for China focus
CHINA_CATEGORIES = {
    "宏观政策": [
        "economy", "gdp", "pboc", "central bank", "stimulus", "interest rate",
        "inflation", "cpi", "ppi", "policy", "debt", "bonds", "sovereign",
        "state council", "national people's congress", "ministry of finance"
    ],
    "贸易关税": [
        "tariff", "tariffs", "trade", "export", "import", "customs", "wto",
        "sanction", "sanctions", "trump", "biden", "commerce", "duties",
        "trade war", "embargo", "supply chain"
    ],
    "科技半导体": [
        "tech", "ai", "chip", "chips", "semiconductor", "semiconductors",
        "huawei", "alibaba", "tencent", "baidu", "bytedance", "smic", "deepseek",
        "quantum", "nvda", "nvidia", "asml", "robotics", "ev", "electric vehicle"
    ],
    "金融外汇": [
        "yuan", "rmb", "renminbi", "forex", "fx", "currency", "stocks", "equities",
        "csi 300", "shanghai", "hang seng", "h-shares", "a-share", "yield",
        "banking", "liquidity", "ipo"
    ],
    "房产消费": [
        "property", "real estate", "housing", "developer", "vanke", "country garden",
        "evergrande", "home sales", "retail", "consumer", "consumption", "travel",
        "tourism", "e-commerce"
    ],
    "大宗商品": [
        "copper", "gold", "oil", "crude", "iron ore", "steel", "lithium", "nickel",
        "gas", "lng", "grain", "soybean", "rare earth", "coal", "clean energy"
    ]
}

# General China keywords for relevance checking
CHINA_KEYWORDS = [
    "china", "chinese", "beijing", "shanghai", "shenzhen", "hong kong", "yuan", "rmb",
    "pboc", "xi jinping", "taiwan", "alibaba", "tencent", "byd", "huawei", "smic"
]

# Scraping intervals in minutes
DEFAULT_SCRAPE_INTERVAL = 30
