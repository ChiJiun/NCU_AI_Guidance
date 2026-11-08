# Qdrant 備份與還原教學

從雲端 Qdrant 備份所有 collection 到本地，並透過 Docker 在本地端運行。

## 檔案說明

| 檔案 | 用途 |
|------|------|
| `test_connection.py` | 測試 Qdrant 連線並列出所有 collections |
| `download_snapshots.py` | 從雲端下載所有 collection 的 snapshot |
| `restore_to_docker.py` | 將 snapshot 還原至本地 Docker Qdrant |

---

## 備份流程

### Step 1 — 確認 `.env` 指向雲端

```env
QDRANT_URL=https://<your-cluster>.cloud.qdrant.io
QDRANT_API_KEY=<your-api-key>
```

### Step 2 — 下載所有 snapshot

```bash
python scripts/qdrant/download_snapshots.py
```

snapshot 檔案會存放於 `data/processed/qdrant_snapshots/`。

### Step 3 — 啟動本地 Qdrant Docker

```bash
docker-compose up -d
```

### Step 4 — 還原所有 snapshot

```bash
python scripts/qdrant/restore_to_docker.py
```

若只需還原特定 collection：

```bash
python scripts/qdrant/restore_to_docker.py ncu_departments ncu_graph_nodes
```

### Step 5 — 切換 `.env` 至本地模式

```env
QDRANT_URL=http://localhost:6333
# QDRANT_API_KEY 不需要，可刪除或註解
```

---

## 驗證

```bash
python scripts/qdrant/test_connection.py
```

或直接查詢：

```bash
curl http://localhost:6333/collections
```

---

## 注意事項

- **不要把 Qdrant 的儲存目錄放在 OneDrive／雲端同步的資料夾底下。** 同步工具會在 Qdrant 寫檔時動到檔案
  （產生 `-電腦名稱` 的衝突副本、改壞 WAL 的 `first-index`），造成 collection 損壞、重啟崩潰迴圈。
  `docker-compose.yml` 因此使用 Docker 具名 volume（`qdrant_storage`），資料存在 Docker 自己的磁碟空間。
- 第一次啟動（或換成新 volume）是空的：先 `docker compose up -d`，再執行
  `python scripts/qdrant/restore_to_docker.py` 從 snapshot 還原；之後若圖譜或 NLP 檔案有更新，用
  `python scripts/rag/sync_graph_nodes.py --apply` 與 `python scripts/rag/update_course_nlp_payload.py --apply`
  做差異同步，不必全量重建。
- **目前的 `data/processed/qdrant_snapshots/*.snapshot`（09-11）無法直接還原**：快照內許多小檔案
  （`wal/first-index`、`config.json`、`version.info`、`status.dat`）是沒有資料區塊的稀疏檔，內容全空，
  Qdrant 會回 500（`Can't init WAL` / `Can't parse version`）。`repair_snapshot_wal.py` 只補得了 WAL，
  補不了其餘檔案，所以請改從雲端重新下載快照，或請持有健康資料的組員提供。
  圖譜節點 collection 則可隨時用 `python scripts/rag/build_qdrant_index.py --reset` 重建（只 embed 節點名稱，約 $0.0001）。
- 舊的 `data/processed/qdrant_data/` 資料夾（舊版 bind mount）已不再使用，確認新 volume 正常後可自行刪除。
- container 重啟後 volume 內的資料不會消失
- 若還原失敗，直接重跑指定 collection 即可，腳本會自動刪除舊的再重建
- 雲端 snapshot 下載時間依 collection 大小而定，`ncu_graph_nodes` 約需數分鐘
