import gc
from pathlib import Path
from urllib.request import Request, urlopen

import pymupdf
from flask import Flask, jsonify, request, send_from_directory
from ftfy import fix_text


# =========================================================
# KLASÖRLER
# =========================================================

BASE_DIR = Path(__file__).resolve().parent


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
#
# ÖNEMLİ NOT (Vercel için):
# Vercel'de her istek FARKLI bir sunucuya gidebiliyor. Bu yüzden
# kitabı sunucu hafızasında (global değişken) ya da /tmp klasöründe
# SAKLAMIYORUZ. Bunun yerine PDF'i tek seferde işleyip TÜM chunk'ları
# (bölümleri) tarayıcıya (frontend'e) geri gönderiyoruz. Tarayıcı
# bunları kendi hafızasında tutuyor, böylece hangi sunucu cevap
# verirse versin sorun olmuyor.
#
def prepare_pdf_from_bytes(content, pdf_name):

    safe_name = Path(pdf_name).name

    print("PDF açılıyor:", safe_name)

    # PyMuPDF - dosyayı diske yazmadan, doğrudan bytes'tan aç
    doc = pymupdf.open(stream=content, filetype="pdf")

    page_count = len(doc)

    # Chunk boyutu
    if page_count < 100:
        pages_per_chunk = 4

    elif page_count < 300:
        pages_per_chunk = 5

    else:
        pages_per_chunk = 6

    chunks = []
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

                start_page = (
                    chunk_index * pages_per_chunk + 1
                )

                end_page = page_index + 1

                chunks.append({
                    "index": chunk_index,
                    "text": chunk_text,
                    "page_start": start_page,
                    "page_end": end_page,
                })

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

        start_page = (
            chunk_index * pages_per_chunk + 1
        )

        end_page = page_count

        chunks.append({
            "index": chunk_index,
            "text": chunk_text,
            "page_start": start_page,
            "page_end": end_page,
        })

        chunk_word_counts.append(word_count)

        total_words += word_count

        chunk_index += 1

    # PDF'i kapat
    doc.close()

    gc.collect()

    print("=========================================")
    print("KİTAP HAZIR")
    print("=========================================")
    print("Dosya:", safe_name)
    print("Sayfa:", page_count)
    print("Chunk:", chunk_index)
    print("Kelime:", total_words)

    return {
        "file_name": safe_name,
        "page_count": page_count,
        "chunk_count": chunk_index,
        "pages_per_chunk": pages_per_chunk,
        "chunk_word_counts": chunk_word_counts,
        "total_words": total_words,
        "chunks": chunks,
    }


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

    return prepare_pdf_from_bytes(
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

        result = prepare_pdf_from_bytes(
            content,
            filename
        )

        return jsonify(
            ok=True,
            **result
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

        result = prepare_pdf_from_url(url)

        return jsonify(
            ok=True,
            **result
        )

    except Exception as error:

        return jsonify(
            ok=False,
            error=str(error)
        ), 500


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
