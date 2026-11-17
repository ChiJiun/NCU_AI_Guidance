"""
build_graph.py — NCU 知識圖譜統一建置腳本

整合原本三支腳本的全部功能：
  build_knowledge_graph.py  → Phase 1：基礎圖結構
  merge_nlp_to_graph.py     → Phase 2：NLP 豐富化（Field / TAGGED_AS）
  enrich_graph_v2.py        → Phase 2+：全面豐富化（Technology / Concept / PREREQUISITE_OF...）

用法：
  python scripts/graph/build_graph.py              # 完整流程（建圖 → 豐富化）
  python scripts/graph/build_graph.py --build-only  # 只建基礎圖，跳過豐富化
  python scripts/graph/build_graph.py --enrich-only # 只豐富化現有圖

輸出：
  data/processed/graph/knowledge_graph.gpickle
  data/processed/graph/knowledge_graph.json
  data/processed/graph/knowledge_graph_stats.json
"""

import argparse
import csv
import json
import os
import pickle
import re
from collections import Counter
from pathlib import Path
from typing import Optional

try:
    import networkx as nx
except ImportError:
    raise ImportError("pip install networkx")

# ══════════════════════════════════════════════════════════════════════════════
# 1.  路徑設定
# ══════════════════════════════════════════════════════════════════════════════

BASE = Path(__file__).parent.parent.parent

# 輸入
CURRICULUM_PATH = BASE / "data" / "processed" / "curriculum_requirements_114.json"
CP_DIR          = BASE / "data" / "processed" / "credit_programs"
RAW_COURSE_DIRS = [
    (BASE / "data" / "raw" / "courses",          "ugrad"),
    (BASE / "data" / "raw" / "graduate_courses", "grad"),
]
SCRAPED_PATH    = BASE / "data" / "raw" / "scraped_missing" / "courses.json"
# 原始課程學期清單，可用環境變數 NCU_DATA_TERMS 覆寫（例如 "115_1,115_2"）
RAW_TERMS       = [t.strip() for t in os.environ.get("NCU_DATA_TERMS", "114_1,114_2").split(",") if t.strip()]

NLP_DIR         = BASE / "data" / "processed" / "nlp"
ELIGIBILITY     = BASE / "data" / "processed" / "course_eligibility.json"
SCHEDULE_DIR    = BASE / "data" / "processed" / "schedule_draft"
TEACHER_CSV     = BASE / "data" / "raw" / "114_ulistteacher.csv"

# 輸出
GRAPH_PKL   = BASE / "data" / "processed" / "graph" / "knowledge_graph.gpickle"
GRAPH_JSON  = BASE / "data" / "processed" / "graph" / "knowledge_graph.json"
GRAPH_STATS = BASE / "data" / "processed" / "graph" / "knowledge_graph_stats.json"

# ══════════════════════════════════════════════════════════════════════════════
# 2.  節點 / 邊 類型說明（文件用途）
# ══════════════════════════════════════════════════════════════════════════════

NODE_TYPES = {
    # 機構結構
    "University":             "大學（最高層）",
    "College":                "學院",
    "Department":             "系所",
    "DeptGroup":              "系內分組",
    "CollegeBachelorProgram": "學院學士班",
    "SpecializationTrack":    "專長分流",
    "CurriculumPlan":         "課程計畫",
    "ElectiveGroup":          "選修群",
    "Slot":                   "等效課程群",
    "GraduationRule":         "畢業規定",
    "CreditProgram":          "學分學程",
    "Certification":          "證照／認證",
    # 課程語意
    "Course":                 "課程",
    "Instructor":             "授課教師",
    "Domain":                 "課程領域",
    "Competency":             "核心能力",
    # NLP 補充
    "Field":                  "學術研究領域（教師專長）",
    "Technology":             "程式語言 / 框架 / 工具",
    "Concept":                "學術概念",
}

EDGE_TYPES = {
    # 機構結構
    "HAS_COLLEGE": "設有學院", "HAS_DEPARTMENT": "下設系所",
    "HAS_CBP": "開設學院學士班", "HAS_GROUP": "包含系內分組",
    "HAS_TRACK": "包含專長分流", "HAS_CURRICULUM": "制定課程計畫",
    "HAS_ELECTIVE_GROUP": "包含選修群", "HAS_SLOT": "包含等效課程群",
    "HAS_CREDIT_PROGRAM": "開設學分學程",
    # 課程要求
    "REQUIRES": "規定必修", "OFFERS_ELECTIVE": "提供選修",
    "GOVERNED_BY": "受畢業規定約束", "REQUIRES_CERTIFICATION": "要求取得證照",
    # 學分學程
    "PROGRAM_REQUIRES": "學程必修", "REQUIRES_SLOT": "學程必修（等效選一）",
    "PROGRAM_OFFERS": "學程提供選修群",
    "REQUIRES_PROGRAM": "畢業須完成學程", "PROGRAM_CHOICE": "畢業擇一完成學程",
    "PROGRAM_ELECTIVE": "建議選修學程",
    # 課程基本語意
    "TAUGHT_BY": "由教師授課", "IN_DOMAIN": "屬於課程領域", "DEVELOPS": "培養核心能力",
    # NLP 補充
    "COVERS_FIELD": "課程涵蓋研究領域", "RELEVANT_EXPERT": "教師為領域專家",
    "EXPERT_IN": "教師官方專長", "TAGGED_AS": "通識主題標籤",
    "TEACHES": "課程使用此技術", "COVERS": "課程涵蓋此概念",
    "COURSE_EXPERT": "教師專長與此課程領域相關（NLP 分析）",
    # 先修關係
    "PREREQUISITE_OF": "為…的先修", "COREQUISITE": "同修",
    # 語意同義
    "SIMILAR_TO": "語意相近（字串相似度）",
}

# ══════════════════════════════════════════════════════════════════════════════
# 3.  共用工具函式
# ══════════════════════════════════════════════════════════════════════════════

def load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def strip_section(code: str) -> str:
    return re.sub(r"-[A-Z0-9*]+$", "", code.strip())


def ensure_node(G: nx.DiGraph, nid: str, **attrs) -> bool:
    """若節點不存在則新增，回傳是否為新增。"""
    if not G.has_node(nid):
        G.add_node(nid, **attrs)
        return True
    return False


def ensure_edge(G: nx.DiGraph, src: str, tgt: str, **attrs) -> bool:
    """若邊不存在則新增，回傳是否為新增。"""
    if not G.has_edge(src, tgt):
        G.add_edge(src, tgt, **attrs)
        return True
    return False


def parse_when(when_str: str) -> tuple[Optional[int], Optional[int]]:
    """'大二下' → (2, 2)；解析失敗回傳 (None, None)。取範圍起始段。"""
    year_map = {"一": 1, "二": 2, "三": 3, "四": 4}
    sem_map  = {"上": 1, "下": 2}
    first = when_str.split("~")[0].strip()
    m = re.search(r"大([一二三四])([上下])?", first)
    if not m:
        return None, None
    return year_map.get(m.group(1)), sem_map.get(m.group(2)) if m.group(2) else None


