import os
import re
import csv
import io
import time
import socket
import subprocess
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response

from .config import DEFAULT_SCRAPE_INTERVAL, DEFAULT_PROXY
from .database import (
    init_db,
    get_articles,
    get_article_by_id,
    get_stats,
    get_setting,
    set_setting,
    insert_article
)
from .scraper import run_scraper, extract_article_body, is_proxy_available
from .translator import translate_free

app = Flask(__name__, template_folder="templates", static_folder="static")

_is_scraping = False
_last_scrape_result = {}

def get_lan_ip() -> str:
    """Detect local physical LAN IP address for mobile phone access."""
    try:
        output = subprocess.check_output('ipconfig', shell=True).decode('gbk', errors='ignore')
        ips = re.findall(r'IPv4 [^\r\n]+:\s*([0-9\.]+)', output)
        for ip in ips:
            if not ip.startswith('198.18.') and not ip.startswith('127.'):
                return ip
    except Exception:
        pass
        
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def background_scheduler():
    """Periodic background scraper task."""
    # Run an initial scrape after 5 seconds of startup if DB is empty
    time.sleep(5)
    try:
        stats = get_stats()
        if stats.get("total", 0) == 0:
            print("Database empty on startup. Triggering initial scrape...")
            run_scraper(max_items=25)
    except Exception as e:
        print(f"Initial scrape error: {e}")

    while True:
        try:
            interval_str = get_setting("scrape_interval", str(DEFAULT_SCRAPE_INTERVAL))
            interval_mins = max(5, int(interval_str))
        except Exception:
            interval_mins = 30
            
        time.sleep(interval_mins * 60)
        
        global _is_scraping, _last_scrape_result
        if not _is_scraping:
            _is_scraping = True
            try:
                print(f"[{datetime.now()}] Running scheduled background scrape...")
                _last_scrape_result = run_scraper()
            except Exception as e:
                print(f"Background scrape error: {e}")
            finally:
                _is_scraping = False

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/news")
def api_news():
    category = request.args.get("category", "")
    sentiment = request.args.get("sentiment", "")
    search = request.args.get("search", "")
    china_only = request.args.get("china_only", "false").lower() == "true"
    page = max(1, int(request.args.get("page", 1)))
    per_page = min(50, max(5, int(request.args.get("per_page", 15))))
    
    articles, total = get_articles(
        category=category if category else None,
        sentiment=sentiment if sentiment else None,
        search=search if search else None,
        china_only=china_only,
        page=page,
        per_page=per_page
    )
    
    total_pages = (total + per_page - 1) // per_page
    return jsonify({
        "status": "success",
        "articles": articles,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages
    })

@app.route("/api/article/<int:article_id>")
def api_article_detail(article_id):
    article = get_article_by_id(article_id)
    if not article:
        return jsonify({"status": "error", "message": "Article not found"}), 404
    return jsonify({"status": "success", "article": article})

@app.route("/api/article/<int:article_id>/fetch_full", methods=["POST"])
def api_fetch_full_text(article_id):
    article = get_article_by_id(article_id)
    if not article:
        return jsonify({"status": "error", "message": "Article not found"}), 404
        
    url = article.get("original_url", "")
    proxy = get_setting("proxy_url", DEFAULT_PROXY)
    proxy_to_use = proxy if is_proxy_available(proxy) else None
    
    body_en = extract_article_body(url, proxy=proxy_to_use)
    body_zh = ""
    if body_en:
        paragraphs = [p.strip() for p in body_en.split("\n\n") if p.strip()]
        translated_paras = []
        for p in paragraphs[:6]:
            trans = translate_free(p, proxy=proxy_to_use)
            translated_paras.append(trans if trans else p)
        body_zh = "\n\n".join(translated_paras)
        
    return jsonify({
        "status": "success",
        "content_en": body_en,
        "content_zh": body_zh
    })

@app.route("/api/scrape", methods=["POST"])
def api_trigger_scrape():
    global _is_scraping, _last_scrape_result
    if _is_scraping:
        return jsonify({
            "status": "busy",
            "message": "抓取任务正在后台运行中，请稍候。"
        })
        
    def do_scrape():
        global _is_scraping, _last_scrape_result
        _is_scraping = True
        try:
            _last_scrape_result = run_scraper(max_items=35)
        except Exception as e:
            _last_scrape_result = {"status": "error", "message": str(e)}
        finally:
            _is_scraping = False

    t = threading.Thread(target=do_scrape, daemon=True)
    t.start()
    
    return jsonify({
        "status": "started",
        "message": "抓取任务已在后台启动，系统正在抓取并翻译最新彭博中国新闻..."
    })

@app.route("/api/scrape_status")
def api_scrape_status():
    global _is_scraping, _last_scrape_result
    return jsonify({
        "is_scraping": _is_scraping,
        "last_result": _last_scrape_result
    })

@app.route("/api/stats")
def api_stats():
    stats = get_stats()
    stats["is_scraping"] = _is_scraping
    stats["lan_ip"] = get_lan_ip()
    return jsonify(stats)

@app.route("/api/mobile_info")
def api_mobile_info():
    lan_ip = get_lan_ip()
    host = request.host
    port = host.split(":")[-1] if ":" in host else "5000"
    mobile_url = f"http://{lan_ip}:{port}"
    return jsonify({
        "lan_ip": lan_ip,
        "port": port,
        "url": mobile_url
    })

