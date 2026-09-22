import re
import socket
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import email.utils
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup

from .database import article_exists, insert_article, get_setting
from .translator import process_and_translate_article, check_china_focus, clean_news_text
from .config import DEFAULT_PROXY

def clean_canonical_url(url: str) -> str:
    """Extract real destination URL from search redirects and strip tracking tags."""
    if not url:
        return ""
        
    # Unpack Bing apiclick redirects
    if "bing.com/news/apiclick.aspx" in url:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        if "url" in qs and qs["url"]:
            url = qs["url"][0]

    parsed = urllib.parse.urlparse(url)
    clean_pairs = []
    for pair in parsed.query.split("&"):
        if not pair:
            continue
        k = pair.split("=")[0].lower()
        if not any(k.startswith(p) for p in ["utm_", "c", "mkt", "ref", "fbclid", "gclid", "sp_source"]):
            clean_pairs.append(pair)
            
    clean_query = "&".join(clean_pairs)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, clean_query, ""))

def normalize_title(title: str) -> str:
    """Normalize title for fuzzy deduplication."""
    t = re.sub(r'[\-—|•]\s*Bloomberg(\.com|\s*News)?\s*$', '', title, flags=re.IGNORECASE)
    t = re.sub(r'[^\w\s]', '', t.lower())
    return re.sub(r'\s+', ' ', t).strip()

def is_recent_article(pub_date_str: str, max_days: int = 5) -> bool:
    """Verify that the article was published within max_days (defaults to 5 days)."""
    if not pub_date_str:
        return True # Keep if unknown
    try:
        dt = email.utils.parsedate_to_datetime(pub_date_str)
        now = datetime.now(timezone.utc)
        diff = now - dt
        return diff.total_seconds() <= max_days * 86400
    except Exception:
        return True

def is_proxy_available(proxy_url: str = DEFAULT_PROXY) -> bool:
    """Check if the local proxy port is open and responding."""
    try:
        parsed = urllib.parse.urlparse(proxy_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 7897
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.4)
            s.connect((host, port))
            return True
    except Exception:
        return False

