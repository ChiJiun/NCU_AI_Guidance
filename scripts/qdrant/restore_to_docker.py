"""
將本地 snapshot 還原至 Docker 版本地 Qdrant
前提：本地 Qdrant Docker 已啟動（見下方指令）

啟動 Docker：
  docker run -d -p 6333:6333 -p 6334:6334 ^
    -v "%cd%/data/processed/qdrant_data:/qdrant/storage" ^
    --name qdrant-local qdrant/qdrant

執行還原：
  python scripts/qdrant/restore_to_docker.py
"""
import os, sys, time, requests
from pathlib import Path

ROOT         = Path(__file__).parent.parent.parent
SNAPSHOT_DIR = Path(os.environ.get("QDRANT_SNAPSHOT_DIR") or ROOT / "data" / "processed" / "qdrant_snapshots")
LOCAL_URL    = "http://localhost:6333"

# 若有指定 collection 名稱則只還原那幾個，否則還原全部
# 用法：python restore_to_docker.py ncu_departments ncu_graph_nodes
only = set(sys.argv[1:])

all_snapshots = sorted(SNAPSHOT_DIR.glob("*.snapshot"))
snapshots = [s for s in all_snapshots if not only or s.stem in only]
if not snapshots:
    print(f"[!] {SNAPSHOT_DIR} 找不到任何 .snapshot 檔")
    print("    請先執行：python scripts/qdrant/download_snapshots.py")
    sys.exit(1)

print(f"目標：{LOCAL_URL}")
print(f"找到 {len(snapshots)} 個 snapshot 檔案：")
for s in snapshots:
    size_mb = s.stat().st_size / 1024 / 1024
    print(f"  {s.name}  ({size_mb:.1f} MB)")
print()

# 確認本地 Qdrant 是否在線
print("確認本地 Qdrant 連線...", end=" ", flush=True)
try:
    r = requests.get(f"{LOCAL_URL}/collections", timeout=5)
    r.raise_for_status()
    existing = [c["name"] for c in r.json().get("result", {}).get("collections", [])]
    print(f"OK（現有 {len(existing)} 個 collections）")
except Exception as e:
    print(f"FAIL\n")
    print(f"[!] 無法連到本地 Qdrant：{e}")
    print()
    print("請先啟動 Docker（Windows PowerShell）：")
    print()
    print('  docker run -d -p 6333:6333 -p 6334:6334 `')
    print('    -v "${PWD}/data/processed/qdrant_data:/qdrant/storage" `')
    print('    --name qdrant-local qdrant/qdrant')
    sys.exit(1)

print("-" * 60)
failed = []

for idx, snap_path in enumerate(snapshots, 1):
    name = snap_path.stem
    size_mb = snap_path.stat().st_size / 1024 / 1024
    print(f"[{idx}/{len(snapshots)}] {name}  ({size_mb:.1f} MB)")

    # 若 collection 已存在，先刪除再還原
    if name in existing:
        print(f"  已存在，先刪除...", end=" ", flush=True)
        try:
            r = requests.delete(f"{LOCAL_URL}/collections/{name}", timeout=30)
            r.raise_for_status()
            print("OK")
        except Exception as e:
            print(f"FAIL: {e}")
            failed.append(name)
            continue

    # 上傳 snapshot 還原
    print(f"  還原中...", end=" ", flush=True)
    t0 = time.time()
    try:
        with open(snap_path, "rb") as f:
            r = requests.post(
                f"{LOCAL_URL}/collections/{name}/snapshots/upload?priority=snapshot",
                files={"snapshot": (snap_path.name, f, "application/octet-stream")},
                timeout=600,
            )
        if r.status_code in (200, 201):
            elapsed = time.time() - t0
            print(f"OK ({elapsed:.1f}s)")
        else:
            print(f"FAIL {r.status_code}: {r.text[:300]}")
            failed.append(name)
    except Exception as e:
        print(f"FAIL: {e}")
        failed.append(name)

print()
print("=" * 60)
if failed:
    print(f"[!] 以下 collection 還原失敗：{failed}")
else:
    print(f"全部 {len(snapshots)} 個 collection 還原完成！")

# 驗證結果
print()
print("驗證：")
try:
    r = requests.get(f"{LOCAL_URL}/collections", timeout=10)
    cols = r.json().get("result", {}).get("collections", [])
    for c in cols:
        r2 = requests.get(f"{LOCAL_URL}/collections/{c['name']}", timeout=10)
        info = r2.json().get("result", {})
        count = info.get("points_count", "?")
        print(f"  ✓ {c['name']}：{count} 筆")
except Exception as e:
    print(f"  驗證失敗：{e}")

print()
print("切換到本地模式：將 .env 的 QDRANT_URL 改為 http://localhost:6333")
print("並移除 QDRANT_API_KEY（本地不需要）")
