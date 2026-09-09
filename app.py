import gc
import shutil
from pathlib import Path
from urllib.request import Request, urlopen

import pymupdf
from flask import Flask, jsonify, request, send_from_directory
from ftfy import fix_text


# =========================================================
# KLASÖRLER
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

# Vercel'de geçici olarak yazılabilir alan
DATA_DIR = Path("/tmp/lazybook")

CHUNK_DIR = DATA_DIR / "lazybook_chunks"
UPLOAD_DIR = DATA_DIR / "uploads"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# =========================================================
# KİTAP DURUMU
# =========================================================

BOOK_STATE = {
    "prepared": False,
    "file_name": "",
    "page_count": 0,
    "chunk_count": 0,
    "pages_per_chunk": 5,
    "chunk_word_counts": [],
    "total_words": 0,
}


# =========================================================
# FLASK
# =========================================================

app = Flask(
    __name__,
    static_folder="static",
    static_url_path="/static"
)


# =========================================================
# YARDIMCI FONKSİYONLAR
# =========================================================

def clean_text(text):
    text = fix_text(text or "")
    text = text.replace("\x00", "")
    text = text.replace("\r", "\n")

    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")

    return text.strip()


def count_words(text):
    return len(str(text).split())


# =========================================================
# PDF HAZIRLAMA
# =========================================================

def prepare_pdf_from_bytes(content, pdf_name):
    global BOOK_STATE

    # Eski chunk'ları temizle
    if CHUNK_DIR.exists():
        shutil.rmtree(CHUNK_DIR)

    CHUNK_DIR.mkdir(parents=True, exist_ok=True)

    # Güvenli dosya adı
    safe_name = Path(pdf_name).name

    pdf_path = UPLOAD_DIR / safe_name

    pdf_path.write_bytes(content)

    print("PDF açılıyor:", safe_name)

    # PyMuPDF
    doc = pymupdf.open(pdf_path)

    page_count = len(doc)

    # Chunk boyutu
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

    # =====================================================
    # SAYFALARI OKU
    # =====================================================

    for page_index in range(page_count):

        try:
            page = doc.load_page(page_index)

            text = clean_text(
                page.get_text("text")
            )

            block = (
                f"\n[Page {page_index + 1}]\n"
                f"{text}"
            )

            current_pages.append(block)

            # Chunk tamamlandı
            if len(current_pages) >= pages_per_chunk:

                chunk_text = "\n".join(current_pages)

                word_count = count_words(chunk_text)

                chunk_file = (
                    CHUNK_DIR /
                    f"chunk_{chunk_index}.txt"
                )

                chunk_file.write_text(
                    chunk_text,
                    encoding="utf-8"
                )

                chunk_word_counts.append(word_count)

                total_words += word_count

                chunk_index += 1

                current_pages = []

                percent = round(
                    (page_index + 1)
                    / page_count
                    * 100
                )

                print(
                    f"%{percent} hazırlandı - "
                    f"chunk {chunk_index}"
                )

                gc.collect()

        except Exception as error:

            print(
                f"Sayfa okunamadı: "
                f"{page_index + 1}"
            )

            print(error)

    # =====================================================
    # SON CHUNK
    # =====================================================

    if current_pages:

        chunk_text = "\n".join(current_pages)

        word_count = count_words(chunk_text)

        chunk_file = (
            CHUNK_DIR /
            f"chunk_{chunk_index}.txt"
        )

        chunk_file.write_text(
            chunk_text,
            encoding="utf-8"
        )

        chunk_word_counts.append(word_count)

        total_words += word_count

        chunk_index += 1

    # PDF'i kapat
    doc.close()

    gc.collect()

    # =====================================================
    # DURUMU KAYDET
    # =====================================================

    BOOK_STATE = {
        "prepared": True,
        "file_name": safe_name,
        "page_count": page_count,
        "chunk_count": chunk_index,
        "pages_per_chunk": pages_per_chunk,
        "chunk_word_counts": chunk_word_counts,
        "total_words": total_words,
    }

    print("=========================================")
    print("KİTAP HAZIR")
    print("=========================================")
    print("Dosya:", safe_name)
    print("Sayfa:", page_count)
    print("Chunk:", chunk_index)
    print("Kelime:", total_words)


