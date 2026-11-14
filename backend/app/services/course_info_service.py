from __future__ import annotations

import json
import os
import hashlib
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from openai import AzureOpenAI, OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, PayloadSchemaType, PointStruct, VectorParams

from app.services.ai_provider import get_chat_client, get_chat_model_name


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
QDRANT_DIR = PROCESSED_DIR / "qdrant_data"
COURSE_INDEX_PATH = PROCESSED_DIR / "course_index.json"
ELIGIBILITY_PATH = PROCESSED_DIR / "course_eligibility.json"

COURSE_COLLECTIONS = ("ncu_courses_ug", "ncu_courses_grad")
QUERY_CACHE_COLLECTION = "ncu_query_embedding_cache"
VECTOR_DIM = 3072
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-large"
DEFAULT_CHAT_MODEL = "gpt-4o-mini"
DEFAULT_QUERY_CACHE_KEYWORDS = [
    "程式",
    "Python",
    "人工智慧",
    "AI",
    "機器學習",
    "深度學習",
    "資料分析",
    "資料庫",
    "演算法",
    "資料結構",
    "軟體工程",
    "網路",
    "資訊安全",
    "統計",
    "微積分",
    "電路",
    "訊號",
    "管理",
    "金融",
    "永續",
]


def normalize_course_code(value: Any) -> str:
    text = str(value or "").strip()
    return text.split("-", 1)[0].strip()


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _shorten(value: Any, limit: int = 320) -> str:
    text = " ".join(_clean_text(value).split())
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        text = str(value).strip()
        if not text:
            return []
        for separator in ("||", "|", "、", ",", ";"):
            text = text.replace(separator, "\n")
        items = text.splitlines()

    normalized: list[str] = []
    for item in items:
        if isinstance(item, dict):
            candidate = item.get("display") or item.get("name") or item.get("label") or item.get("topic") or item.get("concept")
        else:
            candidate = item
        text = _clean_text(candidate)
        if not text:
            continue
        if "::" in text:
            text = text.split("::")[-1].strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _semester_display(value: Any) -> str:
    text = _clean_text(value)
    if text in {"1", "上", "上學期"}:
        return "上學期"
    if text in {"2", "下", "下學期"}:
        return "下學期"
    if text in {"全", "全年"}:
        return "全年"
    return text or "未指定"


@lru_cache(maxsize=4)
def _load_json(path: str) -> Any:
    file_path = Path(path)
    if not file_path.exists():
        return [] if file_path.suffix == ".json" else {}
    try:
        with file_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"[WARN] Failed to load {file_path}: {exc}")
        return [] if file_path.suffix == ".json" else {}


@lru_cache(maxsize=1)
def _course_index() -> dict[str, dict[str, Any]]:
    data = _load_json(str(COURSE_INDEX_PATH))
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def _eligibility_indexes() -> dict[str, dict[Any, Any]]:
    data = _load_json(str(ELIGIBILITY_PATH))
    rows = data if isinstance(data, list) else []

    by_code: dict[str, dict[str, Any]] = {}
    by_name_dept_semester: dict[tuple[str, str, str], dict[str, Any]] = {}
    by_name_dept: dict[tuple[str, str], dict[str, Any]] = {}

    for row in rows:
        if not isinstance(row, dict):
            continue
        code = normalize_course_code(row.get("course_code"))
        if code and code not in by_code:
            by_code[code] = row

        name = _clean_text(row.get("course_name"))
        dept = _clean_text(row.get("dept"))
        academic_year = _clean_text(row.get("academic_year"))
        semester = _clean_text(row.get("semester"))
        semester_key = f"{academic_year}_{semester}" if academic_year or semester else ""
        if name and dept and semester_key:
            by_name_dept_semester.setdefault((name, dept, semester_key), row)
        if name and dept:
            by_name_dept.setdefault((name, dept), row)

    return {
        "by_code": by_code,
        "by_name_dept_semester": by_name_dept_semester,
        "by_name_dept": by_name_dept,
    }


