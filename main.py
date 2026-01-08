import feedparser
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
import datetime
import time
import os
import ssl

# --- 1. 定制媒体列表 (英文版 - 15家) ---
MEDIA_LIST = [
    # --- 美国 (US) ---
    {"name": "Washington Post", "url": "https://feeds.washingtonpost.com/rss/world"},
    {"name": "Wall Street Journal", "url": "https://feeds.a.dj.com/rss/RSSWorldNews.xml"},
    {"name": "New York Times", "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"},
    {"name": "Los Angeles Times", "url": "https://www.latimes.com/world/rss2.0.xml"},
    {"name": "Politico", "url": "https://rss.politico.com/politics-news.xml"},
    {"name": "Bloomberg", "url": "https://feeds.bloomberg.com/politics/news.xml"}, # 彭博社部分源可能有反爬限制
    {"name": "Reuters", "url": "https://news.google.com/rss/search?q=site:reuters.com&hl=en-US&gl=US&ceid=US:en"}, # 路透社专属源

    # --- 欧洲/英国 (Europe/UK) ---
    {"name": "The Guardian", "url": "https://www.theguardian.com/world/rss"},
    {"name": "Financial Times", "url": "https://www.ft.com/rss/home"},

    # --- 亚洲 (Asia) ---
    {"name": "Nikkei Asia", "url": "https://asia.nikkei.com/rss/feed/nar"},
    {"name": "Straits Times (Singapore)", "url": "https://www.straitstimes.com/news/world/rss.xml"},
    {"name": "Hong Kong Free Press", "url": "https://www.hongkongfp.com/feed/"},
    {"name": "Japan Times", "url": "https://www.japantimes.co.jp/feed/"}, # 修正为官方标准feed
    {"name": "Korea Times", "url": "https://www.koreatimes.co.kr/www/rss/rss.xml"},
    {"name": "Taipei Times", "url": "https://www.taipeitimes.com/xml/index.rss"},
]

# --- 2. 核心抓取逻辑 (24小时筛选) ---
def fetch_news():
    print("Generating Daily Briefing...")
    # 获取当前UTC时间
    now = datetime.datetime.utcnow()
    
    # 邮件标题和头部
    report_html = "<h2>🌍 Global Daily Briefing (English)</h2>"
    report_html += f"<p>Date: {datetime.date.today()} | Period: Past 24 Hours</p><hr>"

    has_content = False

    for media in MEDIA_LIST:
        try:
            print(f"Fetching: {media['name']}...")
            # 设置 user-agent 防止部分基础反爬
            feed = feedparser.parse(media['url'], agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
            
            if not feed.entries:
                print(f"  -> {media['name']} has no content (possible block or empty feed).")
                continue

            # 筛选过去 24 小时内的文章
            recent_entries = []
            for entry in feed.entries:
                # 尝试获取发布时间
                published_time = None
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    published_time = datetime.datetime.fromtimestamp(time.mktime(entry.published_parsed))
                elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                    published_time = datetime.datetime.fromtimestamp(time.mktime(entry.updated_parsed))
                
                # 如果找不到时间，默认保留（防止漏掉重要新闻），或者你可以选择跳过
                if published_time:
                    # 计算时间差
                    if (now - published_time).total_seconds() <= 24 * 3600:
                        recent_entries.append(entry)
                else:
                    # 如果RSS没有标准时间戳，保守起见我们取前3条
                    recent_entries.append(entry)

            # 如果筛选后只有太多旧闻，只取前 5 条作为兜底，防止邮件太长
            # 这里逻辑是：如果有recent_entries，就用recent_entries。
            # 另外为了防止某些源一天发几百条，限制最大数量为 10
            final_entries = recent_entries[:10]
            
            if final_entries:
                has_content = True
                report_html += f"<h3>📰 {media['name']}</h3><ul>"
                for entry in final_entries:
                    link = entry.link
                    title = entry.title
                    report_html += f"<li><a href='{link}' style='text-decoration:none; color:#0366d6;'>{title}</a></li>"
                report_html += "</ul>"
            else:
                print(f"  -> {media['name']} fetched successfully but no new articles in last 24h.")

        except Exception as e:
            print(f"Error fetching {media['name']}: {e}")

    if not has_content:
        report_html += "<p>No updates detected in the last 24 hours.</p>"
    
    return report_html

# --- 3. 发送邮件 (SSL 465) ---
def send_email(content):
    sender = os.environ.get('MAIL_USERNAME')
    password = os.environ.get('MAIL_PASSWORD')
    receiver = os.environ.get('MAIL_RECEIVER')

    if not sender or not password:
        print("❌ Error: Secrets not found.")
        return

    # 自动判断邮件服务器
    if 'qq.com' in sender:
        smtp_server = 'smtp.qq.com'
    elif '163.com' in sender:
        smtp_server = 'smtp.163.com'
    elif 'gmail.com' in sender:
        smtp_server = 'smtp.gmail.com'
    else:
        smtp_server = 'smtp.gmail.com' 

    message = MIMEMultipart()
    message['From'] = Header("News Bot", 'utf-8')
    message['To'] = Header("Reader", 'utf-8')
    message['Subject'] = Header(f"【Global Briefing】{datetime.date.today()} - 15 Sources", 'utf-8')
    message.attach(MIMEText(content, 'html', 'utf-8'))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, 465, context=context) as server:
            server.login(sender, password)
            server.sendmail(sender, [receiver], message.as_string())
        print("✅ Email sent successfully!")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

if __name__ == "__main__":
    news_content = fetch_news()
    send_email(news_content)
