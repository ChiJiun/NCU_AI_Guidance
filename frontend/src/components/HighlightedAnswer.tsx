import { useMemo } from 'react';
import { HiAcademicCap } from 'react-icons/hi';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import type { CourseCard } from '../types';
import glossaryData from '../data/glossary.json';
import GlossaryTerm from './GlossaryTerm';
import { createMatcher, injectGlossary } from './glossary';

const GLOSSARY_MATCHER = createMatcher(glossaryData as Record<string, string>);

interface HighlightedAnswerProps {
  text:          string;
  courseCards:   CourseCard[];
  onCourseClick: (course: CourseCard) => void;
}

function injectCourseMarkers(text: string, sorted: CourseCard[]): string {
  // 建立課名 → index 的 lookup
  const nameToIdx: Record<string, number> = {};
  for (let i = 0; i < sorted.length; i++) {
    nameToIdx[sorted[i].name] = i;
  }

  // 只替換 <course>課名（系所）</course> 或 <course>課名</course> 標籤所在位置
  // 避免把全文中的同名子字串（如「巨量資料分析學程」中的「資料分析」）誤匹配
  return text.replace(
    /<course>(.*?)(?:（([^）]*)）)?<\/course>/g,
    (_, courseName, deptHint) => {
      const name = courseName.trim();
      const dept = deptHint?.trim() || '';
      // 若 LLM 有標注系所則保留，否則從 card 補上
      const idx = nameToIdx[name];
      const card = idx !== undefined ? sorted[idx] : undefined;
      const displayDept = dept || card?.dept || '';
      const displayText = displayDept ? `${name}（${displayDept}）` : name;
      if (idx !== undefined) {
        return `<mark data-cid="${idx}">${displayText}</mark>`;
      }
      // pool 中找不到對應課程，直接顯示文字（去掉標籤）
      return displayText;
    },
  );
}

export default function HighlightedAnswer({
  text,
  courseCards,
  onCourseClick,
}: HighlightedAnswerProps) {
  // 過濾串流中尚未完整的 <course_list> tag
  const clean = text.includes('<course_list>')
    ? text.slice(0, text.indexOf('<course_list>')).trimEnd()
    : text;

  // 先標課名，再標術語（術語比對會略過課名按鈕、程式碼與連結）
  const { text: processedText, hits: glossaryHits } = useMemo(() => {
    const withCourses = courseCards.length ? injectCourseMarkers(clean, courseCards) : clean;
    return injectGlossary(withCourses, GLOSSARY_MATCHER);
  }, [clean, courseCards]);

  return (
    <div className="markdown-answer text-sm leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw]}
        components={{
          // 課程名稱高亮按鈕
          mark({ node: _n, ...props }) {
            const cid = parseInt((props as Record<string, unknown>)['data-cid'] as string ?? '-1', 10);
            const card = courseCards[cid];
            if (!card) return <mark {...props} />;
            return (
              <button
                type="button"
                onClick={() => onCourseClick(card)}
                className="inline-flex items-center gap-1 rounded-md bg-white px-1.5 py-0.5 font-medium text-primary-700 shadow-sm ring-1 ring-black/[0.06] transition-all hover:-translate-y-px hover:shadow active:translate-y-0 active:shadow-sm"
              >
                <HiAcademicCap className="h-3.5 w-3.5 shrink-0 text-primary-400" />
                {props.children}
              </button>
            );
          },
          // 名詞白話提示（詞庫術語）
          dfn({ node: _n, ...props }) {
            const hit = glossaryHits[parseInt((props as Record<string, unknown>)['data-gi'] as string ?? '-1', 10)];
            if (!hit) return <>{props.children}</>;
            return <GlossaryTerm term={hit.surface} gloss={hit.gloss}>{props.children}</GlossaryTerm>;
          },
          // Markdown 元素樣式
          p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
          h1: ({ children }) => <h1 className="mb-2 text-base font-bold text-gray-900">{children}</h1>,
          h2: ({ children }) => <h2 className="mb-1.5 text-sm font-bold text-gray-900">{children}</h2>,
          h3: ({ children }) => <h3 className="mb-1 text-sm font-semibold text-gray-800">{children}</h3>,
          ul: ({ children }) => <ul className="mb-2 list-disc space-y-0.5 pl-4">{children}</ul>,
          ol: ({ children }) => <ol className="mb-2 list-decimal space-y-0.5 pl-4">{children}</ol>,
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
          em: ({ children }) => <em className="italic">{children}</em>,
          code: ({ children, className }) =>
            className ? (
              <code className="block overflow-x-auto rounded-lg bg-gray-100 p-3 font-mono text-xs text-gray-700">
                {children}
              </code>
            ) : (
              <code className="rounded bg-gray-200 px-1 py-0.5 font-mono text-xs text-gray-700">
                {children}
              </code>
            ),
          pre: ({ children }) => <pre className="mb-2 overflow-x-auto rounded-lg bg-gray-100 p-3">{children}</pre>,
          blockquote: ({ children }) => (
            <blockquote className="mb-2 border-l-4 border-gray-300 pl-3 text-gray-600 italic">
              {children}
            </blockquote>
          ),
          hr: () => <hr className="my-3 border-gray-200" />,
          table: ({ children }) => (
            <div className="mb-2 overflow-x-auto">
              <table className="w-full border-collapse text-xs">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border border-gray-300 bg-gray-100 px-2 py-1 text-left font-semibold">{children}</th>
          ),
          td: ({ children }) => (
            <td className="border border-gray-300 px-2 py-1">{children}</td>
          ),
        }}
      >
        {processedText}
      </ReactMarkdown>
    </div>
  );
}
