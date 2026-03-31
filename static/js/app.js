// ─── State ───────────────────────────────────────────────────────────────
  let currentMode     = 'hybrid';
  let selectedIndices = new Set(['all']); // multiselect; 'all' = reserved "search everything" key
  let activeIndicesMap = null;            // logical key → physical index name (from active profile)
  let evalMode        = false;
  let markedIds    = new Set();
  let lastHits     = [];
  let activeFilters = []; // [{type: 'term'|'gte'|'lte', field: string, value: string}]
  let rankEvalQueries = []; // [{id, query, ratings: [{doc_id, rating}]}]

  // ─── Mode / Index selectors ──────────────────────────────────────────────
  function setMode(m) {
    currentMode = m;
    document.querySelectorAll('#modeGroup button').forEach(b => b.classList.toggle('active', b.dataset.mode === m));
    document.getElementById('weightsSection').classList.toggle('visible', m === 'hybrid');
  }

  function toggleIndex(k) {
    if (k === 'all') {
      selectedIndices = new Set(['all']);
    } else {
      selectedIndices.delete('all');
      if (selectedIndices.has(k)) {
        selectedIndices.delete(k);
        if (selectedIndices.size === 0) selectedIndices.add('all');
      } else {
        selectedIndices.add(k);
      }
    }
    _syncIndexButtons();
  }

  function _syncIndexButtons() {
    document.querySelectorAll('#indexGroup button').forEach(b => {
      b.classList.toggle('active', selectedIndices.has(b.dataset.index));
    });
  }

  /** Returns the index_key to send to the search API.
   *  - 'all' if all or nothing selected
   *  - single logical key if exactly one selected
   *  - comma-joined physical names for partial multi-selection
   */
  function getEffectiveIndex() {
    if (selectedIndices.has('all') || selectedIndices.size === 0) return 'all';
    if (selectedIndices.size === 1) return [...selectedIndices][0];
    // partial selection → join physical names directly
    if (activeIndicesMap) {
      const physicals = [...selectedIndices].map(k => activeIndicesMap[k]).filter(Boolean);
      if (physicals.length) return physicals.join(',');
    }
    return 'all';
  }

  // ─── Weight sliders ──────────────────────────────────────────────────────
  function onWeightChange(changed) {
    const bs = document.getElementById('bm25Slider');
    const ks = document.getElementById('knnSlider');
    if (changed === 'bm25') ks.value = 100 - parseInt(bs.value);
    else                    bs.value = 100 - parseInt(ks.value);
    updateWeightUI();
  }

  function resetWeights() {
    document.getElementById('bm25Slider').value = 30;
    document.getElementById('knnSlider').value  = 70;
    updateWeightUI();
  }

  function updateWeightUI() {
    const b = parseInt(document.getElementById('bm25Slider').value);
    const k = 100 - b;
    document.getElementById('bm25Pct').textContent = b + '%';
    document.getElementById('knnPct').textContent  = k + '%';
    document.getElementById('bm25Bar').style.width = b + '%';
    document.getElementById('knnBar').style.width  = k + '%';
  }

  // ─── Filters ─────────────────────────────────────────────────────────────

  function addFilter() {
    const field = document.getElementById('filterField').value.trim();
    const type  = document.getElementById('filterType').value;
    const value = document.getElementById('filterValue').value.trim();
    if (!field || !value) return;
    activeFilters.push({ type, field, value });
    document.getElementById('filterField').value = '';
    document.getElementById('filterValue').value = '';
    renderActiveFiltersList();
  }

  function removeFilter(idx) {
    activeFilters.splice(idx, 1);
    renderActiveFiltersList();
  }

  function clearFilters() {
    activeFilters = [];
    renderActiveFiltersList();
  }

  function getFilters() {
    const result = {};
    activeFilters.forEach(({ type, field, value }) => {
      const key = type === 'term' ? 'filter_term' : `filter_${type}`;
      if (!result[key]) result[key] = [];
      result[key].push(`${field}:${value}`);
    });
    return result;
  }

  function renderActiveFiltersList() {
    const list = document.getElementById('activeFiltersList');
    const clearBtn = document.getElementById('clearFiltersBtn');
    if (!activeFilters.length) {
      list.innerHTML = '';
      if (clearBtn) clearBtn.style.display = 'none';
      return;
    }
    if (clearBtn) clearBtn.style.display = '';
    list.innerHTML = activeFilters.map((f, i) => `
      <div class="filter-chip">
        <span class="filter-chip-type">${esc(f.type)}</span>
        <span class="filter-chip-field">${esc(f.field)}</span>
        <span class="filter-chip-colon">:</span>
        <span class="filter-chip-value">${esc(f.value)}</span>
        <button class="filter-chip-remove" onclick="removeFilter(${i})">×</button>
      </div>`).join('');
  }

  function renderActiveFilters(filters) {
    const el = document.getElementById('activeFilters');
    el.innerHTML = Object.entries(filters)
      .map(([k, v]) => `<span class="filter-tag">${esc(k)}: <strong>${esc(String(v))}</strong></span>`).join('');
  }

  // ─── Eval mode ───────────────────────────────────────────────────────────
  function toggleEvalMode() {
    evalMode = document.getElementById('evalToggle').checked;
    document.getElementById('results').classList.toggle('eval-mode', evalMode);
    if (!evalMode) clearMarked();
  }

  function onExplainToggle() {
    const explain = document.getElementById('explainToggle').checked;
    const q = document.getElementById('q').value.trim();
    if (!explain && lastHits.length) {
      // Turning off: re-render cached hits without breakdown (no server call needed)
      renderResults(lastHits, false, currentMode);
    } else if (explain && q) {
      // Turning on: must re-fetch because score_breakdown data only comes with explain=true
      doSearch();
    }
  }

  function clearMarked() {
    markedIds.clear();
    document.querySelectorAll('.card-checkbox').forEach(cb => cb.checked = false);
    document.querySelectorAll('.card').forEach(c => c.classList.remove('marked'));
    updateMarkedCount();
    document.getElementById('metricsPanel').classList.remove('visible');
  }

  function updateMarkedCount() {
    const n = markedIds.size;
    document.getElementById('markedCount').textContent = n;
    document.getElementById('evalBtn').disabled = (n === 0);
    document.getElementById('saveTemplateBtn').disabled = (n === 0);
  }

  function onCardCheck(id, checked) {
    if (checked) markedIds.add(id);
    else         markedIds.delete(id);
    document.querySelector(`.card[data-id="${id}"]`)?.classList.toggle('marked', checked);
    updateMarkedCount();
  }

  // ─── URL builder ─────────────────────────────────────────────────────────
  function buildUrl(base) {
    const q       = document.getElementById('q').value.trim();
    const size    = document.getElementById('sizeSelect').value;
    const cands   = document.getElementById('candidatesSelect').value;
    const explain = document.getElementById('explainToggle').checked;
    const bw      = (parseInt(document.getElementById('bm25Slider').value) / 100).toFixed(2);
    const kw      = (1 - parseFloat(bw)).toFixed(2);

    const params = new URLSearchParams({
      q, mode: currentMode, index: getEffectiveIndex(), size,
      num_candidates: cands, explain: explain ? 'true' : 'false',
      bm25_weight: bw, knn_weight: kw,
    });
    // Filter params are arrays → use append() so FastAPI receives repeated keys
    Object.entries(getFilters()).forEach(([k, vs]) => {
      if (Array.isArray(vs)) vs.forEach(v => params.append(k, v));
      else params.set(k, String(vs));
    });
    return `${base}?${params}`;
  }

  // ─── Main search ─────────────────────────────────────────────────────────
  async function doSearch() {
    const q = document.getElementById('q').value.trim();
    if (!q) return;
    setError(null);
    setLoading(true);
    document.getElementById('results').innerHTML = '';
    document.getElementById('meta').innerHTML = '';
    document.getElementById('metricsPanel').classList.remove('visible');

    try {
      const t0  = performance.now();
      const res = await fetch(buildUrl('/api/v1/search'));
      const ms  = Math.round(performance.now() - t0);
      if (!res.ok) throw new Error((await res.json().catch(() => ({detail: res.statusText}))).detail);
      const data = await res.json();
      setLoading(false);
      lastHits = data.hits;
      renderMeta(data, ms);
      renderActiveFilters(data.filters || {});
      renderResults(data.hits, document.getElementById('explainToggle').checked, data.mode);
    } catch(e) {
      setLoading(false);
      setError(e.message);
    }
  }

  // ─── Eval run ────────────────────────────────────────────────────────────
  async function runEval() {
    const q = document.getElementById('q').value.trim();
    if (!q || markedIds.size === 0) return;
    setError(null);
    setLoading(true);

    const bw = (parseInt(document.getElementById('bm25Slider').value) / 100).toFixed(2);
    const kw = (1 - parseFloat(bw)).toFixed(2);

    const body = {
      query: q,
      relevant_ids: [...markedIds],
      mode: currentMode,
      index: getEffectiveIndex(),
      k: parseInt(document.getElementById('sizeSelect').value),
      bm25_weight: parseFloat(bw),
      knn_weight: parseFloat(kw),
      num_candidates: parseInt(document.getElementById('candidatesSelect').value),
    };

    try {
      const res  = await fetch('/api/v1/eval', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) });
      if (!res.ok) throw new Error((await res.json().catch(() => ({detail: res.statusText}))).detail);
      const data = await res.json();
      setLoading(false);
      renderMetrics(data);
      // Re-render hits, highlight relevant positions
      renderResults(data.hits, false, currentMode, new Set(data.relevant_positions.map(p => p - 1)));
    } catch(e) {
      setLoading(false);
      setError(e.message);
    }
  }

  // ─── Render helpers ──────────────────────────────────────────────────────
  function setLoading(on) { document.getElementById('spinner').classList.toggle('active', on); }

  function setError(msg) {
    const el = document.getElementById('errorBanner');
    el.classList.toggle('visible', !!msg);
    el.textContent = msg || '';
  }

  function renderMeta(data, ms) {
    const modeStr  = `<strong>${data.mode}</strong>`;
    const indexStr = `<strong>${data.index}</strong>`;
    document.getElementById('meta').innerHTML =
      `<strong>${data.total.toLocaleString()}</strong> docs · ${data.hits.length} shown · ${modeStr} · ${indexStr} · <strong>${ms}ms</strong>`;
  }

  function renderMetrics(data) {
    const m = data.metrics;
    document.getElementById('mNDCG').textContent      = m.ndcg_at_k.toFixed(3);
    document.getElementById('mMRR').textContent       = m.mrr.toFixed(3);
    document.getElementById('mPrecision').textContent = m.precision_at_k.toFixed(3);
    document.getElementById('mRecall').textContent    = m.recall_at_k.toFixed(3);

    const posHtml = data.relevant_positions.map(p =>
      `<span class="pos-badge">#${p}</span>`).join('');
    document.getElementById('metricInfo').innerHTML =
      `Found <strong>${data.relevant_found}</strong> of <strong>${data.relevant_provided}</strong> relevant docs &nbsp;|&nbsp; positions: ${posHtml}`;
    document.getElementById('metricsPanel').classList.add('visible');
  }

  // ─── Index color registry ─────────────────────────────────────────────────
  // Assign colors in encounter order — avoids hash collisions between similar index names
  const INDEX_TAG_COLORS = ['idx-c0','idx-c1','idx-c2','idx-c3','idx-c4','idx-c5','idx-c6','idx-c7','idx-c8','idx-c9','idx-c10','idx-c11'];
  const _indexColorMap = new Map();

  function indexColorClass(key) {
    if (!_indexColorMap.has(key)) {
      _indexColorMap.set(key, INDEX_TAG_COLORS[_indexColorMap.size % INDEX_TAG_COLORS.length]);
    }
    return _indexColorMap.get(key);
  }

  function resetIndexColors() { _indexColorMap.clear(); }

  function orderLogicalIndexKeys(keys) {
    const rest = keys.filter(k => k !== 'all').sort((a, b) => a.localeCompare(b));
    return keys.includes('all') ? ['all', ...rest] : [...rest];
  }

  function renderCollectionButtons(orderedKeys, container) {
    container.innerHTML = '';
    orderedKeys.forEach(k => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.dataset.index = k;
      btn.textContent = k.charAt(0).toUpperCase() + k.slice(1);
      btn.classList.toggle('active', selectedIndices.has(k));
      btn.title = k === 'all' ? 'Search all indices' : `Toggle index "${k}" (Ctrl+click for multi-select)`;
      btn.onclick = (e) => {
        if (k !== 'all' && (e.ctrlKey || e.metaKey || e.shiftKey)) {
          // modifier key: pure toggle without clearing others
          if (selectedIndices.has(k)) {
            selectedIndices.delete(k);
            if (selectedIndices.size === 0) selectedIndices.add('all');
          } else {
            selectedIndices.delete('all');
            selectedIndices.add(k);
          }
          _syncIndexButtons();
        } else {
          toggleIndex(k);
        }
      };
      container.appendChild(btn);
    });
  }

  function populateExperimentIndexSelects(orderedKeys, tmplSelect) {
    const prevSelected = new Set([...tmplSelect.selectedOptions].map(o => o.value));
    tmplSelect.innerHTML = '';
    orderedKeys.forEach(k => {
      const ot = document.createElement('option');
      ot.value = k;
      ot.textContent = k.charAt(0).toUpperCase() + k.slice(1);
      ot.selected = prevSelected.has(k);
      tmplSelect.appendChild(ot);
    });
    // If nothing selected, select 'all' or first key
    if (![...tmplSelect.options].some(o => o.selected)) {
      const allOpt = [...tmplSelect.options].find(o => o.value === 'all') || tmplSelect.options[0];
      if (allOpt) allOpt.selected = true;
    }
  }

  function getTmplIndexValue() {
    const sel = document.getElementById('tmplIndex');
    const selected = [...sel.selectedOptions].map(o => o.value);
    if (selected.length === 0) return 'all';
    if (selected.includes('all') || selected.length === 1) return selected[0] ?? 'all';
    // Multiple specific indices — join as comma-separated logical keys
    return selected.filter(k => k !== 'all').join(',');
  }

  // Fields excluded from JSON display — embedding vectors are large and unreadable
  const _HIDDEN_FIELDS = new Set(['embedding']);

  function cardSnippet(source) {
    // Find first long string value by length (domain-agnostic), skip vectors
    for (const [k, v] of Object.entries(source)) {
      if (_HIDDEN_FIELDS.has(k)) continue;
      if (typeof v === 'string' && v.length > 60) return v.slice(0, 220) + (v.length > 220 ? '…' : '');
    }
    return '';
  }

  function cardSourceUrl(source) {
    // Extract URL from any nested object that has a 'source' or 'url' string field
    for (const v of Object.values(source)) {
      if (v && typeof v === 'object' && !Array.isArray(v)) {
        const url = v['source'] || v['url'] || v['link'] || v['href'];
        if (typeof url === 'string' && url.startsWith('http')) return url;
      }
    }
    // Also check top-level fields directly
    for (const k of ['source', 'url', 'link', 'href']) {
      const v = source[k];
      if (typeof v === 'string' && v.startsWith('http')) return v;
    }
    return null;
  }

  function renderJsonHighlight(source) {
    // Pretty-print JSON with excluded fields, with simple syntax highlighting
    const filtered = Object.fromEntries(
      Object.entries(source).filter(([k]) => !_HIDDEN_FIELDS.has(k))
    );
    const raw = JSON.stringify(filtered, null, 2);
    // Highlight: keys, strings, numbers, booleans, null
    return raw
      .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
      .replace(/("[\w\s\-:./@]+")\s*:/g, '<span class="jk">$1</span>:')
      .replace(/:\s*("(?:[^"\\]|\\.)*")/g, ': <span class="js">$1</span>')
      .replace(/:\s*(-?\d+\.?\d*(?:[eE][+-]?\d+)?)/g, ': <span class="jn">$1</span>')
      .replace(/:\s*(true|false)/g, ': <span class="jb">$1</span>')
      .replace(/:\s*(null)/g, ': <span class="jnull">$1</span>');
  }

  function esc(s) {
    return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  // ─── Score breakdown renderer ─────────────────────────────────────────────
  function renderBreakdown(bd, mode) {
    if (!bd) return '';
    if (mode === 'rrf') {
      return `<div class="breakdown">
        <div class="breakdown-title">RRF Breakdown</div>
        <div class="rrf-grid">
          <div class="rrf-cell">BM25 rank: <strong>#${bd.bm25_rank ?? '—'}</strong></div>
          <div class="rrf-cell">KNN rank: <strong>#${bd.knn_rank ?? '—'}</strong></div>
          <div class="rrf-cell">RRF(bm25): <strong>${bd.rrf_bm25?.toFixed(5) ?? '—'}</strong></div>
          <div class="rrf-cell">RRF(knn): <strong>${bd.rrf_knn?.toFixed(5) ?? '—'}</strong></div>
        </div>
      </div>`;
    }

    // Hybrid breakdown with bars
    const bm25n = bd.bm25_normalized ?? 0;
    const knnn  = bd.knn_normalized  ?? bd.knn_cosine ?? 0;
    const comb  = (bd.bm25_contribution ?? 0) + (bd.knn_contribution ?? 0);

    return `<div class="breakdown">
      <div class="breakdown-title">Score Breakdown (explain)</div>
      <div class="breakdown-bars">
        <div class="bk-row">
          <div class="bk-label">BM25 raw → norm</div>
          <div class="bk-bar-wrap"><div class="bk-bar bk-bm25" style="width:${bm25n*100}%"></div></div>
          <div class="bk-val">${bm25n.toFixed(3)}</div>
        </div>
        <div class="bk-row">
          <div class="bk-label">KNN cosine → norm</div>
          <div class="bk-bar-wrap"><div class="bk-bar bk-knn" style="width:${knnn*100}%"></div></div>
          <div class="bk-val">${knnn.toFixed(3)}</div>
        </div>
        <div class="bk-row">
          <div class="bk-label">Combined score</div>
          <div class="bk-bar-wrap"><div class="bk-bar bk-combined" style="width:${comb*100}%"></div></div>
          <div class="bk-val">${comb.toFixed(3)}</div>
        </div>
      </div>
    </div>`;
  }

  // ─── Card renderer ────────────────────────────────────────────────────────
  function renderCard(hit, explain, mode, relevantIdxSet, position) {
    const s   = hit.source;
    const sc  = hit.score;
    const key = String(hit.index ?? '');
    const cid = 'card-' + hit.id;

    const isRelevant = relevantIdxSet && relevantIdxSet.has(position);
    const isMarked   = markedIds.has(hit.id);

    const snippet  = cardSnippet(s);
    const sourceUrl = cardSourceUrl(s);
    const jsonHtml = renderJsonHighlight(s);

    const scoreBadge = sc > 1
      ? `<span class="score-badge">${sc.toFixed(2)}</span>`
      : `<span class="score-badge">${sc.toFixed(4)}</span>`;

    const breakdownHtml = (explain && hit.score_breakdown) ? renderBreakdown(hit.score_breakdown, mode) : '';
    const relevantBadge = isRelevant ? `<div class="rank-badge">#${position + 1}</div>` : '';

    const sourceHtml = sourceUrl
      ? `<span class="card-source-url">${esc(sourceUrl)}</span>`
      : '';

    return `
      <div class="card ${isRelevant ? 'relevant' : ''} ${isMarked ? 'marked' : ''}" data-id="${hit.id}" id="${cid}">
        ${relevantBadge}
        <div class="card-header" onclick="toggleCard('${cid}', event)">
          <span class="card-arrow">▸</span>
          <span class="index-tag ${indexColorClass(key)}">${esc(key || '—')}</span>
          <div class="card-header-mid">
            ${sourceHtml}
            ${snippet ? `<span class="card-snippet">${esc(snippet)}</span>` : ''}
          </div>
          <input type="checkbox" class="card-checkbox" ${isMarked ? 'checked' : ''}
            onchange="onCardCheck('${hit.id}', this.checked)" />
          ${scoreBadge}
        </div>
        <div class="card-body">
          <pre class="card-json">${jsonHtml}</pre>
          ${breakdownHtml}
        </div>
      </div>`;
  }

  function renderResults(hits, explain, mode, relevantIdxSet) {
    const container = document.getElementById('results');
    container.className = evalMode ? 'eval-mode' : '';
    if (!hits.length) {
      container.innerHTML = `<div class="empty"><div class="icon">🔍</div>No results found.</div>`;
      return;
    }
    resetIndexColors();
    container.innerHTML = hits.map((h, i) => renderCard(h, explain, mode, relevantIdxSet, i)).join('');
  }

  // ════════════════════════════ EXPERIMENTS ════════════════════════════════

  // ─── State ───────────────────────────────────────────────────────────────
  let algorithms = [];
  let templates  = [];
  let runs       = [];
  let activeRun  = null;
  let selectedAlgoIds = new Set();
  let selectedTmplIds = new Set();
  let relIds = [];          // working list for template form
  let currentExpTab = 'algorithms';

  // Settings (connection profiles) — declared before showPane()
  let profiles = [];
  let editingProfileId = null;

  // ─── Pane switcher ───────────────────────────────────────────────────────
  function showPane(name) {
    document.getElementById('searchPane').style.display =
      name === 'search' ? 'block' : 'none';
    document.getElementById('experimentsPane').classList.toggle('visible', name === 'experiments');
    document.getElementById('settingsPane').classList.toggle('visible', name === 'settings');
    document.querySelectorAll('.tab-nav button').forEach(b =>
      b.classList.toggle('active', b.dataset.pane === name)
    );
    if (name !== 'settings') {
      const pp = document.getElementById('profileCreatePanel');
      if (pp) pp.classList.add('profile-panel-hidden');
      editingProfileId = null;
    }
    if (name === 'experiments') refreshExpData();
    if (name === 'settings') loadProfiles();
  }

  // ─── Sub-tab switcher ────────────────────────────────────────────────────
  function showExpTab(tab) {
    currentExpTab = tab;
    document.querySelectorAll('.sub-tab-btn').forEach((b, i) => {
      const tabs = ['algorithms', 'templates', 'benchmark'];
      b.classList.toggle('active', tabs[i] === tab);
    });
    ['algorithms', 'templates', 'benchmark'].forEach(t => {
      document.getElementById('expTab' + cap(t)).classList.toggle('visible', t === tab);
      const side = document.getElementById('expSide' + cap(t));
      if (side) side.style.display = t === tab ? 'block' : 'none';
    });
  }
  function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

  // ─── Utility ─────────────────────────────────────────────────────────────
  function expSetLoading(on) { document.getElementById('expSpinner').classList.toggle('active', on); }
  function expSetError(msg) {
    const el = document.getElementById('expError');
    el.classList.toggle('visible', !!msg);
    el.textContent = msg || '';
  }
  async function apiFetch(url, opts = {}) {
    const r = await fetch(url, { headers: {'Content-Type': 'application/json'}, ...opts });
    if (!r.ok) { const e = await r.json().catch(() => ({detail: r.statusText})); throw new Error(e.detail || r.statusText); }
    if (r.status === 204) return null;
    return r.json();
  }

  async function refreshActiveProfileIndices() {
    try {
      const list = await apiFetch('/api/v1/profiles');
      const profilesList = Array.isArray(list) ? list : [];
      const active = profilesList.find(p => p.is_active === true);
      const indicesObj =
        active && active.indices && active.indices.indices
          ? active.indices.indices
          : {};
      activeIndicesMap = indicesObj;
      reUpdateIndexOptions();
      const rawKeys = Object.keys(indicesObj);
      const ordered = orderLogicalIndexKeys(rawKeys);
      const indexGroup = document.getElementById('indexGroup');
      if (indexGroup) renderCollectionButtons(ordered, indexGroup);
      const tmplSel = document.getElementById('tmplIndex');
      if (tmplSel) populateExperimentIndexSelects(ordered, tmplSel);
      // reset selection: keep valid keys, fall back to 'all'
      const validSelected = [...selectedIndices].filter(k => k === 'all' || ordered.includes(k));
      selectedIndices = validSelected.length ? new Set(validSelected) : new Set(['all']);
      _syncIndexButtons();
      // Update header tagline with active profile name and index keys
      const tagline = document.getElementById('headerTagline');
      if (tagline) {
        const indexKeys = ordered.filter(k => k !== 'all');
        const profileLabel = active ? esc(active.name) : '';
        tagline.innerHTML = profileLabel
          ? `${profileLabel} &nbsp;·&nbsp; ${indexKeys.join(' · ')}`
          : (indexKeys.length ? indexKeys.join(' · ') : 'no active profile');
      }
    } catch (_) {
      /* profiles may be unavailable */
    }
  }

  // ─── Refresh all data ────────────────────────────────────────────────────
  async function refreshExpData() {
    try {
      expSetLoading(true);
      [algorithms, templates, runs] = await Promise.all([
        apiFetch('/api/v1/experiments/algorithms'),
        apiFetch('/api/v1/experiments/templates'),
        apiFetch('/api/v1/experiments/benchmark'),
      ]);
      renderAlgorithms();
      renderTemplates();
      renderRunList();
      if (activeRun) {
        const full = await apiFetch(`/api/v1/experiments/benchmark/${activeRun.id}`).catch(() => null);
        if (full) { activeRun = full; renderBenchTable(); }
      }
    } catch(e) { expSetError(e.message); }
    finally   { expSetLoading(false); }
  }

  // ─── Algorithms ──────────────────────────────────────────────────────────
  function renderAlgorithms() {
    const el = document.getElementById('algoList');
    if (!algorithms.length) { el.innerHTML = '<div class="exp-empty">No algorithms yet.</div>'; return; }
    el.innerHTML = '<div class="entity-list">' + algorithms.map(a => `
      <div class="entity-card ${selectedAlgoIds.has(a.id) ? 'selected' : ''}" id="algo-${a.id}">
        <input type="checkbox" class="entity-checkbox"
          ${selectedAlgoIds.has(a.id) ? 'checked' : ''}
          onchange="toggleAlgoSel('${a.id}', this.checked)" />
        <div class="entity-info">
          <div class="entity-name">${esc(a.name)}</div>
          <div class="entity-meta">
            <span class="e-chip">${a.mode}</span>
            ${a.mode==='hybrid' ? `<span class="e-chip">BM25 ${a.bm25_weight} / KNN ${a.knn_weight}</span>` : ''}
            <span class="e-chip">k=${a.num_candidates}</span>
            ${a.description ? `<span style="color:var(--muted)">${esc(a.description)}</span>` : ''}
          </div>
        </div>
        <div class="entity-actions">
          <button class="btn btn-danger btn-sm" onclick="deleteAlgorithm('${a.id}')">✕</button>
        </div>
      </div>`).join('') + '</div>';
  }

  function toggleAlgoSel(id, checked) {
    if (checked) selectedAlgoIds.add(id);
    else         selectedAlgoIds.delete(id);
    document.getElementById('algo-' + id)?.classList.toggle('selected', checked);
  }

  function onAlgoModeChange() {
    const mode = document.getElementById('algoMode').value;
    const weightsRow = document.getElementById('algoWeightsRow');
    const candsRow   = document.getElementById('algoCandsRow');
    if (weightsRow) weightsRow.style.display = mode === 'hybrid' ? '' : 'none';
    if (candsRow)   candsRow.style.display   = (mode === 'hybrid' || mode === 'rrf') ? '' : 'none';
  }

  async function createAlgorithm() {
    const name = document.getElementById('algoName').value.trim();
    if (!name) { expSetError('Algorithm name is required.'); return; }
    expSetError(null);
    try {
      expSetLoading(true);
      const body = {
        name,
        description: document.getElementById('algoDesc').value.trim(),
        mode:         document.getElementById('algoMode').value,
        bm25_weight:  parseFloat(document.getElementById('algoBm25').value),
        knn_weight:   parseFloat(document.getElementById('algoKnn').value),
        num_candidates: parseInt(document.getElementById('algoCands').value),
        filters:      {},
      };
      const algo = await apiFetch('/api/v1/experiments/algorithms', { method: 'POST', body: JSON.stringify(body) });
      algorithms.unshift(algo);
      document.getElementById('algoName').value = '';
      document.getElementById('algoDesc').value = '';
      renderAlgorithms();
    } catch(e) { expSetError(e.message); }
    finally    { expSetLoading(false); }
  }

  async function deleteAlgorithm(id) {
    if (!confirm('Delete this algorithm?')) return;
    try {
      await apiFetch(`/api/v1/experiments/algorithms/${id}`, { method: 'DELETE' });
      algorithms = algorithms.filter(a => a.id !== id);
      selectedAlgoIds.delete(id);
      renderAlgorithms();
    } catch(e) { expSetError(e.message); }
  }

  // ─── Templates ───────────────────────────────────────────────────────────
  function renderTemplates() {
    const el = document.getElementById('tmplList');
    if (!templates.length) { el.innerHTML = '<div class="exp-empty">No templates yet.</div>'; return; }
    el.innerHTML = '<div class="entity-list">' + templates.map(t => `
      <div class="entity-card ${selectedTmplIds.has(t.id) ? 'selected' : ''}" id="tmpl-${t.id}">
        <input type="checkbox" class="entity-checkbox"
          ${selectedTmplIds.has(t.id) ? 'checked' : ''}
          onchange="toggleTmplSel('${t.id}', this.checked)" />
        <div class="entity-info">
          <div class="entity-name">${esc(t.name)}</div>
          <div class="entity-meta">
            <span class="e-chip">"${esc(t.query)}"</span>
            <span class="e-chip">${t.index}</span>
            <span class="e-chip">${t.relevant_ids.length} relevant</span>
            ${t.notes ? `<span style="color:var(--muted)">${esc(t.notes)}</span>` : ''}
          </div>
        </div>
        <div class="entity-actions">
          <button class="btn btn-danger btn-sm" onclick="deleteTemplate('${t.id}')">✕</button>
        </div>
      </div>`).join('') + '</div>';
  }

  function toggleTmplSel(id, checked) {
    if (checked) selectedTmplIds.add(id);
    else         selectedTmplIds.delete(id);
    document.getElementById('tmpl-' + id)?.classList.toggle('selected', checked);
  }

  // ─── Relevant IDs editor ─────────────────────────────────────────────────
  function renderRelIds() {
    const box = document.getElementById('relIdsBox');
    const inp = document.getElementById('relIdsInput');
    box.querySelectorAll('.rel-id-chip').forEach(c => c.remove());
    relIds.forEach((id, i) => {
      const chip = document.createElement('span');
      chip.className = 'rel-id-chip';
      chip.innerHTML = `${esc(id.slice(0, 8))}… <button onclick="removeRelId(${i})">×</button>`;
      box.insertBefore(chip, inp);
    });
  }
  function removeRelId(i) { relIds.splice(i, 1); renderRelIds(); }
  function onRelIdKey(e) {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      const val = e.target.value.trim().replace(/,/g, '');
      if (val && !relIds.includes(val)) { relIds.push(val); renderRelIds(); }
      e.target.value = '';
    }
  }
  function importMarkedIds() {
    markedIds.forEach(id => { if (!relIds.includes(id)) relIds.push(id); });
    renderRelIds();
    expSetError(null);
  }

  async function createTemplate() {
    const name  = document.getElementById('tmplName').value.trim();
    const query = document.getElementById('tmplQuery').value.trim();
    if (!name || !query) { expSetError('Name and query are required.'); return; }
    // also grab any text still in the input
    const inp = document.getElementById('relIdsInput').value.trim();
    if (inp) { relIds.push(inp); document.getElementById('relIdsInput').value = ''; }
    expSetError(null);
    try {
      expSetLoading(true);
      const body = {
        name, query,
        index:        getTmplIndexValue(),
        relevant_ids: [...relIds],
        notes:        document.getElementById('tmplNotes').value.trim(),
      };
      const tmpl = await apiFetch('/api/v1/experiments/templates', { method: 'POST', body: JSON.stringify(body) });
      templates.unshift(tmpl);
      document.getElementById('tmplName').value  = '';
      document.getElementById('tmplQuery').value = '';
      document.getElementById('tmplNotes').value = '';
      relIds = [];
      renderRelIds();
      renderTemplates();
    } catch(e) { expSetError(e.message); }
    finally    { expSetLoading(false); }
  }

  async function deleteTemplate(id) {
    if (!confirm('Delete this template?')) return;
    try {
      await apiFetch(`/api/v1/experiments/templates/${id}`, { method: 'DELETE' });
      templates = templates.filter(t => t.id !== id);
      selectedTmplIds.delete(id);
      renderTemplates();
    } catch(e) { expSetError(e.message); }
  }

  // ─── Save as Template from Search tab ────────────────────────────────────
  async function saveAsTemplate() {
    if (markedIds.size === 0) return;
    const q = document.getElementById('q').value.trim();
    const name = prompt('Template name:', q ? `"${q}"` : 'My template');
    if (!name) return;
    try {
      const body = {
        name,
        query: q || name,
        index: getEffectiveIndex(),
        relevant_ids: [...markedIds],
        notes: 'Saved from Search tab',
      };
      await apiFetch('/api/v1/experiments/templates', { method: 'POST', body: JSON.stringify(body) });
      alert(`Template "${name}" saved with ${markedIds.size} relevant IDs.`);
    } catch(e) { alert('Error: ' + e.message); }
  }

  // ─── Benchmark ───────────────────────────────────────────────────────────
  async function runBenchmark() {
    if (selectedAlgoIds.size === 0) { expSetError('Select at least one algorithm.'); return; }
    if (selectedTmplIds.size === 0) { expSetError('Select at least one template.'); return; }
    expSetError(null);
    expSetLoading(true);
    try {
      const k    = parseInt(document.getElementById('benchK').value) || 10;
      const size = parseInt(document.getElementById('benchSize').value) || 10;
      const body = {
        name:          document.getElementById('benchName').value.trim(),
        algorithm_ids: [...selectedAlgoIds],
        template_ids:  [...selectedTmplIds],
        k,
        size:          Math.max(size, k),
      };
      const run = await apiFetch('/api/v1/experiments/benchmark', { method: 'POST', body: JSON.stringify(body) });
      runs.unshift(run);
      activeRun = run;
      renderRunList();
      await loadRunDetail(run.id);
    } catch(e) { expSetError(e.message); }
    finally    { expSetLoading(false); }
  }

  async function loadRunDetail(id) {
    try {
      expSetLoading(true);
      activeRun = await apiFetch(`/api/v1/experiments/benchmark/${id}`);
      renderBenchTable();
      showExpTab('benchmark');
    } catch(e) { expSetError(e.message); }
    finally    { expSetLoading(false); }
  }

  async function deleteRun(id) {
    if (!confirm('Delete this benchmark run?')) return;
    try {
      await apiFetch(`/api/v1/experiments/benchmark/${id}`, { method: 'DELETE' });
      runs = runs.filter(r => r.id !== id);
      if (activeRun?.id === id) { activeRun = null; document.getElementById('benchTable').innerHTML = '<div class="exp-empty">Run a benchmark to see results here.</div>'; }
      renderRunList();
    } catch(e) { expSetError(e.message); }
  }

  function renderRunList() {
    const el = document.getElementById('runList');
    if (!runs.length) { el.innerHTML = ''; return; }
    el.innerHTML = `<div class="section-title" style="margin-bottom:8px;">Past Runs</div>` +
      runs.map(r => `
        <div class="run-item ${activeRun?.id === r.id ? 'active-run' : ''}" onclick="loadRunDetail('${r.id}')">
          <div class="run-info">
            <div class="run-name">${esc(r.name || 'Untitled run')}</div>
            <div class="run-meta">${r.algorithm_ids.length} algos × ${r.template_ids.length} templates · size=${r.size ?? r.k} @K=${r.k} · ${new Date(r.created_at).toLocaleString()}</div>
          </div>
          <button class="btn btn-danger btn-sm" onclick="event.stopPropagation();deleteRun('${r.id}')">✕</button>
        </div>`).join('');
  }

  // ─── Benchmark table renderer ─────────────────────────────────────────────
  function renderBenchTable() {
    if (!activeRun) return;
    const run = activeRun;

    const METRICS = [
      { key: 'avg_ndcg_at_k',        label: 'NDCG@K',      isLatency: false, tooltip: 'Normalized Discounted Cumulative Gain\nMeasures ranking quality — relevant docs ranked higher contribute more (log₂ position discount).\nRange: 0–1, higher is better.' },
      { key: 'avg_mrr',              label: 'MRR',          isLatency: false, tooltip: 'Mean Reciprocal Rank\nReciprocal of the position of the first relevant document.\nExample: first relevant at position 3 → score = 1/3.\nRange: 0–1, higher is better.' },
      { key: 'avg_precision_at_k',   label: 'Precision@K',  isLatency: false, tooltip: 'Precision@K\nFraction of relevant docs among the top K results.\nExample: 3 relevant out of 10 → P@10 = 0.30.\nRange: 0–1, higher is better.' },
      { key: 'avg_recall_at_k',      label: 'Recall@K',     isLatency: false, tooltip: 'Recall@K\nFraction of known relevant docs found in top K.\nExample: 3 found out of 5 known → Recall = 0.60.\nRange: 0–1, higher is better.' },
      { key: 'avg_score_separation', label: 'Sep',          isLatency: false, tooltip: 'Score Separation = rel_mean − non_rel_mean\nPositive: relevant docs score higher than non-relevant ✓\nNegative: non-relevant docs outscore relevant ones ✗\nHigher is better; negative = ranking is inverted.' },
      { key: 'avg_latency_ms',       label: 'Latency',      isLatency: true,  tooltip: 'Latency (ms)\nAverage query execution time in milliseconds.\nLower is better.' },
      { key: 'avg_score_mean',       label: 'Score Mean',   isLatency: false, tooltip: 'Score Mean\nMean score across all returned documents.\nIndicates the algorithm\'s overall confidence in its results.' },
    ];

    const algoIds = run.algorithm_ids || [];
    const algoMap = {};
    algorithms.forEach(a => { algoMap[a.id] = a; });

    // Pre-compute per-column best/worst values
    const colBest = {};
    const colWorst = {};
    METRICS.forEach(m => {
      const vals = algoIds
        .map(aid => run.summary?.[aid]?.[m.key])
        .filter(v => v !== null && v !== undefined);
      if (vals.length === 0) return;
      if (m.isLatency) {
        colBest[m.key]  = Math.min(...vals);
        colWorst[m.key] = Math.max(...vals);
      } else {
        colBest[m.key]  = Math.max(...vals);
        colWorst[m.key] = Math.min(...vals);
      }
    });

    const thead = `<tr><th>Algorithm</th>${METRICS.map(m => `<th data-tooltip="${esc(m.tooltip)}">${esc(m.label)}</th>`).join('')}</tr>`;

    const rows = algoIds.map(aid => {
      const a = algoMap[aid];
      const cells = METRICS.map(m => {
        const val = run.summary?.[aid]?.[m.key];
        if (val === null || val === undefined) return '<td>—</td>';
        const fmt = m.isLatency ? val.toFixed(0) + 'ms' : val.toFixed(4);
        const isBest  = colBest[m.key]  !== undefined && val === colBest[m.key];
        const isWorst = colWorst[m.key] !== undefined && val === colWorst[m.key];
        const cls = isBest ? 'cell-best' : isWorst ? 'cell-worst' : '';
        return `<td><div class="cell-val ${cls}">${fmt}</div></td>`;
      }).join('');
      return `<tr>
      <td class="cell-algo" title="${esc(a?.name || aid)}">${esc((a?.name || aid).slice(0, 28))}</td>
      ${cells}
    </tr>`;
    }).join('');

    document.getElementById('benchTable').innerHTML = `
    <div style="margin-bottom:10px;font-size:.8rem;color:var(--muted);">
      <strong style="color:var(--text)">${esc(run.name || 'Untitled run')}</strong>
      &nbsp;·&nbsp; size=${run.size ?? run.k} @K=${run.k}
      &nbsp;·&nbsp; <span style="color:var(--green)">green</span> = best
      &nbsp;·&nbsp; <span style="color:var(--red)">red</span> = worst
      &nbsp;·&nbsp; Latency: lower is better
    </div>
    <div class="bench-table-wrap">
      <table class="bench-table">
        <thead>${thead}</thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;

    renderRunList();
  }

  // ════════════════════════════ PROFILES (SETTINGS) ════════════════════════════════

  let _indexRowCounter = 0;

  function _indicesContainerId(prefix) {
    return prefix === 'pc' ? 'pc_indices_list' : `pe_${prefix}_indices_list`;
  }

  function addIndexRow(prefix, key = '', indexName = '', bm25 = '') {
    const container = document.getElementById(_indicesContainerId(prefix));
    if (!container) return;
    const rowId = 'idx_row_' + (++_indexRowCounter);
    const row = document.createElement('div');
    row.className = 'index-row';
    row.id = rowId;
    const keyIn = document.createElement('input');
    keyIn.className = 'form-input idx-key';
    keyIn.placeholder = 'e.g. docs';
    keyIn.value = key;
    const nameIn = document.createElement('input');
    nameIn.className = 'form-input idx-name';
    nameIn.placeholder = 'physical_index_v1';
    nameIn.value = indexName;
    const bm25In = document.createElement('input');
    bm25In.className = 'form-input idx-bm25';
    bm25In.placeholder = 'title, body (optional)';
    bm25In.value = bm25;
    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'btn btn-danger btn-sm';
    removeBtn.textContent = '✕';
    removeBtn.onclick = () => row.remove();
    row.appendChild(keyIn);
    row.appendChild(nameIn);
    row.appendChild(bm25In);
    row.appendChild(removeBtn);
    container.appendChild(row);
  }

  function populateEditIndices(profileId) {
    const p = profiles.find(x => x.id === profileId);
    if (!p) return;
    const container = document.getElementById(_indicesContainerId(profileId));
    if (!container) return;
    container.innerHTML = '';
    const indicesMap = (p.indices && p.indices.indices) || {};
    const bm25Map = (p.indices && p.indices.bm25_fields) || {};
    const keys = Object.keys(indicesMap).filter(k => k !== 'all');
    if (keys.length === 0) {
      addIndexRow(profileId);
    } else {
      keys.forEach(k => {
        const bm25Val = (bm25Map[k] || []).join(', ');
        addIndexRow(profileId, k, indicesMap[k], bm25Val);
      });
    }
  }

  function profileEditFieldId(profileId, key) {
    return 'pe_' + profileId + '_' + key;
  }

  function profileSetLoading(on) {
    document.getElementById('profileSpinner').classList.toggle('active', on);
  }

  function profileSetError(msg) {
    const el = document.getElementById('profileError');
    el.classList.toggle('visible', !!msg);
    el.textContent = msg || '';
  }

  function toggleProfileCreatePanel() {
    const p = document.getElementById('profileCreatePanel');
    const hidden = p.classList.toggle('profile-panel-hidden');
    if (!hidden) {
      resetProfileCreateForm();
      editingProfileId = null;
      renderProfiles();
    }
  }

  function hideProfileCreatePanel() {
    document.getElementById('profileCreatePanel').classList.add('profile-panel-hidden');
  }

  function resetProfileCreateForm() {
    document.getElementById('pc_name').value = '';
    document.getElementById('pc_host').value = 'localhost';
    document.getElementById('pc_port').value = '9200';
    document.getElementById('pc_use_ssl').checked = false;
    document.getElementById('pc_auth_type').value = 'none';
    document.getElementById('pc_username').value = '';
    document.getElementById('pc_password').value = '';
    document.getElementById('pc_aws_region').value = '';
    document.getElementById('pc_aws_access_key_id').value = '';
    document.getElementById('pc_aws_secret_access_key').value = '';
    document.getElementById('pc_embed_provider').value = 'local_sentence_transformers';
    document.getElementById('pc_model_name').value = 'all-MiniLM-L6-v2';
    document.getElementById('pc_bedrock_model_name').value = '';
    document.getElementById('pc_embed_aws_region').value = '';
    document.getElementById('pc_embed_aws_access_key_id').value = '';
    document.getElementById('pc_embed_aws_secret_access_key').value = '';
    const idxList = document.getElementById('pc_indices_list');
    if (idxList) { idxList.innerHTML = ''; addIndexRow('pc'); }
    syncProfileAuthVisibility('pc');
    syncProfileEmbedVisibility('pc');
  }

  /** prefix: "pc" (create) or profile id string for edit fields pe_{id}_* */
  function syncProfileAuthVisibility(prefix) {
    const isCreate = prefix === 'pc';
    const selId = isCreate ? 'pc_auth_type' : profileEditFieldId(prefix, 'auth_type');
    const auth = (document.getElementById(selId) || {}).value || 'none';
    const basicEl = document.getElementById(isCreate ? 'pc_auth_basic' : 'pe_' + prefix + '_auth_basic');
    const awsEl = document.getElementById(isCreate ? 'pc_auth_aws' : 'pe_' + prefix + '_auth_aws');
    if (basicEl) {
      basicEl.classList.toggle('visible', auth === 'basic');
    }
    if (awsEl) {
      awsEl.classList.toggle('visible', auth === 'aws_signature_v4');
    }
  }

  function syncProfileEmbedVisibility(prefix) {
    const isCreate = prefix === 'pc';
    const selId = isCreate ? 'pc_embed_provider' : profileEditFieldId(prefix, 'embed_provider');
    const prov = (document.getElementById(selId) || {}).value || 'local_sentence_transformers';
    const localEl = document.getElementById(isCreate ? 'pc_embed_local' : 'pe_' + prefix + '_embed_local');
    const bedEl = document.getElementById(isCreate ? 'pc_embed_bedrock' : 'pe_' + prefix + '_embed_bedrock');
    if (localEl) {
      localEl.classList.toggle('visible', prov === 'local_sentence_transformers');
    }
    if (bedEl) {
      bedEl.classList.toggle('visible', prov === 'aws_bedrock');
    }
  }

  function buildOpenSearchBody(prefix) {
    const gid = id => {
      const el = document.getElementById(id);
      return el ? el.value.trim() : '';
    };
    const gc = id => {
      const el = document.getElementById(id);
      return el ? el.checked : false;
    };
    const auth = gid(prefix === 'pc' ? 'pc_auth_type' : profileEditFieldId(prefix, 'auth_type')) || 'none';
    const host = gid(prefix === 'pc' ? 'pc_host' : profileEditFieldId(prefix, 'host')) || 'localhost';
    const portRaw = gid(prefix === 'pc' ? 'pc_port' : profileEditFieldId(prefix, 'port'));
    const port = Math.min(65535, Math.max(1, parseInt(portRaw || '9200', 10) || 9200));
    const base = {
      host,
      port,
      use_ssl: gc(prefix === 'pc' ? 'pc_use_ssl' : profileEditFieldId(prefix, 'use_ssl')),
      auth_type: auth,
      username: null,
      password: null,
      aws_region: null,
      aws_access_key_id: null,
      aws_secret_access_key: null,
    };
    if (auth === 'basic') {
      base.username = gid(prefix === 'pc' ? 'pc_username' : profileEditFieldId(prefix, 'username')) || null;
      base.password = gid(prefix === 'pc' ? 'pc_password' : profileEditFieldId(prefix, 'password')) || null;
    }
    if (auth === 'aws_signature_v4') {
      base.aws_region = gid(prefix === 'pc' ? 'pc_aws_region' : profileEditFieldId(prefix, 'aws_region')) || null;
      base.aws_access_key_id =
        gid(prefix === 'pc' ? 'pc_aws_access_key_id' : profileEditFieldId(prefix, 'aws_access_key_id')) || null;
      base.aws_secret_access_key =
        gid(prefix === 'pc' ? 'pc_aws_secret_access_key' : profileEditFieldId(prefix, 'aws_secret_access_key')) ||
        null;
    }
    return base;
  }

  function buildEmbeddingBody(prefix) {
    const gid = id => {
      const el = document.getElementById(id);
      return el ? el.value.trim() : '';
    };
    const prov =
      gid(prefix === 'pc' ? 'pc_embed_provider' : profileEditFieldId(prefix, 'embed_provider')) ||
      'local_sentence_transformers';
    const emb = {
      provider: prov,
      model_name: 'all-MiniLM-L6-v2',
      aws_region: null,
      aws_access_key_id: null,
      aws_secret_access_key: null,
    };
    if (prov === 'local_sentence_transformers') {
      emb.model_name =
        gid(prefix === 'pc' ? 'pc_model_name' : profileEditFieldId(prefix, 'model_name')) ||
        'all-MiniLM-L6-v2';
    } else {
      emb.model_name =
        gid(prefix === 'pc' ? 'pc_bedrock_model_name' : profileEditFieldId(prefix, 'bedrock_model_name')) || '';
      emb.aws_region =
        gid(prefix === 'pc' ? 'pc_embed_aws_region' : profileEditFieldId(prefix, 'embed_aws_region')) || null;
      emb.aws_access_key_id =
        gid(prefix === 'pc' ? 'pc_embed_aws_access_key_id' : profileEditFieldId(prefix, 'embed_aws_access_key_id')) ||
        null;
      emb.aws_secret_access_key =
        gid(prefix === 'pc' ? 'pc_embed_aws_secret_access_key' : profileEditFieldId(prefix, 'embed_aws_secret_access_key')) ||
        null;
    }
    return emb;
  }

  function buildIndicesBody(prefix) {
    const container = document.getElementById(_indicesContainerId(prefix));
    const indices = {};
    const bm25_fields = {};
    if (container) {
      container.querySelectorAll('.index-row').forEach(row => {
        const key = (row.querySelector('.idx-key')?.value || '').trim();
        const name = (row.querySelector('.idx-name')?.value || '').trim();
        const bm25Raw = (row.querySelector('.idx-bm25')?.value || '').trim();
        if (key && name) {
          indices[key] = name;
          bm25_fields[key] = bm25Raw
            ? bm25Raw.split(',').map(s => s.trim()).filter(Boolean)
            : [];
        }
      });
    }
    return { indices, bm25_fields };
  }

  async function loadProfiles() {
    profileSetError(null);
    profileSetLoading(true);
    editingProfileId = null;
    try {
      profiles = await apiFetch('/api/v1/profiles');
      renderProfiles();
    } catch (e) {
      profileSetError(e.message);
      document.getElementById('profileList').innerHTML =
        '<div class="exp-empty">Could not load profiles.</div>';
    } finally {
      profileSetLoading(false);
    }
  }

  function startEditProfile(id) {
    editingProfileId = id;
    document.getElementById('profileCreatePanel').classList.add('profile-panel-hidden');
    renderProfiles();
    setTimeout(() => {
      syncProfileAuthVisibility(id);
      syncProfileEmbedVisibility(id);
      populateEditIndices(id);
    }, 0);
  }

  function cancelEditProfile() {
    editingProfileId = null;
    renderProfiles();
  }

  function renderProfileEditForm(p) {
    const pid = p.id;
    const os = p.opensearch || {};
    const emb = p.embedding || {};
    const idx = p.indices || {};
    const auth = os.auth_type || 'none';
    const prov = emb.provider || 'local_sentence_transformers';
    const id = x => profileEditFieldId(pid, x);
    const basicVis = auth === 'basic' ? ' visible' : '';
    const awsVis = auth === 'aws_signature_v4' ? ' visible' : '';
    const localVis = prov === 'local_sentence_transformers' ? ' visible' : '';
    const bedVis = prov === 'aws_bedrock' ? ' visible' : '';
    return `
      <div class="form-card" style="margin-bottom:10px;">
        <h3>Edit profile</h3>
        <div class="form-row"><label>Name *</label><input id="${id('name')}" class="form-input" value="${esc(p.name)}" /></div>
        <h3 style="margin-top:12px;">OpenSearch</h3>
        <div class="form-row-2">
          <div class="form-row" style="margin:0"><label>Host</label><input id="${id('host')}" class="form-input" value="${esc(os.host)}" /></div>
          <div class="form-row" style="margin:0"><label>Port</label><input id="${id('port')}" class="form-input" type="number" min="1" max="65535" value="${esc(os.port)}" /></div>
        </div>
        <div class="field-row" style="margin-top:6px;"><label>Use SSL</label><input type="checkbox" id="${id('use_ssl')}" ${os.use_ssl ? 'checked' : ''} /></div>
        <div class="form-row"><label>Auth type</label>
          <select id="${id('auth_type')}" class="form-input" onchange="syncProfileAuthVisibility('${pid}')">
            <option value="none" ${auth === 'none' ? 'selected' : ''}>none</option>
            <option value="basic" ${auth === 'basic' ? 'selected' : ''}>basic</option>
            <option value="aws_signature_v4" ${auth === 'aws_signature_v4' ? 'selected' : ''}>aws_signature_v4</option>
          </select>
        </div>
        <div id="pe_${pid}_auth_basic" class="profile-cond${basicVis}">
          <div class="form-row-2">
            <div class="form-row" style="margin:0"><label>Username</label><input id="${id('username')}" class="form-input" value="${esc(os.username)}" autocomplete="off" /></div>
            <div class="form-row" style="margin:0"><label>Password</label><input id="${id('password')}" class="form-input" type="password" placeholder="Required on save (not loaded from API)" autocomplete="new-password" /></div>
          </div>
        </div>
        <div id="pe_${pid}_auth_aws" class="profile-cond${awsVis}">
          <div class="form-row"><label>AWS Region</label><input id="${id('aws_region')}" class="form-input" value="${esc(os.aws_region)}" /></div>
          <div class="form-row-2">
            <div class="form-row" style="margin:0"><label>Access Key ID</label><input id="${id('aws_access_key_id')}" class="form-input" value="${esc(os.aws_access_key_id)}" autocomplete="off" /></div>
            <div class="form-row" style="margin:0"><label>Secret Access Key</label><input id="${id('aws_secret_access_key')}" class="form-input" type="password" placeholder="(unchanged if empty)" autocomplete="new-password" /></div>
          </div>
        </div>
        <h3 style="margin-top:12px;">Embedding</h3>
        <div class="form-row"><label>Provider</label>
          <select id="${id('embed_provider')}" class="form-input" onchange="syncProfileEmbedVisibility('${pid}')">
            <option value="local_sentence_transformers" ${prov === 'local_sentence_transformers' ? 'selected' : ''}>local_sentence_transformers</option>
            <option value="aws_bedrock" ${prov === 'aws_bedrock' ? 'selected' : ''}>aws_bedrock</option>
          </select>
        </div>
        <div id="pe_${pid}_embed_local" class="profile-cond${localVis}">
          <div class="form-row"><label>Model name</label><input id="${id('model_name')}" class="form-input" value="${esc(emb.model_name)}" /></div>
        </div>
        <div id="pe_${pid}_embed_bedrock" class="profile-cond${bedVis}">
          <div class="form-row"><label>Model name</label><input id="${id('bedrock_model_name')}" class="form-input" value="${prov === 'aws_bedrock' ? esc(emb.model_name) : ''}" /></div>
          <div class="form-row"><label>AWS Region</label><input id="${id('embed_aws_region')}" class="form-input" value="${esc(emb.aws_region)}" /></div>
          <div class="form-row-2">
            <div class="form-row" style="margin:0"><label>Access Key ID</label><input id="${id('embed_aws_access_key_id')}" class="form-input" value="${esc(emb.aws_access_key_id)}" autocomplete="off" /></div>
            <div class="form-row" style="margin:0"><label>Secret Access Key</label><input id="${id('embed_aws_secret_access_key')}" class="form-input" type="password" placeholder="(unchanged if empty)" autocomplete="new-password" /></div>
          </div>
        </div>
        <h3 style="margin-top:12px;">Indices</h3>
        <div class="indices-header"><span>Logical key</span><span>Physical index name</span><span>BM25 fields (comma-sep)</span><span></span></div>
        <div id="pe_${pid}_indices_list"></div>
        <button type="button" class="btn btn-ghost btn-sm" style="margin-bottom:8px;" onclick="addIndexRow('${pid}')">+ Add index</button>
        <div style="display:flex;gap:8px;margin-top:12px;">
          <button type="button" class="btn btn-primary" onclick="submitProfileUpdate('${pid}')">Save</button>
          <button type="button" class="btn btn-ghost" onclick="cancelEditProfile()">Cancel</button>
        </div>
      </div>`;
  }

  function renderProfiles() {
    const el = document.getElementById('profileList');
    if (!profiles.length) {
      el.innerHTML = '<div class="exp-empty">No profiles yet. Use Add Profile to create one.</div>';
      return;
    }
    el.innerHTML =
      '<div class="entity-list">' +
      profiles
        .map(p => {
          if (editingProfileId === p.id) {
            return renderProfileEditForm(p);
          }
          const os = p.opensearch || {};
          const emb = p.embedding || {};
          const active = !!p.is_active;
          const cardClass = 'entity-card' + (active ? ' profile-active' : '');
          const hostPort = esc(os.host) + ':' + esc(String(os.port ?? ''));
          const authLabel = esc(os.auth_type || 'none');
          const embedLabel = esc(emb.provider || '—');
          const activeBtn = active
            ? ''
            : `<button type="button" class="btn btn-green btn-sm" onclick="activateProfile('${p.id}')">Activate</button>`;
          const deleteBtn = active
            ? `<button type="button" class="btn btn-danger btn-sm" disabled title="Cannot delete active profile">✕</button>`
            : `<button type="button" class="btn btn-danger btn-sm" onclick="deleteProfile('${p.id}')">✕</button>`;
          const badge = active ? `<span class="profile-badge-active">Active</span>` : '';
          return `
      <div class="${cardClass}">
        <div class="entity-info">
          <div class="entity-name">${esc(p.name)} ${badge}</div>
          <div class="entity-meta">
            <span class="e-chip">${hostPort}</span>
            <span class="e-chip">auth: ${authLabel}</span>
            <span class="e-chip">${embedLabel}</span>
            <span class="e-chip">SSL: ${os.use_ssl ? 'on' : 'off'}</span>
          </div>
          <div class="profile-test-result" id="profile-test-${p.id}"></div>
        </div>
        <div class="entity-actions">
          ${activeBtn}
          <button type="button" class="btn btn-ghost btn-sm" onclick="testProfileConnection('${p.id}')">Test connection</button>
          <button type="button" class="btn btn-ghost btn-sm" onclick="startEditProfile('${p.id}')">Edit</button>
          ${deleteBtn}
        </div>
      </div>`;
        })
        .join('') +
      '</div>';
  }

  async function submitProfileCreate() {
    const name = document.getElementById('pc_name').value.trim();
    if (!name) {
      profileSetError('Profile name is required.');
      return;
    }
    const osPre = buildOpenSearchBody('pc');
    if (osPre.auth_type === 'basic' && (!osPre.username || !osPre.password)) {
      profileSetError('Basic auth requires username and password.');
      return;
    }
    const indicesBody = buildIndicesBody('pc');
    if (Object.keys(indicesBody.indices).length === 0) {
      profileSetError('At least one index is required.');
      return;
    }
    profileSetError(null);
    profileSetLoading(true);
    try {
      const body = {
        name,
        opensearch: osPre,
        embedding: buildEmbeddingBody('pc'),
        indices: indicesBody,
      };
      const created = await apiFetch('/api/v1/profiles', { method: 'POST', body: JSON.stringify(body) });
      profiles = profiles.filter(pr => pr.id !== created.id);
      profiles.unshift(created);
      hideProfileCreatePanel();
      resetProfileCreateForm();
      renderProfiles();
    } catch (e) {
      profileSetError(e.message);
    } finally {
      profileSetLoading(false);
    }
  }

  async function submitProfileUpdate(profileId) {
    const nameEl = document.getElementById(profileEditFieldId(profileId, 'name'));
    const name = (nameEl && nameEl.value.trim()) || '';
    if (!name) {
      profileSetError('Profile name is required.');
      return;
    }
    profileSetError(null);
    profileSetLoading(true);
    try {
      const os = buildOpenSearchBody(profileId);
      const emb = buildEmbeddingBody(profileId);
      if (os.auth_type === 'basic') {
        const pwdOs = document.getElementById(profileEditFieldId(profileId, 'password'));
        if (!pwdOs || !pwdOs.value.trim()) {
          profileSetError('Password is required to save basic auth (secrets are not returned by the API).');
          profileSetLoading(false);
          return;
        }
        os.password = pwdOs.value.trim();
      }
      const editIndices = buildIndicesBody(profileId);
      if (Object.keys(editIndices.indices).length === 0) {
        profileSetError('At least one index is required.');
        profileSetLoading(false);
        return;
      }
      const body = {
        name,
        opensearch: os,
        embedding: emb,
        indices: editIndices,
      };
      const updated = await apiFetch(`/api/v1/profiles/${profileId}`, {
        method: 'PUT',
        body: JSON.stringify(body),
      });
      profiles = profiles.map(pr => (pr.id === profileId ? updated : pr));
      editingProfileId = null;
      renderProfiles();
    } catch (e) {
      profileSetError(e.message);
    } finally {
      profileSetLoading(false);
    }
  }

  function formatProfileConnectionTest(data) {
    const fmt = (label, block) => {
      const st = block.ok ? 'OK' : 'FAIL';
      const lat = block.latency_ms != null ? ` ${Math.round(block.latency_ms)}ms` : '';
      const err = block.error ? ` — ${esc(block.error)}` : '';
      return `${esc(label)}: ${st}${lat}${err}`;
    };
    return `<span class="profile-test-line">${fmt('OpenSearch', data.opensearch)} &nbsp;·&nbsp; ${fmt('Embedding', data.embedding)}</span>`;
  }

  async function testProfileConnection(id) {
    profileSetError(null);
    const outEl = document.getElementById('profile-test-' + id);
    if (outEl) outEl.innerHTML = '<span style="color:var(--muted)">Testing…</span>';
    try {
      const res = await fetch(`/api/v1/profiles/${encodeURIComponent(id)}/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) {
        if (outEl) outEl.innerHTML = '';
        const d = payload.detail;
        let msg = res.statusText;
        if (typeof d === 'string') msg = d;
        else if (Array.isArray(d)) msg = d.map(x => (x && x.msg) ? x.msg : String(x)).join('; ');
        profileSetError(msg);
        return;
      }
      if (outEl) outEl.innerHTML = formatProfileConnectionTest(payload);
    } catch (e) {
      if (outEl) outEl.innerHTML = '';
      profileSetError(e.message || String(e));
    }
  }

  async function activateProfile(id) {
    profileSetError(null);
    profileSetLoading(true);
    try {
      await apiFetch(`/api/v1/profiles/${id}/activate`, { method: 'POST' });
      await loadProfiles();
      await refreshActiveProfileIndices();
    } catch (e) {
      profileSetError(e.message);
    } finally {
      profileSetLoading(false);
    }
  }

  async function deleteProfile(id) {
    const p = profiles.find(x => x.id === id);
    if (p && p.is_active) {
      profileSetError('Cannot delete the active profile.');
      return;
    }
    if (!confirm('Delete this profile?')) return;
    profileSetError(null);
    profileSetLoading(true);
    try {
      await apiFetch(`/api/v1/profiles/${id}`, { method: 'DELETE' });
      profiles = profiles.filter(pr => pr.id !== id);
      if (editingProfileId === id) editingProfileId = null;
      renderProfiles();
    } catch (e) {
      profileSetError(e.message);
    } finally {
      profileSetLoading(false);
    }
  }

  // ─── Global tooltip (fixed-position, bypasses overflow clipping) ─────────
  (function initTooltip() {
    const tip = document.createElement('div');
    tip.id = 'ui-tooltip';
    document.body.appendChild(tip);

    const GAP = 10;

    function show(el, text) {
      tip.textContent = text;
      tip.classList.add('visible');
      position(el);
    }

    function position(el) {
      const r = el.getBoundingClientRect();
      const tw = tip.offsetWidth;
      const th = tip.offsetHeight;
      const vw = window.innerWidth;
      const vh = window.innerHeight;

      // Prefer above, fall back to below
      let top = r.top - th - GAP;
      if (top < 6) top = r.bottom + GAP;

      // Center horizontally, clamp to viewport
      let left = r.left + r.width / 2 - tw / 2;
      left = Math.max(6, Math.min(left, vw - tw - 6));

      tip.style.top  = top + 'px';
      tip.style.left = left + 'px';
    }

    function hide() { tip.classList.remove('visible'); }

    document.addEventListener('mouseover', e => {
      const el = e.target.closest('[data-tooltip]');
      if (el) show(el, el.dataset.tooltip);
    });
    document.addEventListener('mouseout', e => {
      if (e.target.closest('[data-tooltip]')) hide();
    });
    document.addEventListener('scroll', hide, true);
  })();

  // ─── Rank Eval (native OpenSearch _rank_eval, BM25 only) ─────────────────

  function reUpdateIndexOptions() {
    const sel = document.getElementById('reIndex');
    if (!sel || !activeIndicesMap) return;
    const keys = Object.keys(activeIndicesMap).filter(k => k !== 'all');
    sel.innerHTML = keys.length
      ? keys.map(k => `<option value="${esc(k)}">${esc(k)}</option>`).join('')
      : '<option value="">— no indices —</option>';
  }

  function reUpdateUI() {
    document.getElementById('reQueryCount').textContent = rankEvalQueries.length;
    document.getElementById('reRunBtn').disabled = rankEvalQueries.length === 0;
    const list = document.getElementById('reQueryList');
    list.innerHTML = rankEvalQueries.map((q, i) => `
      <div class="re-query-item">
        <span class="re-qid">${esc(q.id)}</span>
        <span class="re-qtext">${esc(q.query)}</span>
        <span class="re-qcount">${q.ratings.length} doc${q.ratings.length !== 1 ? 's' : ''}</span>
        <button class="re-remove-btn" onclick="reRemoveQuery(${i})">×</button>
      </div>`).join('');
  }

  function reAddCurrentQuery() {
    const q = document.getElementById('q').value.trim();
    if (!q) { setError('Enter a search query first.'); return; }
    if (markedIds.size === 0) { setError('Enable Eval mode and mark at least one relevant document first.'); return; }
    const id = `q${rankEvalQueries.length + 1}`;
    rankEvalQueries.push({ id, query: q, ratings: [...markedIds].map(doc_id => ({ doc_id, rating: 1 })) });
    reUpdateUI();
  }

  function reRemoveQuery(idx) {
    rankEvalQueries.splice(idx, 1);
    rankEvalQueries.forEach((q, i) => { if (/^q\d+$/.test(q.id)) q.id = `q${i + 1}`; });
    reUpdateUI();
  }

  function reClearQueries() {
    rankEvalQueries = [];
    reUpdateUI();
    document.getElementById('rePanel').classList.remove('visible');
  }

  async function runRankEval() {
    if (rankEvalQueries.length === 0) return;
    const indexKey = document.getElementById('reIndex').value;
    if (!indexKey) { setError('Select a single index for Rank Eval.'); return; }
    setError(null);
    setLoading(true);
    const body = {
      queries: rankEvalQueries,
      index: indexKey,
      k: parseInt(document.getElementById('reK').value) || 10,
      metric: document.getElementById('reMetric').value,
    };
    try {
      const data = await apiFetch('/api/v1/eval/rank-eval', { method: 'POST', body: JSON.stringify(body) });
      setLoading(false);
      reRenderResults(data, body.metric, body.k);
    } catch (e) {
      setLoading(false);
      setError(e.message);
    }
  }

  function reRenderResults(data, metricName, k) {
    document.getElementById('rePanelMetric').textContent = metricName.toUpperCase();
    document.getElementById('reOverallScore').textContent = data.metric_score.toFixed(4);

    const qCount = Object.keys(data.details).length;
    document.getElementById('reQuerySummary').innerHTML =
      `${qCount} quer${qCount !== 1 ? 'ies' : 'y'} · top-${k}` +
      (Object.keys(data.failures).length ? ` · <span style="color:var(--red,#f87171)">${Object.keys(data.failures).length} failed</span>` : '');

    const rows = Object.entries(data.details).map(([qid, d]) => `
      <div class="re-detail-row">
        <span class="re-detail-qid">${esc(qid)}</span>
        <span class="re-detail-score">${d.metric_score.toFixed(4)}</span>
        ${d.unrated_docs.length ? `<span class="re-unrated" data-tooltip="Documents OpenSearch could not rate">${d.unrated_docs.length} unrated</span>` : ''}
      </div>`).join('');
    document.getElementById('reDetailTable').innerHTML = rows ||
      '<em style="color:var(--muted);font-size:.8rem;">No per-query details.</em>';

    const failDiv = document.getElementById('reFailures');
    const failures = Object.entries(data.failures);
    if (failures.length) {
      failDiv.style.display = '';
      failDiv.innerHTML = `<div style="font-size:.72rem;color:var(--red,#f87171);font-weight:600;margin-bottom:4px;">Failures</div>` +
        failures.map(([id, msg]) => `<div style="font-size:.72rem;color:var(--muted);margin-bottom:2px;"><strong>${esc(id)}</strong>: ${esc(msg)}</div>`).join('');
    } else {
      failDiv.style.display = 'none';
    }

    document.getElementById('rePanel').classList.add('visible');
  }

  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('q').addEventListener('keydown', e => { if (e.key === 'Enter') doSearch(); });
    updateWeightUI();
    refreshActiveProfileIndices();
    onAlgoModeChange();
  });

  // ─── Card expand/collapse ─────────────────────────────────────────────────
  window.toggleCard = function(cid, event) {
    // Don't toggle when clicking the eval checkbox
    if (event && event.target.classList.contains('card-checkbox')) return;
    const card = document.getElementById(cid);
    if (!card) return;
    const expanded = card.classList.toggle('expanded');
    const arrow = card.querySelector('.card-arrow');
    if (arrow) arrow.textContent = expanded ? '▾' : '▸';
  };