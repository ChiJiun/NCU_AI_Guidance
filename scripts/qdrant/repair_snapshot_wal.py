"""
repair_snapshot_wal.py — 修復 snapshot 裡被清成 0 的 WAL first-index

現象：還原時 Qdrant 回 500 "Can't init WAL: failed to read first-index file ... expected value at line 1 column 1"。
原因：snapshot 內 `<shard>/wal/first-index` 長度正確但內容全是 0x00（正常內容是 JSON：{"ack_index":N}）。
作法：把 snapshot 重寫到 OneDrive 之外的資料夾（這些成員是 GNU 稀疏檔，無法就地改），
      只把這個檔案換成同長度的合法 JSON（N=0，用空白補到原長度）。
      ack_index=0 只代表啟動時會重播 WAL 內的操作，upsert 是冪等的，不影響資料。

用法：
  python scripts/qdrant/repair_snapshot_wal.py C:/qdrant_snapshots_fixed
  QDRANT_SNAPSHOT_DIR=C:/qdrant_snapshots_fixed python scripts/qdrant/restore_to_docker.py
"""

import io
import sys
import tarfile
from pathlib import Path

SRC = Path(__file__).parent.parent.parent / "data" / "processed" / "qdrant_snapshots"
NUL = bytes([0])


def fixed_content(size: int) -> bytes:
    head, tail = b'{"ack_index":0', b"}"
    return head + b" " * (size - len(head) - len(tail)) + tail


def repair(src: Path, dst: Path) -> int:
    """重寫 tar：first-index 若內容全為 0，換成合法 JSON；其餘成員照搬（稀疏檔展開成一般檔）。"""
    patched = 0
    with tarfile.open(src) as tin, tarfile.open(dst, "w", format=tarfile.PAX_FORMAT) as tout:
        for m in tin:
            fobj = tin.extractfile(m) if m.isfile() else None
            if m.isfile() and m.name.endswith("wal/first-index"):
                data = fobj.read()
                if data.strip(NUL) == b"":
                    data = fixed_content(len(data))
                    patched += 1
                fobj = io.BytesIO(data)
            if m.isfile():
                m.type = tarfile.REGTYPE
            m.pax_headers = {}
            tout.addfile(m, fobj)
    return patched


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for s in sorted(SRC.glob("*.snapshot")):
        n = repair(s, out / s.name)
        print(f"{s.name}: 修正 {n} 個 first-index")
    return 0


if __name__ == "__main__":
    sys.exit(main())
