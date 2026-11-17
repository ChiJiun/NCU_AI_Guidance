# 一鍵資料更新：`python -m scripts.update_data`

把原本分散、手動執行的資料處理腳本串成一個入口。在 repo 根目錄執行：

```bash
python -m scripts.update_data            # dry-run：在暫存沙盒跑完免費步驟，只印變更摘要，不寫入
python -m scripts.update_data --apply    # 驗證通過後套用到 data/processed
python -m scripts.update_data --list     # 列出所有步驟、權限需求、成本與被擋下的腳本
```

需要的 Python 套件與後端相同（`pip install -r backend/requirements.txt`）。爬蟲另外需要
`selenium` 與 Chrome；PDF 抽取需要 `pdfplumber`；圖譜需要 `networkx`（`python-igraph`、`leidenalg` 選用）。

## 定期更新的建議流程

每學期開學前後，或學校課程資料有更新時：

1. **先 dry-run 看會改什麼**（不連網、不花錢、不寫入）：
   ```bash
   python -m scripts.update_data --fetch --terms 114_1,114_2
   ```
   dry-run 加 `--fetch` 只會列出爬取計畫，不會真的連網。
2. **爬資料並套用免費步驟**：
   ```bash
   python -m scripts.update_data --fetch --apply --terms 114_1,114_2
   ```
   爬課程要數小時（每門課開 2 個彈窗、每次點擊間隔 2～3 秒）。中斷後重跑同一個指令會從暫存目錄續爬。
   任何系所翻頁或存檔失敗，爬蟲都會以非 0 結束、該系所不存檔，整個 fetch 視為失敗、不動 `data/raw`；重跑會補爬失敗的系所。
   補課綱（`fetch_course_content`）的斷點放在各學期目錄的 `.content_fix_done.txt`，重新爬課程換掉學期目錄時一起清空；載入或解析失敗的課程不記斷點，下次重試。
   頁面能載入但找不到課號／流水號／課程名稱（例如「系統忙碌」錯誤頁）也算失敗。連續 10 筆出錯（通常是瀏覽器掛掉）或錯誤率超過 20%，補課綱會以非 0 結束，管線停在 fetch、不往下 build，避免把課綱空白的課程套用進 `data/processed`。這時 `data/raw` 已經是新爬的課程，修好後用 `--fetch --apply --only fetch_course_content` 續補，再跑一次完整的 `--apply`。
   新課程換進 `data/raw` 時，學期目錄會留下 `.content_fix_pending` 標記，補課綱成功跑完才會刪除。標記還在時，之後任何一次 `--apply`（即使沒加 `--fetch`）都會在 build 前停下（報告裡的 `content_fix_check`），不會把課綱空白的課程帶進 `data/processed`。每次都卡在同一批課時，見下面的「補課綱一直卡住」。
3. **看報告**：`logs/data_update/<時間>/summary.md` 會列出每個檔案的筆數變化、新增／移除的項目。
4. **重啟後端**：後端多數 JSON 有快取（`lru_cache`），重啟後才會讀到新資料。
5. **需要時再更新外部服務**（會花錢或寫入正式環境，請確認後再跑）：
   ```bash
   # 只改 Qdrant 課程 payload（NLP 欄位、修課時間），不花錢
   python -m scripts.update_data --apply --allow-external --only qdrant_payloads
   # 圖譜重建後同步 ncu_graph_nodes（會刪點、會 embed 新節點）
   python -m scripts.update_data --apply --allow-external --allow-paid --allow-destructive --only qdrant_graph_nodes
   ```
6. 確認 `git diff data/` 沒問題後再 commit。

新學年度（例如 115）只要改 `--terms 115_1,115_2`；課程去重、圖譜、課綱補爬都會跟著換學期。

> **只跑一個學期時要加 `--allow-shrink`。** `--terms` 決定 `courses_deduped` 等輸出要納入哪些學期，
> 例如 `--terms 115_1` 只會用 115_1 的課程重建，筆數通常比現有（兩個學期合併）少很多，
> 會被「筆數少超過 10%」的驗證擋下。確認這是預期的再加 `--allow-shrink`（或調高 `--max-shrink`），
> 並看報告裡的筆數變化。
>
> **NLP 標註（`nlp_local_llm`）的學期不會跟著 `--terms` 換。** 管線用 `--terms` 檢查這個步驟的輸入是否存在，
> 但 `scripts/nlp/run_agent*.py` 讀原始課程的學期寫死 114；用新學期跑時，NLP 欄位仍是 114 課程的標註，
> 要先改 agent 腳本才會標到新學期的課。

