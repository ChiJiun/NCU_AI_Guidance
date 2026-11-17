import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { HiArrowLeft, HiArrowRight } from 'react-icons/hi';
import { useAssessment } from '../../features/assessment/useAssessment';
import type { AssessmentMode } from '../../types';
import { useSite } from '../site';
import RovingGroup from '../components/RovingGroup';

const MODES: { id: AssessmentMode; label: string }[] = [
  { id: 'grade1', label: '高一' },
  { id: 'grade2', label: '高二' },
  { id: 'grade3', label: '高三' },
];

const TRACKS = [
  { id: 'liberal', label: '文組' },
  { id: 'science', label: '理組' },
] as const;

const SUBJECTS = [
  { id: 'chinese', label: '國文' },
  { id: 'english', label: '英文' },
  { id: 'math_a', label: '數學A' },
  { id: 'math_b', label: '數學B' },
  { id: 'social', label: '社會' },
  { id: 'science', label: '自然' },
];

const SCORES = [1, 2, 3, 4, 5];

/** 每種模式的份量：題卡數、題數、分鐘數（與後端抽題規則一致，見 useAssessment 的說明） */
function workload(mode: AssessmentMode, track: 'liberal' | 'science' | null) {
  if (mode === 'grade1') return { cards: '10', questions: '30', minutes: '10' };
  if (mode === 'grade2') {
    if (track === 'liberal') return { cards: '8', questions: '24', minutes: '8' };
    if (track === 'science') return { cards: '16', questions: '48', minutes: '15' };
    return { cards: '–', questions: '–', minutes: '–' };
  }
  return { cards: '≤16', questions: '≤48', minutes: '≤15' };
}

function Loading() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center" role="status">
      <span className="v2-spinner" aria-hidden="true" />
      <span className="sr-only">載入中</span>
    </div>
  );
}

