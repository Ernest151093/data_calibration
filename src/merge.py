"""Этап 2 (merge_filtered_reports): сборка rag-вопросов в full_filtered_batch.json."""
from __future__ import annotations

import logging
from pathlib import Path

from src.data import FILTERING_SUFFIX, FULL_FILTERED_BATCH, get_question, load_json, save_json

logger = logging.getLogger(__name__)


def merge_source(source_dir: Path) -> None:
    united_batch = None

    for res_path in sorted(source_dir.glob("*" + FILTERING_SUFFIX)):
        original_batch_path = res_path.with_name(res_path.name.removesuffix(FILTERING_SUFFIX) + ".json")

        rag_set = set(load_json(res_path)["rag"])
        original_batch = load_json(original_batch_path)

        filtered_items = [el for el in original_batch["request"]["batch"] if get_question(el) in rag_set]

        if united_batch is None:
            united_batch = original_batch
            united_batch["request"]["batch"] = filtered_items
        else:
            united_batch["request"]["batch"].extend(filtered_items)

    if united_batch is None:
        logger.warning("Нет результатов фильтрации в %s", source_dir)
        return
    save_json(source_dir / FULL_FILTERED_BATCH, united_batch)


def run_merge(source_dirs: list[Path]) -> None:
    for source_dir in source_dirs:
        merge_source(source_dir)
