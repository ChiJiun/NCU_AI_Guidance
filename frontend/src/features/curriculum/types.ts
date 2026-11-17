// 系所修課（curriculum）資料型別，新舊版頁面共用

export interface CourseEntry {
  code: string;
  name: string;
  credits: number;
  when?: string;
  mandatory?: boolean;
}

export interface ElectiveGroup {
  name: string;
  select?: number;
  select_credits?: number;
  group_rule?: string;
  description?: string;
  courses?: CourseEntry[];
  option_a?: CourseEntry[];
  option_b?: CourseEntry[];
  option_c?: CourseEntry[];
  slots?: { slot_name: string; slot_rule?: string; courses: CourseEntry[] }[];
}

export interface GraduationRule {
  type: string;
  category: string;
  description?: string;
  credits?: number;
  select?: number;
  books?: number;
  cert?: string;
  course_codes?: string[];
  courses?: CourseEntry[];
  options?: { name: string; credits?: number }[];
  [key: string]: unknown;
}

export interface DeptNode {
  id: string;
  name: string;
  program_type: string;
  min_credits: number;
  groups?: { id: string; name: string; group_label: string }[];
  specialization_tracks?: { id: string; name: string }[];
}

export interface CollegeNode {
  id: string;
  name: string;
  departments: DeptNode[];
  college_bachelor_programs: (DeptNode & { specialization_tracks?: { id: string; name: string }[] })[];
}

export interface DeptDetail {
  id: string;
  name: string;
  program_type: string;
  min_credits: number;
  required_credits?: number;
  graduation_rules: GraduationRule[];
  // 各種「必修」欄位名稱（不同系所用不同 key）
  required_courses?: CourseEntry[];
  foundation_courses?: CourseEntry[];
  college_required_courses?: CourseEntry[];
  common_required_courses?: CourseEntry[];
  dept_required_courses?: CourseEntry[];
  required_electives?: CourseEntry[];
  cross_domain_required?: CourseEntry[];
  earth_system_courses?: CourseEntry[];
  cross_group_required?: CourseEntry[];
  application_courses?: CourseEntry[];
  first_domain_electives?: CourseEntry[];
  // 領域選修（可從中選修以達到選修學分要求）
  elective_courses?: CourseEntry[];
  // 選修群
  elective_groups?: ElectiveGroup[];
  core_elective_groups?: ElectiveGroup[];
  college_required_elective_groups?: ElectiveGroup[];
  science_ability_groups?: ElectiveGroup[];
  other_elective_groups?: ElectiveGroup[];
  groups?: DeptDetail[];
  graduation_notes?: string;
}

export interface NotesEntry {
  key: string;
  raw_text: string;
  source?: string;
}

export interface CourseHit {
  deptId: string;
  deptName: string;
  collegeName: string;
  accentHex: string;
  category: 'required' | 'elective';
  groupName?: string;
  credits: number;
  originalName: string;
  originalCode: string;
}
export type CourseIndex = Map<string, CourseHit[]>;

export interface DeptSummary {
  id: string;
  name: string;
  collegeName: string;
  accentHex: string;
  min_credits: number;
}
