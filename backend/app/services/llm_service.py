"""
llm_service.py

Azure OpenAI GPT-4o 呼叫 + LangSmith 監控。

環境變數：
  AZURE_OPENAI_API_KEY          — Azure OpenAI 金鑰
  AZURE_OPENAI_ENDPOINT         — https://<resource>.openai.azure.com/
  AZURE_OPENAI_API_VERSION      — 例如 2024-12-01-preview
  AZURE_OPENAI_CHAT_DEPLOYMENT  — 對話模型的部署名稱（例如 gpt-4o）
  LANGSMITH_API_KEY             — LangSmith 金鑰（選填）
  LANGSMITH_PROJECT             — LangSmith 專案名稱（預設 "ncu-rag-system"）
"""

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Optional

from openai import AzureOpenAI

try:
    from langsmith import traceable
    from langsmith.wrappers import wrap_openai
    _LANGSMITH_AVAILABLE = True
except ImportError:
    _LANGSMITH_AVAILABLE = False

    def traceable(func=None, **kwargs):
        if func is not None:
            return func
        def decorator(f):
            return f
        return decorator


MAX_TOKENS = 2048

def _build_completion_params(**kwargs) -> dict:
    """
    建立支援 max_tokens 和 max_completion_tokens 的參數字典。
    自動根據 API 回應調整參數名稱。
    """
    params = dict(kwargs)
    max_val = kwargs.get("max_tokens") or kwargs.get("max_completion_tokens")

    if max_val:
        # 移除舊參數名稱，優先使用 max_completion_tokens（新標準）
        params.pop("max_tokens", None)
        params.pop("max_completion_tokens", None)
        params["max_completion_tokens"] = max_val

    return params

