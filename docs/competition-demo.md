# 比賽展示版：部署、Demo 案例與實證驗證

對應原 repo issue「feat: 比賽展示版部署、Demo 案例與實證驗證」（clairechien0627/NCU_AI_Guidance#28）。
整個作品要呈現的證據鏈是：

```
校內公開資料 → 資料處理（scripts/extraction、scripts/nlp、scripts/rag）
  → 模型與工具（課程助理 ReAct 工具呼叫／研究助理 PDF 檢索）
  → 推論結果（Demo 案例完整記錄分析過程與引用依據）
  → 人工驗證（每個 Demo 案例人工檢查；獨立測試集雙人評分）
  → 量化評估（平均分、通過率、錯誤類型、評分一致性）
```

## 1. 訪客展示模式

公開網站不提供即時提問，避免訪客觸發付費的模型呼叫。前後端各有一個開關，**兩個都要開**：

| 位置 | 設定 | 作用 |
|---|---|---|
| 後端 | `DEMO_MODE=true`（CloudFormation 參數 `DemoMode`，預設就是 `true`） | 預設拒絕：所有 POST／PUT／PATCH／DELETE 一律回 403 `LIVE_AI_DISABLED`，只放行確定不呼叫模型的白名單（量表計分、學測篩選、關鍵字課程搜尋、課程詳情）。GET 照常。 |
| 前端 | build 時設 `VITE_DEMO_MODE=true` | 首頁改為示範案例入口、隱藏登入、課程助理頁導向 `/demo`、研究計畫與課程詳情的提問框換成提示、課程資訊頁只提供一般文字搜尋（語意搜尋需要 embedding，後端會擋）、全站顯示「比賽展示版」說明條。 |

- 後端白名單在 `backend/app/demo_mode.py`。新增白名單前必須確認那個 endpoint 的整條呼叫鏈都不碰 Bedrock。
  `backend/tests/test_demo_mode.py` 會掃描所有路由，確保白名單以外的寫入型 endpoint 都被擋下；
  另外把目前的 GET 路由列成快照，新增 GET 路由時測試會失敗，提醒先確認它不呼叫模型（展示模式會放行所有 GET）。
- 後端狀態可用 `GET /api/demo/status` 確認：`{"demo_mode": true, "live_ai_enabled": false}`。
- 展示模式啟動時不會載入 FlashRank reranker 與向量庫（AI endpoint 都被擋下，用不到），
  記憶體峰值約 420 MB，可以跑在 Render 免費方案（512 MB）上；`GET /ready` 會回 `"rag": "skipped"`。
  細節見 [deployment.md](deployment.md) 的「Render 免費方案的記憶體限制」。
- 模型金鑰只在後端（ECS task role 呼叫 Bedrock，不需要金鑰）。前端打包檔只含公開的 Firebase web config；
  可以在 build 後執行下列指令自行確認：

  ```bash
  grep -l -E "AKIA[0-9A-Z]{16}|AWS_SECRET|bedrock-runtime|AZURE_OPENAI" frontend/dist/assets/*.js || echo OK
  ```

- 前端部署流程（`.github/workflows/firebase-hosting-merge.yml`）**目前還沒有**帶入 `VITE_DEMO_MODE`。
  比賽版上線前要在 workflow 的 build env 加上 `VITE_DEMO_MODE: "true"`（或改由 repository variable 控制）。

## 2. Demo 案例（13 組）

| 步驟 | 指令／檔案 |
|---|---|
| 情境定義 | `data/demo/scenarios.json`：課程助理 10 組、研究助理 3 組，涵蓋一般、資料不足、跨系比較、錯誤前提、安全隱私、複雜推論 |
| 錄製 | `python scripts/demo/record_demo_cases.py`（在本機以真實後端執行，需 Bedrock 等環境變數，**DEMO_MODE 會被強制關閉**） |
| 輸出 | `frontend/src/demo/cases/<id>.json`，前端 build 時打包，展示時不需要後端也不會呼叫模型 |
| 人工檢查 | 逐一核對回答、引用與匿名化，在 `review` 填 `status: "approved"`、`reviewer`、`reviewed_at`、`conclusion` |
| 驗收 | `python scripts/demo/validate_demo_cases.py --require-approved` |

