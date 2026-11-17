# 資料目錄說明

本目錄包含 NCU 科系探索系統的所有資料檔案。

> **更新 `data/processed` 請用 `python -m scripts.update_data`**：每個檔案由哪個步驟產生、
> 怎麼定期執行、哪些步驟會花錢或寫外部服務，見 [`scripts/update_data/README.md`](../scripts/update_data/README.md)。
> 下方「資料處理流程」一節是早期記錄，部分路徑與檔案（如 `courses.json`）已不再使用。

## 目錄結構

```
data/
├── raw/                          # 原始資料
│   ├── courses/                 # 課程原始資料
│   │   ├── 114_1/              # 114學年度第1學期 (87個JSON檔)
│   │   └── 114_2/              # 114學年度第2學期 (87個JSON檔)
│   ├── projects/               # 研究計畫原始資料
│   │   └── 104-114/            # 104-114學年度大專生計畫 (38個系所資料夾)
│   └── admission/              # 學測篩選資料
│       └── ncu_caac.csv        # 中央大學學測篩選標準
│
└── processed/                   # 處理後資料
    ├── courses.json            # 整合後課程資料 (3,316筆)
    ├── projects.json           # 研究計畫元資料 (459筆)
    └── assessment_questions.json  # 量表題目 (189題)
```

## 資料檔案說明

### Raw Data (原始資料)

#### 1. `raw/courses/114_1/` 和 `114_2/`
- **來源：** 中央大學課程系統
- **格式：** JSON
- **檔案數量：** 每學期 87 個檔案
- **命名規則：** `{學院}_{系所}.json`
- **內容：** 各系所的課程詳細資訊
  - 課程代碼、名稱（中英文）
  - 學分、必選修
  - 授課教師、時間、教室
  - 課程目標、內容、評分方式

#### 2. `raw/projects/104-114/`
- **來源：** 各系大專生研究計畫 PDF 檔案
- **格式：** PDF 文件
- **資料夾數量：** 38 個系所
- **檔案命名：** `{學年度}{類型}{編號}_{學生姓名}_{研究題目}.pdf`
  - 類型：E (個人) / H (雙人) / M (多人) / B (跨領域)
- **總計：** 約 459 個研究計畫
- **部署策略：** 不建議隨後端一起部署，正式環境改上傳至 Cloudinary

#### 3. `raw/admission/ncu_caac.csv`
- **來源：** 大學甄選入學委員會
- **格式：** CSV
- **內容：** 中央大學各系組學測篩選標準
  - 系所代碼、名稱
  - 各科採計與檢定標準
  - 招收人數

### Processed Data (處理後資料)

#### 1. `processed/courses.json`
- **來源：** 由 `raw/courses/114_1/` 和 `114_2/` 合併處理
- **格式：** JSON Array
- **筆數：** 3,316 筆
- **處理：**
  - 合併兩學期資料
  - 去重（保留較新學期）
  - 新增 `semester_display` 欄位 (上學期/下學期/全年)
  - 統一欄位格式

**欄位說明：**
```json
{
  "id": "課程ID_學期",
  "serial_no": "流水號",
  "course_id": "課程代碼",
  "course_name_zh": "中文課程名稱",
  "course_name_en": "英文課程名稱",
  "semester": "114_1",
  "semester_number": "1",
  "semester_display": "上學期",
  "college": "學院",
  "department": "系所",
  "credits": 3,
  "required_elective": "必修/選修",
  "instructor": "授課教師",
  "course_objective": "課程目標",
  ...
}
```

#### 2. `processed/projects.json`
- **來源：** 由 `raw/projects/104-114/` 提取 metadata
- **格式：** JSON Array
- **筆數：** 459 筆
- **處理：**
  - 從 PDF 檔名提取資訊
  - 自動歸類科系
  - 生成唯一 ID

**欄位說明：**
```json
{
  "id": "proj001",
  "year": "109",
  "type": "H",
  "department": "資訊工程學系",
  "studentName": "王小明",
  "title": "基於深度學習的影像辨識系統",
  "pdfPath": "資訊工程學系/109H123_王小明_基於深度學習的影像辨識系統.pdf"
}
```

