"""資料更新管線的步驟登錄表。

每個步驟宣告：
  - 要跑哪些既有腳本（commands）
  - 允許改動哪些檔案（outputs；沙盒裡改到其他檔案不會被套用）
  - 需要哪些輸入（requires；缺了就跳過並說明原因）
  - 權限標籤（tags；會花錢、會寫外部服務、會刪資料的步驟要加旗標才會跑）

新增步驟時只要在 STEPS 加一筆；危險、不該被管線執行的腳本列在 BLOCKED。
"""

from __future__ import annotations

from dataclasses import dataclass

# ── 權限標籤 ────────────────────────────────────────────────────────────────
NETWORK = "network"          # 連學校網站爬資料
LOCAL_LLM = "local_llm"      # 需要本機 vLLM（http://localhost:8000/v1），不花錢但要 GPU
PAID = "paid"                # 呼叫付費 API（Azure OpenAI chat / embedding）
EXTERNAL = "external"        # 讀寫外部服務（Qdrant、Cloudinary、PostgreSQL）
DESTRUCTIVE = "destructive"  # 會刪除外部服務裡的資料

FLAG_FOR_TAG = {
    NETWORK: "--fetch",
    LOCAL_LLM: "--with-local-llm",
    PAID: "--allow-paid",
    EXTERNAL: "--allow-external",
    DESTRUCTIVE: "--allow-destructive",
}

# dry-run 時這些標籤的步驟只列出計畫、不執行（避免連網、花錢、碰外部服務）
LIVE_TAGS = frozenset({NETWORK, PAID, EXTERNAL})

# ── 階段 ───────────────────────────────────────────────────────────────────
FETCH = "fetch"      # 直接寫 data/raw（原始資料快取，可續爬）
BUILD = "build"      # 在沙盒產生 data/processed，驗證通過才套用
CHECK = "check"      # 在沙盒做唯讀檢查
PUBLISH = "publish"  # 套用後才跑，寫外部服務（Qdrant / Cloudinary）

STAGES = (FETCH, BUILD, CHECK, PUBLISH)

RUN_DIR_TOKEN = "{run_dir}"


@dataclass(frozen=True)
class Step:
    name: str
    stage: str
    title: str
    commands: tuple[tuple[str, ...], ...] = ()
    outputs: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    tags: frozenset[str] = frozenset()
    default: bool = True
    explicit_only: bool = False
    runner: str = "commands"
    cost: str = "免費"
    note: str = ""


def _s(*parts: str) -> tuple[str, ...]:
    return tuple(parts)


