"""Имена файлов и папок пайплайна, общие функции работы с батчами."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

STRUCTURED_GLOB = "*structured.json"
FILTERING_SUFFIX = "_filtering_result.json"
FULL_FILTERED_BATCH = "full_filtered_batch.json"
BATCH_WITH_SCORES = "full_filtered_batch_with_scores.json"
MARKUP_RESULT = "control_set_lora_markup_part1.json"


@dataclass(frozen=True)
class Layout:
    """Входные данные — data_dir/<uuid>/; результаты этапа — output_dir/<stage>/<uuid>/."""

    data_dir: Path
    output_dir: Path

    def input_dir(self, source_uuid: str) -> Path:
        return self.data_dir / source_uuid

    def stage_dir(self, stage: str, source_uuid: Optional[str] = None) -> Path:
        path = self.output_dir / stage
        return path / source_uuid if source_uuid else path


def load_json(path: Path):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)


def get_question(batch_elem: dict) -> str:
    """Вопрос пользователя — предпоследнее сообщение диалога."""
    return batch_elem["messages"][-2]["content"]


def get_sources(batch_elem: dict) -> list:
    """Найденные источники лежат в последнем сообщении (ответе ассистента)."""
    return batch_elem["messages"][-1]["sources"]


def list_source_uuids(data_dir: Path, source_uuids: Optional[Iterable[str]] = None) -> list[str]:
    """UUID источников, у которых есть директория в data_dir; без source_uuids — все."""
    if source_uuids is None:
        return sorted(path.name for path in data_dir.iterdir() if path.is_dir())

    found = []
    for source_uuid in source_uuids:
        if (data_dir / source_uuid).is_dir():
            found.append(source_uuid)
        else:
            logger.warning("Директория источника не найдена: %s", data_dir / source_uuid)
    return found