def find_eligibility(course: dict[str, Any]) -> dict[str, Any] | None:
    indexes = _eligibility_indexes()
    by_code = indexes["by_code"]
    code = normalize_course_code(course.get("course_id") or course.get("course_code"))
    if code and code in by_code:
        return by_code[code]

    name = _clean_text(course.get("course_name_zh") or course.get("course_name"))
    dept = _clean_text(course.get("department") or course.get("dept"))
    semester = _clean_text(course.get("semester"))
    if name and dept and semester:
        row = indexes["by_name_dept_semester"].get((name, dept, semester))
        if row:
            return row
    if name and dept:
        return indexes["by_name_dept"].get((name, dept))
    return None


def summarize_eligibility(row: dict[str, Any] | None) -> dict[str, str | None]:
    if not row:
        return {
            "summary": "尚未找到可對應的修課資格資料。",
            "status": "missing",
            "warning": "此課程未能從 course_eligibility.json 對應到修課資格。",
        }

    if row.get("is_unrestricted"):
        summary = "此課程標記為不限修課資格。"
    elif row.get("is_grad_only"):
        summary = "此課程標記為研究生課程，主要開放研究生修習。"
    elif row.get("is_open_to_all_undergrad"):
        summary = "此課程標記為全校大學部可修。"
    elif row.get("is_undergrad_open"):
        summary = "此課程標記為開放大學部學生修習，但仍需留意條件限制。"
    else:
        summary = "此課程有修課資格限制，請搭配分發條件原文確認。"

    rule_parts: list[str] = []
    for rule in row.get("access_rules") or []:
        if not isinstance(rule, dict):
            continue
        program_types = _normalize_list(rule.get("program_types"))
        if program_types:
            mapped = [
                {"bachelor": "學士班", "master": "碩士班", "phd": "博士班"}.get(item, item)
                for item in program_types
            ]
            rule_parts.append(f"學制: {'、'.join(mapped[:4])}")
        years = _normalize_list(rule.get("years"))
        if years:
            rule_parts.append(f"年級: {'、'.join(years[:4])}")
        for key, label in (
            ("dept_include", "系所"),
            ("college_include", "學院"),
            ("minor_include", "輔系"),
            ("double_major_include", "雙主修"),
            ("credit_prog_include", "學分學程"),
            ("spec_include", "第二專長"),
            ("edu_program_include", "教育學程"),
            ("section_include", "班別"),
        ):
            values = _normalize_list(rule.get(key))
            if values:
                rule_parts.append(f"{label}: {'、'.join(values[:4])}")
        if rule.get("open_to_minor"):
            rule_parts.append("開放輔系")
        if rule.get("open_to_double_major"):
            rule_parts.append("開放雙主修")
        if rule.get("open_to_credit_prog"):
            rule_parts.append("開放學分學程")
        if rule.get("open_to_cross_school"):
            rule_parts.append("開放校際選課")
    if rule_parts:
        summary = f"{summary} 條件摘要：{'；'.join(rule_parts[:3])}。"

    relations = row.get("course_relations") or {}
    relation_parts: list[str] = []
    if isinstance(relations, dict):
        prereq = _normalize_list(relations.get("prereq_codes"))
        coreq = _normalize_list(relations.get("coreq_codes"))
        conflicts = _normalize_list(relations.get("conflict_codes"))
        if prereq:
            relation_parts.append(f"先修: {'、'.join(prereq[:5])}")
        if coreq:
            relation_parts.append(f"並修: {'、'.join(coreq[:5])}")
        if conflicts:
            relation_parts.append(f"不得重複修習: {'、'.join(conflicts[:5])}")
    if relation_parts:
        summary = f"{summary} {'；'.join(relation_parts)}。"

    warning = None
    if row.get("unparseable_conditions") or row.get("has_special_condition"):
        warning = "資格條件含特殊或無法完整解析內容，建議人工確認。"

    return {
        "summary": summary,
        "status": "warning" if warning else "ok",
        "warning": warning,
    }


