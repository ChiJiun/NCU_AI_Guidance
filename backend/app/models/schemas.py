from pydantic import BaseModel, field_validator
from typing import List, Optional
from enum import Enum

# 科系興趣量表相關模型
class AssessmentMode(str, Enum):
    GRADE1 = "grade1"  # 高一：文組 vs 理組
    GRADE2 = "grade2"  # 高二：細分科系
    GRADE3 = "grade3"  # 高三：結合學測

class Question(BaseModel):
    id: str
    department: str
    title: str
    motivation: Optional[str] = None
    method: Optional[str] = None
    result: Optional[str] = None
    intro: Optional[str] = None
    questions: Optional[List[str]] = None
    tags: List[str]
    tracks: List[str] = []  # 高二文理分組：'liberal' / 'science'

class Answer(BaseModel):
    questionId: str
    score: int  # 1-5

class SubmitAnswersRequest(BaseModel):
    mode: AssessmentMode
    answers: List[Answer]

class DepartmentScore(BaseModel):
    name: str
    college: str
    score: float
    matchedTags: List[str]

class TagScore(BaseModel):
    tag: str
    score: float  # 帶有此標籤的題卡平均分（1-5），不受題卡數多寡影響
    count: int = 1  # 出現在幾張題卡

class TrackScores(BaseModel):
    liberal: Optional[float] = None  # 文組系所題卡平均分（1-5）
    science: Optional[float] = None  # 理組系所題卡平均分（1-5）

class AssessmentResult(BaseModel):
    departments: List[DepartmentScore]
    tagScores: List[TagScore]
    trackScores: Optional[TrackScores] = None

# 課程相關模型
class CoreAbility(BaseModel):
    """核心能力模型"""
    ability_name: str  # 能力名稱
    intensity: str  # 強度指數，如 "(5) 非常高"
    evaluation: str  # 評量方式

class DistributionCondition(BaseModel):
    """分發條件模型"""
    priority: str  # 優先順序
    condition: str  # 條件限制說明

class CourseOutline(BaseModel):
    课程目标: Optional[str] = None
    课程内容: Optional[str] = None
    教科书: Optional[str] = None
    评分方式: Optional[str] = None

class Course(BaseModel):
    serial_no: str
    course_id: str
    course_name_zh: str
    course_name_en: str
    college: str
    department: str
    instructor: str
    credits: int
    required_elective: str
    semester_display: str  # 上學期/下學期/全年
    semester: Optional[str] = None  # 原始學期資訊 (114_1, 114_2)
    full_half_year: Optional[str] = None  # 全/半
    course_objective: Optional[str] = None
    course_content: Optional[str] = None
    textbooks: Optional[str] = None
    grading: Optional[str] = None
    # 新增字段
    course_system: Optional[str] = None  # 課程學制
    course_field: Optional[str] = None  # 課程領域
    core_abilities: Optional[List[CoreAbility]] = None  # 核心能力列表
    distribution_conditions: Optional[List[DistributionCondition]] = None  # 分發條件
    distribution_link: Optional[str] = None  # 分發條件連結
    outline_link: Optional[str] = None  # 課程綱要連結
    class_time: Optional[str] = None  # 上課時間
    classroom: Optional[str] = None  # 教室
    note: Optional[str] = None  # 備註
    teaching_method: Optional[str] = None  # 授課方式
    office_hours: Optional[str] = None  # 辦公時間
    weeks: Optional[str] = None  # 授課週數
    is_grad: Optional[bool] = None
    relevance_score: Optional[float] = None
    search_source: Optional[str] = None
    semantic_summary: Optional[str] = None
    eligibility_summary: Optional[str] = None
    eligibility_status: Optional[str] = None
    eligibility_warning: Optional[str] = None
    languages: Optional[List[str]] = None
    tools: Optional[List[str]] = None
    concepts: Optional[List[str]] = None
    topic_tags: Optional[List[str]] = None
    domain_tags: Optional[List[str]] = None
    core_questions: Optional[List[str]] = None
    simplified_concepts: Optional[List[str]] = None

class CourseSearchRequest(BaseModel):
    query: str

# 大專生計畫相關模型
class Project(BaseModel):
    id: str
    year: str
    type: str  # E/H/M/B
    department: str
    studentName: str
    title: str
    pdfPath: Optional[str] = None
    pdfUrl: Optional[str] = None
    documentId: Optional[int] = None
    motivation: Optional[str] = None
    method: Optional[str] = None
    result: Optional[str] = None
    tags: Optional[List[str]] = None

class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None

    @field_validator("message")
    @classmethod
    def message_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message must not be empty")
        return v.strip()

    @field_validator("thread_id")
    @classmethod
    def thread_id_valid(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if len(v) > 36:
            raise ValueError("thread_id must be at most 36 characters")
        return v

class ChatResponse(BaseModel):
    reply: str

# 學測篩選相關模型
class AdmissionCriteria(BaseModel):
    dept_code: str
    dept_name: str
    quota: int
    chinese_required: int  # 0 或 1
    english_required: int
    math_a_required: int
    math_b_required: int
    social_required: int
    science_required: int
    chinese_standard: Optional[str] = None  # 前/均/頂/--
    english_standard: Optional[str] = None
    math_a_standard: Optional[str] = None
    math_b_standard: Optional[str] = None
    social_standard: Optional[str] = None
    science_standard: Optional[str] = None
    english_listening: Optional[str] = None
    sum_criteria: Optional[str] = None

class SubjectSelectionRequest(BaseModel):
    subjects: List[str]  # ['chinese', 'english', 'math_a', 'math_b', 'social', 'science']