def make_request(url: str, proxy: Optional[str] = None, timeout: int = 5) -> Optional[bytes]:
    """Fetch URL with optional proxy and standard browser headers."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        if proxy:
            handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
            opener = urllib.request.build_opener(handler)
            with opener.open(req, timeout=timeout) as res:
                return res.read()
        else:
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return res.read()
    except Exception:
        return None

def extract_article_body(url: str, proxy: Optional[str] = None) -> str:
    """Extract clean article paragraphs from syndicated partner page using targeted containers."""
    try:
        content = make_request(url, proxy=proxy, timeout=5)
        if not content:
            return ""
        soup = BeautifulSoup(content, "html.parser")
        
        for element in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe", "noscript"]):
            element.decompose()

        article_elem = (
            soup.find("article") or
            soup.find(attrs={"itemprop": "articleBody"}) or
            soup.find(class_=re.compile(r"article[-_]?body|story[-_]?content|post[-_]?content|entry[-_]?content", re.I)) or
            soup.find("main")
        )
        search_target = article_elem if article_elem else soup

        paragraphs = []
        for p in search_target.find_all("p"):
            text = p.get_text().strip()
            if len(text) > 40 and not any(skip in text.lower() for skip in [
                "copyright", "all rights reserved", "terms of service", "cookie policy",
                "subscribe now", "advertisement", "sign up for", "follow us on"
            ]):
                paragraphs.append(clean_news_text(text))
                
        return "\n\n".join(paragraphs[:8])
    except Exception:
        return ""

def parse_bing_news_rss(query: str, proxy: Optional[str] = None) -> List[Dict[str, Any]]:
    """Scrape newest Bloomberg China news via Bing News RSS with strict sortbydate=1."""
    encoded_query = urllib.parse.quote(query)
    # Crucial: &qft=sortbydate%3d%221%22 ensures latest real-time articles
    url = f"https://www.bing.com/news/search?q={encoded_query}&qft=sortbydate%3d%221%22&format=rss"
    content = make_request(url, proxy=proxy, timeout=6)
    if not content:
        return []
        
    items = []
    try:
        root = ET.fromstring(content)
        for it in root.findall("./channel/item"):
            raw_title = it.find("title").text if it.find("title") is not None else ""
            raw_link = it.find("link").text if it.find("link") is not None else ""
            desc = it.find("description").text if it.find("description") is not None else ""
            pub_date = it.find("pubDate").text if it.find("pubDate") is not None else ""
            
            clean_link = clean_canonical_url(raw_link)
            clean_t = clean_news_text(raw_title)
            
            # Check freshness: only keep if published within last 5 days
            if clean_t and clean_link and is_recent_article(pub_date, max_days=5):
                domain = urllib.parse.urlparse(clean_link).netloc.replace("www.", "")
                source_label = f"{domain} (彭博转载)" if domain else "彭博辛迪加授权源"
                
                items.append({
                    "title_en": clean_t,
                    "original_url": clean_link,
                    "desc_en": clean_news_text(desc),
                    "published_at": pub_date,
                    "source": source_label
                })
    except Exception as e:
        print(f"Error parsing Bing RSS for query '{query}': {e}")
        
    return items

def parse_google_news_rss(query: str, proxy: Optional[str] = None) -> List[Dict[str, Any]]:
    """Scrape Bloomberg news via Google News RSS with time-limited queries (when:1d / 2d)."""
    if not proxy:
        return []
        
    encoded_query = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"
    content = make_request(url, proxy=proxy, timeout=6)
    if not content:
        return []
        
    items = []
    try:
        root = ET.fromstring(content)
        for it in root.findall("./channel/item"):
            title = it.find("title").text if it.find("title") is not None else ""
            raw_link = it.find("link").text if it.find("link") is not None else ""
            pub_date = it.find("pubDate").text if it.find("pubDate") is not None else ""
            source_el = it.find("source")
            source_name = source_el.text if source_el is not None else "Bloomberg"
            
            clean_link = clean_canonical_url(raw_link)
            clean_t = clean_news_text(title)
            
            if clean_t and clean_link and is_recent_article(pub_date, max_days=5):
                items.append({
                    "title_en": clean_t,
                    "original_url": clean_link,
                    "desc_en": "",
                    "published_at": pub_date,
                    "source": f"{source_name} 聚焦"
                })
    except Exception as e:
        print(f"Error parsing Google News RSS for query '{query}': {e}")
        
    return items

def _process_single_article(item: Dict[str, Any], proxy_to_use: Optional[str], ai_config: Optional[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    """Worker function for concurrent article processing."""
    try:
        full_text_candidate = f"{item['title_en']} {item.get('desc_en', '')}"
        if not check_china_focus(full_text_candidate):
            return None

        body_en = item.get("desc_en", "")

        processed = process_and_translate_article(
            title_en=item["title_en"],
            desc_en=item.get("desc_en", ""),
            content_en=body_en,
            proxy=proxy_to_use,
            ai_config=ai_config
        )

        return {
            "original_url": item["original_url"],
            "title_en": item["title_en"],
            "title_zh": processed["title_zh"],
            "summary_zh": processed["summary_zh"],
            "content_en": body_en,
            "content_zh": processed.get("content_zh", ""),
            "source_name": item.get("source", "Bloomberg 授权源"),
            "published_at": item.get("published_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "category": processed["category"],
            "sentiment": processed["sentiment"],
            "key_points": processed["key_points"],
            "is_china_focus": processed["is_china_focus"]
        }
    except Exception as e:
        print(f"Error processing article: {e}")
        return None

def run_scraper(proxy_override: Optional[str] = None, max_items: int = 30) -> Dict[str, Any]:
    """Execute scraping with latest-date queries and concurrent processing."""
    configured_proxy = get_setting("proxy_url", DEFAULT_PROXY)
    active_proxy = proxy_override or configured_proxy
    proxy_to_use = active_proxy if is_proxy_available(active_proxy) else None

    ai_api_key = get_setting("ai_api_key", "")
    ai_base_url = get_setting("ai_base_url", "https://api.openai.com/v1")
    ai_model = get_setting("ai_model", "gpt-3.5-turbo")
    ai_config = {"api_key": ai_api_key, "base_url": ai_base_url, "model": ai_model} if ai_api_key else None

    raw_items: List[Dict[str, Any]] = []

    # 1. Bing News Queries (sorted by date, newest first)
    bing_queries = [
        "Bloomberg China",
        "Bloomberg China economy",
        "Bloomberg China market",
        "site:theedgesingapore.com bloomberg",
        "site:asiaone.com bloomberg"
    ]
    for q in bing_queries:
        items = parse_bing_news_rss(q, proxy=proxy_to_use)
        raw_items.extend(items)

    # 2. Google News RSS Queries (Strict when:1d / when:2d freshness)
    if proxy_to_use:
        google_queries = [
            "source:Bloomberg China when:1d",
            "Bloomberg China when:1d",
            "Bloomberg China economy when:2d"
        ]
        for q in google_queries:
            items = parse_google_news_rss(q, proxy=proxy_to_use)
            raw_items.extend(items)

    # Multi-dimensional deduplication: Canonical URL + Normalized Title
    unique_items = []
    seen_urls: Set[str] = set()
    seen_titles: Set[str] = set()
    
    for item in raw_items:
        url = item["original_url"]
        norm_t = normalize_title(item["title_en"])
        
        if (url not in seen_urls and 
            norm_t not in seen_titles and 
            not article_exists(url)):
            seen_urls.add(url)
            seen_titles.add(norm_t)
            unique_items.append(item)

    items_to_process = unique_items[:max_items]
    print(f"Scraped {len(raw_items)} raw items. Processing {len(items_to_process)} clean latest articles...")

    new_added = 0
    # Concurrent processing
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(_process_single_article, item, proxy_to_use, ai_config)
            for item in items_to_process
        ]
        for future in as_completed(futures):
            res = future.result()
            if res:
                if insert_article(res):
                    new_added += 1

    return {
        "status": "success",
        "total_scraped": len(raw_items),
        "new_added": new_added,
        "proxy_used": proxy_to_use or "Direct (No proxy)"
    }