def enrich_course_dict(course: dict[str, Any]) -> dict[str, Any]:
    code = normalize_course_code(course.get("course_id"))
    indexed = _course_index().get(code, {}) if code else {}

    if indexed:
        course.setdefault("is_grad", indexed.get("is_grad"))
        course.setdefault("course_objective", indexed.get("objective"))
        course.setdefault("course_content", indexed.get("content"))
        course.setdefault("textbooks", indexed.get("textbook"))
        course.setdefault("course_field", indexed.get("course_domain"))
        course.setdefault("class_time", indexed.get("class_time"))
        if not course.get("instructor"):
            course["instructor"] = indexed.get("teacher") or ""

        course["languages"] = _normalize_list(indexed.get("languages"))
        course["tools"] = _normalize_list(indexed.get("tools"))
        course["concepts"] = _normalize_list(indexed.get("concepts"))
        course["topic_tags"] = _normalize_list(indexed.get("topic_tags"))
        course["domain_tags"] = _normalize_list(indexed.get("domain_tags"))
        course["core_questions"] = _normalize_list(indexed.get("core_questions"))
        course["simplified_concepts"] = _normalize_list(indexed.get("simplified_concepts"))

    eligibility = find_eligibility(course)
    eligibility_summary = summarize_eligibility(eligibility)
    course["eligibility_summary"] = eligibility_summary["summary"]
    course["eligibility_status"] = eligibility_summary["status"]
    course["eligibility_warning"] = eligibility_summary["warning"]

    return course


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _has_azure_openai_hint() -> bool:
    return bool(
        _env("AZURE_OPENAI_API_KEY")
        or _env("AZURE_OPENAI_ENDPOINT")
        or _env("AZURE_OPENAI_CHAT_DEPLOYMENT")
        or _env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
    )


def _get_ai_client() -> AzureOpenAI | OpenAI:
    azure_api_key = _env("AZURE_OPENAI_API_KEY")
    azure_endpoint = _env("AZURE_OPENAI_ENDPOINT")

    if _has_azure_openai_hint():
        if not azure_api_key or not azure_endpoint:
            raise RuntimeError(
                "AI_API_CONFIG_MISSING: 使用 Azure OpenAI 時，請同時設定 "
                "AZURE_OPENAI_API_KEY 和 AZURE_OPENAI_ENDPOINT。"
            )
        return AzureOpenAI(
            api_key=azure_api_key,
            azure_endpoint=azure_endpoint,
            api_version=_env("AZURE_OPENAI_API_VERSION") or "2024-12-01-preview",
        )

    openai_api_key = _env("OPENAI_API_KEY")
    if openai_api_key:
        return OpenAI(api_key=openai_api_key)

    raise RuntimeError(
        "AI_API_CONFIG_MISSING: 請設定 Azure OpenAI "
        "(AZURE_OPENAI_API_KEY、AZURE_OPENAI_ENDPOINT、AZURE_OPENAI_CHAT_DEPLOYMENT、"
        "AZURE_OPENAI_EMBEDDING_DEPLOYMENT)，或設定 OPENAI_API_KEY。"
    )


