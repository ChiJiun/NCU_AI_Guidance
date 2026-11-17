import { useEffect, useRef } from 'react';
import type { FormEvent, ReactNode } from 'react';
import { HiArrowUp, HiChatAlt2, HiExternalLink, HiMinus, HiPlus, HiX } from 'react-icons/hi';
import HighlightText from '../../components/HighlightText';
import { splitFields } from '../../features/courses/catalog';
import { QUICK_ACTIONS, useCourseAsk } from '../../features/courses/useCourseAsk';
import type { Course } from '../../types';
import LiveAiGate from './LiveAiGate';
import Markdown from './Markdown';

interface CourseDetailV2Props {
  course: Course;
  keyword?: string;
  isCompared?: boolean;
  onToggleCompare?: (course: Course) => void;
}

const unique = (values?: string[]) => Array.from(new Set((values ?? []).map((item) => item.trim()).filter(Boolean)));

/** 強度指數字串（例如「(5) 非常高」）裡的數字 */
const intensityValue = (intensity: string) => Number(intensity.match(/\((\d+)\)/)?.[1] ?? 0);

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="grid gap-x-6 gap-y-2 border-t py-5 md:grid-cols-[5.5rem_1fr]" style={{ borderColor: 'var(--v2-line)' }}>
      <h3 className="v2-faint text-sm font-semibold">{title}</h3>
      <div className="min-w-0">{children}</div>
    </section>
  );
}

function Chips({ items, keyword }: { items: string[]; keyword: string }) {
  return (
    <ul className="flex flex-wrap gap-1.5">
      {items.map((item) => (
        <li key={item} className="v2-tag !whitespace-normal">
          <HighlightText text={item} keyword={keyword} />
        </li>
      ))}
    </ul>
  );
}

