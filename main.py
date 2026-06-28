#!/usr/bin/env python3
"""
AI 小说工厂 - CLI 入口
用法：
  python main.py init                          # 从飞书 Wiki 初始化
  python main.py init --file novel.txt         # 从本地文件初始化
  python main.py run                           # 运行完整流程（写10章+审核+同步）
  python main.py write --chapters 10           # 仅写章节
  python main.py review --batch 1              # 审核指定批次
  python main.py sync --chapters 11,12,13      # 同步到飞书
  python main.py schedule                      # 启动定时发布
  python main.py status                        # 查看状态
"""
import sys
import argparse
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    FEISHU_APP_ID, FEISHU_APP_SECRET,
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    NOVEL_WIKI_TOKEN,
    WRITE_BATCH_SIZE, WRITE_MIN_WORDS, WRITE_MAX_WORDS,
    validate_config, print_config,
)
from src.pipeline import NovelPipeline


def create_pipeline() -> NovelPipeline:
    """创建流水线实例"""
    return NovelPipeline(
        deepseek_api_key=DEEPSEEK_API_KEY,
        deepseek_base_url=DEEPSEEK_BASE_URL,
        deepseek_model=DEEPSEEK_MODEL,
        feishu_app_id=FEISHU_APP_ID,
        feishu_app_secret=FEISHU_APP_SECRET,
        data_dir=Path("data"),
    )


def cmd_init(args):
    """初始化项目"""
    pipeline = create_pipeline()

    if args.file:
        # 从本地文件初始化
        filepath = Path(args.file)
        if not filepath.exists():
            print(f"错误：文件不存在 {filepath}")
            sys.exit(1)
        pipeline.init_from_file(
            title=args.title or filepath.stem,
            filepath=filepath,
            genre=args.genre or "",
        )
    else:
        # 从飞书 Wiki 初始化
        wiki_token = args.wiki_token or NOVEL_WIKI_TOKEN
        if not wiki_token:
            print("错误：请提供 --wiki-token 或在 .env 中设置 NOVEL_WIKI_TOKEN")
            sys.exit(1)
        try:
            pipeline.init_from_wiki(wiki_token)
        except RuntimeError as e:
            print(f"初始化失败: {e}")
            sys.exit(1)

    # 显示统计
    pipeline.print_status()


def cmd_run(args):
    """运行完整流程"""
    pipeline = create_pipeline()

    # 检查是否已初始化
    stats = pipeline.state.get_stats()
    if stats["total_chapters"] == 0:
        print("错误：项目未初始化，请先运行 'python main.py init'")
        sys.exit(1)

    pipeline.run_full_cycle(
        num_chapters=args.chapters or WRITE_BATCH_SIZE,
        min_words=args.min_words or WRITE_MIN_WORDS,
        max_words=args.max_words or WRITE_MAX_WORDS,
        auto_sync=not args.no_sync,
        max_revise_rounds=args.max_revise,
    )


def cmd_write(args):
    """仅写章节"""
    pipeline = create_pipeline()

    if pipeline.state.get_stats()["total_chapters"] == 0:
        print("错误：项目未初始化")
        sys.exit(1)

    chapters = pipeline.run_write_batch(
        num_chapters=args.chapters or WRITE_BATCH_SIZE,
        min_words=args.min_words or WRITE_MIN_WORDS,
        max_words=args.max_words or WRITE_MAX_WORDS,
    )

    print(f"\n写作完成！生成 {len(chapters)} 章")


def cmd_review(args):
    """审核章节"""
    pipeline = create_pipeline()

    # 读取指定章节
    if args.chapters:
        ch_nums = [int(c.strip()) for c in args.chapters.split(",")]
    else:
        # 读取最新 batch
        batches = pipeline.state.data.get("batches", [])
        if not batches:
            print("错误：没有可审核的批次")
            sys.exit(1)
        ch_nums = batches[-1]["chapters"]

    chapters = []
    for ch_num in ch_nums:
        filepath = pipeline.chapters_dir / f"chapter_{ch_num:04d}.txt"
        if filepath.exists():
            chapters.append({
                "chapter_number": ch_num,
                "content": filepath.read_text(encoding="utf-8"),
            })

    if not chapters:
        print("错误：未找到章节文件")
        sys.exit(1)

    result = pipeline.run_review_batch(chapters)
    print(f"\n审核结果: {result['batch_verdict']} ({result['batch_score']}/10)")


def cmd_sync(args):
    """同步到飞书"""
    pipeline = create_pipeline()

    if args.chapters:
        ch_nums = [int(c.strip()) for c in args.chapters.split(",")]
    else:
        # 同步所有已审核未同步的章节
        ch_nums = pipeline.state.get_approved_chapters()
        if not ch_nums:
            print("没有待同步的章节")
            return

    results = pipeline.run_sync_to_feishu(ch_nums)
    success = sum(1 for r in results if r.get("success"))
    print(f"同步完成: {success}/{len(results)} 成功")


def cmd_status(args):
    """查看状态"""
    pipeline = create_pipeline()
    print_config()
    pipeline.print_status()


def cmd_schedule(args):
    """启动定时发布调度器"""
    from scheduler import run_scheduler
    run_scheduler()


def main():
    parser = argparse.ArgumentParser(
        description="AI 小说工厂 - 自动化小说写作与发布系统",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # init
    p_init = subparsers.add_parser("init", help="初始化项目")
    p_init.add_argument("--wiki-token", help="飞书 Wiki Token")
    p_init.add_argument("--file", help="从本地文件初始化")
    p_init.add_argument("--title", help="小说标题")
    p_init.add_argument("--genre", help="小说类型")

    # run
    p_run = subparsers.add_parser("run", help="运行完整流程")
    p_run.add_argument("--chapters", type=int, help="每批章节数")
    p_run.add_argument("--min-words", type=int, help="每章最少字数")
    p_run.add_argument("--max-words", type=int, help="每章最多字数")
    p_run.add_argument("--no-sync", action="store_true", help="不同步到飞书")
    p_run.add_argument("--max-revise", type=int, default=3, help="最大修改轮数")

    # write
    p_write = subparsers.add_parser("write", help="仅写章节")
    p_write.add_argument("--chapters", type=int, help="写作章节数")
    p_write.add_argument("--min-words", type=int, help="每章最少字数")
    p_write.add_argument("--max-words", type=int, help="每章最多字数")

    # review
    p_review = subparsers.add_parser("review", help="审核章节")
    p_review.add_argument("--chapters", help="章节号，逗号分隔，如 '11,12,13'")
    p_review.add_argument("--batch", type=int, help="审核指定批次")

    # sync
    p_sync = subparsers.add_parser("sync", help="同步到飞书")
    p_sync.add_argument("--chapters", help="章节号，逗号分隔")

    # schedule
    subparsers.add_parser("schedule", help="启动定时发布调度器")

    # status
    subparsers.add_parser("status", help="查看小说状态")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # 验证配置
    missing = validate_config()
    if missing:
        print(f"警告：缺少以下配置项: {', '.join(missing)}")
        if args.command in ("init", "run", "sync"):
            print("这些命令需要完整的飞书和 API 配置，请检查 .env 文件")
            sys.exit(1)

    # 执行命令
    commands = {
        "init": cmd_init,
        "run": cmd_run,
        "write": cmd_write,
        "review": cmd_review,
        "sync": cmd_sync,
        "status": cmd_status,
        "schedule": cmd_schedule,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)


if __name__ == "__main__":
    main()
