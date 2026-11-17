import { useMemo, useState } from 'react';
import ReactECharts from 'echarts-for-react';
import {
  HiCheckCircle, HiXCircle, HiRefresh,
  HiTrendingUp, HiTrendingDown,
  HiDatabase, HiServer, HiChip, HiChatAlt2, HiDocumentText, HiAcademicCap,
} from 'react-icons/hi';
import {
  type MonitorStats, type MonitorTrend,
  type LLMLatency, type DBStats, type PdfStats, type CombinedStats, type DepthStats,
} from '../api/services';
import {
  agentLabel,
  combineActivity,
  combinedDailyCost,
  courseRowCost,
  fmt,
  fmtUptime,
  ms,
  todayISO,
  type PickerMode,
  type TimeRangeState,
} from '../features/monitor/monitorUtils';
import { useMonitor, type MonitorTabId } from '../features/monitor/useMonitor';

type TipParam = { marker: string; seriesName: string; value: number; name: string; axisValue: string; seriesIndex: number };

// ── ECharts 深色共用 ──────────────────────────────────────────────
const TIP = { backgroundColor: '#0f172a', borderColor: '#334155', textStyle: { color: '#e2e8f0' } };
const AX  = {
  axisLine: { lineStyle: { color: '#334155' } },
  splitLine: { lineStyle: { color: '#1e293b' } },
  axisLabel: { color: '#94a3b8', fontSize: 11 },
};

// ── 共用組件 ──────────────────────────────────────────────────────
function Trend({ t }: { t: MonitorTrend }) {
  const p = t.change_pct;
  if (p === null) return <span className="text-slate-600 text-[11px]">— 前期無資料</span>;
  const up = p >= 0;
  return (
    <span className={`inline-flex items-center gap-0.5 text-[11px] font-medium ${up?'text-emerald-400':'text-red-400'}`}>
      {up ? <HiTrendingUp className="h-3 w-3"/> : <HiTrendingDown className="h-3 w-3"/>}
      {up?'+':''}{p}% vs 前期
    </span>
  );
}

function Stat({ label, value, sub, trend }: {
  label: string; value: string|number; sub?: string; trend?: MonitorTrend;
}) {
  return (
    <div className="flex flex-col gap-1 py-4 px-5 border-r border-slate-800 last:border-r-0">
      <span className="text-[11px] uppercase tracking-wide text-slate-500">{label}</span>
      <span className="text-2xl font-semibold text-slate-100 tabular-nums leading-tight">
        {typeof value==='number'?value.toLocaleString():value}
      </span>
      <div className="flex items-center gap-2 min-h-[16px]">
        {trend && <Trend t={trend}/>}
        {sub && <span className="text-[11px] text-slate-600">{sub}</span>}
      </div>
    </div>
  );
}

function Section({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
      <div className="mb-3 flex items-baseline gap-2">
        <span className="text-sm font-medium text-slate-300">{title}</span>
        {sub && <span className="text-xs text-slate-600">{sub}</span>}
      </div>
      {children}
    </div>
  );
}

function ServiceDot({ label, ok, extra }: { label: string; ok: boolean; extra?: string }) {
  return (
    <span className="flex items-center gap-1.5 text-xs text-slate-400">
      <span className={`h-1.5 w-1.5 rounded-full ${ok?'bg-emerald-500':'bg-red-500'}`}/>
      {label}
      {extra && <span className={ok?'text-slate-600':'text-red-400'}>{extra}</span>}
    </span>
  );
}

function LatencyGrid({ lat }: { lat: LLMLatency }) {
  const items = [
    { label: 'avg', value: lat.avg_ms },
    { label: 'P95', value: lat.p95_ms },
    { label: 'P99', value: lat.p99_ms },
    { label: 'min', value: lat.min_ms },
    { label: 'max', value: lat.max_ms },
  ];
  return (
    <div className="grid grid-cols-5 divide-x divide-slate-800 rounded-xl border border-slate-800 bg-slate-900">
      {items.map(i => (
        <div key={i.label} className="flex flex-col items-center py-3 gap-0.5">
          <span className="text-[11px] uppercase text-slate-500">{i.label}</span>
          <span className="text-lg font-semibold text-slate-100 tabular-nums">{ms(i.value)}</span>
        </div>
      ))}
    </div>
  );
}

// ── ECharts 圖表 ──────────────────────────────────────────────────
function TokenChart({ daily_trend, isHourly }: { daily_trend: MonitorStats['daily_trend']; isHourly: boolean }) {
  const xData = isHourly
    ? Array.from({length:24},(_,i)=>`${String(i).padStart(2,'0')}:00`)
    : daily_trend.map(r=>r.date??'');
  const inp = daily_trend.map(r=>r.input);
  const out = daily_trend.map(r=>r.output);
  const hasData = inp.some(v=>v>0)||out.some(v=>v>0);
  const opt = {
    backgroundColor:'transparent', grid:{left:54,right:16,top:12,bottom:36},
    legend:{data:['Input','Output'],bottom:0,textStyle:{color:'#94a3b8',fontSize:11}},
    tooltip:{...TIP,trigger:'axis',formatter:(p:TipParam[])=>p.map(x=>`${x.marker}${x.seriesName}: <b>${fmt(x.value)}</b>`).join('<br/>')},
    xAxis:{type:'category',data:xData,boundaryGap:false,...AX},
    yAxis:{type:'value',...AX,axisLabel:{...AX.axisLabel,formatter:fmt}},
    series:[
      {name:'Input',type:'line',smooth:true,data:inp,symbol:'none',lineStyle:{color:'#6366f1',width:2},itemStyle:{color:'#6366f1'},
       areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(99,102,241,.25)'},{offset:1,color:'rgba(99,102,241,.02)'}]}}},
      {name:'Output',type:'line',smooth:true,data:out,symbol:'none',lineStyle:{color:'#0ea5e9',width:2},itemStyle:{color:'#0ea5e9'},
       areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(14,165,233,.2)'},{offset:1,color:'rgba(14,165,233,.02)'}]}}},
    ],
  };
  return hasData
    ? <ReactECharts option={opt} style={{height:180}}/>
    : <div className="flex h-28 items-center justify-center text-sm text-slate-600">對話後開始記錄</div>;
}

type PdfTrendRow = PdfStats['daily_trend'][number];

function PdfTokenChart({ daily_trend, isHourly }: { daily_trend: PdfTrendRow[]; isHourly: boolean }) {
  const xData = isHourly
    ? Array.from({length:24},(_,i)=>`${String(i).padStart(2,'0')}:00`)
    : daily_trend.map(r=>r.date??'');
  const agentInp  = daily_trend.map(r => Math.max(0, (r.input||0) - (r.router_input||0)));
  const agentOut  = daily_trend.map(r => Math.max(0, (r.output||0) - (r.router_output||0)));
  const routerInp = daily_trend.map(r => r.router_input || 0);
  const routerOut = daily_trend.map(r => r.router_output || 0);
  const hasData   = agentInp.some(v=>v>0) || agentOut.some(v=>v>0) || routerInp.some(v=>v>0);
  const makeLine = (name: string, data: number[], color: string) => ({
    name, type:'line', smooth:true, data, symbol:'none',
    lineStyle:{color,width:2}, itemStyle:{color},
    areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:`${color}40`},{offset:1,color:`${color}06`}]}},
  });
  const opt = {
    backgroundColor:'transparent', grid:{left:54,right:16,top:12,bottom:52},
    legend:{data:['Agent Input','Agent Output','Router Input','Router Output'],bottom:4,textStyle:{color:'#94a3b8',fontSize:10}},
    tooltip:{...TIP,trigger:'axis',formatter:(p:TipParam[])=>p.map(x=>`${x.marker}${x.seriesName}: <b>${fmt(x.value)}</b>`).join('<br/>')},
    xAxis:{type:'category',data:xData,boundaryGap:false,...AX},
    yAxis:{type:'value',...AX,axisLabel:{...AX.axisLabel,formatter:fmt}},
    series:[
      makeLine('Agent Input',  agentInp,  '#6366f1'),
      makeLine('Agent Output', agentOut,  '#10b981'),
      makeLine('Router Input', routerInp, '#f59e0b'),
      makeLine('Router Output',routerOut, '#f87171'),
    ],
  };
  return hasData
    ? <ReactECharts option={opt} style={{height:200}}/>
    : <div className="flex h-28 items-center justify-center text-sm text-slate-600">對話後開始記錄</div>;
}

