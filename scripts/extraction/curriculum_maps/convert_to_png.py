"""
Step 2: 格式統一轉換
將課程地圖的 PDF / PPTX / AVIF / JPG 全部轉成 PNG，
以便後續 Vision API 統一處理。

相依套件：
  pip install pymupdf pillow python-pptx

輸出目錄：data/processed/curriculum_maps_png/
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[3]
CURRICULUM_MAP_DIR = BASE_DIR / "data" / "raw" / "課程地圖"
OUTPUT_DIR         = BASE_DIR / "data" / "processed" / "curriculum_maps_png"

SUPPORTED_FORMATS = {".pdf", ".png", ".jpg", ".jpeg", ".pptx", ".avif"}


# ============================================================
# 各格式轉換函式
# ============================================================

def convert_pdf_to_png(pdf_path: Path, out_dir: Path, stem: str) -> list[Path]:
    """PDF 每頁轉一張 PNG。使用 PyMuPDF（不需要 poppler）。"""
    try:
        import fitz  # pymupdf
    except ImportError:
        print("  ⚠️  pymupdf 未安裝，跳過 PDF 轉換。執行：pip install pymupdf")
        return []

    try:
        doc = fitz.open(str(pdf_path))
        output_paths = []
        for i, page in enumerate(doc):
            mat = fitz.Matrix(150 / 72, 150 / 72)  # 150 dpi
            pix = page.get_pixmap(matrix=mat)
            suffix = f"_p{i+1}" if len(doc) > 1 else ""
            out_path = out_dir / f"{stem}{suffix}.png"
            pix.save(str(out_path))
            output_paths.append(out_path)
        doc.close()
        return output_paths
    except Exception as e:
        print(f"  ❌ PDF 轉換失敗 ({pdf_path.name}): {e}")
        return []


def convert_pptx_to_png(pptx_path: Path, out_dir: Path, stem: str) -> list[Path]:
    """
    PPTX 每張投影片轉 PNG。
    使用 python-pptx 將每頁轉成圖片（透過 LibreOffice 或直接截圖）。
    """
    try:
        from pptx import Presentation
        from pptx.util import Inches
        from PIL import Image
        import io
    except ImportError:
        print("  ⚠️  python-pptx 未安裝，跳過 PPTX 轉換。執行：pip install python-pptx pillow")
        return []

    # 優先嘗試 LibreOffice 轉換（效果最好）
    output_paths = _convert_pptx_via_libreoffice(pptx_path, out_dir, stem)
    if output_paths:
        return output_paths

    # Fallback：用 python-pptx 提取文字 + 縮圖（文字轉圖片）
    print(f"  ℹ️  LibreOffice 不可用，改用 python-pptx 提取文字版本")
    return _convert_pptx_text_fallback(pptx_path, out_dir, stem)


def _convert_pptx_via_libreoffice(pptx_path: Path, out_dir: Path, stem: str) -> list[Path]:
    """透過 LibreOffice 將 PPTX 轉為 PNG（效果最佳）"""
    import subprocess
    import shutil

    if not shutil.which("libreoffice") and not shutil.which("soffice"):
        return []

    cmd_name = "libreoffice" if shutil.which("libreoffice") else "soffice"
    try:
        result = subprocess.run(
            [cmd_name, "--headless", "--convert-to", "png",
             "--outdir", str(out_dir), str(pptx_path)],
            capture_output=True, text=True, timeout=60
        )
        # LibreOffice 輸出檔名格式：stem.png 或 stem_1.png 等
        output_paths = list(out_dir.glob(f"{stem}*.png"))
        if output_paths:
            return sorted(output_paths)
    except Exception as e:
        print(f"  ⚠️  LibreOffice 轉換失敗: {e}")
    return []


def _convert_pptx_text_fallback(pptx_path: Path, out_dir: Path, stem: str) -> list[Path]:
    """
    Fallback：用 python-pptx 把每頁文字轉成純文字圖片
    （視覺效果較差，但至少有內容可讀）
    """
    from pptx import Presentation
    from PIL import Image, ImageDraw, ImageFont

    prs = Presentation(str(pptx_path))
    output_paths = []

    for i, slide in enumerate(prs.slides):
        # 提取投影片文字
        texts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    line = para.text.strip()
                    if line:
                        texts.append(line)

        # 製作文字圖片
        img = Image.new("RGB", (1200, 900), color="white")
        draw = ImageDraw.Draw(img)

        y = 30
        for text in texts:
            draw.text((30, y), text, fill="black")
            y += 28
            if y > 860:
                break

        suffix = f"_p{i+1}" if len(prs.slides) > 1 else ""
        out_path = out_dir / f"{stem}{suffix}.png"
        img.save(str(out_path), "PNG")
        output_paths.append(out_path)

    return output_paths


def convert_image_to_png(img_path: Path, out_dir: Path, stem: str) -> list[Path]:
    """JPG / PNG / AVIF → PNG"""
    try:
        from PIL import Image
        # AVIF 支援
        try:
            import pillow_avif  # noqa: F401
        except ImportError:
            pass  # 若沒有 avif 外掛，PIL 可能仍支援

        img = Image.open(str(img_path)).convert("RGB")
        out_path = out_dir / f"{stem}.png"
        if img_path.suffix.lower() == ".png" and img_path != out_path:
            # 直接複製即可，不需要轉換
            import shutil
            shutil.copy2(str(img_path), str(out_path))
        else:
            img.save(str(out_path), "PNG")
        return [out_path]
    except Exception as e:
        print(f"  ❌ 圖片轉換失敗 ({img_path.name}): {e}")
        return []


# ============================================================
# 主流程
# ============================================================

def convert_all(force: bool = False) -> dict:
    """
    轉換課程地圖資料夾中的所有檔案到 PNG。
    回傳 { "原始檔名": ["輸出PNG路徑", ...] }
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = {}
    files = [f for f in CURRICULUM_MAP_DIR.iterdir()
             if f.is_file() and f.suffix.lower() in SUPPORTED_FORMATS]

    print(f"找到 {len(files)} 個課程地圖檔案")

    for f in sorted(files):
        stem = f.stem
        ext  = f.suffix.lower()

        # 檢查是否已轉換
        existing = list(OUTPUT_DIR.glob(f"{stem}*.png"))
        if existing and not force:
            print(f"  ✅ 已存在，略過：{f.name}")
            results[f.name] = [str(p) for p in existing]
            continue

        print(f"  🔄 轉換：{f.name}")

        if ext == ".pdf":
            output_paths = convert_pdf_to_png(f, OUTPUT_DIR, stem)
        elif ext == ".pptx":
            output_paths = convert_pptx_to_png(f, OUTPUT_DIR, stem)
        elif ext in {".jpg", ".jpeg", ".png", ".avif"}:
            output_paths = convert_image_to_png(f, OUTPUT_DIR, stem)
        else:
            print(f"  ⚠️  不支援的格式：{ext}")
            continue

        if output_paths:
            print(f"     → 產生 {len(output_paths)} 張 PNG")
            results[f.name] = [str(p) for p in output_paths]
        else:
            print(f"     → 轉換失敗")

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="課程地圖格式統一轉換為 PNG")
    parser.add_argument("--force", action="store_true", help="強制重新轉換已存在的檔案")
    args = parser.parse_args()

    results = convert_all(force=args.force)

    success = sum(1 for v in results.values() if v)
    print(f"\n✅ 完成！成功轉換 {success}/{len(results)} 個檔案")
    print(f"   輸出目錄：{OUTPUT_DIR}")


if __name__ == "__main__":
    main()