SYSTEM_PROMPT = """你是「中央大學選課助理」，協助高中生、大學生了解中央大學的課程、系所、學分學程資訊。使用繁體中文，語氣像學長姐：友善、簡短、白話。

## 一、不可違反的原則（防止幻覺）

1. 只能說工具這一輪實際回傳的內容。沒查到就說「中大課程資料中沒有查到」，並指向可查證的方向（系網、教務處），不要用常識補答案。
2. 使用者提到的系所、課程、老師、學程若不在工具回傳中，一律視為查無。搜尋結果只是「相近」的課，不能說成就是使用者問的那個；有名稱相近的其他單位（例如研究所）要明說是不同單位。工具回傳 found=False 時只能列 fallback_candidates，不得自行推斷或補全名稱（例如不可把「法律與政府研究所」猜成「法律與政府學系」）。
3. 資料庫沒有的內容不得回答也不得暗示：薪資、就業率與出路統計、錄取分數、招生名額、課程涼不涼／好不好過、老師評價、「適合什麼個性」。學生問到時簡短說明沒有這類資料，再轉到可查證的內容（課程在學什麼、需要哪些基礎）。
4. 不保證結果：不說「一定」「保證」「不用數學」「絕對跟不上」，也不替學生決定該讀哪個系。
5. 不編造網址、電話、信箱、辦公室位置或活動日期；工具沒回傳就不提供。
6. 資料是 114 學年：開課、時間、教師、名額、修課限制可能變動，涉及選課、必修、畢業時提醒以選課系統與教務公告為準。
7. 區分「課程資料上寫的」與「你的歸納」：歸納用「看起來」「大致偏向」等保留語氣，且必須能由查到的課程支持。
8. 「學生背景資訊」是自述、未經查證：可用來調整建議，但不能據此推論修課資格（仍須查課程的修課限制）。
9. 只回答中央大學的課程、系所、學分學程與修課規定；其他學校或無關問題，簡短說明範圍後婉拒。
10. 回答中不要出現系統技術用語：「知識圖譜」「圖譜」「語意相近」「精確命中」「節點」「向量搜尋」「工具回傳」「系統查詢」。可以說「依中大 114 學年課程資料」。

## 二、怎麼回答高中生

**長度與份量**（最常出錯，請遵守）
- 一般回答控制在約 500 字內。探索或比較時最多 3–4 條路徑，每條 2–3 門代表課並說明它在學什麼；完整清單等學生要求再給。
- 先講「大學會學什麼」，再用課名佐證；不要整段倒課名。同一則回答不要把相同內容換句話再寫一遍。
- **學生明確指定要什麼，就照做**：要「完整必修」「全部列出」「逐年課表」這類完整清單時，依要求完整列出（仍只列工具回傳的課），不受字數與路徑數限制；課數沒有上限。

**先問還是先查**
- **有線索 → 先查再答，最後只問一個問題。** 學生提到任何具體的主題、科目、興趣關鍵詞或想做的東西（天氣、機率、寫程式、做 App、要在兩個系之間選），就先呼叫工具，用查到的資料給 2–3 個方向，每個方向一兩句話加 1–2 門代表課，最後問一個能幫他縮小範圍的問題。不要只丟問題而不給任何系所或課程。
- **只要出現一個具體名詞就算有線索**：科目、領域、興趣、作品、系所或課名（「機率」「天氣」「做 App」「資工」）都算。不要因為還不知道年級、分數、志向，就改成只問不查。
- **學生已經說清楚要查什麼**（點名系所、課名、要完整清單或比較哪兩個系）時，直接查並回答，不要先反問。
- **完全沒線索 → 只問不查。** 學生只說「我不知道喜歡什麼」「喜歡動手做」這類沒有科系、主題或作品線索的話，這一輪只用口語問 1–2 個問題並給 2–3 個選項讓學生挑；不呼叫工具，也不要同時列出路徑與課程。問題只出現一次。
- **事實性問題一律查證，不憑印象。** 「資工會不會跟不上」「這個系有沒有數學」「這門課要先修什麼」這類問題，以及任何涉及具體課程、系所、學程、教師、修課或畢業規定的資訊，都要呼叫工具，不可只憑常識、記憶或對話歷史回答（對話歷史只用來理解語境）。聊興趣、問「什麼是學分」這類一般名詞才不需要工具。

**說明方式**
- 第一次出現學分、必修、選修、先修、學程等詞，用一句白話解釋。
- 比較兩個系：分「相同的地方」「不同的地方」「各自代表課」，用查到的課程支持，不評價誰比較好、誰比較簡單。
- 遇到迷思或錯誤前提（「資工不用數學」「自然組讀文學院是浪費」），先溫和說明課程資料看到的樣子，不照單接受，也不空泛安慰。
- 資料查不到的需求（例如藝術創作）明說中大課程資料中沒有對應，再提供可查證的相近課程。
- 結尾給一個可行的下一步（例如「想先看哪一類？」）。

## 三、課程標籤 <course>

- 提到課程名稱時用 `<course>課名（系所）</course>` 包住；不知道系所時用 `<course>課名</course>`；同名但學分不同時用 `<course>課名（2學分）</course>`。
- 課名必須與工具回傳的原始名稱逐字相同；只標工具回傳過、且正文中實際點名的課。不確定就不要標，寧可不標也不要標錯。同名有多個版本又無法確定是哪個時不標，在文字中說明。
- 標籤只能包課程名稱。課程涵蓋的「概念」與「技術」（二元搜尋樹、動態規劃、Python、C++）不是課程，一律用純文字；老師姓名、系所名稱、學分學程名稱同樣不是課程，不加標籤。
- 課程卡片依標籤顯示，沒被點名的課不用標。工具回傳 0 筆時不得標任何課程。

## 四、工具怎麼選

各工具的參數與用途以工具說明為準，這裡只列容易選錯的地方。

- **認識、比較系所**（「XX系在學什麼」「A系和B系差在哪」）→ get_dept_overview(dept_name)，支援「資工系」「化材系」等縮寫；比較時兩系各呼叫一次並行。
  回傳全部必修課 required_courses（有分組的系為 common_required_courses + tracks）、畢業學分 graduation、課程領域 course_domains 與核心能力 core_competencies（課綱原有欄位，可直接引用）、涵蓋主題 topic_fields／技術 technologies／每門課的 topics（系統分析，語氣要保留，如「課程內容常涉及…」）、選修分布 elective_by_domain 與 elective_rules。
  介紹時用「大一學什麼、大二學什麼」的順序；必修要完整列出，不要挑幾門就說是全部；必修清單不含共同必修（國文、英文、體育），講總學分用 graduation 並說明差異；outline_available 為 false 的課不要補寫；出現 stats_warning 時明說可統計的課很少，不據此歸納特色。只能依回傳資料說明，不補寫系所特色、生涯進路；這是課程統計，不是系所官方介紹，必要時提醒看系網。
- **系所課表、選修清單** → get_dept_courses(dept_name, course_type)；total_found 超過 15 時說「共有 X 門，以下列出代表性的」。
- **通識、外語、主題式查詢**（「通識有沒有法律課」「語言中心有日文嗎」「哪些課培養溝通能力」）→ search_courses(query, dept="通識教育中心" 或 "語言中心")。不要用 get_dept_courses("通識教育中心") 當通識清單（會混入跨開課的普通物理、電路學），除非學生明確要完整清單；通識廣泛問法先問想看哪個主題。
- **技術**（「哪裡有教 PyTorch」）→ search_courses(query, tech="技術名")；只有學生問「哪些系所有教」才再呼叫 get_depts_by_tech。回答時：有必修／選修科系就直接引用清單；某類為空說「目前沒有科系將 XX 列為必修／選修」；完全沒有說「目前沒有查到教 XX 的系所資料」，不補系所；補充（◆相關）結果依課名本身判斷是否真的教到該技術。
- **具體課名、課綱、先修、修課資格**（「外系可以修嗎」）→ get_course_detail(name_zh 或 course_code)；raw_conditions 已含先修與限制原文，不用再呼叫其他工具。回傳 ambiguous=True（同名多系）時請學生選系；found=False 時列 fallback_candidates 請學生確認。查不到再用 search_courses(exclude_grad_only=False)：只有研究所版本或已停開都要明說。
- **課程在教什麼概念、有沒有類似的課** → get_course_knowledge_map（課程涵蓋的概念與技術，不含先修資訊）與 find_similar_courses；通識、人文課無結果時改用 search_courses。
- **已有明確概念或技術詞**（「有哪些課涵蓋神經網路」）→ explore_concept_neighborhood(query)。
- **廣泛探索**（「AI 相關有哪些」「我對 XX 有興趣」）→ ppr_explore(seed, focus)：多個概念用逗號分隔成多個 seed；focus 預設 "course"，找老師用 "instructor"，找系所用 "dept"；"overview" 只在學生明確要「課程＋教師＋系所」全貌時用，用完要再 search_courses 補完整課程並說明「以下是代表性課程」。以課名為 seed（微積分、線性代數）必須用 focus="course"。不要用 ppr_explore 找某一門具體的課。
- **老師** → ppr_explore(focus="instructor") 或 search_teachers 找人，再 get_teacher_info(姓名)；姓名必須來自上一步回傳，不可自己想。老師資料偏少時照實說「這個方向目前查到的老師資料不多」。
- **學程** → 不知道名稱先 search_programs(query)，知道名稱用 get_program_info(program_name)。
- **畢業規定** → get_graduation_requirements(dept_name)，一次呼叫即可。
- 同一輪查詢的主題相同、只換修飾詞時合併成一次。工具無結果時換更短的核心詞，或改用 search_courses 重試；ppr_explore、get_depts_by_tech 回傳 0 筆時不得標任何課程，也不得自行補課名。

**Filter 只在學生明確說出條件時才加**
- dept：提到「XX系開的課」才加。college 限制開課學院；student_college 依學生身份過濾（含全校開放課程）。兩者意思相反，不要混用：「文學院開設的機器學習」→ college；「文學院學生可以修的機器學習」→ student_college。
- course_type：學生說「選修」「必修」才加。exclude_grad_only 預設 true，學生明確問研究所課程才設 false。

## 五、工具回傳欄位

- concepts、technologies、field_tags 是系統分析出的內容，說明「課程教什麼」時用保留語氣；course_domain 與 competencies 是課綱原有欄位。
- competencies 每筆為 {name, level_num, level_label}，level_num 是 0–5（無／非常低／低／普通／高／非常高）。多數課都標「高」或「非常高」，區分力有限：只說「課綱標示此能力強度為高」，不說「精通」，也不用它比較兩門課誰比較強。
- search_courses：exact_match 為 true 代表課名完全相同，優先呈現；matched_via 說明此課為何出現。get_dept_courses：sections 是同名課的開課班數。

## 六、範例

**範例 A — 比較系所**
問：資工系和電機系都會寫程式嗎？實際學的東西差在哪裡？
✓ 並行 get_dept_overview("資訊工程學系") + get_dept_overview("電機工程學系")，再照下面的形狀回答，語氣保留（「課程內容常涉及…」）：
　**相同的地方**：兩系都有程式與數學基礎，例：〈查到的共同課或主題〉
　**不同的地方**：資工偏〈查到的主題〉、電機偏〈查到的主題〉，各用一兩句講它在學什麼
　**各自代表課**：每系列出查到的代表課（課數視資料而定，不設上限），每門一句說明它學什麼
　最後問一題幫他縮小範圍
✗ 只查一邊、另一邊憑印象補；或直接說「資工比較難」「電機比較好找工作」

**範例 B — 資訊太少，先問不查**
問：我不知道自己喜歡什麼，只知道數學不算差，可以從哪些科系開始看？
✓ 不呼叫工具；用口語問 1–2 題（例如：比較喜歡把東西做出來，還是想弄懂背後的原理？），並給 2–3 個選項
✗ 一次丟出 20 門課；只推薦單一科系；問完又接著列出路徑

**範例 B2 — 有線索，先查再問**
問：我常常會注意天氣、雲和颱風，但不知道這能讀什麼。
✓ 先呼叫工具（例如 get_dept_overview 或 search_courses）；回答 2–3 個方向各一兩句，附 1–2 門查到的代表課（偏天氣本身、偏資料與預報…），最後問一題：「你比較想弄懂天氣怎麼形成，還是想用資料做預報？」
✗ 沒查任何資料，只回兩個問題讓學生選；或一次列出一長串課名

**範例 C — 查無系所**
問：中大法律系有哪些跟科技法律有關的課？
✓ 先查證；沒有就直說「中大資料中沒有法律系」，再用 search_courses 找法律、資訊社會相關的課，並說明是通識或其他單位開的；有名稱相近的單位（如研究所）要說明是不同單位
✗ 把相近名稱當成使用者問的系所；用一般印象描述「法律系」的課

**範例 D — 老師（串行）**
問：哪些教授在研究深度學習？他們的專長是什麼？
✓ 第一步 ppr_explore(seed="深度學習", focus="instructor")；第二步 get_teacher_info("第一步結果中的姓名")
✗ 自己想一個教授姓名去查

**範例 E — 先修與修課資格**
問：外系學生可以修客語教學這門課嗎？
✓ get_course_detail(name_zh="客語教學")；不確定課名時先 search_courses 確認
✗ 用 search_programs 或 search_courses 代替；沒查就憑印象回答

## 最後再提醒

1. 只說工具回傳的內容，沒查到就說沒查到。
2. 標籤只包課程名稱，不包概念、技術、老師、系所、學程。
3. 約 500 字內、最多 3–4 條路徑（學生明確要完整清單時例外）。有線索先查再答、最後只問一題；完全沒線索才只問不查；事實性問題一律查證。
"""


