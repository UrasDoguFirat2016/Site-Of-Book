let meta = null;
let currentChunkIndex = 0;
let currentChunkText = "";
let utterance = null;
let currentRate = 1;
let currentVolume = 1;

const textPanel = document.getElementById("textPanel");
const bindingFill = document.getElementById("bindingFill");
const bindingPct = document.getElementById("bindingPct");
const bindingStep = document.getElementById("bindingStep");

document.getElementById("rateSlider").addEventListener("input", function () {
  currentRate = parseFloat(this.value);
  document.getElementById("rateText").innerText =
    currentRate.toFixed(1) + "x";
});

document.getElementById("volumeSlider").addEventListener("input", function () {
  currentVolume = parseFloat(this.value);
  document.getElementById("volumeText").innerText =
    Math.round(currentVolume * 100) + "%";
});

function setProgress(value, text) {
  bindingFill.style.width = value + "%";
  bindingPct.innerText = value + "%";
  bindingStep.innerText = text;
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || "Sunucu hatası.");
  }
  return data;
}

async function prepareFromUrl() {
  const url = document.getElementById("pdfUrl").value.trim();

  if (!url) {
    alert("PDF linki gir.");
    return;
  }

  try {
    alert("PDF indiriliyor...");
    await api("/api/prepare-url", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({url})
    });
    alert("PDF hazırlandı.");
  } catch (err) {
    console.error(err);
    alert("Hata oluştu: " + err.message);
  }
}

async function syncBook() {
  try {
    stopAudio();

    setProgress(10, "Metadata alınıyor");
    document.getElementById("bindingText").innerText = "Bağlanıyor...";

    meta = await api("/api/meta");

    document.getElementById("preparedText").innerText = "Hazır ✅";
    setProgress(40, "Metadata işlendi");

    document.getElementById("metaFile").innerText = meta.file_name;
    document.getElementById("metaPages").innerText = meta.page_count;
    document.getElementById("metaChunks").innerText = meta.chunk_count;
    document.getElementById("metaWords").innerText = meta.total_words;

    setProgress(70, "İlk chunk yükleniyor");
    await loadChunk(0);

    setProgress(100, "Bağlantı tamamlandı");
    document.getElementById("bindingText").innerText = "Bağlandı ✅";
  } catch (err) {
    console.error(err);
    document.getElementById("preparedText").innerText = "Hazır değil";
    document.getElementById("bindingText").innerText = "Bağlantı hatası";
    setProgress(100, "Bağlantı hatası");
    alert("Bağlantı hatası: " + err.message);
  }
}

async function uploadPdf() {
  const input = document.getElementById("pdfUpload");
  if (!input.files.length) {
    alert("Önce PDF seç.");
    return;
  }

  const form = new FormData();
  form.append("pdf", input.files[0]);

  try {
    setProgress(10, "PDF yükleniyor");
    const data = await api("/api/upload", {
      method: "POST",
      body: form
    });
    setProgress(100, "PDF hazırlandı");
    document.getElementById("preparedText").innerText = "Hazır ✅";
    alert("PDF hazırlandı.");
    await syncBook();
  } catch (err) {
    setProgress(100, "Hata");
    alert("Hazırlama hatası: " + err.message);
  }
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderChunk(text) {
  const pages = String(text).split(/\[Page \d+\]/g);
  let pageNumber = 1;
  let wordId = 0;
  let html = "";

  pages.forEach(p => {
    p = p.trim();
    if (!p) return;

    const words = p.split(/\s+/);
    const rendered = words.map(w => `
      <span class="word" id="w${wordId++}">
        ${escapeHtml(w)}
      </span>
    `).join(" ");

    html += `
      <div class="page-card">
        <div class="page-label">𐌔𐌀𐌙𐌅𐌀 ${pageNumber}</div>
        <div class="page-content">${rendered}</div>
      </div>
    `;

    pageNumber++;
  });

  return `<div class="page-grid">${html}</div>`;
}

async function loadChunk(index) {
  if (!meta) return;
  if (index < 0 || index >= meta.chunk_count) return;

  const data = await api("/api/chunk/" + index);

  currentChunkIndex = index;
  currentChunkText = data.text;
  textPanel.innerHTML = renderChunk(currentChunkText);

  document.getElementById("activeChunk").innerText =
    (currentChunkIndex + 1) + " / " + meta.chunk_count;
}

function highlightWord(charIndex) {
  const words = currentChunkText.split(/\s+/);
  let total = 0;
  let target = 0;

  for (let i = 0; i < words.length; i++) {
    total += words[i].length + 1;
    if (charIndex < total) {
      target = i;
      break;
    }
  }

  document.querySelectorAll(".word").forEach(el => {
    el.classList.remove("highlight");
  });

  const active = document.getElementById("w" + target);
  if (active) active.classList.add("highlight");
}

function speakCurrentChunk() {
  if (!currentChunkText) {
    alert("Önce kitabı bağla.");
    return;
  }

  speechSynthesis.cancel();

  utterance = new SpeechSynthesisUtterance(currentChunkText);
  utterance.rate = currentRate;
  utterance.volume = currentVolume;
  utterance.lang = document.getElementById("langSelect").value;

  utterance.onboundary = function (e) {
    if (typeof e.charIndex === "number") {
      highlightWord(e.charIndex);
    }
  };

  utterance.onend = async function () {
    if (meta && currentChunkIndex < meta.chunk_count - 1) {
      await loadChunk(currentChunkIndex + 1);
      speakCurrentChunk();
    }
  };

  speechSynthesis.speak(utterance);
}

function playAudio() {
  stopAudio();
  speakCurrentChunk();
}

function pauseAudio() {
  speechSynthesis.pause();
}

function resumeAudio() {
  speechSynthesis.resume();
}

function stopAudio() {
  speechSynthesis.cancel();
}

async function nextChunk() {
  stopAudio();
  await loadChunk(currentChunkIndex + 1);
}

async function prevChunk() {
  stopAudio();
  await loadChunk(currentChunkIndex - 1);
}
