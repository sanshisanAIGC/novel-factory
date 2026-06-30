#!/usr/bin/env python3
"""
定时调度器 — 番茄驱动模型
- 飞书始终保持比番茄多 10 章（缓冲池）
- 每天 00:00 检查：番茄前进了多少 → 补写多少 → 推飞书
- 每天 12:00 推送状态报告
"""
import sys
import time
import logging
from pathlib import Path
from datetime import datetime

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent))

import schedule
from config import (
    FEISHU_APP_ID, FEISHU_APP_SECRET,
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    FEISHU_BUFFER_SIZE,
    validate_config,
)
from src.pipeline import NovelPipeline

import json as json_mod
import httpx

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("novel-scheduler")


def notify(text: str):
    """发送飞书通知"""
    try:
        resp = httpx.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}, timeout=10)
        token = resp.json()["tenant_access_token"]
        import os
        open_id = os.getenv("FEISHU_NOTIFY_OPEN_ID", "")
        if not open_id:
            return
        httpx.post(
            "https://open.feishu.cn/open-apis/im/v1/messages",
            params={"receive_id_type": "open_id"},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"receive_id": open_id, "msg_type": "text",
                  "content": json_mod.dumps({"text": text})}, timeout=10)
    except Exception as e:
        logger.warning(f"通知失败: {e}")


