from fastapi import APIRouter, Query
import random
from collections import defaultdict
from statistics import mean
from typing import Dict, List, Literal, Optional
import json
import os
import csv
from app.models.schemas import (
    AssessmentMode,
    Question,
    SubmitAnswersRequest,
    AssessmentResult,
    DepartmentScore,
    TagScore,
    TrackScores,
    AdmissionCriteria,
    SubjectSelectionRequest
)
from app.services.department_names import (
    dept_college,
    dept_tracks,
    match_admission_to_bank,
)

router = APIRouter()

# 載入量表題目
def load_questions():
    data_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'processed', 'assessment_questions.json')
    with open(data_path, 'r', encoding='utf-8') as f:
        return json.load(f)

# 載入學測篩選標準
def load_admission_criteria():
    csv_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'raw', 'admission', 'ncu_caac.csv')
    criteria_list = []

    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            criteria_list.append(AdmissionCriteria(
                dept_code=row['系所代碼'],
                dept_name=row['系所名稱'],
                quota=int(row['招收人數']),
                chinese_required=int(row['國_採計']),
                english_required=int(row['英_採計']),
                math_a_required=int(row['數A_採計']),
                math_b_required=int(row['數B_採計']),
                social_required=int(row['社_採計']),
                science_required=int(row['自_採計']),
                chinese_standard=row.get('國_檢定'),
                english_standard=row.get('英_檢定'),
                math_a_standard=row.get('數A_檢定'),
                math_b_standard=row.get('數B_檢定'),
                social_standard=row.get('社_檢定'),
                science_standard=row.get('自_檢定'),
                english_listening=row.get('英聽'),
                sum_criteria=row.get('相加項')
            ))

    return criteria_list

# ── 抽題 ─────────────────────────────────────────────────────
# 每張題卡約 370 字（導讀約 200 字 + 3 個子題約 180 字），高中生閱讀加上 3 次評分
# 約需 1 分鐘；10 張題卡 = 30 個子題，約 10 分鐘可完成。
CARDS_PER_ATTEMPT = 10


def _with_tracks(card: dict) -> dict:
    return {**card, 'tracks': dept_tracks(card['department'])}


def mode_cards(mode: str) -> List[dict]:
    """該模式題庫中的所有題卡（附 tracks）。"""
    return [_with_tracks(q) for q in load_questions() if q['mode'] == mode]


def _allocate_by_college(depts: List[str], n: int, rng: random.Random) -> List[str]:
    """從 depts 中抽 n 個系所：名額依各學院系所數按比例分配（最大餘數法，同分隨機），
    名額不少於學院數時每個學院至少 1 個；學院內隨機抽系所。"""
    depts = sorted(depts)
    if n >= len(depts):
        return depts
    by_college: Dict[str, List[str]] = defaultdict(list)
    for d in depts:
        by_college[dept_college(d)].append(d)
    colleges = sorted(by_college)

    seats = {c: 0 for c in colleges}
    if n < len(colleges):
        for c in rng.sample(colleges, n):
            seats[c] = 1
    else:
        for c in colleges:
            seats[c] = 1
        remaining = n - len(colleges)
        total = len(depts)
        quotas = {c: len(by_college[c]) * n / total for c in colleges}
        for c in colleges:
            extra = min(max(int(quotas[c]) - seats[c], 0), len(by_college[c]) - seats[c], remaining)
            seats[c] += extra
            remaining -= extra
        tiebreak = {c: rng.random() for c in colleges}
        while remaining > 0:
            order = sorted(
                (c for c in colleges if seats[c] < len(by_college[c])),
                key=lambda c: (-(quotas[c] - seats[c]), tiebreak[c]),
            )
            if not order:
                break
            seats[order[0]] += 1
            remaining -= 1

    picked: List[str] = []
    for c in colleges:
        picked.extend(rng.sample(by_college[c], seats[c]))
    return picked


def sample_cards(cards: List[dict], n: int, rng: random.Random) -> List[dict]:
    """每個系所固定 1 張題卡（題卡多的系所隨機抽一張）；系所數超過 n 時依學院分層抽 n 個系所。"""
    by_dept: Dict[str, List[dict]] = defaultdict(list)
    for c in cards:
        by_dept[c['department']].append(c)
    depts = _allocate_by_college(list(by_dept), n, rng)
    return [rng.choice(sorted(by_dept[d], key=lambda c: c['id'])) for d in depts]


def _required_subjects(criteria: AdmissionCriteria) -> set:
    flags = {
        'chinese': criteria.chinese_required,
        'english': criteria.english_required,
        'math_a': criteria.math_a_required,
        'math_b': criteria.math_b_required,
        'social': criteria.social_required,
        'science': criteria.science_required,
    }
    return {s for s, v in flags.items() if v == 1}


def eligible_bank_departments(subjects: List[str]) -> dict:
    """學生有考的科目涵蓋該系所有採計科目就算可報名（多考的科目不影響；全選 = 全部系所）。"""
    selected = set(subjects)
    matching_depts = [
        c.dept_name for c in load_admission_criteria()
        if _required_subjects(c) <= selected
    ]
    # 招生系所名稱（含分組後綴、學系/系差異）→ 題庫中實際有題卡的系所名稱
    bank_depts = [q['department'] for q in load_questions() if q['mode'] == 'grade3']
    matched, unmatched, excluded = match_admission_to_bank(matching_depts, bank_depts)
    return {
        "departments": matched,              # 題庫系所名稱，前端直接用來篩題卡
        "admission_departments": matching_depts,  # 原始招生系所名稱
        "unmatched": unmatched,
        "excluded": excluded,
    }