## 補課綱一直卡住

補課綱遇到錯誤的課程不會記進斷點，下次會重試，而且這些課仍排在最前面。如果某些課的課綱頁每次都是錯誤頁
（例如學校網站對那幾門課一直回「系統忙碌」，或頁面已下架），每次續補都會在同樣的地方連續出錯 10 筆而中止，
`--only fetch_course_content` 重跑幾次都一樣。管線不能傳參數給補課綱腳本，可以這樣處理：

1. **先確認是不是永久性的錯誤**：看 `logs/data_update/<時間>/steps/fetch_course_content.log` 裡出錯的課，
   用瀏覽器打開課程 JSON 裡的 `課程綱要_連結`。如果是網站暫時故障，等一段時間再續補即可。
2. **確定是永久錯誤、要把其餘課程補完**：直接執行補課綱腳本，放寬錯誤上限。學期要用 `NCU_DATA_TERMS` 指定，
   和管線的 `--terms` 相同：
   ```bash
   NCU_DATA_TERMS=114_1,114_2 python scripts/scrapers/scrape_content_by_url.py --headless --max-consecutive-errors 0 --max-error-rate 1
   ```
   `--max-consecutive-errors 0` 代表不因為連續出錯而中止，`--max-error-rate 1` 代表不因為錯誤率而失敗。
   跑完結束碼是 0，會刪除 `.content_fix_pending`；出錯的那幾門課的課綱仍是空白。之後再照常跑 `--apply`。
   Windows PowerShell 要先 `$env:NCU_DATA_TERMS = "114_1,114_2"`，再執行同一行指令，但不要加前面的 `NCU_DATA_TERMS=`。
3. **不想再補、接受目前的課綱**：在 `--apply` 加上 `--allow-incomplete-content`，略過這個檢查。標記會留著，
   之後每次 build 都要加這個旗標，直到補課綱成功跑完為止。

不建議用 `--skip fetch_course_content` 加 `--allow-incomplete-content` 當成常態：課綱空白的課程在課程卡片與聊天裡會缺少課程目標與授課內容。

## 旗標

| 旗標 | 允許什麼 |
|---|---|
| （無） | dry-run：只在沙盒跑免費步驟，印出變更摘要 |
| `--apply` | 驗證通過後套用到正式目錄；並執行已用其他旗標允許的步驟 |
| `--fetch` | 連學校網站爬資料（課程、課綱、應修科目表 PDF） |
| `--with-local-llm` | 跑需要本機 vLLM（`http://localhost:8000/v1`）的 NLP 標註 |
| `--allow-paid` | 呼叫付費 API（Azure OpenAI chat / embedding） |
| `--allow-external` | 讀寫外部服務（Qdrant、Cloudinary、PostgreSQL） |
| `--allow-destructive` | 刪除外部服務裡的資料（Qdrant 的點或 collection） |
| `--only a,b` / `--include a,b` / `--skip a,b` | 只跑／加跑／跳過指定步驟 |
| `--terms 114_1,114_2` | 學期清單，舊到新（後者覆蓋前者） |
| `--max-shrink 0.1` / `--allow-shrink` | 輸出筆數比現有少超過 10% 視為失敗；確定資料本來就變少時放寬（只跑單一學期時通常需要） |
| `--fresh-fetch` | 不續爬，把上次沒爬完的暫存目錄移開後從頭爬 |
| `--allow-incomplete-content` | 補課綱沒有成功跑完（學期目錄留著 `.content_fix_pending`）時，仍用目前的原始課程 build |
| `--keep-sandbox` | 保留暫存沙盒（預設成功就刪，失敗才保留） |

會連網、花錢或寫外部服務的步驟，即使加了旗標，**沒有 `--apply` 也只會列出計畫**。

## 步驟

依執行順序（完整說明用 `--list`）：

