# Demo 案例資料

這個資料夾的 `*.json` 會在前端 build 時打包，供 `/demo` 示範案例頁使用（不需登入、不呼叫模型）。

- **不要手寫或修改 AI 回答內容。** 案例一律由 `scripts/demo/record_demo_cases.py` 對真實後端錄製，
  情境定義在 `data/demo/scenarios.json`。
- 錄製後必須人工檢查，在 `review` 區塊填寫 `status: "approved"`、`reviewer`、`reviewed_at`、
  `conclusion`（一兩句結論，會顯示在案例頁）。正式 build 只會列出 approved 的案例；
  開發伺服器（`npm run dev`）會列出全部，未檢查的會加註「待人工檢查」。
- 部署前執行 `python scripts/demo/validate_demo_cases.py --require-approved`。

這個資料夾目前沒有案例時，`/demo` 會顯示空狀態。詳細流程見 `docs/demo-cases-and-evaluation.md`。
