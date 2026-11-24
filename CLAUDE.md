# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Что это

Пайплайн калибровки **отчёта о покрытии базы знаний** (RAG) для источников чат-ассистента. Точка входа — `main.py`, логика этапов — в пакете `src/` (по модулю на этап). Этапы связаны только через JSON-файлы: `DATA_DIR` только читается, каждый этап пишет в свою папку `OUTPUT_DIR/<stage>/<source_uuid>/` и читает результаты предыдущих этапов оттуда же. Исходные Jupyter-ноутбуки (`run_*.ipynb`, `merge_filtered_reports.ipynb`) оставлены как референс, из них перенесена логика; правки вносить в `src/`. Комментарии, логи и промпты — на русском. Пользовательская документация (установка, запуск, описание колонок отчётов) — в `README.md`; при изменении CLI, переменных `.env`, имён файлов или колонок отчёта обновлять и его.

## Команды

```bash
pip install -r requirements.txt          # Python ≥ 3.9 (str.removesuffix)
cp .env.example .env                     # заполнить DATA_DIR, RERANKER_CERT, RERANKER_KEY

# весь пайплайн по группе источников из configs/sources.json
python main.py --group ka

# отдельные этапы / отдельные источники; --force пересчитывает уже готовые файлы
python main.py --stages markup report --sources <uuid1> <uuid2>

flake8 main.py src/                      # настройки в .flake8
```

Базовые пути (данные, результаты, конфиги, промпты, сертификаты) и хосты (`SKILL_URL`, `RERANKER_URL`) задаются в `.env` и читаются в `src/settings.py`; относительные пути — от корня проекта. Аргументы командной строки переопределяют `.env`, а переменные окружения процесса имеют приоритет над `.env`. Новые пути/хосты добавлять в `settings.py` и `.env.example`, не хардкодить в модулях.

Без `--sources`/`--group` обрабатываются все поддиректории `DATA_DIR`. Отчёты пишутся в `OUTPUT_DIR/report/` (`OUTPUT_DIR` по умолчанию `output/`): `reports_<label>/<uuid>.json`, `report_<label>.xlsx`, `task_<label>.xlsx`; `--label` (по умолчанию `ka`) также идёт в колонку `source`. Тестов нет.

## Внешние сервисы

- **Сервис навыка** (`SKILL_URL`, по умолчанию `http://localhost:8080/predict`) — `src/skill_client.py::predict`: multipart POST с полями `predictParams` (фиксированный фиктивный JSON), `structuredData` и `configuration`. Ответ — в `response["skillResult"]["response"]` (`tasks_responses` для LLM-задач, `source_types_coverage` / `clusters` для покрытия). Нужен всем этапам, кроме `merge` и `rerank`.
- **Реранкер** (`RERANKER_URL`) — HTTPS с клиентским сертификатом и `verify=False`; `RerankerClient.get_scores` делает 10 попыток и при неудаче возвращает скоры `0` (с warning в логе).

## Этапы (`--stages`, всегда выполняются в этом порядке)

1. **`filter`** (`src/filter_questions.py`) — RAG/no-RAG. Берёт `configs/expected_source_binary.json` и подставляет системный промпт из `prompts/prompt_rag_norag_v3.txt` (строка `SYSTEM_PROMPT = "..."`, парсится `ast.literal_eval`). Дедуплицирует `*structured.json` по вопросу, батчи по 50 → `*_filtering_result.json` = `{"rag": [...], "norag": [...]}`.
2. **`merge`** (`src/merge.py`) — оставляет из исходных батчей только `rag`-вопросы и сливает в `full_filtered_batch.json`. Всегда перезаписывает.
3. **`markup`** (`src/markup.py`) — контрольная выборка (`max(100, 10%)`, seed 42) из `full_filtered_batch.json`, разметка релевантности каждого источника задачей `llm_retrieval` (конфиг и промпт — `configs/relevance_markup.json`) → `control_set_lora_markup_part1.json`.
4. **`rerank`** (`src/reranker.py`) — пишет `reranker_relevance_score` в каждый источник → `full_filtered_batch_with_scores.json`.
5. **`report`** (`src/reports.py`) — два вызова задачи `coverage`: первый с `request.control_set` (разметка `True→"full"`, иначе `"irrel"`, повтор 3×) подбирает по типу источника (`faq`/`document`) порог, TPR, FPR; второй — без control_set, с этими порогами и `classes_effective_coverage_stats` — даёт итоговое (эффективное) покрытие, которое и сохраняется.

`markup` и `rerank` независимы друг от друга (оба читают `full_filtered_batch.json`); `report` требует результатов обоих.

## Соглашения по данным

- Входные данные вне репозитория: `DATA_DIR/<source_uuid>/*structured.json`. Группы источников (`uuid -> число вопросов`) — `SOURCES_CONFIG` (`configs/sources.json`).
- Пути строит `Layout` (`src/data.py`): `input_dir(uuid)` и `stage_dir(stage, uuid)`. Имя папки этапа — константа `STAGE` в его модуле; этап читает вход предыдущего через `layout.stage_dir(<модуль>.STAGE, uuid)`. Имена файлов — константы в `src/data.py`.
- Формат батча: `{"request": {"batch": [{"messages": [...], "duplicates_count"?: int}]}}`. `messages[-2]["content"]` — вопрос пользователя (`get_question`), `messages[-1]["sources"]` — источники (`get_sources`; поля `data_source_type` = `faq`|`document`, `content` или `metadata.raw_text`, `reranker_relevance_score`).
- `element_id` в LLM-задачах — `"<вопрос>|||<uuid4>"`; результаты сопоставляются с батчем по вопросу, поэтому вопрос везде берётся из `messages[-2]`.
- `filter`, `markup`, `rerank` пропускают источник, если выходной файл уже есть (`--force` — пересчитать).
