"""
Spyder: File → Run veya hücreleri buraya kopyala.
Önce Spyder'da Working directory = proje kökü (binance-sentiment-bot) olsun.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# --- 1) Proje kökü (Spyder'da ~/untitled27.py çalışınca cwd yanlış olur — cwd KULLANMA) ---
ROOT = Path("/Users/hamzabalik/binance-sentiment-bot").resolve()
if not (ROOT / "src" / "scraper" / "announcements.py").exists():
    raise SystemExit(f"Yanlış ROOT: {ROOT}")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Alternatif: bu dosyayı projede tutup F5: ROOT = Path(__file__).resolve().parents[1]

# --- 2) Log ----------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# --- 3) Çek ----------------------------------------------------------------
from src.scraper.announcements import scrape_announcements

START = datetime(2025, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 5, 14, 23, 59, 59, 999999, tzinfo=timezone.utc)
OUT = ROOT / "data/raw/announcements_from_2025-06-01.jsonl"

# Tüm kataloglar (8 adet): catalog_ids=None
# Sadece bazılarını tekrar denemek için: catalog_ids=[49, 50, 51, 93, 128, 157, 161]
result = scrape_announcements(
    start_date=START,
    end_date=END,
    output_path=OUT,
    catalog_ids=None,
)

print("Çıktı:", OUT)
print("Yazılan satır:", result.total_written)
print("Hata sayısı:", len(result.errors))
for e in result.errors:
    print(" ", e)
