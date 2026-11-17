import { Link } from 'react-router-dom';
import { HiArrowRight } from 'react-icons/hi';
import { ASSISTANT_LABELS, CATEGORY_LABELS, DEMO_CASES, SHOW_UNREVIEWED } from '../../demo/cases';
import type { DemoAssistant } from '../../demo/types';
import { useDemoGallery } from '../../features/demo/useDemoGallery';
import RovingGroup from '../components/RovingGroup';
import { v2Link } from '../paths';

const ASSISTANTS = Object.keys(ASSISTANT_LABELS) as DemoAssistant[];

export default function DemoGalleryV2() {
  const { assistant, category, counts, categoriesPresent, visible, setFilter } = useDemoGallery();

  return (
    <div className="v2-container pb-20 pt-12 md:pt-16">
      <h1 className="v2-serif text-4xl md:text-5xl">AI 示範案例</h1>

      {DEMO_CASES.length === 0 ? (
        <div className="mt-12 border-t pt-6" style={{ borderColor: 'var(--v2-ink)' }}>
          <p className="font-semibold">目前還沒有示範案例</p>
          {SHOW_UNREVIEWED && (
            <p className="v2-muted mt-1 text-sm">
              用 scripts/demo/record_demo_cases.py 錄製並人工檢查後，標記為 approved 才會出現在正式版。
            </p>
          )}
        </div>
      ) : (
        <>
          <div className="mt-10 flex flex-wrap items-center gap-x-6 gap-y-4">
            <RovingGroup role="radiogroup" aria-label="助理" className="v2-seg">
              <button type="button" role="radio" aria-checked={!assistant} onClick={() => setFilter('assistant', null)}>
                全部
              </button>
              {ASSISTANTS.map((key) => (
                <button
                  key={key}
                  type="button"
                  role="radio"
                  aria-checked={assistant === key}
                  onClick={() => setFilter('assistant', key)}
                >
                  {ASSISTANT_LABELS[key]}
                  <span className="v2-num v2-faint ml-1.5 text-sm">{counts[key]}</span>
                </button>
              ))}
            </RovingGroup>

            {categoriesPresent.length > 1 && (
              <div role="group" aria-label="情境" className="flex flex-wrap gap-2">
                {categoriesPresent.map((key) => (
                  <button
                    key={key}
                    type="button"
                    className="v2-chip v2-chip--sm"
                    aria-pressed={category === key}
                    onClick={() => setFilter('category', category === key ? null : key)}
                  >
                    {CATEGORY_LABELS[key]}
                  </button>
                ))}
              </div>
            )}
          </div>

          {visible.length === 0 ? (
            <p className="v2-muted mt-10">沒有符合條件的案例。</p>
          ) : (
            <ol className="mt-8 border-t" style={{ borderColor: 'var(--v2-ink)' }}>
              {visible.map((demo, index) => (
                <li key={demo.id}>
                  <Link to={v2Link(`/demo/${demo.id}`)} className="v2-row group !items-start !gap-4 !px-1 !py-5">
                    <span className="v2-num v2-faint w-7 flex-none pt-1 text-sm">{String(index + 1).padStart(2, '0')}</span>
                    <span className="min-w-0 flex-1">
                      <span className="v2-faint flex flex-wrap gap-x-3 text-sm">
                        <span>{ASSISTANT_LABELS[demo.assistant]}</span>
                        <span>{CATEGORY_LABELS[demo.category]}</span>
                        {demo.review.status !== 'approved' && <span className="v2-accent font-semibold">待人工檢查</span>}
                      </span>
                      <span className="v2-serif mt-1 block text-xl leading-snug">{demo.title}</span>
                      <span className="v2-muted mt-1 line-clamp-2 block text-sm leading-relaxed">{demo.scenario}</span>
                    </span>
                    <HiArrowRight
                      className="v2-faint mt-2 h-4 w-4 flex-none transition-transform group-hover:translate-x-1"
                      aria-hidden="true"
                    />
                  </Link>
                </li>
              ))}
            </ol>
          )}
        </>
      )}
    </div>
  );
}
