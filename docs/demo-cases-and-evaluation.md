# Demo 案例頁與雙人評分實證評估

本文件說明兩組工具：

1. **Demo 案例頁**（`/demo`）：預先對真實系統提問、錄下完整過程並經人工檢查的 AI 回答，前端直接打包，
   瀏覽時不需登入、不呼叫模型。
2. **雙人評分實證評估**（30 題）：用獨立題組對兩個 AI 助理做人工評分，產生平均分、通過率、錯誤類型與評分一致性。

兩者合起來呈現的證據鏈是：

```
校內公開資料 → 資料處理（scripts/extraction、scripts/nlp、scripts/rag）
  → 模型與工具（課程助理工具呼叫／研究助理 PDF 檢索）
  → 推論結果（Demo 案例完整記錄分析過程與引用依據）
  → 人工驗證（每個 Demo 案例人工檢查；獨立測試集雙人評分）
  → 量化評估（平均分、通過率、錯誤類型、評分一致性）
```

> 與既有評測的分工：`docs/10-retrieval-evaluation/` 與 `scripts/test_course_agent/` 是課程助理的
> 100 題評測集（程式硬指標 + AI 評審），用於開發中反覆比較改動效果；本文件的 30 題評估涵蓋兩個助理、
> 採兩位評分者獨立人工評分，用於對外報告。兩者檔案完全分開，互不取代，詳見
> [evaluation/rubric.md](evaluation/rubric.md#與既有評測的分工)。

## 1. Demo 案例（13 組）

| 步驟 | 指令／檔案 |
|---|---|
| 情境定義 | `data/demo/scenarios.json`：課程助理 10 組、研究助理 3 組，涵蓋一般、資料不足、跨系比較、錯誤前提、安全隱私、複雜推論 |
| 錄製 | `python scripts/demo/record_demo_cases.py`（在本機以真實後端執行，需與執行後端相同的 `.env`；模型供應商沿用後端目前設定，**會產生模型費用**） |
| 輸出 | `frontend/src/demo/cases/<id>.json`，前端 build 時打包，瀏覽時不需要後端也不會呼叫模型 |
| 人工檢查 | 逐一核對回答、引用與匿名化，在 `review` 填 `status: "approved"`、`reviewer`、`reviewed_at`、`conclusion` |
| 驗收 | `python scripts/demo/validate_demo_cases.py --require-approved` |

- 錄製腳本（`scripts/demo/assistant_runner.py`）在同一個 process 內啟動真正的後端（`app.main.app`），
  以 FastAPI dependency override 換掉登入，再打真正的 SSE endpoint（`/api/chat/stream`、
  `/api/projects/{id}/chat/stream`），所以案例內容就是系統的真實輸出。
- **不要手動修改 AI 回答**；回答有問題就修系統或調整情境後重錄（`--only <id> --force`）。
  錄製時會把 `input` + `turns` 的 sha256 寫進 `meta.content_sha256`，驗證腳本會重算比對，內容被改過就不會通過。
  雜湊**不含** `meta`（模型、token、耗時、commit）與 `title`、`scenario`、`review`；這些欄位不受保護，請不要手動修改。
  填寫 `review` 時用一般文字編輯器即可；不要用會把數字 `1.0` 改寫成 `1` 的工具重存整個 JSON，否則雜湊會不符。
- 錄製會寫入對話紀錄（`user_id = demo-recorder:local`）。建議設定 `RECORDER_DATABASE_URL` 指向獨立的測試資料庫，
  避免影響正式站的監控與使用統計；若直接用正式資料庫，錄完後要依這個 user_id 清除紀錄。評估腳本 `run_eval.py` 也一樣。
- 研究助理需要後端的 PDF 問答已就緒、且該研究計畫的 PDF 已完成索引，否則請求會被拒絕（503／409），該案例記為失敗。
  如果錄到「已收到補充，將納入考量。」或空回答（同一 thread 仍有串流進行中，被 stream lock 處理），
  該案例也會被標記為錄製失敗、不寫入檔案。
- 已標記 approved 的案例沒有 `--force` 不會被覆蓋。
- 顯示規則：正式 build（`npm run build`）只列出 approved 的案例；開發伺服器（`npm run dev`）會列出全部，
  未檢查的會加註「待人工檢查」。這是顯示層的過濾，未檢查的 JSON 仍會被打包，有問題的錄製結果不要提交進 repo。
  沒有任何案例時 `/demo` 會顯示空狀態。
- 匿名化：案例不帶研究計畫的學生姓名；驗證腳本會檢查整輪紀錄（回答、分析步驟、引用課程、來源）
  有沒有 email、手機、身分證字號格式，以及該計畫學生的姓名。
- 頁面：`/demo`（依助理與情境篩選，首頁 hero 區有入口）、`/demo/<id>`（使用情境、輸入資料、分析過程、
  AI 回答、引用依據、結論與人工檢查資訊）。不存在或未核可的案例 id 會顯示「找不到這個示範案例」。

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
  並刻意避開 Demo 案例用到的系所與研究計畫。`data/processed/` 變動導致題組不同時，`--check` 與
  `tests/test_demo_eval_scripts.py` 會失敗；確認變動合理後重新執行 `build_test_set.py` 並提交新題組
  （已開始評分的批次不要換題）。
- `analyze_scores.py` 會產生 `report.md`，內容包括平均分 ± 標準差、通過率（依助理與難度分開）、
  錯誤類型、評分一致性（完全一致率、相差 ≤ 1 分比例、quadratic weighted κ），以及代表性的成功與失敗案例。
  有安裝 matplotlib 時另外輸出長條圖。

## 3. 測試

```bash
python -m pytest tests/test_demo_eval_scripts.py
```

只測純函式（SSE 解析、案例組裝與驗證、題組產生、評分統計），不連網路、不呼叫模型。

## 4. 尚未完成、需要人工處理的部分

- 13 個 Demo 案例都還沒有錄製：需要能呼叫模型的後端環境，以及人工檢查。
- 30 題測試集還沒有實際執行與評分：需要兩位評分者。
