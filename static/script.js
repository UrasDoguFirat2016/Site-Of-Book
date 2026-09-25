let meta = null;
let chunksData = []; // Kitap sunucudan bir kere geliyor, burada saklanıyor
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
    setProgress(10, "PDF indiriliyor");
    const data = await api("/api/prepare-url", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({url})
    });
    applyBookData(data);
    alert("PDF hazırlandı.");
    syncBook();
  } catch (err) {
    console.error(err);
    setProgress(100, "Hata");
    alert("Hata oluştu: " + err.message);
  }
}

// Sunucudan gelen kitap verisini (bütün chunk'lar dahil) tarayıcıda saklar.
// Artık sunucuya "kitap hazır mı?" diye tekrar sormaya gerek yok,
// çünkü kitap zaten burada (chunksData içinde) duruyor.
function applyBookData(data) {
  meta = {
    file_name: data.file_name,
    page_count: data.page_count,
    chunk_count: data.chunk_count,
    pages_per_chunk: data.pages_per_chunk,
    total_words: data.total_words,
  };
  chunksData = data.chunks || [];

  document.getElementById("preparedText").innerText = "Hazır ✅";
  document.getElementById("metaFile").innerText = meta.file_name;
  document.getElementById("metaPages").innerText = meta.page_count;
  document.getElementById("metaChunks").innerText = meta.chunk_count;
  document.getElementById("metaWords").innerText = meta.total_words;
}

function syncBook() {
  stopAudio();

  if (!meta || chunksData.length === 0) {
    document.getElementById("bindingText").innerText = "Bağlantı hatası";
    setProgress(100, "Bağlantı hatası");
    alert("Önce bir PDF yükle ya da linkten hazırla.");
    return;
  }

  setProgress(70, "İlk bölüm yükleniyor");
  loadChunk(0);

  setProgress(100, "Bağlantı tamamlandı");
  document.getElementById("bindingText").innerText = "Bağlandı ✅";
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
    applyBookData(data);
    alert("PDF hazırlandı.");
    syncBook();
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

function loadChunk(index) {
  if (!meta) return;
  if (index < 0 || index >= chunksData.length) return;

  const chunkData = chunksData[index];

  currentChunkIndex = index;
  currentChunkText = chunkData.text;
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

let availableVoices = [];

function loadVoices() {
  availableVoices = speechSynthesis.getVoices();
}

loadVoices();
if (speechSynthesis.onvoiceschanged !== undefined) {
  speechSynthesis.onvoiceschanged = loadVoices;
}

// Seçilen dile en uygun sesi bulur.
// Önce tam eşleşme (ör: "ja-JP"), yoksa dilin ilk 2 harfiyle
// eşleşen herhangi bir ses (ör: "ja-...") aranır.
function findVoiceForLang(langCode) {
  if (!availableVoices.length) {
    loadVoices();
  }

  const exact = availableVoices.find(v => v.lang === langCode);
  if (exact) return exact;

  const prefix = langCode.split("-")[0];
  const partial = availableVoices.find(v => v.lang.toLowerCase().startsWith(prefix.toLowerCase()));
  if (partial) return partial;

  return null;
}

function speakCurrentChunk() {
  if (!currentChunkText) {
    alert("Önce kitabı bağla.");
    return;
  }

  const langCode = document.getElementById("langSelect").value;
  const voice = findVoiceForLang(langCode);

  if (!voice) {
    alert(
      "Bu cihazda seçtiğin dil için kurulu bir ses bulunamadı.\n" +
      "Metin yine de görünecek ama sesli okunamayacak.\n" +
      "Cihazının ayarlarından bu dilin 'metin okuma / text-to-speech' sesini kurman gerekiyor."
    );
  }

  speechSynthesis.cancel();

  utterance = new SpeechSynthesisUtterance(currentChunkText);
  utterance.rate = currentRate;
  utterance.volume = currentVolume;
  utterance.lang = langCode;
  if (voice) utterance.voice = voice;

  utterance.onboundary = function (e) {
    if (typeof e.charIndex === "number") {
      highlightWord(e.charIndex);
    }
  };

  utterance.onerror = function (e) {
    console.error("Konuşma hatası:", e);
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
