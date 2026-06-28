# AI 小说工厂 (AI Novel Factory)

> 自动化长篇小说创作平台 — AI 作者仿写风格 + AI 编辑审核质量 + 飞书同步 + 定时发布

## 功能

- **AI 作者**：模仿已有小说风格，批量写作章节（2000-3000 字/章）
- **AI 编辑**：7 维质量审核（人物一致性、剧情连贯、伏笔管理、世界观、节奏、对话、文学质量）
- **飞书同步**：自动读取原小说 → 写新章节 → 同步回飞书 Wiki
- **定时发布**：每天中午 12:00 自动发布 3 章

## 架构

```
飞书 Wiki（原小说）
    ↓ 读取
AI 作者（DeepSeek v4 Pro）
    ↓ 写 10 章
AI 编辑（7 维审核）
    ↓ PASS
飞书同步（追加到 Wiki）
    ↓
定时发布（每天 12:00，3 章/天）
```

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置 .env（参考 .env.example）
cp .env.example .env

# 3. 初始化（从飞书 Wiki 导入原小说）
python main.py init --wiki-token YOUR_WIKI_TOKEN

# 4. 运行完整流程（写 10 章 + 审核 + 同步）
python main.py run

# 5. 启动定时发布
python main.py schedule
```

## CLI 命令

| 命令 | 说明 |
|------|------|
| `python main.py init` | 从飞书 Wiki 初始化项目 |
| `python main.py run` | 运行完整流程（写→审→同步） |
| `python main.py write --chapters 10` | 仅写章节 |
| `python main.py review --chapters 11,12` | 审核指定章节 |
| `python main.py sync --chapters 11,12` | 同步到飞书 |
| `python main.py schedule` | 启动定时发布调度器 |
| `python main.py status` | 查看小说状态 |

## 环境变量

| 变量 | 说明 |
|------|------|
| `FEISHU_APP_ID` | 飞书应用 ID |
| `FEISHU_APP_SECRET` | 飞书应用密钥 |
| `DEEPSEEK_API_KEY` | DeepSeek API Key |
| `DEEPSEEK_MODEL` | 模型 ID（默认 `deepseek-v4-pro`） |
| `NOVEL_WIKI_TOKEN` | 飞书 Wiki Token（从 URL 获取） |
| `WRITE_BATCH_SIZE` | 每批写作章数（默认 10） |
| `PUBLISH_TIME` | 每日发布时间（默认 12:00） |

## 飞书应用权限

需要以下 API 权限：
- `docx:document` / `docx:document:create` — 创建/读写文档
- `wiki:node:read` — 读取 Wiki 节点
- `docx:document:readonly` — 读取文档内容

## 成本

DeepSeek v4 Pro 促销价，每章约 2000-3000 字：

| 操作 | 成本 |
|------|------|
| 写 10 章 | ~$0.05 |
| 审核 10 章 | ~$0.03 |
| **完整 10 章流程** | **~$0.08** |
| 100 章 | ~$0.80 |

## 部署

```bash
# Docker
docker compose up -d

# 或 systemd（推荐）
sudo cp novel-factory.service /etc/systemd/system/
sudo systemctl enable --now novel-factory
```

## License

MIT
