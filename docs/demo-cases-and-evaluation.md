# 展示版示範對話與雙人評分實證評估

本文件說明兩組工具：

1. **展示版示範對話**：預先對真實系統提問、錄下完整過程並經人工檢查的 AI 回答。展示版（`LIVE_AI_ACCESS=developers`）
   中，不能即時提問的訪客直接在課程助理、研究計畫頁裡看示範對話，個人分析頁顯示由示範對話算出的「示範學生」分析；
   瀏覽時不需登入、不呼叫模型。
2. **雙人評分實證評估**（30 題）：用獨立題組對兩個 AI 助理做人工評分，產生平均分、通過率、錯誤類型與評分一致性。

兩者合起來呈現的證據鏈是：

```
校內公開資料 → 資料處理（scripts/extraction、scripts/nlp、scripts/rag）
  → 模型與工具（課程助理工具呼叫／研究助理 PDF 檢索）
  → 推論結果（示範對話完整記錄工具呼叫過程、推薦課程與引用頁碼）
  → 人工驗證（每組示範人工檢查；獨立測試集雙人評分）
  → 量化評估（平均分、通過率、錯誤類型、評分一致性）
```

> 與既有評測的分工：`docs/10-retrieval-evaluation/` 與 `scripts/test_course_agent/` 是課程助理的
> 100 題評測集（程式硬指標 + AI 評審），用於開發中反覆比較改動效果；本文件的 30 題評估涵蓋兩個助理、
> 採兩位評分者獨立人工評分，用於對外報告。兩者檔案完全分開，互不取代，詳見
> [evaluation/rubric.md](evaluation/rubric.md#與既有評測的分工)。

## 1. 展示版示範對話（課程 12 組、研究 4 組）

| 步驟 | 指令／檔案 |
|---|---|
| 題目 | `scripts/demo/demo_questions.json`：第一輪多取自 100 題評測集（`origin` 標出題號），再加上自然的追問，最多 3 輪；涵蓋一般、複雜、資料不足、安全限制四種情境 |
| 錄製 | `python scripts/demo/record_demos.py`（`--only course|research`、`--ids <id>…`、`--dry-run`）；需與執行後端相同的 `.env`，**會產生模型費用** |
| 輸出 | `frontend/public/demo/course-assistant.json`、`research-assistant.json`（前端以靜態檔讀取，不呼叫模型） |
| 人工檢查 | 逐一核對回答、推薦課程、引用頁碼與匿名化，沒問題再把該組的 `reviewed` 改成 `true` |
| 驗收 | `python scripts/demo/validate_demos.py --require-reviewed` |
| 示範學生分析 | `python scripts/demo/build_demo_analytics.py` → `frontend/public/demo/analytics.json` |

- 錄製腳本在同一個 process 內直接呼叫真實的課程助理（`llm_service.stream_with_tools`）與研究助理
  （`route_agent_stream`），所以示範內容就是系統的真實輸出；課程助理不寫入對話紀錄，研究助理會在 PDF 問答的
  checkpoint 資料庫留下錄製用的 thread。
- **不要手動修改 AI 回答**；回答有問題就修系統或換題目後重錄（`--ids <id>`）。重錄過的案例 `reviewed` 會自動改回 `false`。
- 研究助理需要後端的 PDF 問答已就緒、且該研究計畫的 PDF 已完成索引。
- 顯示規則：正式 build 只顯示 `reviewed: true` 的示範；開發伺服器會顯示全部，未檢查的加註「未審核」。
- 匿名化：`validate_demos.py` 會檢查整輪紀錄（回答、推薦課程、工具軌跡、來源）有沒有 email、手機、身分證字號格式、
  殘留的去識別化標記（例如 `<PRIVATE_PERSON>`），以及該研究計畫學生的姓名。
- 示範學生分析：把已審核的示範當成同一位學生的紀錄，用和正式版相同的計算函式
  （`session_store.compute_course_analytics`、`compute_pdf_analytics`）產生；換題目或重錄後要重新執行。
- 前端入口：首頁「示範對話」區、課程助理與研究計畫頁的示範清單（`?demo=<id>` 可直接開某一組）、
  右上角「示範學生 ▾」選單（個人分析、團隊成員登入）。舊的 `/demo`、`/demo/<id>` 網址會轉到對應的助理頁。
- 展示版對外時（未登入或不在開放名單）不顯示新版／v3 的版本切換。

## 2. 雙人評分實證評估（獨立測試集）

評分標準、題型分布與流程見 [evaluation/rubric.md](evaluation/rubric.md)。摘要如下：

```bash
python scripts/evaluation/build_test_set.py --check           # 確認題組與資料一致、沒有被改動（離線）
python scripts/evaluation/run_eval.py --run-id final           # 對真實系統跑 30 題（會產生模型費用）
python scripts/evaluation/make_score_sheet.py data/evaluation/runs/final --raters A B
# 兩位評分者各自填 score_A.csv、score_B.csv（1–5 分）
python scripts/evaluation/analyze_scores.py data/evaluation/runs/final
```

- `data/evaluation/test_set.json` 由 `build_test_set.py` 以固定亂數種子從 `data/processed/` 產生，
  並刻意避開舊版 Demo 案例（已移除）用到的系所與研究計畫。現在的展示版示範對話與評估題的題目不重複、研究計畫也不重疊
  （`tests/test_demo_eval_scripts.py` 會檢查），但課程示範涉及的部分系所（大氣科學、太空科學與工程、中國文學）
  與評估題有重疊，報告時請一併說明。`data/processed/` 變動導致題組不同時，`--check` 與
  `tests/test_demo_eval_scripts.py` 會失敗；確認變動合理後重新執行 `build_test_set.py` 並提交新題組
  （已開始評分的批次不要換題）。
- `analyze_scores.py` 會產生 `report.md`，內容包括平均分 ± 標準差、通過率（依助理與難度分開）、
  錯誤類型、評分一致性（完全一致率、相差 ≤ 1 分比例、quadratic weighted κ），以及代表性的成功與失敗案例。
  有安裝 matplotlib 時另外輸出長條圖。

## 3. 測試

```bash
python -m pytest tests/test_demo_eval_scripts.py
```

只測純函式（SSE 解析、示範對話驗證、題組產生、評分統計），不連網路、不呼叫模型。

## 4. 尚未完成、需要人工處理的部分

- 30 題測試集還沒有實際執行與評分：需要兩位評分者。