/** 課程詳情（新版畫面）。資料與「問這門課」的邏輯和舊版共用 useCourseAsk。 */
export default function CourseDetailV2({ course, keyword = '', isCompared = false, onToggleCompare }: CourseDetailV2Props) {
  const ask = useCourseAsk(course);
  const { askOpen, closeAsk } = ask;
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!askOpen) return;
    inputRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeAsk();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
    // closeAsk 每次 render 都是新的函式，但只會重設 state，不需要列為相依
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [askOpen]);

  const send = (question: string) => {
    const text = question.trim();
    if (!text || ask.askLoading) return;
    ask.setAskQuestion('');
    void ask.submitQuestion(text);
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    send(ask.askQuestion);
  };

  const fields = splitFields(course.course_field);
  const concepts = unique(course.concepts);
  const simplified = unique(course.simplified_concepts);
  const conceptPairs = Array.from({ length: Math.max(concepts.length, simplified.length) }, (_, index) => ({
    title: concepts[index] || simplified[index],
    sub: concepts[index] ? simplified[index] : undefined,
  }));
  const tagGroups = [
    { label: '工具', items: unique(course.tools) },
    { label: '主題', items: unique(course.topic_tags) },
    { label: '領域', items: unique(course.domain_tags) },
    { label: '語言', items: unique(course.languages) },
  ].filter((group) => group.items.length > 0);
  const coreQuestions = unique(course.core_questions);
  const abilities = course.core_abilities ?? [];
  const conditions = course.distribution_conditions ?? [];
  const logistics = [
    { label: '教師', value: course.instructor },
    { label: '時間', value: course.class_time },
    { label: '地點', value: course.classroom },
    { label: '週數', value: course.weeks ? `${course.weeks} 週` : '' },
    { label: '授課', value: course.teaching_method },
    { label: 'Office Hours', value: course.office_hours },
  ].filter((item) => item.value);
  const facts = [
    course.course_id,
    `${course.credits} 學分`,
    course.required_elective,
    course.semester_display,
    course.course_system,
  ].filter(Boolean);
  const isRequired = (course.required_elective || '').trim() === '必修';

  return (
    <article className="px-5 pb-10 pt-6 md:px-8">
      <header>
        <h2 className="v2-serif text-2xl leading-snug md:text-3xl">
          <HighlightText text={course.course_name_zh} keyword={keyword} />
        </h2>
        {course.course_name_en && (
          <p className="v2-muted mt-1">
            <HighlightText text={course.course_name_en} keyword={keyword} />
          </p>
        )}
        <ul className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
          {facts.map((fact, index) => (
            <li key={index} className={fact === course.required_elective && isRequired ? 'v2-accent font-bold' : 'font-medium'}>
              {fact}
            </li>
          ))}
          {fields.map((field) => (
            <li key={field} className="v2-tag">
              <HighlightText text={field} keyword={keyword} />
            </li>
          ))}
        </ul>
        <div className="mt-5 flex flex-wrap gap-2">
          <button
            type="button"
            className="v2-btn"
            onClick={() => {
              ask.resetAskState();
              ask.setAskOpen(true);
            }}
          >
            <HiChatAlt2 className="h-4 w-4" aria-hidden="true" />
            問這門課
          </button>
          {onToggleCompare && (
            <button
              type="button"
              className="v2-btn v2-btn--ghost"
              aria-pressed={isCompared}
              onClick={() => onToggleCompare(course)}
            >
              {isCompared ? <HiMinus className="h-4 w-4" aria-hidden="true" /> : <HiPlus className="h-4 w-4" aria-hidden="true" />}
              {isCompared ? '移出對比' : '加入對比'}
            </button>
          )}
          {course.outline_link && (
            <a href={course.outline_link} target="_blank" rel="noopener noreferrer" className="v2-btn v2-btn--ghost">
              課綱
              <HiExternalLink className="h-4 w-4" aria-hidden="true" />
            </a>
          )}
          {course.distribution_link && (
            <a href={course.distribution_link} target="_blank" rel="noopener noreferrer" className="v2-btn v2-btn--ghost">
              分發資訊
              <HiExternalLink className="h-4 w-4" aria-hidden="true" />
            </a>
          )}
        </div>
      </header>

      <div className="mt-6">
        {course.course_objective && (
          <Block title="目標">
            <p className="whitespace-pre-wrap leading-relaxed">
              <HighlightText text={course.course_objective} keyword={keyword} />
            </p>
          </Block>
        )}

        {course.course_content && (
          <Block title="內容">
            <p className="whitespace-pre-wrap leading-relaxed">
              <HighlightText text={course.course_content} keyword={keyword} />
            </p>
          </Block>
        )}

        {conceptPairs.length > 0 && (
          <Block title="概念">
            <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
              {conceptPairs.map((pair, index) => (
                <div key={index}>
                  <dt className="font-semibold">
                    <HighlightText text={pair.title} keyword={keyword} />
                  </dt>
                  {pair.sub && (
                    <dd className="v2-muted text-sm">
                      <HighlightText text={pair.sub} keyword={keyword} />
                    </dd>
                  )}
                </div>
              ))}
            </dl>
          </Block>
        )}

        {tagGroups.map((group) => (
          <Block key={group.label} title={group.label}>
            <Chips items={group.items} keyword={keyword} />
          </Block>
        ))}

        {coreQuestions.length > 0 && (
          <Block title="核心問題">
            <ul className="list-disc space-y-1 pl-5">
              {coreQuestions.map((question) => (
                <li key={question}>
                  <HighlightText text={question} keyword={keyword} />
                </li>
              ))}
            </ul>
          </Block>
        )}

        {abilities.length > 0 && (
          <Block title="核心能力">
            <ul className="space-y-3">
              {abilities.map((ability, index) => (
                <li key={`${ability.ability_name}-${index}`}>
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="font-medium">{ability.ability_name}</span>
                    <span className="v2-faint shrink-0 text-sm">{ability.intensity}</span>
                  </div>
                  <div className="v2-bar mt-1.5" aria-hidden="true">
                    <span style={{ width: `${intensityValue(ability.intensity) * 20}%` }} />
                  </div>
                  {ability.evaluation && <p className="v2-muted mt-1 text-sm">{ability.evaluation}</p>}
                </li>
              ))}
            </ul>
          </Block>
        )}

        {conditions.length > 0 && (
          <Block title="分發條件">
            <ol className="space-y-2">
              {conditions.map((condition, index) => (
                <li key={index} className="grid grid-cols-[1.75rem_1fr] gap-2">
                  <span className="v2-num">{condition.priority}</span>
                  <span>
                    <HighlightText text={condition.condition} keyword={keyword} />
                  </span>
                </li>
              ))}
            </ol>
          </Block>
        )}

        {logistics.length > 0 && (
          <Block title="上課">
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
              {logistics.map((item) => (
                <div key={item.label} className="contents">
                  <dt className="v2-muted">{item.label}</dt>
                  <dd>
                    {item.label === '教師' ? <HighlightText text={item.value ?? ''} keyword={keyword} /> : item.value}
                  </dd>
                </div>
              ))}
            </dl>
          </Block>
        )}

        {course.textbooks && (
          <Block title="教材">
            <p className="whitespace-pre-wrap leading-relaxed">
              <HighlightText text={course.textbooks} keyword={keyword} />
            </p>
          </Block>
        )}

        {course.grading && (
          <Block title="評分">
            <p className="whitespace-pre-wrap leading-relaxed">{course.grading}</p>
          </Block>
        )}

        {course.note && (
          <Block title="備註">
            <p className="whitespace-pre-wrap leading-relaxed">
              <HighlightText text={course.note} keyword={keyword} />
            </p>
          </Block>
        )}
      </div>

      {askOpen && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div className="absolute inset-0 bg-black/30" onClick={closeAsk} aria-hidden="true" />
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="v2-ask-title"
            className="v2-rise relative flex h-full w-full max-w-md flex-col border-l shadow-2xl"
            style={{ background: 'var(--v2-paper)', borderColor: 'var(--v2-line)' }}
          >
            <header className="flex items-center gap-2 border-b py-2 pl-5 pr-2" style={{ borderColor: 'var(--v2-line)' }}>
              <h3 id="v2-ask-title" className="v2-serif min-w-0 flex-1 truncate text-lg">
                {course.course_name_zh}
              </h3>
              <button type="button" className="v2-iconbtn" aria-label="關閉" onClick={closeAsk}>
                <HiX className="h-5 w-5" aria-hidden="true" />
              </button>
            </header>

            <div className="v2-scroll min-h-0 flex-1 space-y-4 px-5 py-5" aria-live="polite">
              {ask.askLastQuestion && (
                <p className="ml-auto w-fit max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm px-4 py-2.5 text-white" style={{ background: 'var(--v2-ink)' }}>
                  {ask.askLastQuestion}
                </p>
              )}
              {ask.askLoading && (
                <div role="status" className="flex items-center gap-2">
                  <span className="v2-spinner" aria-hidden="true" />
                  <span className="sr-only">回答中</span>
                </div>
              )}
              {ask.askAnswer && <Markdown text={ask.askAnswer} />}
              {ask.askError && (
                <p role="alert" className="text-sm" style={{ color: 'var(--v2-danger)' }}>
                  {ask.askError}
                </p>
              )}
            </div>

            <footer className="border-t p-4" style={{ borderColor: 'var(--v2-line)' }}>
              <LiveAiGate liveAi={ask.liveAi} assistant="course">
                <ul className="-mx-4 mb-3 flex gap-1.5 overflow-x-auto px-4" aria-label="快速提問">
                  {QUICK_ACTIONS.map((action) => (
                    <li key={action.id} className="shrink-0">
                      <button
                        type="button"
                        className="v2-chip v2-chip--sm"
                        disabled={ask.askLoading}
                        onClick={() => send(action.prompt)}
                      >
                        {action.label}
                      </button>
                    </li>
                  ))}
                </ul>
                <form onSubmit={handleSubmit} className="flex items-end gap-2">
                  <textarea
                    ref={inputRef}
                    value={ask.askQuestion}
                    onChange={(event) => ask.setAskQuestion(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
                        event.preventDefault();
                        send(ask.askQuestion);
                      }
                    }}
                    rows={2}
                    aria-label="問這門課"
                    placeholder="問這門課…"
                    className="v2-input resize-none"
                    disabled={ask.askLoading}
                  />
                  <button
                    type="submit"
                    className="v2-btn !w-11 !px-0"
                    aria-label="送出"
                    disabled={ask.askLoading || !ask.askQuestion.trim()}
                  >
                    <HiArrowUp className="h-5 w-5" aria-hidden="true" />
                  </button>
                </form>
              </LiveAiGate>
            </footer>
          </div>
        </div>
      )}
    </article>
  );
}
