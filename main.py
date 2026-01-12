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

# --- 1. 带地区标签的媒体列表 ---
# 我们在这里直接给媒体分类，方便 AI 做地区分析
MEDIA_SOURCES = {
    "US": [
        {"name": "The New York Times", "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"},
        {"name": "The Wall Street Journal", "url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml"},
        {"name": "The Washington Post", "url": "https://feeds.washingtonpost.com/rss/world"},
        {"name": "Bloomberg", "url": "https://feeds.bloomberg.com/politics/news.xml"},
        {"name": "Politico", "url": "https://rss.politico.com/politics-news.xml"},
        {"name": "Los Angeles Times", "url": "https://www.latimes.com/world/rss2.0.xml"},
        {"name": "Reuters", "url": "https://news.google.com/rss/search?q=site:reuters.com&hl=en-US&gl=US&ceid=US:en"},
    ],
    "Europe": [
        {"name": "The Guardian", "url": "https://www.theguardian.com/world/rss"},
        {"name": "Financial Times", "url": "https://www.ft.com/rss/home"},
    ],
    "Asia": [
        {"name": "Nikkei Asia", "url": "https://asia.nikkei.com/rss/feed/nar"},
        {"name": "The Straits Times", "url": "https://www.straitstimes.com/news/world/rss.xml"},
        {"name": "South China Morning Post", "url": "https://www.scmp.com/rss/91/feed"}, # 加回 SCMP 补充亚洲视角
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

    # 遍历每个地区
    for region, sources in MEDIA_SOURCES.items():
        for source in sources:
            try:
                # 使用 verify=False 防止部分 SSL 报错，设置 user-agent
                # 这里的 agent 设置非常重要，防止被 403 拦截
                feed = feedparser.parse(source['url'], agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
                
                if not feed.entries:
                    continue

                for entry in feed.entries:
                    # 1. 时间筛选 (24小时内)
                    published_time = None
                    # 尝试各种时间格式
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        published_time = datetime.datetime.fromtimestamp(time.mktime(entry.published_parsed))
                    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                        published_time = datetime.datetime.fromtimestamp(time.mktime(entry.updated_parsed))
                    
                    is_recent = False
                    if published_time:
                        if (now - published_time).total_seconds() <= 24 * 3600:
                            is_recent = True
                    else:
                        # 如果没有时间戳，默认取前 3 条，宁可错杀不可放过
                        is_recent = True 
                        if len(structured_news) > 5: is_recent = False # 简单限流

                    if is_recent:
                        structured_news.append({
                            "region": region, # 关键：带上地区标签
                            "source": source['name'],
                            "title": entry.title,
                            "link": entry.link,
                        })

            except Exception as e:
                print(f"Error fetching {source['name']}: {e}")

    print(f"共抓取到 {len(structured_news)} 条新闻，准备发送给 AI...")
    return structured_news

def call_gemini_api(news_data):
    if not GEMINI_API_KEY:
        print("❌ 错误: 没找到 GEMINI_API_KEY")
        return None
    
    # 限制 token 数量，防止报错，取前 120 条（通常够了）
    data_payload = json.dumps(news_data[:120], ensure_ascii=False)

    # --- 精心设计的 Prompt，包含你的所有新需求 ---
    prompt = f"""
    你是一名资深的国际媒体分析师。我将提供给你一份过去24小时的全球新闻列表，数据格式包含“地区(Region)”、“媒体(Source)”和“标题(Title)”。

    请仔细阅读以下数据：
    {data_payload}

    请生成一份专业的 HTML 简报（不要使用Markdown代码块），包含以下三个部分：

    ### 第一部分：跨区域舆情对比 (Media Focus Analysis)
    **请分析“美国媒体”、“欧洲媒体”和“亚洲媒体”在过去24小时的关注重点有何不同？**
    - 比如：美国是否聚焦于国内政治或中东？亚洲是否更关注经济或台海？
    - 请用 200 字左右的中文进行深度点评。

    ### 第二部分：全球核心议题聚合 (Top Stories)
    **请找出全球媒体共同关注的 5-8 个核心大事件。**
    - 对每个事件，写一个**中文主标题**。
    - 下方附上**中英文摘要**。
    - 列出相关报道的链接（保留媒体名称，例如：[NYT] Title...）。

    ### 第三部分：地区观察 (Regional Highlights)
    - 如果有某些新闻只在特定地区（如仅在亚洲）被热议，请单独列出 1-2 条。

    **HTML 样式要求**：
    - 使用简洁的内联 CSS。
    - 标题使用深蓝色 (#2c3e50)，正文使用深灰色 (#34495e)。
    - 链接去除下划线，使用蓝色 (#3498db)。
    - 不需要 `<html>` 或 `<body>` 标签，直接输出内容。
    """

    # --- 修复后的 URL 构造方式 ---
    # 使用 v1beta 接口，这是最稳的
    base_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"
    url = f"{base_url}?key={GEMINI_API_KEY}"
    
    headers = {'Content-Type': 'application/json'}
    body = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }

    print("🤖 正在连接 Google Gemini (HTTP 直连)...")
    
    try:
        # 增加 timeout 防止网络卡死
        response = requests.post(url, headers=headers, json=body, timeout=60)
        
        if response.status_code != 200:
            print(f"❌ API 请求失败，状态码: {response.status_code}")
            print(f"❌ 错误信息: {response.text}")
            return None
            
        result = response.json()
        
        # 安全解析
        if 'candidates' in result and result['candidates']:
            return result['candidates'][0]['content']['parts'][0]['text']
        else:
            print("❌ API 返回了空内容，可能是被安全策略拦截。")
            print(result)
            return None

    except Exception as e:
        print(f"❌ 连接发生异常: {e}")
        return None

def send_email(content):
    sender = os.environ.get('MAIL_USERNAME')
    password = os.environ.get('MAIL_PASSWORD')
    receivers_str = os.environ.get('MAIL_RECEIVER')

    if not sender or not password or not receivers_str:
        print("❌ 无法发送邮件：Secrets 缺失")
        return

    receivers = [r.strip() for r in receivers_str.split(',') if r.strip()]

    # 自动匹配服务器
    if 'qq.com' in sender: smtp_server = 'smtp.qq.com'
    elif '163.com' in sender: smtp_server = 'smtp.163.com'
    else: smtp_server = 'smtp.gmail.com'

    msg = MIMEMultipart()
    msg['From'] = Header("News Analyst", 'utf-8')
    msg['To'] = Header("Subscriber", 'utf-8')
    msg['Subject'] = Header(f"【深度舆情】{datetime.date.today()} 全球媒体关注点分析", 'utf-8')

    # 加上精美的头部
    full_html = f"""
    <div style="font-family: 'Helvetica Neue', Arial, sans-serif; max-width: 800px; margin: auto; padding: 20px; background-color: #f9f9f9;">
        <div style="background-color: #2c3e50; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
            <h1 style="margin:0; font-size: 24px;">🌍 Global Media Monitor</h1>
            <p style="margin:5px 0 0; font-size: 14px; opacity: 0.8;">{datetime.date.today()} | US · Europe · Asia Comparison</p>
        </div>
        <div style="background-color: white; padding: 20px; border: 1px solid #ddd; border-top: none; border-radius: 0 0 8px 8px;">
            {content}
        </div>
        <div style="text-align: center; margin-top: 20px; color: #aaa; font-size: 12px;">
            Powered by Google Gemini 1.5 & GitHub Actions
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
    # 1. 抓取
    news_data = fetch_all_news()
    
    if news_data:
        # 2. 分析
        analysis_html = call_gemini_api(news_data)
        
        # 3. 发送
        if analysis_html:
            # 清洗 Markdown 标记
            clean_html = analysis_html.replace("```html", "").replace("```", "").strip()
            send_email(clean_html)
        else:
            print("⚠️ 分析失败，未发送邮件。请检查日志中的 API 报错。")
    else:
        print("未抓取到任何新闻，请检查网络或 RSS 源。")
