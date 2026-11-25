# data_calibration

Пайплайн калибровки отчёта о покрытии базы знаний (RAG) для источников чат-ассистента.

Для каждого источника (UUID) пайплайн:

1. отбирает вопросы, для ответа на которые нужен поиск (RAG);
2. размечает LLM-моделью релевантность найденных источников на контрольной выборке;
3. считает скоры реранкера для всех найденных источников;
4. по разметке подбирает пороги релевантности реранкера отдельно для `faq` и `document` и строит отчёт о покрытии.

## Требования

- Python 3.9+
- Запущенный сервис навыка (по умолчанию `http://localhost:8080/predict`) — нужен для этапов `filter`, `markup`, `report`
- Доступ к реранкеру и клиентский сертификат (`cert.pem` / `cert.key`) — нужен для этапа `rerank`

## Установка

```bash
pip install -r requirements.txt
cp .env.example .env
```

Заполните `.env`:

| Переменная | Назначение | По умолчанию |
|---|---|---|
| `DATA_DIR` | директория `structured_data` с поддиректориями групп (`ka`, `sh`), в каждой — `<source_uuid>/*structured.json`; только читается | — (обязательна) |
| `OUTPUT_DIR` | корень результатов: `<stage>/<group>/<source_uuid>/` | `output` |
| `SKILL_URL` | адрес сервиса навыка | `http://localhost:8080/predict` |
| `RERANKER_URL` | адрес реранкера | — |
| `RERANKER_CERT`, `RERANKER_KEY` | клиентский сертификат и ключ реранкера | — |
| `SOURCES_CONFIG` | группы источников | `configs/sources.json` |
| `FILTER_CONFIG`, `FILTER_PROMPT` | конфиг и промпт фильтра RAG/no-RAG | `configs/expected_source_binary.json`, `prompts/prompt_rag_norag_v3.txt` |
| `MARKUP_CONFIG` | конфиг и промпт разметки релевантности | `configs/relevance_markup.json` |

Относительные пути считаются от корня проекта. Любое значение можно переопределить аргументом командной строки (`python main.py --help`).

## Запуск

```bash
# весь пайплайн для группы источников ka из configs/sources.json
python main.py --group ka

# только указанные источники (группа ka/sh определяется по папке в DATA_DIR)
python main.py --sources 3dbbf0a0-4858-4591-9e26-5a672edf5a2e 8771ad26-20cc-4130-93cb-4435da96e0ee

# только отдельные этапы
python main.py --group ka --stages markup report

# пересчитать этапы, даже если результаты уже есть
python main.py --group ka --force

# своя метка для колонки source и имён отчётов (по умолчанию — имя группы)
python main.py --group sh --label sh_test
```

Без `--sources` / `--group` обрабатываются все источники всех групп `DATA_DIR`. С `--sources` каждый UUID ищется в `DATA_DIR/ka/` и `DATA_DIR/sh/`; найденные источники обрабатываются по группам.

## Этапы и файлы

Этапы выполняются в порядке `filter → merge → markup → rerank → report`. `DATA_DIR` только читается; каждый этап пишет результаты в свою папку:

```
OUTPUT_DIR/
├── filter/<group>/<source_uuid>/*structured_filtering_result.json
├── merge/<group>/<source_uuid>/full_filtered_batch.json
├── markup/<group>/<source_uuid>/control_set_lora_markup_part1.json
├── rerank/<group>/<source_uuid>/full_filtered_batch_with_scores.json
└── report/<group>/
    ├── reports_<label>/<source_uuid>.json
    ├── report_<label>.xlsx
    └── task_<label>.xlsx
```

| Этап | Читает | Пишет |
|---|---|---|
| `filter` | `DATA_DIR/<group>/<uuid>/*structured.json` | `filter/<group>/<uuid>/*structured_filtering_result.json` — списки вопросов `rag` / `norag` |
| `merge` | `DATA_DIR/<group>/<uuid>/*structured.json` + `filter/<group>/<uuid>/` | `merge/<group>/<uuid>/full_filtered_batch.json` — только `rag`-вопросы |
| `markup` | `merge/<group>/<uuid>/full_filtered_batch.json` | `markup/<group>/<uuid>/control_set_lora_markup_part1.json` — разметка контрольной выборки (10%, но не меньше 100 вопросов) |
| `rerank` | `merge/<group>/<uuid>/full_filtered_batch.json` | `rerank/<group>/<uuid>/full_filtered_batch_with_scores.json` — то же + `reranker_relevance_score` у каждого источника |
| `report` | `rerank/<group>/<uuid>/` + `markup/<group>/<uuid>/` | `report/<group>/reports_<label>/<uuid>.json`, `report/<group>/report_<label>.xlsx`, `report/<group>/task_<label>.xlsx` |

Этапы `filter`, `markup` и `rerank` пропускают источник, если их выходной файл уже существует, поэтому прерванный запуск можно просто повторить. Чтобы пересчитать этап, удалите его выходной файл или запустите с `--force`. `merge` и `report` выполняются всегда.

## Результаты

**`report/<group>/report_<label>.xlsx`** — строка на источник, колонки для каждого типа источника (`faq`, `document`):

| Колонка | Значение |
|---|---|
| `questions_count` | число вопросов с найденными источниками (с учётом `duplicates_count`) |
| `t_rel_<type>` | подобранный порог релевантности реранкера |
| `TPR_<type>`, `FPR_<type>` | TPR и FPR порога на контрольной выборке |
| `c_set_total_questions_<type>` | размер контрольной выборки |
| `c_set_total_uncovered_questions_<type>` | вопросов контрольной выборки без релевантного источника по разметке |
| `raw_cov_<type>` | покрытие по порогу реранкера (`total_coverage_percentage`) |
| `cov_eff_<type>` | эффективное покрытие с учётом TPR/FPR (`total_coverage_effective_percentage`) |
| `max_coverage_<type>` | максимум из `raw_cov` и `cov_eff` |

Если какого-то типа источников у источника нет, его колонки равны 0. Колонки `report` и `is_top_agent` всегда пустые.

**`report/<group>/task_<label>.xlsx`** — список вопросов по кластерам из отчёта. Кластеризация в конфиге отчёта сейчас выключена, поэтому `list_questions` пустой.

**`report/<group>/reports_<label>/<uuid>.json`** — полный ответ сервиса по источнику.

## Структура проекта

```
main.py              точка входа
src/                 логика этапов (по модулю на этап) и клиенты сервисов
configs/             конфиги задач и группы источников
prompts/             промпты
```
