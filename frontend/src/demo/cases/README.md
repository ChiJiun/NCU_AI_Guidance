# Demo 案例資料

這個資料夾的 `*.json` 會在前端 build 時打包，供比賽展示版的 `/demo` 頁面使用。

- **不要手寫或修改 AI 回答內容。** 案例一律由 `scripts/demo/record_demo_cases.py` 對真實後端錄製，
  情境定義在 `data/demo/scenarios.json`。
- 錄製後必須人工檢查，在 `review` 區塊填寫 `status: "approved"`、`reviewer`、`reviewed_at`、
  `conclusion`（一兩句結論，會顯示在案例頁）。只有 approved 的案例會出現在展示版（`VITE_DEMO_MODE=true`）。
- 上線前執行 `python scripts/demo/validate_demo_cases.py --require-approved`。

詳細流程見 `docs/competition-demo.md`。