STEPS: tuple[Step, ...] = (
    # ── fetch：連學校網站，寫 data/raw ─────────────────────────────────────
    Step(
        name="fetch_courses",
        stage=FETCH,
        title="爬取各學期課程（cis.ncu.edu.tw，Selenium + Chrome headless）",
        runner="fetch_courses",
        outputs=("data/raw/courses", "data/raw/graduate_courses"),
        tags=frozenset({NETWORK}),
        cost="免費；每門課開 2 個彈窗，每次點擊間隔 2～3 秒，全校兩學期約需數小時",
        note="先爬到 logs/data_update/incoming/<學期>（中斷可續爬），筆數驗證通過才換進 data/raw；"
             "碩博士系所會自動分到 data/raw/graduate_courses/",
    ),
    Step(
        name="fetch_course_content",
        stage=FETCH,
        title="補爬課綱空白的課程（課程目標與授課內容都少於 10 字）",
        commands=(_s("scripts/scrapers/scrape_content_by_url.py", "--headless"),),
        outputs=("data/raw/courses", "data/raw/graduate_courses", "data/raw/scraped_missing"),
        requires=("data/raw/courses/{term}",),
        tags=frozenset({NETWORK}),
        cost="免費；每頁間隔約 1.2～1.5 秒，每門課再等 0.8 秒",
    ),
    Step(
        name="fetch_requirement_pdfs",
        stage=FETCH,
        title="下載應修科目表 PDF（已存在的跳過）",
        commands=(_s("scripts/scrapers/scrape_requirements.py"),),
        outputs=("data/raw/應修科目表",),
        tags=frozenset({NETWORK}),
        cost="免費；每個檔案間隔 0.5 秒",
        note="網址清單與檔名（_114）寫死在腳本裡，換學年要手動更新；目前只供人工審核與驗證工具使用",
    ),
    # ── build：沙盒裡產生 data/processed ───────────────────────────────────
    Step(
        name="project_document_ids",
        stage=BUILD,
        title="從 PDF 資料庫補 projects.json 的 documentId（唯讀查詢 PostgreSQL）",
        commands=(_s("scripts/populate_document_ids.py"),),
        outputs=("data/processed/projects.json",),
        requires=("data/processed/projects.json",),
        tags=frozenset({EXTERNAL}),
        default=False,
        note="需要 .env 的 DATABASE_URL；只讀資料庫，只寫本機 projects.json",
    ),
    Step(
        name="nlp_local_llm",
        stage=BUILD,
        title="NLP 標註（技術節點、領域、通識主題、白話說明、別名合併）",
        commands=(
            _s("scripts/nlp/normalize_teacher_specialties.py"),
            _s("scripts/nlp/run_agent1_tech.py"),
            _s("scripts/nlp/run_agent2_domain.py"),
            _s("scripts/nlp/run_agent3_topics.py"),
            _s("scripts/nlp/run_agent4_simplify.py"),
            _s("scripts/nlp/postprocess_simplified.py"),
            _s("scripts/nlp/normalize_aliases.py", "--apply"),
        ),
        outputs=("data/processed/nlp",),
        requires=("data/raw/courses/{term}", "data/raw/114_ulistteacher.csv"),
        tags=frozenset({LOCAL_LLM}),
        cost="免費（本機 GPU）；約 3,000＋3,100＋120＋2,200 次本機 LLM 呼叫，已處理的課程會跳過",
        note="需先啟動本機 vLLM；Agent 1～4 讀原始課程的學期目前寫死 114。"
             "normalize_teacher_specialties 會蓋掉別名合併結果，所以最後一定接 normalize_aliases --apply",
    ),
    Step(
        name="courses",
        stage=BUILD,
        title="課程去重與修課資格（courses_deduped、course_eligibility、dept_college_map）",
        commands=(
            _s("scripts/extraction/course_programs/deduplicate_courses.py"),
            _s("scripts/extraction/course_programs/parse_distribution_conditions.py"),
            _s("scripts/extraction/course_programs/deduplicate_courses.py"),
        ),
        outputs=(
            "data/processed/courses_deduped",
            "data/processed/course_eligibility.json",
            "data/processed/dept_college_map.json",
        ),
        requires=("data/raw/courses/{term}",),
        note="去重會讀 dept_college_map 補學院，而該檔由 parse_distribution_conditions 產生，所以去重跑兩次",
    ),
    Step(
        name="program_descriptions",
        stage=BUILD,
        title="學分學程說明（從學分學程 PDF 抽取）",
        commands=(_s("scripts/extraction/course_programs/extract_program_descriptions.py"),),
        outputs=("data/processed/program_descriptions.json",),
        requires=("data/raw/學分學程",),
        note="學分學程 PDF 沒有下載腳本，需手動放到 data/raw/學分學程/<學院>/",
    ),
    Step(
        name="curriculum_merge_schedule",
        stage=BUILD,
        title="把 schedule_draft 的修課時間併回 curriculum_requirements_114.json",
        commands=(_s("scripts/data/merge_schedule_to_curriculum.py"),),
        outputs=("data/processed/curriculum_requirements_114.json",),
        requires=("data/processed/schedule_draft",),
        default=False,
        explicit_only=True,
        note="會用 schedule_draft 整個取代同 id 的節點；直接改在 curriculum 檔、沒同步回 schedule_draft 的修正會被蓋掉，"
             "請先用 dry-run 看變更摘要",
    ),
    Step(
        name="course_index",
        stage=BUILD,
        title="課程索引 course_index.json（後端課程卡片、聊天用）",
        commands=(_s("scripts/rag/build_course_index.py"),),
        outputs=("data/processed/course_index.json",),
        requires=("data/processed/courses_deduped/undergrad.json",),
    ),
    Step(
        name="projects_summaries",
        stage=BUILD,
        title="研究計畫摘要與量表題目（由 step2/step3 快照重建，seed 固定）",
        commands=(_s("scripts/data/import_step2_step3_summaries.py"),),
        outputs=("data/processed/projects.json", "data/processed/assessment_questions.json"),
        requires=("data/raw/step2_step3_summaries.jsonl", "data/processed/projects.json"),
    ),
    Step(
        name="graph",
        stage=BUILD,
        title="知識圖譜完整重建（knowledge_graph.json / .pkl / .gpickle）",
        commands=(_s("scripts/graph/build_graph.py"),),
        outputs=(
            "data/processed/graph/knowledge_graph.json",
            "data/processed/graph/knowledge_graph.pkl",
            "data/processed/graph/knowledge_graph.gpickle",
            "data/processed/graph/knowledge_graph_stats.json",
        ),
        requires=("data/raw/courses/{term}", "data/raw/114_ulistteacher.csv"),
        note="一律完整重建（--enrich-only 不會移除舊節點）；沒有原始課程時會跳過，避免產生殘缺的圖",
    ),
    Step(
        name="communities",
        stage=BUILD,
        title="圖譜社群偵測與命名（communities.json）",
        commands=(
            _s("scripts/graph/compute_communities.py"),
            _s("scripts/graph/label_communities.py"),
        ),
        outputs=("data/processed/graph/communities.json",),
        requires=("data/processed/graph/knowledge_graph.json",),
        tags=frozenset({PAID}),
        cost="Azure OpenAI chat（預設 gpt-4o-mini），每 6 個社群 1 次，目前約 8 次",
        note="compute_communities 會把所有 label 清空，所以一定和 label_communities 綁在一起跑",
    ),
    Step(
        name="glossary_frontend",
        stage=BUILD,
        title="匯出前端名詞詞庫 frontend/src/data/glossary.json",
        commands=(_s("scripts/nlp/export_glossary_frontend.py"),),
        outputs=("frontend/src/data/glossary.json",),
        requires=("data/processed/nlp/concept_glossary.json",),
        default=False,
        explicit_only=True,
        note="concept_glossary.json 只有重建詞庫（付費、需人工審核）時才會變，所以預設不跑",
    ),
    # ── check：沙盒裡的唯讀檢查 ────────────────────────────────────────────
    Step(
        name="assessment_coverage",
        stage=CHECK,
        title="檢查量表題目是否涵蓋所有系所",
        commands=(_s("scripts/check_assessment_dept_coverage.py"),),
        requires=("data/processed/assessment_questions.json", "data/raw/admission/ncu_caac.csv"),
    ),
    # ── publish：套用後寫外部服務 ──────────────────────────────────────────
    Step(
        name="qdrant_payloads",
        stage=PUBLISH,
        title="更新 Qdrant 課程 payload（NLP 欄位、修課時間）",
        commands=(
            _s("scripts/rag/update_course_nlp_payload.py", "--apply"),
            _s("scripts/rag/update_schedule_payload.py"),
        ),
        tags=frozenset({EXTERNAL}),
        note="只改 payload、逐點比對，不重算向量；寫入 .env 的 QDRANT_URL",
    ),
    Step(
        name="qdrant_graph_nodes",
        stage=PUBLISH,
        title="差異同步 Qdrant ncu_graph_nodes，再重寫 Community 點",
        commands=(
            _s("scripts/rag/sync_graph_nodes.py", "--apply", "--backup", f"{RUN_DIR_TOKEN}/graph_nodes_backup.json"),
            _s("scripts/rag/add_communities_to_qdrant.py"),
        ),
        tags=frozenset({EXTERNAL, PAID, DESTRUCTIVE}),
        cost="只 embed 新增節點的名稱（短字串）與社群（目前 48 個）",
        note="會刪除圖譜已不存在的節點（Community 點不刪）；執行前自動把受影響的點備份到本次的 logs 目錄",
    ),
    Step(
        name="qdrant_course_vectors_rebuild",
        stage=PUBLISH,
        title="重建課程／教師／學分學程向量（build_vector_index --reset）",
        commands=(
            _s("scripts/rag/build_vector_index.py", "--reset"),
            _s("scripts/rag/update_schedule_payload.py"),
        ),
        tags=frozenset({EXTERNAL, PAID, DESTRUCTIVE}),
        default=False,
        explicit_only=True,
        cost="約 4,500 筆課程長文＋1,000 筆教師＋數十筆學程的 embedding（text-embedding-3-large）",
        note="新學期課程要進語意搜尋時才需要；會刪掉 ncu_courses_ug/grad、ncu_teachers、ncu_credit_programs 重建",
    ),
    Step(
        name="cloudinary_pdfs",
        stage=PUBLISH,
        title="上傳研究計畫 PDF 到 Cloudinary（已存在的跳過）",
        commands=(_s("scripts/storage/upload_pdfs_to_cloudinary.py"),),
        requires=("data/raw/projects/104-114",),
        tags=frozenset({EXTERNAL}),
        default=False,
        explicit_only=True,
        note="每個檔案會呼叫一次 Admin API 檢查是否已存在，會用到 API 配額",
    ),
)