| 階段 | 步驟 | 預設 | 需要旗標 | 產出 |
|---|---|---|---|---|
| fetch | `fetch_courses` | ✓ | `--fetch` | `data/raw/courses/<學期>`、`data/raw/graduate_courses/<學期>` |
| fetch | `fetch_course_content` | ✓ | `--fetch` | 補齊原始課程裡空白的課綱 |
| fetch | `fetch_requirement_pdfs` | ✓ | `--fetch` | `data/raw/應修科目表/` |
| build | `project_document_ids` | 點名 | `--allow-external` | `projects.json` 的 `documentId`（唯讀查 PostgreSQL） |
| build | `nlp_local_llm` | ✓ | `--with-local-llm` | `data/processed/nlp/*` |
| build | `courses` | ✓ | — | `courses_deduped/*`、`course_eligibility.json`、`dept_college_map.json` |
| build | `program_descriptions` | ✓ | — | `program_descriptions.json` |
| build | `curriculum_merge_schedule` | 點名 | — | `curriculum_requirements_114.json` |
| build | `course_index` | ✓ | — | `course_index.json` |
| build | `projects_summaries` | ✓ | — | `projects.json`、`assessment_questions.json` |
| build | `graph` | ✓ | — | `graph/knowledge_graph.{json,pkl,gpickle}`、`knowledge_graph_stats.json` |
| build | `communities` | ✓ | `--allow-paid` | `graph/communities.json` |
| build | `glossary_frontend` | 點名 | — | `frontend/src/data/glossary.json` |
| check | `assessment_coverage` | ✓ | — | 只檢查量表題目涵蓋的系所 |
| publish | `qdrant_payloads` | ✓ | `--allow-external` | Qdrant 課程 payload |
| publish | `qdrant_graph_nodes` | ✓ | `--allow-external --allow-paid --allow-destructive` | Qdrant `ncu_graph_nodes` |
| publish | `qdrant_course_vectors_rebuild` | 點名 | `--allow-external --allow-paid --allow-destructive` | 重建四個課程類 collection |
| publish | `cloudinary_pdfs` | 點名 | `--allow-external` | Cloudinary 上的研究計畫 PDF |

「點名」代表要用 `--only` 或 `--include` 指定才會跑。

### 成本

| 步驟 | 花費 |
|---|---|
| `communities` | Azure OpenAI chat（gpt-4o-mini），約 8 次呼叫 |
| `qdrant_graph_nodes` | 只 embed 新增節點的名稱（短字串）與 48 個社群 |
| `qdrant_course_vectors_rebuild` | 約 4,500 筆課程長文、1,000 筆教師、數十筆學程的 embedding（text-embedding-3-large） |
| `nlp_local_llm` | 本機 GPU，不花 API 費用；已處理的課程會跳過 |
| 其他 | 免費 |

## 安全機制

- **套用前整體再驗證**：全部 build 步驟跑完後，對所有要套用的檔案用最終內容再驗證一次（後面的步驟可能改到前面步驟的輸出）；套用時任何檔案替換失敗都會還原、寫報告並以非 0 結束。
- **沙盒**：build／check 步驟在暫存目錄的 repo 副本裡跑（不複製 `.env`、`data/raw/projects`、`qdrant*` 等）。
  正式的 `data/processed` 在全部步驟與驗證通過前完全不會被動到。
- **驗證**：每個輸出檔要能解析、不能是空的、筆數不能比現有少超過 `--max-shrink`；課程檔不能有重複的
  `課號-班別`；圖譜裡有原始資料的課程節點數不能大幅下降（原始課程缺漏時會擋下）；`communities.json` 空白的
  `label` 不能比現有多（`label_communities` 缺 Azure 憑證或 API 失敗時也會以非 0 結束）。
- **補課綱未完成就不 build**：新課程換進 `data/raw` 後，學期目錄留著 `.content_fix_pending` 直到補課綱成功跑完；
  標記存在時，讀原始課程的 build 步驟一律擋下（跨次執行也有效），除非加 `--allow-incomplete-content`。
- **報告的結果列**：有步驟失敗時，若 `data/raw` 已被 fetch 步驟改寫、build 輸出已套用、或外部服務已寫入，
  結果列會逐項寫出，不會只寫「正式資料未變更」。
- **只套用宣告過的輸出**：沙盒裡被改到、但不在步驟宣告輸出內的檔案會列在報告的「未宣告的變動」，不會套用。
- **備份與原子替換**：套用前把原檔備份到 `logs/data_update/<時間>/backup/`，逐檔寫暫存檔再 `os.replace`；
  任何一檔失敗就還原已替換的檔案。管線不會刪除正式目錄的檔案。