@lru_cache(maxsize=1)
def _get_client() -> AzureOpenAI:
    api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    if not api_key or not endpoint:
        raise EnvironmentError("請設定 AZURE_OPENAI_API_KEY 和 AZURE_OPENAI_ENDPOINT 環境變數")

    client = AzureOpenAI(
        api_key=api_key,
        azure_endpoint=endpoint,
        api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
    )

    # LangSmith 包裝（若有設定 API key 才啟用）
    if (
        _LANGSMITH_AVAILABLE
        and os.environ.get("LANGSMITH_API_KEY")
        and os.environ.get("LANGSMITH_TRACING", "true").lower() == "true"
    ):
        return wrap_openai(client)
    return client


def _build_context(
    vector_results: list[dict],
    graph_results: dict,
) -> str:
    """將向量搜尋結果和圖查詢結果組裝成 context 字串"""
    parts: list[str] = []

    if vector_results:
        parts.append("【相關課程資訊】")
        for i, r in enumerate(vector_results[:6], 1):
            meta = r.get("metadata", {})
            name = meta.get("name_zh", "")
            dept = meta.get("dept", "")
            credits = meta.get("credits", "")
            type_ = meta.get("type", "")
            teacher = meta.get("teacher", "")
            doc = r.get("document", "")[:300]

            header = f"{i}. {name}"
            if dept:
                header += f"（{dept}"
                if credits:
                    header += f"，{credits}學分"
                if type_:
                    header += f"，{type_}"
                header += "）"
            if teacher:
                header += f" ／ 授課：{teacher}"
            parts.append(header)
            if doc:
                parts.append(f"   {doc}")
            spec = meta.get("teacher_specialties", "")
            when_raw = meta.get("when_raw", "")
            prereq = meta.get("prereq_codes", "")
            eligible = meta.get("eligible_years", "")
            if spec:
                parts.append(f"   教師專長：{spec[:80]}")
            if when_raw:
                parts.append(f"   建議修習：{when_raw}")
            if prereq:
                parts.append(f"   先修課號：{prereq}")
            if eligible:
                parts.append(f"   適合年級：{eligible}")
            parts.append("")

    if graph_results:
        if graph_results.get("required_courses"):
            parts.append("【系所必修課程】")
            for c in graph_results["required_courses"][:20]:
                line = f"- {c.get('name', c.get('id', ''))}"
                if c.get("credits"):
                    line += f"（{c['credits']}學分）"
                parts.append(line)
            parts.append("")

        if graph_results.get("elective_courses"):
            parts.append("【系所選修課程】")
            for c in graph_results["elective_courses"][:20]:
                line = f"- {c.get('name', c.get('id', ''))}"
                if c.get("credits"):
                    line += f"（{c['credits']}學分）"
                parts.append(line)
            parts.append("")

        if graph_results.get("program_courses"):
            parts.append("【學程課程】")
            for c in graph_results["program_courses"][:20]:
                line = f"- {c.get('name', c.get('id', ''))}（{c.get('relation', '')}）"
                parts.append(line)
            parts.append("")

        if graph_results.get("teacher_courses"):
            parts.append("【教師開課】")
            for c in graph_results["teacher_courses"][:10]:
                line = f"- {c.get('name', c.get('id', ''))}"
                parts.append(line)
            parts.append("")

        if graph_results.get("graduation_info"):
            info = graph_results["graduation_info"]
            parts.append(f"【畢業規定：{info.get('dept_name', '')}】")
            parts.append(f"最低畢業學分：{info.get('min_credits', 0)}")
            parts.append(f"必修學分：{info.get('required_credits', 0)}")
            for rule in info.get("graduation_rules", [])[:8]:
                parts.append(f"- {rule.get('description', '')}")
            certs = info.get("certifications", [])
            if certs:
                parts.append(f"證照要求：{', '.join(certs)}")
            parts.append("")

        if graph_results.get("prereq_courses"):
            parts.append("【先修課程詳情】")
            for r in graph_results["prereq_courses"][:5]:
                m = r.get("metadata", {})
                parts.append(f"- {m.get('name_zh', r.get('id', ''))}（{m.get('dept', '')}）")
            parts.append("")

    return "\n".join(parts) if parts else "（無相關資料）"


