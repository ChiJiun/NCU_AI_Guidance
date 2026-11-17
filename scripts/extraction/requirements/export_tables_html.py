"""
將所有 應修科目表 PDF 用 pdfplumber extract_tables() 轉成互動式 HTML 編輯器。

功能：
  - 點擊格子可直接編輯文字
  - 右鍵選單：切換 merge / empty / value 類型
  - Export 按鈕：輸出 JSON（存檔）＋ LLM Markdown（可複製）
  - 每個 PDF 獨立 section，可折疊

格子類型：
  橘底 ◀ merge  = None（合併延伸格，同一門課橫跨多格）
  白底 空白      = ''（真正空白，這學期沒排這門課）
  藍底 有值      = 實際內容
"""

import pdfplumber, json, re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
PDF_DIR  = BASE_DIR / "data" / "raw" / "應修科目表"
OUT_HTML = BASE_DIR / "tables_editor.html"
SEMESTER_MAP_PATH = BASE_DIR / "data" / "processed" / "requirements_semester_map.json"

PDFS = sorted(PDF_DIR.rglob("*.pdf"))

# ── 收集所有 PDF 表格資料 ────────────────────────────────────

all_data = {}   # dept_name -> [ {page, table_idx, rows: [[cell,...],...]} ]

for pdf_path in PDFS:
    dept = pdf_path.stem
    print(f"Processing: {dept}")
    entries = []
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for pg_i, page in enumerate(pdf.pages):
                for t_i, table in enumerate(page.extract_tables() or []):
                    entries.append({
                        "page": pg_i + 1,
                        "table": t_i + 1,
                        "rows": table   # None / '' / str
                    })
    except Exception as e:
        entries.append({"page":1,"table":1,"rows":[],"error": str(e)})
    all_data[dept] = entries

data_json = json.dumps(all_data, ensure_ascii=False)

# ── 載入萃取結果（若已跑 extract_requirements_pdfplumber.py）────
_semester_raw: dict = {}
if SEMESTER_MAP_PATH.exists():
    try:
        _semester_raw = json.loads(SEMESTER_MAP_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass

# 建立快速查詢表：dept_stem → {課號/標準化課名 → {year_level, semester, low_confidence}}
def _build_lookup(raw: dict) -> dict:
    """raw key 是系所名稱（去掉 _114），value 含 courses 陣列。"""
    lookup: dict[str, dict] = {}
    for dept, info in raw.items():
        entries: dict = {}
        for c in (info.get("courses") or []):
            entries[c["key"]] = {
                "year_level": c.get("year_level"),
                "semester":   c.get("semester"),
                "low_confidence": c.get("low_confidence", False),
            }
        lookup[dept] = entries
    return lookup

_semester_lookup = _build_lookup(_semester_raw)

# dept_stem（HTML sidebar 用的 key）→ 系所名稱（semester_map 的 key）
# PDF stem 格式：系所名稱_114 → normalize 後去掉 _114
def _stem_to_dept(stem: str) -> str:
    return re.sub(r'_\d{3}$', '', stem)

# 把 lookup 序列化進 HTML
semester_lookup_json = json.dumps(
    {_stem_to_dept(k) if re.search(r'_\d{3}$', k) else k: v
     for k, v in _semester_lookup.items()},
    ensure_ascii=False,
)

# ── HTML ────────────────────────────────────────────────────

HTML = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<title>應修科目表 表格編輯器</title>
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: 'Noto Sans TC', sans-serif; font-size: 12px;
       background:#f0f0f0; margin:0; display:flex; height:100vh; overflow:hidden; }}

/* ── sidebar ── */
#sidebar {{ width:220px; background:#263238; color:#cfd8dc; overflow-y:auto;
            flex-shrink:0; padding:8px 0; }}
