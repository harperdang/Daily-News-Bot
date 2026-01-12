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
import requests

# --- 配置 ---
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# --- 1. 媒体列表 ---
MEDIA_SOURCES = {
    "US": [
        {"name": "The New York Times", "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"},
        {"name": "The Wall Street Journal", "url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml"},
        {"name": "The Washington Post", "url": "https://feeds.washingtonpost.com/rss/world"},
        {"name": "Bloomberg", "url": "https://feeds.bloomberg.com/politics/news.xml"},
        {"name": "Politico", "url": "https://rss.politico.com/politics-news.xml"},
        {"name": "Reuters", "url": "https://news.google.com/rss/search?q=site:reuters.com&hl=en-US&gl=US&ceid=US:en"},
    ],
    "Europe": [
        {"name": "The Guardian", "url": "https://www.theguardian.com/world/rss"},
        {"name": "Financial Times", "url": "https://www.ft.com/rss/home"},
    ],
    "Asia": [
        {"name": "Nikkei Asia", "url": "https://asia.nikkei.com/rss/feed/nar"},
        {"name": "The Straits Times", "url": "https://www.straitstimes.com/news/world/rss.xml"},
        {"name": "South China Morning Post", "url": "https://www.scmp.com/rss/91/feed"}, 
        {"name": "Hong Kong Free Press", "url": "https://www.hongkongfp.com/feed/"},
        {"name": "The Japan Times", "url": "https://www.japantimes.co.jp/feed/"},
        {"name": "The Korea Times", "url": "https://www.koreatimes.co.kr/www/rss/rss.xml"},
        {"name": "Taipei Times", "url": "https://www.taipeitimes.com/xml/index.rss"},
    ]
}

