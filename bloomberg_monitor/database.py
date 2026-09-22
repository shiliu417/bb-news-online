import sqlite3
import hashlib
import json
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from .config import DB_PATH

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Articles table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url_hash TEXT UNIQUE NOT NULL,
            original_url TEXT NOT NULL,
            title_en TEXT NOT NULL,
            title_zh TEXT NOT NULL,
            summary_zh TEXT,
            content_en TEXT,
            content_zh TEXT,
            source_name TEXT,
            published_at TEXT,
            category TEXT DEFAULT '宏观政策',
            sentiment TEXT DEFAULT '中性',
            key_points TEXT,
            is_china_focus INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_published_at ON articles(published_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_category ON articles(category)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_china_focus ON articles(is_china_focus)")

    # Key-value Settings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

def hash_url(url: str) -> str:
    return hashlib.md5(url.strip().encode("utf-8")).hexdigest()

def article_exists(url: str) -> bool:
    h = hash_url(url)
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM articles WHERE url_hash = ?", (h,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def insert_article(data: Dict[str, Any]) -> bool:
    """Insert article if not exists. Returns True if inserted, False if duplicate."""
    url = data.get("original_url", "")
    if not url:
        return False
    
    h = hash_url(url)
    key_points_json = json.dumps(data.get("key_points", []), ensure_ascii=False) if isinstance(data.get("key_points"), list) else data.get("key_points", "[]")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO articles (
                url_hash, original_url, title_en, title_zh, summary_zh,
                content_en, content_zh, source_name, published_at, category,
                sentiment, key_points, is_china_focus
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            h,
            url,
            data.get("title_en", ""),
            data.get("title_zh", ""),
            data.get("summary_zh", ""),
            data.get("content_en", ""),
            data.get("content_zh", ""),
            data.get("source_name", "Bloomberg Syndication"),
            data.get("published_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            data.get("category", "宏观政策"),
            data.get("sentiment", "中性"),
            key_points_json,
            1 if data.get("is_china_focus", True) else 0
        ))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_articles(
    category: Optional[str] = None,
    search: Optional[str] = None,
    china_only: bool = False,
    sentiment: Optional[str] = None,
    page: int = 1,
    per_page: int = 20
) -> Tuple[List[Dict[str, Any]], int]:
    """Retrieve articles with filtering, pagination and search."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    conditions = []
    params = []
    
    if category and category != "全部":
        conditions.append("category = ?")
        params.append(category)
        
    if sentiment:
        conditions.append("sentiment = ?")
        params.append(sentiment)

    if china_only:
        conditions.append("is_china_focus = 1")
        
    if search:
        search_pattern = f"%{search.strip()}%"
        conditions.append("(title_zh LIKE ? OR title_en LIKE ? OR summary_zh LIKE ?)")
        params.extend([search_pattern, search_pattern, search_pattern])
        
    where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    
    # Count total
    count_sql = f"SELECT COUNT(*) as total FROM articles{where_clause}"
    cursor.execute(count_sql, params)
    total = cursor.fetchone()["total"]
    
    # Query items with pagination
    offset = (page - 1) * per_page
    query_sql = f"""
        SELECT * FROM articles{where_clause}
        ORDER BY id DESC
        LIMIT ? OFFSET ?
    """
    cursor.execute(query_sql, params + [per_page, offset])
    rows = cursor.fetchall()
    
    articles = []
    for r in rows:
        item = dict(r)
        try:
            item["key_points"] = json.loads(item.get("key_points") or "[]")
        except Exception:
            item["key_points"] = []
        articles.append(item)
        
    conn.close()
    return articles, total

def get_article_by_id(article_id: int) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM articles WHERE id = ?", (article_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    item = dict(row)
    try:
        item["key_points"] = json.loads(item.get("key_points") or "[]")
    except Exception:
        item["key_points"] = []
    return item

def get_stats() -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) as total FROM articles")
    total = cursor.fetchone()["total"]
    
    cursor.execute("SELECT COUNT(*) as china_total FROM articles WHERE is_china_focus = 1")
    china_total = cursor.fetchone()["china_total"]
    
    cursor.execute("SELECT category, COUNT(*) as count FROM articles GROUP BY category")
    cats = {r["category"]: r["count"] for r in cursor.fetchall()}

    cursor.execute("SELECT sentiment, COUNT(*) as count FROM articles GROUP BY sentiment")
    sents = {r["sentiment"]: r["count"] for r in cursor.fetchall()}
    
    cursor.execute("SELECT MAX(created_at) as last_scraped FROM articles")
    last_row = cursor.fetchone()
    last_scraped = last_row["last_scraped"] if last_row and last_row["last_scraped"] else "尚未抓取"
    
    conn.close()
    return {
        "total": total,
        "china_total": china_total,
        "categories": cats,
        "sentiments": sents,
        "last_scraped": last_scraped
    }

def get_setting(key: str, default: str = "") -> str:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row["value"] if row else default

def set_setting(key: str, value: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO settings (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
    """, (key, value))
    conn.commit()
    conn.close()