#### 3. `processed/assessment_questions.json`
- **來源：** 由 `projects.json` 生成真實研究題目
- **格式：** JSON Array
- **筆數：** 189 題
- **分布：**
  - 高一模式：40 題
  - 高二模式：99 題
  - 高三模式：50 題
- **涵蓋：** 43 個科系

**欄位說明：**
```json
{
  "id": "q001",
  "mode": "grade2",
  "department": "資訊工程學系",
  "title": "基於深度學習的影像辨識系統",
  "motivation": "研究動機說明",
  "method": "研究方法說明",
  "result": "預期成果說明",
  "tags": ["人工智慧", "影像處理", "深度學習"]
}
```

## 資料處理流程

### 1. 課程資料處理
```bash
# 位於：old_scripts/scripts/1_merge_courses.py
cd old_scripts/scripts
python 1_merge_courses.py
```

**處理步驟：**
1. 讀取 `data_ncu_course/114_1/` 和 `114_2/` 所有 JSON 檔案
2. 標準化欄位格式
3. 去除重複課程（保留較新學期）
4. 新增學期顯示欄位
5. 輸出到 `data/processed/courses.json`

### 2. 研究計畫資料提取
```bash
# 位於：scripts/1_extract_pdf_metadata.py
cd scripts
python 1_extract_pdf_metadata.py
```

**處理步驟：**
1. 掃描 `各系大專生計畫(104-114)/` 所有 PDF 檔案
2. 從檔名提取：學年度、類型、學生姓名、研究題目
3. 根據資料夾歸類科系
4. 生成唯一 ID
5. 輸出到 `backend/app/mock_data/projects_metadata.json`
   （現已移動到 `data/processed/projects.json`）

### 3. 量表題目生成
```bash
# 位於：scripts/2_generate_questions.py
cd scripts
python 2_generate_questions.py
```

**處理步驟：**
1. 讀取 `data/processed/projects.json`
2. 每個科系隨機選擇 1-3 個研究計畫
3. 使用真實研究題目作為量表題目
4. 配對適當的興趣標籤
5. 分配到高一/高二/高三模式
6. 輸出到 `data/processed/assessment_questions.json`

## 資料更新

### 當課程資料更新時
1. 將新的學期資料放入 `data/raw/courses/`
2. 執行課程處理腳本
3. 後端會自動讀取新的 `processed/courses.json`

### 當研究計畫更新時
1. 將新的 PDF 檔案放入 `raw/projects/104-114/` 對應系所資料夾
2. 執行 metadata 提取與題目生成腳本
3. 執行 `scripts/storage/upload_pdfs_to_cloudinary.py`
4. 後端讀取 `projects.json`，並依 `pdfPath` 組出 Cloudinary `pdfUrl`

## 注意事項

1. **備份重要**：原始資料 (`raw/`) 不應被修改或刪除
2. **編碼格式**：所有文字檔案使用 UTF-8 編碼
3. **CSV 編碼**：`ncu_caac.csv` 使用 UTF-8-BOM 編碼
4. **檔案大小**：`courses.json` 約 12 MB，載入時注意記憶體
5. **PDF 部署**：`raw/projects/104-114/` 主要作為原始資料來源，正式環境請使用 Cloudinary
6. **路徑引用**：後端程式碼使用相對路徑，移動檔案需同步更新

## 相關腳本

- `scripts/1_extract_pdf_metadata.py` - PDF metadata 提取
- `scripts/2_generate_questions.py` - 量表題目生成
- `old_scripts/scripts/1_merge_courses.py` - 課程資料合併（舊版）

## 資料統計

| 資料類型 | 原始資料 | 處理後 | 備註 |
|---------|---------|--------|------|
| 課程 | 174 個 JSON 檔 | 3,316 筆 | 兩學期合併 |
| 研究計畫 | 459 個 PDF | 459 筆 | 104-114 學年度 |
| 量表題目 | - | 189 題 | 從研究計畫生成 |
| 學測標準 | 1 個 CSV | - | 各系篩選標準 |
