"""Имена файлов пайплайна и общие функции работы с батчами."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

STRUCTURED_GLOB = "*structured.json"
FILTERING_SUFFIX = "_filtering_result.json"
FULL_FILTERED_BATCH = "full_filtered_batch.json"
BATCH_WITH_SCORES = "full_filtered_batch_with_scores.json"
MARKUP_RESULT = "control_set_lora_markup_part1.json"


def load_json(path: Path):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def save_json(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def get_question(batch_elem: dict) -> str:
    """Вопрос пользователя — предпоследнее сообщение диалога."""
    return batch_elem["messages"][-2]["content"]


def get_sources(batch_elem: dict) -> list:
    """Найденные источники лежат в последнем сообщении (ответе ассистента)."""
    return batch_elem["messages"][-1]["sources"]


def iter_source_dirs(data_dir: Path, source_uuids: Optional[Iterable[str]] = None) -> list[Path]:
    """Директории источников внутри data_dir; при заданном source_uuids — только они."""
    if source_uuids is None:
        return sorted(path for path in data_dir.iterdir() if path.is_dir())

    source_dirs = []
    for source_uuid in source_uuids:
        path = data_dir / source_uuid
        if path.is_dir():
            source_dirs.append(path)
        else:
            logger.warning("Директория источника не найдена: %s", path)
    return source_dirs