def parse_when_range(when_str: str) -> tuple[int, int, int, int]:
    """'大三上~大三下' → (3, 1, 3, 2)；解析失敗各欄位為 0。"""
    year_map = {"一": 1, "二": 2, "三": 3, "四": 4}
    sem_map  = {"上": 1, "下": 2}

    def _single(token: str) -> tuple[Optional[int], Optional[int]]:
        m = re.search(r"大([一二三四])([上下])?", token.strip())
        if not m:
            return None, None
        return year_map.get(m.group(1)), sem_map.get(m.group(2)) if m.group(2) else None

    parts = [p.strip() for p in when_str.split("~")]
    y_s, s_s = _single(parts[0])
    if y_s is None:
        return 0, 0, 0, 0
    y_e, s_e = (_single(parts[1]) if len(parts) > 1 else (y_s, s_s))
    if y_e is None:
        y_e, s_e = y_s, s_s
    return y_s, (s_s or 1), y_e, (s_e or 2)


# ══════════════════════════════════════════════════════════════════════════════
# 4.  Phase 1：基礎圖建置
#     （原 build_knowledge_graph.py 的全部邏輯）
# ══════════════════════════════════════════════════════════════════════════════

def _parse_level_str(s: str) -> tuple[int, str]:
    """'(4) 高' → (4, '高')；無法解析回傳 (0, original)。"""
    m = re.search(r'\((\d)\)\s*(.+)', (s or "").strip())
    return (int(m.group(1)), m.group(2).strip()) if m else (0, (s or "").strip())


def _load_raw_courses() -> dict:
    """回傳 code → {name, credits, dept, college, level, semester, instructors, domains, competencies}
    competencies 格式：[{name, level_num, level_label}]
    """
    raw: dict = {}

    def register(c: dict, level: str, source: str):
        code = strip_section(c.get("課號-班別", ""))
        if not code:
            return
        name = c.get("課程名稱(中文)", "").strip()
        try:
            credits = int(c.get("學分", 0))
        except (ValueError, TypeError):
            credits = 0

        outline = c.get("課程綱要", {}) or {}
        domain_raw = outline.get("課程領域", "") or c.get("課程領域", "") or ""
        domains = [p.strip() for p in re.split(r"[、,，]+", domain_raw) if p.strip()]
        competencies = []
        for a in (outline.get("核心能力") or []):
            cname = a.get("能力名稱", "").strip()
            if not cname:
                continue
            level_num, level_label = _parse_level_str(a.get("強度指數", ""))
            competencies.append({"name": cname, "level_num": level_num, "level_label": level_label})
        instructors = [
            t.strip() for t in re.split(r"[\n,、；;]", c.get("授課教師", "") or "")
            if t.strip()
        ]
        if code in raw:
            if raw[code]["semester"] != source:
                raw[code]["semester"] = "both"
            return
        raw[code] = {
            "name": name, "credits": credits,
            "dept": c.get("系所", ""), "college": c.get("學院", ""),
            "level": level, "semester": source,
            "instructors": instructors, "domains": domains,
            "competencies": competencies, "source": "raw",
        }

    for raw_dir, level in RAW_COURSE_DIRS:
        for sem in RAW_TERMS:
            d = raw_dir / sem
            if not d.exists():
                continue
            for f in d.glob("*.json"):
                for c in load_json(f):
                    register(c, level, sem)

    if SCRAPED_PATH.exists():
        for c in load_json(SCRAPED_PATH):
            if c.get("_not_found") or c.get("_error"):
                continue
            m = re.search(r"(\d+)", strip_section(c.get("課號-班別", "")))
            lvl = "grad" if m and int(m.group(1)) >= 5000 else "ugrad"
            register(c, lvl, "scraped")

    return raw


def _ensure_course(G, raw, code, fallback_name="", fallback_credits=0, stub_source="cp_only"):
    if G.has_node(code):
        return code
    if code in raw:
        r = raw[code]
        G.add_node(code, node_type="Course",
                   name=r["name"], credits=r["credits"],
                   dept=r["dept"], college=r["college"],
                   level=r["level"], semester=r["semester"],
                   domains=r["domains"], source="raw")
    else:
        G.add_node(code, node_type="Course",
                   name=fallback_name, credits=fallback_credits,
                   source=stub_source, level="unknown")
    return code


def _add_courses(G, raw, courses, owner_id, rel="REQUIRES", stub="curriculum_only"):
    for c in courses:
        if not isinstance(c, dict) or not c.get("code"):
            continue
        _ensure_course(G, raw, c["code"], c.get("name", ""), c.get("credits", 0), stub)
        when_raw = c.get("when", "")
        if when_raw and rel == "REQUIRES":
            y_s, s_s, y_e, s_e = parse_when_range(when_raw)
            ensure_edge(G, owner_id, c["code"], relation=rel, credits=c.get("credits", 0),
                        when_raw=when_raw,
                        when_year_start=y_s, when_sem_start=s_s,
                        when_year_end=y_e,   when_sem_end=s_e)
        else:
            ensure_edge(G, owner_id, c["code"], relation=rel, credits=c.get("credits", 0))


def _add_slot(G, raw, slot, parent_id, idx, stub="cp_only"):
    sid = f"{parent_id}__slot{idx}__{slot.get('slot_id', idx)}"
    G.add_node(sid, node_type="Slot",
               name=slot.get("slot_name", f"Slot {idx}"),
               select=slot.get("select", 1),
               slot_rule=slot.get("slot_rule", ""))
    G.add_edge(parent_id, sid, relation="HAS_SLOT")
    for c in slot.get("courses", []):
        if not c.get("code"):
            continue
        _ensure_course(G, raw, c["code"], c.get("name", ""), c.get("credits", 0), stub)
        ensure_edge(G, sid, c["code"], relation="OFFERS_ELECTIVE")
    return sid


def _add_eg(G, raw, grp, owner_id, idx, stub="curriculum_only"):
    eid = f"{owner_id}__eg{idx}"
    G.add_node(eid, node_type="ElectiveGroup",
               name=grp.get("name", f"選修群{idx}"),
               select=grp.get("select"), select_credits=grp.get("select_credits"),
               group_rule=grp.get("group_rule", ""))
    G.add_edge(owner_id, eid, relation="HAS_ELECTIVE_GROUP")
    for key in ("courses", "option_a", "option_b", "option_c"):
        _add_courses(G, raw, grp.get(key, []), eid, "OFFERS_ELECTIVE", stub)
    for si, slot in enumerate(grp.get("slots", [])):
        _add_slot(G, raw, slot, eid, si, stub)
    return eid


def _add_rules(G, rules, owner_id, raw=None, plan_id=None):
    """
    建立 GraduationRule 節點。
    若規則含 course_codes（如 design_course_min），額外建 ElectiveGroup 並連課程。
    raw / plan_id 在有 course_codes 時必須提供。
    """
    for i, r in enumerate(rules):
        rid = f"{owner_id}__rule{i}"
        G.add_node(rid, node_type="GraduationRule",
                   **{k: v for k, v in r.items() if isinstance(v, (str, int, float, bool))})
        G.add_edge(owner_id, rid, relation="GOVERNED_BY")
        # 若規則帶 course_codes，建對應的 ElectiveGroup 讓課程可被查詢
        codes = r.get("course_codes", [])
        if codes and raw is not None and plan_id is not None:
            eg_id = f"{rid}__eg"
            G.add_node(eg_id, node_type="ElectiveGroup",
                       name=r.get("description", f"規定課程群{i}"),
                       select=r.get("select", 1),
                       group_rule=r.get("type", ""))
            G.add_edge(plan_id, eg_id, relation="HAS_ELECTIVE_GROUP")
            for code in codes:
                info = (raw or {}).get(code, {})
                _ensure_course(G, raw, code,
                               fallback_name=info.get("name", ""),
                               fallback_credits=info.get("credits", 0),
                               stub_source="curriculum_only")
                ensure_edge(G, eg_id, code, relation="OFFERS_ELECTIVE")