def select_questions(
    mode: str,
    track: Optional[str] = None,
    subjects: Optional[List[str]] = None,
    seed: Optional[int] = None,
    limit: int = CARDS_PER_ATTEMPT,
) -> List[dict]:
    """依模式抽出一次作答的題卡；同一組 (mode, track, subjects, seed) 一定得到同一組題目。"""
    if seed is None:
        seed = random.randrange(2**31)
    key = f"{mode}|{track or ''}|{','.join(sorted(subjects or []))}|{seed}"
    rng = random.Random(key)
    cards = mode_cards(mode)

    if mode == 'grade1':
        # 文 / 理各一半，只抽單一類組的系所（跨文理的資管系不列入，避免同時替兩邊加分）
        per_track = max(limit // 2, 1)
        picked: List[dict] = []
        for t in ('liberal', 'science'):
            pool = [c for c in cards if c['tracks'] == [t]]
            picked += sample_cards(pool, per_track, rng)
    else:
        if mode == 'grade2' and track:
            cards = [c for c in cards if track in c['tracks']]
        elif mode == 'grade3' and subjects is not None:
            allowed = set(eligible_bank_departments(subjects)['departments'])
            cards = [c for c in cards if c['department'] in allowed]
        picked = sample_cards(cards, limit, rng)

    rng.shuffle(picked)
    return picked


@router.get("/questions", response_model=List[Question])
async def get_questions(
    mode: AssessmentMode = Query(..., description="Assessment mode: grade1, grade2, or grade3"),
    track: Optional[Literal['liberal', 'science']] = Query(None, description="高二文 / 理組"),
    subjects: Optional[List[str]] = Query(None, description="高三有考的學測科目"),
    seed: Optional[int] = Query(None, description="抽題種子，同一次作答固定不變"),
):
    """
    取得一次作答的題卡（每張題卡 3 個子題：研究情境、研究方法、思考方式，各 1-5 分）
    - 每個系所固定 1 張題卡（題卡多的系所依 seed 隨機抽一張），最多 10 張 = 30 個子題，約 10 分鐘
    - grade1: 高一模式，文組 5 個系 + 理組 5 個系（各依學院分層抽），判斷文 / 理組方向
    - grade2: 高二模式，依 track 篩系所；文組 8 個系全出（8 張），理組 30 個系依學院分層抽 10 個
    - grade3: 高三模式，依 subjects 篩可報名系所（採計科目都有考即可），超過 10 個系依學院分層抽 10 個
    - seed 相同則題目相同；前端每次開始作答產生一個 seed，作答期間題目不變
    """
    return select_questions(mode.value, track=track, subjects=subjects, seed=seed)


@router.post("/submit", response_model=AssessmentResult)
async def submit_answers(request: SubmitAnswersRequest):
    """
    提交答案並取得推薦結果

    - 題卡分數 = 該題卡子題平均（1-5）
    - 系所分數 = 該系題卡分數平均（1-5），不因題卡多寡而偏高；同分時以單題最高分、再以系名排序
    - 標籤分數 = 帶此標籤的題卡分數平均（1-5），不是加總，所以題卡多的系所標籤不會灌分
    - trackScores = 文組 / 理組（單一類組）系所的題卡平均，高一用來判斷文理方向
    """
    question_dict = {q['id']: q for q in load_questions()}

    card_scores: Dict[str, List[int]] = defaultdict(list)
    for answer in request.answers:
        if answer.questionId in question_dict and 1 <= answer.score <= 5:
            card_scores[answer.questionId].append(answer.score)

    dept_cards: Dict[str, List[float]] = defaultdict(list)
    dept_max: Dict[str, int] = defaultdict(int)
    dept_tags: Dict[str, List[str]] = defaultdict(list)
    tag_cards: Dict[str, List[float]] = defaultdict(list)
    track_cards: Dict[str, List[float]] = defaultdict(list)

    for qid, scores in card_scores.items():
        q = question_dict[qid]
        card = mean(scores)
        dept = q['department']
        dept_cards[dept].append(card)
        dept_max[dept] = max(dept_max[dept], max(scores))
        for tag in q['tags']:
            if tag not in dept_tags[dept]:
                dept_tags[dept].append(tag)
            tag_cards[tag].append(card)
        tracks = dept_tracks(dept)
        if len(tracks) == 1:
            track_cards[tracks[0]].append(card)

    department_results = [
        DepartmentScore(
            name=dept,
            college=get_college_for_department(dept),
            score=round(mean(cards), 2),
            matchedTags=dept_tags[dept],
        )
        for dept, cards in dept_cards.items()
    ]
    department_results.sort(key=lambda d: (-d.score, -dept_max[d.name], d.name))

    tag_results = [
        TagScore(tag=tag, score=round(mean(cards), 2), count=len(cards))
        for tag, cards in tag_cards.items()
    ]
    tag_results.sort(key=lambda t: (-t.score, -t.count, t.tag))

    track_scores = TrackScores(**{t: round(mean(v), 2) for t, v in track_cards.items()})

    return AssessmentResult(
        departments=department_results[:15],  # 回傳前15個推薦
        tagScores=tag_results[:20],  # 回傳前20個標籤
        trackScores=track_scores,
    )

def get_college_for_department(department: str) -> str:
    """根據科系名稱回傳學院名稱（對照表見 app.services.department_names）"""
    return dept_college(department)

@router.get("/admission-criteria", response_model=List[AdmissionCriteria])
async def get_admission_criteria():
    """
    取得所有學測篩選標準
    """
    return load_admission_criteria()

@router.post("/filter-by-subjects")
async def filter_departments_by_subjects(request: SubjectSelectionRequest):
    """
    根據選擇的學測科目篩選科系
    """
    return eligible_bank_departments(request.subjects)