@app.route("/api/qrcode")
def api_qrcode():
    import qrcode
    lan_ip = get_lan_ip()
    host = request.host
    port = host.split(":")[-1] if ":" in host else "5000"
    mobile_url = f"http://{lan_ip}:{port}"
    
    img = qrcode.make(mobile_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Response(buf.getvalue(), mimetype="image/png")

@app.route("/feed.xml")
@app.route("/rss")
def rss_feed():
    articles, _ = get_articles(page=1, per_page=30)
    lan_ip = get_lan_ip()
    host = request.host
    port = host.split(":")[-1] if ":" in host else "5000"
    site_url = f"http://{lan_ip}:{port}"
    
    xml_items = []
    for a in articles:
        xml_items.append(f"""
        <item>
            <title><![CDATA[{a['title_zh']}]]></title>
            <link>{a['original_url']}</link>
            <description><![CDATA[
                <p><strong>原标题：</strong>{a['title_en']}</p>
                <p><strong>分类：</strong>{a['category']} | <strong>情绪：</strong>{a['sentiment']}</p>
                <p><strong>核心摘要：</strong>{a['summary_zh']}</p>
                <p><strong>来源：</strong>{a['source_name']}</p>
            ]]></description>
            <pubDate>{a['published_at']}</pubDate>
            <guid>{a['original_url']}</guid>
        </item>
        """)
    rss_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
<channel>
    <title>彭博中国财经资讯监控终端</title>
    <link>{site_url}</link>
    <description>彭博社授权转载与中国相关核心财经新闻中文汇总</description>
    <language>zh-cn</language>
    {''.join(xml_items)}
</channel>
</rss>"""
    return Response(rss_xml, mimetype="application/xml; charset=utf-8")

@app.route("/api/settings", methods=["GET", "POST"])
def api_settings():
    if request.method == "POST":
        data = request.json or {}
        if "proxy_url" in data:
            set_setting("proxy_url", data["proxy_url"].strip())
        if "scrape_interval" in data:
            set_setting("scrape_interval", str(data["scrape_interval"]).strip())
        if "ai_api_key" in data:
            set_setting("ai_api_key", data["ai_api_key"].strip())
        if "ai_base_url" in data:
            set_setting("ai_base_url", data["ai_base_url"].strip())
        if "ai_model" in data:
            set_setting("ai_model", data["ai_model"].strip())
        return jsonify({"status": "success", "message": "配置已保存"})
    
    proxy_url = get_setting("proxy_url", DEFAULT_PROXY)
    return jsonify({
        "proxy_url": proxy_url,
        "proxy_active": is_proxy_available(proxy_url),
        "scrape_interval": get_setting("scrape_interval", str(DEFAULT_SCRAPE_INTERVAL)),
        "ai_api_key": get_setting("ai_api_key", ""),
        "ai_base_url": get_setting("ai_base_url", "https://api.openai.com/v1"),
        "ai_model": get_setting("ai_model", "gpt-3.5-turbo")
    })

@app.route("/api/export")
def api_export():
    fmt = request.args.get("format", "markdown").lower()
    articles, _ = get_articles(page=1, per_page=200)
    
    if fmt == "json":
        return jsonify(articles)
        
    if fmt == "csv":
        output = io.StringIO()
        output.write('\ufeff')
        writer = csv.writer(output)
        writer.writerow(["ID", "分类", "情绪", "中文标题", "英文原标题", "核心摘要", "发布时间", "来源", "原文链接"])
        for a in articles:
            writer.writerow([
                a.get("id"),
                a.get("category"),
                a.get("sentiment"),
                a.get("title_zh"),
                a.get("title_en"),
                a.get("summary_zh"),
                a.get("published_at"),
                a.get("source_name"),
                a.get("original_url")
            ])
        csv_data = output.getvalue().encode('utf-8-sig')
        return Response(
            csv_data,
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=bloomberg_china_news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
        )

    lines = [
        f"# 彭博社中国财经新闻汇总简报",
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 共 {len(articles)} 条资讯\n",
        "---",
        ""
    ]
    for i, a in enumerate(articles, 1):
        lines.append(f"### {i}. {a['title_zh']}")
        lines.append(f"- **原标题**: {a['title_en']}")
        lines.append(f"- **分类**: `{a['category']}` | **情绪**: `{a['sentiment']}` | **来源**: {a['source_name']}")
        lines.append(f"- **发布时间**: {a['published_at']}")
        if a.get("summary_zh"):
            lines.append(f"- **核心摘要**: {a['summary_zh']}")
        if a.get("key_points"):
            lines.append("- **要点归纳**:")
            for pt in a["key_points"]:
                lines.append(f"  * {pt}")
        lines.append(f"- [查看原文报道]({a['original_url']})")
        lines.append("\n---\n")
        
    md_content = "\n".join(lines)
    return Response(
        md_content,
        mimetype="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=bloomberg_china_news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"}
    )

def find_available_port(start_port=5000, max_port=5020):
    env_port = os.environ.get("PORT")
    if env_port:
        try:
            return int(env_port)
        except ValueError:
            pass
            
    for port in range(start_port, max_port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    return start_port

def start_server(host="0.0.0.0", port=None, debug=False):
    actual_port = port if port else find_available_port(5000)
    lan_ip = get_lan_ip()
    
    print(f"============================================================")
    print(f"  彭博社新闻（中国专题）自动抓取与分析监控系统已启动!")
    print(f"  电脑本地访问: http://127.0.0.1:{actual_port}")
    print(f"  手机/局域网访问: http://{lan_ip}:{actual_port}")
    print(f"============================================================")
    app.run(host=host, port=actual_port, debug=debug)

# Initialize DB and scheduler thread on module import for WSGI/Gunicorn
init_db()
_scheduler_thread = threading.Thread(target=background_scheduler, daemon=True)
_scheduler_thread.start()

if __name__ == "__main__":
    start_server()
