"""Этап 4 (run_reranker): скоры реранкера для каждого источника."""
from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import requests
import urllib3
from tqdm import tqdm

from src.data import BATCH_WITH_SCORES, FULL_FILTERED_BATCH, get_question, get_sources, load_json, save_json

logger = logging.getLogger(__name__)

# Реранкер вызывается с verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class RerankerClient:
    def __init__(self, url: str, cert_path: Path, key_path: Path, retries: int = 10):
        self.url = url
        self.cert = (str(cert_path), str(key_path))
        self.retries = retries

    def get_scores(self, query: str, passages_text: list[str]) -> list[float]:
        """Скоры для пар (query, passage); после всех неудачных попыток — нули."""
        for _ in range(self.retries):
            try:
                json_data = {
                    "workId": str(uuid.uuid4()),
                    "msgId": str(uuid.uuid4()),
                    "msgTm": datetime.now().isoformat() + "Z",
                    "inputs": [{"query": query.lower(), "paragraph": text.lower()} for text in passages_text],
                }
                resp = requests.post(
                    url=self.url,
                    headers={"Content-Type": "application/json"},
                    json=json_data,
                    cert=self.cert,
                    verify=False,
                )
                return [el["score"] for el in resp.json()["modelResults"]]
            except Exception:
                continue

        logger.warning("Реранкер не ответил, скоры = 0 для вопроса: %.80s", query)
        return [0] * len(passages_text)


def score_batch_elem(client: RerankerClient, batch_elem: dict) -> None:
    sources = get_sources(batch_elem)
    if not sources:
        return

    texts = [source.get("content") or source["metadata"].get("raw_text") for source in sources]
    # Скоры сразу для всех текстов одного вопроса, записываем обратно в источники
    scores = client.get_scores(get_question(batch_elem), texts)
    for score, source in zip(scores, sources):
        source["reranker_relevance_score"] = score


def run_rerank(source_dirs: list[Path], client: RerankerClient, max_workers: int = 7, force: bool = False) -> None:
    for source_dir in source_dirs:
        out_path = source_dir / BATCH_WITH_SCORES
        if out_path.exists() and not force:
            continue

        batch_path = source_dir / FULL_FILTERED_BATCH
        if not batch_path.exists():
            logger.warning("Нет %s", batch_path)
            continue

        data = load_json(batch_path)
        batch_elems = data["request"]["batch"]

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(score_batch_elem, client, el) for el in batch_elems]
            for future in tqdm(as_completed(futures), total=len(futures), desc=f"rerank {source_dir.name}", leave=False):
                future.result()

        save_json(out_path, data)