def _embedding_model_name() -> str:
    if _has_azure_openai_hint():
        deployment = _env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
        if not deployment:
            raise RuntimeError("AI_API_CONFIG_MISSING: 請設定 AZURE_OPENAI_EMBEDDING_DEPLOYMENT。")
        return deployment
    return _env("OPENAI_EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL


def _chat_model_name() -> str:
    if _has_azure_openai_hint():
        deployment = _env("AZURE_OPENAI_CHAT_DEPLOYMENT")
        if not deployment:
            raise RuntimeError("AI_API_CONFIG_MISSING: 請設定 AZURE_OPENAI_CHAT_DEPLOYMENT。")
        return deployment
    return _env("OPENAI_MODEL") or DEFAULT_CHAT_MODEL


@lru_cache(maxsize=512)
def _embed_query(query: str) -> list[float]:
    client = _get_ai_client()
    model = _embedding_model_name()
    response = client.embeddings.create(model=model, input=query)
    return response.data[0].embedding


def _get_shared_qdrant_client() -> QdrantClient:
    from app.services.retriever import _get_qdrant

    return _get_qdrant()


def normalize_query_for_cache(query: str) -> str:
    return " ".join(query.strip().lower().split())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _query_cache_point_id(normalized_query: str, model: str) -> int:
    raw = f"{model}:{normalized_query}"
    return int(hashlib.md5(raw.encode("utf-8")).hexdigest()[:15], 16)


def _ensure_query_cache_collection(client: QdrantClient) -> None:
    existing = {collection.name for collection in client.get_collections().collections}
    if QUERY_CACHE_COLLECTION in existing:
        _ensure_query_cache_indexes(client)
        return
    client.create_collection(
        collection_name=QUERY_CACHE_COLLECTION,
        vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
    )
    _ensure_query_cache_indexes(client)


def _ensure_query_cache_indexes(client: QdrantClient) -> None:
    """為 query cache collection 建立必要的 keyword payload indexes。"""
    for field in ("normalized_query", "embedding_model"):
        try:
            client.create_payload_index(
                collection_name=QUERY_CACHE_COLLECTION,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception:
            pass  # 索引已存在時 Qdrant 會回傳錯誤，忽略即可


def _extract_record_vector(record: Any) -> list[float] | None:
    vector = getattr(record, "vector", None)
    if isinstance(vector, dict):
        vector = vector.get("") or next(iter(vector.values()), None)
    if not vector:
        return None
    return list(vector)


def _load_cached_query_embedding(
    client: QdrantClient,
    normalized_query: str,
    model: str,
) -> tuple[list[float] | None, dict[str, Any]]:
    _ensure_query_cache_collection(client)
    records, _ = client.scroll(
        collection_name=QUERY_CACHE_COLLECTION,
        scroll_filter=Filter(
            must=[
                FieldCondition(key="normalized_query", match=MatchValue(value=normalized_query)),
                FieldCondition(key="embedding_model", match=MatchValue(value=model)),
            ]
        ),
        limit=1,
        with_payload=True,
        with_vectors=True,
    )
    if not records:
        return None, {}
    record = records[0]
    return _extract_record_vector(record), getattr(record, "payload", None) or {}


def _save_query_embedding_cache(
    client: QdrantClient,
    query: str,
    normalized_query: str,
    model: str,
    embedding: list[float],
    payload: dict[str, Any] | None = None,
) -> None:
    now = _now_iso()
    base_payload = payload or {}
    hit_count = int(base_payload.get("hit_count") or 0)
    point_id = _query_cache_point_id(normalized_query, model)
    client.upsert(
        collection_name=QUERY_CACHE_COLLECTION,
        points=[
            PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    **base_payload,
                    "query": query.strip(),
                    "normalized_query": normalized_query,
                    "embedding_model": model,
                    "created_at": base_payload.get("created_at") or now,
                    "last_used_at": now,
                    "hit_count": hit_count + 1,
                    "source": base_payload.get("source") or "runtime",
                },
            )
        ],
    )


def get_or_create_query_embedding(
    client: QdrantClient,
    query: str,
    source: str = "runtime",
) -> tuple[list[float], bool]:
    normalized_query = normalize_query_for_cache(query)
    if not normalized_query:
        return [], False

    model = _embedding_model_name()
    cached_vector, payload = _load_cached_query_embedding(client, normalized_query, model)
    if cached_vector:
        _save_query_embedding_cache(client, query, normalized_query, model, cached_vector, payload)
        return cached_vector, True

    embedding = _embed_query(normalized_query)
    _save_query_embedding_cache(
        client,
        query,
        normalized_query,
        model,
        embedding,
        {**payload, "source": source},
    )
    return embedding, False


def seed_query_embedding_cache(keywords: list[str] | None = None) -> list[dict[str, Any]]:
    if not QDRANT_DIR.exists():
        raise RuntimeError(f"Qdrant data directory not found: {QDRANT_DIR}")

    client = QdrantClient(path=str(QDRANT_DIR))
    seeded: list[dict[str, Any]] = []
    try:
        _ensure_query_cache_collection(client)
        for keyword in keywords or DEFAULT_QUERY_CACHE_KEYWORDS:
            normalized = normalize_query_for_cache(keyword)
            if not normalized:
                continue
            _, cache_hit = get_or_create_query_embedding(client, keyword, source="seed")
            seeded.append({"query": keyword, "normalized_query": normalized, "cache_hit": cache_hit})
        return seeded
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def _query_collection(client: QdrantClient, collection_name: str, embedding: list[float], limit: int) -> list[Any]:
    if hasattr(client, "query_points"):
        result = client.query_points(
            collection_name=collection_name,
            query=embedding,
            limit=limit,
            with_payload=True,
        )
        return list(result.points)

    return list(
        client.search(
            collection_name=collection_name,
            query_vector=embedding,
            limit=limit,
            with_payload=True,
        )
    )


