"""Этап 5 (run_reports): калибровка порогов и отчёты о покрытии."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
from tqdm import tqdm

from src.data import BATCH_WITH_SCORES, MARKUP_RESULT, get_question, get_sources, load_json, save_json
from src.skill_client import predict, question_from_element_id

logger = logging.getLogger(__name__)

SOURCE_TYPES = ("faq", "document")


@dataclass
class SourceReport:
    source_uuid: str
    questions_count: int
    # Статистика калибровки по типу источника: threshold, tpr, fpr, total, actual_not_covered
    stats: dict
    # Итоговый ответ сервиса (с порогами и эффективными метриками)
    response: dict

    @property
    def coverage_by_type(self) -> dict:
        coverage = self.response["skillResult"]["response"]["source_types_coverage"]
        return {item["source_type"]: item for item in coverage}


def build_coverage_config(thr_faq: Optional[float] = None, thr_doc: Optional[float] = None, eff_metrics: Optional[dict] = None) -> dict:
    config = {
        "task": {
            "type": "coverage",
            "name": "sbol",
            "configuration": {
                "relevance_configuration": [
                    {
                        "source_type": "faq",
                        "relevance_threshold": thr_faq or 1,
                        "relevance_scenario": "reranker",
                    },
                    {
                        "source_type": "document",
                        "relevance_threshold": thr_doc or 1,
                        "relevance_scenario": "reranker",
                    },
                ],
                "classifier": {
                    "enabled": False,
                    "llm_params": {
                        "profanity_check": True,
                        "model_name": "GigaChat-2-Max",
                    },
                },
                "clustering": {
                    "enabled": False,
                    "dbscan_configuration": {
                        "dbscan_eps": 0.15,
                        "metric": "cosine",
                    },
                },
                "question_generator": {"enabled": False},
                "control_set_parser": {"enabled": True},
                "answer_generator": {"enabled": False},
                "output_format": {
                    "scenarios": [
                        {"name": "analysis_by_source_type"},
                        {"name": "analysis_by_cluster"},
                    ]
                },
            },
        }
    }

    if eff_metrics:
        config["task"]["configuration"]["output_format"]["scenarios"][0]["configuration"] = eff_metrics
    return config


def drop_empty_sources(batch: dict) -> dict:
    batch["request"]["batch"] = [el for el in batch["request"]["batch"] if get_sources(el) != []]
    return batch


def load_question_tags(markup: dict, source_uuid: str) -> Optional[dict]:
    """Вопрос -> разметка источников ("full"/"irrel"), повторённая 3 раза."""
    if "skillResult" not in markup:
        return None

    question2tags = {}
    for el in markup["skillResult"]["response"]["tasks_responses"]:
        try:
            question = question_from_element_id(el["element_id"])
            tags = ["full" if tag is True else "irrel" for tag in el["task_result"]["metrics"][0]["value"]]
            question2tags[question] = [tags] * 3
        except (KeyError, IndexError, TypeError):
            logger.warning("[%s] битый элемент разметки: %.200s", source_uuid, el)
    return question2tags


def present_source_types(batch: dict) -> set:
    return {source["data_source_type"] for el in batch["request"]["batch"] for source in get_sources(el)}


def build_source_report(source_dir: Path, skill_url: str) -> Optional[SourceReport]:
    source_uuid = source_dir.name
    batch_path = source_dir / BATCH_WITH_SCORES
    markup_path = source_dir / MARKUP_RESULT
    for path in (batch_path, markup_path):
        if not path.exists():
            logger.warning("Нет %s", path)
            return None

    batch = drop_empty_sources(load_json(batch_path))
    batch_elems = batch["request"]["batch"]
    if not batch_elems:
        logger.warning("Пустой батч, пропуск: %s", source_dir)
        return None

    questions_count = sum(el.get("duplicates_count", 1) for el in batch_elems)
    question2messages = {get_question(el): el["messages"] for el in batch_elems}

    question2tags = load_question_tags(load_json(markup_path), source_uuid)
    if question2tags is None:
        logger.warning("[%s] в разметке нет skillResult", source_uuid)
        return None

    # 1-й проход: подбор порогов по контрольной выборке
    batch["request"]["control_set"] = [
        {"messages": question2messages[question], "markup": tags}
        for question, tags in question2tags.items()
        if question in question2messages
    ]
    calibration = predict(skill_url, batch, build_coverage_config())
    if "skillResult" not in calibration:
        logger.error("[%s] ошибка калибровки: %.500s", source_uuid, calibration)
        return None

    coverage_by_type = {item["source_type"]: item for item in calibration["skillResult"]["response"]["source_types_coverage"]}
    present_types = present_source_types(batch)
    stats = {}
    eff_metrics = {"classes_effective_coverage_stats": {"enabled": True, "class_metrics": []}}

    for source_type in SOURCE_TYPES:
        if source_type not in present_types:
            continue
        obj = coverage_by_type[source_type]
        stats[source_type] = {key: obj[key] for key in ("threshold", "tpr", "fpr", "total", "actual_not_covered")}
        eff_metrics["classes_effective_coverage_stats"]["class_metrics"].append(
            {
                "source_type": source_type,
                "tpr": obj["tpr"],
                "fpr": obj["fpr"],
                "n_actually_not_covered": obj["actual_not_covered"],
                "n_total": obj["total"],
            }
        )

    # 2-й проход: покрытие с подобранными порогами и эффективными метриками
    del batch["request"]["control_set"]
    response = predict(
        skill_url,
        batch,
        build_coverage_config(
            thr_faq=stats.get("faq", {}).get("threshold"),
            thr_doc=stats.get("document", {}).get("threshold"),
            eff_metrics=eff_metrics,
        ),
    )
    if "skillResult" not in response:
        logger.error("[%s] ошибка построения отчёта: %.500s", source_uuid, response)
        return None

    return SourceReport(source_uuid, questions_count, stats, response)


def build_report_row(report: SourceReport, label: str) -> dict:
    row = {
        "source_uuid": report.source_uuid,
        "report": "",
        "json_name": report.source_uuid,
        "source": label,
        "questions_count": report.questions_count,
    }
    coverage_by_type = report.coverage_by_type
    for source_type in SOURCE_TYPES:
        coverage = coverage_by_type.get(source_type, {})
        stats = report.stats.get(source_type, {})
        cov_eff = coverage.get("total_coverage_effective_percentage", 0)
        raw_cov = coverage.get("total_coverage_percentage", 0)
        row[f"cov_eff_{source_type}"] = cov_eff
        row[f"raw_cov_{source_type}"] = raw_cov
        row[f"max_coverage_{source_type}"] = max(cov_eff, raw_cov)
        row[f"TPR_{source_type}"] = stats.get("tpr", 0)
        row[f"FPR_{source_type}"] = stats.get("fpr", 0)
        row[f"c_set_total_questions_{source_type}"] = stats.get("total", 0)
        row[f"c_set_total_uncovered_questions_{source_type}"] = stats.get("actual_not_covered", 0)
        row[f"t_rel_{source_type}"] = stats.get("threshold", 0)
    row["is_top_agent"] = ""
    return row


def build_task_row(report: SourceReport, label: str) -> dict:
    response = report.response["skillResult"]["response"]
    questions = [question["question"] for cluster in response.get("clusters", []) for question in cluster["questions"]]
    return {
        "report": "",
        "source": label,
        "source_uuid": report.source_uuid,
        "class_name": "Все вопросы",
        "cluster_name": "",
        "list_questions": questions,
    }


def run_reports(source_dirs: list[Path], skill_url: str, output_dir: Path, label: str) -> None:
    reports_dir = output_dir / f"reports_{label}"
    reports_dir.mkdir(parents=True, exist_ok=True)

    report_rows = []
    task_rows = []
    for source_dir in tqdm(source_dirs, desc="reports"):
        report = build_source_report(source_dir, skill_url)
        if report is None:
            continue
        save_json(reports_dir / f"{report.source_uuid}.json", report.response)
        report_rows.append(build_report_row(report, label))
        task_rows.append(build_task_row(report, label))

    if not report_rows:
        logger.warning("Ни одного отчёта не построено")
        return
    pd.DataFrame(report_rows).to_excel(output_dir / f"report_{label}.xlsx")
    pd.DataFrame(task_rows).to_excel(output_dir / f"task_{label}.xlsx")
    logger.info("Отчёты сохранены в %s", output_dir)