# =========================================================
# URL'DEN PDF İNDİR
# =========================================================

def prepare_pdf_from_url(pdf_url):

    print("PDF indiriliyor...")

    # requests yerine Python urllib
    req = Request(
        pdf_url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    content = bytearray()

    with urlopen(req, timeout=60) as response:

        while True:

            chunk = response.read(
                1024 * 1024
            )

            if not chunk:
                break

            content.extend(chunk)

    prepare_pdf_from_bytes(
        bytes(content),
        "browser_book.pdf"
    )


# =========================================================
# ANA SAYFA
# =========================================================

@app.get("/")
def index():

    return send_from_directory(
        BASE_DIR,
        "index.html"
    )


# =========================================================
# PDF YÜKLE
# =========================================================

@app.post("/api/upload")
def upload_pdf():

    file = request.files.get("pdf")

    if not file or not file.filename:

        return jsonify(
            ok=False,
            error="Önce PDF seç."
        ), 400

    filename = Path(
        file.filename
    ).name

    if not filename.lower().endswith(".pdf"):

        return jsonify(
            ok=False,
            error="Sadece PDF dosyası yükleyebilirsin."
        ), 400

    try:

        content = file.read()

        prepare_pdf_from_bytes(
            content,
            filename
        )

        return jsonify(
            ok=True
        )

    except Exception as error:

        return jsonify(
            ok=False,
            error=str(error)
        ), 500


# =========================================================
# URL'DEN PDF HAZIRLA
# =========================================================

@app.post("/api/prepare-url")
def prepare_url():

    data = request.get_json(
        silent=True
    ) or {}

    url = str(
        data.get("url", "")
    ).strip()

    if not url:

        return jsonify(
            ok=False,
            error="PDF linki gir."
        ), 400

    try:

        prepare_pdf_from_url(url)

        return jsonify(
            ok=True
        )

    except Exception as error:

        return jsonify(
            ok=False,
            error=str(error)
        ), 500


# =========================================================
# KİTAP BİLGİLERİ
# =========================================================

@app.get("/api/meta")
def meta():

    if not BOOK_STATE["prepared"]:

        return jsonify(
            ok=False
        )

    return jsonify(

        ok=True,

        file_name=BOOK_STATE[
            "file_name"
        ],

        page_count=BOOK_STATE[
            "page_count"
        ],

        chunk_count=BOOK_STATE[
            "chunk_count"
        ],

        pages_per_chunk=BOOK_STATE[
            "pages_per_chunk"
        ],

        chunk_word_counts=BOOK_STATE[
            "chunk_word_counts"
        ],

        total_words=BOOK_STATE[
            "total_words"
        ],

        mode="DISK CHUNK MODE"
    )


# =========================================================
# CHUNK GETİR
# =========================================================

@app.get("/api/chunk/<int:index>")
def chunk(index):

    if not BOOK_STATE["prepared"]:

        return jsonify(
            ok=False
        ), 404

    path = (
        CHUNK_DIR /
        f"chunk_{index}.txt"
    )

    if not path.exists():

        return jsonify(
            ok=False
        ), 404

    text = path.read_text(
        encoding="utf-8"
    )

    start_page = (
        index *
        BOOK_STATE["pages_per_chunk"]
        + 1
    )

    end_page = min(

        BOOK_STATE["page_count"],

        start_page
        + BOOK_STATE["pages_per_chunk"]
        - 1
    )

    return jsonify(

        ok=True,

        text=text,

        page_start=start_page,

        page_end=end_page
    )


# =========================================================
# LOCAL ÇALIŞTIRMA
# =========================================================

if __name__ == "__main__":

    print(
        "Sesli Kitap sunucusu başlatılıyor..."
    )

    print(
        "Tarayıcıdan "
        "http://127.0.0.1:5000 "
        "adresini aç."
    )

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
