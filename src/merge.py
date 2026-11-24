"""Этап 2 (merge_filtered_reports): сборка rag-вопросов в full_filtered_batch.json."""
from __future__ import annotations

import logging

from src import filter_questions
from src.data import FILTERING_SUFFIX, FULL_FILTERED_BATCH, Layout, get_question, load_json, save_json

logger = logging.getLogger(__name__)

STAGE = "merge"


def merge_source(source_uuid: str, layout: Layout) -> None:
    united_batch = None
    filter_dir = layout.stage_dir(filter_questions.STAGE, source_uuid)

    for res_path in sorted(filter_dir.glob("*" + FILTERING_SUFFIX)):
        original_batch_path = layout.input_dir(source_uuid) / (res_path.name.removesuffix(FILTERING_SUFFIX) + ".json")

        rag_set = set(load_json(res_path)["rag"])
        original_batch = load_json(original_batch_path)

        filtered_items = [el for el in original_batch["request"]["batch"] if get_question(el) in rag_set]

        if united_batch is None:
            united_batch = original_batch
            united_batch["request"]["batch"] = filtered_items
        else:
            united_batch["request"]["batch"].extend(filtered_items)

    if united_batch is None:
        logger.warning("Нет результатов фильтрации в %s", filter_dir)
        return
    save_json(layout.stage_dir(STAGE, source_uuid) / FULL_FILTERED_BATCH, united_batch)


def run_merge(source_uuids: list[str], layout: Layout) -> None:
    for source_uuid in source_uuids:
        merge_source(source_uuid, layout)
