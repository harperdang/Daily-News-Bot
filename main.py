import feedparser
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
import datetime
import time
import os
import ssl
import json
from google import genai  # <--- 注意这里引用变了

# --- 配置 ---
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# --- 1. 媒体列表 ---
MEDIA_LIST = [
    # --- 美国 ---
    {"name": "Washington Post", "url": "https://feeds.washingtonpost.com/rss/world"},
    {"name": "Wall Street Journal", "url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml"},
    {"name": "New York Times", "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"},
    {"name": "Los Angeles Times", "url": "https://www.latimes.com/world/rss2.0.xml"},
    {"name": "Politico", "url": "https://rss.politico.com/politics-news.xml"},
    {"name": "Bloomberg", "url": "https://feeds.bloomberg.com/politics/news.xml"}, 
    {"name": "Reuters", "url": "https://news.google.com/rss/search?q=site:reuters.com&hl=en-US&gl=US&ceid=US:en"}, 

    # --- 欧洲/英国 ---
    {"name": "The Guardian", "url": "https://www.theguardian.com/world/rss"},
    {"name": "Financial Times", "url": "https://www.ft.com/rss/home"},

    # --- 亚洲 ---
    {"name": "Nikkei Asia", "url": "https://asia.nikkei.com/rss/feed/nar"},
    {"name": "Straits Times", "url": "https://www.straitstimes.com/news/world/rss.xml"},
    {"name": "Hong Kong Free Press", "url": "https://www.hongkongfp.com/feed/"},
    {"name": "Japan Times", "url": "https://www.japantimes.co.jp/feed/"}, 
    {"name": "Korea Times", "url": "https://www.koreatimes.co.kr/www/rss/rss.xml"},
    {"name": "Taipei Times", "url": "https://www.taipeitimes.com/xml/index.rss"},
]

def fetch_raw_data():
    """只负责抓取数据，不生成HTML"""
    print("正在抓取 RSS 数据...")
    now = datetime.datetime.utcnow()
    all_articles = []

    for media in MEDIA_LIST:
        try:
            feed = feedparser.parse(media['url'], agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
            if not feed.entries: continue

            for entry in feed.entries:
                # 时间筛选 (24h)
                published_time = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published_time = datetime.datetime.fromtimestamp(time.mktime(entry.published_parsed))
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    published_time = datetime.datetime.fromtimestamp(time.mktime(entry.updated_parsed))
                
                # 如果没有时间戳，默认收录前5条
                is_recent = False
                if published_time:
                    if (now - published_time).total_seconds() <= 24 * 3600:
                        is_recent = True
                else:
                    is_recent = True 

                if is_recent:
                    all_articles.append({
                        "source": media['name'],
                        "title": entry.title,
                        "link": entry.link,
                        "summary": entry.summary[:200] if hasattr(entry, 'summary') else ""
                    })
        except Exception as e:
            print(f"Error fetching {media['name']}: {e}")
            
    print(f"共抓取到 {len(all_articles)} 条新闻。")
    return all_articles

def analyze_with_ai(articles):
    """调用 Gemini API (新版 SDK) 进行整理"""
    if not GEMINI_API_KEY:
        print("❌ 未检测到 API Key，跳过 AI 分析，使用原始列表。")
        return None

    print("🤖 正在调用 Gemini 1.5 Flash (新版 SDK) 进行分析...")
    
    # 限制投喂数量，防止超出 Token 限制
    data_str = json.dumps(articles[:80], ensure_ascii=False) 
    
    prompt = f"""
    你是一名专业的国际新闻主编。以下是过去24小时全球主要媒体的原始新闻数据（JSON格式）：
    
    {data_str}

    请完成以下任务：
    1. **去重与聚类**：将报道同一事件的不同媒体新闻归为一类。
    2. **中文简报**：为每个重要事件写一段中文摘要（100字以内）。
    3. **引用来源**：在摘要下方列出原文链接（格式：[媒体名] 英文原标题 (带链接)）。
    4. **重要性排序**：优先展示地缘政治、中美关系、重大经济新闻。
    5. **HTML输出**：直接输出 HTML 代码 (无markdown标记)。
    
    HTML 格式要求：
    - 使用 <h3 style="color:#2c3e50; margin-top:20px;"> 作为事件标题。
    - 使用 <p style="font-size:14px; line-height:1.6;"> 作为摘要。
    - 使用 <ul style="color:#7f8c8d; font-size:12px;"> 列表展示来源。
    """

    try:
        # --- 新版 SDK 调用方式 ---
        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.models.generate_content(
            model='gemini-1.5-flash',  # 这里可以用 gemini-1.5-flash 或 gemini-2.0-flash-exp
            contents=prompt
        )
        return response.text
    except Exception as e:
        print(f"❌ AI 分析失败: {e}")
        # 打印更多错误细节以便调试
        if hasattr(e, 'message'): print(e.message)
        return None

def fallback_html_generator(articles):
    """如果 AI 挂了，使用这个备用生成器"""
    html = "<h2>⚠️ AI 服务暂时不可用，以下是原始列表</h2><hr>"
    articles_by_source = {}
    for art in articles:
        if art['source'] not in articles_by_source:
            articles_by_source[art['source']] = []
        articles_by_source[art['source']].append(art)
    
    for source, arts in articles_by_source.items():
        html += f"<h3>{source}</h3><ul>"
        for art in arts:
            html += f"<li><a href='{art['link']}'>{art['title']}</a></li>"
        html += "</ul>"
    return html

def send_email(content):
    sender = os.environ.get('MAIL_USERNAME')
    password = os.environ.get('MAIL_PASSWORD')
    receivers_str = os.environ.get('MAIL_RECEIVER')

    if not sender or not password or not receivers_str:
        print("❌ Error: Secrets not found.")
        return

    receivers = [r.strip() for r in receivers_str.split(',') if r.strip()]

    if 'qq.com' in sender: smtp_server = 'smtp.qq.com'
    elif '163.com' in sender: smtp_server = 'smtp.163.com'
    else: smtp_server = 'smtp.gmail.com' 

    message = MIMEMultipart()
    message['From'] = Header("AI News Editor", 'utf-8')
    message['To'] = Header("Global Readers", 'utf-8')
    message['Subject'] = Header(f"【AI Briefing】{datetime.date.today()} 全球舆情内参", 'utf-8')
    
    full_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 800px; margin: auto; padding: 20px;">
        <h2 style="color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px;">
            🌍 Global Daily Insight
        </h2>
        <p style="color: #7f8c8d; font-size: 12px; margin-bottom: 30px;">
            Powered by Google Gemini 1.5 | {datetime.date.today()}
        </p>
        {content}
    </div>
    """
    message.attach(MIMEText(full_html, 'html', 'utf-8'))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, 465, context=context) as server:
            server.login(sender, password)
            server.sendmail(sender, receivers, message.as_string())
        print(f"✅ Email sent successfully to {len(receivers)} recipients!")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

if __name__ == "__main__":
    raw_data = fetch_raw_data()
    if raw_data:
        ai_content = analyze_with_ai(raw_data)
        if ai_content:
            # 清洗 AI 可能带有的 Markdown 标记
            clean_content = ai_content.replace("```html", "").replace("```", "").strip()
            send_email(clean_content)
        else:
            print("⚠️ 降级使用普通列表发送")
            backup_content = fallback_html_generator(raw_data)
            send_email(backup_content)
    else:
        print("No news fetched today.")