def _add_certs(G, certs, owner_id):
    for cert in certs:
        cid = f"cert::{cert}"
        ensure_node(G, cid, node_type="Certification", name=cert)
        G.add_edge(owner_id, cid, relation="REQUIRES_CERTIFICATION")


def _make_plan(G, plan_id, name, req_credits=0):
    G.add_node(plan_id, node_type="CurriculumPlan", name=name, required_credits=req_credits)
    return plan_id


def _process_dept_group(G, raw, grp, parent_id, rel="HAS_GROUP"):
    gid = grp["id"]
    G.add_node(gid, node_type="DeptGroup", name=grp["name"],
               group_label=grp.get("group_label", ""),
               min_credits=grp.get("min_credits", 0))
    G.add_edge(parent_id, gid, relation=rel)
    _add_certs(G, grp.get("certifications", []), gid)
    pid = _make_plan(G, f"{gid}::plan", f"{grp['name']}課程計畫",
                     grp.get("group_required_credits", grp.get("required_credits", 0)))
    G.add_edge(gid, pid, relation="HAS_CURRICULUM")
    _add_rules(G, grp.get("graduation_rules", []), gid, raw=raw, plan_id=pid)
    for key in ("required_courses", "cross_group_required",
                "college_required_courses", "common_required_courses",
                "dept_required_courses", "required_electives",
                "cross_domain_required", "earth_system_courses", "application_courses"):
        _add_courses(G, raw, grp.get(key, []), pid, "REQUIRES")
    for key in ("first_domain_electives", "elective_courses"):
        _add_courses(G, raw, grp.get(key, []), pid, "OFFERS_ELECTIVE")
    for i, eg in enumerate(grp.get("elective_groups", [])):
        _add_eg(G, raw, eg, pid, i)
    for i, eg in enumerate(grp.get("core_elective_groups", [])):
        _add_eg(G, raw, eg, pid, 100 + i)
    for i, eg in enumerate(grp.get("college_required_elective_groups", [])):
        _add_eg(G, raw, eg, pid, 200 + i)
    for i, eg in enumerate(grp.get("science_ability_groups", [])):
        _add_eg(G, raw, eg, pid, 300 + i)
    for i, eg in enumerate(grp.get("other_elective_groups", [])):
        _add_eg(G, raw, eg, pid, 400 + i)
    for sub in grp.get("groups", []):
        _process_dept_group(G, raw, sub, gid)


def _process_dept(G, raw, dept, college_id):
    did = dept["id"]
    G.add_node(did, node_type="Department", name=dept["name"],
               program_type=dept.get("program_type", "traditional_dept"),
               min_credits=dept.get("min_credits", 0))
    G.add_edge(college_id, did, relation="HAS_DEPARTMENT")
    _add_certs(G, dept.get("certifications", []), did)
    pid = _make_plan(G, f"{did}::plan", f"{dept['name']}課程計畫",
                     dept.get("required_credits", 0))
    G.add_edge(did, pid, relation="HAS_CURRICULUM")
    _add_rules(G, dept.get("graduation_rules", []), did, raw=raw, plan_id=pid)
    for key in ("required_courses", "required_electives", "college_required_courses",
                "dept_required_courses", "foundation_courses", "common_required_courses",
                "cross_domain_required", "earth_system_courses",
                "cross_group_required", "application_courses"):
        _add_courses(G, raw, dept.get(key, []), pid, "REQUIRES")
    for key in ("first_domain_electives", "elective_courses"):
        _add_courses(G, raw, dept.get(key, []), pid, "OFFERS_ELECTIVE")
    for i, eg in enumerate(dept.get("elective_groups", [])):
        _add_eg(G, raw, eg, pid, i)
    for i, eg in enumerate(dept.get("core_elective_groups", [])):
        _add_eg(G, raw, eg, pid, 100 + i)
    for i, eg in enumerate(dept.get("college_required_elective_groups", [])):
        _add_eg(G, raw, eg, pid, 200 + i)
    for i, eg in enumerate(dept.get("science_ability_groups", [])):
        _add_eg(G, raw, eg, pid, 300 + i)
    for i, eg in enumerate(dept.get("other_elective_groups", [])):
        _add_eg(G, raw, eg, pid, 400 + i)
    # dept_with_groups 的系訂必修也需掛到各 group 底下（透過 dept_required_courses 已加在 plan 上）
    if dept.get("program_type") == "dept_with_groups":
        for grp in dept.get("groups", []):
            _process_dept_group(G, raw, grp, did)
    for track in dept.get("tracks", []):
        _process_dept_group(G, raw, {
            "id": track["id"], "name": track["name"],
            "group_label": track.get("group_label", track["name"]),
            "required_courses": track.get("required_courses", []),
            "elective_groups": track.get("elective_groups", []),
            "graduation_rules": track.get("graduation_rules", []),
        }, did, "HAS_TRACK")


def _process_track(G, raw, track, parent_id, rel="HAS_TRACK"):
    tid = track["id"]
    G.add_node(tid, node_type="SpecializationTrack", name=track["name"],
               min_credits=track.get("min_credits", 0))
    G.add_edge(parent_id, tid, relation=rel)
    pid = _make_plan(G, f"{tid}::plan", f"{track['name']}課程計畫")
    G.add_edge(tid, pid, relation="HAS_CURRICULUM")
    _add_rules(G, track.get("graduation_rules", []), tid, raw=raw, plan_id=pid)
    for key in ("required_courses", "foundation_courses", "college_required_courses",
                "common_required_courses", "cross_domain_required", "cross_group_required"):
        _add_courses(G, raw, track.get(key, []), pid, "REQUIRES")
    _add_courses(G, raw, track.get("elective_courses", []), pid, "OFFERS_ELECTIVE")
    for i, eg in enumerate(track.get("elective_groups", [])):
        _add_eg(G, raw, eg, pid, i)
    for sub in track.get("groups", []):
        sub_id = sub["id"]
        G.add_node(sub_id, node_type="SpecializationTrack", name=sub["name"], parent_track=tid)
        G.add_edge(tid, sub_id, relation="HAS_TRACK")
        sp = _make_plan(G, f"{sub_id}::plan", f"{sub['name']}課程計畫")
        G.add_edge(sub_id, sp, relation="HAS_CURRICULUM")
        _add_rules(G, sub.get("graduation_rules", []), sub_id, raw=raw, plan_id=sp)
        for key in ("required_courses", "foundation_courses", "college_required_courses",
                    "common_required_courses", "cross_domain_required"):
            _add_courses(G, raw, sub.get(key, []), sp, "REQUIRES")
        _add_courses(G, raw, sub.get("elective_courses", []), sp, "OFFERS_ELECTIVE")
        for i, eg in enumerate(sub.get("elective_groups", [])):
            _add_eg(G, raw, eg, sp, i)