class BufferManager:
    """
    番茄驱动缓冲管理器

    模型：
    ┌──────────┐     ┌──────────┐     ┌──────────┐
    │ 番茄小说  │ ←→  │ 系统检测  │ ←→  │ 飞书文档  │
    │ (已发N章) │     │ 缓冲<10?  │     │ (N+10章)  │
    └──────────┘     └──────────┘     └──────────┘
    """

    def __init__(self):
        self.pipeline = NovelPipeline(
            deepseek_api_key=DEEPSEEK_API_KEY,
            deepseek_base_url=DEEPSEEK_BASE_URL,
            deepseek_model=DEEPSEEK_MODEL,
            feishu_app_id=FEISHU_APP_ID,
            feishu_app_secret=FEISHU_APP_SECRET,
            data_dir=Path("data"),
        )

    def sync_platform_progress(self) -> int:
        """
        抓取番茄小说页面，获取最新章节数，更新 published_on_platform。
        返回: 番茄最新章数（抓取失败返回 0）
        """
        import re
        try:
            import httpx
            resp = httpx.get(
                "https://fanqienovel.com/page/7649339734027668505",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                timeout=15,
            )
            m = re.search(r'"chapterTotal":(\d+)', resp.text)
            if m:
                tomato_chapters = int(m.group(1))
                local = self.pipeline.state.get("novel.published_on_platform", 0)
                if tomato_chapters > local:
                    logger.info(f"检测到番茄更新: {local} → {tomato_chapters} (+{tomato_chapters - local}章)")
                    self.pipeline.set_platform_published(tomato_chapters)
                    # 同时更新 current_chapter（番茄上已有的，本地视为已存在）
                    cur = self.pipeline.state.get("novel.current_chapter", 0)
                    if tomato_chapters > cur:
                        self.pipeline.state.set("novel.current_chapter", tomato_chapters)
                        self.pipeline.state.save()
                        logger.info(f"同步 current_chapter: {cur} → {tomato_chapters}")
                return tomato_chapters
            else:
                logger.warning(f"未在页面中找到 chapterTotal")
                return 0
        except Exception as e:
            logger.warning(f"抓取番茄章节数失败: {e}")
            return 0

    def get_buffer_status(self) -> dict:
        """获取当前缓冲状态"""
        platform_pub = self.pipeline.state.get("novel.published_on_platform", 0)
        feishu_synced = self.pipeline.state.get("novel.last_synced_feishu_chapter", 0)
        current_ch = self.pipeline.state.get("novel.current_chapter", 0)

        buffer = feishu_synced - platform_pub
        shortage = max(0, FEISHU_BUFFER_SIZE - buffer)

        return {
            "platform_pub": platform_pub,
            "feishu_synced": feishu_synced,
            "current_ch": current_ch,
            "buffer": buffer,
            "target_buffer": FEISHU_BUFFER_SIZE,
            "shortage": shortage,
        }

    def replenish_buffer(self) -> dict:
        """
        检查并补充缓冲：如果飞书缓冲不足 10 章，写新章并推飞书

        返回: {action, chapters_written, synced, ...}
        """
        status = self.get_buffer_status()
        shortage = status["shortage"]
        current_ch = status["current_ch"]

        if shortage == 0:
            logger.info(f"缓冲充足: 番茄={status['platform_pub']}, "
                        f"飞书={status['feishu_synced']}, "
                        f"缓冲={status['buffer']}章")
            return {"action": "skip", "reason": "buffer_full", "status": status}

        logger.info(f"缓冲不足: 番茄={status['platform_pub']}, "
                    f"飞书={status['feishu_synced']}, "
                    f"缓冲={status['buffer']}章, "
                    f"需补 {shortage} 章")

        # 写新章并同步
        try:
            result = self.pipeline.run_full_cycle(
                num_chapters=shortage,
                min_words=2000,
                max_words=3000,
                auto_sync=True,       # 直接推到飞书
                max_revise_rounds=3,
            )
            notify(f"[小说工厂] 番茄前进{shortage}章 → 已补写{shortage}章并推送飞书")
            return {
                "action": "replenished",
                "chapters_written": shortage,
                "result": result,
                "status": self.get_buffer_status(),
            }
        except Exception as e:
            logger.error(f"补写失败: {e}")
            notify(f"[小说工厂] 补写失败: {e}")
            return {"action": "error", "error": str(e)}

    def daily_check(self):
        """每日检查（00:00 触发）：抓番茄 → 更新状态 → 补充缓冲"""
        logger.info("=" * 50)
        logger.info(f"每日缓冲检查 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

        # Step 1: 抓番茄最新章节数
        tomato_ch = self.sync_platform_progress()
        if tomato_ch:
            logger.info(f"  番茄最新: 第{tomato_ch}章")

        # Step 2: 检查缓冲
        status = self.get_buffer_status()
        logger.info(f"  飞书已同步: 第{status['feishu_synced']}章")
        logger.info(f"  缓冲: {status['buffer']}/{status['target_buffer']}章")
        logger.info(f"  总进度: 第{status['current_ch']}章")

        # Step 3: 补写
        if status["shortage"] > 0:
            result = self.replenish_buffer()
            if result.get("action") == "replenished":
                new_status = result["status"]
                logger.info(f"  补充完成 → 飞书={new_status['feishu_synced']}, "
                            f"缓冲={new_status['buffer']}章")
        else:
            logger.info("  缓冲充足，跳过")

        logger.info("=" * 50)

    def status_report(self):
        """每日状态报告（12:00 触发）"""
        logger.info("=" * 50)
        logger.info(f"状态报告 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

        status = self.get_buffer_status()
        stats = self.pipeline.state.get_stats()

        logger.info(f"  总章节: {stats['total_chapters']}章, {stats['total_words']}字")
        logger.info(f"  番茄已发: 第{status['platform_pub']}章")
        logger.info(f"  飞书缓冲: 第{status['feishu_synced']}章")
        logger.info(f"  缓冲余量: {status['buffer']}/{status['target_buffer']}章")

        if status["shortage"] > 0:
            logger.info(f"  ⚠ 缓冲不足 {status['shortage']} 章，将在 00:00 自动补写")
        else:
            logger.info(f"  ✓ 缓冲充足")

        notify(
            f"[小说工厂] 日报\n"
            f"番茄: {status['platform_pub']}章 | "
            f"飞书: {status['feishu_synced']}章 | "
            f"缓冲: {status['buffer']}章 | "
            f"总字数: {stats['total_words']:,}"
        )
        logger.info("=" * 50)


def run_scheduler():
    """启动调度器"""
    missing = validate_config()
    if missing:
        logger.error(f"缺少配置项: {', '.join(missing)}")
        sys.exit(1)

    manager = BufferManager()

    # 00:00 — 检查缓冲，必要时补写
    schedule.every().day.at("00:00").do(manager.daily_check)

    # 12:00 — 状态报告
    schedule.every().day.at("12:00").do(manager.status_report)

    logger.info(f"小说工厂调度器已启动")
    logger.info(f"  模型: 番茄驱动 + 飞书 {FEISHU_BUFFER_SIZE} 章缓冲")
    logger.info(f"  00:00 — 检查缓冲 → 补写 → 推飞书")
    logger.info(f"  12:00 — 状态日报")

    # 启动时状态
    status = manager.get_buffer_status()
    stats = manager.pipeline.state.get_stats()
    logger.info(f"  当前: 番茄{status['platform_pub']}章 | "
                f"飞书{status['feishu_synced']}章 | "
                f"缓冲{status['buffer']}章 | "
                f"总{stats['total_chapters']}章")

    # 启动时立即检查一次
    if status["shortage"] > 0:
        logger.info(f"  启动时检测到缓冲不足 {status['shortage']} 章，立即补充...")
        manager.replenish_buffer()

    logger.info("等待定时任务触发...")

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        logger.info("调度器已停止")


if __name__ == "__main__":
    run_scheduler()