#sidebar h3 {{ color:#80cbc4; padding:8px 12px; margin:0; font-size:13px; }}
.dept-btn {{ display:block; width:100%; text-align:left; background:none; border:none;
             color:#cfd8dc; padding:6px 14px; cursor:pointer; font-size:11px;
             border-left:3px solid transparent; }}
.dept-btn:hover {{ background:#37474f; }}
.dept-btn.active {{ background:#37474f; border-left-color:#80cbc4; color:white; }}

/* ── main ── */
#main {{ flex:1; display:flex; flex-direction:column; overflow:hidden; }}

/* ── toolbar ── */
#toolbar {{ background:#37474f; color:white; padding:6px 12px;
            display:flex; gap:10px; align-items:center; flex-shrink:0; }}
#toolbar button {{ padding:4px 12px; border:none; border-radius:3px; cursor:pointer; font-size:12px; }}
#btn-export-json  {{ background:#26a69a; color:white; }}
#btn-export-llm   {{ background:#7e57c2; color:white; }}
#btn-reset        {{ background:#ef5350; color:white; }}
#dept-title {{ font-weight:bold; font-size:13px; margin-right:auto; }}
.legend {{ display:flex; gap:8px; align-items:center; font-size:11px; }}
.leg {{ padding:2px 8px; border:1px solid #888; border-radius:2px; }}

/* ── content ── */
#content {{ flex:1; overflow:auto; padding:12px; }}
.table-section {{ margin-bottom:24px; }}
.table-section h3 {{ font-size:12px; color:#555; margin:0 0 4px 0; }}

/* ── table ── */
table {{ border-collapse:collapse; background:white; }}
td {{ border:1px solid #bbb; padding:3px 6px; vertical-align:top;
      min-width:36px; max-width:200px; white-space:pre-wrap;
      word-break:break-all; cursor:text; outline:none; }}
td[data-type="merge"]  {{ background:#ffe0b2; color:#999; font-style:italic; font-size:10px; }}
td[data-type="empty"]  {{ background:#fafafa; color:#ddd; }}
td[data-type="value"]  {{ background:#e3f2fd; }}
td:focus               {{ outline:2px solid #1976d2; }}
td.low-conf            {{ outline:2px solid #ef5350 !important; }}
.ys-tag {{ position:absolute; top:1px; right:2px; font-size:9px;
           background:#43a047; color:white; border-radius:2px;
           padding:0 3px; pointer-events:none; z-index:1; }}
.ys-tag.low {{ background:#ef5350; }}
td {{ position:relative; }}

/* ── context menu ── */
#ctx-menu {{ position:fixed; background:white; border:1px solid #ccc;
             box-shadow:2px 2px 6px rgba(0,0,0,.2); border-radius:4px;
             display:none; z-index:999; min-width:140px; }}
#ctx-menu div {{ padding:7px 14px; cursor:pointer; font-size:12px; }}
#ctx-menu div:hover {{ background:#e0f2f1; }}

/* ── LLM modal ── */
#llm-modal {{ display:none; position:fixed; inset:0; background:rgba(0,0,0,.5);
              z-index:9999; align-items:center; justify-content:center; }}
#llm-modal.show {{ display:flex; }}
#llm-box {{ background:white; width:80%; max-height:80vh; border-radius:6px;
            display:flex; flex-direction:column; overflow:hidden; }}
#llm-box h3 {{ margin:0; padding:10px 14px; background:#7e57c2; color:white; font-size:14px; }}
#llm-box textarea {{ flex:1; border:none; padding:10px; font-family:monospace;
                     font-size:11px; resize:none; outline:none; }}
#llm-box-footer {{ padding:8px 12px; display:flex; gap:8px; background:#f5f5f5; }}
#llm-box-footer button {{ padding:4px 12px; border:none; border-radius:3px;
                           cursor:pointer; background:#7e57c2; color:white; }}
</style>
</head>
<body>

<div id="sidebar">
  <h3>📋 系所列表</h3>
  <div id="dept-list"></div>
</div>

<div id="main">
  <div id="toolbar">
    <span id="dept-title">（選擇系所）</span>
    <div class="legend">
      <span class="leg" style="background:#e3f2fd">藍 = 有值</span>
      <span class="leg" style="background:#ffe0b2">橘 = ◀ merge</span>
      <span class="leg" style="background:#fafafa;color:#aaa">白 = 空白</span>
    </div>
    <button id="btn-export-json">💾 存 JSON</button>
    <button id="btn-export-llm">🤖 看 LLM Markdown</button>
    <button id="btn-export-verified">✅ 匯出年級資料</button>
    <button id="btn-reset">↩ 還原</button>
  </div>
  <div id="content">
    <p style="color:#888;padding:20px;">← 點擊左側系所開始編輯</p>
  </div>
</div>

<div id="ctx-menu">
  <div id="ctx-value">🔵 設為 value（有值）</div>
  <div id="ctx-merge">🟠 設為 merge（合併延伸）</div>
  <div id="ctx-empty">⬜ 設為 empty（空白格）</div>
</div>

<div id="llm-modal">
  <div id="llm-box">
    <h3>🤖 LLM Markdown 格式（可複製進 prompt）</h3>
    <textarea id="llm-text" readonly></textarea>
    <div id="llm-box-footer">
      <button id="btn-copy-llm">📋 複製全部</button>
      <button id="btn-close-llm" style="background:#888;">✕ 關閉</button>
    </div>
  </div>
</div>

<script>
// ── 資料 ─────────────────────────────────────────────────
const RAW = {data_json};

// 萃取結果 lookup：系所名稱 → {{課號/課名 → {{year_level, semester, low_confidence}}}}
const SEMESTER_LOOKUP = {semester_lookup_json};

// working copy: deep clone so edits don't touch RAW
let data = JSON.parse(JSON.stringify(RAW));

let currentDept = null;
let ctxTarget    = null;

// ── 年級標籤輔助 ──────────────────────────────────────────
const SEM_LABELS = ['一上','一下','二上','二下','三上','三下','四上','四下'];
function ysLabel(year_level, semester) {{
  return SEM_LABELS[(year_level - 1) * 2 + (semester - 1)] || `${{year_level}}-${{semester}}`;
}}

// 從文字中嘗試抓課號
function extractCode(text) {{
  const m = text && text.match(/[A-Z]{{2,4}}\\d{{4}}/);
  return m ? m[0] : null;
}}

// 取得目前系所的 lookup（去掉 _114 後綴）
function currentLookup() {{
  if (!currentDept) return {{}};
  const key = currentDept.replace(/_\\d{{3}}$/, '');
  return SEMESTER_LOOKUP[key] || {{}};
}}

// ── sidebar ──────────────────────────────────────────────
const deptList = document.getElementById('dept-list');
Object.keys(data).forEach(dept => {{
  const btn = document.createElement('button');
  btn.className = 'dept-btn';
  btn.textContent = dept.replace(/_114$|_113$/, '').replace(/_/g, ' ');
  btn.dataset.dept = dept;
  btn.onclick = () => loadDept(dept);
  deptList.appendChild(btn);
}});

// ── render dept ──────────────────────────────────────────
function loadDept(dept) {{
  currentDept = dept;
  document.querySelectorAll('.dept-btn').forEach(b => b.classList.toggle('active', b.dataset.dept === dept));
  document.getElementById('dept-title').textContent = dept;
  renderContent();
}}

function renderContent() {{
  const content = document.getElementById('content');
  content.innerHTML = '';
  const entries = data[currentDept] || [];
  if (!entries.length) {{ content.innerHTML = '<p>無資料</p>'; return; }}

  entries.forEach((entry, eIdx) => {{
    const sec = document.createElement('div');
    sec.className = 'table-section';
    const h3 = document.createElement('h3');
    h3.textContent = `Page ${{entry.page}}，Table ${{entry.table}}（${{entry.rows.length}} rows）`;
    sec.appendChild(h3);

    if (entry.error) {{
      sec.innerHTML += `<p style="color:red">錯誤：${{entry.error}}</p>`;
    }} else {{
      sec.appendChild(buildTable(entry.rows, eIdx));
    }}
    content.appendChild(sec);
  }});
}}

function cellType(val) {{
  if (val === null) return 'merge';
  if (val === '')   return 'empty';
  return 'value';
}}

function buildTable(rows, eIdx) {{
  const tbl = document.createElement('table');
  rows.forEach((row, rIdx) => {{
    const tr = document.createElement('tr');
    row.forEach((cell, cIdx) => {{
      const td = document.createElement('td');
      const type = cellType(cell);
      td.dataset.type  = type;
      td.dataset.eIdx  = eIdx;
      td.dataset.rIdx  = rIdx;
      td.dataset.cIdx  = cIdx;

      if (type === 'merge') {{
        td.textContent = '◀ merge';
        td.contentEditable = false;
      }} else {{
        td.textContent = cell ?? '';
        td.contentEditable = true;
      }}

      // live edit → sync to data
      td.addEventListener('input', () => {{
        data[currentDept][eIdx].rows[rIdx][cIdx] = td.textContent;
      }});

      // 年級標籤疊加（從 SEMESTER_LOOKUP 查詢）
      if (type === 'value' && cell) {{
        const lookup = currentLookup();
        const code   = extractCode(String(cell));
        let info = code ? lookup[code] : null;
        // 若無課號，嘗試用標準化課名查（去掉課號、空白）
        if (!info) {{
          const norm = String(cell).replace(/[A-Z]{{2,4}}\\d{{4}}/g,'').replace(/[\\s\\-\\/]+/g,'');
          if (norm.length >= 2) info = lookup[norm];
        }}
        if (info && info.year_level) {{
          const tag = document.createElement('span');
          tag.className = 'ys-tag' + (info.low_confidence ? ' low' : '');
          tag.title = info.low_confidence ? '低可信度，建議確認' : '自動偵測';
          tag.textContent = ysLabel(info.year_level, info.semester);
          td.appendChild(tag);
          if (info.low_confidence) td.classList.add('low-conf');
        }}
      }}

      // right-click context menu
      td.addEventListener('contextmenu', e => {{
        e.preventDefault();
        ctxTarget = td;
        const menu = document.getElementById('ctx-menu');
        menu.style.left = e.clientX + 'px';
        menu.style.top  = e.clientY + 'px';
        menu.style.display = 'block';
      }});

      tr.appendChild(td);
    }});
    tbl.appendChild(tr);
  }});
  return tbl;
}}

// ── context menu actions ──────────────────────────────────
function applyType(td, type) {{
  const eIdx = +td.dataset.eIdx, rIdx = +td.dataset.rIdx, cIdx = +td.dataset.cIdx;
  td.dataset.type = type;
  if (type === 'merge') {{
    data[currentDept][eIdx].rows[rIdx][cIdx] = null;
    td.textContent = '◀ merge';
    td.contentEditable = false;
  }} else if (type === 'empty') {{
    data[currentDept][eIdx].rows[rIdx][cIdx] = '';
    td.textContent = '';
    td.contentEditable = true;
  }} else {{
    const cur = data[currentDept][eIdx].rows[rIdx][cIdx];
    data[currentDept][eIdx].rows[rIdx][cIdx] = (cur === null || cur === '') ? '' : cur;
    td.textContent = data[currentDept][eIdx].rows[rIdx][cIdx];
    td.contentEditable = true;
    td.focus();
  }}
}}

document.getElementById('ctx-value').onclick = () => {{ if(ctxTarget) applyType(ctxTarget,'value'); hideMenu(); }};
document.getElementById('ctx-merge').onclick = () => {{ if(ctxTarget) applyType(ctxTarget,'merge'); hideMenu(); }};
document.getElementById('ctx-empty').onclick = () => {{ if(ctxTarget) applyType(ctxTarget,'empty'); hideMenu(); }};
document.addEventListener('click', hideMenu);
function hideMenu() {{ document.getElementById('ctx-menu').style.display = 'none'; }}

// ── 匯出年級資料（人工確認後的版本）────────────────────────
document.getElementById('btn-export-verified').onclick = () => {{
  if (!currentDept) return alert('請先選擇系所');
  const lookup = currentLookup();
  const verified = {{}};
  // 重新掃描當前系所的表格，抓所有有課號的格子
  (data[currentDept] || []).forEach(entry => {{
    (entry.rows || []).forEach(row => {{
      row.forEach(cell => {{
        if (!cell) return;
        const code = extractCode(String(cell));
        if (!code) return;
        const info = lookup[code];
        if (info && info.year_level) {{
          verified[code] = {{
            year_level: info.year_level,
            semester:   info.semester,
            low_confidence: info.low_confidence,
          }};
        }}
      }});
    }});
  }});
  const out = {{ [currentDept.replace(/_\\d{{3}}$/, '')]: verified }};
  const blob = new Blob([JSON.stringify(out, null, 2)], {{type: 'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = currentDept + '_verified.json';
  a.click();
}};

// ── export JSON ───────────────────────────────────────────
document.getElementById('btn-export-json').onclick = () => {{
  if (!currentDept) return alert('請先選擇系所');
  const blob = new Blob([JSON.stringify(data[currentDept], null, 2)], {{type:'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = currentDept + '_table.json';
  a.click();
}};

// ── reset ─────────────────────────────────────────────────
document.getElementById('btn-reset').onclick = () => {{
  if (!currentDept) return;
  if (!confirm('還原 ' + currentDept + ' 的所有修改？')) return;
  data[currentDept] = JSON.parse(JSON.stringify(RAW[currentDept]));
  renderContent();
}};

// ── LLM Markdown ─────────────────────────────────────────
document.getElementById('btn-export-llm').onclick = () => {{
  if (!currentDept) return alert('請先選擇系所');
  const lines = [`# ${{currentDept}} 應修科目表\\n`];
  (data[currentDept] || []).forEach(entry => {{
    lines.push(`## Page ${{entry.page}} Table ${{entry.table}}\\n`);
    const rows = entry.rows;
    if (!rows.length) return;
    // build markdown table
    // header = first row
    const cols = Math.max(...rows.map(r => r.length));

    rows.forEach((row, ri) => {{
      const cells = Array.from({{length: cols}}, (_, i) => {{
        const v = row[i] ?? null;
        if (v === null) return '`←M`';   // merge
        if (v === '')   return '';         // empty
        return v.replace(/\\n/g,'↵').replace(/\\|/g,'\\\\|');
      }});
      lines.push('| ' + cells.join(' | ') + ' |');
      if (ri === 0) lines.push('|' + Array(cols).fill('---').map(s=>' '+s+' ').join('|') + '|');
    }});
    lines.push('');
    // legend reminder
    lines.push('> `←M` = 合併延伸格（None），空白 = 此學期無此課\\n');
  }});
  document.getElementById('llm-text').value = lines.join('\\n');
  document.getElementById('llm-modal').classList.add('show');
}};

document.getElementById('btn-copy-llm').onclick = () => {{
  const ta = document.getElementById('llm-text');
  ta.select();
  document.execCommand('copy');
  document.getElementById('btn-copy-llm').textContent = '✅ 已複製！';
  setTimeout(() => document.getElementById('btn-copy-llm').textContent = '📋 複製全部', 1500);
}};
document.getElementById('btn-close-llm').onclick = () => {{
  document.getElementById('llm-modal').classList.remove('show');
}};
</script>
</body>
</html>
"""

OUT_HTML.write_text(HTML, encoding="utf-8")
print(f"\n✅ 已輸出：{OUT_HTML}")
print(f"   共處理 {len(PDFS)} 個 PDF")