@traceable(name="ncu_rag_answer", run_type="llm")
def generate_answer(
    question: str,
    vector_results: Optional[list[dict]] = None,
    graph_results: Optional[dict] = None,
    extra_context: Optional[str] = None,
) -> dict:
    """
    根據 context 生成回答。

    回傳：
      {"answer": str, "model": str, "input_tokens": int, "output_tokens": int}
    """
    client = _get_client()
    deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o")

    context = _build_context(vector_results or [], graph_results or {})
    if extra_context:
        context = extra_context + "\n\n" + context

    user_message = f"""以下是關於這個問題的相關資料：

{context}

問題：{question}

請根據上面的資料回答問題。"""

    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        **_build_completion_params(max_completion_tokens=MAX_TOKENS)
    )

    answer = response.choices[0].message.content or ""
    return {
        "answer": answer,
        "model": deployment,
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
    }


def generate_simple_answer(question: str, context: str) -> str:
    """輕量版：直接傳入 context 字串"""
    result = generate_answer(question, extra_context=context)
    return result["answer"]


def _enrich_course_cards(cards: list[dict]) -> list[dict]:
    """以課名向量 DB 補齊 code/teacher/credits/type/domain_tags 等欄位。
    code 已存在表示來自 search_courses（基本資料完整），只補 domain_tags。
    code 為空表示來自 graph 工具，需補全所有欄位。
    """
    from app.services import retriever
    for card in cards:
        has_code = bool(card.get("code"))
        if has_code and card.get("domain_tags"):
            continue  # 已完整，跳過
        try:
            if has_code:
                results = retriever.get_courses_by_code(card["code"])
                if not results:
                    results = retriever.get_courses_by_code(
                        card["code"], collection="ncu_courses_grad"
                    )
            else:
                results = retriever.get_courses_by_name(card["name"])
            if results:
                meta = results[0].get("metadata", {})
                if not has_code:
                    card["code"]    = meta.get("course_code", "")
                    card["teacher"] = card.get("teacher") or meta.get("teacher", "")
                    card["credits"] = card.get("credits") or meta.get("credits", 0)
                    card["type"]    = card.get("type")    or meta.get("type", "")
                # domain_tags：優先取有 score 的 domain_tags_rich，fallback plain list
                raw = meta.get("domain_tags_rich") or meta.get("domain_tags") or []
                if isinstance(raw, list) and raw:
                    card["domain_tags"] = "||".join(str(x) for x in raw)
                elif isinstance(raw, str) and raw:
                    card["domain_tags"] = raw
        except Exception:
            pass
    return cards


def _verify_course_list(question: str, answer: str, course_pool: dict) -> list[dict]:
    """讓 LLM 從 course_pool 中選出真正相關的課程（一次集中驗證）。
    LLM 只能從 pool 中選，不能發明課程 → 確保無幻覺。
    """
    if not course_pool:
        return []

    client = _get_client()
    deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o")

    pool_items = list(course_pool.items())[:60]

    def _pool_line(name: str, c: dict) -> str:
        parts = [f"{name}（{c.get('dept', '')}，{c.get('credits', 0) or '?'}學分）"]
        # 附上 tech/tools 讓 LLM 知道課程實際教什麼，避免單憑課名誤判
        tech = " | ".join(filter(None, [c.get("tools", ""), c.get("languages", ""), c.get("tech", "")]))
        if tech:
            parts.append(f"[技術：{tech}]")
        return " ".join(parts)

    pool_text = "\n".join(_pool_line(name, c) for name, c in pool_items)

    prompt = f"""助理回答：{answer[:800]}

以下是本次工具搜尋到的課程：
{pool_text}

請從上面清單中選出在「助理回答」裡有被提及或推薦的課程。
目的：確認回答不包含工具未找到的課程（反幻覺），不是重新評估課程是否相關。
規則：只能選清單裡有的課程，不能新增其他課程。
輸出格式：每行一個課程名稱，不要任何說明、編號或括號。"""

    try:
        resp = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            **_build_completion_params(max_completion_tokens=300)
        )
        raw_lines = (resp.choices[0].message.content or "").splitlines()
    except Exception:
        return list(course_pool.values())

    pool_map = dict(course_pool)
    result: list[dict] = []
    seen: set[str] = set()
    for line in raw_lines:
        name = line.strip().lstrip("•-·0123456789.）) ").strip()
        if '（' in name:
            name = name[:name.index('（')].strip()
        if not name or len(name) < 2 or name in seen:
            continue
        if name in pool_map:
            seen.add(name)
            result.append(pool_map[name])

    return result


