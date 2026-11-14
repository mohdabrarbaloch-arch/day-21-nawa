/* Nawa studio — vanilla JS, no build step.
   The interesting part is the transcript highlight: word timings come from the
   server and are matched to real audio playback with a binary search, so the
   highlight never drifts. */

(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const api = {
    token: localStorage.getItem('nawa_token') || '',
    user: JSON.parse(localStorage.getItem('nawa_user') || 'null'),
  };

  let voices = [];
  let current = null;      // active generation detail
  let words = [];          // [{start_ms,end_ms,text}]
  let spans = [];          // transcript span elements, parallel to words
  let pollTimer = null;

  /* ── HTTP ───────────────────────────────────────────── */

  async function call(path, { method = 'GET', body, auth = true } = {}) {
    const headers = {};
    if (body) headers['Content-Type'] = 'application/json';
    if (auth && api.token) headers.Authorization = `Bearer ${api.token}`;

    const res = await fetch(path, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });

    if (res.status === 204) return null;

    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }

    if (!res.ok) {
      if (res.status === 401 && auth) signOut();
      const detail = data && data.detail;
      const message = Array.isArray(detail)
        ? detail.map((d) => d.msg || d.detail || '').join('. ')
        : detail || `Request failed (${res.status})`;
      throw new Error(message);
    }
    return data;
  }

  /* ── Auth ───────────────────────────────────────────── */

  let mode = 'login';

  document.querySelectorAll('.tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      mode = tab.dataset.mode;
      document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('is-on', t === tab));
      $('name-field').hidden = mode === 'login';
      $('auth-submit').textContent = mode === 'login' ? 'Sign in' : 'Create account';
      const input = document.querySelector('[name=password]');
      input.autocomplete = mode === 'login' ? 'current-password' : 'new-password';
      $('auth-hint').hidden = mode === 'login';
      $('auth-err').hidden = true;
    });
  });

  $('auth-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = new FormData(event.target);
    const err = $('auth-err');
    err.hidden = true;

    if (mode === 'register' && form.get('display_name') === '') form.delete('display_name');

    try {
      $('auth-submit').disabled = true;
      const data = await call(`/api/auth/${mode}`, {
        method: 'POST',
        auth: false,
        body: Object.fromEntries(form.entries()),
      });
      api.token = data.access_token;
      api.user = data.user;
      localStorage.setItem('nawa_token', api.token);
      localStorage.setItem('nawa_user', JSON.stringify(api.user));
      enterStudio();
    } catch (error) {
      err.textContent = error.message;
      err.hidden = false;
    } finally {
      $('auth-submit').disabled = false;
    }
  });

  $('demo-btn').addEventListener('click', () => {
    document.querySelector('[name=email]').value = 'demo@nawa.app';
    document.querySelector('[name=password]').value = 'nawademo2026';
    mode = 'login';
    $('auth-form').dispatchEvent(new Event('submit'));
  });

  function signOut() {
    localStorage.removeItem('nawa_token');
    localStorage.removeItem('nawa_user');
    api.token = '';
    api.user = null;
    if (pollTimer) clearInterval(pollTimer);
    $('app').hidden = true;
    $('gate').hidden = false;
  }

  $('avatar').addEventListener('click', signOut);

  /* ── Boot ───────────────────────────────────────────── */

  async function enterStudio() {
    $('gate').hidden = true;
    $('app').hidden = false;
    $('avatar').textContent = (api.user?.display_name || api.user?.email || '?')[0].toUpperCase();
    await Promise.all([loadVoices(), loadQuota()]);
    if (typeof loadLibrary === 'function') loadLibrary();
  }

  async function loadQuota() {
    try {
      const usage = await call('/api/generations/usage');
      $('quota').textContent = `${usage.remaining} left today`;
      $('quota').title = `${usage.used_today} of ${usage.limit} generations used today`;
    } catch { /* non-critical */ }
  }

  async function loadVoices() {
    const data = await call('/api/voices', { auth: false });
    voices = data.languages.flatMap((g) => g.voices);
    const select = $('voice');
    select.innerHTML = '';
    data.languages.forEach((group) => {
      const og = document.createElement('optgroup');
      og.label = `${group.language} (${group.count})`;
      group.voices.forEach((v) => {
        const option = document.createElement('option');
        option.value = v.id;
        option.textContent = `${v.label} — ${v.accent} ${v.gender.toLowerCase()}`;
        og.appendChild(option);
      });
      select.appendChild(og);
    });
    select.value = data.default;
    $('voice-count').textContent = `${data.total} voices`;
  }

  /* ── Views ──────────────────────────────────────────── */

  document.querySelectorAll('.navlink').forEach((link) => {
    link.addEventListener('click', () => {
      const view = link.dataset.view;
      document.querySelectorAll('.navlink').forEach((l) => l.classList.toggle('is-on', l === link));
      document.querySelectorAll('.view').forEach((v) => { v.hidden = v.id !== `view-${view}`; });
      if (view === 'library') loadLibrary();
      if (view === 'voice') loadPronunciations();
    });
  });

  /* ── Compose ────────────────────────────────────────── */

  const SAMPLES = {
    money:
      'Last quarter we raised Rs 2.5 crore at a valuation of $14 million. ' +
      'Our average order is now Rs 1,850, up 12.5 percent, and 40 percent of customers return within 90 days.',
    date:
      'The pilot runs from 15/11/2026 to 2027-03-01. Kickoff is at 09:30 AM in Karachi, ' +
      'and the review happens on the 3rd of every month at 4 PM.',
    urdu: 'یہ آواز کا ایک نمونہ ہے۔ ہم نے 1,50,000 روپے کا بجٹ منظور کیا تھا۔',
    tech:
      'Call 0300-1234567 before 5 PM. Order No. 42 ships on 2026-11-15, costs $1,299 excluding 18% tax, ' +
      'and weighs 2.4 kilograms.',
  };

  document.querySelectorAll('.chip-sample').forEach((chip) => {
    chip.addEventListener('click', () => {
      $('text').value = SAMPLES[chip.dataset.sample];
      updateCounter();
      schedulePreview();
    });
  });

  $('sample-btn').addEventListener('click', () => {
    $('text').value = SAMPLES.money;
    updateCounter();
    schedulePreview();
  });

  function updateCounter() {
    $('counter').textContent = `${$('text').value.length} / 4000`;
  }

  $('text').addEventListener('input', () => {
    updateCounter();
    schedulePreview();
  });

  let previewTimer = null;
  function schedulePreview() {
    if (previewTimer) clearTimeout(previewTimer);
    previewTimer = setTimeout(runPreview, 380);
  }

  async function runPreview() {
    const text = $('text').value.trim();
    if (text.length < 3) {
      $('preview-block').hidden = true;
      return;
    }
    try {
      const data = await call('/api/preview', {
        method: 'POST',
        auth: false,
        body: { text, voice: $('voice').value, normalise: $('normalise').checked },
      });
      $('preview-text').textContent = data.after;
      $('preview-original').textContent = data.before;
      const changed = data.before.trim() !== data.after.trim();
      $('preview-meta').textContent =
        `${data.char_count} chars · ~${Math.round(data.estimated_seconds)}s · ${data.chunks.length} chunk${data.chunks.length === 1 ? '' : 's'}`;
      $('preview-details').hidden = !changed;
      $('preview-block').hidden = false;
    } catch { /* leave the last preview in place */ }
  }

  $('normalise').addEventListener('change', () => schedulePreview());

  // Slider readouts
  const sliders = [
    ['rate', (v) => `${Number(v).toFixed(2)}×`],
    ['pitch', (v) => `${Number(v) > 0 ? '+' : ''}${v} st`],
    ['volume', (v) => `${Math.round(Number(v) * 100)}%`],
  ];
  sliders.forEach(([id, format]) => {
    const el = $(id);
    const out = $(`${id}-val`);
    const sync = () => { out.textContent = format(el.value); };
    el.addEventListener('input', sync);
    sync();
  });

  /* ── Generate ───────────────────────────────────────── */

  $('generate').addEventListener('click', async () => {
    const text = $('text').value.trim();
    const err = $('gen-err');
    err.hidden = true;

    if (text.length < 3) {
      err.textContent = 'Write something first — even one sentence.';
      err.hidden = false;
      return;
    }

    try {
      $('generate').disabled = true;
      $('generate').textContent = 'Sending…';
      const created = await call('/api/generations', {
        method: 'POST',
        body: {
          text,
          voice: $('voice').value,
          rate: Number($('rate').value),
          pitch: Number($('pitch').value),
          volume: Number($('volume').value),
          normalise: $('normalise').checked,
        },
      });
      showPlayer(created);
      poll(created.id);
      loadQuota();
    } catch (error) {
      err.textContent = error.message;
      err.hidden = false;
    } finally {
      $('generate').disabled = false;
      $('generate').textContent = 'Speak it';
    }
  });

  /* ── Player ─────────────────────────────────────────── */

  function showPlayer(gen) {
    $('player-card').hidden = false;
    $('player-title').textContent = gen.title || 'Untitled';
    $('player-eyebrow').textContent = statusLabel(gen.status);
    $('player-meta').textContent = `${gen.voice_label} · ${gen.chunk_count} chunks`;
    $('audio').hidden = true;
    $('play-btn').hidden = true;
    $('transcript').hidden = true;
    $('download').hidden = true;
    $('copy-link').hidden = true;
    $('wave').hidden = false;
    drawWave();

    if (gen.status === 'queued' || gen.status === 'processing') {
      $('progress-line').hidden = false;
      $('progress-text').textContent = 'Synthesising…';
    } else {
      $('progress-line').hidden = true;
    }
  }

  function statusLabel(status) {
    return { queued: 'Queued', processing: 'Synthesising…', completed: 'Ready', failed: 'Failed' }[status] || status;
  }

  function poll(id, attempt = 0) {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
      attempt += 1;
      try {
        const gen = await call(`/api/generations/${id}`);
        if (gen.status === 'completed') {
          clearInterval(pollTimer);
          await renderReady(gen);
          loadLibrary();
        } else if (gen.status === 'failed') {
          clearInterval(pollTimer);
          $('player-eyebrow').textContent = 'Failed';
          $('progress-line').hidden = true;
          $('player-meta').textContent = gen.error || 'Synthesis failed';
        } else if (attempt > 180) {
          clearInterval(pollTimer);
          $('progress-text').textContent = 'Still working — check the library later.';
        }
      } catch {
        if (attempt > 6) clearInterval(pollTimer);
      }
    }, 1200);
  }

  async function renderReady(gen) {
    current = gen;
    words = gen.words || [];
    $('player-eyebrow').textContent = 'Ready';
    $('player-title').textContent = gen.title || 'Untitled';
    $('player-meta').textContent =
      `${gen.voice_label} · ${(gen.duration_ms / 1000).toFixed(1)}s · ${words.length} words`;
    $('progress-line').hidden = true;

    const audio = $('audio');
    audio.src = gen.audio_url;
    audio.hidden = false;
    $('play-btn').hidden = true;

    const download = $('download');
    download.href = `/api/generations/${gen.id}/download?t=${new URL(gen.audio_url, location.origin).searchParams.get('t')}`;
    download.hidden = false;
    $('copy-link').hidden = false;

    buildTranscript();
    drawWave();
    $('wave').classList.add('is-live');
  }

  function buildTranscript() {
    const box = $('transcript');
    box.innerHTML = '';
    spans = [];

    if (!words.length) {
      box.textContent = current?.normalised_text || '';
      box.hidden = false;
      return;
    }

    // Rebuild the text from timings, inserting a space where the service
    // dropped one (it reports punctuation as its own token).
    words.forEach((word) => {
      const span = document.createElement('span');
      span.className = 'w';
      span.textContent = word.text;
      spans.push(span);
      box.appendChild(span);
      box.appendChild(document.createTextNode(' '));
    });

    box.hidden = false;
  }

  /* -- Word highlight driven by real playback time -- */

  function indexAt(ms) {
    // Binary search for the last word whose start is <= ms.
    let lo = 0;
    let hi = words.length - 1;
    let found = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (words[mid].start_ms <= ms) { found = mid; lo = mid + 1; }
      else hi = mid - 1;
    }
    return found;
  }

  let activeIndex = -1;

  $('audio').addEventListener('timeupdate', () => {
    drawWave();
    if (!words.length) return;
    const ms = $('audio').currentTime * 1000;
    const next = indexAt(ms);

    if (next === activeIndex) return;
    if (activeIndex >= 0 && spans[activeIndex]) spans[activeIndex].classList.remove('is-on');
    activeIndex = next;
    if (next >= 0 && spans[next]) {
      spans[next].classList.add('is-on');
      // Keep the spoken word visible without jerking the whole page.
      const box = $('transcript');
      const span = spans[next];
      const target = span.offsetTop - box.clientHeight / 2 + span.clientHeight / 2;
      if (Math.abs(box.scrollTop - target) > box.clientHeight / 2) box.scrollTop = target;
    }
  });

  $('audio').addEventListener('ended', () => {
    if (activeIndex >= 0 && spans[activeIndex]) spans[activeIndex].classList.remove('is-on');
    activeIndex = -1;
    drawWave();
  });

  $('audio').addEventListener('play', () => {
    $('player-eyebrow').textContent = 'Playing';
  });

  $('audio').addEventListener('pause', () => {
    $('player-eyebrow').textContent = 'Ready';
  });

  $('player-close').addEventListener('click', () => {
    $('audio').pause();
    $('player-card').hidden = true;
  });

  $('copy-link').addEventListener('click', async () => {
    if (!current) return;
    const url = new URL(current.audio_url, location.origin).href;
    try {
      await navigator.clipboard.writeText(url);
      $('copy-link').textContent = 'Copied';
      setTimeout(() => { $('copy-link').textContent = 'Copy link'; }, 1600);
    } catch {
      $('copy-link').textContent = 'Copy failed';
      setTimeout(() => { $('copy-link').textContent = 'Copy link'; }, 1600);
    }
  });

  /* -- Waveform bars (deterministic, not random noise) -- */

  function drawWave() {
    const wave = $('wave');
    if (!wave.children.length) {
      for (let i = 0; i < 40; i += 1) wave.appendChild(document.createElement('span'));
    }
    const bars = [...wave.children];
    const audio = $('audio');
    const progress = audio.duration ? audio.currentTime / audio.duration : 0;
    const past = Math.floor(progress * bars.length);

    bars.forEach((bar, i) => {
      // A fixed, human-looking envelope — taller in the middle, varied.
      const h = 18 + Math.abs(Math.sin((i + 1) * 1.9)) * 34 + Math.abs(Math.cos(i * 0.7)) * 12;
      bar.style.height = `${Math.min(100, h)}%`;
      bar.classList.toggle('is-past', i < past);
    });
  }

  /* ── Library ────────────────────────────────────────── */

  async function loadLibrary() {
    const box = $('library');
    if (!box) return;
    try {
      const data = await call('/api/generations?limit=50');
      $('library-count').textContent = data.total
        ? `${data.total} generation${data.total === 1 ? '' : 's'}`
        : '';

      if (!data.items.length) {
        box.innerHTML = '<div class="empty">Nothing here yet. Head to the Studio and say something.</div>';
        return;
      }

      box.innerHTML = '';
      data.items.forEach((gen) => {
        const card = document.createElement('div');
        card.className = 'card';
        card.innerHTML = `
          <div>
            <p class="card-title"></p>
            <div class="card-meta"></div>
          </div>
          <span class="badge badge-${gen.status}">${statusLabel(gen.status)}</span>`;
        card.querySelector('.card-title').textContent = gen.title || 'Untitled';
        card.querySelector('.card-meta').textContent =
          `${gen.voice_label} · ${(gen.duration_ms / 1000).toFixed(1)}s · ${gen.char_count} chars`;
        card.addEventListener('click', () => openFromLibrary(gen));
        box.appendChild(card);
      });
    } catch (error) {
      box.innerHTML = `<div class="empty">Could not load the library: ${error.message}</div>`;
    }
  }

  async function openFromLibrary(gen) {
    document.querySelector('[data-view="studio"]').click();
    showPlayer(gen);
    if (gen.status === 'completed') {
      const detail = await call(`/api/generations/${gen.id}`);
      renderReady(detail);
    } else if (gen.status !== 'failed') {
      poll(gen.id);
    }
  }

  /* ── Pronunciations ─────────────────────────────────── */

  async function loadPronunciations() {
    try {
      const rows = await call('/api/pronunciations');
      const box = $('pron-list');
      if (!rows.length) {
        box.innerHTML = '<div class="empty">No overrides yet. Add one above and it applies to everything you generate.</div>';
        return;
      }
      box.innerHTML = '';
      rows.forEach((row) => {
        const el = document.createElement('div');
        el.className = 'pron-row';
        el.innerHTML = `
          <span class="written"></span>
          <span class="arrow">→</span>
          <span class="said"></span>
          <span class="spacer"></span>
          <button class="icon-btn" title="Remove">✕</button>`;
        el.querySelector('.written').textContent = row.written;
        el.querySelector('.said').textContent = row.spoken;
        el.querySelector('button').addEventListener('click', async () => {
          await call(`/api/pronunciations/${row.id}`, { method: 'DELETE' });
          loadPronunciations();
        });
        box.appendChild(el);
      });
    } catch { /* ignore */ }
  }

  $('pron-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const err = $('pron-err');
    err.hidden = true;
    try {
      await call('/api/pronunciations', {
        method: 'POST',
        body: { written: $('pron-written').value, spoken: $('pron-spoken').value },
      });
      $('pron-written').value = '';
      $('pron-spoken').value = '';
      loadPronunciations();
    } catch (error) {
      err.textContent = error.message;
      err.hidden = false;
    }
  });

  /* ── Start ──────────────────────────────────────────── */

  if (api.token) {
    call('/api/auth/me')
      .then((user) => { api.user = user; enterStudio(); })
      .catch(() => signOut());
  } else {
    $('gate').hidden = false;
  }
})();