def _payload_to_course(payload: dict[str, Any], score: float, source_collection: str, point_id: Any) -> dict[str, Any]:
    code = normalize_course_code(payload.get("course_code"))
    semester = _clean_text(payload.get("semester"))
    academic_year = _clean_text(payload.get("academic_year"))
    is_grad = bool(payload.get("is_grad") or source_collection.endswith("_grad"))
    raw_text = payload.get("_text")

    course = {
        "serial_no": f"{source_collection}:{point_id}",
        "course_id": code,
        "course_name_zh": _clean_text(payload.get("name_zh")),
        "course_name_en": _clean_text(payload.get("name_en")),
        "college": _clean_text(payload.get("college")),
        "department": _clean_text(payload.get("dept")),
        "instructor": _clean_text(payload.get("teacher")),
        "credits": _coerce_int(payload.get("credits")),
        "required_elective": _clean_text(payload.get("type")),
        "semester_display": _semester_display(semester),
        "semester": f"{academic_year}_{semester}" if academic_year or semester else None,
        "full_half_year": None,
        "course_objective": _clean_text(payload.get("objective")) or None,
        "course_content": _clean_text(payload.get("content")) or None,
        "textbooks": _clean_text(payload.get("textbook")) or None,
        "grading": None,
        "course_system": "研究所" if is_grad else "大學部",
        "course_field": _clean_text(payload.get("course_domain")) or None,
        "core_abilities": None,
        "distribution_conditions": None,
        "distribution_link": None,
        "outline_link": None,
        "class_time": _clean_text(payload.get("class_time")) or None,
        "classroom": None,
        "note": None,
        "teaching_method": None,
        "office_hours": None,
        "weeks": None,
        "is_grad": is_grad,
        "relevance_score": round(score, 4),
        "search_source": source_collection,
        "semantic_summary": _shorten(raw_text),
        "languages": _normalize_list(payload.get("languages")),
        "tools": _normalize_list(payload.get("tools")),
        "concepts": _normalize_list(payload.get("concepts")),
        "topic_tags": _normalize_list(payload.get("topic_tags")),
        "domain_tags": _normalize_list(payload.get("domain_tags")),
        "core_questions": _normalize_list(payload.get("core_questions")),
        "simplified_concepts": _normalize_list(payload.get("simplified_concepts")),
    }

    raw_conditions = _normalize_list(payload.get("when_raw"))
    if raw_conditions:
        course["distribution_conditions"] = [{"priority": "Qdrant", "condition": item} for item in raw_conditions[:4]]

    return enrich_course_dict(course)


def _matches_structured_filters(
    course: dict[str, Any],
    selected_types: list[str] | None,
    selected_credits: list[str] | None,
    selected_semesters: list[str] | None,
) -> bool:
    types = selected_types or []
    credits = selected_credits or []
    semesters = selected_semesters or []

    if types and _clean_text(course.get("required_elective")) not in types:
        return False
    if credits and str(course.get("credits")) not in credits:
        return False
    if semesters and _clean_text(course.get("semester_display")) not in semesters:
        return False
    return True


