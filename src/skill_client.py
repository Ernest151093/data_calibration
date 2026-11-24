"""Клиент сервиса навыка (/predict)."""
from __future__ import annotations

import io
import json
import uuid

import requests
from requests_toolbelt.multipart.encoder import MultipartEncoder

from src.data import get_question

PREDICT_PARAMS = '{"msgId": "message001", "workId": "word001", "msgTm": "time001", "msgProperties": {"external_uuid": "22222222"}}'

ELEMENT_ID_SEPARATOR = "|||"


def predict(url: str, structured_data: dict, configuration: dict, timeout: int = 99999) -> dict:
    """Отправляет запрос в сервис навыка; данные стримятся через MultipartEncoder."""
    encoder = MultipartEncoder(
        fields={
            "predictParams": (None, PREDICT_PARAMS, "application/json"),
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
