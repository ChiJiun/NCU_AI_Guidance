"""
department_names.py

興趣量表用的系所名稱正規化與對照（單一事實來源）。

題庫 (data/processed/assessment_questions.json) 的 department 名稱、
學測篩選表 (data/raw/admission/ncu_caac.csv) 的系所名稱、以及前端原本寫死的清單
彼此不一致，例如：
  - 「生命科學學系」 vs 「生命科學系」（學系 / 系）
  - 「企管學系」 vs 「企業管理學系」（簡稱）
  - 「數學系數學科學組」、「機械工程學系光機電工程組」（招生分組後綴）
  - 題庫中有研究所 / 研究中心的題卡，但學測只招大學部學系

這個模組負責：
  1. dept_key()：把任何寫法轉成比對用的 key（去分組後綴、括號、學系/系統一、別名）
  2. dept_tracks()：題庫系所屬於高二「文組 / 理組」哪一邊
  3. match_admission_to_bank()：高三學測篩選出的招生系所 → 可出題的題庫系所
不修改題庫內容，只在比對時轉換。
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Set, Tuple

# ── 1. 名稱正規化 ──────────────────────────────────────────────

# 簡稱 / 舊稱 → 正式名稱（先套用別名，再做 key 正規化）
ALIASES: Dict[str, str] = {
    "企管學系": "企業管理學系",
    "企管系": "企業管理學系",
    "地球科學學士班": "地球科學學院學士班",
}

# 「…系」後面接「…組」的招生分組後綴，例如 數學系數學科學組 → 數學系
_GROUP_SUFFIX = re.compile(r"^(.+?系)(.+組)$")
_PARENS = re.compile(r"[（(].*?[）)]")


def dept_key(name: str) -> str:
    """回傳比對用 key。兩個名稱 key 相同即視為同一系所。"""
    s = _PARENS.sub("", (name or "").strip()).replace(" ", "")
    s = ALIASES.get(s, s)
    m = _GROUP_SUFFIX.match(s)
    if m:
        s = m.group(1)
    s = ALIASES.get(s, s)
    # 學系 / 系 統一：去掉結尾「系」，再把結尾重複的「學學」合併
    #   生命科學學系 → 生命科學、生命科學系 → 生命科學、化學學系 → 化學
    if s.endswith("系"):
        s = s[:-1]
        if s.endswith("學學"):
            s = s[:-1]
    return s


# ── 2. 系所 → 學院（與 frontend/src/constants/colleges.ts 一致） ─────

DEPT_TO_COLLEGE: Dict[str, str] = {
    # 文學院
    "文學院學士班": "文學院",
    "中國文學系": "文學院",
    "英美語文學系": "文學院",
    "法國語文學系": "文學院",
    # 理學院
    "理學院學士班": "理學院",
    "化學學系": "理學院",
    "物理學系": "理學院",
    "數學系": "理學院",
    "光電科學與工程學系": "理學院",
    "光電科學研究中心": "理學院",
    "天文研究所": "理學院",
    "統計研究所": "理學院",
    # 工學院
    "工學院學士班": "工學院",
    "土木工程學系": "工學院",
    "機械工程學系": "工學院",
    "化學工程與材料工程學系": "工學院",
    "材料科學與工程研究所": "工學院",
    "營建管理研究所": "工學院",
    "環境工程研究所": "工學院",
    "能源工程研究所": "工學院",
    # 管理學院
    "經濟學系": "管理學院",
    "企業管理學系": "管理學院",
    "財務金融學系": "管理學院",
    "資訊管理學系": "管理學院",
    # 資訊電機學院
    "資訊電機學院學士班": "資訊電機學院",
    "電機工程學系": "資訊電機學院",
    "資訊工程學系": "資訊電機學院",
    "通訊工程學系": "資訊電機學院",
    "網路學習科技研究所": "資訊電機學院",
    # 地球科學學院
    "地球科學學院學士班": "地球科學學院",
    "地球科學學系": "地球科學學院",
    "大氣科學學系": "地球科學學院",
    "太空科學與工程學系": "地球科學學院",
    "太空及遙測研究中心": "地球科學學院",
    "太空科學與工程研究所": "地球科學學院",
    "太空科學與科技研究中心": "地球科學學院",
    "應用地質研究所": "地球科學學院",
    "水文與海洋科學研究所": "地球科學學院",
    # 客家學院
    "客家語文暨社會科學學系": "客家學院",
    # 生醫理工學院
    "生命科學系": "生醫理工學院",
    "生醫科學與工程學系": "生醫理工學院",
    "系統生物與生物資訊研究所": "生醫理工學院",
    "認知神經科學研究所": "生醫理工學院",
}

_COLLEGE_BY_KEY: Dict[str, str] = {dept_key(k): v for k, v in DEPT_TO_COLLEGE.items()}


def dept_college(name: str) -> str:
    return _COLLEGE_BY_KEY.get(dept_key(name), "其他")


# ── 3. 高二文 / 理組分類 ───────────────────────────────────────

LIBERAL_COLLEGES = {"文學院", "管理學院", "客家學院"}
# 跨領域、文理組都適合探索的系所
BOTH_TRACKS = {dept_key("資訊管理學系")}


def dept_tracks(name: str) -> List[str]:
    """回傳 ['liberal'] / ['science'] / ['liberal', 'science']。"""
    key = dept_key(name)
    if key in BOTH_TRACKS:
        return ["liberal", "science"]
    college = _COLLEGE_BY_KEY.get(key)
    if college is None:
        return []
    return ["liberal"] if college in LIBERAL_COLLEGES else ["science"]


# ── 4. 高三：招生系所 → 題庫系所 ────────────────────────────────

# 題庫中的研究所 / 研究中心 → 對應的大學部學系（大學部學系符合學測條件時一併出題）
GRAD_PARENT: Dict[str, str] = {
    "天文研究所": "物理學系",
    "統計研究所": "數學系",
    "光電科學研究中心": "光電科學與工程學系",
    "材料科學與工程研究所": "化學工程與材料工程學系",
    "營建管理研究所": "土木工程學系",
    "環境工程研究所": "土木工程學系",
    "能源工程研究所": "機械工程學系",
    "網路學習科技研究所": "資訊工程學系",
    "太空及遙測研究中心": "太空科學與工程學系",
    "太空科學與工程研究所": "太空科學與工程學系",
    "太空科學與科技研究中心": "太空科學與工程學系",
    "應用地質研究所": "地球科學學系",
    "水文與海洋科學研究所": "地球科學學系",
    "系統生物與生物資訊研究所": "生命科學系",
    "認知神經科學研究所": "生醫科學與工程學系",
}
_GRAD_PARENT_KEY = {dept_key(k): dept_key(v) for k, v in GRAD_PARENT.items()}
_GRAD_PARENT_NAME = {dept_key(k): v for k, v in GRAD_PARENT.items()}


def dept_unit(name: str) -> str:
    """量表推薦單位：研究所 / 研究中心的題卡算給所屬的大學部學系（高中生只能報大學部）。"""
    return _GRAD_PARENT_NAME.get(dept_key(name), name)

# 學院學士班入學後可在學院內選系 → 展開成該學院的學系
_COLLEGE_PROGRAMS = {
    dept_key(name): college
    for name, college in DEPT_TO_COLLEGE.items()
    if name.endswith("學士班")
}

# 學測招生系所中，題庫本來就沒有任何題卡的項目（合理排除，不算配對失敗）
EXCLUDED_ADMISSION: Dict[str, str] = {
    "經濟學系": "題庫目前沒有經濟學系的研究題卡",
    "法律與政府學系": "新設學系，題庫沒有對應題卡",
    "向日葵聯合招生": "弱勢生聯合招生管道，非單一系所，入學後再分系",
}


def excluded_reason(admission_name: str) -> str | None:
    for prefix, reason in EXCLUDED_ADMISSION.items():
        if admission_name.startswith(prefix):
            return reason
    return None


def _expand_admission_key(admission_name: str) -> Set[str]:
    key = dept_key(admission_name)
    keys = {key}
    college = _COLLEGE_PROGRAMS.get(key)
    if college:
        keys |= {k for k, c in _COLLEGE_BY_KEY.items() if c == college}
    return keys


def bank_dept_matches(bank_dept: str, admission_keys: Set[str]) -> bool:
    key = dept_key(bank_dept)
    if key in admission_keys:
        return True
    parent = _GRAD_PARENT_KEY.get(key)
    return parent is not None and parent in admission_keys


def match_admission_to_bank(
    admission_names: Iterable[str], bank_depts: Iterable[str]
) -> Tuple[List[str], List[str], List[str]]:
    """
    回傳 (matched_bank_depts, unmatched_admission_names, excluded_admission_names)。
    - matched_bank_depts：題庫中的系所原名（含研究所題卡），保留題庫順序、不重複
    - unmatched：找不到任何題卡、也不在合理排除名單內的招生系所（應為空）
    - excluded：在 EXCLUDED_ADMISSION 名單內的招生系所
    """
    bank_list = list(dict.fromkeys(bank_depts))
    matched: List[str] = []
    unmatched: List[str] = []
    excluded: List[str] = []
    all_keys: Set[str] = set()
    for name in admission_names:
        keys = _expand_admission_key(name)
        hits = [d for d in bank_list if bank_dept_matches(d, keys)]
        if hits:
            all_keys |= keys
        elif excluded_reason(name):
            excluded.append(name)
        else:
            unmatched.append(name)
    matched = [d for d in bank_list if bank_dept_matches(d, all_keys)]
    return matched, unmatched, excluded
