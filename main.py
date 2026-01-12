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
import re

# --- 配置 ---
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# 关键词追踪列表
TRACKED_KEYWORDS = ['China', 'Taiwan', 'semiconductor', 'chip', 'TSMC', 'Nvidia']

# 排除的媒体（不纳入关键词追踪）
EXCLUDED_KEYWORD_SOURCES = ['South China Morning Post']

# GitHub Gist 用于存储预测数据（需要配置 GIST_TOKEN 和 GIST_ID）
GIST_TOKEN = os.environ.get('GIST_TOKEN')
GIST_ID = os.environ.get('GIST_ID')

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
    """抓取所有 RSS 新闻"""
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
                        if len(structured_news) > 200: is_recent = False

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

def filter_keyword_news(news_data):
    """筛选包含关键词的新闻（排除特定媒体）"""
    keyword_news = []
    for news in news_data:
        # 排除特定媒体
        if news['source'] in EXCLUDED_KEYWORD_SOURCES:
            continue
            
        title_lower = news['title'].lower()
        for keyword in TRACKED_KEYWORDS:
            if keyword.lower() in title_lower:
                news_copy = news.copy()
                news_copy['matched_keyword'] = keyword
                keyword_news.append(news_copy)
                break
    return keyword_news

def load_previous_predictions():
    """从 GitHub Gist 加载前一天的预测"""
    if not GIST_TOKEN or not GIST_ID:
        print("⚠️ 未配置 GIST_TOKEN 或 GIST_ID，跳过预测复盘")
        return None
    
    try:
        headers = {
            'Authorization': f'token {GIST_TOKEN}',
            'Accept': 'application/vnd.github.v3+json'
        }
        response = requests.get(f'https://api.github.com/gists/{GIST_ID}', headers=headers, timeout=10)
        
        if response.status_code == 200:
            gist_data = response.json()
            if 'predictions.json' in gist_data['files']:
                content = gist_data['files']['predictions.json']['content']
                return json.loads(content)
        return None
    except Exception as e:
        print(f"⚠️ 加载预测数据失败: {e}")
        return None

def save_predictions(predictions):
    """保存今天的预测到 GitHub Gist"""
    if not GIST_TOKEN or not GIST_ID:
        print("⚠️ 未配置 GIST_TOKEN 或 GIST_ID，跳过保存预测")
        return
    
    try:
        headers = {
            'Authorization': f'token {GIST_TOKEN}',
            'Accept': 'application/vnd.github.v3+json'
        }
        data = {
            'files': {
                'predictions.json': {
                    'content': json.dumps(predictions, ensure_ascii=False, indent=2)
                }
            }
        }
        response = requests.patch(f'https://api.github.com/gists/{GIST_ID}', 
                                  headers=headers, json=data, timeout=10)
        if response.status_code == 200:
            print("✅ 预测数据已保存")
        else:
            print(f"⚠️ 保存预测失败: {response.text}")
    except Exception as e:
        print(f"⚠️ 保存预测数据失败: {e}")

def get_available_models(api_key):
    """获取所有可用的 Gemini 模型列表，按优先级排序"""
    print("🔍 正在查询可用模型列表...")
    
    base_url = "https://generativelanguage.googleapis.com/v1beta/models"
    url = f"{base_url}?key={api_key}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"⚠️ 无法获取模型列表: {response.text}")
            return ['models/gemini-1.5-flash', 'models/gemini-1.5-pro']

        data = response.json()
        models = data.get('models', [])
        
        candidates = []
        for m in models:
            name = m.get('name', '')
            methods = m.get('supportedGenerationMethods', [])
            if 'generateContent' in methods and 'gemini' in name:
                candidates.append(name)
        
        print(f"✅ 发现可用模型: {candidates}")

        # 优先使用 Pro 模型（输出更长更完整）
        priority_keywords = [
            'gemini-1.5-pro',
            'gemini-2.0-flash',
            'gemini-1.5-flash',
            'gemini-pro',
        ]
        
        sorted_models = []
        for keyword in priority_keywords:
            for c in candidates:
                if keyword in c and '-exp' not in c and c not in sorted_models:
                    sorted_models.append(c)
        
        for c in candidates:
            if c not in sorted_models:
                sorted_models.append(c)
        
        return sorted_models if sorted_models else ['models/gemini-1.5-flash']

    except Exception as e:
        print(f"⚠️ 模型探测失败: {e}")
        return ['models/gemini-1.5-flash', 'models/gemini-1.5-pro']