def _process_cbp(G, raw, cbp, college_id):
    cid = cbp["id"]
    G.add_node(cid, node_type="CollegeBachelorProgram", name=cbp["name"],
               min_credits=cbp.get("min_credits", 0))
    G.add_edge(college_id, cid, relation="HAS_CBP")
    mp = f"{cid}::base_plan"
    _make_plan(G, mp, f"{cbp['name']}基礎課程計畫")
    G.add_edge(cid, mp, relation="HAS_CURRICULUM")
    _add_rules(G, cbp.get("graduation_rules", []), cid, raw=raw, plan_id=mp)
    for key in ("required_courses", "foundation_courses", "application_courses",
                "earth_system_courses", "cross_domain_required"):
        _add_courses(G, raw, cbp.get(key, []), mp, "REQUIRES")
    # science_ability_groups（地科院）：每個 group 視為一個 ElectiveGroup
    for i, sg in enumerate(cbp.get("science_ability_groups", [])):
        _add_eg(G, raw, sg, mp, 200 + i)
    for i, eg in enumerate(cbp.get("elective_groups", [])):
        _add_eg(G, raw, eg, mp, i)
    for i, eg in enumerate(cbp.get("college_required_elective_groups", [])):
        _add_eg(G, raw, eg, mp, 100 + i)
    for i, eg in enumerate(cbp.get("other_elective_groups", [])):
        _add_eg(G, raw, eg, mp, 300 + i)
    for track in cbp.get("specialization_tracks", []):
        _process_track(G, raw, track, cid)
    for track in cbp.get("tracks", []):
        _process_dept_group(G, raw, {
            "id": track["id"], "name": track["name"],
            "group_label": track.get("name", ""),
            "required_courses": track.get("required_courses", []),
            "elective_groups": track.get("elective_groups", []),
            "graduation_rules": track.get("graduation_rules", []),
        }, cid, "HAS_TRACK")


_COLLEGE_NAME_TO_ID = {
    "文學院":       "college_liberal_arts",
    "理學院":       "college_science",
    "工學院":       "college_engineering",
    "管理學院":     "college_management",
    "客家學院":     "college_hakka",
    "地球科學學院": "college_earth_sciences",
    "資訊電機學院": "college_electrical_engineering",
    "生醫理工學院": "college_biomedical_engineering",
}

_PROGRAM_NAME_TO_ID = {
    "創意與創業":         "cp::creativity_entrepreneurship",
    "地球科學資訊":       "cp::geoscience_informatics",
    "氣候與環境變遷":     "cp::climate_environmental_change",
    "企業資源規劃":       "cp::erp",
    "商業智慧與分析":     "cp::business_intelligence_analytics",
    "跨領域社會參與":     "cp::interdisciplinary_social_engagement",
    "社會企業與社會創新": "cp::social_enterprise_innovation",
    "社會企業":           "cp::social_enterprise",
}


def _match_program_id(text: str) -> Optional[str]:
    for kw, pid in _PROGRAM_NAME_TO_ID.items():
        if kw in text:
            return pid
    return None


def build_base_graph(raw: dict) -> nx.DiGraph:
    G = nx.DiGraph()
    data = load_json(CURRICULUM_PATH)

    # University → College → Department/CBP
    print("  [1/4] curriculum_requirements（系所結構）...")
    uni_id = "NCU"
    G.add_node(uni_id, node_type="University",
               name=data["metadata"]["university"],
               academic_year=data["metadata"]["academic_year"])
    for college in data["colleges"]:
        col_id = college["id"]
        G.add_node(col_id, node_type="College", name=college["name"])
        G.add_edge(uni_id, col_id, relation="HAS_COLLEGE")
        if college.get("college_required_courses"):
            common_id = f"{col_id}::common"
            _make_plan(G, common_id, f"{college['name']}院訂必修")
            G.add_edge(col_id, common_id, relation="HAS_CURRICULUM")
            _add_courses(G, raw, college["college_required_courses"], common_id, "REQUIRES")
            for i, eg in enumerate(college.get("college_required_elective_groups", [])):
                _add_eg(G, raw, eg, common_id, i)
        if college.get("college_elective_courses"):
            elective_id = f"{col_id}::elective"
            G.add_node(elective_id, node_type="CurriculumPlan",
                       name=f"{college['name']}院訂必選")
            G.add_edge(col_id, elective_id, relation="HAS_CURRICULUM")
            _add_courses(G, raw, college["college_elective_courses"], elective_id, "OFFERS_ELECTIVE")
        for dept in college.get("departments", []):
            _process_dept(G, raw, dept, col_id)
        for cbp in college.get("college_bachelor_programs", []):
            _process_cbp(G, raw, cbp, col_id)

    # [1.5/4] 確保所有 raw 課程節點存在（含通識選修、聯盟課程等未在課程結構中的課）
    print("  [1.5/4] raw 課程節點補建...")
    for code, r in raw.items():
        if not G.has_node(code):
            G.add_node(code, node_type="Course",
                       name=r["name"], credits=r["credits"],
                       dept=r["dept"], college=r["college"],
                       level=r["level"], semester=r["semester"],
                       domains=r["domains"], source="raw")

    # Instructor / Domain / Competency
    print("  [2/4] Instructor / Domain / Competency 節點...")
    for code, r in raw.items():
        for name in r.get("instructors", []):
            iid = f"instructor::{name}"
            ensure_node(G, iid, node_type="Instructor", name=name)
            ensure_edge(G, code, iid, relation="TAUGHT_BY")
        for domain in r.get("domains", []):
            did = f"domain::{domain}"
            ensure_node(G, did, node_type="Domain", name=domain)
            ensure_edge(G, code, did, relation="IN_DOMAIN")
        for comp in r.get("competencies", []):
            # 向後相容：comp 可能是舊格式 str 或新格式 {name, level_num, level_label}
            if isinstance(comp, dict):
                cname, level_num, level_label = comp["name"], comp.get("level_num", 0), comp.get("level_label", "")
            else:
                cname, level_num, level_label = comp, 0, ""
            cid = f"competency::{cname}"
            ensure_node(G, cid, node_type="Competency", name=cname)
            ensure_edge(G, code, cid, relation="DEVELOPS",
                        level_num=level_num, level_label=level_label)

    # Credit programs
    print("  [3/4] 學分學程...")
    for f in sorted(CP_DIR.glob("*.json")):
        for prog in load_json(f):
            pid = f"cp::{prog['id']}"
            G.add_node(pid, node_type="CreditProgram",
                       name=prog.get("name", ""), college=prog.get("college", ""),
                       min_credits=prog.get("min_credits", 0),
                       cross_school=prog.get("cross_school", False))
            col_node = _COLLEGE_NAME_TO_ID.get(prog.get("college", ""), "")
            if col_node and G.has_node(col_node):
                G.add_edge(col_node, pid, relation="HAS_CREDIT_PROGRAM")
            for c in prog.get("required_courses", []):
                if not c.get("code"):
                    continue
                _ensure_course(G, raw, c["code"], c.get("name", ""), c.get("credits", 0), "cp_only")
                ensure_edge(G, pid, c["code"], relation="PROGRAM_REQUIRES", credits=c.get("credits", 0))
            for si, slot in enumerate(prog.get("required_slots", [])):
                slot_id = _add_slot(G, raw, slot, pid, si, "cp_only")
                G.edges[pid, slot_id]["relation"] = "REQUIRES_SLOT"
            for i, grp in enumerate(prog.get("elective_groups", [])):
                eid = f"{pid}__eg{i}"
                G.add_node(eid, node_type="ElectiveGroup",
                           name=grp.get("name", f"選修群{i}"),
                           select=grp.get("select"),
                           select_credits=grp.get("select_credits"),
                           group_rule=grp.get("group_rule", ""))
                G.add_edge(pid, eid, relation="PROGRAM_OFFERS")
                for c in grp.get("courses", []):
                    if not c.get("code"):
                        continue
                    _ensure_course(G, raw, c["code"], c.get("name", ""), c.get("credits", 0), "cp_only")
                    ensure_edge(G, eid, c["code"], relation="OFFERS_ELECTIVE")
                for si2, slot in enumerate(grp.get("slots", [])):
                    _add_slot(G, raw, slot, eid, si2, "cp_only")

    # 畢業必修學程邊
    print("  [4/4] 畢業必修學程邊...")
    added = 0

    def _scan_program_rules(obj, owner_id):
        nonlocal added
        if not isinstance(obj, dict):
            return
        nid = obj.get("id", owner_id)
        for rule in obj.get("graduation_rules", []):
            rtype, desc = rule.get("type", ""), rule.get("description", "")
            if rtype == "special_requirement":
                mp = _match_program_id(desc)
                if mp and G.has_node(nid) and G.has_node(mp):
                    if ensure_edge(G, nid, mp, relation="REQUIRES_PROGRAM", description=desc):
                        added += 1
            elif rtype == "program_choice":
                sel = rule.get("select", 1)
                for opt in rule.get("options", []):
                    mp = _match_program_id(opt.get("name", ""))
                    if mp and G.has_node(nid) and G.has_node(mp):
                        if ensure_edge(G, nid, mp, relation="PROGRAM_CHOICE", select=sel,
                                       min_credits=opt.get("credits", opt.get("credits_min", 0))):
                            added += 1
            elif rtype == "special_requirement_one_of":
                for mp in [_match_program_id(p) for p in desc.split("(") if _match_program_id(p)]:
                    if G.has_node(nid) and G.has_node(mp):
                        if ensure_edge(G, nid, mp, relation="PROGRAM_CHOICE", select=1, description=desc):
                            added += 1
            elif rtype == "program_elective":
                for kw, mp in _PROGRAM_NAME_TO_ID.items():
                    if kw in desc and G.has_node(nid) and G.has_node(mp):
                        if ensure_edge(G, nid, mp, relation="PROGRAM_ELECTIVE", description=desc):
                            added += 1
        for key in ("departments", "college_bachelor_programs",
                    "groups", "tracks", "specialization_tracks"):
            for child in obj.get(key, []):
                _scan_program_rules(child, child.get("id", owner_id))

    for college in data["colleges"]:
        _scan_program_rules(college, college["id"])
    print(f"      → 新增 {added} 條學程邊")

    return G


