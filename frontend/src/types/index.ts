// 科系兴趣量表相关类型
export type AssessmentMode = 'grade1' | 'grade2' | 'grade3';

export interface Question {
  id: string;
  department: string; // 隐藏，仅用于后端计算
  title: string; // 研究题目
  motivation?: string; // 动机与问题
  method?: string; // 研究方法
  result?: string; // 研究结果
  intro?: string; // 興趣量表導讀
  questions?: string[]; // 興趣量表題目
  tags: string[]; // 小领域标签
  tracks?: ('liberal' | 'science')[]; // 高二文理分組（後端依系所學院判定）
  sourceDocumentId?: number;
  projectId?: string;
}

export interface Answer {
  questionId: string;
  score: number; // 1-5分
}

export interface AssessmentResult {
  departments: DepartmentScore[];
  tagScores: TagScore[];
}

export interface DepartmentScore {
  name: string;
  college: string;
  score: number;
  matchedTags: string[];
}

export interface TagScore {
  tag: string;
  score: number;
}

// 课程相关类型
export interface CoreAbility {
  ability_name: string;  // 能力名称
  intensity: string;     // 强度指数，如 "(5) 非常高"
  evaluation: string;    // 评量方式
}

export interface DistributionCondition {
  priority: string;  // 优先顺序
  condition: string; // 条件限制说明
}

export interface Course {
  serial_no: string;
  course_id: string;
  course_name_zh: string;
  course_name_en: string;
  college: string;
  department: string;
  instructor: string;
  credits: number;
  required_elective: string;
  semester_display: string; // 上學期/下學期/全年
  semester?: string; // 114_1, 114_2
  full_half_year?: string; // 全/半
  course_objective?: string;
  course_content?: string;
  textbooks?: string;
  grading?: string;
  // 新增字段
  course_system?: string;  // 课程学制
  course_field?: string;  // 课程领域
  core_abilities?: CoreAbility[];  // 核心能力列表
  distribution_conditions?: DistributionCondition[];  // 分发条件
  distribution_link?: string;  // 分发条件链接
  outline_link?: string;  // 课程纲要链接
  class_time?: string;  // 上课时间
  classroom?: string;  // 教室
  note?: string;  // 备注
  teaching_method?: string;  // 授课方式
  office_hours?: string;  // 办公时间
  weeks?: string;  // 授课周数
  is_grad?: boolean;
  relevance_score?: number;
  search_source?: string;
  semantic_summary?: string;
  eligibility_summary?: string;
  eligibility_status?: string;
  eligibility_warning?: string;
  languages?: string[];
  tools?: string[];
  concepts?: string[];
  topic_tags?: string[];
  domain_tags?: string[];
  core_questions?: string[];
  simplified_concepts?: string[];
}

export interface CourseSemanticSearchParams {
  query: string;
  selected_types?: string[];
  selected_credits?: string[];
  selected_semesters?: string[];
  limit?: number;
}

export interface CourseSemanticSearchResponse {
  mode: 'semantic' | 'fallback';
  message?: string;
  results: Course[];
}

export interface CourseAskResponse {
  answer: string;
  model: string;
  warnings: string[];
}

// 大专生计划相关类型
export interface Project {
  id: string;
  year: string; // 学年度
  type: string; // 计划类型 (E/H/M/B)
  department: string;
  studentName: string;
  title: string;
  pdfPath?: string;
  pdfUrl?: string;
  documentId?: number;
  motivation?: string;
  method?: string;
  result?: string;
  tags?: string[];
}

// 聊天 API 相關型別
export interface CourseCard {
  code:        string;
  name:        string;
  dept:        string;
  credits:     number;
  type:        string;
  teacher:     string;
  summary:     string;
  domain_tags?: string; // "領域::relevance||領域::relevance"
}

export interface ChatApiResponse {
  answer:            string;
  session_id:        string;
  tools_used:        string[];
  sources:           { name: string; dept: string; type: string }[];
  course_cards:      CourseCard[];
  course_pool:       CourseCard[];
  course_pool_count: number;
  has_large_result:  boolean;
  model:             string;
  input_tokens:      number;
  output_tokens:     number;
}

export type StreamEventType =
  | 'tool_start' | 'tool_done'
  | 'token' | 'done' | 'error'
  | 'verify_start' | 'verify_done';

export interface StreamEvent {
  type:             StreamEventType;
  text?:            string;   // token
  tool?:            string;   // tool_start / tool_done
  args?:            Record<string, unknown>; // tool_start
  count?:           number;   // tool_done
  courses_found?:   string[]; // tool_done
  scores?:          number[]; // tool_done — 與 courses_found 對應
  score_type?:      string;   // tool_done — "distance" | "shared_concepts" | "ppr"
  message?:         string;   // error
  // verify_start
  pool_size?:       number;
  // verify_done
  selected?:        string[];
  filtered_out?:    string[];
  method?:          'tag' | 'llm';
  // done
  final_answer?:    string;
  session_id?:      string;
  tools_used?:      string[];
  course_cards?:    CourseCard[];
  course_pool?:     CourseCard[];
  course_pool_count?: number;
  has_large_result?:  boolean;
  model?:           string;
  input_tokens?:    number;
  output_tokens?:   number;
  debug_trace?:     { toolCalls: ToolTraceItem[] }; // done — 後端累積的 trace
}

// Debug trace 型別
export interface ToolTraceItem {
  tool:         string;
  args:         Record<string, unknown>;
  coursesFound: string[];
  scores:       number[];
  scoreType:    string | null;
  count?:       number;
}

export interface VerifyTrace {
  poolSize:    number;
  selected:    string[];
  filteredOut: string[];
  method?:     'tag' | 'llm';
}

export interface DebugTrace {
  toolCalls: ToolTraceItem[];
  verify:    VerifyTrace | null;
}

// 学测科目
export type Subject = '国文' | '英文' | '数学A' | '数学B' | '社会' | '自然';

export interface Grade3Filter {
  subjects: Subject[];
  minScore?: number;
}