- **憑證隔離**：免費步驟執行時會移除 Azure、Qdrant、Cloudinary、資料庫等環境變數，不可能意外花錢或寫入正式服務；
  只有加了對應旗標的步驟才會讀 `.env`。輸出與 log 中看起來像金鑰、token、密碼的值會被遮掉。
- **爬蟲**：先爬到 `logs/data_update/incoming/<學期>/`，課程數比現有少超過 `--max-shrink` 就不換進 `data/raw`；
  換進時舊目錄移到本次的 backup，碩博士系所自動分到 `graduate_courses`（依現有資料的系所清單與名稱判斷）。
- **外部服務在最後**：publish 步驟只在本機資料套用成功後才跑；前面任何步驟失敗都不會寫外部服務。

## 被擋下的腳本

下列腳本或模式在盤點時確認會破壞現有資料，管線不會執行（`--only`／`--include` 點名會直接報錯），
腳本本身也加了防呆：

| 名稱 | 原因 |
|---|---|
| `1_extract_pdf_metadata.py` | 整檔重寫 `projects.json`、重新編號，清掉 `documentId` 與摘要 |
| `3b_summarize_with_azure.py` | 現行 `assessment_questions.json` 沒有 `source_id`，重跑會整批重複附加並花錢 |
| `2_generate_questions.py` | 產生罐頭假題目，已由 `projects_summaries` 取代 |
| `process_course_domain.py` | 對 v2 爬蟲資料會把核心能力清成空陣列 |
| `build_vector_index.py --payload-only` | 同課號不同班互相覆蓋 payload，並清掉 `when_*` 欄位（需加 `--force-payload-only` 才會執行） |
| `update_domain_tags_payload.py` | 每個課號只更新一個點，已由 `qdrant_payloads` 取代 |
| `remove_orphaned_field_nodes.py` | 預設直接刪點，已由 `qdrant_graph_nodes` 涵蓋 |
| `build_graph.py --enrich-only` | 只新增不刪除，舊名稱節點會殘留 |
| `migrate_qdrant_to_cloud.py` | 不會複製 bm25 sparse 設定與 payload index |

`sync_graph_nodes.py` 原本每次 `--apply` 都會刪掉 Community 點，已修正為只保留 `communities.json` 目前還有的社群（重算社群後消失的舊社群點會刪除；讀不到 `communities.json` 時全部保留）。

## 仍需人工處理的部分

管線沒辦法自動化、或刻意不自動化的步驟：

- **學分學程 PDF**（`data/raw/學分學程/`）：沒有下載來源腳本，需手動下載。
- **`credit_programs/*.json`、`dept_aliases.json`、`requirements_notes.json`、`schedule_draft/` 的初版**：
  當初是人工或用 Claude 輔助解析，沒有產生腳本；管線只讀不寫。
- **修課時間人工審核**：`scripts/extraction/requirements/schedule_review_html.py` 產生審核頁，
  匯出後用 `update_when_for_verified.py --source-dir <匯出資料夾>` 回填，再用
  `--only curriculum_merge_schedule` 併回 `curriculum_requirements_114.json`。
- **名詞詞庫**（`scripts/nlp/build_glossary.py`）：要用 `claude -p` 與 Azure 審核，並人工維護
  `glossary_manual.json`；完成後用 `--only glossary_frontend` 匯出前端檔。
- **step2/step3 摘要快照**（`data/raw/step2_step3_summaries.jsonl`）：在其他環境產生後放進來，再跑 `projects_summaries`。
- **應修科目表網址**：`scripts/scrapers/scrape_requirements.py` 的網址清單與 `_114` 檔名寫死，換學年要手動更新。
- **NLP agent 的學期**：`scripts/nlp/run_agent*.py` 讀原始課程的學期仍寫死 114；管線對 `nlp_local_llm` 的輸入檢查
  依 `--terms`，所以用 115 學期跑時檢查會通過，但 agent 實際讀的還是 114。

## 輸出位置

- `logs/data_update/<時間>/summary.md`、`summary.json`：步驟結果與變更摘要
- `logs/data_update/<時間>/steps/<步驟>.log`：每個步驟的完整輸出（已遮罩）
- `logs/data_update/<時間>/backup/`：套用前的原檔
- `logs/data_update/incoming/<學期>/`：爬取中的暫存目錄（換進 `data/raw` 後移到該次的 backup）

`logs/` 已在 `.gitignore` 中。
