import feedparser
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
import datetime
import os
import ssl

# --- 1. 媒体列表 (这里可以随时修改) ---
MEDIA_LIST = [
    {"name": "南华早报 (SCMP)", "url": "https://www.scmp.com/rss/91/feed"},
    {"name": "财新网 (Caixin)", "url": "http://www.caixin.com/rss/"},
    {"name": "纽约时报 (NYT World)", "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"},
]

# --- 2. 核心抓取逻辑 ---
def fetch_news():
    print("正在生成今日简报...")
    report_html = "<h2>📅 今日媒体简报</h2>"
    report_html += f"<p>日期：{datetime.date.today()}</p><hr>"

    for media in MEDIA_LIST:
        try:
            print(f"正在抓取：{media['name']}...")
            # 增加超时设置，防止卡死
            feed = feedparser.parse(media['url'])
            
            if not feed.entries:
                print(f"  -> {media['name']} 没有获取到内容，可能是RSS失效或网络问题。")
                report_html += f"<h3>📰 {media['name']}</h3><p>暂无更新或抓取失败</p>"
                continue

            report_html += f"<h3>📰 {media['name']}</h3><ul>"
            
            # 获取前 5 条
            for entry in feed.entries[:5]:
                link = entry.link
                title = entry.title
                report_html += f"<li><a href='{link}'>{title}</a></li>"
            
            report_html += "</ul>"
        except Exception as e:
            print(f"抓取 {media['name']} 报错: {e}")
            report_html += f"<p>{media['name']} 抓取异常</p>"
    
    return report_html

# --- 3. 发送邮件 (使用更稳定的 SSL 465 端口) ---
def send_email(content):
    sender = os.environ.get('MAIL_USERNAME')
    password = os.environ.get('MAIL_PASSWORD')
    receiver = os.environ.get('MAIL_RECEIVER')

    if not sender or not password:
        print("❌ 错误: 未在 Secrets 中找到账号或密码，无法发送邮件。")
        return

    # 自动判断邮箱服务器
    if 'qq.com' in sender:
        smtp_server = 'smtp.qq.com'
    elif '163.com' in sender:
        smtp_server = 'smtp.163.com'
    elif 'gmail.com' in sender:
        smtp_server = 'smtp.gmail.com'
    else:
        # 默认为 Gmail，如果用 Outlook 需手动改为 smtp.office365.com
        smtp_server = 'smtp.gmail.com'

    print(f"正在连接邮件服务器: {smtp_server} (SSL模式)...")

    message = MIMEMultipart()
    message['From'] = Header("News Bot", 'utf-8')
    message['To'] = Header("Reader", 'utf-8')
    message['Subject'] = Header(f"【早报】{datetime.date.today()} 重点媒体标题", 'utf-8')
    message.attach(MIMEText(content, 'html', 'utf-8'))

    try:
        # 使用 SSL (端口 465) - 这是最稳定的方式
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, 465, context=context) as server:
            server.login(sender, password)
            server.sendmail(sender, [receiver], message.as_string())
        
        print("✅ 邮件发送成功！请检查收件箱。")
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")
        # 如果是 Gmail 报错，提示用户检查
        if 'gmail' in smtp_server:
             print("提示: Gmail 请确保使用的是 16 位的【应用专用密码】，而不是登录密码。")

if __name__ == "__main__":
    news_content = fetch_news()
    send_email(news_content)