def _collapse_repeated_answer(text: str) -> str:
    """模型偶爾會把整篇回答原樣寫兩遍（評測 100 題中約 3–4 題）；若整篇是同一組段落重複 2 次以上，只留一份。

    只處理「整篇重複」。同一門課在不同小節各列一次這類正常內容不受影響。
    """
    paras = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    norm = [" ".join(p.split()) for p in paras]
    n = len(norm)
    if n < 2 or len(text.strip()) < 30:
        return text
    for size in range(1, n // 2 + 1):
        if n % size == 0 and norm == norm[:size] * (n // size):
            return "\n\n".join(paras[:size])
    return text


def _extract_courses_from_tags(answer: str, course_pool: dict) -> tuple[list[dict], str]:
    """從回答中的 <course>課名（系所）</course> 標籤提取課程，exact + fuzzy match pool。

    支援帶系所的消歧義格式：<course>統計學（數學系）</course>
    pool 的 key 可能是 course_code（search_courses 路徑）或課名（圖工具路徑），
    以 card["name"] 建立名稱 → list[card] 索引，保留所有同名版本。
    若 LLM 未輸出任何標籤，回傳 ([], answer)。

    fuzzy match 成功時，同步修正 answer text 裡的錯誤課名，確保 <course> tag 與 card 名稱一致。
    回傳 (course_cards, corrected_answer)。
    """
    from difflib import SequenceMatcher

    # 支援 <course>課名</course> / <course>課名（系所）</course> / <course>課名（N學分）</course>
    TAG_RE      = re.compile(r'<course>(.*?)(?:（([^）]*)）)?</course>', re.DOTALL)
    CREDITS_RE  = re.compile(r'^(\d+)\s*學分$')
    tag_matches = TAG_RE.findall(answer)
    if not tag_matches:
        return [], answer

    # name → list[card]，保留所有同名版本（不覆蓋）
    name_index: dict[str, list[dict]] = {}
    for card in course_pool.values():
        cname = card.get("name", "")
        if cname:
            name_index.setdefault(cname, []).append(card)

    result: list[dict] = []
    seen: set[str] = set()
    corrections: dict[str, str] = {}  # 錯誤課名 → 正確課名

    for raw_name, hint in tag_matches:
        name = raw_name.strip()
        hint = hint.strip() if hint else ""
        if not name:
            continue

        # 1. Exact match by course name
        candidates = name_index.get(name, [])
        if candidates:
            if len(candidates) == 1:
                matched_list = [candidates[0]]
            elif hint:
                cm = CREDITS_RE.match(hint)
                if cm:
                    # 括號內是「N學分」→ 以學分數消歧義
                    credits_val = int(cm.group(1))
                    filtered = [c for c in candidates if c.get("credits") == credits_val]
                    matched_list = filtered if filtered else candidates
                else:
                    # 括號內是系所名 → 以系所消歧義
                    filtered = [c for c in candidates if hint in c.get("dept", "")]
                    matched_list = filtered if filtered else candidates
            else:
                # 無 hint 且有多個候選：回傳全部版本，不任意選 first
                matched_list = candidates

            for matched in matched_list:
                uid = f"{matched.get('name', '')}|{matched.get('dept', '')}|{matched.get('credits', 0)}"
                if uid not in seen:
                    seen.add(uid)
                    result.append(matched)
            continue

        # 2. Fuzzy match (ratio >= 0.85)
        best_key, best_ratio = None, 0.0
        for cname in name_index:
            ratio = SequenceMatcher(None, name, cname).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_key = cname

        if best_ratio >= 0.85 and best_key:
            matched = name_index[best_key][0]
            uid = f"{matched.get('name', '')}|{matched.get('dept', '')}|{matched.get('credits', 0)}"
            if uid not in seen:
                seen.add(uid)
                result.append(matched)
            if name != best_key:
                corrections[name] = best_key

    # 修正 answer 裡因 LLM 幻覺產生的錯誤課名（只替換 <course> tag 內的部分）
    corrected = answer
    for wrong, correct in corrections.items():
        corrected = corrected.replace(f"<course>{wrong}", f"<course>{correct}")

    return result, corrected


def _parse_courses_from_str(tool_name: str, text: str) -> list[dict]:
    """從字串型工具回傳中以 regex 解析課程名稱與系所。"""
    import re
    courses: list[dict] = []

    if tool_name == "ppr_explore":
        # [課程] 深度學習程式設計（通訊工程學系）
        for m in re.finditer(r'\[課程\]\s*(.+?)（(.+?)）', text):
            name, dept = m.group(1).strip(), m.group(2).strip()
            if name:
                courses.append({"name": name, "dept": dept, "credits": 0, "type": "", "code": "", "teacher": ""})

    elif tool_name in ("find_similar_courses", "get_course_knowledge_map", "explore_concept_neighborhood"):
        if tool_name == "get_course_knowledge_map":
            # 第一行是被查詢的課本身：【演算法】（生醫科學與工程學系，3學分）；不是清單行，要另外解析
            hm = re.match(r'\s*【(.+?)】（([^，）]+)(?:，(\d+)學分)?）', text)
            if hm and len(hm.group(1).strip()) >= 2:
                courses.append({
                    "name": hm.group(1).strip(), "dept": hm.group(2).strip(),
                    "credits": int(hm.group(3)) if hm.group(3) else 0,
                    "type": "", "code": "", "teacher": "",
                })
            # 另有同名課程：演算法（資訊管理學系，3學分）、演算法（通訊工程學系，3學分）
            om = re.search(r'另有同名課程：(.+)', text)
            if om:
                for m in re.finditer(r'([^、：]+?)（([^，）]+)(?:，(\d+)學分)?）', om.group(1)):
                    courses.append({
                        "name": m.group(1).strip(), "dept": m.group(2).strip(),
                        "credits": int(m.group(3)) if m.group(3) else 0,
                        "type": "", "code": "", "teacher": "",
                    })
        # - 深度學習程式設計（通訊工程學系，3學分） [共享概念：8 個]
        # 學分前可能有空格（「3 學分」，概念鄰域工具的寫法）
        for m in re.finditer(r'-\s*(.+?)（([^，）]+)(?:，\s*(\d+)\s*學分)?）', text):
            name = m.group(1).strip()
            dept = m.group(2).strip()
            credits = int(m.group(3)) if m.group(3) else 0
            # 已停開的課不放進卡片（工具回傳會在課名後加 [已停開]）
            if name and not name.startswith('[') and '[已停開]' not in name and len(name) >= 2:
                courses.append({"name": name, "dept": dept, "credits": credits, "type": "", "code": "", "teacher": ""})

    elif tool_name == "get_depts_by_tech":
        # 格式：每門課程以 4 格縮排 + dash 開頭，例如
        #   - Python程式設計（機械工程學系） → 選修：機械工程學系
        for line in text.splitlines():
            m = re.match(r'\s{2,}-\s+(.+?)（(.+?)）', line)
            if m:
                name, dept = m.group(1).strip(), m.group(2).strip()
                if name and len(name) >= 2 and not name.startswith('【') and not name.startswith('▲') and not name.startswith('◆'):
                    courses.append({"name": name, "dept": dept, "credits": 0, "type": "", "code": "", "teacher": ""})

    return courses


def _collect_course_pool(tool_name: str, result, course_pool: dict) -> None:
    """從單次工具回傳結果中收集課程資料到 course_pool。"""
    if tool_name == "search_courses" and isinstance(result, list):
        for item in result:
            key = item.get("course_code") or item.get("name_zh", "")
            if key:
                course_pool[key] = {
                    "code":    item.get("course_code", ""),
                    "name":    item.get("name_zh", ""),
                    "dept":    item.get("dept", ""),
                    "credits": item.get("credits", 0),
                    "type":    item.get("type", ""),
                    "teacher": item.get("teacher", ""),
                }
    elif tool_name in ("get_dept_courses", "get_program_courses", "get_program_info") and isinstance(result, dict):
        dept_or_prog = result.get("dept_name") or result.get("program_name", "")
        for c in result.get("courses", []):
            name = c.get("name") or c.get("id", "")
            if name:
                course_pool[name] = {
                    "code":    c.get("id", ""),
                    "name":    name,
                    "dept":    dept_or_prog,
                    "credits": c.get("credits", 0),
                    "type":    c.get("relation", ""),
                    "teacher": c.get("teacher", ""),
                }
    elif tool_name == "get_dept_overview" and isinstance(result, dict) and result.get("found"):
        dept = result.get("dept_name", "")
        listed = list(result.get("required_courses", [])) + list(result.get("common_required_courses", []))
        for t in result.get("tracks", []):
            listed += t.get("track_required_courses", [])
        for c in listed:
            name = c.get("name", "")
            if name:
                course_pool[name] = {
                    "code":    (c.get("course_ids") or [""])[0],
                    "name":    name,
                    "dept":    dept,
                    "credits": c.get("credits", 0),
                    "type":    "必修",
                    "teacher": "",
                }
        # 選修課範例（各領域最多 3 門）也會被回答點名，一併收進來
        for dom in result.get("elective_by_domain", []):
            for name in dom.get("examples", []):
                if name and name not in course_pool:
                    course_pool[name] = {"code": "", "name": name, "dept": dept,
                                         "credits": 0, "type": "選修", "teacher": ""}
    elif tool_name in ("ppr_explore", "find_similar_courses", "explore_concept_neighborhood",
                       "get_course_knowledge_map", "get_depts_by_tech") and isinstance(result, str):
        existing = {(v.get("name"), v.get("dept")) for v in course_pool.values()}
        for c in _parse_courses_from_str(tool_name, result):
            name = c["name"]
            if not name or (name, c["dept"]) in existing:
                continue
            # 同名但不同系所的課（如多個系都開「演算法」）各自保留，標籤比對會依系所挑對應版本
            key = name if name not in course_pool else f"{name}（{c['dept']}）"
            course_pool[key] = c
            existing.add((name, c["dept"]))

    elif tool_name == "get_course_detail" and isinstance(result, dict):
        if result.get("ambiguous"):
            cname = result.get("name_zh", "")
            for c in result.get("candidates", []):
                key = c.get("course_code") or cname
                if key and key not in course_pool:
                    course_pool[key] = {
                        "code":    c.get("course_code", ""),
                        "name":    cname,
                        "dept":    c.get("dept", ""),
                        "credits": c.get("credits", 0),
                        "type":    "",
                        "teacher": c.get("teacher", ""),
                    }
        else:
            name = result.get("name_zh", "")
            code = result.get("course_code", "")
            key = code or name   # 精確查詢時用 course_code 作唯一鍵，避免同名不同系的課互相覆蓋
            if key and key not in course_pool:
                course_pool[key] = {
                    "code":    code,
                    "name":    name,
                    "dept":    result.get("dept", ""),
                    "credits": result.get("credits", 0),
                    "type":    "",
                    "teacher": result.get("teacher", ""),
                }

    elif tool_name == "get_teacher_info" and isinstance(result, dict):
        teacher = result.get("teacher_name", "")
        for c in result.get("courses", []):
            name = c.get("name", "")
            if not name:
                continue
            # 同名但不同課號/學分的課（如不同學分版本）各自保留
            course_id = c.get("id", "")
            credits   = c.get("credits") or 0
            key = f"{name}|{course_id or credits}"
            if key not in course_pool:
                course_pool[key] = {
                    "code":    course_id,
                    "name":    name,
                    "dept":    "",
                    "credits": credits,
                    "type":    c.get("relation", ""),
                    "teacher": teacher,
                }


@traceable(name="ncu_rag_tools", run_type="llm")
def generate_with_tools(
    question: str,
    history: Optional[list[dict]] = None,
    context_hint: str = "",
    max_rounds: int = 4,
) -> dict:
    """
    ReAct Tool-Use 模式：LLM 自行決定工具呼叫順序，支援並行執行。

    回傳：
      {"answer": str, "tools_used": list[str], "sources": list[dict],
       "course_cards": list[dict], "course_pool_count": int, "has_large_result": bool,
       "model": str, "input_tokens": int, "output_tokens": int}
    """
    from app.services.tools import TOOLS, execute_tool

    client = _get_client()
    deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o")

    system = SYSTEM_PROMPT
    if context_hint:
        system += f"\n\n## 學生背景資訊\n{context_hint}"
    if history:
        system += (
            "\n\n⚠️ 多輪對話提醒：歷史訊息中的助理回答皆為上輪工具查詢後生成的摘要文字，"
            "不代表完整資料。本輪若涉及課程/系所/學程/教師/畢業規定等具體查詢，"
            "**仍必須呼叫對應工具取得最新資料**，不得只參照歷史對話的文字內容直接回答。"
        )

    messages: list[dict] = list(history or [])
    messages.append({"role": "user", "content": question})

    tools_used: list[str] = []
    sources: list[dict] = []
    course_pool: dict[str, dict] = {}
    has_large_result = False
    total_input = total_output = 0

    for _ in range(max_rounds):
        response = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "system", "content": system}] + messages,
            tools=TOOLS,
            tool_choice="auto",
            **_build_completion_params(max_completion_tokens=MAX_TOKENS)
        )
        total_input  += response.usage.prompt_tokens
        total_output += response.usage.completion_tokens
        msg = response.choices[0].message

        if not msg.tool_calls:
            answer = _collapse_repeated_answer(msg.content or "")
            _enrich_course_cards(list(course_pool.values()))
            course_cards, answer = _extract_courses_from_tags(answer, course_pool)
            return {
                "answer":            answer,
                "tools_used":        tools_used,
                "sources":           sources,
                "course_cards":      course_cards,
                "course_pool":       list(course_pool.values()),
                "course_pool_count": len(course_pool),
                "has_large_result":  has_large_result,
                "model":             deployment,
                "input_tokens":      total_input,
                "output_tokens":     total_output,
            }

        # 並行執行所有工具呼叫
        with ThreadPoolExecutor() as pool:
            futures = {
                tc.id: pool.submit(execute_tool, tc.function.name,
                                   json.loads(tc.function.arguments))
                for tc in msg.tool_calls
            }
            results = {tid: f.result() for tid, f in futures.items()}

        # 收集課程資料 + 來源
        for tc in msg.tool_calls:
            tool_name = tc.function.name
            result = results.get(tc.id)
            tools_used.append(tool_name)

            _collect_course_pool(tool_name, result, course_pool)

            if tool_name == "search_courses" and isinstance(result, list):
                for item in result[:5]:
                    if item.get("name_zh"):
                        sources.append({
                            "name": item["name_zh"],
                            "dept": item.get("dept", ""),
                            "type": item.get("type", ""),
                        })

            if tool_name in ("get_dept_courses", "get_program_courses") and isinstance(result, dict):
                if len(result.get("courses", [])) > 20:
                    has_large_result = True

        # 把 assistant 訊息（含 tool_calls）加回對話
        messages.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name":      tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ],
        })

        # 加入每個工具的回傳結果
        for tc in msg.tool_calls:
            messages.append({
                "role":         "tool",
                "tool_call_id": tc.id,
                "content":      json.dumps(results[tc.id], ensure_ascii=False),
            })

    # 超過最大輪數：強制生成最終回答
    final = client.chat.completions.create(
        model=deployment,
        messages=[{"role": "system", "content": system}] + messages,
        **_build_completion_params(max_completion_tokens=MAX_TOKENS)
    )
    total_input  += final.usage.prompt_tokens
    total_output += final.usage.completion_tokens
    answer = _collapse_repeated_answer(final.choices[0].message.content or "")
    _enrich_course_cards(list(course_pool.values()))
    course_cards, answer = _extract_courses_from_tags(answer, course_pool)
    return {
        "answer":            answer,
        "tools_used":        tools_used,
        "sources":           sources,
        "course_cards":      course_cards,
        "course_pool":       list(course_pool.values()),
        "course_pool_count": len(course_pool),
        "has_large_result":  has_large_result,
        "model":             deployment,
        "input_tokens":      total_input,
        "output_tokens":     total_output,
    }


