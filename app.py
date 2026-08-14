import os
import gc
import shutil
from pathlib import Path

import fitz
import requests
from flask import Flask, jsonify, request, send_from_directory
from ftfy import fix_text

BASE_DIR = Path(__file__).resolve().parent
CHUNK_DIR = BASE_DIR / "lazybook_chunks"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

BOOK_STATE = {
    "prepared": False,
    "file_name": "",
    "page_count": 0,
    "chunk_count": 0,
    "pages_per_chunk": 5,
    "chunk_word_counts": [],
    "total_words": 0,
}

app = Flask(__name__, static_folder="static", static_url_path="/static")


def clean_text(text):
    text = fix_text(text or "")
    text = text.replace("\x00", "")
    text = text.replace("\r", "\n")
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip()


def count_words(text):
    return len(str(text).split())


def prepare_pdf_from_bytes(content, pdf_name):
    global BOOK_STATE

    if CHUNK_DIR.exists():
        shutil.rmtree(CHUNK_DIR)
    CHUNK_DIR.mkdir(parents=True, exist_ok=True)

    pdf_path = UPLOAD_DIR / pdf_name
    pdf_path.write_bytes(content)

    print("PDF açılıyor:", pdf_name)

    doc = fitz.open(pdf_path)
    page_count = len(doc)

    if page_count < 100:
        pages_per_chunk = 4
    elif page_count < 300:
        pages_per_chunk = 5
    else:
        pages_per_chunk = 6

    chunk_word_counts = []
    total_words = 0
    current_pages = []
    chunk_index = 0

    print("Toplam sayfa:", page_count)
    print("Kitap hazırlanıyor...")

    for page_index in range(page_count):
        try:
            page = doc.load_page(page_index)
            text = clean_text(page.get_text("text"))
            block = f"\n[Page {page_index + 1}]\n{text}"
            current_pages.append(block)

            if len(current_pages) >= pages_per_chunk:
                chunk_text = "\n".join(current_pages)
                wc = count_words(chunk_text)
                (CHUNK_DIR / f"chunk_{chunk_index}.txt").write_text(
                    chunk_text, encoding="utf-8"
                )
                chunk_word_counts.append(wc)
                total_words += wc
                chunk_index += 1
                current_pages = []

                percent = round((page_index + 1) / page_count * 100)
                print(f"%{percent} hazırlandı - chunk {chunk_index}")
                gc.collect()

        except Exception as e:
            print(f"Sayfa okunamadı: {page_index + 1}")
            print(e)

    if current_pages:
        chunk_text = "\n".join(current_pages)
        wc = count_words(chunk_text)
        (CHUNK_DIR / f"chunk_{chunk_index}.txt").write_text(
            chunk_text, encoding="utf-8"
        )
        chunk_word_counts.append(wc)
        total_words += wc
        chunk_index += 1

    doc.close()
    gc.collect()

    BOOK_STATE = {
        "prepared": True,
        "file_name": pdf_name,
        "page_count": page_count,
        "chunk_count": chunk_index,
        "pages_per_chunk": pages_per_chunk,
        "chunk_word_counts": chunk_word_counts,
        "total_words": total_words,
    }

    print("=========================================")
    print("KİTAP HAZIR")
    print("=========================================")
    print("Dosya:", pdf_name)
    print("Sayfa:", page_count)
    print("Chunk:", chunk_index)
    print("Kelime:", total_words)


def prepare_pdf_from_url(pdf_url):
    print("PDF indiriliyor...")
    response = requests.get(pdf_url, stream=True, timeout=60)
    response.raise_for_status()

    pdf_name = "browser_book.pdf"
    content = bytearray()

    for chunk in response.iter_content(1024 * 1024):
        if chunk:
            content.extend(chunk)

    prepare_pdf_from_bytes(bytes(content), pdf_name)


@app.get("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.post("/api/upload")
def upload_pdf():
    file = request.files.get("pdf")
    if not file or not file.filename:
        return jsonify(ok=False, error="Önce PDF seç."), 400

    filename = Path(file.filename).name
    if not filename.lower().endswith(".pdf"):
        return jsonify(ok=False, error="Sadece PDF dosyası yükleyebilirsin."), 400

    try:
        prepare_pdf_from_bytes(file.read(), filename)
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500


@app.post("/api/prepare-url")
def prepare_url():
    data = request.get_json(silent=True) or {}
    url = str(data.get("url", "")).strip()

    if not url:
        return jsonify(ok=False, error="PDF linki gir."), 400

    try:
        prepare_pdf_from_url(url)
        return jsonify(ok=True)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500


@app.get("/api/meta")
def meta():
    if not BOOK_STATE["prepared"]:
        return jsonify(ok=False)

    return jsonify(
        ok=True,
        file_name=BOOK_STATE["file_name"],
        page_count=BOOK_STATE["page_count"],
        chunk_count=BOOK_STATE["chunk_count"],
        pages_per_chunk=BOOK_STATE["pages_per_chunk"],
        chunk_word_counts=BOOK_STATE["chunk_word_counts"],
        total_words=BOOK_STATE["total_words"],
        mode="DISK CHUNK MODE",
    )


@app.get("/api/chunk/<int:index>")
def chunk(index):
    if not BOOK_STATE["prepared"]:
        return jsonify(ok=False), 404

    path = CHUNK_DIR / f"chunk_{index}.txt"
    if not path.exists():
        return jsonify(ok=False), 404

    text = path.read_text(encoding="utf-8")
    start_page = index * BOOK_STATE["pages_per_chunk"] + 1
    end_page = min(
        BOOK_STATE["page_count"],
        start_page + BOOK_STATE["pages_per_chunk"] - 1,
    )

    return jsonify(
        ok=True,
        text=text,
        page_start=start_page,
        page_end=end_page,
    )


if __name__ == "__main__":
    print("Sesli Kitap sunucusu başlatılıyor...")
    print("Tarayıcıdan http://127.0.0.1:5000 adresini aç.")
    app.run(host="127.0.0.1", port=5000, debug=False)
