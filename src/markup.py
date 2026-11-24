"""Этап 3 (run_markup_all_sources_filtered_lora): LLM-разметка релевантности контрольной выборки."""
from __future__ import annotations

import logging
import random
from pathlib import Path

from tqdm import tqdm

from src.data import FULL_FILTERED_BATCH, MARKUP_RESULT, load_json, save_json
from src.skill_client import make_batch_eval, predict

logger = logging.getLogger(__name__)


def sample_control_set(batch_elems: list[dict], seed: int = 42) -> list[dict]:
    # 10% выборки, но не меньше 100 (и не больше, чем есть сообщений)
    n = min(len(batch_elems), max(100, len(batch_elems) // 10))
    return random.Random(seed).sample(batch_elems, n)


def run_markup(source_dirs: list[Path], cfg: dict, skill_url: str, force: bool = False) -> None:
    for source_dir in tqdm(source_dirs, desc="markup"):
        out_path = source_dir / MARKUP_RESULT
        if out_path.exists() and not force:
            continue

        batch_path = source_dir / FULL_FILTERED_BATCH
        if not batch_path.exists():
            logger.warning("Нет %s", batch_path)
            continue

        batch_elems = load_json(batch_path).get("request", {}).get("batch", [])
        if not batch_elems:
            logger.warning("Пустой батч, пропуск: %s", source_dir)
            continue

        control_set = sample_control_set(batch_elems)
        logger.info("[%s] Total control_set: %d", source_dir.name, len(control_set))

        try:
            markup_response = predict(skill_url, make_batch_eval(control_set), cfg)
        except Exception as exc:
            logger.error("[%s] ошибка разметки: %r", source_dir.name, exc)
            continue

        save_json(out_path, markup_response)