# ══════════════════════════════════════════════════════════════════════════════
# 5.  Phase 2：NLP + 語意豐富化
#     （原 merge_nlp_to_graph.py + enrich_graph_v2.py 的全部邏輯）
# ══════════════════════════════════════════════════════════════════════════════

def _find_course(G: nx.DiGraph, code: str) -> Optional[str]:
    """嘗試各種格式找到課程節點 ID。"""
    if G.has_node(code):
        return code
    for prefix in (f"course::{code}", f"Course::{code}"):
        if G.has_node(prefix):
            return prefix
    return None


def _find_instructor(G: nx.DiGraph, name: str) -> Optional[str]:
    iid = f"instructor::{name}"
    if G.has_node(iid):
        return iid
    for nid, attrs in G.nodes(data=True):
        if attrs.get("node_type") in ("Instructor", "instructor") and attrs.get("name") == name:
            return nid
    return None


def enrich_nlp(G: nx.DiGraph) -> dict:
    """
    Phase 2a：NLP 六支檔案豐富化
      - Field 節點 + COVERS_FIELD + RELEVANT_EXPERT（from nlp_domain_tags + dept_professor_map）
      - TAGGED_AS + core_questions（from nlp_topic_tags）
      - Technology/Concept 節點 + TEACHES/COVERS（from nlp_tech_nodes）
    """
    stats = {k: 0 for k in ("field_nodes", "covers_field", "relevant_expert",
                              "tagged_as", "core_q_updated",
                              "tech_nodes", "concept_nodes", "teaches", "covers")}

    # ── Field + COVERS_FIELD ─────────────────────────────────────────────────
    domain_path = NLP_DIR / "nlp_domain_tags.json"
    dept_map_path = NLP_DIR / "dept_professor_map.json"

    if domain_path.exists():
        domain_tags = load_json(domain_path)
        dept_map = load_json(dept_map_path) if dept_map_path.exists() else {}

        # 收集全部 field 名稱
        all_fields: set[str] = set()
        for data in domain_tags.values():
            for tag in data.get("domain_tags", []):
                if isinstance(tag, dict) and tag.get("field"):
                    all_fields.add(tag["field"])
        for dept_data in dept_map.values():
            for prof in dept_data.get("professors", []):
                for spec in prof.get("specialties", []):
                    all_fields.add(spec)

        for field in all_fields:
            if ensure_node(G, f"field::{field}", node_type="Field", name=field, source="nlp"):
                stats["field_nodes"] += 1

        for code, data in domain_tags.items():
            if data.get("skipped"):
                continue
            cnid = _find_course(G, code)
            if not cnid:
                continue
            for tag in data.get("domain_tags", []):
                if not isinstance(tag, dict):
                    continue
                field = tag.get("field", "").strip()
                if not field:
                    continue
                fid = f"field::{field}"
                if G.has_node(fid) and ensure_edge(G, cnid, fid, relation="COVERS_FIELD",
                                                    relevance=tag.get("relevance", "medium"),
                                                    source="llm_agent2"):
                    stats["covers_field"] += 1

        # RELEVANT_EXPERT
        for dept, dept_data in dept_map.items():
            for prof in dept_data.get("professors", []):
                iid = _find_instructor(G, prof.get("name", ""))
                if not iid:
                    continue
                for spec in prof.get("specialties", []):
                    fid = f"field::{spec}"
                    if G.has_node(fid) and ensure_edge(G, iid, fid, relation="RELEVANT_EXPERT",
                                                        dept=dept, source="dept_map"):
                        stats["relevant_expert"] += 1

    # ── TAGGED_AS + core_questions ───────────────────────────────────────────
    topic_path = NLP_DIR / "nlp_topic_tags.json"
    if topic_path.exists():
        topic_tags = load_json(topic_path)
        KNOWN_TOPICS = {
            "哲學", "歷史", "文學", "語言學", "藝術", "音樂", "社會學", "心理學",
            "法律", "政治", "經濟", "物理", "化學", "生物", "環境科學", "數學",
            "資訊科技", "工程", "醫學", "倫理學", "性別研究", "族群文化",
            "全球化", "永續發展", "宗教",
        }
        topic_nid_map: dict[str, str] = {}
        for label in KNOWN_TOPICS:
            found = next(
                (nid for nid, a in G.nodes(data=True)
                 if a.get("node_type") in ("domain", "Domain") and a.get("name") == label),
                None,
            )
            if found:
                topic_nid_map[label] = found
            else:
                nid = f"domain::topic::{label}"
                ensure_node(G, nid, node_type="Domain", name=label, source="topic_tags")
                topic_nid_map[label] = nid

        for code, data in topic_tags.items():
            if data.get("skipped"):
                continue
            cnid = _find_course(G, code)
            if not cnid:
                continue
            cqs = data.get("core_questions", [])
            if cqs:
                G.nodes[cnid]["core_questions"] = cqs
                stats["core_q_updated"] += 1
            for tag in data.get("topic_tags", []):
                if tag in topic_nid_map and ensure_edge(G, cnid, topic_nid_map[tag],
                                                         relation="TAGGED_AS",
                                                         source="llm_agent3"):
                    stats["tagged_as"] += 1

    # ── Technology / Concept + TEACHES / COVERS ──────────────────────────────
    tech_path = NLP_DIR / "nlp_tech_nodes.json"
    if tech_path.exists():
        tech_nodes = load_json(tech_path)
        # lowercase → canonical node_id；防止大小寫不同產生重複節點
        _tech_norm_map: dict[str, str] = {}
        for code, data in tech_nodes.items():
            if not isinstance(data, dict):
                continue
            cnid = _find_course(G, code)
            if not cnid:
                continue
            for item in data.get("languages", []) + data.get("tools", []):
                item = item.strip()
                if not item:
                    continue
                norm_key = item.lower()
                if norm_key in _tech_norm_map:
                    tid = _tech_norm_map[norm_key]   # 重定向到已存在的正規節點
                else:
                    tid = f"tech::{item}"
                    if ensure_node(G, tid, node_type="Technology", name=item, source="nlp"):
                        stats["tech_nodes"] += 1
                    _tech_norm_map[norm_key] = tid
                if ensure_edge(G, cnid, tid, relation="TEACHES", source="nlp"):
                    stats["teaches"] += 1
            for concept in data.get("concepts", []):
                concept = concept.strip()
                if not concept:
                    continue
                cid = f"concept::{concept}"
                if ensure_node(G, cid, node_type="Concept", name=concept, source="nlp"):
                    stats["concept_nodes"] += 1
                if ensure_edge(G, cnid, cid, relation="COVERS", source="nlp"):
                    stats["covers"] += 1

    return stats


