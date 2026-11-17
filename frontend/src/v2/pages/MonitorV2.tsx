import { useState, type ReactNode } from 'react';
import { HiRefresh } from 'react-icons/hi';
import type { DBStats, DepthStats, LLMLatency, MonitorStats, MonitorTrend } from '../../api/services';
import { isDeveloper } from '../../auth/developerUtils';
import {
  agentLabel,
  combineActivity,
  combinedDailyCost,
  courseRowCost,
  fmt,
  fmtUptime,
  ms,
  pdfRowCost,
  todayISO,
  type PickerMode,
  type TimeRangeState,
} from '../../features/monitor/monitorUtils';
import { useMonitor, type MonitorTabId } from '../../features/monitor/useMonitor';
import { Block, BarList, Columns, StatRow } from '../components/Charts';
import RovingGroup from '../components/RovingGroup';
import { V2_BASE } from '../paths';

const TABS: { id: MonitorTabId; label: string }[] = [
  { id: 'overview', label: '總覽' },
  { id: 'course', label: '課程推薦' },
  { id: 'pdf', label: '大專生計畫' },
  { id: 'database', label: '資料庫' },
  { id: 'activity', label: '對話活動' },
];

const usd = (value: number, digits = 4) => `$${value.toFixed(digits)}`;

/** 時間軸標籤：按小時顯示 00、01…；按日只留月-日 */
function axisLabels(rows: { date?: string; hour?: number }[], isHourly: boolean): string[] {
  return rows.map((row, index) => (isHourly ? String(row.hour ?? index).padStart(2, '0') : (row.date ?? '').slice(5)));
}

function Trend({ t }: { t?: MonitorTrend }) {
  if (!t) return null;
  if (t.change_pct === null) return <span className="v2-faint">前期無資料</span>;
  const up = t.change_pct >= 0;
  return (
    <span style={{ color: up ? 'var(--v2-ok)' : 'var(--v2-danger)' }}>
      {up ? '▲' : '▼'} {up ? '+' : ''}
      {t.change_pct}% vs 前期
    </span>
  );
}

function Dot({ ok }: { ok: boolean }) {
  return <span className="inline-block h-2 w-2 flex-none rounded-full" style={{ background: ok ? 'var(--v2-ok)' : 'var(--v2-danger)' }} aria-hidden="true" />;
}

function Muted({ children }: { children: ReactNode }) {
  return <p className="v2-faint py-6 text-sm">{children}</p>;
}