def fetch_all_news():
    print("正在抓取 RSS 数据...")
    now = datetime.datetime.utcnow()
    structured_news = []

    for region, sources in MEDIA_SOURCES.items():
        for source in sources:
            try:
                feed = feedparser.parse(source['url'], agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
                if not feed.entries: continue

                for entry in feed.entries:
                    published_time = None
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        published_time = datetime.datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                        published_time = datetime.datetime.fromtimestamp(time.mktime(entry.updated_parsed))
                    
                    is_recent = False
                    if published_time:
                        if (now - published_time).total_seconds() <= 24 * 3600:
                            is_recent = True
                    else:
                        is_recent = True 
                        if len(structured_news) > 150: is_recent = False

                    if is_recent:
                        structured_news.append({
                            "region": region,
                            "source": source['name'],
                            "title": entry.title,
                            "link": entry.link,
                        })
            except Exception as e:
                print(f"Error fetching {source['name']}: {e}")

    print(f"共抓取到 {len(structured_news)} 条新闻。")
    return structured_news

def get_best_available_model(api_key):
    """自动查询 Google API"""
    print("🔍 正在查询可用模型列表...")
    
    # 纯净 URL，绝对不带括号
    raw_base = "https://generativelanguage.googleapis.com/v1beta/models"
    url = f"{raw_base}?key={api_key}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"⚠️ 无法获取模型列表: {response.text}")
            return 'models/gemini-1.5-flash'

        data = response.json()
        models = data.get('models', [])
        
        candidates = []
        for m in models:
            name = m.get('name', '')
            methods = m.get('supportedGenerationMethods', [])
            if 'generateContent' in methods and 'gemini' in name:
                candidates.append(name)
        
        print(f"✅ 发现可用模型: {candidates}")

        # 单行列表写法，防止复制换行错误
        priority_keywords = ['gemini-2.0-flash', 'gemini-2.5-pro', 'gemini-1.5-pro', 'gemini-1.5-flash']
        
        for keyword in priority_keywords:
            for c in candidates:
                if keyword in c:
                    return c
            
        return candidates[0] if candidates else 'models/gemini-1.5-flash'

    except Exception as e:
        print(f"⚠️ 模型探测失败: {e}")
        return 'models/gemini-1.5-flash'

def call_gemini_api(news_data):
    if not GEMINI_API_KEY:
        print("❌ 错误: 没找到 GEMINI_API_KEY")
        return None
    
    model_name = get_best_available_model(GEMINI_API_KEY)
    print(f"🤖 决定使用模型: {model_name}")

    data_payload = json.dumps(news_data[:150], ensure_ascii=False)

    prompt = f"""
    你是一名资深的国际媒体分析师。以下是过去24小时的全球新闻列表。
    数据：
    {data_payload}

    请生成一份专业的 HTML 简报（直接输出HTML，不要Markdown，不要 ```html 包裹）：

    ### 第一部分：跨区域舆情对比 (Media Focus Analysis)
    **深度分析“美国”、“欧洲”和“亚洲”媒体的关注点差异。**
    - 比如：美国是否聚焦于国内政治或中东？亚洲是否更关注经济或台海？
    - 请用 300 字左右的中文进行深度点评。

    ### 第二部分：全球核心议题聚合 (Top Stories)
    **找出全球媒体共同关注的 5-8 个核心大事件。**
    - 使用 <h3 style="color:#2c3e50; margin-top:20px;">中文主标题</h3>
    - <p style="font-size:14px;">中英文摘要（100字）</p>
    - <ul style="font-size:12px; color:#666;"><li>[媒体名] 英文原标题 (带链接)</li></ul>

    ### 第三部分：地区独家 (Regional Highlights)
    - 如果有某些新闻只在特定地区（如仅在亚洲）被热议，请单独列出 1-2 条。

    **样式要求**：
    - 使用内联CSS。
    - 标题深蓝色 (#2c3e50)，正文 (#333)。
    - 链接蓝色 (#3498db)，去除下划线。
    """

    # --- 核心修正点：纯净字符串 ---
    # 绝对没有任何 Markdown 格式
    base_url = "https://generativelanguage.googleapis.com/v1beta"
    
    final_url = f"{base_url}/{model_name}:generateContent?key={GEMINI_API_KEY}"

    headers = {'Content-Type': 'application/json'}
    body = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    try:
        response = requests.post(final_url, headers=headers, json=body, timeout=120)
        
        if response.status_code != 200:
            print(f"❌ API 请求失败，状态码: {response.status_code}")
            print(f"❌ 错误信息: {response.text}")
            return None
            
        result = response.json()
        
        if 'candidates' in result and result['candidates']:
            return result['candidates'][0]['content']['parts'][0]['text']
        else:
            print("❌ API 返回空内容:")
            print(result)
            return None

    except Exception as e:
        print(f"❌ 连接异常: {e}")
        return None

def send_email(content):
    sender = os.environ.get('MAIL_USERNAME')
    password = os.environ.get('MAIL_PASSWORD')
    receivers_str = os.environ.get('MAIL_RECEIVER')

    if not sender or not password or not receivers_str:
        print("❌ 无法发送邮件：Secrets 缺失")
        return

    receivers = [r.strip() for r in receivers_str.split(',') if r.strip()]

    if 'qq.com' in sender: smtp_server = 'smtp.qq.com'
    elif '163.com' in sender: smtp_server = 'smtp.163.com'
    else: smtp_server = 'smtp.gmail.com'

    msg = MIMEMultipart()
    msg['From'] = Header("News Analyst", 'utf-8')
    msg['To'] = Header("Subscriber", 'utf-8')
    msg['Subject'] = Header(f"【深度舆情】{datetime.date.today()} 全球媒体关注点分析", 'utf-8')

    full_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 800px; margin: auto; padding: 20px; background-color: #f9f9f9;">
        <div style="background-color: #2c3e50; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
            <h1 style="margin:0; font-size: 24px;">🌍 Global Media Monitor</h1>
            <p style="margin:5px 0 0; font-size: 14px; opacity: 0.8;">{datetime.date.today()} | US · Europe · Asia Analysis</p>
        </div>
        <div style="background-color: white; padding: 20px; border: 1px solid #ddd;">
            {content}
        </div>
        <div style="text-align: center; margin-top: 20px; color: #aaa; font-size: 12px;">
            Powered by Google Gemini & GitHub Actions
        </div>
    </div>
    """
    
    msg.attach(MIMEText(full_html, 'html', 'utf-8'))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, 465, context=context) as server:
            server.login(sender, password)
            server.sendmail(sender, receivers, msg.as_string())
        print("✅ 邮件发送成功！")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")

if __name__ == "__main__":
    news_data = fetch_all_news()
    if news_data:
        analysis_html = call_gemini_api(news_data)
        if analysis_html:
            # 清洗 Markdown 标记
            clean_html = analysis_html.replace("```html", "").replace("```", "").strip()
            send_email(clean_html)
        else:
            print("⚠️ 分析失败，跳过发送。")
    else:
        print("未抓取到新闻。")