def enrich_eligibility(G: nx.DiGraph) -> dict:
    """
    Phase 2b：修課條件豐富化
      - PREREQUISITE_OF / COREQUISITE / CONFLICTS_WITH 邊
      - eligible_years / open_to_minor / open_to_double_major / is_unrestricted 節點屬性
    支援 v2 格式（eligibility/course_relations 巢狀）與舊格式（頂層扁平）。
    """
    stats = {
        "prereq": 0, "coreq": 0, "conflict": 0,
        "eligible_years_set": 0,
    }
    if not ELIGIBILITY.exists():
        return stats
    eligibility = load_json(ELIGIBILITY)
    if not isinstance(eligibility, list):
        return stats
    for entry in eligibility:
        code = entry.get("course_code", "").strip()
        cnid = _find_course(G, code)
        if not cnid:
            continue

        # 支援 v2 巢狀格式；fallback 讀頂層（舊格式向後相容）
        elig = entry.get("eligibility") or entry
        rels = entry.get("course_relations") or entry

        # ── 節點屬性 ──
        ey = elig.get("eligible_years", [])
        if ey:
            G.nodes[cnid]["eligible_years"] = ey
            stats["eligible_years_set"] += 1
        if elig.get("open_to_minor"):
            G.nodes[cnid]["open_to_minor"] = True
        if elig.get("open_to_double_major"):
            G.nodes[cnid]["open_to_double_major"] = True
        if elig.get("is_unrestricted"):
            G.nodes[cnid]["is_unrestricted"] = True

        # ── PREREQUISITE_OF 邊 ──
        for prereq_code in rels.get("prereq_codes", []):
            pnid = _find_course(G, prereq_code)
            if pnid and ensure_edge(G, pnid, cnid, relation="PREREQUISITE_OF", source="eligibility"):
                stats["prereq"] += 1

        # ── COREQUISITE 邊 ──
        for coreq_code in rels.get("coreq_codes", []):
            qnid = _find_course(G, coreq_code)
            if qnid and ensure_edge(G, cnid, qnid, relation="COREQUISITE", source="eligibility"):
                stats["coreq"] += 1

        # ── CONFLICTS_WITH 邊（擋修 + 禁修，無方向性，建雙向邊）──
        conflict_all = rels.get("conflict_codes", []) + rels.get("forbidden_codes", [])
        for cf_code in conflict_all:
            cnid2 = _find_course(G, cf_code)
            if cnid2:
                ensure_edge(G, cnid, cnid2, relation="CONFLICTS_WITH", source="eligibility")
                ensure_edge(G, cnid2, cnid, relation="CONFLICTS_WITH", source="eligibility")
                stats["conflict"] += 1

    return stats


def enrich_schedule(G: nx.DiGraph) -> dict:
    """Phase 2e：為 REQUIRES 邊補寫 when_raw / when_year_start 等屬性（from schedule_draft）。
    補充 _add_courses 未涵蓋的邊（如 build_base_graph 後才更新 schedule_draft 的情形）。
    """
    stats = {"updated": 0}
    if not SCHEDULE_DIR.exists():
        return stats

    def _apply(courses: list, plan_nid: str):
        for rc in courses:
            code = rc.get("code", "").strip()
            when = rc.get("when", "")
            if not code or not when:
                continue
            if not G.has_edge(plan_nid, code):
                continue
            # 只補寫尚未設定 when_raw 的邊（不覆蓋 _add_courses 已寫入的值）
            if G.edges[plan_nid, code].get("when_raw"):
                continue
            y_s, s_s, y_e, s_e = parse_when_range(when)
            G.edges[plan_nid, code]["when_raw"]        = when
            G.edges[plan_nid, code]["when_year_start"] = y_s
            G.edges[plan_nid, code]["when_sem_start"]  = s_s
            G.edges[plan_nid, code]["when_year_end"]   = y_e
            G.edges[plan_nid, code]["when_sem_end"]    = s_e
            stats["updated"] += 1

    for college_dir in SCHEDULE_DIR.iterdir():
        if not college_dir.is_dir():
            continue
        for dept_file in college_dir.glob("*.json"):
            try:
                data = load_json(dept_file)
                dept_id = data.get("id", dept_file.stem)
                plan_id = f"{dept_id}::plan"
                _apply(data.get("required_courses", []), plan_id)
                for track in data.get("specialization_tracks", []):
                    tid = track.get("id", dept_id)
                    _apply(track.get("required_courses", []), f"{tid}::plan")
                    for grp in track.get("groups", []):
                        gid = grp.get("id", tid)
                        _apply(grp.get("required_courses", []), f"{gid}::plan")
                for grp in data.get("groups", []):
                    gid = grp.get("id", dept_id)
                    _apply(grp.get("required_courses", []), f"{gid}::plan")
            except Exception as e:
                print(f"    [WARN] {dept_file.name}: {e}")
    return stats