/** 表格：數字欄靠右；窄螢幕水平捲動（只在表格內捲，不撐開頁面） */
function Table({ head, rows, numeric = [] }: { head: string[]; rows: ReactNode[][]; numeric?: number[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b" style={{ borderColor: 'var(--v2-line-2)' }}>
            {head.map((title, index) => (
              <th key={title} scope="col" className={`v2-faint whitespace-nowrap px-2 py-2 font-normal ${numeric.includes(index) ? 'text-right' : 'text-left'}`}>
                {title}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex} className="border-b" style={{ borderColor: 'var(--v2-line)' }}>
              {row.map((cell, index) => (
                <td key={index} className={`whitespace-nowrap px-2 py-2.5 ${numeric.includes(index) ? 'v2-num text-right' : ''}`}>
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LatencyRow({ lat }: { lat: LLMLatency }) {
  return (
    <StatRow
      className="sm:!grid-cols-5"
      items={[
        { label: '平均', value: ms(lat.avg_ms) },
        { label: 'P95', value: ms(lat.p95_ms) },
        { label: 'P99', value: ms(lat.p99_ms) },
        { label: '最快', value: ms(lat.min_ms) },
        { label: '最慢', value: ms(lat.max_ms) },
      ]}
    />
  );
}

function TimeRange({ state, onChange, dateRange }: { state: TimeRangeState; onChange: (s: TimeRangeState) => void; dateRange: { start: string; end: string } }) {
  const set = (patch: Partial<TimeRangeState>) => onChange({ ...state, ...patch });
  const modes: [PickerMode, string][] = [
    ['preset', '近期'],
    ['day', '單日'],
    ['week', '週'],
    ['month', '月'],
  ];
  return (
    <div className="flex flex-wrap items-center gap-3">
      <RovingGroup role="radiogroup" aria-label="時間範圍" className="v2-seg">
        {modes.map(([mode, label]) => (
          <button key={mode} type="button" role="radio" aria-checked={state.mode === mode} className="!min-h-9 !px-3 !text-sm" onClick={() => set({ mode })}>
            {label}
          </button>
        ))}
      </RovingGroup>
      {state.mode === 'preset' && (
        <RovingGroup role="radiogroup" aria-label="近期範圍" className="v2-seg">
          {(['1d', '7d', '30d'] as const).map((preset) => (
            <button key={preset} type="button" role="radio" aria-checked={state.preset === preset} className="!min-h-9 !px-3 !text-sm" onClick={() => set({ preset })}>
              {preset === '1d' ? '今天' : preset === '7d' ? '7 天' : '30 天'}
            </button>
          ))}
        </RovingGroup>
      )}
      {state.mode === 'day' && (
        <input type="date" aria-label="日期" className="v2-input !w-auto" value={state.dayVal} max={todayISO()} onChange={(event) => set({ dayVal: event.target.value })} />
      )}
      {state.mode === 'week' && <input type="week" aria-label="週" className="v2-input !w-auto" value={state.weekVal} onChange={(event) => set({ weekVal: event.target.value })} />}
      {state.mode === 'month' && <input type="month" aria-label="月份" className="v2-input !w-auto" value={state.monthVal} onChange={(event) => set({ monthVal: event.target.value })} />}
      <span className="v2-faint text-sm tabular-nums">{dateRange.start === dateRange.end ? dateRange.start : `${dateRange.start} – ${dateRange.end}`}</span>
    </div>
  );
}

function OverviewTab({ stats, timeState, onTimeChange }: { stats: MonitorStats; timeState: TimeRangeState; onTimeChange: (s: TimeRangeState) => void }) {
  const combined = stats.combined;
  const courseAt = stats.course?.all_time ?? stats.all_time;
  const pdfAt = stats.pdf?.all_time;
  const isHourly = stats.date_range.start === stats.date_range.end;
  const cost = combinedDailyCost(stats.daily_trend, stats.pdf?.daily_trend ?? []);
  const pdfPeriod = stats.pdf?.period;

  return (
    <div className="space-y-14">
      <Block title="全時期">
        <StatRow
          className="lg:!grid-cols-6"
          items={[
            { label: '使用者', value: (combined?.total_users ?? courseAt.total_users).toLocaleString(), sub: '兩功能去重' },
            { label: '在線', value: combined?.online_now ?? courseAt.online_now, sub: '15 分鐘內' },
            { label: '課程推薦費用', value: usd(courseAt.estimated_cost_usd ?? 0), sub: stats.model_name },
            { label: '大專生計畫費用', value: usd(pdfAt?.estimated_cost_usd ?? 0), sub: 'gpt-4o + gpt-4o-mini' },
            { label: '合計費用', value: usd(combined?.total_cost_usd ?? 0), sub: 'USD' },
            { label: '對話輪數', value: fmt(combined?.total_turns ?? courseAt.total_turns), sub: '兩功能合計' },
          ]}
        />
        <p className="v2-faint mt-4 text-xs">
          單價（每 1M tokens，以 Azure 帳單為準）：課程推薦 {stats.model_name} $0.75／$4.50；大專生計畫 gpt-4o $2.50／$10.00；Router gpt-4o-mini $0.15／$0.60
        </p>
      </Block>

      <section>
        <TimeRange state={timeState} onChange={onTimeChange} dateRange={stats.date_range} />
        <div className="mt-8 grid gap-14 lg:grid-cols-2 lg:gap-10">
          <Block title="課程推薦" aside={<span className="v2-faint text-sm">{stats.model_name}</span>}>
            <StatRow
              items={[
                { label: '活躍使用者', value: stats.period.active_users, sub: <Trend t={stats.trends?.active_users} /> },
                { label: '對話輪數', value: stats.period.turns, sub: <Trend t={stats.trends?.turns} /> },
                { label: 'Token', value: fmt(stats.period.input_tokens + stats.period.output_tokens), sub: `≈ ${usd(stats.period.estimated_cost_usd)}` },
                { label: '平均深度', value: `${stats.period.avg_turns_per_session} 輪` },
              ]}
            />
            <div className="mt-8">
              <Columns
                label="課程推薦 Token 用量"
                labels={axisLabels(stats.daily_trend, isHourly)}
                series={[
                  { name: 'Input', values: stats.daily_trend.map((row) => row.input) },
                  { name: 'Output', values: stats.daily_trend.map((row) => row.output), tone: 'soft' },
                ]}
                format={fmt}
                empty="對話後開始記錄"
              />
            </div>
          </Block>

          <Block title="大專生計畫" aside={<span className="v2-faint text-sm">gpt-4o + gpt-4o-mini</span>}>
            {pdfPeriod ? (
              <>
                <StatRow
                  items={[
                    { label: '活躍使用者', value: pdfPeriod.active_users, sub: <Trend t={stats.pdf?.trends?.active_users} /> },
                    { label: '對話輪數', value: pdfPeriod.turns, sub: <Trend t={stats.pdf?.trends?.turns} /> },
                    { label: 'Token', value: fmt(pdfPeriod.input_tokens + pdfPeriod.output_tokens), sub: `≈ ${usd(pdfPeriod.estimated_cost_usd)}` },
                    { label: '平均深度', value: `${pdfPeriod.avg_turns_per_session.toFixed(1)} 輪` },
                  ]}
                />
                <div className="mt-8">
                  <Columns
                    label="大專生計畫 Token 用量"
                    labels={axisLabels(stats.pdf?.daily_trend ?? [], isHourly)}
                    series={[
                      { name: 'Input', values: (stats.pdf?.daily_trend ?? []).map((row) => row.input) },
                      { name: 'Output', values: (stats.pdf?.daily_trend ?? []).map((row) => row.output), tone: 'soft' },
                    ]}
                    format={fmt}
                    empty="對話後開始記錄"
                  />
                </div>
              </>
            ) : (
              <Muted>尚無對話資料</Muted>
            )}
          </Block>
        </div>
      </section>

      {!isHourly && (
        <Block title="每日費用">
          <Columns
            label="每日費用"
            labels={cost.dates.map((date) => date.slice(5))}
            series={[
              { name: '課程推薦', values: cost.courseCosts },
              { name: '大專生計畫', values: cost.pdfCosts, tone: 'soft' },
            ]}
            format={(value) => usd(value, 5)}
            empty="尚無費用記錄"
          />
        </Block>
      )}
    </div>
  );
}

function CourseTab({ stats }: { stats: MonitorStats }) {
  const isHourly = stats.date_range.start === stats.date_range.end;
  const lat = stats.period.llm_latency;
  const { input_tokens, output_tokens } = stats.period;
  const ratio = output_tokens > 0 ? (input_tokens / output_tokens).toFixed(1) : '—';
  const trend = stats.course?.daily_trend ?? stats.daily_trend;
  const tools = [...(stats.course?.tools_usage ?? stats.tools_usage)].sort((a, b) => b.count - a.count);
  const latencyTrend = stats.period.llm_latency_trend;

  return (
    <div className="space-y-14">
      <StatRow
        items={[
          { label: '模型', value: <span className="text-2xl">{stats.model_name}</span>, sub: 'Azure OpenAI · Global' },
          { label: 'Input／Output', value: `${ratio} : 1`, sub: '每個 output token 對應的 input' },
          { label: '時段費用', value: usd(stats.period.estimated_cost_usd) },
          { label: '對話', value: lat ? lat.count : '—', sub: '有延遲紀錄' },
        ]}
      />

      <Block title="回應延遲">{lat ? <LatencyRow lat={lat} /> : <Muted>尚無延遲資料（新對話後開始記錄）</Muted>}</Block>

      <div className="grid gap-14 lg:grid-cols-2 lg:gap-10">
        <Block title="延遲趨勢" aside={<span className="v2-faint text-sm">平均</span>}>
          <Columns label="課程推薦延遲趨勢" labels={axisLabels(latencyTrend, isHourly)} series={[{ name: '平均', values: latencyTrend.map((row) => row.avg_ms) }]} format={ms} />
        </Block>
        <Block title="Token 用量">
          <Columns
            label="課程推薦 Token 用量"
            labels={axisLabels(trend, isHourly)}
            series={[
              { name: 'Input', values: trend.map((row) => row.input) },
              { name: 'Output', values: trend.map((row) => row.output), tone: 'soft' },
            ]}
            format={fmt}
          />
        </Block>
      </div>

      <div className="grid gap-14 lg:grid-cols-2 lg:gap-10">
        <Block title="估算費用">
          <Columns label="課程推薦估算費用" labels={axisLabels(trend, isHourly)} series={[{ name: '費用', values: trend.map(courseRowCost) }]} format={(value) => usd(value, 5)} />
        </Block>
        <Block title="工具使用" aside={<span className="v2-faint text-sm">{tools.length} 種</span>}>
          <BarList items={tools.map((tool) => ({ label: tool.label, value: tool.count }))} empty="尚無紀錄" />
        </Block>
      </div>
    </div>
  );
}

function PdfTab({ stats }: { stats: MonitorStats }) {
  const pdf = stats.pdf;
  if (!pdf?.period) return <Muted>尚無大專生計畫對話資料</Muted>;

  const isHourly = stats.date_range.start === stats.date_range.end;
  const agentModel = stats.pdf_model_name ?? 'gpt-4o';
  const routerModel = stats.pdf_router_model_name ?? 'gpt-4o-mini';
  const { period, all_time, trends, daily_trend } = pdf;
  const agentCost = period.estimated_cost_breakdown?.agent_usd ?? 0;
  const routerCost = period.estimated_cost_breakdown?.router_usd ?? 0;
  const agentInp = Math.max(0, period.input_tokens - period.router_input_tokens);
  const agentOut = Math.max(0, period.output_tokens - period.router_output_tokens);
  const routerShare = period.estimated_cost_usd > 0 ? ((routerCost / period.estimated_cost_usd) * 100).toFixed(1) : '0.0';

  return (
    <div className="space-y-14">
      <StatRow
        items={[
          { label: '活躍使用者', value: period.active_users, sub: <>新增 {period.new_users} 人 · <Trend t={trends?.active_users} /></> },
          { label: '對話輪數', value: period.turns, sub: <>{period.sessions} sessions · <Trend t={trends?.turns} /></> },
          { label: 'Token', value: fmt(period.input_tokens + period.output_tokens), sub: <>≈ {usd(period.estimated_cost_usd)} · <Trend t={trends?.tokens} /></> },
          { label: '平均深度', value: `${period.avg_turns_per_session.toFixed(1)} 輪`, sub: '每 session' },
        ]}
      />

      <div className="grid gap-14 lg:grid-cols-2 lg:gap-10">
        <Block title={`${agentModel}（Agent）`} aside={<span className="v2-faint text-sm">$2.50／$10.00 per 1M</span>}>
          <StatRow
            className="!grid-cols-2"
            items={[
              { label: '時段費用', value: usd(agentCost, 5), sub: `Input ${fmt(agentInp)} · Output ${fmt(agentOut)}` },
              { label: '累計費用', value: usd(all_time?.estimated_cost_usd ?? 0), sub: '所有模型合計' },
            ]}
          />
        </Block>
        <Block title={`${routerModel}（Router）`} aside={<span className="v2-faint text-sm">$0.15／$0.60 per 1M</span>}>
          <StatRow
            className="!grid-cols-2"
            items={[
              { label: '時段費用', value: usd(routerCost, 5), sub: `Input ${fmt(period.router_input_tokens)} · Output ${fmt(period.router_output_tokens)}` },
              { label: 'Router 佔比', value: `${routerShare}%` },
            ]}
          />
        </Block>
      </div>

      <div className="grid gap-14 lg:grid-cols-2 lg:gap-10">
        <Block title="Agent 路由">
          <BarList
            items={[...period.agent_distribution].sort((a, b) => b.cnt - a.cnt).map((row) => ({ label: agentLabel(row.agent_name), value: row.cnt, display: `${row.cnt} 次` }))}
          />
        </Block>
        <Block title="各 Agent 延遲">
          {period.latency_by_agent.length > 0 ? (
            <Table
              head={['Agent', '次數', '平均', 'P95']}
              numeric={[1, 2, 3]}
              rows={period.latency_by_agent.map((row) => [agentLabel(row.agent_name), row.cnt, ms(row.avg_ms), ms(row.p95_ms)])}
            />
          ) : (
            <Muted>尚無資料</Muted>
          )}
        </Block>
      </div>

      {period.llm_latency && (
        <Block title="端到端延遲" aside={<span className="v2-faint text-sm">{period.llm_latency.count} 次</span>}>
          <LatencyRow lat={period.llm_latency} />
        </Block>
      )}

      <div className="grid gap-14 lg:grid-cols-2 lg:gap-10">
        <Block title="延遲趨勢" aside={<span className="v2-faint text-sm">平均</span>}>
          <Columns
            label="大專生計畫延遲趨勢"
            labels={axisLabels(period.llm_latency_trend, isHourly)}
            series={[{ name: '平均', values: period.llm_latency_trend.map((row) => row.avg_ms) }]}
            format={ms}
          />
        </Block>
        <Block title="估算費用">
          <Columns label="大專生計畫估算費用" labels={axisLabels(daily_trend, isHourly)} series={[{ name: '費用', values: daily_trend.map(pdfRowCost) }]} format={(value) => usd(value, 5)} />
        </Block>
      </div>

      {all_time && (
        <Block title="全時期">
          <StatRow
            items={[
              { label: 'Sessions', value: all_time.total_sessions.toLocaleString() },
              { label: '對話輪數', value: fmt(all_time.total_turns) },
              { label: 'Token', value: fmt(all_time.total_input + all_time.total_output), sub: 'input + output' },
              { label: '累計費用', value: usd(all_time.estimated_cost_usd), sub: 'USD' },
            ]}
          />
        </Block>
      )}
    </div>
  );
}

function DatabaseTab({ dbStats, loading }: { dbStats: DBStats | null; loading: boolean }) {
  if (loading) {
    return (
      <div role="status" className="flex items-center gap-2 py-6">
        <span className="v2-spinner" aria-hidden="true" />
        <span className="v2-muted text-sm">載入中</span>
      </div>
    );
  }
  if (!dbStats) return <Muted>載入失敗</Muted>;

  const { infra, postgres: pg, qdrant: qd, cloudinary: cl, cloudinary_error: clErr } = dbStats;
  const qdDebug = dbStats.qdrant_debug;
  const cacheOk = pg.cache_hit_pct >= 95;

  return (
    <div className="space-y-14">
      <StatRow
        items={[
          { label: 'Render 後端', value: fmtUptime(infra.server_uptime_seconds), sub: '本次啟動後（冷啟動會重置）' },
          { label: 'Neon PostgreSQL', value: pg.db_size, sub: `${infra.neon_region} · Cache ${pg.cache_hit_pct}%` },
          { label: 'Qdrant Cloud', value: infra.qdrant_total_points.toLocaleString(), sub: `${infra.qdrant_region} · ${qd.collections.length} collections` },
          cl
            ? { label: `Cloudinary（${cl.plan}）`, value: `${cl.total_resources} PDF`, sub: `${cl.storage_pretty} · 本月 ${cl.bandwidth_pretty}` }
            : { label: 'Cloudinary', value: '—', sub: clErr ?? '無法取得' },
        ]}
      />

      <Block title="PostgreSQL" aside={<span className="v2-faint text-sm">連線 {pg.connections} · Cache <span style={{ color: cacheOk ? 'var(--v2-ok)' : 'var(--v2-danger)' }}>{pg.cache_hit_pct}%</span></span>}>
        <Table head={['Table', 'Rows', 'Size']} numeric={[1, 2]} rows={pg.tables.map((table) => [<code key="n" className="text-xs">{table.name}</code>, table.rows.toLocaleString(), table.size_pretty])} />
      </Block>

      <Block title="Qdrant">
        {qd.collections.length === 0 ? (
          <div className="space-y-1 text-sm">
            <p style={{ color: 'var(--v2-danger)' }}>無法取得 Collection 資料</p>
            {qdDebug && (
              <>
                <p className="v2-muted break-all font-mono text-xs">{qdDebug.url}</p>
                <p className="v2-muted break-all text-xs">{qdDebug.error || 'unknown error'}</p>
                <p className="v2-faint text-xs">
                  QDRANT_URL {qdDebug.configured ? '已設定' : '未設定'} · API Key {qdDebug.api_key_set ? '已設定' : '未設定'}
                </p>
              </>
            )}
          </div>
        ) : (
          <Table
            head={['Collection', 'Points', 'Segments', 'Optimizer', 'Status']}
            numeric={[1, 2]}
            rows={qd.collections.map((c) => [
              <code key="n" className="text-xs">{c.name}</code>,
              c.points_count.toLocaleString(),
              c.segments_count,
              c.optimizer_ok ? '正常' : '最佳化中',
              <span key="s" className="inline-flex items-center gap-1.5">
                <Dot ok={c.status === 'green'} />
                {c.status}
              </span>,
            ])}
          />
        )}
      </Block>
    </div>
  );
}

type ActivityFeature = 'all' | 'course' | 'pdf';

function ActivityTab({ stats }: { stats: MonitorStats }) {
  const [feature, setFeature] = useState<ActivityFeature>('all');
  const courseActivity = stats.course?.activity_trend ?? stats.activity_trend;
  const pdfActivity = stats.pdf?.activity_trend ?? [];
  const activity = feature === 'course' ? courseActivity : feature === 'pdf' ? pdfActivity : combineActivity(courseActivity, pdfActivity);
  const coursePeak = stats.course?.peak_hours ?? stats.peak_hours;
  const pdfPeak = stats.pdf?.peak_hours ?? [];
  const tools = [...(stats.course?.tools_usage ?? stats.tools_usage)].sort((a, b) => b.count - a.count);

  const courseP = stats.period;
  const pdfP = stats.pdf?.period;
  const activeUsers = feature === 'pdf' ? (pdfP?.active_users ?? 0) : courseP.active_users;
  const newUsers = feature === 'pdf' ? (pdfP?.new_users ?? 0) : courseP.new_users;
  const returning = Math.max(0, activeUsers - newUsers);
  const share = (n: number) => `${activeUsers > 0 ? Math.round((n / activeUsers) * 100) : 0}%`;

  const depthRows: [string, DepthStats][] = [];
  if (feature !== 'pdf' && courseP.depth_stats) depthRows.push(['課程推薦', courseP.depth_stats]);
  if (feature !== 'course' && pdfP?.depth_stats) depthRows.push(['大專生計畫', pdfP.depth_stats]);
  const depthTrend = activity.filter((row) => row.sessions > 0);

  return (
    <div className="space-y-14">
      <RovingGroup role="radiogroup" aria-label="功能" className="v2-seg">
        {(['all', 'course', 'pdf'] as const).map((value) => (
          <button key={value} type="button" role="radio" aria-checked={feature === value} onClick={() => setFeature(value)}>
            {value === 'all' ? '合計' : value === 'course' ? '課程推薦' : '大專生計畫'}
          </button>
        ))}
      </RovingGroup>

      <StatRow
        className="lg:!grid-cols-5"
        items={[
          { label: '活躍使用者', value: activeUsers },
          { label: '新使用者', value: newUsers, sub: share(newUsers) },
          { label: '回訪使用者', value: returning, sub: share(returning) },
          { label: 'Sessions', value: (feature === 'pdf' ? (pdfP?.sessions ?? 0) : courseP.sessions).toLocaleString() },
          { label: '對話輪數', value: (feature === 'pdf' ? (pdfP?.turns ?? 0) : courseP.turns).toLocaleString() },
        ]}
      />

      <div className="grid gap-14 lg:grid-cols-2 lg:gap-10">
        <Block title="對話深度" aside={<span className="v2-faint text-sm">每 session 輪數</span>}>
          {depthRows.length > 0 ? (
            <Table
              head={['', '最少', 'Q1', '中位數', 'Q3', '最多', '平均']}
              numeric={[1, 2, 3, 4, 5, 6]}
              rows={depthRows.map(([name, d]) => [name, d.min, d.q1, d.median, d.q3, d.max, d.avg.toFixed(1)])}
            />
          ) : (
            <Muted>尚無資料</Muted>
          )}
        </Block>
        <Block title="平均深度趨勢">
          <Columns
            label="每日平均對話深度"
            labels={depthTrend.map((row) => row.date.slice(5))}
            series={[{ name: '輪／session', values: depthTrend.map((row) => +(row.turns / row.sessions).toFixed(2)) }]}
            format={(value) => `${value} 輪`}
          />
        </Block>
      </div>

      <Block title="對話活動">
        <Columns
          label="每日對話活動"
          labels={activity.map((row) => row.date.slice(5))}
          series={[
            { name: 'Sessions', values: activity.map((row) => row.sessions) },
            { name: 'Turns', values: activity.map((row) => row.turns), tone: 'soft' },
          ]}
        />
      </Block>

      <div className="grid gap-14 lg:grid-cols-2 lg:gap-10">
        {feature !== 'pdf' && (
          <Block title="課程推薦活躍時段">
            <Columns label="課程推薦各小時對話輪數" labels={coursePeak.map((row) => String(row.hour).padStart(2, '0'))} series={[{ name: '輪數', values: coursePeak.map((row) => row.turns) }]} />
          </Block>
        )}
        {feature !== 'course' && pdfPeak.length > 0 && (
          <Block title="大專生計畫活躍時段">
            <Columns label="大專生計畫各小時對話輪數" labels={pdfPeak.map((row) => String(row.hour).padStart(2, '0'))} series={[{ name: '輪數', values: pdfPeak.map((row) => row.turns) }]} />
          </Block>
        )}
        {feature !== 'pdf' && (
          <Block title="工具使用">
            <BarList items={tools.map((tool) => ({ label: tool.label, value: tool.count }))} empty="尚無紀錄" />
          </Block>
        )}
      </div>
    </div>
  );
}

/** 系統監控（只給開發者；非開發者由 useMonitor 導回新版首頁）。 */
export default function MonitorV2() {
  const {
    user, authLoading,
    activeTab, setActiveTab,
    timeState, setTimeState,
    refreshSec, setRefreshSec,
    countdown, setCountdown,
    stats, dbStats, dbLoading,
    loading, error, lastAt,
    doRefresh,
  } = useMonitor(V2_BASE);

  // 確認身分前、以及非開發者被導走之前，什麼都不顯示
  if (authLoading || !isDeveloper(user?.email)) return null;

  const ok = stats ? stats.system_health.postgres === 'ok' && stats.system_health.qdrant === 'ok' : null;
  const chatLat = stats?.latency_stats.find((entry) => entry.endpoint === '/api/chat');

  return (
    <div className="v2-container !max-w-[90rem] pb-20 pt-10 md:pt-12">
      <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div>
          <h1 className="v2-serif text-4xl">系統監控</h1>
          <p className="v2-muted mt-2 flex flex-wrap items-center gap-x-3 text-sm" aria-live="polite">
            {ok !== null && (
              <span className="inline-flex items-center gap-1.5 font-semibold" style={{ color: ok ? 'var(--v2-ok)' : 'var(--v2-danger)' }}>
                <Dot ok={ok} />
                {ok ? '全部正常' : '異常'}
              </span>
            )}
            {lastAt && !loading && (
              <span className="tabular-nums">
                {lastAt.toLocaleTimeString('zh-TW')} 更新 · {countdown} 秒後重新整理
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <RovingGroup role="radiogroup" aria-label="自動更新間隔" className="v2-seg">
            {([30, 60, 300] as const).map((sec) => (
              <button
                key={sec}
                type="button"
                role="radio"
                aria-checked={refreshSec === sec}
                className="!min-h-9 !px-3 !text-sm"
                onClick={() => {
                  setRefreshSec(sec);
                  setCountdown(sec);
                }}
              >
                {sec < 60 ? `${sec} 秒` : sec === 60 ? '1 分' : '5 分'}
              </button>
            ))}
          </RovingGroup>
          <button type="button" className="v2-iconbtn" aria-label="立即重新整理" onClick={doRefresh}>
            <HiRefresh className={`h-5 w-5 ${loading ? 'animate-spin' : ''}`} aria-hidden="true" />
          </button>
        </div>
      </header>

      <ul className="v2-muted mt-6 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm" aria-label="服務狀態">
        {stats ? (
          <>
            <li className="inline-flex items-center gap-1.5">
              <Dot ok />
              Render
            </li>
            <li className="inline-flex items-center gap-1.5">
              <Dot ok={stats.system_health.postgres === 'ok'} />
              PostgreSQL
            </li>
            <li className="inline-flex min-w-0 items-center gap-1.5">
              <Dot ok={stats.system_health.qdrant === 'ok'} />
              Qdrant
              {stats.system_health.qdrant === 'error' && stats.qdrant_debug && (
                <span className="truncate text-xs" style={{ color: 'var(--v2-danger)' }} title={`${stats.qdrant_debug.url} · ${stats.qdrant_debug.error || 'unknown error'}`}>
                  {stats.qdrant_debug.error || 'unknown error'}
                </span>
              )}
            </li>
            {chatLat && (
              <li className="inline-flex items-center gap-1.5">
                <Dot ok={chatLat.error_rate_pct <= 5} />
                /api/chat <span className="v2-faint tabular-nums">{chatLat.avg_ms.toFixed(0)}ms</span>
              </li>
            )}
          </>
        ) : (
          <li>檢查中…</li>
        )}
      </ul>

      {error && (
        <p role="alert" className="mt-6 text-sm" style={{ color: 'var(--v2-danger)' }}>
          {error}
          <button type="button" className="ml-2 underline" onClick={doRefresh}>
            重試
          </button>
        </p>
      )}

      {/* 手機寬度放不下五個分頁：延伸到螢幕邊緣橫向捲動，讓被切到的分頁看得出可以往右滑 */}
      <div className="v2-scroll -mx-5 mt-8 overflow-x-auto px-5 md:mx-0 md:px-0">
        <RovingGroup role="tablist" aria-label="監控項目" className="v2-seg">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`monitor-tab-${tab.id}`}
              aria-selected={activeTab === tab.id}
              aria-controls="monitor-panel"
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </RovingGroup>
      </div>

      <div id="monitor-panel" role="tabpanel" aria-labelledby={`monitor-tab-${activeTab}`} className="mt-10">
        {!stats && activeTab !== 'database' && !error && (
          <div role="status" className="flex items-center gap-2">
            <span className="v2-spinner" aria-hidden="true" />
            <span className="v2-muted text-sm">載入中</span>
          </div>
        )}
        {stats && activeTab === 'overview' && <OverviewTab stats={stats} timeState={timeState} onTimeChange={setTimeState} />}
        {stats && activeTab === 'course' && <CourseTab stats={stats} />}
        {stats && activeTab === 'pdf' && <PdfTab stats={stats} />}
        {activeTab === 'database' && <DatabaseTab dbStats={dbStats} loading={dbLoading} />}
        {stats && activeTab === 'activity' && <ActivityTab stats={stats} />}
      </div>
    </div>
  );
}