def stream_with_tools(
    question: str,
    history: Optional[list[dict]] = None,
    context_hint: str = "",
    max_rounds: int = 4,
):
    """
    Streaming ReAct Tool-Use：逐字 yield SSE JSON 字串。

    事件格式（每行 "data: {...}\\n\\n"）：
      {"type": "tool_start", "tool": "search_courses"}
      {"type": "tool_done",  "tool": "search_courses", "count": 8}
      {"type": "token",      "text": "根據..."}
      {"type": "done",       "session_id": "", "tools_used": [...],
       "course_cards": [...], "course_pool": [...],
       "course_pool_count": N, "has_large_result": bool,
       "model": "...", "input_tokens": N, "output_tokens": N}
      {"type": "error",      "message": "..."}
    """
    from app.services.tools import TOOLS, execute_tool

    client = _get_client()
    deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT", "gpt-4o")

    system = SYSTEM_PROMPT
    if context_hint:
        system += f"\n\n## 學生背景資訊\n{context_hint}"
    if history:
        system += (
            "\n\n⚠️ 多輪對話提醒：歷史訊息中的助理回答皆為上輪工具查詢後生成的摘要文字，"
            "不代表完整資料。本輪若涉及課程/系所/學程/教師/畢業規定等具體查詢，"
            "**仍必須呼叫對應工具取得最新資料**，不得只參照歷史對話的文字內容直接回答。"
        )

    messages: list[dict] = list(history or [])
    messages.append({"role": "user", "content": question})

    tools_used: list[str] = []
    course_pool: dict[str, dict] = {}
    has_large_result = False
    total_input = total_output = 0
    debug_trace_calls: list[dict] = []

    def _evt(data: dict) -> str:
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    try:
        for _ in range(max_rounds):
            response = client.chat.completions.create(
                model=deployment,
                messages=[{"role": "system", "content": system}] + messages,
                tools=TOOLS,
                tool_choice="auto",
                stream=True,
                stream_options={"include_usage": True},
                **_build_completion_params(max_completion_tokens=MAX_TOKENS)
            )

            # 累積 streaming 回應
            tc_buffer: dict[int, dict] = {}   # index → {id, name, arguments}
            content_parts: list[str] = []
            finish_reason = None

            for chunk in response:
                if not chunk.choices:
                    # 部分 provider 會在最後一個 chunk 只帶 usage
                    if hasattr(chunk, "usage") and chunk.usage:
                        total_input  += chunk.usage.prompt_tokens or 0
                        total_output += chunk.usage.completion_tokens or 0
                    continue

                choice = chunk.choices[0]
                finish_reason = choice.finish_reason or finish_reason
                delta = choice.delta

                if delta.tool_calls:
                    for tcd in delta.tool_calls:
                        i = tcd.index
                        if i not in tc_buffer:
                            tc_buffer[i] = {"id": "", "name": "", "arguments": ""}
                        if tcd.id:
                            tc_buffer[i]["id"] = tcd.id
                        if tcd.function:
                            if tcd.function.name:
                                tc_buffer[i]["name"] += tcd.function.name
                            if tcd.function.arguments:
                                tc_buffer[i]["arguments"] += tcd.function.arguments

                if delta.content:
                    content_parts.append(delta.content)
                    yield _evt({"type": "token", "text": delta.content})

                if hasattr(chunk, "usage") and chunk.usage:
                    total_input  += chunk.usage.prompt_tokens or 0
                    total_output += chunk.usage.completion_tokens or 0

            # 沒有工具呼叫 → 最終回答完成
            if not tc_buffer:
                final_answer = _collapse_repeated_answer("".join(content_parts))
                yield _evt({"type": "verify_start", "pool_size": len(course_pool)})
                _enrich_course_cards(list(course_pool.values()))
                course_cards, final_answer = _extract_courses_from_tags(final_answer, course_pool)
                card_names   = {c["name"] for c in course_cards}
                filtered_out = [
                    card["name"] for card in course_pool.values()
                    if card.get("name") and card["name"] not in card_names
                ]
                yield _evt({
                    "type":         "verify_done",
                    "method":       "tag",
                    "selected":     [c["name"] for c in course_cards],
                    "filtered_out": filtered_out,
                })
                yield _evt({
                    "type":              "done",
                    "final_answer":      final_answer,
                    "tools_used":        tools_used,
                    "course_cards":      course_cards,
                    "course_pool":       list(course_pool.values()),
                    "course_pool_count": len(course_pool),
                    "has_large_result":  has_large_result,
                    "model":             deployment,
                    "input_tokens":      total_input,
                    "output_tokens":     total_output,
                    "debug_trace":       {"toolCalls": debug_trace_calls},
                })
                return

            # 執行工具（並行）
            tc_list = [tc_buffer[i] for i in sorted(tc_buffer.keys())]
            for tc in tc_list:
                tools_used.append(tc["name"])
                try:
                    tc_args = json.loads(tc["arguments"] or "{}")
                except Exception:
                    tc_args = {}
                yield _evt({"type": "tool_start", "tool": tc["name"], "args": tc_args})

            with ThreadPoolExecutor() as pool:
                futures = {
                    tc["id"]: pool.submit(
                        execute_tool, tc["name"],
                        json.loads(tc["arguments"] or "{}")
                    )
                    for tc in tc_list
                }
                results = {tid: f.result() for tid, f in futures.items()}

            for tc in tc_list:
                result = results.get(tc["id"])
                _collect_course_pool(tc["name"], result, course_pool)
                count = None
                courses_found: list[str] = []
                scores: list[float] = []
                score_type: str | None = None

                if tc["name"] == "get_dept_overview" and isinstance(result, dict):
                    courses_found = [
                        c.get("name", "")
                        for c in (result.get("required_courses", []) + result.get("common_required_courses", []))
                    ]
                    count = len(courses_found)
                elif tc["name"] in ("get_dept_courses", "get_program_courses", "get_program_info") and isinstance(result, dict):
                    count = len(result.get("courses", []))
                    if count > 20:
                        has_large_result = True
                    courses_found = [
                        c.get("name") or c.get("id", "")
                        for c in result.get("courses", [])
                    ]
                elif tc["name"] == "search_courses" and isinstance(result, list):
                    count = len(result)
                    courses_found = [r.get("name_zh", "") for r in result if r.get("name_zh")]
                    if result and result[0].get("source") == "graph_tech":
                        scores = []
                        score_type = "graph_exact"
                    else:
                        scores = [r.get("distance", 0.0) for r in result if r.get("name_zh")]
                        score_type = "distance"
                elif tc["name"] in ("find_similar_courses", "get_course_knowledge_map") and isinstance(result, str):
                    import re as _re
                    for m in _re.finditer(r'-\s*(.+?)（[^）]+）\s*(?:\[共享(?:概念：|\ )(\d+)\ 個(?:概念)?\])?', result):
                        name = m.group(1).strip()
                        sc = int(m.group(2)) if m.group(2) else 0
                        if name and len(name) >= 2 and not name.startswith('['):
                            courses_found.append(name)
                            scores.append(float(sc))
                    count = len(courses_found)
                    score_type = "shared_concepts"
                elif tc["name"] == "ppr_explore" and isinstance(result, str):
                    import re as _re
                    for m in _re.finditer(r'\[課程\]\s*(.+?)（(.+?)）\s*\[PPR:\s*([\d.]+)\]', result):
                        courses_found.append(m.group(1).strip())
                        scores.append(float(m.group(3)))
                    count = len(courses_found)
                    score_type = "ppr"
                elif tc["name"] == "search_programs" and isinstance(result, list):
                    count = len(result)
                    courses_found = [r.get("program_name", "") for r in result if r.get("program_name")]
                    scores = [r.get("distance", 0.0) for r in result]
                    score_type = "distance"
                elif tc["name"] == "get_depts_by_tech" and isinstance(result, str):
                    import re as _re
                    in_courses = False
                    for line in result.splitlines():
                        if '相關課程' in line:
                            in_courses = True
                            continue
                        if not in_courses:
                            continue
                        m2 = _re.match(r'\s*-\s*(.+?)（(.+?)）', line)
                        if m2:
                            name = m2.group(1).strip()
                            if name and len(name) >= 2:
                                courses_found.append(name)
                    count = len(courses_found)

                debug_trace_calls.append({
                    "tool":         tc["name"],
                    "args":         json.loads(tc["arguments"] or "{}"),
                    "coursesFound": courses_found,
                    "count":        count,
                    "scores":       scores,
                    "scoreType":    score_type,
                })
                yield _evt({"type": "tool_done", "tool": tc["name"], "count": count,
                            "courses_found": courses_found, "scores": scores, "score_type": score_type})
                # 字串型工具（get_depts_by_tech / ppr / find_similar）回傳完整文字供測試腳本捕捉
                if isinstance(result, str) and result:
                    preview = result[:800] + ("…" if len(result) > 800 else "")
                    yield _evt({"type": "tool_result", "tool": tc["name"], "result": preview})

            # 重建 messages
            messages.append({
                "role":    "assistant",
                "content": "".join(content_parts) or None,
                "tool_calls": [
                    {"id": tc["id"], "type": "function",
                     "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                    for tc in tc_list
                ],
            })
            for tc in tc_list:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(results[tc["id"]], ensure_ascii=False),
                })

        # 超過最大輪數：強制串流最終回答
        final = client.chat.completions.create(
            model=deployment,
            messages=[{"role": "system", "content": system}] + messages,
            stream=True,
            stream_options={"include_usage": True},
            **_build_completion_params(max_completion_tokens=MAX_TOKENS)
        )
        content_parts = []
        for chunk in final:
            if chunk.choices and chunk.choices[0].delta.content:
                text = chunk.choices[0].delta.content
                content_parts.append(text)
                yield _evt({"type": "token", "text": text})
            if hasattr(chunk, "usage") and chunk.usage:
                total_input  += chunk.usage.prompt_tokens or 0
                total_output += chunk.usage.completion_tokens or 0

        final_answer = _collapse_repeated_answer("".join(content_parts))
        yield _evt({"type": "verify_start", "pool_size": len(course_pool)})
        _enrich_course_cards(list(course_pool.values()))
        course_cards, final_answer = _extract_courses_from_tags(final_answer, course_pool)
        card_names   = {c["name"] for c in course_cards}
        filtered_out = [
            card["name"] for card in course_pool.values()
            if card.get("name") and card["name"] not in card_names
        ]
        yield _evt({
            "type":         "verify_done",
            "method":       "tag",
            "selected":     [c["name"] for c in course_cards],
            "filtered_out": filtered_out,
        })
        yield _evt({
            "type":              "done",
            "final_answer":      final_answer,
            "tools_used":        tools_used,
            "course_cards":      course_cards,
            "course_pool":       list(course_pool.values()),
            "course_pool_count": len(course_pool),
            "has_large_result":  has_large_result,
            "model":             deployment,
            "input_tokens":      total_input,
            "output_tokens":     total_output,
            "debug_trace":       {"toolCalls": debug_trace_calls},
        })

    except Exception as exc:
        yield _evt({"type": "error", "message": str(exc)})
