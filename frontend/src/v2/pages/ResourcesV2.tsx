import type { ReactNode } from 'react';
import { HiArrowUpRight } from 'react-icons/hi2';
import { departmentGroups, scoreResources, studyResources } from '../../features/resources/links';
import type { ResourceLink } from '../../features/resources/links';

/** 外部連結都另開分頁；箭頭表示「離開本站」 */
function ExternalRow({ link }: { link: ResourceLink }) {
  return (
    <li>
      <a href={link.href} target="_blank" rel="noopener noreferrer" className="v2-row group !items-start !px-1 !py-4">
        <span className="min-w-0 flex-1">
          <span className="block font-semibold">{link.title}</span>
          <span className="v2-muted mt-0.5 block text-sm leading-relaxed">{link.description}</span>
        </span>
        <HiArrowUpRight
          className="v2-faint mt-1 h-4 w-4 flex-none transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5"
          aria-hidden="true"
        />
        <span className="sr-only">（另開新分頁）</span>
      </a>
    </li>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="grid gap-4 border-t pt-4 md:grid-cols-[14rem_1fr] md:gap-10" style={{ borderColor: 'var(--v2-ink)' }}>
      <h2 className="v2-serif text-2xl">{title}</h2>
      {children}
    </section>
  );
}

export default function ResourcesV2() {
  return (
    <div className="v2-container pb-20 pt-12 md:pt-16">
      <h1 className="v2-serif text-4xl md:text-5xl">資源連結</h1>

      <div className="mt-12 space-y-14">
        <Section title="落點分析">
          <ul>
            {scoreResources.map((link) => (
              <ExternalRow key={link.href} link={link} />
            ))}
          </ul>
        </Section>

        <Section title="升學參考">
          <ul>
            {studyResources.map((link) => (
              <ExternalRow key={link.href} link={link} />
            ))}
          </ul>
        </Section>

        <Section title="中大系所">
          <div className="grid gap-x-10 gap-y-8 sm:grid-cols-2 xl:grid-cols-3">
            {departmentGroups.map((group) => (
              <div key={group.college}>
                <h3 className="v2-faint text-sm">{group.college}</h3>
                <ul className="mt-1">
                  {group.links.map(([label, href]) => (
                    <li key={href}>
                      <a
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="v2-row group !min-h-11 !px-1 !py-2"
                      >
                        <span className="min-w-0 flex-1">{label}</span>
                        <HiArrowUpRight className="v2-faint h-3.5 w-3.5 flex-none" aria-hidden="true" />
                        <span className="sr-only">（另開新分頁）</span>
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Section>
      </div>
    </div>
  );
}
