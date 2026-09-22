import re
import html
import json
import urllib.request
import urllib.parse
from typing import Dict, Any, List, Optional
from deep_translator import MyMemoryTranslator
from .config import CHINA_CATEGORIES, CHINA_KEYWORDS

_translation_cache: Dict[str, str] = {}
_translator_instance: Optional[MyMemoryTranslator] = None

def get_translator() -> MyMemoryTranslator:
    global _translator_instance
    if _translator_instance is None:
        _translator_instance = MyMemoryTranslator(source='en-US', target='zh-CN')
    return _translator_instance

def clean_news_text(text: str) -> str:
    """Pre-cleaning: unescape entities, remove replacement chars and source tags."""
    if not text:
        return ""
    text = html.unescape(text)
    # Fix unicode replacement character \ufffd (e.g., China's -> China\ufffds)
    text = re.sub(r'(\w)\ufffd(\w)', r"\1'\2", text)
    text = re.sub(r'\s*\ufffd\s*', ' - ', text)
    # Convert curly quotes and dashes
    text = text.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    text = text.replace('—', ' - ').replace('–', ' - ')
    # Strip trailing Bloomberg signatures
    text = re.sub(r'[\-—|•]\s*Bloomberg(\.com|\s*News)?\s*$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^Bloomberg(\s*News)?:\s*', '', text, flags=re.IGNORECASE)
    # Normalize whitespaces
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def polish_chinese_financial(text: str) -> str:
    """Post-polishing: correct literal machine translation into professional financial Chinese."""
    if not text:
        return ""
    text = html.unescape(text).strip()
    
    # Financial glossary replacements
    replacements = [
        ("中国银行采用", "中国银行业采用"),
        ("中国银行使用", "中国银行业使用"),
        ("中国银行发行", "中国银行业发行"),
        ("誓言在", "表态在"),
        ("誓言将", "表态将"),
        ("誓言实现", "强调确保实现"),
        ("陷入弱点", "出现疲软迹象"),
        ("弱点：", "痛点："),
        ("消费者不消费", "居民消费意愿低迷"),
        ("机器人出租车", "自动驾驶出租车 (Robotaxi)"),
        ("停电后", "故障停运后"),
        ("关税削减", "下调关税"),
        ("削减关税", "下调关税"),
        ("贸易休战", "贸易休战协定"),
        ("中国人民银行", "中国央行 (PBOC)"),
        ("独角兽表示", "独角兽企业计划"),
        ("出售中国业务的股份", "出售在华业务股权"),
        ("在华业务的股份", "在华业务股权"),
        ("高科技繁荣未能阻止", "高科技投资热潮未能扭转"),
        ("经济疲软后", "经济增速放缓后"),
        ("年度增长目标", "全年经济增长目标"),
        ("加息将有助于达到通胀目标", "加息将助力实现通胀目标"),
        ("显示出总缺乏财政纪律", "直言美国极度缺乏财政纪律"),
        ("俄罗斯石油流动下降", "受美制裁与沙特供应预期影响 俄原油出口放缓")
    ]
    for old, new in replacements:
        text = text.replace(old, new)
        
    return text.strip()

def translate_free(text: str, proxy: Optional[str] = None) -> str:
    """Translate English text to Chinese using cached engine with post-polishing."""
    if not text or not text.strip():
        return ""
    
    clean_text = clean_news_text(text)
    if clean_text in _translation_cache:
        return _translation_cache[clean_text]
    
    try:
        translator = get_translator()
        chunk = clean_text[:400]
        res = translator.translate(chunk)
        if res and not res.startswith("MYMEMORY WARNING") and not res.startswith("QUERY LENGTH"):
            polished = polish_chinese_financial(res)
            _translation_cache[clean_text] = polished
            return polished
    except Exception as e:
        print(f"Translation warning: {e}")

    return clean_text

def classify_category(text: str) -> str:
    """Classify news into one of the China categories based on keywords."""
    lower_text = text.lower()
    scores = {}
    for cat, kws in CHINA_CATEGORIES.items():
        score = sum(2 if kw in lower_text.split() else (1 if kw in lower_text else 0) for kw in kws)
        if score > 0:
            scores[cat] = score
            
    if scores:
        return max(scores.items(), key=lambda x: x[1])[0]
    return "宏观政策"