def semantic_search_courses(
    query: str,
    selected_types: list[str] | None = None,
    selected_credits: list[str] | None = None,
    selected_semesters: list[str] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if not query.strip():
        return []
    if not QDRANT_DIR.exists():
        raise RuntimeError(f"Qdrant data directory not found: {QDRANT_DIR}")

    per_collection_limit = max(limit, 40)
    client = _get_shared_qdrant_client()

    embedding, _ = get_or_create_query_embedding(client, query.strip())
    merged: list[dict[str, Any]] = []
    for collection_name in COURSE_COLLECTIONS:
        points = _query_collection(client, collection_name, embedding, per_collection_limit)
        for point in points:
            payload = getattr(point, "payload", None) or {}
            score = float(getattr(point, "score", 0.0) or 0.0)
            point_id = getattr(point, "id", "")
            course = _payload_to_course(payload, score, collection_name, point_id)
            if _matches_structured_filters(course, selected_types, selected_credits, selected_semesters):
                merged.append(course)

    deduped: dict[str, dict[str, Any]] = {}
    for course in sorted(merged, key=lambda item: item.get("relevance_score") or 0, reverse=True):
        key = "|".join(
            [
                _clean_text(course.get("course_id")),
                _clean_text(course.get("department")),
                _clean_text(course.get("instructor")),
                _clean_text(course.get("semester")),
            ]
        )
        deduped.setdefault(key, course)
    return list(deduped.values())[:limit]


def build_course_context(course_id: str) -> tuple[str, list[str]]:
    code = normalize_course_code(course_id)
    warnings: list[str] = []
    indexed = _course_index().get(code)
    if not indexed:
        warnings.append("course_index.json 找不到此課程代碼，AI 回答會缺少部分課程脈絡。")
        indexed = {"course_code": code}

    context_course = {
        "course_id": code,
        "course_name_zh": indexed.get("name_zh") or indexed.get("name") or "",
        "department": indexed.get("dept") or "",
        "semester": "",
    }
    eligibility = find_eligibility(context_course)
    eligibility_summary = summarize_eligibility(eligibility)
    if eligibility_summary.get("warning"):
        warnings.append(str(eligibility_summary["warning"]))
    if not eligibility:
        warnings.append("course_eligibility.json 未找到此課程對應資料。")

    lines = [
        f"課號: {code}",
        f"課名: {_clean_text(indexed.get('name_zh') or indexed.get('name'))}",
        f"英文課名: {_clean_text(indexed.get('name_en'))}",
        f"系所: {_clean_text(indexed.get('dept'))}",
        f"學院: {_clean_text(indexed.get('college'))}",
        f"授課教師: {_clean_text(indexed.get('teacher'))}",
        f"學分: {_clean_text(indexed.get('credits'))}",
        f"修別: {_clean_text(indexed.get('type'))}",
        f"學制: {'研究所' if indexed.get('is_grad') else '大學部'}",
        f"課程目標: {_shorten(indexed.get('objective'), 900)}",
        f"授課內容: {_shorten(indexed.get('content'), 1200)}",
        f"教科書/參考書: {_shorten(indexed.get('textbook'), 500)}",
        f"上課時間: {_clean_text(indexed.get('class_time'))}",
        f"修課資格摘要: {eligibility_summary.get('summary') or ''}",
    ]

    if eligibility:
        raw_conditions = _normalize_list(eligibility.get("raw_conditions"))
        if raw_conditions:
            lines.append(f"修課資格原文: {'；'.join(raw_conditions[:3])}")
        unparseable = _normalize_list(eligibility.get("unparseable_conditions"))
        if unparseable:
            lines.append(f"資格解析警示: {'；'.join(unparseable[:3])}")

    metadata = {
        "語言": _normalize_list(indexed.get("languages")),
        "工具": _normalize_list(indexed.get("tools")),
        "概念": _normalize_list(indexed.get("concepts")),
        "簡化概念": _normalize_list(indexed.get("simplified_concepts")),
        "主題": _normalize_list(indexed.get("topic_tags")),
        "領域": _normalize_list(indexed.get("domain_tags")),
        "核心問題": _normalize_list(indexed.get("core_questions")),
    }
    for label, values in metadata.items():
        if values:
            lines.append(f"{label}: {'、'.join(values[:12])}")

    return "\n".join(line for line in lines if line.strip()), warnings


def answer_course_question(course_id: str, question: str) -> dict[str, Any]:
    if not question.strip():
        raise ValueError("Question is empty")

    context, warnings = build_course_context(course_id)
    # 對話依 AI_PROVIDER 切換；embedding（_embed_query）一律維持 _get_ai_client() 的 Azure／OpenAI
    client = get_chat_client(_get_ai_client)
    model = get_chat_model_name(_chat_model_name)

    response = client.chat.completions.create(
        model=model,
        temperature=0.2,
        max_completion_tokens=800,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是中央大學課程資訊頁中的單門課程助理。"
                    "只能根據提供的課程脈絡回答；若資料不足，請明確說明不足之處。"
                    "請使用繁體中文，回答要精簡、可操作，且不要聲稱已查詢未提供的外部資料。"
                ),
            },
            {
                "role": "user",
                "content": f"課程脈絡：\n{context}\n\n學生問題：\n{question.strip()}",
            },
        ],
    )

    answer = response.choices[0].message.content or ""
    return {
        "answer": answer.strip(),
        "model": model,
        "warnings": warnings,
    }