# 盤點時確認「不該被管線執行」的腳本或模式。--only / --include 點名這些會直接報錯。
BLOCKED: dict[str, str] = {
    "extract_pdf_metadata": "scripts/extraction/projects_pdf/1_extract_pdf_metadata.py 會整檔重寫 projects.json、"
                            "依目錄順序重新編號，並清掉 documentId 與摘要欄位",
    "summarize_with_azure": "scripts/extraction/projects_pdf/3b_summarize_with_azure.py 依 source_id 續跑，"
                            "現行 assessment_questions.json 沒有 source_id，重跑會整批重複附加並呼叫付費 API",
    "generate_questions": "scripts/extraction/projects_pdf/2_generate_questions.py 產生罐頭假題目，"
                          "已由 projects_summaries 步驟取代",
    "process_course_domain": "scripts/extraction/course_programs/process_course_domain.py 是修第一版爬蟲格式的一次性腳本，"
                             "對 v2 資料會把核心能力清成空陣列",
    "vector_payload_only": "build_vector_index.py --payload-only 以課號覆寫 payload，同課號不同班會互相蓋掉，"
                           "並清掉 when_* 欄位；請改用 qdrant_payloads 步驟",
    "update_domain_tags_payload": "scripts/rag/update_domain_tags_payload.py 每個課號只更新一個點，"
                                  "已由 qdrant_payloads（update_course_nlp_payload）取代",
    "remove_orphaned_field_nodes": "scripts/rag/remove_orphaned_field_nodes.py 預設直接刪點，功能已由 qdrant_graph_nodes 涵蓋",
    "graph_enrich_only": "build_graph.py --enrich-only 只新增不刪除，舊名稱節點會殘留；管線一律完整重建",
    "migrate_qdrant_to_cloud": "scripts/rag/migrate_qdrant_to_cloud.py 不會複製 bm25 sparse 設定與 payload index",
}


def step_by_name() -> dict[str, Step]:
    return {s.name: s for s in STEPS}
