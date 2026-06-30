"""
AI 小说工厂 - 配置加载
复用 first-cc 项目的模式：模块级变量 + dotenv
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv(Path(__file__).parent / ".env")


def _env(key: str, default: str = "") -> str:
    """获取环境变量，去除首尾空白"""
    return os.getenv(key, default).strip()


# ━━━━ 飞书配置 ━━━━
FEISHU_APP_ID = _env("FEISHU_APP_ID")
FEISHU_APP_SECRET = _env("FEISHU_APP_SECRET")

# ━━━━ DeepSeek 配置 ━━━━
DEEPSEEK_API_KEY = _env("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = _env("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = _env("DEEPSEEK_MODEL", "deepseek-v4-pro")

# ━━━━ 小说配置 ━━━━
NOVEL_WIKI_TOKEN = _env("NOVEL_WIKI_TOKEN")
WRITE_BATCH_SIZE = int(_env("WRITE_BATCH_SIZE", "10"))
WRITE_MIN_WORDS = int(_env("WRITE_MIN_WORDS", "2000"))
WRITE_MAX_WORDS = int(_env("WRITE_MAX_WORDS", "3000"))
PUBLISH_DAILY_COUNT = int(_env("PUBLISH_DAILY_COUNT", "3"))
PUBLISH_TIME = _env("PUBLISH_TIME", "12:00")
FEISHU_BUFFER_SIZE = int(_env("FEISHU_BUFFER_SIZE", "10"))  # 飞书比番茄多保持的章数

# ━━━━ 路径配置 ━━━━
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CHAPTERS_DIR = DATA_DIR / "chapters"
STATE_FILE = DATA_DIR / "state.json"
PUBLISHED_LOG = DATA_DIR / "published_log.txt"
STYLE_PROFILE_FILE = DATA_DIR / "style_profile.json"
ORIGINAL_NOVEL_FILE = DATA_DIR / "original_novel.txt"

# ━━━━ 部署配置 ━━━━
DEPLOY_HOST = _env("DEPLOY_HOST")
DEPLOY_USER = _env("DEPLOY_USER")
DEPLOY_PASSWORD = _env("DEPLOY_PASSWORD")


def validate_config() -> list[str]:
    """验证必需配置，返回缺失项列表"""
    missing = []
    for key, val in [
        ("FEISHU_APP_ID", FEISHU_APP_ID),
        ("FEISHU_APP_SECRET", FEISHU_APP_SECRET),
        ("DEEPSEEK_API_KEY", DEEPSEEK_API_KEY),
        ("NOVEL_WIKI_TOKEN", NOVEL_WIKI_TOKEN),
    ]:
        if not val:
            missing.append(key)
    return missing


def print_config():
    """打印当前配置（隐藏敏感信息）"""
    print("当前配置：")
    print(f"  FEISHU_APP_ID:      {FEISHU_APP_ID[:8]}...{FEISHU_APP_ID[-4:] if len(FEISHU_APP_ID) > 12 else '***'}")
    print(f"  DEEPSEEK_MODEL:     {DEEPSEEK_MODEL}")
    print(f"  DEEPSEEK_BASE_URL:  {DEEPSEEK_BASE_URL}")
    print(f"  NOVEL_WIKI_TOKEN:   {NOVEL_WIKI_TOKEN[:8]}...")
    print(f"  WRITE_BATCH_SIZE:   {WRITE_BATCH_SIZE}")
    print(f"  WORDS_RANGE:        {WRITE_MIN_WORDS}-{WRITE_MAX_WORDS}")
    print(f"  PUBLISH_TIME:       {PUBLISH_TIME} ({PUBLISH_DAILY_COUNT}章/天)")
    print(f"  DEPLOY_HOST:        {DEPLOY_HOST}")
