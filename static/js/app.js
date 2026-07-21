'use strict';

document.addEventListener('DOMContentLoaded', () => {
  const audioInput   = document.getElementById('audioInput');
  const dropZone     = document.getElementById('dropZone');
  const chosenFile   = document.getElementById('chosenFile');
  const songName     = document.getElementById('songName');
  const apiKey       = document.getElementById('apiKey');
  const referenceImage = document.getElementById('referenceImage');
  const enableSubtitles = document.getElementById('enableSubtitles');
  const customStoryboard = document.getElementById('customStoryboard');
  const uploadForm   = document.getElementById('uploadForm');
  const generateBtn  = document.getElementById('generateBtn');
  const formCard     = document.getElementById('formCard');
  const progressCard = document.getElementById('progressCard');
  const statusMsg    = document.getElementById('statusMsg');
  const progressBarFill = document.getElementById('progressBarFill');
  const progressPercent = document.getElementById('progressPercent');
  const resultCard   = document.getElementById('resultCard');
  const downloadLink = document.getElementById('downloadLink');
  const resetBtn     = document.getElementById('resetBtn');
  const errorCard    = document.getElementById('errorCard');
  const errorMsg     = document.getElementById('errorMsg');
  const errorReset   = document.getElementById('errorResetBtn');

  let selectedFile = null;
  let pollTimer    = null;

  // ── File selection ──────────────────────────────────────────────────
  function handleFile(file) {
    if (!file) return;
    selectedFile = file;
    chosenFile.textContent = file.name;
    if (!songName.value.trim()) {
      songName.value = file.name.replace(/\.[^/.]+$/, '');
    }
  }

  audioInput.addEventListener('change', () => handleFile(audioInput.files[0]));

  dropZone.addEventListener('click', () => audioInput.click());

  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
  });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    handleFile(e.dataTransfer.files[0]);
  });

  // ── Form submit ─────────────────────────────────────────────────────
  uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!selectedFile) {
      alert('נא לבחור קובץ שמע תחילה');
      return;
    }

    const customStoryboardText = customStoryboard.value.trim();
    if (customStoryboardText) {
      try {
        JSON.parse(customStoryboardText);
      } catch (err) {
        alert('הסטוריבורד המותאם אינו JSON תקין: ' + err.message);
        return;
      }
    }

    showProgress('מעלה קובץ...');

    const fd = new FormData();
    fd.append('audio',    selectedFile);
    fd.append('song_name', songName.value.trim() || selectedFile.name);
    fd.append('api_key',   apiKey.value.trim());
    if (referenceImage.files[0]) {
      fd.append('reference_image', referenceImage.files[0]);
    }
    fd.append('enable_subtitles', enableSubtitles.checked ? 'true' : 'false');
    if (customStoryboardText) {
      fd.append('custom_storyboard', customStoryboardText);
    }

    try {
      const res  = await fetch('/generate', { method: 'POST', body: fd });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error || 'שגיאה בהעלאה');
      pollStatus(data.job_id);
    } catch (err) {
      showError(err.message);
    }
  });

  // ── Polling ─────────────────────────────────────────────────────────
  const STATUS_LABELS = {
    starting:   'מכין...',
    audio:      '🎧 Gemini מאזין לשיר ומנתח מילים/קצב/מבנה...',
    storyboard: '🎬 יוצר סטורי בורד עם Gemini...',
    clips:      '🎥 יוצר סצנות וידאו עם Veo 3.1... (עשוי לקחת כמה דקות לכל סצנה)',
    video:      '🎞️ מרכיב סרטון סופי...',
    subtitles:  '💬 מטמיע כתוביות קריוקי...',
  };

  function pollStatus(jobId) {
    pollTimer = setInterval(async () => {
      try {
        const res  = await fetch(`/status/${encodeURIComponent(jobId)}`);
        const data = await res.json();

        // Use server message when available, fall back to generic label
        const label = data.message || STATUS_LABELS[data.status] || '';
        if (label) statusMsg.textContent = label;

        const pct = Math.max(0, Math.min(100, data.progress || 0));
        progressBarFill.style.width = `${pct}%`;
        progressPercent.textContent = `${pct}%`;

        if (data.status === 'done') {
          clearInterval(pollTimer);
          showResult(jobId);
        } else if (data.status === 'error') {
          clearInterval(pollTimer);
          showError(data.error || 'שגיאה ביצירת הסרטון');
        }
      } catch (_) {
        clearInterval(pollTimer);
        showError('שגיאת תקשורת עם השרת');
      }
    }, 2500);
  }

  // ── UI states ───────────────────────────────────────────────────────
  function showProgress(msg) {
    formCard.classList.add('hidden');
    errorCard.classList.add('hidden');
    resultCard.classList.add('hidden');
    statusMsg.textContent = msg;
    progressBarFill.style.width = '0%';
    progressPercent.textContent = '0%';
    progressCard.classList.remove('hidden');
  }

  function showResult(jobId) {
    progressCard.classList.add('hidden');
    downloadLink.href = `/download/${encodeURIComponent(jobId)}`;
    resultCard.classList.remove('hidden');
  }

  function showError(msg) {
    progressCard.classList.add('hidden');
    errorMsg.textContent = msg;
    errorCard.classList.remove('hidden');
  }

  function resetUI() {
    resultCard.classList.add('hidden');
    errorCard.classList.add('hidden');
    progressCard.classList.add('hidden');
    formCard.classList.remove('hidden');
    selectedFile = null;
    audioInput.value = '';
    chosenFile.textContent = '';
    songName.value = '';
    referenceImage.value = '';
    enableSubtitles.checked = true;
    customStoryboard.value = '';
    if (pollTimer) clearInterval(pollTimer);
  }

  resetBtn.addEventListener('click', resetUI);
  errorReset.addEventListener('click', resetUI);
});