def analyze_sentiment(text: str) -> str:
    """Detect financial sentiment: 利多 (Bullish), 利空 (Bearish), or 中性 (Neutral)."""
    lower = text.lower()
    bullish_kws = [
        "rise", "surge", "gain", "record", "jump", "boost", "rebound", "high",
        "stimulus", "advance", "growth", "rally", "easing", "recovery", "cut tariff",
        "cut tariffs", "deal", "truce", "optimism", "上涨", "增", "利好", "反弹", "突破", "复苏"
    ]
    bearish_kws = [
        "drop", "fall", "slump", "plunge", "decline", "tumble", "cut", "warn",
        "sanction", "tariff", "risk", "debt", "crisis", "pressure", "probe",
        "halt", "freeze", "curb", "ban", "loss", "deficit", "default", "outage",
        "下跌", "降", "跌", "关税", "制裁", "承压", "限制", "调查", "暂停", "风险"
    ]
    
    bull_count = sum(1 for kw in bullish_kws if kw in lower)
    bear_count = sum(1 for kw in bearish_kws if kw in lower)
    
    if bull_count > bear_count:
        return "利多"
    elif bear_count > bull_count:
        return "利空"
    return "中性"

def check_china_focus(text: str) -> bool:
    """Check if the text is related to China."""
    lower = text.lower()
    return any(kw in lower for kw in CHINA_KEYWORDS)

def ai_summarize(
    title: str,
    content: str,
    api_key: str,
    base_url: str = "https://api.openai.com/v1",
    model: str = "gpt-3.5-turbo"
) -> Optional[Dict[str, Any]]:
    """Optional LLM integration for generating structured Chinese financial summary."""
    if not api_key:
        return None
        
    prompt = f"""你是一名资深彭博社（Bloomberg）特约财经中文主编。请针对以下这篇彭博社/辛迪加授权转载的中国相关英文报道，进行高质量翻译与专业提炼：
英文标题: {title}
正文或概要: {content[:1500]}

请严格输出合法的 JSON 格式（不要包含任何 markdown 语法之外的额外文字），字段如下：
{{
  "title_zh": "地道、醒目的中文财经标题（不要直译，要符合彭博终端中文风格）",
  "summary_zh": "用中文简练归纳本则新闻的核心背景与主要内容（100-200字）",
  "category": "分类（宏观政策/贸易关税/科技半导体/金融外汇/房产消费/大宗商品）",
  "sentiment": "情绪（利多/利空/中性）",
  "key_points": ["核心要点1", "核心要点2", "核心要点3"]
}}
"""
    try:
        url = f"{base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "你是一名金融财经翻译专家，严格以 JSON 格式输出。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3
        }
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
        res = urllib.request.urlopen(req, timeout=12)
        resp_data = json.loads(res.read().decode("utf-8"))
        ans = resp_data["choices"][0]["message"]["content"].strip()
        if "```json" in ans:
            ans = ans.split("```json")[1].split("```")[0].strip()
        elif "```" in ans:
            ans = ans.split("```")[1].split("```")[0].strip()
        return json.loads(ans)
    except Exception as e:
        print(f"AI summarize error: {e}")
        return None

def process_and_translate_article(
    title_en: str,
    desc_en: str,
    content_en: str = "",
    proxy: Optional[str] = None,
    ai_config: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Process an article: translate title and body, classify, and extract key points."""
    clean_title = clean_news_text(title_en)
    clean_desc = clean_news_text(desc_en)
    combined_en = f"{clean_title}. {clean_desc}".strip()
    
    # 1. Try AI first if configured
    if ai_config and ai_config.get("api_key"):
        ai_res = ai_summarize(
            clean_title,
            content_en or clean_desc,
            api_key=ai_config["api_key"],
            base_url=ai_config.get("base_url", "https://api.openai.com/v1"),
            model=ai_config.get("model", "gpt-3.5-turbo")
        )
        if ai_res:
            return {
                "title_zh": ai_res.get("title_zh", clean_title),
                "summary_zh": ai_res.get("summary_zh", ""),
                "content_zh": "",
                "category": ai_res.get("category", classify_category(combined_en)),
                "sentiment": ai_res.get("sentiment", analyze_sentiment(combined_en)),
                "key_points": ai_res.get("key_points", []),
                "is_china_focus": check_china_focus(combined_en)
            }
            
    # 2. Free translation engine with terminology polishing
    title_zh = translate_free(clean_title, proxy=proxy)
    summary_zh = translate_free(clean_desc, proxy=proxy) if clean_desc else ""
    
    # Generate structured bullet key points
    key_points = []
    if summary_zh:
        sentences = [s.strip() for s in re.split(r'[。；;\n]', summary_zh) if len(s.strip()) > 6]
        key_points = sentences[:3]
    if not key_points and title_zh:
        key_points = [title_zh]
        
    category = classify_category(combined_en)
    sentiment = analyze_sentiment(combined_en)
    is_china = check_china_focus(combined_en)
    
    return {
        "title_zh": title_zh or clean_title,
        "summary_zh": summary_zh or title_zh,
        "content_zh": "",
        "category": category,
        "sentiment": sentiment,
        "key_points": key_points,
        "is_china_focus": is_china
    }