export default function AssessmentV2() {
  const { link, collegeHex } = useSite();
  const [error, setError] = useState('');
  const {
    mode, setMode,
    trackType, setTrackType,
    selectedSubjects, setSelectedSubjects,
    started, setStarted,
    questions,
    currentIndex,
    answers,
    loading,
    result, setResult,
    eligibleUnits,
    prevDepts,
    handleStart,
    handleNextRound,
    getQuestionCount,
    getAnswerKey,
    handleScore,
    handleNext,
    handlePrevious,
    handleSubmit,
    determineTrack,
  } = useAssessment({ notify: setError });

  // 換題卡、看到結果時回到頂端，並把焦點移到標題（鍵盤與螢幕閱讀器使用者才知道內容換了）
  const headingRef = useRef<HTMLHeadingElement>(null);
  const showingResult = result !== null;
  useEffect(() => {
    if (!started) return;
    window.scrollTo({ top: 0 });
    headingRef.current?.focus({ preventScroll: true });
  }, [started, currentIndex, showingResult]);

  // ── 設定 ──
  if (!started) {
    const load = workload(mode, trackType);
    const needsTrack = mode === 'grade2' && !trackType;
    const needsSubjects = mode === 'grade3' && selectedSubjects.length === 0;
    const startLabel = needsTrack ? '選擇類組' : needsSubjects ? '選擇科目' : '開始';

    return (
      <div className="v2-container v2-container--narrow py-12 md:py-20">
        <h1 className="v2-serif text-4xl md:text-5xl">興趣量表</h1>

        <div className="mt-10 space-y-8">
          <RovingGroup role="radiogroup" aria-label="年級" className="v2-seg">
            {MODES.map((item) => (
              <button
                key={item.id}
                type="button"
                role="radio"
                aria-checked={mode === item.id}
                onClick={() => {
                  setMode(item.id);
                  setTrackType(null);
                  setSelectedSubjects([]);
                  setError('');
                }}
              >
                {item.label}
              </button>
            ))}
          </RovingGroup>

          {mode === 'grade2' && (
            <RovingGroup role="radiogroup" aria-label="類組" className="flex flex-wrap gap-2">
              {TRACKS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  role="radio"
                  aria-checked={trackType === item.id}
                  className="v2-chip min-w-24"
                  onClick={() => setTrackType(item.id)}
                >
                  {item.label}
                </button>
              ))}
            </RovingGroup>
          )}

          {mode === 'grade3' && (
            <div role="group" aria-label="學測科目" className="flex flex-wrap gap-2">
              {SUBJECTS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  aria-pressed={selectedSubjects.includes(item.id)}
                  className="v2-chip"
                  onClick={() => {
                    setError('');
                    setSelectedSubjects((prev) =>
                      prev.includes(item.id) ? prev.filter((id) => id !== item.id) : [...prev, item.id],
                    );
                  }}
                >
                  {item.label}
                </button>
              ))}
            </div>
          )}

          <dl className="flex gap-10 border-y py-6" style={{ borderColor: 'var(--v2-line)' }}>
            {[
              { value: load.cards, label: '張題卡' },
              { value: load.questions, label: '題' },
              { value: load.minutes, label: '分鐘' },
            ].map((item) => (
              <div key={item.label} className="flex flex-col-reverse">
                <dt className="v2-muted text-sm">{item.label}</dt>
                <dd className="v2-num text-4xl">{item.value}</dd>
              </div>
            ))}
          </dl>

          <div className="flex flex-wrap items-center gap-4">
            <button
              type="button"
              className="v2-btn v2-btn--lg min-w-40"
              disabled={needsTrack || needsSubjects || loading}
              onClick={() => {
                setError('');
                void handleStart();
              }}
            >
              {startLabel}
              {!needsTrack && !needsSubjects && <HiArrowRight className="h-5 w-5" aria-hidden="true" />}
            </button>
            {error && (
              <p role="alert" className="text-sm" style={{ color: 'var(--v2-danger)' }}>
                {error}
              </p>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (loading && questions.length === 0) return <Loading />;

  // ── 結果 ──
  if (result) {
    const track = mode === 'grade1' ? determineTrack() : null;
    const answeredDepts = new Set([...prevDepts, ...questions.map((q) => q.department)]);
    const uncovered = mode === 'grade3' ? eligibleUnits.filter((dept) => !answeredDepts.has(dept)) : [];
    const colleges = result.colleges ?? [];
    const departments = result.departments.slice(0, 10);
    const tags = result.tagScores.slice(0, 12);

    return (
      <div className="v2-container v2-container--mid py-12 md:py-16">
        <h1 ref={headingRef} tabIndex={-1} className="v2-serif text-4xl outline-none md:text-5xl">
          {track ? (
            <>
              你偏向<span className="v2-accent">{track === 'liberal' ? '文組' : '理組'}</span>
            </>
          ) : (
            '你的結果'
          )}
        </h1>

        {track && result.trackScores && (
          <dl className="mt-6 grid max-w-md grid-cols-[auto_1fr_auto] items-center gap-x-4 gap-y-2">
            {TRACKS.map((item) => {
              const score = result.trackScores?.[item.id] ?? 0;
              return (
                <div key={item.id} className="contents">
                  <dt className={track === item.id ? 'font-bold' : 'v2-muted'}>{item.label}</dt>
                  <div className={`v2-bar ${track === item.id ? 'v2-bar--accent' : ''}`} aria-hidden="true">
                    <span style={{ width: `${(score / 5) * 100}%` }} />
                  </div>
                  <dd className="v2-num text-lg">{score.toFixed(1)}</dd>
                </div>
              );
            })}
          </dl>
        )}

        <section aria-labelledby="v2-result-depts" className="mt-12">
          <h2 id="v2-result-depts" className="v2-serif text-xl">
            學系
          </h2>
          <ol className="mt-3 border-t" style={{ borderColor: 'var(--v2-ink)' }}>
            {departments.map((dept, index) => (
              <li
                key={dept.name}
                className="grid grid-cols-[2.5rem_1fr_auto] items-center gap-x-3 border-b py-3 md:grid-cols-[3rem_14rem_1fr_auto]"
                style={{ borderColor: 'var(--v2-line)' }}
              >
                <span className={`v2-num ${index === 0 ? 'v2-accent text-3xl' : 'v2-faint text-xl'}`}>{index + 1}</span>
                <span className="min-w-0">
                  <span className={`block truncate ${index < 3 ? 'text-lg font-bold' : 'font-medium'}`}>{dept.name}</span>
                  <span className="v2-muted flex items-center gap-1.5 text-sm">
                    <span
                      className="h-2 w-2 rounded-full"
                      style={{ background: collegeHex(dept.college) }}
                      aria-hidden="true"
                    />
                    {dept.college}
                  </span>
                </span>
                <div className={`v2-bar hidden md:block ${index === 0 ? 'v2-bar--accent' : ''}`} aria-hidden="true">
                  <span style={{ width: `${(dept.score / 5) * 100}%` }} />
                </div>
                <span className="v2-num text-xl">{dept.score.toFixed(1)}</span>
              </li>
            ))}
          </ol>
        </section>

        {uncovered.length > 0 && (
          <section aria-labelledby="v2-result-more" className="v2-panel mt-10 p-5 md:p-6">
            <h2 id="v2-result-more" className="text-lg font-bold">
              還有 <span className="v2-num v2-accent text-2xl">{uncovered.length}</span> 個可報名的學系
            </h2>
            <ul className="mt-3 flex flex-wrap gap-1.5">
              {uncovered.map((dept) => (
                <li key={dept} className="v2-tag">
                  {dept}
                </li>
              ))}
            </ul>
            <button type="button" className="v2-btn mt-5" disabled={loading} onClick={() => void handleNextRound()}>
              再測一輪
              <HiArrowRight className="h-4 w-4" aria-hidden="true" />
            </button>
          </section>
        )}

        <div className="mt-12 grid gap-12 md:grid-cols-2">
          {colleges.length > 0 && (
            <section aria-labelledby="v2-result-colleges">
              <h2 id="v2-result-colleges" className="v2-serif text-xl">
                學院
              </h2>
              <ol className="mt-4 space-y-3">
                {colleges.map((college) => (
                  <li key={college.name} className="grid grid-cols-[7rem_1fr_2.5rem] items-center gap-3">
                    <span className="truncate text-sm font-medium">{college.name}</span>
                    <div className="v2-bar" aria-hidden="true">
                      <span style={{ width: `${(college.score / 5) * 100}%`, background: collegeHex(college.name) }} />
                    </div>
                    <span className="v2-num text-right">{college.score.toFixed(1)}</span>
                  </li>
                ))}
              </ol>
            </section>
          )}

          {tags.length > 0 && (
            <section aria-labelledby="v2-result-tags">
              <h2 id="v2-result-tags" className="v2-serif text-xl">
                興趣
              </h2>
              <ul className="mt-4 flex flex-wrap gap-2">
                {tags.map((tag) => (
                  <li
                    key={tag.tag}
                    className="inline-flex items-baseline gap-2 rounded-full border px-3 py-1.5"
                    style={{ borderColor: 'var(--v2-line-2)', background: 'var(--v2-surface)' }}
                  >
                    <span className="text-sm">{tag.tag}</span>
                    <span className="v2-num text-sm">{tag.score.toFixed(1)}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        <div className="mt-14 flex flex-wrap gap-3">
          <Link to={link('/curriculum')} className="v2-btn">
            看系所修課
            <HiArrowRight className="h-4 w-4" aria-hidden="true" />
          </Link>
          <button
            type="button"
            className="v2-btn v2-btn--ghost"
            onClick={() => {
              setStarted(false);
              setResult(null);
              setTrackType(null);
            }}
          >
            重新測評
          </button>
          {error && (
            <p role="alert" className="self-center text-sm" style={{ color: 'var(--v2-danger)' }}>
              {error}
            </p>
          )}
        </div>
      </div>
    );
  }

  // ── 作答 ──
  const current = questions[currentIndex];
  if (!current) return <Loading />;

  const prompts = current.questions?.length ? current.questions : ['這個研究主題讓你感興趣嗎？'];
  const scores = prompts.map((_, index) => answers.get(getAnswerKey(current.id, index)) || 0);
  const cardComplete = scores.every((score) => score > 0);
  const totalAnswers = questions.reduce((sum, question) => sum + getQuestionCount(question), 0);
  const remaining = totalAnswers - answers.size;
  const isLast = currentIndex === questions.length - 1;
  const sections = current.intro
    ? [{ label: '', text: current.intro }]
    : [
        { label: '動機', text: current.motivation },
        { label: '方法', text: current.method },
        { label: '結果', text: current.result },
      ].filter((section) => section.text);

  return (
    <div className="v2-container v2-container--narrow pb-28 pt-6 md:pt-10">
      <div className="flex items-center gap-4">
        <div
          className="v2-bar v2-bar--accent flex-1"
          role="progressbar"
          aria-label="作答進度"
          aria-valuemin={0}
          aria-valuemax={totalAnswers}
          aria-valuenow={answers.size}
        >
          <span
            className="transition-[width] duration-300"
            style={{ width: `${totalAnswers ? (answers.size / totalAnswers) * 100 : 0}%` }}
          />
        </div>
        <p className="v2-num text-lg" aria-label={`第 ${currentIndex + 1} 張，共 ${questions.length} 張`}>
          {currentIndex + 1}
          <span className="v2-faint text-sm"> / {questions.length}</span>
        </p>
      </div>

      <article key={current.id} className="v2-rise mt-8">
        <h1 ref={headingRef} tabIndex={-1} className="v2-serif text-2xl leading-snug outline-none md:text-3xl">
          {current.title}
        </h1>

        <div className="mt-5 space-y-4">
          {sections.map((section) => (
            <div key={section.label} className={section.label ? 'grid gap-x-4 gap-y-1 md:grid-cols-[3rem_1fr]' : ''}>
              {section.label && <h2 className="v2-faint pt-0.5 text-sm font-semibold">{section.label}</h2>}
              <p className="v2-muted leading-relaxed">{section.text}</p>
            </div>
          ))}
        </div>

        {current.tags.length > 0 && (
          <ul className="mt-5 flex flex-wrap gap-1.5" aria-label="領域">
            {current.tags.map((tag) => (
              <li key={tag} className="v2-tag">
                {tag}
              </li>
            ))}
          </ul>
        )}

        <div className="mt-8 border-t" style={{ borderColor: 'var(--v2-ink)' }}>
          <div className="v2-faint flex justify-between pt-3 text-sm" aria-hidden="true">
            <span>1 不感興趣</span>
            <span>很感興趣 5</span>
          </div>
          {prompts.map((prompt, promptIndex) => (
            <fieldset
              key={`${current.id}-${promptIndex}`}
              className="border-b py-5"
              style={{ borderColor: 'var(--v2-line)' }}
            >
              <legend className="float-left mb-3 w-full font-medium leading-relaxed">{prompt}</legend>
              <div className="clear-both grid grid-cols-5 gap-2">
                {SCORES.map((score) => (
                  <label key={score} className="cursor-pointer">
                    <input
                      type="radio"
                      className="peer sr-only"
                      name={`${current.id}-${promptIndex}`}
                      value={score}
                      checked={scores[promptIndex] === score}
                      onChange={() => handleScore(score, promptIndex)}
                      aria-label={`${score} 分${score === 1 ? '，不感興趣' : score === 5 ? '，很感興趣' : ''}`}
                    />
                    <span className="v2-num flex h-12 items-center justify-center rounded-lg border border-[var(--v2-line-2)] bg-[var(--v2-surface)] text-lg transition-colors hover:border-[var(--v2-ink)] peer-checked:border-[var(--v2-ink)] peer-checked:bg-[var(--v2-ink)] peer-checked:text-white peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-[var(--v2-focus)]">
                      {score}
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>
          ))}
        </div>
      </article>

      <div
        className="fixed inset-x-0 bottom-0 z-30 border-t"
        style={{ background: 'var(--v2-paper)', borderColor: 'var(--v2-line)' }}
      >
        <div className="v2-container v2-container--narrow flex items-center gap-3 py-3">
          <button
            type="button"
            className="v2-btn v2-btn--ghost"
            disabled={currentIndex === 0}
            onClick={handlePrevious}
          >
            <HiArrowLeft className="h-4 w-4" aria-hidden="true" />
            上一張
          </button>
          <p role="alert" className="min-w-0 flex-1 truncate text-center text-sm" style={{ color: 'var(--v2-danger)' }}>
            {error}
          </p>
          {isLast ? (
            <button
              type="button"
              className="v2-btn"
              disabled={remaining > 0 || loading}
              onClick={() => {
                setError('');
                void handleSubmit();
              }}
            >
              {remaining > 0 ? `還有 ${remaining} 題` : '看結果'}
            </button>
          ) : (
            <button type="button" className="v2-btn" disabled={!cardComplete} onClick={handleNext}>
              下一張
              <HiArrowRight className="h-4 w-4" aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
