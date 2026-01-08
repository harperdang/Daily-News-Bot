import feedparser
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
import datetime
import os

# --- 配置区域 ---
# 1. 媒体列表 (RSS源最稳定，如果没有RSS我们后续再加爬虫逻辑)
MEDIA_LIST = [
    {"name": "南华早报 (SCMP)", "url": "https://www.scmp.com/rss/91/feed"},
    {"name": "财新网 (Caixin)", "url": "http://www.caixin.com/rss/"},
    {"name": "纽约时报 (NYT World)", "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"},
]

# --- 核心逻辑 ---
def fetch_news():
    report_html = "<h2>📅 今日媒体简报</h2>"
    report_html += f"<p>日期：{datetime.date.today()}</p><hr>"

    for media in MEDIA_LIST:
        try:
            print(f"正在抓取：{media['name']}...")
            feed = feedparser.parse(media['url'])
            
            report_html += f"<h3>📰 {media['name']}</h3><ul>"
            
            # 获取前 5 条新闻
            for entry in feed.entries[:5]:
                link = entry.link
                title = entry.title
                report_html += f"<li><a href='{link}'>{title}</a></li>"
            
            report_html += "</ul>"
        except Exception as e:
            print(f"抓取 {media['name']} 失败: {e}")
            report_html += f"<p>{media['name']} 抓取失败</p>"
    
    return report_html

def send_email(content):
    # 从 GitHub Secrets 获取账号密码
    sender = os.environ.get('MAIL_USERNAME')
    password = os.environ.get('MAIL_PASSWORD')
    receiver = os.environ.get('MAIL_RECEIVER') # 接收者的邮箱

    if not sender or not password:
        print("未配置邮箱 Secrets，跳过发送")
        print(content) # 在日志里打印出来以便调试
        return

    message = MIMEMultipart()
    message['From'] = Header("News Bot", 'utf-8')
    message['To'] = Header("Reader", 'utf-8')
    message['Subject'] = Header(f"【早报】{datetime.date.today()} 重点媒体标题", 'utf-8')
    
    message.attach(MIMEText(content, 'html', 'utf-8'))

    try:
        # 这里以 Gmail 为例，如果是其他邮箱需改 smtp 地址
        # Gmail: smtp.gmail.com, 587
        # Outlook: smtp.office365.com, 587
        # QQ: smtp.qq.com, 465 (需要用 SSL)
        server = smtplib.SMTP('smtp.gmail.com', 587) 
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, [receiver], message.as_string())
        server.quit()
        print("邮件发送成功！")
    except Exception as e:
        print(f"邮件发送失败: {e}")

if __name__ == "__main__":
    news_content = fetch_news()
    send_email(news_content)
