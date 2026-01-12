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

# 关键词追踪列表
TRACKED_KEYWORDS = ['China', 'Taiwan', 'semiconductor', 'chip', 'TSMC', 'Nvidia']

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
    """筛选包含关键词的新闻"""
    keyword_news = []
    for news in news_data:
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

        priority_keywords = [
            'gemini-1.5-flash',
            'gemini-1.5-pro',
            'gemini-2.0-flash',
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
    """通用的 Gemini API 调用函数"""
    if not GEMINI_API_KEY:
        print("❌ 错误: 没找到 GEMINI_API_KEY")
        return None
    
    available_models = get_available_models(GEMINI_API_KEY)
    base_url = "https://generativelanguage.googleapis.com/v1beta"
    headers = {'Content-Type': 'application/json'}
    body = {
        "contents": [{
            "parts": [{"text": prompt}]
        }]
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
    
    # 准备数据
    data_payload = json.dumps(news_data[:150], ensure_ascii=False)
    keyword_payload = json.dumps(keyword_news[:50], ensure_ascii=False)
    
    # 准备前一天预测复盘内容
    prediction_review = ""
    if previous_predictions:
        prediction_review = f"""
    ### 前一天预测复盘数据：
    {json.dumps(previous_predictions, ensure_ascii=False)}
    
    请在报告中增加"预测复盘"部分，评估前一天的市场预测是否准确，分析预测偏差的原因。
    """

    prompt = f"""
    你是一名资深的国际媒体分析师和金融市场专家。以下是过去24小时的全球新闻数据。
    
    === 全部新闻数据 ===
    {data_payload}
    
    === 关键词追踪新闻（China/Taiwan/Semiconductor相关）===
    {keyword_payload}
    
    {prediction_review}

    请生成一份专业的 HTML 简报（直接输出HTML，不要Markdown，不要 ```html 包裹）：

    ---
    ## 第一部分：跨区域舆情对比 (Media Focus Analysis)
    深度分析"美国"、"欧洲"和"亚洲"媒体的关注点差异。用 300 字左右的中文进行深度点评。

    ---
    ## 第二部分：全球核心议题聚合 (Top Stories)
    找出全球媒体共同关注的 5-8 个核心大事件。
    - 使用 <h3 style="color:#2c3e50; margin-top:20px;">中文主标题</h3>
    - <p style="font-size:14px;">中英文摘要（100字）</p>
    - <ul style="font-size:12px; color:#666;"><li><a href="链接">[媒体名] 英文原标题</a></li></ul>

    ---
    ## 第三部分：🔥 China/Taiwan/Semiconductor 专题追踪
    专门分析关于中国、台湾、半导体相关的新闻动态：
    - 列出所有相关新闻的标题和链接
    - 分析这些新闻反映的地缘政治趋势
    - 评估对半导体产业链的潜在影响

    ---
    ## 第四部分：📈 市场影响预测 (Market Impact Forecast)
    基于今日重大地缘政治新闻，预测可能的市场变动：
    - 对美股（特别是科技股、半导体股）的影响
    - 对亚太市场的影响
    - 对汇率（美元、人民币、日元）的影响
    - 对大宗商品（石油、黄金）的影响
    - 给出具体的预测方向（上涨/下跌/震荡）和置信度（高/中/低）
    
    **重要**：请在预测部分末尾，用以下JSON格式总结你的预测（用 <!-- PREDICTIONS_JSON_START --> 和 <!-- PREDICTIONS_JSON_END --> 包裹）：
    <!-- PREDICTIONS_JSON_START -->
    {{
        "date": "YYYY-MM-DD",
        "predictions": [
            {{"asset": "资产名称", "direction": "上涨/下跌/震荡", "confidence": "高/中/低", "reason": "简要原因"}}
        ]
    }}
    <!-- PREDICTIONS_JSON_END -->

    ---
    ## 第五部分：预测复盘 (Prediction Review)
    如果有前一天的预测数据，请评估预测准确性；如果没有，请写"暂无历史预测数据可供复盘"。

    ---
    ## 第六部分：📰 其他新闻速览 (Other Headlines)
    将未在核心议题中提及的其他新闻，按地区分类列出标题和链接（每个地区最多10条）。
    格式：
    <h4>🇺🇸 美国媒体</h4>
    <ul style="font-size:12px;"><li><a href="链接">[媒体名] 标题</a></li></ul>
    
    <h4>🇪🇺 欧洲媒体</h4>
    ...
    
    <h4>🌏 亚洲媒体</h4>
    ...

    ---
    **样式要求**：
    - 使用内联CSS
    - 标题深蓝色 (#2c3e50)，正文 (#333)
    - 链接蓝色 (#3498db)，hover时有下划线
    - 各部分之间用 <hr style="border:1px solid #eee; margin:30px 0;"> 分隔
    - 预测部分用醒目的背景色 (#fff3cd) 突出显示
    """

    return call_gemini_api(prompt)

def extract_predictions(html_content):
    """从 HTML 内容中提取预测 JSON"""
    try:
        start_marker = "<!-- PREDICTIONS_JSON_START -->"
        end_marker = "<!-- PREDICTIONS_JSON_END -->"
        
        if start_marker in html_content and end_marker in html_content:
            start_idx = html_content.index(start_marker) + len(start_marker)
            end_idx = html_content.index(end_marker)
            json_str = html_content[start_idx:end_idx].strip()
            return json.loads(json_str)
    except Exception as e:
        print(f"⚠️ 提取预测数据失败: {e}")
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
    msg['Subject'] = Header(f"【深度舆情】{datetime.date.today()} 全球媒体关注点分析 + 市场预测", 'utf-8')

    full_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 900px; margin: auto; padding: 20px; background-color: #f9f9f9;">
        <div style="background-color: #2c3e50; color: white; padding: 20px; border-radius: 8px 8px 0 0;">
            <h1 style="margin:0; font-size: 24px;">🌍 Global Media Monitor Pro</h1>
            <p style="margin:5px 0 0; font-size: 14px; opacity: 0.8;">{datetime.date.today()} | US · Europe · Asia Analysis | Market Forecast</p>
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
    
    # 2. 筛选关键词新闻
    keyword_news = filter_keyword_news(news_data)
    print(f"🔍 找到 {len(keyword_news)} 条关键词相关新闻")
    
    # 3. 加载前一天的预测
    previous_predictions = load_previous_predictions()
    if previous_predictions:
        print(f"📊 已加载前一天的预测数据")
    
    # 4. 生成完整报告
    analysis_html = generate_full_report(news_data, keyword_news, previous_predictions)
    
    if analysis_html:
        # 清洗 Markdown 标记
        clean_html = analysis_html.replace("```html", "").replace("```", "").strip()
        
        # 5. 提取并保存今天的预测
        today_predictions = extract_predictions(clean_html)
        if today_predictions:
            save_predictions(today_predictions)
        
        # 6. 发送邮件
        send_email(clean_html)
    else:
        print("⚠️ 分析失败，跳过发送。")