function CombinedCostChart({
  courseTrend, pdfTrend,
}: {
  courseTrend: MonitorStats['daily_trend'];
  pdfTrend: PdfStats['daily_trend'];
}) {
  const { dates, courseCosts, pdfCosts } = combinedDailyCost(courseTrend, pdfTrend);

  if (!dates.length) return <div className="flex h-28 items-center justify-center text-sm text-slate-600">尚無資料</div>;

  const hasData = [...courseCosts, ...pdfCosts].some(v => v > 0);
  if (!hasData) return <div className="flex h-28 items-center justify-center text-sm text-slate-600">尚無費用記錄（對話後開始統計）</div>;

  const opt = {
    backgroundColor: 'transparent', grid: { left: 64, right: 16, top: 12, bottom: 52 },
    legend: { data: ['課程推薦', '大專生計畫'], bottom: 4, textStyle: { color: '#94a3b8', fontSize: 11 } },
    tooltip: {
      ...TIP, trigger: 'axis',
      formatter: (p: TipParam[]) => {
        const total = p.reduce((s, x) => s + (x.value as number), 0);
        return [p[0].axisValue, ...p.map(x => `${x.marker}${x.seriesName}: <b>$${(x.value as number).toFixed(5)}</b>`), `合計: <b>$${total.toFixed(5)}</b>`].join('<br/>');
      },
    },
    xAxis: { type: 'category', data: dates, ...AX },
    yAxis: { type: 'value', ...AX, axisLabel: { ...AX.axisLabel, formatter: (v: number) => `$${v.toFixed(4)}` } },
    series: [
      { name: '課程推薦',   type: 'bar', stack: 'cost', data: courseCosts, barMaxWidth: 20, itemStyle: { color: '#6366f1', borderRadius: [0,0,0,0] } },
      { name: '大專生計畫', type: 'bar', stack: 'cost', data: pdfCosts,    barMaxWidth: 20, itemStyle: { color: '#10b981', borderRadius: [2,2,0,0] } },
    ],
  };
  return <ReactECharts option={opt} style={{ height: 200 }} />;
}

