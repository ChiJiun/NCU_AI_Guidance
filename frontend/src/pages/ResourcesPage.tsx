import { HiAcademicCap, HiCollection, HiExternalLink } from 'react-icons/hi';
import { departmentGroups, scoreResources, studyResources } from '../features/resources/links';


function ResourceCard({ title, description, href }: { title: string; description: string; href: string }) {
  return (
    <a href={href} target="_blank" rel="noreferrer" className="card-interactive block rounded-3xl p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="text-lg font-semibold text-slate-900">{title}</h3>
          <p className="resource-card-description mt-2 text-sm leading-6 text-slate-600">{description}</p>
        </div>
        <div className="rounded-full bg-slate-100 p-2 text-primary-700">
          <HiExternalLink className="h-5 w-5" />
        </div>
      </div>
    </a>
  );
}

export default function ResourcesPage() {
  return (
    <div className="page-animate pb-12">
      <section className="py-16 md:py-20">
        <div className="max-w-3xl">
          <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white/80 px-4 py-2 text-sm font-medium text-slate-700 shadow-soft">
            <HiCollection className="h-4 w-4 text-primary-700" />
            資源整理
          </div>
          <h1 className="mt-6 text-4xl font-bold tracking-tight text-slate-950 md:text-5xl">升學與校系資源</h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-slate-600 md:text-lg">
            這裡整理了落點分析工具、升學參考平台與中央大學各學院、系所官方網站，方便你快速查詢志願、校系資訊與延伸閱讀。
          </p>
        </div>
      </section>

      <section className="pb-12">
        <div className="mb-6 flex items-center gap-3">
          <div className="rounded-2xl bg-primary-100 p-2 text-primary-700">
            <HiExternalLink className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-2xl font-semibold text-slate-950">落點分析相關網站</h2>
            <p className="text-sm text-slate-500">查詢交叉查榜、招生簡章、錄取公告與成績落點分析工具。</p>
          </div>
        </div>
        <div className="grid gap-5 md:grid-cols-3">
          {scoreResources.map((resource) => (
            <ResourceCard key={resource.title} {...resource} />
          ))}
        </div>
      </section>

      <section className="pb-12">
        <div className="mb-6 flex items-center gap-3">
          <div className="rounded-2xl bg-primary-100 p-2 text-primary-700">
            <HiExternalLink className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-2xl font-semibold text-slate-950">升學參考平台</h2>
            <p className="text-sm text-slate-500">認識學群、學類、校系特色與學長姐經驗，輔助選系與生涯探索。</p>
          </div>
        </div>
        <div className="grid gap-5 md:grid-cols-3">
          {studyResources.map((resource) => (
            <ResourceCard key={resource.title} {...resource} />
          ))}
        </div>
      </section>

      <section className="pb-8">
        <div className="mb-6 flex items-center gap-3">
          <div className="rounded-2xl bg-primary-100 p-2 text-primary-700">
            <HiAcademicCap className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-2xl font-semibold text-slate-950">中央大學學院與系所</h2>
            <p className="text-sm text-slate-500">點選下方連結可前往各學院與系所官方網站。</p>
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          {departmentGroups.map((group) => (
            <section key={group.college} className="card rounded-3xl p-6">
              <h3 className="text-lg font-semibold text-slate-950">{group.college}</h3>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {group.links.map(([label, href]) => (
                  <a
                    key={label}
                    href={href}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center justify-between rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700 transition duration-200 hover:-translate-y-1 hover:border-primary-200 hover:bg-white hover:shadow-medium"
                  >
                    <span className="font-medium text-slate-900">{label}</span>
                    <HiExternalLink className="h-4 w-4 text-primary-600" />
                  </a>
                ))}
              </div>
            </section>
          ))}
        </div>
      </section>
    </div>
  );
}