def enrich_teacher_csv(G: nx.DiGraph) -> dict:
    """Phase 2a：教師節點全量建立 + 官方專長 + EXPERT_IN 邊（from 114_ulistteacher.csv）

    改版重點：
    - 若教師尚未在圖中（未出現在任何課程的授課欄位），直接建立新 Instructor 節點
    - 補充 dept / rank / employment 屬性
    - 建立 Instructor --[EXPERT_IN]--> Field 邊
    """
    stats = {"specs_updated": 0, "expert_in": 0, "new_field_nodes": 0, "new_instructors": 0}
    if not TEACHER_CSV.exists():
        return stats
    with open(TEACHER_CSV, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name     = row["教師名稱"].strip()
            spec_str = row["教師專長"].strip()
            dept     = row["系所名稱"].strip()
            rank     = row["聘書職級"].strip()
            employ   = row["專兼任"].strip()
            if not name:
                continue

            iid = _find_instructor(G, name)
            if not iid:
                # 建立新的 Instructor 節點（原本課程授課欄未收錄的教師）
                iid = f"instructor::{name}"
                G.add_node(iid, node_type="Instructor", name=name,
                           dept=dept, rank=rank, employment=employ)
                stats["new_instructors"] += 1
            else:
                # 補強現有節點屬性（課程授課欄只有名字，缺 dept/rank）
                G.nodes[iid].setdefault("dept",       dept)
                G.nodes[iid].setdefault("rank",       rank)
                G.nodes[iid].setdefault("employment", employ)

            if not spec_str:
                continue
            specs = [s.strip() for s in re.split(r"[,，、]", spec_str) if s.strip()]
            G.nodes[iid]["official_specialties"] = specs
            stats["specs_updated"] += 1
            for spec in specs:
                fid = f"field::{spec}"
                if not G.has_node(fid):
                    G.add_node(fid, node_type="Field", name=spec, source="teacher_csv")
                    stats["new_field_nodes"] += 1
                if ensure_edge(G, iid, fid, relation="EXPERT_IN", source="teacher_csv"):
                    stats["expert_in"] += 1
    return stats


def enrich_professor_links(G: nx.DiGraph) -> dict:
    """Phase 2b：nlp_professor_links.json 補充 COURSE_EXPERT 邊

    資料格式：course_code → [{field, professors: [name, ...], relevance}]
    為每個（教師, 課程）對建立 COURSE_EXPERT 邊，
    同時補強 Instructor --[RELEVANT_EXPERT]--> Field 邊（若該 Field 節點已存在）。
    需在 enrich_teacher_csv 之後執行，確保所有教師節點已存在。
    """
    stats = {"course_expert": 0, "relevant_expert_added": 0, "skipped_no_instructor": 0}
    prof_links_path = NLP_DIR / "nlp_professor_links.json"
    if not prof_links_path.exists():
        return stats

    prof_links = load_json(prof_links_path)
    for course_code, entries in prof_links.items():
        cnid = _find_course(G, course_code)
        if not cnid:
            continue
        for entry in entries:
            field     = entry.get("field", "").strip()
            relevance = entry.get("relevance", "medium")
            fid       = f"field::{field}"
            for prof_name in entry.get("professors", []):
                iid = _find_instructor(G, prof_name)
                if not iid:
                    stats["skipped_no_instructor"] += 1
                    continue
                # Instructor --[COURSE_EXPERT]--> Course
                if ensure_edge(G, iid, cnid, relation="COURSE_EXPERT",
                               field=field, relevance=relevance, source="nlp_prof_links"):
                    stats["course_expert"] += 1
                # Instructor --[RELEVANT_EXPERT]--> Field（若 Field 已建立）
                if G.has_node(fid):
                    if ensure_edge(G, iid, fid, relation="RELEVANT_EXPERT",
                                   source="nlp_prof_links"):
                        stats["relevant_expert_added"] += 1
    return stats


def enrich_concept_synonymy(G: nx.DiGraph) -> dict:
    """Phase 2-f：字串相似度建立 Concept / Technology 同義邊 SIMILAR_TO（雙向）。

    演算法：
    1. 建立字元反向索引 {char → {node_id}} 作為 blocking，減少 O(n²) 比對
    2. 候選對：共享字元 ≥ 2 個（中文字元只計非 ASCII）
    3. 用 difflib.SequenceMatcher 計算字串相似度
    4. 條件：ratio ≥ 0.70 且較長名稱 ≤ 2.5 倍較短名稱長度
    5. 建立雙向 SIMILAR_TO 邊，weight = ratio
    """
    from difflib import SequenceMatcher
    from collections import Counter as _Counter

    stats = {"similar_to": 0, "candidates_checked": 0}

    # 收集 Concept + Technology 節點（排除名稱過短者）
    sem_nodes = [
        (nid, data["name"])
        for nid, data in G.nodes(data=True)
        if data.get("node_type") in ("Concept", "Technology")
        and len(data.get("name", "")) >= 2
    ]

    # 字元反向索引（只對中文字 / 非 ASCII 字元做 blocking）
    char_index: dict[str, list] = {}
    for nid, name in sem_nodes:
        for ch in set(name):
            if ord(ch) > 127:  # 中文及全形字元
                char_index.setdefault(ch, []).append(nid)

    id_to_name = {nid: name for nid, name in sem_nodes}
    seen_pairs: set[tuple] = set()

    for nid, name in sem_nodes:
        # 候選：共享 ≥ 2 個非 ASCII 字元
        overlap_cnt: _Counter = _Counter()
        for ch in set(name):
            if ord(ch) > 127:
                for cid in char_index.get(ch, []):
                    if cid != nid:
                        overlap_cnt[cid] += 1

        for cid, cnt in overlap_cnt.items():
            if cnt < 2:
                continue
            pair = (nid, cid) if nid < cid else (cid, nid)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            stats["candidates_checked"] += 1

            cname = id_to_name[cid]
            # 長度比過大則跳過（避免「學習」匹配「機器學習算法與實作」）
            la, lb = len(name), len(cname)
            if max(la, lb) > 2.5 * min(la, lb):
                continue
            ratio = SequenceMatcher(None, name, cname).ratio()
            if ratio >= 0.70:
                ensure_edge(G, nid, cid, relation="SIMILAR_TO", weight=round(ratio, 3))
                ensure_edge(G, cid, nid, relation="SIMILAR_TO", weight=round(ratio, 3))
                stats["similar_to"] += 1

    return stats


def enrich_all(G: nx.DiGraph):
    """執行所有 Phase 2 豐富化步驟。

    執行順序說明：
    1. enrich_teacher_csv  先建立全量 1009 位 Instructor 節點 + EXPERT_IN 邊
    2. enrich_nlp          現在能對所有教師建立 RELEVANT_EXPERT 邊
    3. enrich_professor_links  利用完整教師節點建 COURSE_EXPERT 邊
    4. enrich_eligibility / enrich_schedule（不依賴教師節點，順序無影響）
    """
    print("\n  [Phase 2-a] 教師全量節點 + 官方專長（from teacher CSV）...")
    s = enrich_teacher_csv(G)
    print(f"    新增 Instructor 節點：{s['new_instructors']}，"
          f"專長已更新：{s['specs_updated']}，"
          f"EXPERT_IN 邊：{s['expert_in']}，"
          f"新 Field 節點：{s['new_field_nodes']}")

    print("\n  [Phase 2-b] NLP 豐富化（Field / Technology / Concept / TAGGED_AS）...")
    s = enrich_nlp(G)
    print(f"    Field 節點：{s['field_nodes']}，Technology：{s['tech_nodes']}，"
          f"Concept：{s['concept_nodes']}")
    print(f"    COVERS_FIELD：{s['covers_field']}，RELEVANT_EXPERT：{s['relevant_expert']}")
    print(f"    TEACHES：{s['teaches']}，COVERS：{s['covers']}")
    print(f"    TAGGED_AS：{s['tagged_as']}，core_questions 更新：{s['core_q_updated']}")

    print("\n  [Phase 2-c] 教授-課程領域關聯（from nlp_professor_links）...")
    s = enrich_professor_links(G)
    print(f"    COURSE_EXPERT 邊：{s['course_expert']}，"
          f"RELEVANT_EXPERT 補強：{s['relevant_expert_added']}，"
          f"略過（教師未在圖中）：{s['skipped_no_instructor']}")

    print("\n  [Phase 2-d] 修課條件（PREREQUISITE_OF / COREQUISITE / eligible_years）...")
    s = enrich_eligibility(G)
    print(f"    PREREQUISITE_OF：{s['prereq']}，COREQUISITE：{s['coreq']}，"
          f"eligible_years 更新：{s['eligible_years_set']}")

    print("\n  [Phase 2-e] 必修建議學期（from schedule_draft）...")
    s = enrich_schedule(G)
    print(f"    suggested_year/semester 更新：{s['updated']} 筆")

    print("\n  [Phase 2-f] Concept/Technology 同義邊（字串相似度）...")
    s = enrich_concept_synonymy(G)
    print(f"    候選配對檢查：{s['candidates_checked']}，"
          f"SIMILAR_TO 邊（單方向計）：{s['similar_to']}")


# ══════════════════════════════════════════════════════════════════════════════
# 6.  儲存與統計
# ══════════════════════════════════════════════════════════════════════════════

def _save_igraph_format(G: nx.DiGraph) -> None:
    """將 NetworkX 圖轉換為 igraph 格式並儲存（含預計算邊權重）。"""
    try:
        import igraph as ig
    except ImportError:
        print("  [跳過] python-igraph 未安裝，略過 .igraph 格式輸出")
        return

    GRAPH_IGRAPH = GRAPH_PKL.parent / "knowledge_graph.pkl"
    COVERS_FIELD_W = {"high": 1.5, "medium": 1.0, "low": 0.5}
    REL_WEIGHT = {
        "COVERS": 1.0, "TEACHES": 1.2,
        "PREREQUISITE_OF": 0.8,
        "EXPERT_IN": 1.0, "RELEVANT_EXPERT": 1.0, "COURSE_EXPERT": 0.8,
        "TAGGED_AS": 0.5, "IN_DOMAIN": 0.5, "DEVELOPS": 0.3,
    }

    nodes_list = list(G.nodes(data=True))
    id_to_idx = {nid: i for i, (nid, _) in enumerate(nodes_list)}

    G_ig = ig.Graph(directed=True)
    G_ig.add_vertices(len(nodes_list))
    for i, (nid, attrs) in enumerate(nodes_list):
        G_ig.vs[i]["name"]      = nid
        G_ig.vs[i]["node_type"] = attrs.get("node_type", "")
        G_ig.vs[i]["node_name"] = attrs.get("name", "")
        G_ig.vs[i]["dept"]      = attrs.get("dept", "")
        G_ig.vs[i]["credits"]   = int(attrs.get("credits") or 0)
        G_ig.vs[i]["level"]     = attrs.get("level", "")

    edge_tuples: list[tuple] = []
    weights: list[float] = []
    relations: list[str] = []
    seen_similar: set[tuple] = set()

    for src, tgt, attrs in G.edges(data=True):
        si = id_to_idx.get(src)
        ti = id_to_idx.get(tgt)
        if si is None or ti is None:
            continue
        rel = attrs.get("relation", "")
        if rel == "SIMILAR_TO":
            pair = (min(si, ti), max(si, ti))
            if pair in seen_similar:
                continue
            seen_similar.add(pair)
            w = float(attrs.get("weight", 0.8))
        elif rel == "COVERS_FIELD":
            w = COVERS_FIELD_W.get(attrs.get("relevance", "medium"), 1.0)
        elif rel == "DEVELOPS":
            # 等級 1-4 映射到 0.25-1.0；無等級資訊預設 0.3
            lv = attrs.get("level_num", 0)
            w = max(0.25, lv / 4.0) if lv else 0.3
        else:
            w = REL_WEIGHT.get(rel, 0.3)
        edge_tuples.append((si, ti))
        weights.append(w)
        relations.append(rel)

    G_ig.add_edges(edge_tuples)
    G_ig.es["weight"]   = weights
    G_ig.es["relation"] = relations
    G_ig.write_pickle(str(GRAPH_IGRAPH))
    print(f"  儲存：{GRAPH_IGRAPH}（{G_ig.vcount()} 節點，{G_ig.ecount()} 邊，"
          f"其中 SIMILAR_TO 已去重）")


def save_graph(G: nx.DiGraph):
    GRAPH_PKL.parent.mkdir(parents=True, exist_ok=True)
    with open(GRAPH_PKL, "wb") as f:
        pickle.dump(G, f)
    data = nx.readwrite.json_graph.node_link_data(G)
    with open(GRAPH_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n  儲存：{GRAPH_PKL}")
    print(f"  儲存：{GRAPH_JSON}")
    _save_igraph_format(G)


def print_and_save_stats(G: nx.DiGraph):
    node_types = Counter(d.get("node_type", "?") for _, d in G.nodes(data=True))
    edge_types = Counter(d.get("relation", "?") for _, _, d in G.edges(data=True))
    stub = sum(1 for _, d in G.nodes(data=True)
               if d.get("node_type") == "Course" and d.get("source") != "raw")
    raw_c = sum(1 for _, d in G.nodes(data=True)
                if d.get("node_type") == "Course" and d.get("source") == "raw")

    stats = {
        "total_nodes": G.number_of_nodes(),
        "total_edges": G.number_of_edges(),
        "node_types": dict(sorted(node_types.items(), key=lambda x: -x[1])),
        "edge_types": dict(sorted(edge_types.items(), key=lambda x: -x[1])),
    }
    with open(GRAPH_STATS, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    print(f"  總節點：{G.number_of_nodes()}  總邊：{G.number_of_edges()}")
    print(f"  Course: {raw_c} 有完整資料 / {stub} stub")
    print("\n  節點類型：")
    for nt, cnt in sorted(node_types.items(), key=lambda x: -x[1]):
        label = NODE_TYPES.get(nt, "")
        print(f"    {nt:30s} {cnt:5d}  {label}")
    print("\n  邊類型：")
    for et, cnt in sorted(edge_types.items(), key=lambda x: -x[1]):
        label = EDGE_TYPES.get(et, "")
        print(f"    {et:30s} {cnt:5d}  {label}")
    print(f"  統計已存：{GRAPH_STATS}")


# ══════════════════════════════════════════════════════════════════════════════
# 7.  main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="NCU 知識圖譜建置工具")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--build-only",    action="store_true", help="只建基礎圖，跳過豐富化")
    group.add_argument("--enrich-only",  action="store_true", help="只豐富化現有圖，不重建")
    group.add_argument("--synonymy-only", action="store_true", help="只補 SIMILAR_TO 邊（最快）")
    args = parser.parse_args()

    if args.synonymy_only:
        if not GRAPH_PKL.exists():
            print(f"找不到現有圖譜：{GRAPH_PKL}")
            return
        print("載入現有圖譜（synonymy-only 模式）...")
        with open(GRAPH_PKL, "rb") as f:
            G = pickle.load(f)
        print(f"  {G.number_of_nodes()} 節點，{G.number_of_edges()} 邊")
        print("\n  [Phase 2-f] Concept/Technology 同義邊（字串相似度）...")
        s = enrich_concept_synonymy(G)
        print(f"    候選配對：{s['candidates_checked']}，SIMILAR_TO 邊：{s['similar_to']}")
        save_graph(G)
        print_and_save_stats(G)
        print("\n✓ 完成")
        return

    if args.enrich_only:
        # 載入現有圖
        if not GRAPH_PKL.exists():
            print(f"找不到現有圖譜：{GRAPH_PKL}，請先執行完整流程（不加參數）")
            return
        print("載入現有圖譜...")
        with open(GRAPH_PKL, "rb") as f:
            G = pickle.load(f)
        print(f"  {G.number_of_nodes()} 節點，{G.number_of_edges()} 邊")
        print("\n=== Phase 2：NLP 豐富化 ===")
        enrich_all(G)
    else:
        # 完整流程：Phase 1
        print("=== Phase 1：基礎圖建置 ===")
        print("載入 raw 課程資料...")
        raw = _load_raw_courses()
        print(f"  課號：{len(raw)} 筆")
        G = build_base_graph(raw)

        if not args.build_only:
            # Phase 2
            print("\n=== Phase 2：NLP 豐富化 ===")
            enrich_all(G)

    save_graph(G)
    print_and_save_stats(G)
    print("\n✓ 完成")


if __name__ == "__main__":
    main()
