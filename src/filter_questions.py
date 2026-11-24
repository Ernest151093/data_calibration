"""Этап 1 (run_nerel_questions): разделение вопросов на rag / norag."""
from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Optional

from tqdm import tqdm

from src.data import FILTERING_SUFFIX, STRUCTURED_GLOB, Layout, get_question, load_json, save_json
from src.skill_client import make_batch_eval, predict, question_from_element_id

logger = logging.getLogger(__name__)

STAGE = "filter"


def load_filter_config(config_path: Path, prompt_path: Path) -> dict:
    cfg = load_json(config_path)
    prompt_line = prompt_path.read_text(encoding="utf-8").strip()
    # SYSTEM_PROMPT = "..." -> берём значение справа от "=" и разворачиваем \n-эскейпы
    cfg["tasks"][0]["configuration"]["prompts"]["system_prompt"] = ast.literal_eval(prompt_line.split("=", 1)[1])
    return cfg


def dedupe_by_question(batch_elems: list[dict]) -> list[dict]:
    uniq_batch = []
    seen = set()
    for el in batch_elems:
        question = get_question(el)
        if question not in seen:
            uniq_batch.append(el)
            seen.add(question)
    return uniq_batch


def classify_batch(batch: list[dict], cfg: dict, skill_url: str, retries: int = 5) -> Optional[dict]:
    """Возвращает {"rag": [...], "norag": [...]} или None, если все попытки неудачны."""
    for _ in range(retries):
        try:
            response = predict(skill_url, make_batch_eval(batch), cfg)
            result = {"rag": [], "norag": []}
            for task_response in response["skillResult"]["response"]["tasks_responses"]:
                tag = task_response["task_result"]["metrics"][0]["value"]
                result[tag].append(question_from_element_id(task_response["element_id"]))
            return result
        except Exception as exc:
            logger.warning("Ошибка классификации батча: %r", exc)
    return None


def filter_file(path: Path, cfg: dict, skill_url: str, batch_size: int) -> dict:
    uniq_batch = dedupe_by_question(load_json(path)["request"]["batch"])
    result = {"rag": [], "norag": []}
    for i in range(0, len(uniq_batch), batch_size):
        batch_result = classify_batch(uniq_batch[i:i + batch_size], cfg, skill_url)
        if batch_result is None:
            continue
        result["rag"].extend(batch_result.get("rag", []))
        result["norag"].extend(batch_result.get("norag", []))
    return result


def run_filter(source_uuids: list[str], layout: Layout, cfg: dict, skill_url: str, batch_size: int = 50, force: bool = False) -> None:
    for source_uuid in source_uuids:
        out_dir = layout.stage_dir(STAGE, source_uuid)
        for path in tqdm(sorted(layout.input_dir(source_uuid).glob(STRUCTURED_GLOB)), desc=f"filter {source_uuid}"):
            out_path = out_dir / (path.name.removesuffix(".json") + FILTERING_SUFFIX)
            if out_path.exists() and not force:
                continue
            save_json(out_path, filter_file(path, cfg, skill_url, batch_size))
