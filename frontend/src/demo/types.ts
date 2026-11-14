import type { CourseCard, ToolTraceItem } from '../types';

/** 與 scripts/demo/record_demo_cases.py 產生的 JSON 對應 */
export type DemoAssistant = 'course' | 'research';

export type DemoCategory =
  | 'general'
  | 'insufficient_data'
  | 'comparison'
  | 'anomaly'
  | 'safety'
  | 'complex';

export interface DemoToolStep {
  kind: 'tool';
  tool: string;
  args?: Record<string, unknown>;
  status: 'running' | 'done';
  count?: number | null;
  courses_found?: string[];
}

export interface DemoVerifyStep {
  kind: 'verify';
  pool_size?: number;
  status: 'running' | 'done';
  method?: 'tag' | 'llm';
  selected?: string[];
  filtered_out?: string[];
}

export type DemoStep = DemoToolStep | DemoVerifyStep;

export interface DemoTurn {
  user: string;
  assistant: string;
  latency_ms?: number;
  error?: string | null;
  // 課程助理
  steps?: DemoStep[];
  tools_used?: string[];
  course_cards?: CourseCard[];
  debug_trace?: { toolCalls?: ToolTraceItem[] } | null;
  model?: string;
  input_tokens?: number;
  output_tokens?: number;
  // 研究助理
  agent?: { name: string; label: string } | null;
  stages?: string[];
  sources?: unknown[];
}

export interface DemoProjectInfo {
  id: string;
  title: string;
  department: string;
  year: string;
  type?: string;
}

export interface DemoCase {
  id: string;
  assistant: DemoAssistant;
  category: DemoCategory;
  title: string;
  scenario: string;
  input: {
    messages: string[];
    project?: DemoProjectInfo | null;
    college?: string | null;
    dept?: string | null;
  };
  turns: DemoTurn[];
  meta: {
    generated_at: string;
    git_commit: string;
    models: string[];
    total_latency_ms: number;
    input_tokens: number;
    output_tokens: number;
    recorder?: string;
    /** input + turns 的 sha256，validate_demo_cases.py 會重算比對，防止 AI 回答被手動修改 */
    content_sha256?: string;
  };
  review: {
    status: 'pending' | 'approved' | 'rejected';
    reviewer: string | null;
    reviewed_at: string | null;
    notes?: string;
    conclusion?: string;
  };
}
