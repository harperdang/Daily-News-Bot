# 📰 Daily News Bot

全球新闻简报系统，每日自动抓取美国、欧洲、亚洲主流媒体的新闻，通过 AI 生成分析简报并发送邮件。

## 功能特点

- **多区域覆盖**：追踪美国、欧洲、亚洲 15+ 家主流媒体
- **24小时新闻**：自动筛选过去24小时内的新闻
- **AI 智能分析**：使用 Google Gemini 生成深度分析
- **关键词追踪**：专题追踪 China、Taiwan、Semiconductor 相关新闻
- **市场预测**：基于地缘政治新闻预测市场走势
- **预测复盘**：次日自动复盘前一天的预测准确性

## 追踪的媒体

### 美国媒体
| 媒体 | 类型 |
|------|------|
| The New York Times | 综合新闻 |
| The Wall Street Journal | 财经新闻 |
| The Washington Post | 政治新闻 |
| Bloomberg | 财经/政治 |
| Politico | 政治新闻 |
| Reuters | 通讯社 |

### 欧洲媒体
| 媒体 | 类型 |
|------|------|
| The Guardian | 综合新闻 |
| Financial Times | 财经新闻 |

### 亚洲媒体
| 媒体 | 类型 |
|------|------|
| Nikkei Asia | 亚洲财经 |
| The Straits Times | 东南亚新闻 |
| South China Morning Post | 中国/香港新闻 |
| Hong Kong Free Press | 香港新闻 |
| The Japan Times | 日本新闻 |
| The Korea Times | 韩国新闻 |
| Taipei Times | 台湾新闻 |

## 简报内容

每日简报包含以下部分：

1. **跨区域舆情对比** - 分析美国、欧洲、亚洲媒体关注点差异
2. **全球核心议题聚合** - 5-8个核心大事件，含中英文摘要和原文链接
3. **China/Taiwan/Semiconductor 专题** - 关键词相关新闻追踪和地缘政治分析
4. **市场影响预测** - 预测美股、亚太市场、汇率、大宗商品走势
5. **预测复盘** - 评估前一天预测的准确性（需配置 Gist）
6. **其他新闻速览** - 按地区分类的其他新闻标题和链接

## 配置说明

### 1. Fork 本仓库

### 2. 配置 Secrets

在仓库 Settings → Secrets and variables → Actions 中添加：

| Secret | 必需 | 说明 |
|--------|------|------|
| `GEMINI_API_KEY` | ✅ | Google Gemini API 密钥 |
| `MAIL_USERNAME` | ✅ | 发件邮箱地址 |
| `MAIL_PASSWORD` | ✅ | 邮箱授权码（非登录密码） |
| `MAIL_RECEIVER` | ✅ | 收件人邮箱（多个用逗号分隔） |
| `GIST_TOKEN` | ❌ | GitHub Token（用于预测复盘） |
| `GIST_ID` | ❌ | Gist ID（用于存储预测数据） |

### 3. 获取 Gemini API Key

1. 访问 [Google AI Studio](https://aistudio.google.com/)
2. 点击 "Get API Key"
3. 创建新的 API Key
4. （可选）在 Google Cloud Console 设置 Billing 以获得更高配额

### 4. 邮箱授权码获取

| 邮箱 | 获取方法 |
|------|----------|
| Gmail | Google 账号 → 安全性 → 两步验证 → 应用专用密码 |
| QQ邮箱 | 设置 → 账户 → POP3/SMTP服务 → 开启 → 生成授权码 |
| 163邮箱 | 设置 → POP3/SMTP/IMAP → 开启 → 生成授权码 |

### 5. 配置预测复盘功能（可选）

如需启用预测复盘功能：

1. 创建 GitHub Gist：https://gist.github.com/
   - 文件名：`predictions.json`
   - 内容：`{}`
2. 创建 GitHub Token：https://github.com/settings/tokens
   - 勾选 `gist` 权限
3. 在仓库 Secrets 中添加 `GIST_TOKEN` 和 `GIST_ID`

## 运行频率

- **默认**：每天北京时间早上 8:00 自动运行
- **手动触发**：Actions → Daily News Scraper → Run workflow

## 自定义配置

### 修改关键词追踪

编辑 `main.py` 中的 `TRACKED_KEYWORDS`：

```python
TRACKED_KEYWORDS = ['China', 'Taiwan', 'semiconductor', 'chip', 'TSMC', 'Nvidia']
```

### 添加/移除媒体源

编辑 `main.py` 中的 `MEDIA_SOURCES` 字典，添加 RSS 源：

```python
{"name": "媒体名称", "url": "RSS链接"}
```

### 修改运行时间

编辑 `.github/workflows/daily.yml` 中的 cron 表达式：

```yaml
schedule:
  - cron: '0 0 * * *'  # UTC 时间，北京时间 +8
```

## 技术栈

- Python 3.11
- Feedparser (RSS 解析)
- Google Gemini API (AI 分析)
- GitHub Actions (定时任务)
- GitHub Gist (数据存储)

## License

MIT
