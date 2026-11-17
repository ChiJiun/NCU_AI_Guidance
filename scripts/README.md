# 資料處理腳本說明

本目錄包含所有資料處理和生成腳本。

> **定期更新資料請用一鍵入口 `python -m scripts.update_data`**（預設 dry-run，加 `--apply` 才寫入），
> 它會依正確順序呼叫下面這些腳本、驗證輸出並產生變更摘要。步驟、旗標、成本與仍需人工處理的部分見
> [`update_data/README.md`](update_data/README.md)。本檔以下的內容是早期的個別腳本說明，部分已過時。

## 腳本列表

### 0. `storage/upload_pdfs_to_cloudinary.py`
**功能：** 批次上傳 `data/raw/projects/104-114/` 的 PDF 到 Cloudinary

**使用方法：**
```bash
python scripts/storage/upload_pdfs_to_cloudinary.py --dry-run
python scripts/storage/upload_pdfs_to_cloudinary.py
```

**需要環境變數：**
```env
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=
CLOUDINARY_PROJECT_FOLDER=ncu-ai-guidance/data/raw/projects
```

**說明：**
- `--dry-run` 只檢查檔案與產生 `public_id`，不會真的上傳
- 正式上傳後，後端會依 `pdfPath` 組出 Cloudinary `pdfUrl`

---

### 1. `1_extract_pdf_metadata.py`
**功能：** 從 PDF 檔案提取研究計畫的 metadata

**輸入：**
- `各系大專生計畫(104-114)/` - PDF 檔案

**輸出：**
- `data/processed/projects.json` - 研究計畫元資料

**使用方法：**
```bash
python 1_extract_pdf_metadata.py
```

**處理內容：**
1. 掃描所有系所資料夾
2. 解析 PDF 檔名格式：`{學年度}{類型}{編號}_{學生姓名}_{研究題目}.pdf`
3. 提取資訊：
   - 學年度 (104-114)
   - 計畫類型 (E/H/M/B)
   - 學生姓名
   - 研究題目
   - 科系歸屬
4. 生成唯一 ID
5. 輸出 JSON 格式

**預期結果：**
- 約 459 筆研究計畫資料
- 涵蓋 38 個系所

---

### 2. `2_generate_questions.py`
**功能：** 從研究計畫生成量表題目

**輸入：**
- `data/processed/projects.json` - 研究計畫資料

**輸出：**
- `data/processed/assessment_questions.json` - 量表題目

**使用方法：**
```bash
python 2_generate_questions.py
```

**處理邏輯：**
1. 讀取所有研究計畫
2. 按科系分組
3. 每個科系隨機選擇 1-3 個代表性研究
4. 使用真實研究題目作為量表題目
5. 根據科系特性配對興趣標籤
6. 分配到三種模式：
   - 高一模式：40 題（文理組綜合）
   - 高二模式：99 題（分文理組）
   - 高三模式：50 題（結合學測）

**標籤配對規則：**
- 資訊/電機相關 → 程式設計、資料分析、人工智慧
- 文學相關 → 文學創作、語言學習、文化研究
- 理學相關 → 數學建模、實驗設計、科學探究
- 等等...

**預期結果：**
- 總計 189 題
- 涵蓋 43 個科系
- 每題包含真實研究題目

---

## 執行順序

如果要重新生成所有資料：

```bash
# 1. 提取研究計畫 metadata
python 1_extract_pdf_metadata.py

# 2. 生成量表題目
python 2_generate_questions.py
```

## 注意事項

### 路徑設定
- 腳本使用相對路徑
- 需要在 `scripts/` 目錄下執行
- 或修改腳本中的路徑設定

### 資料完整性
- 確保 `各系大專生計畫(104-114)/` 資料夾存在
- PDF 檔案命名需符合格式
- 輸出目錄需有寫入權限

### Python 版本
- 建議使用 Python 3.8+
- 需要的套件：
  ```bash
  pip install json
  pip install os
  pip install random
  ```

## 舊版腳本

在 `old_scripts/scripts/` 中保留了舊版本的腳本：
- `1_merge_courses.py` - 課程資料合併（舊版處理流程）

這些腳本已經被新的資料處理流程取代，但保留作為參考。

## 資料品質檢查

### 檢查研究計畫數量
```bash
python -c "import json; data = json.load(open('../data/processed/projects.json')); print(f'總計: {len(data)} 筆')"
```

### 檢查題目分布
```bash
python -c "import json; data = json.load(open('../data/processed/assessment_questions.json')); from collections import Counter; modes = Counter([q['mode'] for q in data]); print(modes)"
```

### 檢查科系涵蓋
```bash
python -c "import json; data = json.load(open('../data/processed/assessment_questions.json')); depts = set([q['department'] for q in data]); print(f'涵蓋 {len(depts)} 個科系')"
```

## 未來改進

1. **PDF 內容提取**
   - 使用 PyMuPDF 提取 PDF 內文
   - 分段提取：研究動機、方法、結果
   - 供 LLM 生成高中生友善版摘要

2. **自動標籤生成**
   - 使用 NLP 技術從研究內容提取關鍵字
   - 自動分類興趣領域

3. **資料驗證**
   - 自動檢查檔名格式
   - 驗證資料完整性
   - 產生資料品質報告

4. **增量更新**
   - 支援增量式資料更新
   - 避免重複處理已有資料
   - 版本控制
