# 部署與環境設定

本文件涵蓋環境變數設定、本地開發、雲端部署流程與資料部署原則。專案介紹請見根目錄
[README.md](../README.md)。

> 後端搬到 AWS（ECS Fargate）並改用 Amazon Bedrock 的做法，請見 [aws-deployment.md](aws-deployment.md)。
> 以下環境變數與 Render 流程描述的是目前仍在運作的舊部署。

---

## 環境需求

- Python 3.10+
- Node.js 18+
- npm 9+

---

## 環境變數

### 根目錄 `.env`

給本地後端與工具腳本使用：

```env
APP_ENV=development
APP_PORT=8000
DATA_DIR=data
COURSE_JSON_PATH=data/processed/courses.json
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:5174,http://localhost:3000

CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=
CLOUDINARY_PROJECT_FOLDER=ncu-ai-guidance/data/raw/projects
```

說明：
- 本地 FastAPI 會讀根目錄 `.env`
- `ALLOWED_ORIGINS` 在本地通常只需要 localhost
- 正式站的 CORS 請在 Render 後台設定

### 前端環境變數

- `frontend/.env.example`
  本地範例
- `frontend/.env.production`
  正式 build 會使用的 API 網址

正式環境目前設定為：

```env
VITE_API_URL=https://ncu-ai-guidance.onrender.com/api
```

---

## 本地開發

### 後端

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

後端預設跑在：

- API：`http://localhost:8000`
- 文件：`http://localhost:8000/docs`

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端預設跑在：

- `http://localhost:5173`

前端若未額外設定 `VITE_API_URL`，會 fallback 到：

```text
http://localhost:8000/api
```

---

## 部署流程

### 1. 前端部署到 Firebase Hosting

目前 repo 已包含 Firebase Hosting workflow：

- `.github/workflows/firebase-hosting-merge.yml`
- `.github/workflows/firebase-hosting-pull-request.yml`

規則：
- push 到 fork repo 的 `main`：自動部署正式站
- fork repo 內部 PR：自動建立 preview deploy
- workflow 已限制只在 `ChiJiun/ncu_ai_guidance` 執行

### 2. 後端部署到 Render

Render 設定建議：

- Runtime：`Python 3`
- Build Command：

```bash
pip install -r backend/requirements.txt
```

- Start Command：

```bash
cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Render 後台至少需要這些 environment variables：

```env
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_PROJECT_FOLDER=ncu-ai-guidance/data/raw/projects
ALLOWED_ORIGINS=http://localhost:5173,https://ncu-ai-guidance.web.app,https://ncu-ai-guidance.firebaseapp.com
```

部署後請確認：

- `https://ncu-ai-guidance.onrender.com/health`
- `https://ncu-ai-guidance.onrender.com/docs`
- `https://ncu-ai-guidance.onrender.com/api/projects`

### 3. PDF 部署到 Cloudinary

專題 PDF 不再跟後端一起部署，改由 Cloudinary 提供公開連結。

上傳腳本：

- `scripts/storage/upload_pdfs_to_cloudinary.py`

使用方式：

```bash
pip install cloudinary python-dotenv
python scripts/storage/upload_pdfs_to_cloudinary.py --dry-run
python scripts/storage/upload_pdfs_to_cloudinary.py
```

---

## 資料部署原則

### 應該留在 repo / 隨後端部署

- `data/processed/assessment_questions.json`
- `data/processed/projects.json`
- `data/processed/courses.json`
- `data/processed/graph/knowledge_graph.json`
- `data/raw/admission/ncu_caac.csv`
- `data/raw/courses/...`（若後端仍直接讀這些原始課程檔）

### 不建議跟後端一起部署

- `data/raw/projects/104-114/**/*.pdf`

這些 PDF 已改由 Cloudinary 提供。
