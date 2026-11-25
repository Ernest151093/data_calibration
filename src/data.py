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
    """Входные данные — data_dir/<group>/<uuid>/; результаты этапа — output_dir/<stage>/<group>/<uuid>/."""

    data_dir: Path
    output_dir: Path
    group: str

    def input_dir(self, source_uuid: str) -> Path:
        return self.data_dir / self.group / source_uuid

    def stage_dir(self, stage: str, source_uuid: Optional[str] = None) -> Path:
        path = self.output_dir / stage / self.group
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


def list_groups(data_dir: Path) -> list[str]:
    """Группы источников — поддиректории data_dir (ka, sh, ...)."""
    return sorted(path.name for path in data_dir.iterdir() if path.is_dir())


def group_source_uuids(
    data_dir: Path,
    source_uuids: Optional[Iterable[str]] = None,
    group: Optional[str] = None,
) -> dict[str, list[str]]:
    """Раскладывает источники по группам: {группа: [uuid, ...]}.

    Источник ищется в data_dir/<группа>/<uuid>; с group — только в этой группе.
    Без source_uuids берутся все источники групп.
    """
    groups = [group] if group else list_groups(data_dir)
    for name in groups:
        if not (data_dir / name).is_dir():
            logger.warning("Директория группы не найдена: %s", data_dir / name)
    groups = [name for name in groups if (data_dir / name).is_dir()]

    if source_uuids is None:
        result = {name: sorted(p.name for p in (data_dir / name).iterdir() if p.is_dir()) for name in groups}
        return {name: uuids for name, uuids in result.items() if uuids}

    result: dict[str, list[str]] = {}
    for source_uuid in source_uuids:
        found = [name for name in groups if (data_dir / name / source_uuid).is_dir()]
        if not found:
            logger.warning("Директория источника %s не найдена в группах %s в %s", source_uuid, ", ".join(groups), data_dir)
            continue
        if len(found) > 1:
            logger.warning("Источник %s найден в нескольких группах (%s), берётся %s", source_uuid, ", ".join(found), found[0])
        result.setdefault(found[0], []).append(source_uuid)
    return result