- 錄製腳本是在同一個 process 內啟動真正的後端，並打真正的 SSE endpoint，所以案例內容就是系統的真實輸出。
  **不要手動修改 AI 回答**；回答有問題就修系統或調整情境後重錄（`--only <id> --force`）。
  錄製時會把 `input` + `turns` 的 sha256 寫進 `meta.content_sha256`，驗證腳本會重算比對，內容被改過就不會通過。
  雜湊**不含** `meta`（模型、token、耗時、commit）與 `title`、`scenario`、`review`；這些欄位不受保護，請不要手動修改。
  填寫 `review` 時用一般文字編輯器即可；不要用會把數字 `1.0` 改寫成 `1` 的工具重存整個 JSON，否則雜湊會不符。
- 錄製會寫入對話紀錄（`user_id = demo-recorder:local`）。建議設定 `RECORDER_DATABASE_URL` 指向獨立資料庫
  （例如 Neon 的 branch），避免影響正式站的監控與使用統計；若直接用正式資料庫，錄完後要依這個 user_id 清除紀錄。
  評估腳本 `run_eval.py` 也一樣。
- 研究助理如果錄到「已收到補充，將納入考量。」或空回答（同一 thread 仍有串流進行中，被 stream lock 處理），
  該案例會被標記為錄製失敗、不寫入檔案。
- 已標記 approved 的案例沒有 `--force` 不會被覆蓋。
- 展示模式只顯示 approved 的案例；開發模式會顯示全部，未檢查的會加註「待人工檢查」。
- 匿名化：案例不帶研究計畫的學生姓名；驗證腳本會檢查整輪紀錄（回答、分析步驟、引用課程、來源）
  有沒有 email、手機、身分證字號格式，以及該計畫學生的姓名。
- 頁面：`/demo`（依助理與情境篩選）、`/demo/<id>`（使用情境、輸入資料、分析過程、AI 回答、引用依據、
  結論與人工檢查資訊）。

## 3. 實證驗證（獨立測試集）

評分標準、題型分布與流程見 [evaluation/rubric.md](evaluation/rubric.md)。摘要如下：

```bash
python scripts/evaluation/build_test_set.py --check           # 確認題組沒有被改動
python scripts/evaluation/run_eval.py --run-id final           # 對真實系統跑 30 題
python scripts/evaluation/make_score_sheet.py data/evaluation/runs/final --raters A B
# 兩位評分者各自填 score_A.csv、score_B.csv（1–5 分）
python scripts/evaluation/analyze_scores.py data/evaluation/runs/final
```

`analyze_scores.py` 會產生 `report.md`，內容包括平均分 ± 標準差、通過率（依助理與難度分開）、
錯誤類型、評分一致性（完全一致率、相差 ≤ 1 分比例、quadratic weighted κ），以及代表性的成功與失敗案例。

## 4. 部署檢查清單

- [ ] 確定比賽版本的 commit，並在報告與頁面記錄（Demo 案例的 `meta.git_commit` 會自動記錄錄製時的版本）
- [ ] 後端：依 `docs/aws-deployment.md` 部署，`DemoMode=true`
- [ ] 前端：`VITE_DEMO_MODE=true` build 並部署到 Firebase Hosting
- [ ] `GET /api/demo/status` 回傳 `demo_mode: true`
- [ ] 在瀏覽器確認 `POST /api/chat/stream` 回 403 `LIVE_AI_DISABLED`
- [ ] 桌面與手機版瀏覽首頁、`/demo`、各案例頁、研究計畫頁、課程頁
- [ ] 錯誤頁面：不存在的案例 id 會顯示「找不到這個示範案例」
- [ ] `validate_demo_cases.py --require-approved` 通過
- [ ] 記錄正式網址與版本資訊

## 5. 尚未完成、需要人工處理的部分

- 13 個 Demo 案例都還沒有錄製：需要能用的 Bedrock 環境（AWS Learner Lab 開通後），以及人工檢查。
- 30 題測試集還沒有實際執行與評分：需要兩位評分者。
- Firebase Hosting workflow 還沒有加 `VITE_DEMO_MODE`（修改 CI 設定前需要確認）。
- `POST /api/course-search` 讀取的 `data/processed/courses.json` 目前不在 repo 中，這是既有問題，
  這次沒有處理；展示模式雖然放行這個 endpoint，但它本身就會失敗。
