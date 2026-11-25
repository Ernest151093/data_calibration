"""Настройки из .env: базовые пути и хосты. Аргументы командной строки их переопределяют."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

load_dotenv(ROOT / ".env")


def env_str(name: str, default: Optional[str] = None) -> Optional[str]:
    return os.getenv(name) or default


def env_path(name: str, default: Optional[str] = None) -> Optional[Path]:
    """Путь из переменной окружения; относительные пути считаются от корня проекта."""
    value = env_str(name, default)
    if value is None:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT / path


# Хосты
SKILL_URL = env_str("SKILL_URL", "http://localhost:8080/predict")
RERANKER_URL = env_str("RERANKER_URL")

# Данные и результаты
DATA_DIR = env_path("DATA_DIR")
OUTPUT_DIR = env_path("OUTPUT_DIR", "output")
LOG_DIR = env_path("LOG_DIR", "logs")

# Конфиги и промпты
FILTER_CONFIG = env_path("FILTER_CONFIG", "configs/expected_source_binary.json")
FILTER_PROMPT = env_path("FILTER_PROMPT", "prompts/prompt_rag_norag_v3.txt")
MARKUP_CONFIG = env_path("MARKUP_CONFIG", "configs/relevance_markup.json")

# Сертификаты реранкера
RERANKER_CERT = env_path("RERANKER_CERT")
RERANKER_KEY = env_path("RERANKER_KEY")