def call_gemini_api(prompt, max_retries=3):
    """通用的 Gemini API 调用函数，增加输出长度配置"""
    if not GEMINI_API_KEY:
        print("❌ 错误: 没找到 GEMINI_API_KEY")
        return None
    
    available_models = get_available_models(GEMINI_API_KEY)
    base_url = "https://generativelanguage.googleapis.com/v1beta"
    headers = {'Content-Type': 'application/json'}
    body = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "maxOutputTokens": 8192,  # 增加输出长度限制
            "temperature": 0.7
        }
    }

    for model_name in available_models:
        print(f"\n🤖 尝试使用模型: {model_name}")
        final_url = f"{base_url}/{model_name}:generateContent?key={GEMINI_API_KEY}"
        
        for attempt in range(max_retries):
            try:
                response = requests.post(final_url, headers=headers, json=body, timeout=180)
                
                if response.status_code == 200:
                    result = response.json()
                    if 'candidates' in result and result['candidates']:
                        # 检查是否因为长度被截断
                        finish_reason = result['candidates'][0].get('finishReason', '')
                        if finish_reason == 'MAX_TOKENS':
                            print(f"⚠️ 输出被截断，尝试下一个模型...")
                            break
                        print(f"✅ 成功使用模型 {model_name}")
                        return result['candidates'][0]['content']['parts'][0]['text']
                    else:
                        print(f"⚠️ API 返回空内容: {result}")
                        break
                
                elif response.status_code == 429:
                    error_data = response.json()
                    retry_delay = 30
                    
                    details = error_data.get('error', {}).get('details', [])
                    for detail in details:
                        if detail.get('@type') == 'type.googleapis.com/google.rpc.RetryInfo':
                            delay_str = detail.get('retryDelay', '30s')
                            retry_delay = int(delay_str.replace('s', ''))
                            break
                    
                    if attempt < max_retries - 1:
                        print(f"⏳ 配额限制，等待 {retry_delay} 秒后重试... (尝试 {attempt + 1}/{max_retries})")
                        time.sleep(retry_delay)
                    else:
                        print(f"⚠️ 模型 {model_name} 配额已用尽，尝试下一个模型...")
                        break
                
                else:
                    print(f"❌ API 请求失败，状态码: {response.status_code}")
                    print(f"❌ 错误信息: {response.text}")
                    break

            except requests.exceptions.Timeout:
                print(f"⏱️ 请求超时 (尝试 {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(5)
            except Exception as e:
                print(f"❌ 连接异常: {e}")
                break

    print("❌ 所有模型都失败了")
    return None

def generate_full_report(news_data, keyword_news, previous_predictions):
    """生成完整的新闻简报"""
    
    # 准备数据 - 限制数量以减少 token 消耗
    data_payload = json.dumps(news_data[:100], ensure_ascii=False)
    keyword_payload = json.dumps(keyword_news[:30], ensure_ascii=False)
    
    # 准备前一天预测复盘内容
    prediction_review = ""
    if previous_predictions:
        prediction_review = f"""
    ### 前一天预测复盘数据：
    {json.dumps(previous_predictions, ensure_ascii=False)}
    
    请在报告中增加"预测复盘"部分，评估前一天的市场预测是否准确。
    """

    prompt = f"""你是一名资深的国际媒体分析师。请根据以下新闻数据生成 HTML 简报。

=== 新闻数据 ===
{data_payload}

=== 关键词新闻（China/Taiwan/Semiconductor，已排除南华早报）===
{keyword_payload}

{prediction_review}

请生成 HTML 简报（直接输出HTML，不要```html包裹），包含以下6个部分：

【第一部分：跨区域舆情对比】
分析美国、欧洲、亚洲媒体关注点差异，约200字中文。

【第二部分：全球核心议题】
5-6个核心事件，每个包含：中文标题、50字摘要、2-3条原文链接。

【第三部分：China/Taiwan/Semiconductor 专题】
先写150字分析（含你的判断），再列出相关新闻链接。不含南华早报。

【第四部分：市场影响预测】
用表格形式展示预测：
<table style="width:100%; border-collapse:collapse; margin:15px 0;">
<tr style="background:#2c3e50; color:white;">
<th style="padding:10px; border:1px solid #ddd;">资产</th>
<th style="padding:10px; border:1px solid #ddd;">预测方向</th>
<th style="padding:10px; border:1px solid #ddd;">置信度</th>
<th style="padding:10px; border:1px solid #ddd;">理由</th>
</tr>
<tr><td style="padding:8px; border:1px solid #ddd;">美股科技股</td><td>...</td><td>...</td><td>...</td></tr>
</table>

预测数据用HTML注释隐藏：
<!-- PREDICTIONS_JSON_START {{"date":"YYYY-MM-DD","predictions":[...]}} PREDICTIONS_JSON_END -->

【第五部分：预测复盘】
如有历史数据则评估，否则写"暂无历史预测数据"。

【第六部分：其他新闻速览】
按地区分3列展示（每列最多8条）：
<div style="display:flex; gap:15px; flex-wrap:wrap;">
<div style="flex:1; min-width:250px; background:#f8f9fa; padding:12px; border-radius:6px; border-left:3px solid #3498db;">
<h4 style="margin:0 0 8px; color:#2c3e50; font-size:14px;">🇺🇸 美国</h4>
<ul style="margin:0; padding-left:16px; font-size:12px; line-height:1.6;">
<li><a href="链接" style="color:#3498db;">标题</a></li>
</ul>
</div>
<div style="flex:1; min-width:250px; background:#f8f9fa; padding:12px; border-radius:6px; border-left:3px solid #e74c3c;">
<h4 style="margin:0 0 8px; color:#2c3e50; font-size:14px;">🇪🇺 欧洲</h4>
...
</div>
<div style="flex:1; min-width:250px; background:#f8f9fa; padding:12px; border-radius:6px; border-left:3px solid #f39c12;">
<h4 style="margin:0 0 8px; color:#2c3e50; font-size:14px;">🌏 亚洲</h4>
...
</div>
</div>

样式：标题#2c3e50，链接#3498db，各部分用<hr style="border:1px solid #eee; margin:25px 0;">分隔。
"""

    return call_gemini_api(prompt)

def extract_predictions(html_content):
    """从 HTML 内容中提取预测 JSON（从注释中提取）"""
    try:
        # 匹配 HTML 注释中的 JSON
        pattern = r'<!-- PREDICTIONS_JSON_START\s*(.*?)\s*PREDICTIONS_JSON_END -->'
        match = re.search(pattern, html_content, re.DOTALL)
        
        if match:
            json_str = match.group(1).strip()
            return json.loads(json_str)
    except Exception as e:
        print(f"⚠️ 提取预测数据失败: {e}")
    return None

def clean_html_output(html_content):
    """清理 HTML 输出，移除不需要显示的内容"""
    # 移除 Markdown 代码块标记
    html_content = html_content.replace("```html", "").replace("```", "")
    
    # 移除可能暴露的 JSON 数据（作为备用清理）
    json_pattern = r'\{\s*"date"\s*:\s*"[^"]+"\s*,\s*"predictions"\s*:\s*\[.*?\]\s*\}'
    html_content = re.sub(json_pattern, '', html_content, flags=re.DOTALL)
    
    return html_content.strip()

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
    msg['Subject'] = Header(f"【全球新闻简报】{datetime.date.today()}", 'utf-8')

    full_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 900px; margin: auto; padding: 20px; background-color: #f9f9f9;">
        <div style="background-color: #2c3e50; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
            <h1 style="margin:0; font-size: 24px;">🌍 全球新闻简报</h1>
            <p style="margin:5px 0 0; font-size: 14px; opacity: 0.8;">{datetime.date.today()} | Global News Digest</p>
        </div>
        <div style="background-color: white; padding: 20px; border: 1px solid #ddd;">
            {content}
        </div>
        <div style="text-align: center; margin-top: 20px; color: #aaa; font-size: 12px;">
            Powered by Google Gemini & GitHub Actions<br>
            关键词追踪: China | Taiwan | Semiconductor
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
    # 1. 抓取新闻
    news_data = fetch_all_news()
    
    if not news_data:
        print("未抓取到新闻。")
        exit()
    
    # 2. 筛选关键词新闻（已排除南华早报）
    keyword_news = filter_keyword_news(news_data)
    print(f"🔍 找到 {len(keyword_news)} 条关键词相关新闻")
    
    # 3. 加载前一天的预测
    previous_predictions = load_previous_predictions()
    if previous_predictions:
        print(f"📊 已加载前一天的预测数据")
    
    # 4. 生成完整报告
    analysis_html = generate_full_report(news_data, keyword_news, previous_predictions)
    
    if analysis_html:
        # 5. 提取并保存今天的预测（在清理之前）
        today_predictions = extract_predictions(analysis_html)
        if today_predictions:
            save_predictions(today_predictions)
        
        # 6. 清理 HTML 输出
        clean_html = clean_html_output(analysis_html)
        
        # 7. 发送邮件
        send_email(clean_html)
    else:
        print("⚠️ 分析失败，跳过发送。")