function LatencyDistBar({ lat }: { lat: LLMLatency }) {
  const range = lat.max_ms - lat.min_ms;
  if (range <= 0) return null;
  const pct = (v: number) => `${Math.max(0, Math.min(100, ((v - lat.min_ms) / range) * 100)).toFixed(1)}%`;
  const ticks = [
    { val: lat.min_ms, label: 'min', color: '#64748b' },
    { val: lat.avg_ms, label: 'avg', color: '#f59e0b' },
    { val: lat.p95_ms, label: 'P95', color: '#fb923c' },
    { val: lat.p99_ms, label: 'P99', color: '#ef4444' },
    { val: lat.max_ms, label: 'max', color: '#64748b' },
  ];
  const segments = [
    { from: lat.min_ms, to: lat.avg_ms, bg: 'rgba(99,102,241,0.25)' },
    { from: lat.avg_ms, to: lat.p95_ms, bg: 'rgba(245,158,11,0.30)' },
    { from: lat.p95_ms, to: lat.p99_ms, bg: 'rgba(251,146,60,0.45)' },
    { from: lat.p99_ms, to: lat.max_ms, bg: 'rgba(239,68,68,0.45)' },
  ];
  return (
    <div className="mt-3 px-1 select-none">
      <div className="relative h-3 rounded-full bg-slate-800 overflow-hidden">
        {segments.map((s, i) => {
          const left  = ((s.from - lat.min_ms) / range) * 100;
          const width = ((s.to   - s.from)     / range) * 100;
          return <div key={i} className="absolute top-0 bottom-0" style={{ left: `${left}%`, width: `${width}%`, backgroundColor: s.bg }}/>;
        })}
      </div>
      <div className="relative mt-0.5" style={{ height: 32 }}>
        {ticks.map((t, i) => (
          <div key={i} className="absolute flex flex-col items-center gap-px" style={{ left: pct(t.val), transform: 'translateX(-50%)' }}>
            <div className="h-1.5 w-px" style={{ backgroundColor: t.color }}/>
            <span className="text-[10px] font-medium" style={{ color: t.color }}>{t.label}</span>
            <span className="text-[9px] text-slate-600 tabular-nums whitespace-nowrap">{ms(t.val)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function LatencyTrendChart({ trend, isHourly, p95Ref, p99Ref }: {
  trend: {date?:string;hour?:number;avg_ms:number}[];
  isHourly: boolean;
  p95Ref?: number;
  p99Ref?: number;
}) {
  if (!trend.length) return <div className="flex h-28 items-center justify-center text-sm text-slate-600">尚無資料（需有 llm_latency_ms &gt; 0 的對話）</div>;
  const xData = isHourly ? trend.map(r=>`${String(r.hour??0).padStart(2,'0')}:00`) : trend.map(r=>r.date??'');
  const data  = trend.map(r=>r.avg_ms);
  const refLines: object[] = [];
  if (p95Ref) refLines.push({ yAxis: p95Ref, name: 'P95', lineStyle: { color: '#fb923c', type: 'dashed', width: 1 },
    label: { show: true, position: 'end', formatter: `P95 ${ms(p95Ref)}`, color: '#fb923c', fontSize: 10, padding: [2,4] } });
  if (p99Ref) refLines.push({ yAxis: p99Ref, name: 'P99', lineStyle: { color: '#ef4444', type: 'dashed', width: 1 },
    label: { show: true, position: 'end', formatter: `P99 ${ms(p99Ref)}`, color: '#ef4444', fontSize: 10, padding: [2,4] } });
  const opt = {
    backgroundColor:'transparent', grid:{left:54,right:64,top:12,bottom:36},
    tooltip:{...TIP,trigger:'axis',formatter:(p:TipParam[])=>`${p[0].axisValue} &nbsp;<b>${ms(p[0].value)}</b>`},
    xAxis:{type:'category',data:xData,boundaryGap:false,...AX},
    yAxis:{type:'value',...AX,axisLabel:{...AX.axisLabel,formatter:(v:number)=>ms(v)}},
    series:[{
      type:'line', smooth:true, data, symbol:'none',
      lineStyle:{color:'#f59e0b',width:2}, itemStyle:{color:'#f59e0b'},
      areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(245,158,11,.25)'},{offset:1,color:'rgba(245,158,11,.02)'}]}},
      ...(refLines.length ? { markLine:{ silent:true, symbol:['none','none'], data: refLines } } : {}),
    }],
  };
  return <ReactECharts option={opt} style={{height:160}}/>;
}

function PeakChart({ data }: { data: {hour:number;turns:number}[] }) {
  const mx = Math.max(...data.map(h=>h.turns),1);
  const opt = {
    backgroundColor:'transparent', grid:{left:28,right:8,top:8,bottom:36},
    tooltip:{...TIP,trigger:'axis',formatter:(p:TipParam[])=>`${String(p[0].name).padStart(2,'0')}:00 &nbsp;<b>${p[0].value} 輪</b>`},
    xAxis:{type:'category',data:data.map(h=>h.hour),...AX,axisLabel:{...AX.axisLabel,fontSize:10,formatter:(v:number)=>v%6===0?String(v).padStart(2,'0'):''}},
    yAxis:{type:'value',...AX,minInterval:1},
    series:[{type:'bar',barMaxWidth:16,data:data.map(h=>({value:h.turns,itemStyle:{color:`rgba(99,102,241,${Math.max(.12,h.turns/mx)})`,borderRadius:[2,2,0,0]}}))}],
  };
  return <ReactECharts option={opt} style={{height:160}}/>;
}

function ActivityChart({ data }: { data:{date:string;sessions:number;turns:number}[] }) {
  if (!data.length) return <div className="flex h-28 items-center justify-center text-sm text-slate-600">尚無資料</div>;
  const opt = {
    backgroundColor:'transparent', grid:{left:28,right:8,top:8,bottom:52},
    legend:{data:['Sessions','Turns'],bottom:4,textStyle:{color:'#94a3b8',fontSize:11}},
    tooltip:{...TIP,trigger:'axis'},
    xAxis:{type:'category',data:data.map(r=>r.date),...AX},
    yAxis:{type:'value',...AX,minInterval:1},
    series:[
      {name:'Sessions',type:'bar',data:data.map(r=>r.sessions),barMaxWidth:16,itemStyle:{color:'#10b981',borderRadius:[2,2,0,0]}},
      {name:'Turns',   type:'bar',data:data.map(r=>r.turns),   barMaxWidth:16,itemStyle:{color:'#6366f1',borderRadius:[2,2,0,0]}},
    ],
  };
  return <ReactECharts option={opt} style={{height:160}}/>;
}

function DailyCostChart({ daily_trend, isHourly }: {
  daily_trend: MonitorStats['daily_trend']; isHourly: boolean;
}) {
  if (!daily_trend.length) return <div className="flex h-28 items-center justify-center text-sm text-slate-600">尚無資料</div>;
  const xData   = isHourly
    ? Array.from({length:24}, (_,i) => `${String(i).padStart(2,'0')}:00`)
    : daily_trend.map(r => r.date ?? '');
  const costs   = daily_trend.map(courseRowCost);
  const tokPerTurn = daily_trend.map(r =>
    r.turns > 0 ? +((r.input + r.output) / r.turns).toFixed(0) : 0
  );
  const hasCost = costs.some(v => v > 0);
  const opt = {
    backgroundColor: 'transparent',
    grid: { left: 60, right: 60, top: 12, bottom: 52 },
    legend: { data: ['估算費用 (USD)', '每輪 Token'], bottom: 4, textStyle: { color: '#94a3b8', fontSize: 11 } },
    tooltip: {
      ...TIP, trigger: 'axis',
      formatter: (p: TipParam[]) => p.map(x =>
        `${x.marker}${x.seriesName}: <b>${x.seriesIndex === 0 ? `$${x.value.toFixed(5)}` : fmt(x.value)}</b>`
      ).join('<br/>'),
    },
    xAxis: { type: 'category', data: xData, ...AX },
    yAxis: [
      { type: 'value', name: 'USD', nameTextStyle: { color: '#94a3b8', fontSize: 10 },
        axisLabel: { ...AX.axisLabel, formatter: (v: number) => `$${v.toFixed(4)}` },
        splitLine: AX.splitLine },
      { type: 'value', name: 'tok/輪', nameTextStyle: { color: '#94a3b8', fontSize: 10 },
        axisLabel: { ...AX.axisLabel, formatter: fmt }, splitLine: { show: false } },
    ],
    series: [
      { name: '估算費用 (USD)', type: 'bar', data: costs, yAxisIndex: 0, barMaxWidth: 18,
        itemStyle: { color: '#f59e0b', borderRadius: [2,2,0,0] } },
      { name: '每輪 Token', type: 'line', data: tokPerTurn, yAxisIndex: 1,
        smooth: true, symbol: 'none',
        lineStyle: { color: '#6366f1', width: 2 },
        itemStyle: { color: '#6366f1' } },
    ],
  };
  return hasCost
    ? <ReactECharts option={opt} style={{ height: 200 }}/>
    : <div className="flex h-28 items-center justify-center text-sm text-slate-600">尚無 Token 記錄（對話後開始統計）</div>;
}

function AllToolsBarChart({ tools }: { tools:{label:string;count:number}[] }) {
  if (!tools.length) return <div className="flex h-24 items-center justify-center text-sm text-slate-600">尚無紀錄</div>;
  const sorted = [...tools].sort((a,b) => b.count - a.count);
  const total  = sorted.reduce((s,t) => s + t.count, 0);
  const opt = {
    backgroundColor: 'transparent',
    grid: { left: 140, right: 60, top: 8, bottom: 16 },
    tooltip: { ...TIP, trigger: 'axis', axisPointer: { type: 'none' },
      formatter: (p: TipParam[]) => `${p[0].name}<br/>${p[0].marker}<b>${p[0].value}</b> 次（${((p[0].value/total)*100).toFixed(1)}%）` },
    xAxis: { type: 'value', ...AX, axisLabel: { ...AX.axisLabel, fontSize: 10 } },
    yAxis: {
      type: 'category',
      data: sorted.map(t => t.label),
      axisLabel: { color: '#94a3b8', fontSize: 11, width: 128, overflow: 'truncate' },
      axisLine: { lineStyle: { color: '#334155' } },
    },
    series: [{
      type: 'bar', data: sorted.map(t => t.count), barMaxWidth: 14,
      itemStyle: { color: '#6366f1', borderRadius: [0,3,3,0] },
      label: { show: true, position: 'right', color: '#94a3b8', fontSize: 10,
               formatter: (p: { value: number }) => `${p.value}` },
    }],
  };
  const chartHeight = Math.max(160, sorted.length * 28 + 30);
  return <ReactECharts option={opt} style={{ height: chartHeight }}/>;
}

function AgentDistributionChart({ data }: { data: { agent_name: string; cnt: number }[] }) {
  if (!data.length || data.every(d => d.cnt === 0)) {
    return <div className="flex h-28 items-center justify-center text-sm text-slate-600">尚無資料</div>;
  }
  const COLORS = ['#6366f1','#10b981','#f59e0b','#0ea5e9','#a78bfa'];
  const pieSeries = data.map((d, i) => ({
    value: d.cnt,
    name: agentLabel(d.agent_name),
    itemStyle: { color: COLORS[i % COLORS.length] },
  }));
  const opt = {
    backgroundColor: 'transparent',
    tooltip: { ...TIP, trigger: 'item',
      formatter: (p: { name: string; value: number; percent: number }) =>
        `${p.name}<br/><b>${p.value}</b> 次（${p.percent.toFixed(1)}%）`,
    },
    legend: { orient: 'vertical', right: 8, top: 'middle', textStyle: { color: '#94a3b8', fontSize: 11 } },
    series: [{
      type: 'pie', radius: ['40%','70%'], center: ['40%','50%'],
      data: pieSeries,
      label: {
        show: true, color: '#e2e8f0', fontSize: 11,
        formatter: (p: { name: string; percent: number }) => `${p.name}\n${p.percent.toFixed(0)}%`,
      },
      emphasis: { itemStyle: { shadowBlur: 8, shadowColor: 'rgba(0,0,0,.5)' } },
    }],
  };
  return <ReactECharts option={opt} style={{ height: 220 }}/>;
}

function LatencyByAgentChart({ data }: { data: { agent_name: string; cnt: number; avg_ms: number; p95_ms: number }[] }) {
  if (!data.length) {
    return <div className="flex h-28 items-center justify-center text-sm text-slate-600">尚無資料</div>;
  }
  const labels = data.map(d => agentLabel(d.agent_name));
  const avgs   = data.map(d => d.avg_ms);
  const p95s   = data.map(d => d.p95_ms);
  const opt = {
    backgroundColor: 'transparent',
    grid: { left: 90, right: 72, top: 8, bottom: 8 },
    tooltip: { ...TIP, trigger: 'axis', axisPointer: { type: 'none' },
      formatter: (p: TipParam[]) =>
        `${p[0].name}<br/>${p.map(x=>`${x.marker}${x.seriesName}: <b>${ms(x.value)}</b>`).join('<br/>')}`,
    },
    xAxis: { type: 'value', ...AX, axisLabel: { ...AX.axisLabel, formatter: (v:number)=>ms(v) } },
    yAxis: {
      type: 'category', data: labels,
      axisLabel: { color: '#94a3b8', fontSize: 11, width: 80, overflow: 'truncate' },
      axisLine: { lineStyle: { color: '#334155' } },
    },
    series: [
      { name: 'Avg', type: 'bar', data: avgs, barMaxWidth: 14,
        itemStyle: { color: '#f59e0b', borderRadius: [0,3,3,0] },
        label: { show: true, position: 'right', color: '#94a3b8', fontSize: 10, formatter: (p:{value:number})=>ms(p.value) },
      },
      { name: 'P95', type: 'bar', data: p95s, barMaxWidth: 14,
        itemStyle: { color: '#fb923c', borderRadius: [0,3,3,0] },
        label: { show: true, position: 'right', color: '#94a3b8', fontSize: 10, formatter: (p:{value:number})=>ms(p.value) },
      },
    ],
  };
  const chartHeight = Math.max(100, data.length * 46 + 24);
  return (
    <div>
      <div className="mb-2 flex gap-4 text-[11px] text-slate-500">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-3 rounded-sm bg-amber-400"/>Avg
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-3 rounded-sm bg-orange-400"/>P95
        </span>
      </div>
      <ReactECharts option={opt} style={{ height: chartHeight }}/>
    </div>
  );
}

// ── Tab 內容組件 ──────────────────────────────────────────────────

interface TimeRangeProps {
  state: TimeRangeState;
  onChange: (s: TimeRangeState) => void;
  dateRange?: { start: string; end: string };
}

function TimeRangeSelector({ state, onChange, dateRange }: TimeRangeProps) {
  const { mode, preset, dayVal, weekVal, monthVal } = state;
  const set = (patch: Partial<TimeRangeState>) => onChange({ ...state, ...patch });
  return (
    <div className="flex items-center gap-2 flex-wrap">
      <div className="flex items-center gap-0.5 rounded-lg bg-slate-900 border border-slate-800 p-0.5">
        {(['preset','day','week','month'] as PickerMode[]).map(m => (
          <button key={m} type="button" onClick={() => set({mode:m})}
            className={`px-3 py-1 rounded-md text-xs font-medium transition
              ${mode===m?'bg-indigo-700 text-white':'text-slate-500 hover:text-slate-300'}`}>
            {m==='preset'?'預設':m==='day'?'單日':m==='week'?'週':'月'}
          </button>
        ))}
      </div>
      {mode === 'preset' && (
        <div className="flex items-center gap-0.5 rounded-lg bg-slate-900 border border-slate-800 p-0.5">
          {(['1d','7d','30d'] as const).map(p => (
            <button key={p} type="button" onClick={() => set({preset:p})}
              className={`px-3 py-1 rounded-md text-xs font-medium transition
                ${preset===p?'bg-slate-700 text-slate-100':'text-slate-500 hover:text-slate-300'}`}>
              {p==='1d'?'今天':p==='7d'?'近 7 天':'近 30 天'}
            </button>
          ))}
        </div>
      )}
      {mode === 'day' && (
        <input type="date" value={dayVal} max={todayISO()}
          onChange={e => set({dayVal:e.target.value})}
          className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"/>
      )}
      {mode === 'week' && (
        <input type="week" value={weekVal} onChange={e => set({weekVal:e.target.value})}
          className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"/>
      )}
      {mode === 'month' && (
        <input type="month" value={monthVal} onChange={e => set({monthVal:e.target.value})}
          className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"/>
      )}
      {dateRange && (
        <span className="text-[11px] text-slate-600">
          {dateRange.start===dateRange.end ? dateRange.start : `${dateRange.start} ~ ${dateRange.end}`}
        </span>
      )}
    </div>
  );
}

// ── OverviewTab ───────────────────────────────────────────────────
function OverviewTab({ stats, timeState, onTimeChange }: {
  stats: MonitorStats; timeState: TimeRangeState; onTimeChange: (s: TimeRangeState) => void;
}) {
  const combined: CombinedStats | undefined = stats.combined;
  const courseAt = stats.course?.all_time ?? stats.all_time;
  const pdfAt    = stats.pdf?.all_time;
  const isHourly = stats.date_range.start === stats.date_range.end;

  return (
    <div className="space-y-5">
      {/* 全時期合計 */}
      <div>
        <p className="mb-2 text-[11px] uppercase tracking-wide text-slate-600">全時期合計</p>
        <div className="rounded-xl border border-slate-800 bg-slate-900 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 divide-x divide-y md:divide-y-0 divide-slate-800">
          <Stat label="合計用戶"     value={combined?.total_users ?? courseAt.total_users}  sub="去重（兩功能）"/>
          <Stat label="即時在線"     value={combined?.online_now  ?? courseAt.online_now}   sub="15 分鐘內"/>
          <Stat label="課程推薦費用" value={`$${(courseAt.estimated_cost_usd??0).toFixed(4)}`} sub={stats.model_name}/>
          <Stat label="大專生計畫費用" value={`$${(pdfAt?.estimated_cost_usd??0).toFixed(4)}`} sub="gpt-4o + gpt-4o-mini"/>
          <Stat label="合計費用"     value={`$${(combined?.total_cost_usd??0).toFixed(4)}`} sub="USD"/>
          <Stat label="合計 Turns"   value={fmt(combined?.total_turns ?? courseAt.total_turns)} sub="兩功能合計"/>
        </div>
        <p className="mt-1.5 text-[10px] text-slate-700">
          課程推薦（{stats.model_name}）：Input $0.75 · Output $4.50 per 1M；大專生計畫（gpt-4o）：$2.50 · $10.00；Router（gpt-4o-mini）：$0.15 · $0.60（以 Azure 帳單為準）
        </p>
      </div>

      {/* 時段統計 */}
      <div>
        <div className="mb-3 flex items-center justify-between flex-wrap gap-2">
          <p className="text-[11px] uppercase tracking-wide text-slate-600">時段統計</p>
          <TimeRangeSelector state={timeState} onChange={onTimeChange} dateRange={stats.date_range}/>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* 課程推薦時段卡 */}
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
            <div className="flex items-center gap-2 mb-3">
              <HiAcademicCap className="h-4 w-4 text-indigo-400"/>
              <span className="text-sm font-medium text-slate-300">課程推薦</span>
              <span className="text-[11px] text-slate-600">{stats.model_name}</span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-[11px] text-slate-500 uppercase">活躍用戶</p>
                <p className="text-xl font-semibold text-slate-100 tabular-nums">{stats.period.active_users}</p>
                {stats.trends?.active_users && <Trend t={stats.trends.active_users}/>}
              </div>
              <div>
                <p className="text-[11px] text-slate-500 uppercase">對話輪數</p>
                <p className="text-xl font-semibold text-slate-100 tabular-nums">{stats.period.turns}</p>
                {stats.trends?.turns && <Trend t={stats.trends.turns}/>}
              </div>
              <div>
                <p className="text-[11px] text-slate-500 uppercase">Token 用量</p>
                <p className="text-xl font-semibold text-slate-100 tabular-nums">{fmt(stats.period.input_tokens + stats.period.output_tokens)}</p>
                <p className="text-[11px] text-slate-600">≈ ${stats.period.estimated_cost_usd.toFixed(4)}</p>
              </div>
              <div>
                <p className="text-[11px] text-slate-500 uppercase">平均深度</p>
                <p className="text-xl font-semibold text-slate-100 tabular-nums">{stats.period.avg_turns_per_session} 輪</p>
              </div>
            </div>
          </div>

          {/* 大專生計畫時段卡 */}
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
            <div className="flex items-center gap-2 mb-3">
              <HiDocumentText className="h-4 w-4 text-emerald-400"/>
              <span className="text-sm font-medium text-slate-300">大專生計畫</span>
              <span className="text-[11px] text-slate-600">gpt-4o + gpt-4o-mini</span>
            </div>
            {stats.pdf?.period ? (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="text-[11px] text-slate-500 uppercase">活躍用戶</p>
                  <p className="text-xl font-semibold text-slate-100 tabular-nums">{stats.pdf.period.active_users}</p>
                  {stats.pdf.trends?.active_users && <Trend t={stats.pdf.trends.active_users}/>}
                </div>
                <div>
                  <p className="text-[11px] text-slate-500 uppercase">對話輪數</p>
                  <p className="text-xl font-semibold text-slate-100 tabular-nums">{stats.pdf.period.turns}</p>
                  {stats.pdf.trends?.turns && <Trend t={stats.pdf.trends.turns}/>}
                </div>
                <div>
                  <p className="text-[11px] text-slate-500 uppercase">Token 用量</p>
                  <p className="text-xl font-semibold text-slate-100 tabular-nums">{fmt(stats.pdf.period.input_tokens + stats.pdf.period.output_tokens)}</p>
                  <p className="text-[11px] text-slate-600">≈ ${stats.pdf.period.estimated_cost_usd.toFixed(4)}</p>
                </div>
                <div>
                  <p className="text-[11px] text-slate-500 uppercase">平均深度</p>
                  <p className="text-xl font-semibold text-slate-100 tabular-nums">{stats.pdf.period.avg_turns_per_session.toFixed(1)} 輪</p>
                </div>
              </div>
            ) : (
              <div className="flex h-24 items-center justify-center text-sm text-slate-600">尚無對話資料</div>
            )}
          </div>
        </div>
      </div>

      {/* Token 趨勢（各自 Y 軸，避免量級差距） */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Section title="課程推薦 Token 趨勢" sub={isHourly?'今日（按小時）':'按日'}>
          <TokenChart daily_trend={stats.daily_trend} isHourly={isHourly}/>
        </Section>
        <Section title="大專生計畫 Token 趨勢" sub={isHourly?'今日（按小時）':'按日'}>
          {stats.pdf?.daily_trend
            ? <PdfTokenChart daily_trend={stats.pdf.daily_trend} isHourly={isHourly}/>
            : <div className="flex h-28 items-center justify-center text-sm text-slate-600">尚無對話資料</div>
          }
        </Section>
      </div>

      {/* 每日費用比較 */}
      {!isHourly && (
        <Section title="每日費用比較" sub="課程推薦 vs 大專生計畫（堆疊，USD）">
          <CombinedCostChart
            courseTrend={stats.daily_trend}
            pdfTrend={stats.pdf?.daily_trend ?? []}
          />
        </Section>
      )}
    </div>
  );
}

// ── CourseTab ─────────────────────────────────────────────────────
function CourseTab({ stats }: { stats: MonitorStats }) {
  const isHourly      = stats.date_range.start === stats.date_range.end;
  const lat           = stats.period.llm_latency;
  const { input_tokens, output_tokens } = stats.period;
  const ratio         = output_tokens > 0 ? (input_tokens / output_tokens).toFixed(1) : '—';
  const courseTrend   = stats.course?.daily_trend ?? stats.daily_trend;
  const courseTools   = stats.course?.tools_usage ?? stats.tools_usage;

  return (
    <div className="space-y-5">
      {/* Model 資訊 */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-4 flex items-start justify-between gap-4">
        <div>
          <p className="text-xs text-slate-500 mb-1">Model</p>
          <p className="text-lg font-semibold text-slate-200">{stats.model_name}</p>
          <p className="text-xs text-slate-600 mt-0.5">Azure OpenAI · Global 端點 · Input $0.75 / Output $4.50 per 1M tokens</p>
        </div>
        <div className="text-right shrink-0">
          <p className="text-xs text-slate-500 mb-1">Input / Output 比</p>
          <p className="text-lg font-semibold text-slate-200">{ratio} : 1</p>
          <p className="text-xs text-slate-600">每 1 個 output token 對應的 input tokens</p>
        </div>
      </div>

      {/* Model Latency */}
      <div>
        <p className="mb-2 text-[11px] uppercase tracking-wide text-slate-600">
          Model Latency（{lat ? `${lat.count} 次對話` : '無資料'}）
        </p>
        {lat
          ? <LatencyGrid lat={lat}/>
          : <div className="rounded-xl border border-slate-800 bg-slate-900 py-6 text-center text-sm text-slate-600">
              尚無 latency 資料（新對話後即開始記錄）
            </div>
        }
      </div>

      {/* Latency 分布 */}
      {lat && (
        <div className="rounded-xl border border-slate-800 bg-slate-900 px-5 pt-3 pb-4">
          <p className="text-[11px] uppercase tracking-wide text-slate-500 mb-1">Latency 分布（min → avg → P95 → P99 → max）</p>
          <LatencyDistBar lat={lat}/>
        </div>
      )}

      {/* Latency 趨勢 */}
      <Section title="Model Latency 趨勢" sub={isHourly?'今日（按小時）':'按日 · 虛線為整體 P95 / P99 基準'}>
        <LatencyTrendChart
          trend={stats.period.llm_latency_trend}
          isHourly={isHourly}
          p95Ref={lat?.p95_ms}
          p99Ref={lat?.p99_ms}
        />
      </Section>

      {/* Token + 費用 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Section title="Token 用量趨勢" sub={isHourly?'今日（按小時）':'按日'}>
          <TokenChart daily_trend={courseTrend} isHourly={isHourly}/>
        </Section>
        <Section title="每日費用 & 每輪 Token" sub="黃柱：USD 費用（左軸）  紫線：每輪平均 Token（右軸）">
          <DailyCostChart daily_trend={courseTrend} isHourly={isHourly}/>
        </Section>
      </div>

      {/* 工具使用 */}
      <Section title="工具使用統計" sub={`${courseTools.length} 種工具（時段內）`}>
        <AllToolsBarChart tools={courseTools}/>
      </Section>
    </div>
  );
}

// ── PdfTab ────────────────────────────────────────────────────────
function PdfTab({ stats }: { stats: MonitorStats }) {
  const pdf        = stats.pdf;
  const isHourly   = stats.date_range.start === stats.date_range.end;
  const agentModel  = stats.pdf_model_name ?? 'gpt-4o';
  const routerModel = stats.pdf_router_model_name ?? 'gpt-4o-mini';

  if (!pdf?.period) {
    return <div className="flex h-40 items-center justify-center text-slate-600 text-sm">尚無大專生計畫對話資料</div>;
  }

  const { period, all_time, trends, daily_trend } = pdf;
  const agentCost  = period.estimated_cost_breakdown?.agent_usd ?? 0;
  const routerCost = period.estimated_cost_breakdown?.router_usd ?? 0;
  const agentInp   = Math.max(0, period.input_tokens  - period.router_input_tokens);
  const agentOut   = Math.max(0, period.output_tokens - period.router_output_tokens);

  return (
    <div className="space-y-5">
      {/* 統計列 */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 grid grid-cols-2 md:grid-cols-4 divide-x divide-y md:divide-y-0 divide-slate-800">
        <Stat label="活躍用戶"  value={period.active_users}
          sub={`新增 ${period.new_users} 人`} trend={trends?.active_users}/>
        <Stat label="對話輪數"  value={period.turns}
          sub={`${period.sessions} sessions`} trend={trends?.turns}/>
        <Stat label="Token 用量" value={fmt(period.input_tokens+period.output_tokens)}
          sub={`≈ $${period.estimated_cost_usd.toFixed(4)}`} trend={trends?.tokens}/>
        <Stat label="平均深度"  value={`${period.avg_turns_per_session.toFixed(1)} 輪`} sub="每 session"/>
      </div>

      {/* Model 費用拆分 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="h-2 w-2 rounded-full bg-indigo-500"/>
            <span className="text-sm font-medium text-slate-300">{agentModel}（Agent）</span>
          </div>
          <p className="text-xs text-slate-600 mb-3">Input $2.50 / Output $10.00 per 1M tokens</p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-[11px] text-slate-500 uppercase">時段費用</p>
              <p className="text-xl font-semibold text-slate-100 tabular-nums">${agentCost.toFixed(5)}</p>
            </div>
            <div>
              <p className="text-[11px] text-slate-500 uppercase">累計費用</p>
              <p className="text-xl font-semibold text-slate-100 tabular-nums">${(all_time?.estimated_cost_usd??0).toFixed(4)}</p>
              <p className="text-[11px] text-slate-600">（所有模型合計）</p>
            </div>
          </div>
          <div className="mt-2 flex gap-4 text-[11px] text-slate-600">
            <span>Agent Input: {fmt(agentInp)} tok</span>
            <span>Agent Output: {fmt(agentOut)} tok</span>
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          <div className="flex items-center gap-2 mb-2">
            <span className="h-2 w-2 rounded-full bg-violet-400"/>
            <span className="text-sm font-medium text-slate-300">{routerModel}（Router）</span>
          </div>
          <p className="text-xs text-slate-600 mb-3">Input $0.15 / Output $0.60 per 1M tokens</p>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-[11px] text-slate-500 uppercase">時段費用</p>
              <p className="text-xl font-semibold text-slate-100 tabular-nums">${routerCost.toFixed(5)}</p>
            </div>
            <div>
              <p className="text-[11px] text-slate-500 uppercase">Router 佔比</p>
              <p className="text-xl font-semibold text-slate-100 tabular-nums">
                {period.estimated_cost_usd > 0
                  ? ((routerCost / period.estimated_cost_usd) * 100).toFixed(1)
                  : '0.0'}%
              </p>
            </div>
          </div>
          <div className="mt-2 flex gap-4 text-[11px] text-slate-600">
            <span>Router Input: {fmt(period.router_input_tokens)} tok</span>
            <span>Router Output: {fmt(period.router_output_tokens)} tok</span>
          </div>
        </div>
      </div>

      {/* Agent 路由分佈 + Latency by Agent */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Section title="Agent 路由分佈" sub="各 Agent 被調用次數">
          <AgentDistributionChart data={period.agent_distribution}/>
        </Section>
        <Section title="各 Agent Latency" sub="端到端延遲（avg / P95）">
          <LatencyByAgentChart data={period.latency_by_agent}/>
        </Section>
      </div>

      {/* 端到端 Latency */}
      {period.llm_latency && (
        <div>
          <p className="mb-2 text-[11px] uppercase tracking-wide text-slate-600">
            端到端 Latency（{period.llm_latency.count} 次）
          </p>
          <LatencyGrid lat={period.llm_latency}/>
          <div className="mt-3 rounded-xl border border-slate-800 bg-slate-900 px-5 pt-3 pb-4">
            <p className="text-[11px] uppercase tracking-wide text-slate-500 mb-1">Latency 分布（min → avg → P95 → P99 → max）</p>
            <LatencyDistBar lat={period.llm_latency}/>
          </div>
        </div>
      )}

      {/* Latency 趨勢 */}
      <Section title="Latency 趨勢" sub={isHourly?'今日（按小時）':'按日 · 虛線為整體 P95 / P99 基準'}>
        <LatencyTrendChart
          trend={period.llm_latency_trend}
          isHourly={isHourly}
          p95Ref={period.llm_latency?.p95_ms}
          p99Ref={period.llm_latency?.p99_ms}
        />
      </Section>

      {/* PDF Token 趨勢（4 系列） */}
      <Section title="Token 用量趨勢" sub={`${isHourly?'今日（按小時）':'按日'} · 紫/藍：Agent · 淺紫/淺藍：Router`}>
        <PdfTokenChart daily_trend={daily_trend} isHourly={isHourly}/>
      </Section>

      {/* 全時期摘要 */}
      {all_time && (
        <div>
          <p className="mb-2 text-[11px] uppercase tracking-wide text-slate-600">全時期累計</p>
          <div className="rounded-xl border border-slate-800 bg-slate-900 grid grid-cols-2 md:grid-cols-4 divide-x divide-y md:divide-y-0 divide-slate-800">
            <Stat label="總 Sessions" value={all_time.total_sessions} sub=""/>
            <Stat label="總 Turns"    value={fmt(all_time.total_turns)} sub=""/>
            <Stat label="總 Token"    value={fmt(all_time.total_input + all_time.total_output)} sub="input + output"/>
            <Stat label="累計費用"    value={`$${all_time.estimated_cost_usd.toFixed(4)}`} sub="USD"/>
          </div>
        </div>
      )}
    </div>
  );
}

// ── InfraCard & DatabaseTab ────────────────────────────────────────
function InfraCard({ label, sub, badge, badgeColor, value, valueColor }: {
  label: string; sub: string; badge?: string; badgeColor?: string;
  value?: string; valueColor?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-4 flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-300">{label}</span>
        {badge && (
          <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${badgeColor||'bg-emerald-900/50 text-emerald-400'}`}>
            {badge}
          </span>
        )}
      </div>
      {value && <p className="text-2xl font-semibold tabular-nums" style={{color:valueColor||'#e2e8f0'}}>{value}</p>}
      <p className="text-[11px] text-slate-600">{sub}</p>
    </div>
  );
}

function DatabaseTab({ dbStats, loading }: { dbStats: DBStats|null; loading: boolean }) {
  if (loading) return <div className="flex h-40 items-center justify-center text-slate-600 text-sm">載入中…</div>;
  if (!dbStats) return <div className="flex h-40 items-center justify-center text-slate-600 text-sm">載入失敗</div>;

  const { infra, postgres: pg, qdrant: qd, cloudinary: cl, cloudinary_error: clErr } = dbStats;
  const qdDebug    = dbStats.qdrant_debug;
  const cacheColor = pg.cache_hit_pct >= 95 ? '#10b981' : pg.cache_hit_pct >= 80 ? '#f59e0b' : '#ef4444';

  return (
    <div className="space-y-5">
      {/* 基礎設施概覽 */}
      <div>
        <p className="mb-3 text-[11px] uppercase tracking-wide text-slate-600">基礎設施概覽</p>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <InfraCard
            label="Render 後端" badge="運行中" badgeColor="bg-emerald-900/50 text-emerald-400"
            value={fmtUptime(infra.server_uptime_seconds)}
            sub="本次伺服器啟動時間（冷啟動後重置）"
          />
          <InfraCard
            label="Neon PostgreSQL" badge="正常" badgeColor="bg-sky-900/50 text-sky-400"
            value={pg.db_size}
            sub={`${infra.neon_region} (AWS) · Cache ${pg.cache_hit_pct}%`}
          />
          <InfraCard
            label="Qdrant Cloud" badge="正常" badgeColor="bg-violet-900/50 text-violet-400"
            value={infra.qdrant_total_points.toLocaleString()}
            sub={`${infra.qdrant_region} (AWS) · ${qd.collections.length} collections`}
          />
          {cl ? (
            <InfraCard
              label="Cloudinary" badge={cl.plan} badgeColor="bg-orange-900/50 text-orange-400"
              value={`${cl.total_resources} PDFs`}
              sub={`${cl.storage_pretty} 已用 · 本月 ${cl.bandwidth_pretty} 流量`}
            />
          ) : (
            <InfraCard
              label="Firebase Hosting" badge="CDN" badgeColor="bg-amber-900/50 text-amber-400"
              sub="靜態 CDN，無需監控"
            />
          )}
        </div>
        {cl && (
          <div className="mt-3">
            <InfraCard
              label="Firebase Hosting" badge="CDN" badgeColor="bg-amber-900/50 text-amber-400"
              sub="靜態前端 CDN，無需監控"
            />
          </div>
        )}
      </div>

      {/* PostgreSQL */}
      <div>
        <p className="mb-3 text-[11px] uppercase tracking-wide text-slate-600 flex items-center gap-1.5">
          <HiDatabase className="h-3.5 w-3.5"/> PostgreSQL
          <span className="text-slate-700 normal-case">Neon · {infra.neon_region} (AWS)</span>
        </p>
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-4 space-y-4">
          <div className="grid grid-cols-3 gap-4">
            <div>
              <p className="text-[11px] text-slate-500 uppercase">DB 大小</p>
              <p className="text-xl font-semibold text-slate-200 mt-0.5">{pg.db_size}</p>
            </div>
            <div>
              <p className="text-[11px] text-slate-500 uppercase">連線數</p>
              <p className="text-xl font-semibold text-slate-200 mt-0.5">{pg.connections}</p>
            </div>
            <div>
              <p className="text-[11px] text-slate-500 uppercase">Cache Hit</p>
              <p className="text-xl font-semibold mt-0.5" style={{color:cacheColor}}>{pg.cache_hit_pct}%</p>
              <div className="mt-1 h-1.5 rounded-full bg-slate-800">
                <div className="h-full rounded-full" style={{width:`${Math.min(pg.cache_hit_pct,100)}%`,backgroundColor:cacheColor}}/>
              </div>
            </div>
          </div>
          <div className="rounded-lg border border-slate-800 overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800 bg-slate-950/40">
                  <th className="text-left px-4 py-2 text-[11px] uppercase text-slate-500 font-normal">Table</th>
                  <th className="text-right px-4 py-2 text-[11px] uppercase text-slate-500 font-normal">Rows</th>
                  <th className="text-right px-4 py-2 text-[11px] uppercase text-slate-500 font-normal">Size</th>
                </tr>
              </thead>
              <tbody>
                {pg.tables.map(t => (
                  <tr key={t.name} className="border-b border-slate-800/60 last:border-0 hover:bg-slate-800/30">
                    <td className="px-4 py-2.5 text-slate-300 font-mono text-xs">{t.name}</td>
                    <td className="px-4 py-2.5 text-right text-slate-300 tabular-nums">{t.rows.toLocaleString()}</td>
                    <td className="px-4 py-2.5 text-right text-slate-500 text-xs">{t.size_pretty}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Qdrant */}
      <div>
        <p className="mb-3 text-[11px] uppercase tracking-wide text-slate-600 flex items-center gap-1.5">
          <HiServer className="h-3.5 w-3.5"/> Qdrant Cloud
          <span className="text-slate-700 normal-case">{infra.qdrant_region} (AWS)</span>
        </p>
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-4">
          {qd.collections.length === 0
            ? <div className="space-y-2">
                <p className="text-sm text-red-400">無法取得 Collection 資料</p>
                {qdDebug && (
                  <div className="rounded-lg border border-red-900/60 bg-red-950/30 px-3 py-2 text-xs text-red-200">
                    <p className="font-mono break-all">{qdDebug.url}</p>
                    <p className="mt-1 break-all">{qdDebug.error || 'unknown error'}</p>
                    <p className="mt-1 text-red-300/70">
                      QDRANT_URL: {qdDebug.configured ? '已設定' : '未設定'} · API Key: {qdDebug.api_key_set ? '已設定' : '未設定'}
                    </p>
                  </div>
                )}
              </div>
            : <div className="rounded-lg border border-slate-800 overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-800 bg-slate-950/40">
                      <th className="text-left px-4 py-2 text-[11px] uppercase text-slate-500 font-normal">Collection</th>
                      <th className="text-right px-4 py-2 text-[11px] uppercase text-slate-500 font-normal">Points</th>
                      <th className="text-right px-4 py-2 text-[11px] uppercase text-slate-500 font-normal">Segments</th>
                      <th className="text-center px-4 py-2 text-[11px] uppercase text-slate-500 font-normal">Optimizer</th>
                      <th className="text-center px-4 py-2 text-[11px] uppercase text-slate-500 font-normal">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {qd.collections.map(c => (
                      <tr key={c.name} className="border-b border-slate-800/60 last:border-0 hover:bg-slate-800/30">
                        <td className="px-4 py-2.5 text-slate-300 font-mono text-xs">{c.name}</td>
                        <td className="px-4 py-2.5 text-right text-slate-200 tabular-nums font-medium">{c.points_count.toLocaleString()}</td>
                        <td className="px-4 py-2.5 text-right text-slate-500 tabular-nums text-xs">{c.segments_count}</td>
                        <td className="px-4 py-2.5 text-center">
                          <span className={`text-[11px] ${c.optimizer_ok?'text-slate-500':'text-amber-400'}`}>
                            {c.optimizer_ok ? '✓' : '最佳化中'}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 text-center">
                          <span className={`inline-flex items-center gap-1 text-[11px] font-medium
                            ${c.status==='green'?'text-emerald-400':c.status==='yellow'?'text-amber-400':'text-slate-600'}`}>
                            <span className={`h-1.5 w-1.5 rounded-full ${c.status==='green'?'bg-emerald-500':c.status==='yellow'?'bg-amber-500':'bg-slate-600'}`}/>
                            {c.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
          }
        </div>
      </div>

      {/* Cloudinary */}
      <div>
        <p className="mb-3 text-[11px] uppercase tracking-wide text-slate-600">Cloudinary（PDF 儲存）</p>
        {cl ? (
          <div className="rounded-xl border border-slate-800 bg-slate-900 p-4 grid grid-cols-3 gap-4">
            <div>
              <p className="text-[11px] text-slate-500 uppercase">PDF 總數</p>
              <p className="text-2xl font-semibold text-slate-200 mt-0.5">{cl.total_resources.toLocaleString()}</p>
              <p className="text-[11px] text-slate-600 mt-0.5">方案：{cl.plan}</p>
            </div>
            <div>
              <p className="text-[11px] text-slate-500 uppercase">儲存用量</p>
              <p className="text-2xl font-semibold text-slate-200 mt-0.5">{cl.storage_pretty}</p>
            </div>
            <div>
              <p className="text-[11px] text-slate-500 uppercase">本月流量</p>
              <p className="text-2xl font-semibold text-slate-200 mt-0.5">{cl.bandwidth_pretty}</p>
            </div>
          </div>
        ) : (
          <div className="rounded-xl border border-red-900/50 bg-red-950/30 px-5 py-4">
            <p className="text-sm text-red-400 mb-1">無法取得 Cloudinary 資料</p>
            {clErr && <p className="text-xs text-slate-500 font-mono break-all">{clErr}</p>}
          </div>
        )}
      </div>
    </div>
  );
}

// ── 對話深度 Box Plot ─────────────────────────────────────────────
type ActivityFeature = 'all' | 'course' | 'pdf';

function DepthBoxPlot({ courseStats, pdfStats, feature }: {
  courseStats: DepthStats | null;
  pdfStats: DepthStats | null;
  feature: ActivityFeature;
}) {
  const items: { name: string; stats: DepthStats; color: string }[] = [];
  if ((feature === 'all' || feature === 'course') && courseStats) {
    items.push({ name: '課程推薦', stats: courseStats, color: '#6366f1' });
  }
  if ((feature === 'all' || feature === 'pdf') && pdfStats) {
    items.push({ name: '大專生計畫', stats: pdfStats, color: '#10b981' });
  }

  if (!items.length) {
    return <div className="flex h-28 items-center justify-center text-sm text-slate-600">尚無資料</div>;
  }

  const boxData  = items.map(i => [i.stats.min, i.stats.q1, i.stats.median, i.stats.q3, i.stats.max]);
  const meanData = items.map((item, idx) => [idx, item.stats.avg]);

  const opt = {
    backgroundColor: 'transparent',
    grid: { left: 48, right: 20, top: 12, bottom: 48 },
    tooltip: {
      ...TIP,
      trigger: 'item',
      formatter: (p: { seriesType: string; name: string; value: unknown; seriesName: string }) => {
        if (p.seriesType === 'scatter') {
          const v = p.value as [number, number];
          return `${p.name}<br/>${p.seriesName}: <b>${(v[1] as number).toFixed(1)} 輪</b>`;
        }
        const v = p.value as number[];
        return `${p.name}<br/>min: <b>${v[0]}</b> · Q1: <b>${v[1]}</b> · 中位: <b>${v[2]}</b> · Q3: <b>${v[3]}</b> · max: <b>${v[4]}</b>`;
      },
    },
    xAxis: { type: 'category', data: items.map(i => i.name), ...AX },
    yAxis: { type: 'value', ...AX, minInterval: 1 },
    series: [
      {
        name: '對話深度',
        type: 'boxplot',
        data: boxData,
        itemStyle: { color: 'rgba(99,102,241,0.15)', borderColor: '#6366f1', borderWidth: 2 },
        boxWidth: ['30%', '50%'],
      },
      {
        name: '平均值',
        type: 'scatter',
        data: meanData,
        symbolSize: 10,
        itemStyle: { color: '#f59e0b' },
        tooltip: {},
      },
    ],
  };

  return (
    <div>
      <ReactECharts option={opt} style={{ height: 220 }}/>
      <div className="mt-1 flex flex-wrap gap-x-5 gap-y-0.5">
        {items.map(i => (
          <p key={i.name} className="text-[11px] text-slate-500">
            <span className="font-medium" style={{ color: i.color }}>{i.name}</span>
            {' '}· {i.stats.count} sessions · 平均{' '}
            <span className="text-slate-400 font-medium">{i.stats.avg.toFixed(1)} 輪</span>
            {' '}· 中位 <span className="text-slate-400 font-medium">{i.stats.median} 輪</span>
          </p>
        ))}
      </div>
    </div>
  );
}

// ── 每日平均深度趨勢 ──────────────────────────────────────────────
function DepthTrendChart({ data }: { data: { date: string; sessions: number; turns: number }[] }) {
  const filtered = data.filter(d => d.sessions > 0);
  if (!filtered.length) {
    return <div className="flex h-20 items-center justify-center text-sm text-slate-600">尚無資料</div>;
  }
  const xData = filtered.map(d => d.date);
  const yData = filtered.map(d => +(d.turns / d.sessions).toFixed(2));
  const opt = {
    backgroundColor: 'transparent',
    grid: { left: 40, right: 16, top: 8, bottom: 36 },
    tooltip: { ...TIP, trigger: 'axis',
      formatter: (p: TipParam[]) => `${p[0].axisValue} &nbsp;<b>${p[0].value} 輪/session</b>`,
    },
    xAxis: { type: 'category', data: xData, boundaryGap: false, ...AX,
      axisLabel: { ...AX.axisLabel, fontSize: 10 } },
    yAxis: { type: 'value', ...AX, axisLabel: { ...AX.axisLabel, formatter: (v: number) => `${v}輪` } },
    series: [{
      type: 'line', smooth: true, data: yData, symbol: 'circle', symbolSize: 5,
      lineStyle: { color: '#a78bfa', width: 2 },
      itemStyle: { color: '#a78bfa' },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [{ offset: 0, color: 'rgba(167,139,250,.25)' }, { offset: 1, color: 'rgba(167,139,250,.02)' }] } },
    }],
  };
  return <ReactECharts option={opt} style={{ height: 140 }}/>;
}

// ── ActivityTab ───────────────────────────────────────────────────

function ActivityTab({ stats }: { stats: MonitorStats }) {
  const [feature, setFeature] = useState<ActivityFeature>('all');

  const courseActivity = stats.course?.activity_trend ?? stats.activity_trend;
  const pdfActivity    = stats.pdf?.activity_trend ?? [];
  const coursePeak     = stats.course?.peak_hours ?? stats.peak_hours;
  const courseTools    = stats.course?.tools_usage ?? stats.tools_usage;

  const combinedActivity = useMemo(
    () => combineActivity(courseActivity, pdfActivity),
    [courseActivity, pdfActivity],
  );

  const activityData = feature === 'course' ? courseActivity : feature === 'pdf' ? pdfActivity : combinedActivity;

  const courseP = stats.period;
  const pdfP    = stats.pdf?.period;

  const active_users     = feature === 'pdf' ? (pdfP?.active_users ?? 0) : courseP.active_users;
  const new_users        = feature === 'pdf' ? (pdfP?.new_users ?? 0)    : courseP.new_users;
  const returning        = Math.max(0, active_users - new_users);
  const courseDepthStats = courseP.depth_stats ?? null;
  const pdfDepthStats    = pdfP?.depth_stats ?? null;

  const featureLabel = feature === 'all' ? '合計' : feature === 'course' ? '課程推薦' : '大專生計畫';

  return (
    <div className="space-y-5">
      {/* Feature 切換 */}
      <div className="flex items-center gap-0.5 rounded-lg bg-slate-900 border border-slate-800 p-0.5 w-fit">
        {(['all','course','pdf'] as ActivityFeature[]).map(f => (
          <button key={f} type="button" onClick={() => setFeature(f)}
            className={`px-4 py-1.5 rounded-md text-xs font-medium transition
              ${feature===f?'bg-indigo-700 text-white':'text-slate-500 hover:text-slate-300'}`}>
            {f==='all'?'合計':f==='course'?'課程推薦':'大專生計畫'}
          </button>
        ))}
      </div>

      {/* 用戶概況 */}
      <div className="rounded-xl border border-slate-800 bg-slate-900 grid grid-cols-3 md:grid-cols-5 divide-x divide-slate-800">
        <Stat label="時段活躍用戶" value={active_users} sub="有對話紀錄"/>
        <Stat label="新用戶"       value={new_users}    sub={`佔 ${active_users>0?Math.round(new_users/active_users*100):0}%`}/>
        <Stat label="回訪用戶"     value={returning}    sub={`佔 ${active_users>0?Math.round(returning/active_users*100):0}%`}/>
        <Stat label="Sessions"     value={(feature==='pdf'?(pdfP?.sessions??0):courseP.sessions).toLocaleString()} sub={featureLabel}/>
        <Stat label="Turns"        value={(feature==='pdf'?(pdfP?.turns??0):courseP.turns).toLocaleString()} sub={featureLabel}/>
      </div>

      {/* 對話深度分布 Box Plot */}
      <Section title="對話深度分布" sub="min / Q1 / 中位數 / Q3 / max  ·  黃點為平均值">
        <DepthBoxPlot
          courseStats={courseDepthStats}
          pdfStats={pdfDepthStats}
          feature={feature}
        />
      </Section>

      {/* 每日平均深度趨勢 */}
      <Section title="每日平均對話深度趨勢" sub={`${featureLabel} · turns ÷ sessions`}>
        <DepthTrendChart data={activityData}/>
      </Section>

      {/* 活動趨勢 */}
      <Section title={`對話活動趨勢 — ${featureLabel}`} sub="Sessions & Turns">
        <ActivityChart data={activityData}/>
      </Section>

      {/* 工具使用（課程推薦 or 合計） */}
      {feature !== 'pdf' && (
        <Section title="課程推薦工具使用統計" sub={`${courseTools.length} 種工具（時段內）`}>
          <AllToolsBarChart tools={courseTools}/>
        </Section>
      )}

      {/* 活躍時段（課程推薦 or 合計） */}
      {feature !== 'pdf' && (
        <Section title="課程推薦活躍時段分布" sub="24 小時">
          <PeakChart data={coursePeak}/>
        </Section>
      )}

      {/* 活躍時段（大專生計畫） */}
      {feature !== 'course' && stats.pdf?.peak_hours && stats.pdf.peak_hours.length > 0 && (
        <Section title="大專生計畫活躍時段分布" sub="24 小時">
          <PeakChart data={stats.pdf.peak_hours}/>
        </Section>
      )}
    </div>
  );
}

// ── 主頁面 ────────────────────────────────────────────────────────
type TabId = MonitorTabId;
const TABS: { id: TabId; label: string; icon: React.ComponentType<{className?:string}> }[] = [
  { id:'overview',  label:'總覽',      icon: HiChip },
  { id:'course',    label:'課程推薦',  icon: HiAcademicCap },
  { id:'pdf',       label:'大專生計畫', icon: HiDocumentText },
  { id:'database',  label:'資料庫',    icon: HiDatabase },
  { id:'activity',  label:'對話活動',  icon: HiChatAlt2 },
];

export default function MonitorPage() {
  const {
    authLoading,
    activeTab, setActiveTab,
    timeState, setTimeState,
    refreshSec, setRefreshSec,
    countdown, setCountdown,
    stats, dbStats, dbLoading,
    loading, error, lastAt,
    doRefresh,
  } = useMonitor();

  if (authLoading) return null;

  const ok = stats
    ? stats.system_health.postgres==='ok' && stats.system_health.qdrant==='ok'
    : null;
  const chatLat = stats?.latency_stats.find(e=>e.endpoint==='/api/chat');

  return (
    <div className="min-h-screen bg-slate-950 text-slate-300">
      <div className="max-w-[1400px] mx-auto px-5 py-6 space-y-4">

        {/* ── 頁頭 ── */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <h1 className="text-base font-semibold text-slate-200">系統監控</h1>
            {ok!==null && (
              <span className={`flex items-center gap-1 text-xs ${ok?'text-emerald-500':'text-red-400'}`}>
                {ok ? <HiCheckCircle className="h-3.5 w-3.5"/> : <HiXCircle className="h-3.5 w-3.5"/>}
                {ok?'全部正常':'異常'}
              </span>
            )}
            {lastAt && !loading && (
              <span className="text-[11px] text-slate-600">
                {lastAt.toLocaleTimeString('zh-TW')} · {countdown}s 後更新
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-0.5 rounded-lg bg-slate-900 border border-slate-800 p-0.5">
              {([30,60,300] as const).map(s => (
                <button key={s} type="button" onClick={() => { setRefreshSec(s); setCountdown(s); }}
                  className={`px-2.5 py-1 rounded-md text-xs transition ${refreshSec===s?'bg-slate-700 text-slate-100':'text-slate-500 hover:text-slate-300'}`}>
                  {s<60?`${s}s`:s===60?'1m':'5m'}
                </button>
              ))}
            </div>
            <button type="button" onClick={doRefresh}
              className="rounded-lg border border-slate-800 bg-slate-900 px-2.5 py-1 text-slate-400 hover:text-slate-200 transition">
              <HiRefresh className={`h-4 w-4 ${loading?'animate-spin':''}`}/>
            </button>
          </div>
        </div>

        {/* ── 健康列 ── */}
        <div className="flex items-center gap-3 flex-wrap">
          {stats ? (
            <>
              <ServiceDot label="Render" ok/>
              <span className="text-slate-700">·</span>
              <ServiceDot label="PostgreSQL" ok={stats.system_health.postgres==='ok'}/>
              <span className="text-slate-700">·</span>
              <ServiceDot label="Qdrant" ok={stats.system_health.qdrant==='ok'}/>
              {stats.system_health.qdrant === 'error' && stats.qdrant_debug && (
                <span
                  className="max-w-[720px] truncate text-[11px] text-red-300"
                  title={`${stats.qdrant_debug.url} · ${stats.qdrant_debug.error || 'unknown error'}`}
                >
                  {stats.qdrant_debug.url} · {stats.qdrant_debug.error || 'unknown error'}
                </span>
              )}
              {chatLat && <>
                <span className="text-slate-700">·</span>
                <ServiceDot label="/api/chat" ok={chatLat.error_rate_pct<=5} extra={`${chatLat.avg_ms.toFixed(0)}ms avg`}/>
              </>}
            </>
          ) : <span className="text-[11px] text-slate-700">檢查中…</span>}
        </div>

        {/* ── 錯誤 ── */}
        {error && (
          <div className="rounded-lg border border-red-900 bg-red-950/50 px-4 py-3 text-sm text-red-400">
            {error} — <button type="button" onClick={doRefresh} className="underline">重試</button>
          </div>
        )}

        {/* ── Tab bar ── */}
        <div className="sticky top-0 z-10 -mx-5 px-5 py-2 bg-slate-950/95 backdrop-blur-sm border-b border-slate-900">
        <div className="flex items-center gap-0.5 rounded-lg bg-slate-900 border border-slate-800 p-0.5 w-fit">
          {TABS.map(t => (
            <button key={t.id} type="button" onClick={() => setActiveTab(t.id)}
              className={`flex items-center gap-1.5 px-4 py-1.5 rounded-md text-xs font-medium transition
                ${activeTab===t.id?'bg-indigo-700 text-white':'text-slate-500 hover:text-slate-300'}`}>
              <t.icon className="h-3.5 w-3.5"/>
              {t.label}
            </button>
          ))}
        </div>
        </div>

        {/* ── Tab content ── */}
        {stats && activeTab==='overview' && (
          <OverviewTab stats={stats} timeState={timeState} onTimeChange={setTimeState}/>
        )}
        {stats && activeTab==='course'   && <CourseTab stats={stats}/>}
        {stats && activeTab==='pdf'      && <PdfTab stats={stats}/>}
        {activeTab==='database' && (
          <DatabaseTab dbStats={dbStats} loading={dbLoading}/>
        )}
        {stats && activeTab==='activity' && <ActivityTab stats={stats}/>}

      </div>
    </div>
  );
}
