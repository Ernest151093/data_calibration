"""Полный пайплайн калибровки: filter -> merge -> markup -> rerank -> report.

Пути и хосты по умолчанию берутся из .env (см. README.md), аргументы их переопределяют.

Пример:
    python main.py --group ka
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from src import settings
from src.data import Layout, group_source_uuids, load_json
from src.filter_questions import load_filter_config, run_filter
from src.markup import run_markup
from src.merge import run_merge
from src.reports import run_reports
from src.reranker import RerankerClient, run_rerank

STAGES = ("filter", "merge", "markup", "rerank", "report")

logger = logging.getLogger("main")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, default=settings.DATA_DIR, help="директория с поддиректориями групп <group>/<source_uuid> (DATA_DIR)")
    parser.add_argument("--stages", nargs="+", choices=STAGES, default=list(STAGES), help="какие этапы запускать (по умолчанию все)")

    sources = parser.add_mutually_exclusive_group()
    sources.add_argument("--sources", nargs="+", metavar="UUID", help="UUID источников")
    sources.add_argument("--group", help="группа источников из SOURCES_CONFIG и поддиректория DATA_DIR (ka, sh)")

    parser.add_argument("--skill-url", default=settings.SKILL_URL, help="SKILL_URL")
    parser.add_argument("--filter-config", type=Path, default=settings.FILTER_CONFIG, help="FILTER_CONFIG")
    parser.add_argument("--filter-prompt", type=Path, default=settings.FILTER_PROMPT, help="FILTER_PROMPT")
    parser.add_argument("--filter-batch-size", type=int, default=50)
    parser.add_argument("--markup-config", type=Path, default=settings.MARKUP_CONFIG, help="MARKUP_CONFIG")

    parser.add_argument("--reranker-url", default=settings.RERANKER_URL, help="RERANKER_URL")
    parser.add_argument("--reranker-cert", type=Path, default=settings.RERANKER_CERT, help="клиентский сертификат (RERANKER_CERT)")
    parser.add_argument("--reranker-key", type=Path, default=settings.RERANKER_KEY, help="ключ сертификата (RERANKER_KEY)")
    parser.add_argument("--reranker-workers", type=int, default=7)

    parser.add_argument("--output-dir", type=Path, default=settings.OUTPUT_DIR, help="корень результатов, по папке на этап (OUTPUT_DIR)")
    parser.add_argument("--label", help="значение колонки source и суффикс имён отчётов (по умолчанию — имя группы)")
    parser.add_argument("--force", action="store_true", help="пересчитать этапы, даже если выходные файлы уже есть")
    return parser.parse_args()


def resolve_source_uuids(args: argparse.Namespace):
    if args.sources:
        return args.sources
    if args.group:
        groups = load_json(settings.SOURCES_CONFIG)
        if args.group not in groups:
            sys.exit(f"Группа {args.group!r} не найдена в {settings.SOURCES_CONFIG}: {', '.join(groups)}")
        return list(groups[args.group])
    return None


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    stages = [stage for stage in STAGES if stage in args.stages]
    if args.data_dir is None:
        sys.exit("Не задана директория с данными: DATA_DIR в .env или --data-dir")
    if "rerank" in stages and not (args.reranker_url and args.reranker_cert and args.reranker_key):
        sys.exit("Для этапа rerank нужны RERANKER_URL, RERANKER_CERT и RERANKER_KEY (в .env или аргументами)")

    groups = group_source_uuids(args.data_dir, resolve_source_uuids(args), args.group)
    logger.info(
        "Источников: %d (%s), этапы: %s",
        sum(map(len, groups.values())),
        ", ".join(f"{group}: {len(uuids)}" for group, uuids in groups.items()),
        ", ".join(stages),
    )

    for group, source_uuids in groups.items():
        layout = Layout(args.data_dir, args.output_dir, group)
        for stage in stages:
            logger.info("=== %s / %s ===", group, stage)
            if stage == "filter":
                cfg = load_filter_config(args.filter_config, args.filter_prompt)
                run_filter(source_uuids, layout, cfg, args.skill_url, batch_size=args.filter_batch_size, force=args.force)
            elif stage == "merge":
                run_merge(source_uuids, layout)
            elif stage == "markup":
                run_markup(source_uuids, layout, load_json(args.markup_config), args.skill_url, force=args.force)
            elif stage == "rerank":
                client = RerankerClient(args.reranker_url, args.reranker_cert, args.reranker_key)
                run_rerank(source_uuids, layout, client, max_workers=args.reranker_workers, force=args.force)
            elif stage == "report":
                run_reports(source_uuids, layout, args.skill_url, args.label or group)

if __name__ == "__main__":
    main()
