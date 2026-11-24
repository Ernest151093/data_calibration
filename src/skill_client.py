"""Клиент сервиса навыка (/predict)."""
from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, timezone

import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder

from src.data import get_question

ELEMENT_ID_SEPARATOR = "|||"


def format_msg_tm(moment: datetime) -> str:
    """ISO 8601 в UTC с миллисекундами: 2026-11-24T15:04:05.123Z."""
    return moment.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def make_predict_params(source_uuid: str) -> str:
    """predictParams запроса: новые msgId/workId на каждый вызов, external_uuid — UUID источника."""
    return json.dumps(
        {
            "msgId": str(uuid.uuid4()),
            "workId": str(uuid.uuid4()),
            "msgTm": format_msg_tm(datetime.now(timezone.utc)),
            "msgProperties": {"external_uuid": source_uuid},
        }
    )


def predict(url: str, source_uuid: str, structured_data: dict, configuration: dict, timeout: int = 99999) -> dict:
    """Отправляет запрос в сервис навыка; данные стримятся через MultipartEncoder."""
    encoder = MultipartEncoder(
        fields={
            "predictParams": (None, make_predict_params(source_uuid), "application/json"),
            "structuredData": (None, io.BytesIO(json.dumps(structured_data).encode("utf-8")), "application/json"),
            "configuration": (None, io.BytesIO(json.dumps(configuration).encode("utf-8")), "application/json"),
        }
    )
    # Content-Type берём из энкодера: в нём boundary для разделения полей
    response = requests.post(url, data=encoder, headers={"Content-Type": encoder.content_type}, timeout=timeout)
    return response.json()


def make_batch_eval(batch: list[dict]) -> dict:
    """structuredData для LLM-задач; element_id = "<вопрос>|||<uuid4>"."""
    return {
        "request_type": "batch_eval",
        "batch": [
            {
                "element_id": get_question(el) + ELEMENT_ID_SEPARATOR + str(uuid.uuid4()),
                "messages": el["messages"],
            }
            for el in batch
        ],
    }


def question_from_element_id(element_id: str) -> str:
    return element_id.split(ELEMENT_ID_SEPARATOR)[0]
