#!/usr/bin/env python3
"""
定时发布调度器
每天 12:00 CST 自动发布 3 章到飞书
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
    PUBLISH_DAILY_COUNT, PUBLISH_TIME,
    validate_config,
)
from src.pipeline import NovelPipeline

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("novel-scheduler")


class DailyPublisher:
    """每日定时发布器"""

    def __init__(self):
        self.pipeline = NovelPipeline(
            deepseek_api_key=DEEPSEEK_API_KEY,
            deepseek_base_url=DEEPSEEK_BASE_URL,
            deepseek_model=DEEPSEEK_MODEL,
            feishu_app_id=FEISHU_APP_ID,
            feishu_app_secret=FEISHU_APP_SECRET,
            data_dir=Path("data"),
        )
        self.published_log = Path("data/published_log.txt")
        self.published = self._load_published()

    def _load_published(self) -> set:
        """加载已发布章节记录"""
        if self.published_log.exists():
            with open(self.published_log, "r", encoding="utf-8") as f:
                return set(int(line.strip()) for line in f if line.strip().isdigit())
        return set()

    def _save_published(self, chapter_nums: list[int]):
        """保存已发布章节记录"""
        self.published_log.parent.mkdir(parents=True, exist_ok=True)
        with open(self.published_log, "a", encoding="utf-8") as f:
            for num in chapter_nums:
                f.write(f"{num}\n")
                self.published.add(num)

    def get_pending_chapters(self, count: int = 3) -> list[int]:
        """
        获取待发布的章节
        优先取已审核通过但未发布的章节，按章节号顺序
        """
        approved = self.pipeline.state.get_approved_chapters()
        pending = [ch for ch in approved if ch not in self.published]
        pending.sort()
        return pending[:count]

    def publish_chapters(self, chapter_nums: list[int]):
        """发布章节"""
        if not chapter_nums:
            logger.info("没有待发布的章节")
            return

        logger.info(f"发布章节: {chapter_nums}")

        try:
            results = self.pipeline.run_sync_to_feishu(chapter_nums)
            success = sum(1 for r in results if r.get("success"))
            logger.info(f"发布结果: {success}/{len(results)} 成功")

            if success > 0:
                self._save_published(chapter_nums)

                # 打印发布摘要
                for r in results:
                    if r.get("success") and r.get("url"):
                        logger.info(f"  第{r.get('chapter_num', '?')}章: {r['url']}")

        except Exception as e:
            logger.error(f"发布失败: {e}")

    def daily_publish(self):
        """每日发布任务"""
        logger.info("=" * 50)
        logger.info(f"开始每日发布 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")

        pending = self.get_pending_chapters(PUBLISH_DAILY_COUNT)

        if not pending:
            logger.info("没有待发布的章节（所有已审核章节均已发布）")
            logger.info("提示：运行 'python main.py run' 生成新章节")
        else:
            self.publish_chapters(pending)

        logger.info("每日发布完成")
        logger.info("=" * 50)

    def check_and_write_if_needed(self):
        """
        检查是否有足够的待发布章节，如果不够则自动触发写作
        """
        pending = self.get_pending_chapters(PUBLISH_DAILY_COUNT)

        if len(pending) < PUBLISH_DAILY_COUNT:
            logger.info(f"待发布章节不足 ({len(pending)} < {PUBLISH_DAILY_COUNT})，自动触发写作...")
            try:
                self.pipeline.run_full_cycle(
                    num_chapters=10,
                    min_words=2000,
                    max_words=3000,
                    auto_sync=True,
                )
            except Exception as e:
                logger.error(f"自动写作失败: {e}")


def run_scheduler():
    """启动调度器"""
    missing = validate_config()
    if missing:
        logger.error(f"缺少配置项: {', '.join(missing)}")
        sys.exit(1)

    publisher = DailyPublisher()

    # 解析发布时间
    hour, minute = PUBLISH_TIME.split(":")
    schedule_time = f"{int(hour):02d}:{int(minute):02d}"
    schedule.every().day.at(schedule_time).do(publisher.daily_publish)

    logger.info(f"定时发布调度器已启动")
    logger.info(f"  发布时间: 每天 {schedule_time} CST")
    logger.info(f"  每次发布: {PUBLISH_DAILY_COUNT} 章")

    # 启动时检查一次
    logger.info("启动检查...")
    stats = publisher.pipeline.state.get_stats()
    logger.info(f"  当前进度: {stats['total_chapters']} 章, {stats['total_words']} 字")
    logger.info(f"  已审核: {stats['approved_chapters']} 章")

    pending = publisher.get_pending_chapters(PUBLISH_DAILY_COUNT)
    logger.info(f"  待发布: {len(pending)} 章")

    # 定时检查：如果待发布章节不够明天的，自动触发写作
    schedule.every().day.at("00:00").do(publisher.check_and_write_if_needed)

    logger.info("等待定时任务触发...")

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)  # 每 30 秒检查一次
    except KeyboardInterrupt:
        logger.info("调度器已停止")


if __name__ == "__main__":
    run_scheduler()
