/**
 * 比賽展示版的前端開關。
 *
 * VITE_DEMO_MODE=true 時：首頁改為 Demo 入口、隱藏登入、關閉所有即時提問介面。
 * 這只是介面層；真正擋下模型呼叫的是後端的 DEMO_MODE（backend/app/demo_mode.py），
 * 兩邊都要開，公開網站才不會產生模型費用。
 */
export const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === 'true';

export const DEMO_NOTICE = '比賽展示版目前不提供即時提問，以下 AI 回答皆為預先產生的示範結果。';
