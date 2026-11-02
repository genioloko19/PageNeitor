/**
 * Main application script for Pageneitor v3.0.
 * Enriched with:
 * - Zero-Flicker in-place DOM updates
 * - 10 Persisted Color Themes x 3 Modes (Dark, Light, High-Contrast)
 * - 4-Element Clean Header & Collapsible Sidebar Accordions
 * - Control Panel (Themes, Profiles, Categories, Ollama AI Local)
 * - Level Detail Modal with Celebrations
 * - Console Trophy System (26+ trophies) & Inactivity Decay
 * - Cyclic Non-Static AI Tips powered by Ollama Local / Procedural Engine
 */

const State = {
  links: [],
  profiles: [],
  categories: [],
  gamification: null,
  dashboardAnalytics: null,
  ollamaStatus: null,
  currentProfileId: null,
  currentCategoryId: null,
  activeView: 'all',
  searchQuery: '',
  stats: null,
  currentTheme: localStorage.getItem('pageneitor_theme') || 'cyber-neon',
  currentMode: localStorage.getItem('pageneitor_mode') || 'dark',
  isDashboardOpen: false,
  cyclicTipTimer: null,
  currentCredentialsLink: null,
  currentSublinksLink: null,
  chat: {
    open: false,
    sessionId: null,
    sessions: [],
    sending: false,
    historyOpen: false,
    restored: false
  },
  domain: {
    groups: [],
    suggestions: [],
    settings: null,
    counts: { pending: 0, unread: 0 },
    groupByDomain: localStorage.getItem('pageneitor_group_by_domain') === '1',
    currentRootDomain: null,
    scanPoll: null,
    toastSeen: []
  },
  linkAssistant: {
    preview: null,
    items: [],
    targetDomain: null,
    lastChatPreview: null
  },
  domainDetail: null,
  analytics: {
    snapshot: null,
    mode: localStorage.getItem('pageneitor_analytics_mode') || 'beginner',
    charts: {},
    loading: false,
    insights: null
  },
  wordcloud: {
    sets: [],
    index: 0,
    timer: null,
    rotation: 60,
    drawnAt: 0
  },
  view: 'links',
  charts: {
    category: null,
    profile: null
  }
};

// 10 Themes definition for Control Panel visual selector
const THEMES_CATALOG = [
  { id: 'cyber-neon', name: 'Cyber Neón', colors: ['#6366f1', '#a855f7', '#06b6d4'] },
  { id: 'emerald', name: 'Esmeralda', colors: ['#059669', '#10b981', '#34d399'] },
  { id: 'sunset', name: 'Atardecer', colors: ['#f43f5e', '#fb923c', '#facc15'] },
  { id: 'ocean', name: 'Zafiro Océano', colors: ['#1d4ed8', '#0284c7', '#38bdf8'] },
  { id: 'amethyst', name: 'Amatista', colors: ['#7e22ce', '#c084fc', '#f472b6'] },
  { id: 'crimson', name: 'Carmesí', colors: ['#be123c', '#e11d48', '#fbbf24'] },
  { id: 'golden', name: 'Oro Imperial', colors: ['#b45309', '#f59e0b', '#fef08a'] },
  { id: 'obsidian', name: 'Obsidian Stealth', colors: ['#334155', '#64748b', '#cbd5e1'] },
  { id: 'synthwave', name: 'Synthwave 80s', colors: ['#ec4899', '#8b5cf6', '#06b6d4'] },
  { id: 'glacier', name: 'Glaciar Ártico', colors: ['#0891b2', '#22d3ee', '#a5f3fc'] }
];

// --- Web Audio API Console Chime Synthesizer ---
function playConsoleTrophySound() {
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    const ctx = new AudioContext();
    const notes = [659.25, 830.61, 987.77, 1318.51];
    const now = ctx.currentTime;

    notes.forEach((freq, idx) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(freq, now + idx * 0.08);

      gain.gain.setValueAtTime(0.001, now + idx * 0.08);
      gain.gain.exponentialRampToValueAtTime(0.3, now + idx * 0.08 + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + idx * 0.08 + 0.32);

      osc.connect(gain);
      gain.connect(ctx.destination);

      osc.start(now + idx * 0.08);
      osc.stop(now + idx * 0.08 + 0.35);
    });
  } catch (e) {}
}

function triggerConfettiBurst(originY = 0.6) {
  if (typeof confetti === 'function') {
    confetti({
      particleCount: 85,
      spread: 75,
      origin: { y: originY },
      colors: ['#6366f1', '#06b6d4', '#fbbf24', '#ec4899', '#10b981']
    });
  }
}

// --- App Bootstrap ---
document.addEventListener('DOMContentLoaded', async () => {
  applyThemeAndMode();
  setupEventListeners();
  await refreshAllData();
  setupCyclicAITips();
  await initChat();
  await initDomains();
  await initBackgroundLayers();

  try {
    const params = new URLSearchParams(window.location.search);
    const deepView = params.get('view');
    if (deepView === 'analytics') await openAnalyticsView();
    if (deepView === 'domain' && params.get('domain')) {
      await openDomainDetail(params.get('domain'));
    }
    if (deepView === 'assistant') {
      openLinkAssistant();
      const deepUrls = params.get('urls');
      if (deepUrls) {
        document.getElementById('linkAssistantText').value = deepUrls;
        analyzeAssistantLinks();
      }
    }
  } catch (err) {}
});

function applyThemeAndMode() {
  document.documentElement.setAttribute('data-theme', State.currentTheme);
  document.documentElement.setAttribute('data-mode', State.currentMode);

  // Sync mode buttons in header
  document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-mode') === State.currentMode);
  });

  // Background layers depend on theme colors.
  setTimeout(() => {
    try { if (typeof drawWordCloud === 'function') drawWordCloud(); } catch (err) {}
  }, 60);
}

async function refreshAllData() {
  await Promise.all([
    loadProfiles(),
    loadCategories(),
    loadStats(),
    loadGamification(),
    loadAnalytics(),
    loadOllamaStatus()
  ]);
  await loadLinks();
}

// ============================================================
// GAMIFICATION, TROPHIES & INACTIVITY DECAY
// ============================================================
async function loadGamification() {
  try {
    State.gamification = await API.getGamification();
    renderGamificationHeader();
    renderLevelDetailModal();

    // Check if user was penalized for inactivity
    if (State.gamification && State.gamification.decay_alert) {
      const decay = State.gamification.decay_alert;
      if (typeof Swal !== 'undefined') {
        Swal.fire({
          icon: 'warning',
          title: '⚠️ Penalización de Inactividad',
          text: decay.message,
          customClass: { popup: 'swal2-glass-popup', confirmButton: 'swal2-glass-confirm' },
          confirmButtonText: '¡A ponerse al día!'
        });
      }
    }
  } catch (err) {
    console.error('Error cargando gamificación:', err);
  }
}

function renderGamificationHeader() {
  if (!State.gamification) return;
  const g = State.gamification;

  // Header 4-element Item 2: Level Pill
  document.getElementById('headerLevelTag').textContent = `LVL ${g.level}`;
  document.getElementById('headerLevelTitle').textContent = g.level_title;
  document.getElementById('headerLevelMiniBar').style.width = `${g.progress_pct}%`;
  document.getElementById('menuTrophiesCount').textContent = `${g.unlocked_count}/${g.total_trophies}`;

  // KPI Dashboard cards
  document.getElementById('kpiLevelVal').textContent = `Nivel ${g.level}`;
  document.getElementById('kpiTabsVal').textContent = `${g.tabs_closed + (State.stats ? State.stats.total_active : 0)}`;
  document.getElementById('kpiTrophiesVal').textContent = `${g.unlocked_count} / ${g.total_trophies}`;
}

function renderLevelDetailModal() {
  if (!State.gamification) return;
  const g = State.gamification;

  document.getElementById('modalLevelNumber').textContent = `NIVEL ${g.level}`;
  document.getElementById('modalLevelTitle').textContent = g.level_title;
  document.getElementById('modalXpText').textContent = `${g.xp} / ${g.next_level_xp} XP`;
  document.getElementById('modalXpFill').style.width = `${g.progress_pct}%`;
  document.getElementById('modalTotalXp').textContent = `${g.xp} XP`;
  document.getElementById('modalTrophiesRatio').textContent = `${g.unlocked_count} / ${g.total_trophies}`;
  document.getElementById('modalTabsClosed').textContent = `${g.tabs_closed}`;
  document.getElementById('modalPrunedLinks').textContent = `${g.deleted_count || 0}`;
}

function handleGamificationEventResult(event) {
  if (!event) return;
  loadGamification();

  if (event.new_trophies && event.new_trophies.length > 0) {
    event.new_trophies.forEach(t => notifyTrophyUnlocked(t));
  } else if (event.level_up) {
    notifyLevelUp(event.level, event.level_title);
  }
}

function notifyTrophyUnlocked(trophy) {
  playConsoleTrophySound();
  triggerConfettiBurst(0.5);

  const tierColors = {
    platinum: '#38bdf8',
    gold: '#fbbf24',
    silver: '#cbd5e1',
    bronze: '#d97706'
  };
  const color = tierColors[trophy.tier] || '#fbbf24';

  if (typeof Swal !== 'undefined') {
    Swal.fire({
      title: '¡TROFEO DESBLOQUEADO!',
      html: `
        <div style="font-size: 38px; color: ${color}; margin: 12px 0;" class="animate__animated animate__tada">
          <i class="fa-solid ${trophy.icon}"></i>
        </div>
        <div style="font-size: 18px; font-weight: 800; color: #ffffff;">${escapeHtml(trophy.title)}</div>
        <div style="font-size: 11px; text-transform: uppercase; font-weight: 800; color: ${color}; margin: 4px 0 10px 0;">
          Trofeo ${trophy.tier.toUpperCase()} &bull; +${trophy.xp} XP
        </div>
        <p style="font-size: 13px; color: #cbd5e1; line-height: 1.4;">${escapeHtml(trophy.description)}</p>
      `,
      customClass: { popup: 'swal2-glass-popup', confirmButton: 'swal2-glass-confirm' },
      confirmButtonText: '¡Genial!'
    });
  } else {
    showToast(`🏆 ¡Trofeo Desbloqueado: ${trophy.title}!`, 'success');
  }
}

function notifyLevelUp(level, title) {
  playConsoleTrophySound();
  triggerConfettiBurst(0.4);

  if (typeof Swal !== 'undefined') {
    Swal.fire({
      title: '¡SUBISTE DE NIVEL! 🚀',
      html: `
        <div style="font-size: 44px; color: var(--primary); margin: 10px 0;" class="animate__animated animate__bounceIn">
          <i class="fa-solid fa-crown"></i>
        </div>
        <div style="font-size: 20px; font-weight: 800;">NIVEL ${level}</div>
        <div style="font-size: 14px; font-weight: 700; color: var(--primary); margin-top: 4px;">${escapeHtml(title)}</div>
        <p style="font-size: 13px; color: #94a3b8; margin-top: 10px;">
          Tu navegador está cada vez más libre de pestañas. ¡Sigue así para desbloquear trofeos de Platino!
        </p>
      `,
      customClass: { popup: 'swal2-glass-popup', confirmButton: 'swal2-glass-confirm' },
      confirmButtonText: '¡A seguir limpiando!'
    });
  } else {
    showToast(`🚀 ¡Subiste a Nivel ${level}: ${title}!`, 'success');
  }
}

// Render Trophies in Modal
function renderTrophiesModal() {
  if (!State.gamification) return;
  const grid = document.getElementById('trophiesGrid');
  grid.innerHTML = '';

  const list = State.gamification.trophies || [];
  document.getElementById('trophyCompletionBadge').textContent = `${State.gamification.unlocked_count} / ${State.gamification.total_trophies} Desbloqueados`;

  list.forEach(t => {
    const card = document.createElement('div');
    card.className = `trophy-card tier-${t.tier} ${t.unlocked ? 'unlocked' : 'locked'}`;

    card.innerHTML = `
      <div class="trophy-icon-box">
        <i class="fa-solid ${t.unlocked ? t.icon : 'fa-lock'}"></i>
      </div>
      <div class="trophy-details">
        <div class="trophy-tier-badge">
          <i class="fa-solid fa-trophy"></i> Trofeo ${t.tier.toUpperCase()}
        </div>
        <div class="trophy-title">${escapeHtml(t.title)}</div>
        <div class="trophy-desc">${escapeHtml(t.description)}</div>
        <div class="trophy-xp-tag">+${t.xp} XP</div>
      </div>
      <div style="font-size: 11px;">
        ${t.unlocked ? '<i class="fa-solid fa-circle-check" style="color: #34d399;"></i>' : '<i class="fa-solid fa-lock" style="color: #64748b;"></i>'}
      </div>
    `;
    grid.appendChild(card);
  });
}

// ============================================================
// OLLAMA LOCAL AI SERVICE & CYCLIC DYNAMIC TIPS
// ============================================================
async function loadOllamaStatus() {
  try {
    State.ollamaStatus = await API.getOllamaStatus();
    renderOllamaStatus();
  } catch (err) {
    console.error('Error comprobando Ollama:', err);
  }
}

function renderOllamaStatus() {
  if (!State.ollamaStatus) return;
  const s = State.ollamaStatus;

  const badge = document.getElementById('ollamaStatusBadge');
  const pathInfo = document.getElementById('ollamaPathInfo');
  const modelSelect = document.getElementById('ollamaModelSelect');

  if (s.is_running) {
    badge.textContent = 'En Ejecución';
    badge.style.background = 'rgba(16, 185, 129, 0.2)';
    badge.style.color = '#34d399';
  } else if (s.binary_found) {
    badge.textContent = 'Detenido (Instalado)';
    badge.style.background = 'rgba(245, 158, 11, 0.2)';
    badge.style.color = '#fbbf24';
  } else {
    badge.textContent = 'No Detectado';
    badge.style.background = 'rgba(239, 68, 68, 0.2)';
    badge.style.color = '#ef4444';
  }

  pathInfo.textContent = s.binary_path ? `Binario: ${s.binary_path}` : 'No se detectó ollama.exe en Windows ni en la raíz.';

  // Populate models
  modelSelect.innerHTML = '';
  if (s.available_models && s.available_models.length > 0) {
    s.available_models.forEach(m => {
      const opt = document.createElement('option');
      opt.value = m;
      opt.textContent = m;
      if (m === s.selected_model) opt.selected = true;
      modelSelect.appendChild(opt);
    });
  } else {
    modelSelect.innerHTML = '<option value="">Sin modelos descargados en Ollama</option>';
  }
}

async function triggerAITip(showSuccessToast = false) {
  const g = State.gamification || { level: 1, level_title: 'Novato' };
  const ram = State.stats ? (State.stats.total_active * 220 > 1000 ? `~${(State.stats.total_active * 220 / 1024).toFixed(1)} GB` : `~${State.stats.total_active * 220} MB`) : '~1.2 GB';
  const cnt = State.stats ? State.stats.total_active : 0;

  try {
    const tipData = await API.getCyclicTip({
      level: g.level,
      level_title: g.level_title,
      ram_saved: ram,
      links_count: cnt
    });

    if (tipData && tipData.tip) {
      document.getElementById('aiTipText').textContent = tipData.tip;
      document.getElementById('aiTipSource').textContent = tipData.source;
      if (showSuccessToast) {
        showToast(`Consejo generado por ${tipData.source}`, 'info');
      }
    }
  } catch (err) {
    console.warn('Error fetching tip:', err);
  }
}

function setupCyclicAITips() {
  triggerAITip();
  if (State.cyclicTipTimer) clearInterval(State.cyclicTipTimer);
  // Cyclic dynamic generation every 4 minutes (never static!)
  State.cyclicTipTimer = setInterval(() => {
    triggerAITip();
  }, 4 * 60 * 1000);
}

// ============================================================
// ZERO-FLICKER LINKS RENDERING & IN-PLACE DOM UPDATES
// ============================================================
async function loadLinks() {
  try {
    const params = {
      query: State.searchQuery,
      profile_id: State.currentProfileId,
      category_id: State.currentCategoryId,
      root_domain: State.domain.currentRootDomain,
      favorite: State.activeView === 'favorites',
      unread: State.activeView === 'unread'
    };

    State.links = await API.getLinks(params);
    renderLinksGridZeroFlicker();
    updateFilterBanner();
  } catch (err) {
    console.error('Error cargando enlaces:', err);
  }
}

function renderLinksGridZeroFlicker() {
  const grid = document.getElementById('linksGrid');
  grid.innerHTML = '';

  if (State.links.length === 0) {
    grid.innerHTML = `
      <div class="empty-state">
        <div style="font-size: 40px; color: var(--text-muted);"><i class="fa-solid fa-inbox"></i></div>
        <div style="font-size: 16px; font-weight: 800; color: var(--text-bright);">No hay enlaces para mostrar</div>
        <p style="font-size: 12.5px; color: var(--text-secondary); max-width: 380px;">
          Guarda enlaces o importa tus pestañas para mantener el navegador con 0 pestañas acumuladas.
        </p>
        <button class="glass-btn glass-btn-primary" onclick="openNewLinkModal()" style="margin-top: 6px;">
          <i class="fa-solid fa-plus"></i> Guardar Enlace
        </button>
      </div>
    `;
    return;
  }

  if (State.domain.groupByDomain) {
    renderGroupedLinksGrid(grid);
    return;
  }

  State.links.forEach(link => {
    const card = createLinkCardElement(link);
    grid.appendChild(card);
  });
}

function getDomainMosaicHtml(links, limit = 4) {
  const items = (links || []).slice(0, limit);
  if (!items.length) {
    return '<div class="domain-group-thumb fallback">?</div>';
  }
  return items.map(link => {
    if (link.thumbnail_url) {
      return `<div class="domain-group-thumb">
        <img src="${escapeHtml(link.thumbnail_url)}" alt="" onerror="this.parentElement.classList.add('fallback');this.parentElement.textContent='${escapeHtml((link.domain || '?').charAt(0).toUpperCase())}';">
      </div>`;
    }
    const initial = (link.domain || link.title || '?').charAt(0).toUpperCase();
    return `<div class="domain-group-thumb fallback">${escapeHtml(initial)}</div>`;
  }).join('');
}

function renderGroupedLinksGrid(grid) {
  const groups = new Map();
  State.links.forEach(link => {
    const root = link.root_domain || link.domain || 'sin-dominio';
    if (!groups.has(root)) groups.set(root, []);
    groups.get(root).push(link);
  });

  const sorted = [...groups.entries()].sort((a, b) => b[1].length - a[1].length);

  sorted.forEach(([root, items]) => {
    const section = document.createElement('section');
    section.className = 'domain-group';
    section.dataset.rootDomain = root;

    const header = document.createElement('div');
    header.className = 'domain-group-header';
    header.innerHTML = `
      <div class="domain-group-head-left">
        <div class="domain-group-mosaic">${getDomainMosaicHtml(items)}</div>
        <div class="domain-group-title-box">
          <h3><i class="fa-solid fa-globe"></i> ${escapeHtml(root)}</h3>
          <span>${items.length} ${items.length === 1 ? 'enlace' : 'enlaces'} agrupados</span>
        </div>
      </div>
      <div class="domain-group-actions">
        <button type="button" class="glass-btn btn-compact" data-domain-action="open-all" data-domain="${escapeHtml(root)}">
          <i class="fa-solid fa-up-right-from-square"></i> Abrir todos
        </button>
        <button type="button" class="glass-btn btn-compact" data-domain-action="merge" data-domain="${escapeHtml(root)}">
          <i class="fa-solid fa-object-group"></i> Fusionar
        </button>
        <button type="button" class="glass-btn glass-btn-secondary btn-compact" data-domain-action="suggest" data-domain="${escapeHtml(root)}">
          <i class="fa-solid fa-wand-magic-sparkles"></i> Sugerir IA
        </button>
      </div>`;
    section.appendChild(header);

    const body = document.createElement('div');
    body.className = 'links-grid domain-group-grid';
    items.forEach(link => body.appendChild(createLinkCardElement(link)));
    section.appendChild(body);
    grid.appendChild(section);
  });
}

function createLinkCardElement(link) {
  const card = document.createElement('article');
  card.className = 'link-card';
  card.id = `link-card-${link.id}`;

  let thumbnailHtml = '';
  if (link.thumbnail_url && link.thumbnail_url.trim() !== '') {
    thumbnailHtml = `
      <img class="card-thumbnail-img" src="${escapeHtml(link.thumbnail_url)}" alt="${escapeHtml(link.title)}" onerror="this.onerror=null; this.parentElement.innerHTML = getFallbackBannerHtml('${escapeHtml(link.domain)}', '${link.category_color || 'var(--primary)'}');">
    `;
  } else {
    thumbnailHtml = getFallbackBannerHtml(link.domain, link.category_color || 'var(--primary)');
  }

  const profileColor = link.profile_color || 'var(--primary)';
  const profileName = link.profile_name || 'General';
  const catColor = link.category_color || '#8b5cf6';
  const catName = link.category_name || 'Sin Categoría';
  const tagsHtml = (link.tags || []).map(t => `<span class="tag-badge">#${escapeHtml(t)}</span>`).join('');
  const credentialCount = (link.credentials || []).length;
  const sublinkCount = (link.sublinks || []).length;

  card.innerHTML = `
    <div class="card-thumbnail-container">
      ${thumbnailHtml}
      <div class="card-badges-top">
        <div class="profile-pill">
          <div class="color-dot" style="background-color: ${profileColor}"></div>
          <span>${escapeHtml(profileName)}</span>
        </div>
        <button class="quick-star-btn ${link.is_favorite ? 'active' : ''}" title="${link.is_favorite ? 'Quitar de Favoritos' : 'Marcar como Favorito'}" data-action="toggle-fav" data-id="${link.id}">
          <i class="fa-solid fa-star"></i>
        </button>
      </div>
    </div>

    <div class="card-body">
      <div class="card-topic-row">
        <span class="category-tag" style="color: ${catColor}; border-color: ${catColor}44; background: ${catColor}15;">
          ${escapeHtml(catName)}
        </span>
        <div class="card-domain">
          <img src="${escapeHtml(link.favicon_url || 'https://www.google.com/s2/favicons?domain=' + link.domain)}" alt="ico" onerror="this.style.display='none'">
          <span>${escapeHtml(link.domain || 'web')}</span>
        </div>
      </div>

      <h3 class="card-title" title="${escapeHtml(link.title)}" data-action="open-link" data-id="${link.id}">
        ${escapeHtml(link.title)}
      </h3>

      ${link.description ? `<p class="card-desc" title="${escapeHtml(link.description)}">${escapeHtml(link.description)}</p>` : ''}
      ${tagsHtml ? `<div class="card-tags">${tagsHtml}</div>` : ''}

      <div class="card-resource-row">
        <button class="resource-chip ${credentialCount ? 'has-items' : ''}" data-action="open-credentials" data-id="${link.id}" title="Gestionar cuentas y contraseñas de este sitio">
          <i class="fa-solid fa-key"></i>
          <span>${credentialCount ? `${credentialCount} cuenta${credentialCount === 1 ? '' : 's'}` : 'Credenciales'}</span>
        </button>
        <button class="resource-chip ${sublinkCount ? 'has-items' : ''}" data-action="open-sublinks" data-id="${link.id}" title="Ver y guardar más enlaces de esta misma página">
          <i class="fa-solid fa-folder-tree"></i>
          <span>${sublinkCount ? `${sublinkCount} sub-enlace${sublinkCount === 1 ? '' : 's'}` : 'Sub-enlaces'}</span>
        </button>
      </div>
    </div>

    <div class="card-footer">
      <button class="open-browser-btn" data-action="open-link" data-id="${link.id}" title="Abrir en el navegador y cerrar pestaña">
        <i class="fa-solid fa-rocket"></i> Abrir
      </button>

      <div class="card-actions-menu">
        <button class="icon-action-btn" data-action="copy-url" data-url="${escapeHtml(link.url)}" title="Copiar enlace">
          <i class="fa-regular fa-copy"></i>
        </button>
        <button class="icon-action-btn" data-action="open-credentials" data-id="${link.id}" title="Cuentas / credenciales">
          <i class="fa-solid fa-key"></i>
        </button>
        <button class="icon-action-btn" data-action="open-sublinks" data-id="${link.id}" title="Sub-enlaces del sitio">
          <i class="fa-solid fa-folder-tree"></i>
        </button>
        <button class="icon-action-btn" data-action="toggle-read" data-id="${link.id}" title="${link.is_read ? 'Marcar como no leído' : 'Marcar como leído'}">
          <i class="fa-solid ${link.is_read ? 'fa-check-double' : 'fa-clock'}" style="${link.is_read ? 'color: #34d399;' : ''}"></i>
        </button>
        <button class="icon-action-btn" data-action="edit-link" data-id="${link.id}" title="Editar enlace">
          <i class="fa-solid fa-pen"></i>
        </button>
        <button class="icon-action-btn delete-btn" data-action="delete-link" data-id="${link.id}" title="Eliminar enlace (Poda saludable)">
          <i class="fa-regular fa-trash-can"></i>
        </button>
      </div>
    </div>
  `;
  return card;
}

function getFallbackBannerHtml(domain, color) {
  const cleanDomain = domain || 'Sitio Web';
  const initial = cleanDomain.charAt(0).toUpperCase();
  return `
    <div class="fallback-banner" style="background: radial-gradient(circle at 70% 30%, ${color}33 0%, rgba(15, 23, 42, 0.9) 80%);">
      <div style="width: 40px; height: 40px; border-radius: 50%; border: 1px solid ${color}; color: ${color}; display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: 800;">
        ${initial}
      </div>
      <div style="font-size: 13px; font-weight: 700; color: #fff;">${escapeHtml(cleanDomain)}</div>
    </div>
  `;
}

// ============================================================
// PROFILES & CATEGORIES RENDERERS (SIDEBAR & CONTROL PANEL)
// ============================================================
async function loadProfiles() {
  State.profiles = await API.getProfiles();
  renderSidebarProfiles();
  renderControlPanelProfiles();
}

function renderSidebarProfiles() {
  const list = document.getElementById('sidebarProfilesList');
  list.innerHTML = '';

  State.profiles.forEach(p => {
    const li = document.createElement('li');
    li.className = `nav-item ${State.currentProfileId === p.id ? 'active' : ''}`;
    li.innerHTML = `
      <div class="nav-item-left">
        <div class="color-dot" style="background-color: ${p.color}"></div>
        <span>${escapeHtml(p.name)}</span>
      </div>
      <span class="nav-badge">${p.link_count || 0}</span>
    `;
    li.addEventListener('click', () => {
      State.currentProfileId = (State.currentProfileId === p.id) ? null : p.id;
      loadLinks();
      renderSidebarProfiles();
    });
    list.appendChild(li);
  });

  // Sync modal selects
  ['selectProfile', 'batchSelectProfile'].forEach(id => {
    const select = document.getElementById(id);
    if (!select) return;
    select.innerHTML = '';
    State.profiles.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.name;
      select.appendChild(opt);
    });
  });
}

function renderControlPanelProfiles() {
  const list = document.getElementById('cpProfilesList');
  list.innerHTML = '';

  State.profiles.forEach(p => {
    const row = document.createElement('div');
    row.className = 'cp-item-row';
    row.innerHTML = `
      <div class="cp-item-left">
        <div class="color-dot" style="background-color: ${p.color}; width: 12px; height: 12px;"></div>
        <div>
          <strong style="font-size: 13px; color: var(--text-bright);">${escapeHtml(p.name)}</strong>
          <span style="font-size: 11px; color: var(--text-muted); margin-left: 6px;">(${p.link_count || 0} enlaces)</span>
        </div>
      </div>
      <div class="cp-item-actions">
        <button class="icon-action-btn" title="Editar Perfil" onclick="editProfileDialog(${p.id}, '${escapeHtml(p.name)}', '${p.color}', '${escapeHtml(p.description || '')}')">
          <i class="fa-solid fa-pen"></i>
        </button>
        <button class="icon-action-btn delete-btn" title="Eliminar Perfil" onclick="deleteProfileDialog(${p.id}, '${escapeHtml(p.name)}')">
          <i class="fa-solid fa-trash-can"></i>
        </button>
      </div>
    `;
    list.appendChild(row);
  });
}

async function loadCategories() {
  State.categories = await API.getCategories();
  renderSidebarCategories();
  renderControlPanelCategories();
}

function renderSidebarCategories() {
  const list = document.getElementById('sidebarCategoriesList');
  list.innerHTML = '';

  State.categories.forEach(c => {
    const li = document.createElement('li');
    li.className = `nav-item ${State.currentCategoryId === c.id ? 'active' : ''}`;
    li.innerHTML = `
      <div class="nav-item-left">
        <div class="color-dot" style="background-color: ${c.color}"></div>
        <span>${escapeHtml(c.name)}</span>
      </div>
      <span class="nav-badge">${c.link_count || 0}</span>
    `;
    li.addEventListener('click', () => {
      State.currentCategoryId = (State.currentCategoryId === c.id) ? null : c.id;
      loadLinks();
      renderSidebarCategories();
    });
    list.appendChild(li);
  });

  // Sync modal selects
  ['selectCategory', 'batchSelectCategory'].forEach(id => {
    const select = document.getElementById(id);
    if (!select) return;
    select.innerHTML = '';
    State.categories.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c.id;
      opt.textContent = c.name;
      select.appendChild(opt);
    });
  });
}

function renderControlPanelCategories() {
  const list = document.getElementById('cpCategoriesList');
  list.innerHTML = '';

  State.categories.forEach(c => {
    const row = document.createElement('div');
    row.className = 'cp-item-row';
    row.innerHTML = `
      <div class="cp-item-left">
        <div class="color-dot" style="background-color: ${c.color}; width: 12px; height: 12px;"></div>
        <div>
          <strong style="font-size: 13px; color: var(--text-bright);">${escapeHtml(c.name)}</strong>
          <span style="font-size: 11px; color: var(--text-muted); margin-left: 6px;">(${c.link_count || 0} enlaces)</span>
        </div>
      </div>
      <div class="cp-item-actions">
        <button class="icon-action-btn" title="Editar Tema" onclick="editCategoryDialog(${c.id}, '${escapeHtml(c.name)}', '${c.color}')">
          <i class="fa-solid fa-pen"></i>
        </button>
        <button class="icon-action-btn delete-btn" title="Eliminar Tema" onclick="deleteCategoryDialog(${c.id}, '${escapeHtml(c.name)}')">
          <i class="fa-solid fa-trash-can"></i>
        </button>
      </div>
    `;
    list.appendChild(row);
  });
}

// Dialogs for Editing/Deleting Profiles & Categories in Control Panel
window.editProfileDialog = async function(id, name, color, desc) {
  if (typeof Swal === 'undefined') return;
  const { value: formValues } = await Swal.fire({
    title: 'Editar Perfil de Navegador',
    html: `
      <div class="form-group" style="text-align: left;">
        <label>Nombre:</label>
        <input id="swalProfileName" class="form-control" value="${name}">
      </div>
      <div class="form-group" style="text-align: left; margin-top: 10px;">
        <label>Color Identificador:</label>
        <input id="swalProfileColor" type="color" value="${color}" style="width: 100%; height: 36px; border: none; border-radius: 6px; cursor: pointer;">
      </div>
      <div class="form-group" style="text-align: left; margin-top: 10px;">
        <label>Descripción:</label>
        <input id="swalProfileDesc" class="form-control" value="${desc || ''}">
      </div>
    `,
    customClass: { popup: 'swal2-glass-popup', confirmButton: 'swal2-glass-confirm', cancelButton: 'swal2-glass-cancel' },
    showCancelButton: true,
    confirmButtonText: 'Guardar Cambios',
    cancelButtonText: 'Cancelar',
    preConfirm: () => {
      return {
        name: document.getElementById('swalProfileName').value.trim(),
        color: document.getElementById('swalProfileColor').value,
        description: document.getElementById('swalProfileDesc').value.trim()
      };
    }
  });

  if (formValues && formValues.name) {
    await API.updateProfile(id, formValues);
    showToast(`Perfil "${formValues.name}" actualizado`, 'success');
    await loadProfiles();
    await loadLinks();
  }
};

window.deleteProfileDialog = async function(id, name) {
  if (typeof Swal === 'undefined') return;
  const result = await Swal.fire({
    title: `¿Eliminar perfil "${name}"?`,
    text: 'Los enlaces asociados no se borrarán, solo quedarán desvinculados de este perfil.',
    icon: 'warning',
    showCancelButton: true,
    confirmButtonText: 'Sí, eliminar',
    cancelButtonText: 'Cancelar',
    customClass: { popup: 'swal2-glass-popup', confirmButton: 'swal2-glass-confirm', cancelButton: 'swal2-glass-cancel' }
  });

  if (result.isConfirmed) {
    await API.deleteProfile(id);
    showToast('Perfil eliminado', 'info');
    await loadProfiles();
    await loadLinks();
  }
};

window.editCategoryDialog = async function(id, name, color) {
  if (typeof Swal === 'undefined') return;
  const { value: formValues } = await Swal.fire({
    title: 'Editar Tema / Categoría',
    html: `
      <div class="form-group" style="text-align: left;">
        <label>Nombre:</label>
        <input id="swalCatName" class="form-control" value="${name}">
      </div>
      <div class="form-group" style="text-align: left; margin-top: 10px;">
        <label>Color Semántico:</label>
        <input id="swalCatColor" type="color" value="${color}" style="width: 100%; height: 36px; border: none; border-radius: 6px; cursor: pointer;">
      </div>
    `,
    customClass: { popup: 'swal2-glass-popup', confirmButton: 'swal2-glass-confirm', cancelButton: 'swal2-glass-cancel' },
    showCancelButton: true,
    confirmButtonText: 'Guardar Cambios',
    cancelButtonText: 'Cancelar',
    preConfirm: () => {
      return {
        name: document.getElementById('swalCatName').value.trim(),
        color: document.getElementById('swalCatColor').value
      };
    }
  });

  if (formValues && formValues.name) {
    await API.updateCategory(id, formValues);
    showToast(`Tema "${formValues.name}" actualizado`, 'success');
    await loadCategories();
    await loadLinks();
  }
};

window.deleteCategoryDialog = async function(id, name) {
  if (typeof Swal === 'undefined') return;
  const result = await Swal.fire({
    title: `¿Eliminar categoría "${name}"?`,
    text: 'Los enlaces asociados quedarán sin categoría pero seguirán en tu banco visual.',
    icon: 'warning',
    showCancelButton: true,
    confirmButtonText: 'Sí, eliminar',
    cancelButtonText: 'Cancelar',
    customClass: { popup: 'swal2-glass-popup', confirmButton: 'swal2-glass-confirm', cancelButton: 'swal2-glass-cancel' }
  });

  if (result.isConfirmed) {
    await API.deleteCategory(id);
    showToast('Tema eliminado', 'info');
    await loadCategories();
    await loadLinks();
  }
};

// ============================================================
// STATS & CHARTS (FLICKER-FREE IN-PLACE UPDATE)
// ============================================================
async function loadStats() {
  State.stats = await API.getStats();
  if (!State.stats) return;

  document.getElementById('badgeAllCount').textContent = State.stats.total_active || 0;
  document.getElementById('badgeFavCount').textContent = State.stats.total_favorites || 0;
  document.getElementById('badgeUnreadCount').textContent = State.stats.total_unread || 0;

  const count = State.stats.total_active;
  const ramMB = count * 220;
  const formattedRam = ramMB > 1000 ? `~${(ramMB / 1024).toFixed(1)} GB` : `~${ramMB} MB`;
  document.getElementById('sidebarRamVal').textContent = formattedRam;
  document.getElementById('kpiRamVal').textContent = formattedRam;
}

async function loadAnalytics() {
  State.dashboardAnalytics = await API.getAnalytics();
  renderChartsZeroFlicker();
}

function renderChartsZeroFlicker() {
  if (!State.dashboardAnalytics || typeof Chart === 'undefined') return;

  const cats = State.dashboardAnalytics.categories || [];
  const profs = State.dashboardAnalytics.profiles || [];

  const catLabels = cats.map(c => c.name);
  const catData = cats.map(c => c.count);
  const catColors = cats.map(c => c.color || '#6366f1');

  const catCanvas = document.getElementById('categoryChart');
  if (catCanvas) {
    if (State.charts.category) {
      State.charts.category.data.labels = catLabels.length ? catLabels : ['Sin datos'];
      State.charts.category.data.datasets[0].data = catData.length ? catData : [1];
      State.charts.category.data.datasets[0].backgroundColor = catColors.length ? catColors : ['#475569'];
      State.charts.category.update('none');
    } else {
      State.charts.category = new Chart(catCanvas, {
        type: 'doughnut',
        data: {
          labels: catLabels.length ? catLabels : ['Sin datos'],
          datasets: [{
            data: catData.length ? catData : [1],
            backgroundColor: catColors.length ? catColors : ['#475569'],
            borderWidth: 0,
            hoverOffset: 4
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: '70%',
          plugins: { legend: { display: false } }
        }
      });
    }
  }

  const profLabels = profs.map(p => p.name);
  const profData = profs.map(p => p.count);
  const profColors = profs.map(p => p.color || '#3b82f6');

  const profCanvas = document.getElementById('profileChart');
  if (profCanvas) {
    if (State.charts.profile) {
      State.charts.profile.data.labels = profLabels.length ? profLabels : ['General'];
      State.charts.profile.data.datasets[0].data = profData.length ? profData : [0];
      State.charts.profile.data.datasets[0].backgroundColor = profColors.length ? profColors : ['#3b82f6'];
      State.charts.profile.update('none');
    } else {
      State.charts.profile = new Chart(profCanvas, {
        type: 'bar',
        data: {
          labels: profLabels.length ? profLabels : ['General'],
          datasets: [{
            data: profData.length ? profData : [0],
            backgroundColor: profColors.length ? profColors : ['#3b82f6'],
            borderRadius: 4
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          indexAxis: 'y',
          scales: {
            x: { grid: { display: false }, ticks: { precision: 0 } },
            y: { grid: { display: false } }
          },
          plugins: { legend: { display: false } }
        }
      });
    }
  }
}

// ============================================================
// 10 THEMES SELECTOR GENERATOR IN CONTROL PANEL
// ============================================================
function renderThemesSelector() {
  const container = document.getElementById('themesSelectorGrid');
  container.innerHTML = '';

  THEMES_CATALOG.forEach(t => {
    const card = document.createElement('div');
    card.className = `theme-card-option ${State.currentTheme === t.id ? 'selected' : ''}`;
    card.innerHTML = `
      <div class="theme-palette-preview">
        <div class="theme-color-slice" style="background: ${t.colors[0]};"></div>
        <div class="theme-color-slice" style="background: ${t.colors[1]};"></div>
        <div class="theme-color-slice" style="background: ${t.colors[2]};"></div>
      </div>
      <div class="theme-option-name">${escapeHtml(t.name)}</div>
    `;

    card.addEventListener('click', () => {
      State.currentTheme = t.id;
      localStorage.setItem('pageneitor_theme', t.id);
      applyThemeAndMode();
      renderThemesSelector();
      showToast(`Tema "${t.name}" aplicado`, 'success');
      API.trackEvent('ui', 'change_theme', { theme: t.id });
    });

    container.appendChild(card);
  });
}

// ============================================================
// DOMAIN GROUPING, LLM SUGGESTIONS & INTERNAL NOTIFICATIONS
// ============================================================
async function initDomains() {
  try {
    const seen = JSON.parse(localStorage.getItem('pageneitor_domain_toast_seen') || '[]');
    State.domain.toastSeen = Array.isArray(seen) ? seen : [];
  } catch (err) {
    State.domain.toastSeen = [];
  }

  // Optional deep link: /?group=domains opens the grouped view.
  try {
    const urlGroup = new URLSearchParams(window.location.search).get('group');
    if (urlGroup === '1' || urlGroup === 'domains') {
      State.domain.groupByDomain = true;
      localStorage.setItem('pageneitor_group_by_domain', '1');
      renderLinksGridZeroFlicker();
    }
  } catch (err) {}

  document.getElementById('btnToggleDomainGrouping')
    .classList.toggle('active', State.domain.groupByDomain);

  await refreshDomainDashboard(false);
  maybeShowDomainToast(State.domain.suggestions);

  if (State.domain.pollTimer) clearInterval(State.domain.pollTimer);
  State.domain.pollTimer = setInterval(() => {
    refreshDomainDashboard(true);
  }, 30000);
}

function applyDomainSettingsToForm(settings) {
  if (!settings) return;
  document.getElementById('domainGroupSubdomains').checked = !!settings.group_subdomains;
  document.getElementById('domainScanEnabled').checked = !!settings.domain_scan_enabled;
  document.getElementById('domainScanInterval').value = String(settings.domain_scan_interval ?? 10);
  document.getElementById('domainMinConfidence').value = String(settings.domain_min_confidence ?? 0.6);
  document.getElementById('domainToastEnabled').checked = !!settings.domain_toast_enabled;
  document.getElementById('wordcloudRotation').value = String(settings.wordcloud_rotation ?? 60);
  document.getElementById('analyticsRetentionDays').value = String(settings.analytics_retention_days ?? 90);
}

function renderDomainSettingsStatus(dashboard) {
  const el = document.getElementById('domainSettingsStatus');
  if (!el) return;
  const d = dashboard || {};
  const last = d.last_scan && d.last_scan.at
    ? new Date(d.last_scan.at * 1000).toLocaleString()
    : 'Aún no ejecutado';
  const pending = (d.counts && d.counts.pending) || 0;
  const groups = (d.groups || []).length;
  el.innerHTML =
    `<i class="fa-solid fa-circle-info"></i> Dominios: <strong>${groups}</strong> · ` +
    `Sugerencias pendientes: <strong>${pending}</strong><br>` +
    `<span>Último análisis: ${escapeHtml(last)}</span>`;
}

async function refreshDomainDashboard(showToast = false) {
  try {
    const dashboard = await API.getDomainDashboard();
    State.domain.groups = dashboard.groups || [];
    State.domain.suggestions = dashboard.suggestions || [];
    State.domain.counts = dashboard.counts || { pending: 0, unread: 0 };
    State.domain.settings = dashboard.settings || State.domain.settings;

    applyDomainSettingsToForm(State.domain.settings);
    renderSidebarDomains();
    renderDomainNotifications();
    updateDomainBell();
    renderDomainSettingsStatus(dashboard);
    if (showToast) maybeShowDomainToast(State.domain.suggestions);
    return dashboard;
  } catch (err) {
    console.warn('No se pudo actualizar el panel de dominios:', err);
    return null;
  }
}

async function loadDomainGroups() {
  return refreshDomainDashboard(false);
}

function renderSidebarDomains() {
  const list = document.getElementById('sidebarDomainsList');
  if (!list) return;
  const groups = State.domain.groups || [];

  if (!groups.length) {
    list.innerHTML = '<li class="nav-item" style="opacity:.6; cursor:default;"><div class="nav-item-left"><i class="fa-solid fa-globe" style="width:14px;"></i><span>Sin dominios aún</span></div></li>';
    return;
  }

  list.innerHTML = groups.map(group => {
    const active = State.domain.currentRootDomain === group.root_domain;
    return `
      <li class="nav-item ${active ? 'active' : ''}" data-domain-root="${escapeHtml(group.root_domain)}">
        <div class="nav-item-left">
          <i class="fa-solid fa-globe" style="width: 14px; color: var(--primary);"></i>
          <span title="${escapeHtml(group.root_domain)}">${escapeHtml(group.root_domain)}</span>
        </div>
        <span class="nav-badge">${group.count || 0}</span>
      </li>`;
  }).join('');
}

function updateDomainBell() {
  const badge = document.getElementById('domainNotificationBadge');
  if (!badge) return;
  const pending = State.domain.counts.pending || 0;
  const unread = State.domain.counts.unread || 0;
  badge.textContent = pending > 99 ? '99+' : String(pending);
  badge.style.display = pending > 0 ? 'inline-flex' : 'none';
  badge.classList.toggle('has-unread', unread > 0);
}

function domainActionLabel(action) {
  if (action === 'merge_group') return 'Fusionar grupo';
  if (action === 'refresh_thumbnail') return 'Recuperar miniaturas';
  return 'Sugerencia de dominio';
}

function buildDomainSuggestionCard(suggestion, compact = false) {
  const payload = suggestion.payload || {};
  const links = payload.links || [];
  const main = payload.main_link || null;
  const confidence = Math.round((suggestion.confidence || 0) * 100);
  const mosaic = getDomainMosaicHtml(links, compact ? 3 : 4);
  const mainText = main
    ? `<div class="domain-suggestion-main"><i class="fa-solid fa-star"></i> Principal propuesto: <strong>${escapeHtml(main.title || main.url)}</strong></div>`
    : '';

  return `
    <div class="domain-suggestion-card" data-suggestion-card="${suggestion.id}">
      <div class="domain-suggestion-top">
        <div class="domain-suggestion-mosaic">${mosaic}</div>
        <div class="domain-suggestion-info">
          <div class="domain-suggestion-action">
            <i class="fa-solid fa-wand-magic-sparkles"></i> ${domainActionLabel(suggestion.action)}
          </div>
          <strong>${escapeHtml(suggestion.root_domain || '')}</strong>
          <span>${escapeHtml(suggestion.reason || '')}</span>
          ${mainText}
        </div>
        <div class="domain-confidence" title="Confianza de Ollama">
          ${confidence}%
        </div>
      </div>
      <div class="domain-suggestion-actions">
        <button type="button" class="glass-btn glass-btn-primary btn-compact" data-apply-domain-suggestion="${suggestion.id}">
          <i class="fa-solid fa-check"></i> Aplicar
        </button>
        <button type="button" class="glass-btn btn-compact" data-dismiss-domain-suggestion="${suggestion.id}">
          <i class="fa-solid fa-xmark"></i> Descartar
        </button>
        <button type="button" class="glass-btn btn-compact" data-open-domain-group="${escapeHtml(suggestion.root_domain || '')}">
          <i class="fa-solid fa-eye"></i> Ver grupo
        </button>
      </div>
    </div>`;
}

function renderDomainNotifications() {
  const list = document.getElementById('domainNotificationsList');
  const summary = document.getElementById('domainNotifSummary');
  if (!list) return;
  const suggestions = State.domain.suggestions || [];

  if (summary) {
    summary.innerHTML =
      `<strong>${suggestions.length}</strong> sugerencia(s) pendiente(s) · ` +
      `<strong>${State.domain.groups.length}</strong> dominio(s) agrupado(s)`;
  }

  if (!suggestions.length) {
    list.innerHTML = `
      <div class="db-empty">
        <i class="fa-solid fa-bell-slash" style="font-size:22px;opacity:.5;display:block;margin-bottom:6px;"></i>
        No hay sugerencias pendientes. Ollama revisará los dominios al guardar enlaces o cada ${escapeHtml(String((State.domain.settings && State.domain.settings.domain_scan_interval) || 10))} minutos.
      </div>`;
    return;
  }

  list.innerHTML = suggestions.map(s => buildDomainSuggestionCard(s, false)).join('');
}

async function openDomainNotifications() {
  await refreshDomainDashboard(false);
  document.getElementById('domainNotificationsModal').classList.add('active');

  const ids = (State.domain.suggestions || []).map(s => s.id);
  if (ids.length) {
    try {
      await API.markDomainSuggestionsRead(ids);
      State.domain.counts.unread = 0;
      updateDomainBell();
    } catch (err) {}
  }
}

function saveDomainToastSeen() {
  const seen = [...new Set(State.domain.toastSeen)].slice(-200);
  State.domain.toastSeen = seen;
  try {
    localStorage.setItem('pageneitor_domain_toast_seen', JSON.stringify(seen));
  } catch (err) {}
}

function maybeShowDomainToast(suggestions) {
  const settings = State.domain.settings;
  if (!settings || !settings.domain_toast_enabled) return;

  const candidates = (suggestions || []).filter(s =>
    s.status === 'pending' &&
    !s.is_read &&
    !State.domain.toastSeen.includes(s.id)
  );
  if (!candidates.length) return;

  candidates.sort((a, b) => (b.confidence || 0) - (a.confidence || 0));
  const suggestion = candidates[0];
  State.domain.toastSeen.push(suggestion.id);
  saveDomainToastSeen();
  showDomainToast(suggestion);
}

function showDomainToast(suggestion) {
  const container = document.getElementById('domainToastContainer');
  if (!container) return;
  container.innerHTML = '';

  const toast = document.createElement('div');
  toast.className = 'domain-toast';
  toast.dataset.toastSuggestion = suggestion.id;
  toast.innerHTML = `
    <div class="domain-toast-icon"><i class="fa-solid fa-wand-magic-sparkles"></i></div>
    <div class="domain-toast-body">
      <strong>${domainActionLabel(suggestion.action)} · ${escapeHtml(suggestion.root_domain || '')}</strong>
      <p>${escapeHtml(suggestion.reason || 'Nueva sugerencia de Ollama')}</p>
    </div>
    <div class="domain-toast-actions">
      <button type="button" class="glass-btn glass-btn-primary btn-compact" data-domain-toast-apply="${suggestion.id}" title="Aplicar con confirmación">Aplicar</button>
      <button type="button" class="glass-btn btn-compact" data-domain-toast-review="${suggestion.id}">Revisar</button>
      <button type="button" class="icon-action-btn" data-domain-toast-close title="Cerrar"><i class="fa-solid fa-xmark"></i></button>
    </div>`;
  container.appendChild(toast);

  setTimeout(() => {
    if (toast.parentElement) toast.remove();
  }, 12000);
}

async function applyDomainSuggestionUI(suggestionId) {
  const suggestion = (State.domain.suggestions || []).find(s => String(s.id) === String(suggestionId));
  const label = suggestion ? domainActionLabel(suggestion.action) : 'esta sugerencia';
  const ok = await safeConfirm(
    `¿Aplicar ${label}?`,
    'Se creará una copia de seguridad automática y el cambio se podrá deshacer.'
  );
  if (!ok) return;

  const res = await API.applyDomainSuggestion(suggestionId);
  if (res && res.success) {
    showToast('Sugerencia aplicada correctamente', 'success');
    API.trackEvent('domain', 'apply_suggestion', { suggestion_id: suggestionId, action: suggestion && suggestion.action });
    await refreshAllData();
    await refreshDomainDashboard(false);
    document.getElementById('domainNotificationsModal').classList.remove('active');
  } else {
    showToast((res && (res.error || res.message)) || 'No se pudo aplicar la sugerencia', 'error');
  }
}

async function dismissDomainSuggestionUI(suggestionId) {
  const res = await API.dismissDomainSuggestion(suggestionId);
  if (res && res.success) {
    showToast('Sugerencia descartada', 'info');
    API.trackEvent('domain', 'dismiss_suggestion', { suggestion_id: suggestionId });
    await refreshDomainDashboard(false);
  }
}

async function scanDomainsNow() {
  const res = await API.scanDomains();
  if (res && res.started) {
    showToast('Ollama está analizando los dominios...', 'info');
    API.trackEvent('domain', 'scan_requested');
    startDomainScanPolling();
  } else if (res && res.success === false) {
    showToast(res.error || 'No se pudo iniciar el análisis', 'error');
  }
}

function startDomainScanPolling() {
  if (State.domain.scanPoll) clearInterval(State.domain.scanPoll);
  let ticks = 0;
  State.domain.scanPoll = setInterval(async () => {
    ticks += 1;
    await refreshDomainDashboard(true);
    if (ticks >= 12) {
      clearInterval(State.domain.scanPoll);
      State.domain.scanPoll = null;
    }
  }, 5000);
}

async function undoDomainActionUI() {
  const ok = await safeConfirm(
    '¿Deshacer la última acción de dominios?',
    'Se restaurarán los enlaces y miniaturas al estado anterior.'
  );
  if (!ok) return;

  const res = await API.undoDomainAction();
  if (res && res.success) {
    showToast(res.message || 'Cambio deshecho', 'success');
    API.trackEvent('domain', 'undo');
    await refreshAllData();
    await refreshDomainDashboard(false);
  } else {
    showToast((res && res.error) || 'No hay acciones para deshacer', 'error');
  }
}

async function selectDomainGroup(rootDomain) {
  if (State.domain.currentRootDomain === rootDomain && State.view === 'domain') {
    setMainView('links');
    State.domain.currentRootDomain = null;
    renderSidebarDomains();
    await loadLinks();
    return;
  }
  await openDomainDetail(rootDomain);
}

async function handleDomainGroupAction(action, rootDomain) {
  if (action === 'open-all') {
    const res = await API.openAllDomain(rootDomain);
    if (res && res.success) {
      showToast(`${res.opened_count} enlaces abiertos`, 'success');
      if (res._gamification) handleGamificationEventResult(res._gamification);
      loadStats();
    } else {
      showToast('No se pudieron abrir los enlaces', 'error');
    }
  } else if (action === 'merge') {
    await mergeDomainGroupUI(rootDomain);
  } else if (action === 'suggest') {
    await scanDomainsNow();
  }
}

async function mergeDomainGroupUI(rootDomain) {
  // Always use the complete domain group, not only the currently filtered cards.
  const groups = await API.getDomainGroups();
  const group = (groups || []).find(g => g.root_domain === rootDomain);
  let links = group ? (group.links || []) : [];

  if (links.length < 2) {
    showToast('Este dominio necesita al menos dos enlaces para fusionarse', 'info');
    return;
  }

  links.sort((a, b) =>
    ((b.is_favorite || 0) - (a.is_favorite || 0)) ||
    ((b.visit_count || 0) - (a.visit_count || 0)) ||
    ((b.id || 0) - (a.id || 0))
  );
  const main = links[0];

  const ok = await safeConfirm(
    `¿Fusionar ${links.length} enlaces de «${rootDomain}»?`,
    `Se conservará «${main.title}» como principal y se archivarán los demás. ` +
    'Se combinarán credenciales, sub-enlaces, etiquetas y notas. Podrás deshacerlo.'
  );
  if (!ok) return;

  const res = await API.mergeDomain(rootDomain, main.id, links.map(l => l.id), 'Fusión manual desde el grupo');
  if (res && res.success) {
    showToast(`Grupo fusionado: ${res.merged_count} enlaces archivados`, 'success');
    API.trackEvent('domain', 'merge_group', { root_domain: rootDomain, merged: res.merged_count });
    await refreshAllData();
    await refreshDomainDashboard(false);
  } else {
    showToast((res && (res.error || res.message)) || 'No se pudo fusionar el grupo', 'error');
  }
}

async function saveDomainSettingsFromUI() {
  const payload = {
    group_subdomains: document.getElementById('domainGroupSubdomains').checked,
    domain_scan_enabled: document.getElementById('domainScanEnabled').checked,
    domain_scan_interval: parseInt(document.getElementById('domainScanInterval').value, 10),
    domain_min_confidence: parseFloat(document.getElementById('domainMinConfidence').value),
    domain_toast_enabled: document.getElementById('domainToastEnabled').checked,
    wordcloud_rotation: parseInt(document.getElementById('wordcloudRotation').value, 10),
    analytics_retention_days: parseInt(document.getElementById('analyticsRetentionDays').value, 10)
  };

  const res = await API.saveDomainSettings(payload);
  if (res && res.success) {
    State.domain.settings = res.settings;
    State.wordcloud.rotation = res.settings.wordcloud_rotation || 60;
    if (State.wordcloud.timer) {
      clearInterval(State.wordcloud.timer);
      State.wordcloud.timer = setInterval(rotateWordCloud, Math.max(15, State.wordcloud.rotation) * 1000);
    }
    applyDomainSettingsToForm(res.settings);
    showToast('Configuración guardada', 'success');
    await loadLinks();
    await refreshDomainDashboard(false);
    startDomainScanPolling();
  } else {
    showToast('No se pudo guardar la configuración', 'error');
  }
}

// ============================================================
// FLOATING PERSISTENT ASSISTANT (OLLAMA + LOCAL SEARCH)
// ============================================================
const CHAT_DEFAULT_SUGGESTIONS = [
  'Ver categorías',
  'Ver perfiles',
  'Ver dominios',
  'Ver sugerencias',
  'Resumen de mi banco',
  'Enlaces sin leer'
];

async function initChat() {
  await loadChatEngineStatus();
  await loadChatSessions();

  const savedId = localStorage.getItem('pageneitor_chat_session');
  if (savedId) {
    const ok = await restoreChatSession(savedId, false);
    if (!ok) localStorage.removeItem('pageneitor_chat_session');
  }
}

async function loadChatEngineStatus() {
  const badge = document.getElementById('chatEngineBadge');
  const dot = document.getElementById('chatFabDot');
  if (!badge) return;

  try {
    const s = await API.getOllamaStatus();
    if (s && s.is_running && s.selected_model) {
      badge.innerHTML = `<i class="fa-solid fa-circle" style="color:#34d399;"></i> Ollama · ${escapeHtml(s.selected_model)}`;
      badge.className = 'chat-engine-badge online';
      dot.className = 'chat-fab-dot online';
    } else if (s && s.binary_found) {
      badge.innerHTML = '<i class="fa-solid fa-circle" style="color:#fbbf24;"></i> Ollama disponible';
      badge.className = 'chat-engine-badge idle';
      dot.className = 'chat-fab-dot idle';
    } else {
      badge.innerHTML = '<i class="fa-solid fa-circle" style="color:#38bdf8;"></i> Motor local';
      badge.className = 'chat-engine-badge local';
      dot.className = 'chat-fab-dot local';
    }
  } catch (err) {
    badge.innerHTML = '<i class="fa-solid fa-circle" style="color:#38bdf8;"></i> Motor local';
    badge.className = 'chat-engine-badge local';
  }
}

function toggleChatPanel(force) {
  const panel = document.getElementById('chatPanel');
  const fab = document.getElementById('chatFab');
  State.chat.open = typeof force === 'boolean' ? force : !State.chat.open;

  panel.classList.toggle('open', State.chat.open);
  panel.setAttribute('aria-hidden', State.chat.open ? 'false' : 'true');
  fab.classList.toggle('active', State.chat.open);
  document.body.classList.toggle('chat-open', State.chat.open);

  if (State.chat.open) {
    loadChatEngineStatus();
    scrollChatToBottom();
    setTimeout(() => document.getElementById('chatInput').focus(), 120);
  }
}

function scrollChatToBottom() {
  const box = document.getElementById('chatMessages');
  if (box) box.scrollTop = box.scrollHeight;
}

function chatWelcomeHtml() {
  return `
    <div class="chat-welcome">
      <div class="chat-welcome-icon"><i class="fa-solid fa-wand-magic-sparkles"></i></div>
      <div class="chat-welcome-title">Tu asistente de enlaces</div>
      <p>Puedo buscar en tu banco, mostrarte temas, perfiles y abrir enlaces por ti.</p>
    </div>`;
}

function resetChatView() {
  const box = document.getElementById('chatMessages');
  box.innerHTML = chatWelcomeHtml();
  setChatSuggestions(CHAT_DEFAULT_SUGGESTIONS);
}

function startNewChat() {
  State.chat.sessionId = null;
  localStorage.removeItem('pageneitor_chat_session');
  resetChatView();
  closeChatHistory();
  setTimeout(() => document.getElementById('chatInput').focus(), 100);
}

async function loadChatSessions() {
  try {
    State.chat.sessions = await API.getChatSessions();
    renderChatSessionList();
  } catch (err) {
    console.warn('No se pudieron cargar las conversaciones:', err);
  }
}

function renderChatSessionList() {
  const container = document.getElementById('chatSessionList');
  if (!container) return;
  const sessions = State.chat.sessions || [];

  if (!sessions.length) {
    container.innerHTML = '<div class="chat-history-empty">Aún no hay conversaciones.</div>';
    return;
  }

  container.innerHTML = sessions.map(session => {
    const active = String(session.id) === String(State.chat.sessionId);
    const date = (session.updated_at || session.created_at || '').replace('T', ' ').slice(0, 16);
    return `
      <div class="chat-session-item ${active ? 'active' : ''}" data-session-id="${session.id}">
        <div class="chat-session-main">
          <strong>${escapeHtml(session.title || 'Conversación')}</strong>
          <span>${escapeHtml(date)} · ${session.message_count || 0} mensajes</span>
          <p>${escapeHtml((session.last_message || '').slice(0, 90))}</p>
        </div>
        <button type="button" class="chat-session-delete" data-delete-chat-session="${session.id}" title="Eliminar conversación">
          <i class="fa-regular fa-trash-can"></i>
        </button>
      </div>`;
  }).join('');
}

async function restoreChatSession(sessionId, openPanel = true) {
  try {
    const session = await API.getChatSession(sessionId);
    if (!session || session.error) return false;

    State.chat.sessionId = session.id;
    localStorage.setItem('pageneitor_chat_session', session.id);

    const box = document.getElementById('chatMessages');
    box.innerHTML = '';
    (session.messages || []).forEach(msg => appendChatMessage(msg.role, msg.content, msg.data, false));

    if (!(session.messages || []).length) box.innerHTML = chatWelcomeHtml();
    if (openPanel) toggleChatPanel(true);
    scrollChatToBottom();
    renderChatSessionList();
    return true;
  } catch (err) {
    return false;
  }
}

function appendChatMessage(role, content, data = null, animate = true) {
  const box = document.getElementById('chatMessages');
  const welcome = box.querySelector('.chat-welcome');
  if (welcome) welcome.remove();

  const wrapper = document.createElement('div');
  wrapper.className = `chat-msg ${role}${animate ? ' animate__animated animate__fadeInUp' : ''}`;

  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble';

  const avatar = document.createElement('div');
  avatar.className = 'chat-msg-avatar';
  avatar.innerHTML = role === 'user'
    ? '<i class="fa-solid fa-user"></i>'
    : '<i class="fa-solid fa-robot"></i>';

  const body = document.createElement('div');
  body.className = 'chat-bubble-body';
  const text = document.createElement('div');
  text.className = 'chat-text';
  text.textContent = content || '';
  body.appendChild(text);

  if (data && role === 'assistant') {
    const results = document.createElement('div');
    results.className = 'chat-results';
    renderChatResults(results, data);
    if (results.childElementCount) body.appendChild(results);
  }

  bubble.appendChild(avatar);
  bubble.appendChild(body);
  wrapper.appendChild(bubble);
  box.appendChild(wrapper);

  if (data && data.suggestions && data.suggestions.length) {
    setChatSuggestions(data.suggestions);
  }
  if (data && data.source) {
    const source = document.createElement('div');
    source.className = 'chat-msg-source';
    source.innerHTML = `<i class="fa-solid fa-microchip"></i> ${escapeHtml(data.source)}`;
    body.appendChild(source);
  }
  scrollChatToBottom();
}

function setChatSuggestions(suggestions) {
  const container = document.getElementById('chatSuggestions');
  if (!container) return;
  const chips = (suggestions && suggestions.length) ? suggestions : CHAT_DEFAULT_SUGGESTIONS;
  container.innerHTML = chips.slice(0, 6).map(text => `
    <button type="button" class="chat-chip" data-chat-suggestion="${escapeHtml(text)}">${escapeHtml(text)}</button>
  `).join('');
}

function renderChatResults(container, data) {
  if (data.link_preview && data.link_preview.items) {
    State.linkAssistant.lastChatPreview = data.link_preview;
    const preview = data.link_preview;
    const wrap = document.createElement('div');
    wrap.className = 'chat-link-assistant-preview';
    wrap.innerHTML = `
      <div class="chat-domain-action-head">
        <i class="fa-solid fa-wand-magic-sparkles"></i>
        Asistente de enlaces · ${preview.items.length} detectados
      </div>
      <div class="chat-link-list">
        ${preview.items.slice(0, 4).map(item => `
          <div class="chat-link-card">
            <div class="chat-link-top">
              <div class="chat-link-favicon">
                ${item.thumbnail_url ? `<img src="${escapeHtml(item.thumbnail_url)}" alt="" onerror="this.style.display='none'">` : '<i class="fa-solid fa-link"></i>'}
              </div>
              <div class="chat-link-info">
                <strong>${escapeHtml(item.title || item.url)}</strong>
                <span>${escapeHtml(item.root_domain || '')} · ${escapeHtml(item.category_name || '')} · ${escapeHtml(item.profile_name || '')}</span>
              </div>
            </div>
          </div>`).join('')}
      </div>
      <button type="button" class="glass-btn glass-btn-primary btn-compact" data-open-link-assistant>
        <i class="fa-solid fa-arrow-right"></i> Revisar y guardar
      </button>`;
    container.appendChild(wrap);
  }

  if (data.stats && Object.keys(data.stats).length) {
    const s = data.stats;
    const stats = document.createElement('div');
    stats.className = 'chat-stats-grid';
    stats.innerHTML = `
      <div><span>Enlaces</span><strong>${s.total_active || 0}</strong></div>
      <div><span>Favoritos</span><strong>${s.total_favorites || 0}</strong></div>
      <div><span>Pendientes</span><strong>${s.total_unread || 0}</strong></div>
      <div><span>Temas</span><strong>${s.total_categories || 0}</strong></div>`;
    container.appendChild(stats);
  }

  if (data.domain_groups && data.domain_groups.length) {
    const grid = document.createElement('div');
    grid.className = 'chat-domain-groups';
    data.domain_groups.slice(0, 8).forEach(group => {
      const card = document.createElement('div');
      card.className = 'chat-domain-group-card';
      card.innerHTML = `
        <div class="chat-domain-mosaic">${getDomainMosaicHtml((group.links || []).slice(0, 3), 3)}</div>
        <div class="chat-domain-group-info">
          <strong>${escapeHtml(group.root_domain)}</strong>
          <span>${group.count || 0} enlaces</span>
        </div>
        <button type="button" class="chat-link-open" data-chat-open-domain="${escapeHtml(group.root_domain)}">
          Ver grupo
        </button>`;
      grid.appendChild(card);
    });
    container.appendChild(grid);
  }

  if (data.domain_suggestions && data.domain_suggestions.length) {
    const list = document.createElement('div');
    list.className = 'chat-domain-suggestions';
    data.domain_suggestions.slice(0, 4).forEach(s => {
      list.insertAdjacentHTML('beforeend', buildDomainSuggestionCard(s, true));
    });
    container.appendChild(list);
  }

  if (data.domain_action) {
    const action = data.domain_action;
    const wrap = document.createElement('div');
    if (action.action === 'apply_suggestion' && action.suggestion) {
      wrap.innerHTML = buildDomainSuggestionCard(action.suggestion, true);
    } else if (action.action === 'merge_preview') {
      const links = action.links || [];
      wrap.innerHTML = `
        <div class="chat-domain-action">
          <div class="chat-domain-action-head">
            <i class="fa-solid fa-object-group"></i> Fusión propuesta · ${escapeHtml(action.root_domain)}
          </div>
          <div class="chat-domain-mosaic">${getDomainMosaicHtml(links, 4)}</div>
          <p>Principal: <strong>${escapeHtml((action.main_link && (action.main_link.title || action.main_link.url)) || '')}</strong></p>
          <div class="domain-suggestion-actions">
            <button type="button" class="glass-btn glass-btn-primary btn-compact"
              data-chat-merge-domain="${escapeHtml(action.root_domain)}"
              data-chat-merge-main="${action.main_link_id}"
              data-chat-merge-ids="${(action.link_ids || []).join(',')}">
              <i class="fa-solid fa-check"></i> Fusionar
            </button>
            <button type="button" class="glass-btn btn-compact" data-chat-dismiss-domain-action>
              <i class="fa-solid fa-xmark"></i> Cancelar
            </button>
          </div>
        </div>`;
    } else if (action.action === 'undo') {
      wrap.innerHTML = `
        <div class="chat-domain-action">
          <div class="chat-domain-action-head"><i class="fa-solid fa-rotate-left"></i> Deshacer último cambio</div>
          <p>${escapeHtml(action.description || 'Restaurar el estado anterior de los dominios.')}</p>
          <div class="domain-suggestion-actions">
            <button type="button" class="glass-btn glass-btn-primary btn-compact" data-chat-undo-domain>
              <i class="fa-solid fa-rotate-left"></i> Deshacer
            </button>
          </div>
        </div>`;
    }
    if (wrap.childElementCount) container.appendChild(wrap);
  }

  if (data.categories && data.categories.length) {
    const grid = document.createElement('div');
    grid.className = 'chat-chip-grid';
    data.categories.forEach(cat => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'chat-result-chip';
      btn.style.borderColor = `${cat.color}66`;
      btn.style.background = `${cat.color}18`;
      btn.innerHTML = `
        <span class="chat-result-dot" style="background:${cat.color}"></span>
        <span>${escapeHtml(cat.name)}</span>
        <em>${cat.link_count || 0}</em>`;
      btn.addEventListener('click', () => sendChatMessage(`enlaces de ${cat.name}`));
      grid.appendChild(btn);
    });
    container.appendChild(grid);
  }

  if (data.profiles && data.profiles.length) {
    const grid = document.createElement('div');
    grid.className = 'chat-chip-grid';
    data.profiles.forEach(profile => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'chat-result-chip';
      btn.style.borderColor = `${profile.color}66`;
      btn.style.background = `${profile.color}18`;
      btn.innerHTML = `
        <span class="chat-result-dot" style="background:${profile.color}"></span>
        <span>${escapeHtml(profile.name)}</span>
        <em>${profile.link_count || 0}</em>`;
      btn.addEventListener('click', () => sendChatMessage(`enlaces de ${profile.name}`));
      grid.appendChild(btn);
    });
    container.appendChild(grid);
  }

  if (data.links && data.links.length) {
    const list = document.createElement('div');
    list.className = 'chat-link-list';
    data.links.forEach(link => {
      const card = document.createElement('div');
      card.className = 'chat-link-card';
      const tags = (link.tags || []).slice(0, 2).map(t => `<span class="chat-link-tag">#${escapeHtml(t)}</span>`).join('');
      card.innerHTML = `
        <div class="chat-link-top">
          <div class="chat-link-favicon">
            <img src="${escapeHtml(link.favicon_url || 'https://www.google.com/s2/favicons?domain=' + link.domain)}" alt="" onerror="this.style.display='none'">
          </div>
          <div class="chat-link-info">
            <strong>${escapeHtml(link.title || link.url)}</strong>
            <span>${escapeHtml(link.domain || '')} · ${escapeHtml(link.category_name)} · ${escapeHtml(link.profile_name)}</span>
          </div>
        </div>
        <div class="chat-link-meta">
          ${tags}
          ${link.credentials_count ? `<span class="chat-link-tag"><i class="fa-solid fa-key"></i> ${link.credentials_count}</span>` : ''}
          ${link.sublinks_count ? `<span class="chat-link-tag"><i class="fa-solid fa-folder-tree"></i> ${link.sublinks_count}</span>` : ''}
        </div>
        <div class="chat-link-actions">
          <button type="button" class="chat-link-open" data-chat-open-link="${link.id}">
            <i class="fa-solid fa-rocket"></i> Abrir
          </button>
          <button type="button" class="chat-link-copy" data-chat-copy-url="${escapeHtml(link.url)}" title="Copiar URL">
            <i class="fa-regular fa-copy"></i>
          </button>
        </div>`;
      list.appendChild(card);
    });
    container.appendChild(list);
  }
}

function showChatTyping() {
  const box = document.getElementById('chatMessages');
  const wrapper = document.createElement('div');
  wrapper.className = 'chat-msg assistant chat-typing';
  wrapper.id = 'chatTypingIndicator';
  wrapper.innerHTML = `
    <div class="chat-bubble">
      <div class="chat-msg-avatar"><i class="fa-solid fa-robot"></i></div>
      <div class="chat-bubble-body">
        <span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span>
      </div>
    </div>`;
  box.appendChild(wrapper);
  scrollChatToBottom();
}

function hideChatTyping() {
  const el = document.getElementById('chatTypingIndicator');
  if (el) el.remove();
}

async function sendChatMessage(rawMessage) {
  const message = (rawMessage || '').trim();
  if (!message || State.chat.sending) return;

  State.chat.sending = true;
  const sendBtn = document.getElementById('btnChatSend');
  sendBtn.disabled = true;

  API.trackEvent('chat', 'send_message', { length: message.length });
  appendChatMessage('user', message, null, true);
  document.getElementById('chatInput').value = '';
  autoResizeChatInput();
  showChatTyping();
  closeChatHistory();

  try {
    const res = await API.sendChatMessage(message, State.chat.sessionId);
    hideChatTyping();

    if (!res || res.error) {
      appendChatMessage('assistant', (res && res.error) || 'No pude procesar tu mensaje.', null, true);
      showToast((res && res.error) || 'Error del asistente', 'error');
      return;
    }

    State.chat.sessionId = res.session_id;
    localStorage.setItem('pageneitor_chat_session', res.session_id);

    const payload = {
      ...(res.results || {}),
      source: res.source
    };
    appendChatMessage('assistant', res.answer || '', payload, true);
    await loadChatSessions();
    loadChatEngineStatus();
  } catch (err) {
    hideChatTyping();
    appendChatMessage('assistant', 'No pude conectar con el asistente. Revisa que el servidor local esté activo.', null, true);
    showToast('Error de conexión con el asistente', 'error');
  } finally {
    State.chat.sending = false;
    sendBtn.disabled = false;
    autoResizeChatInput();
    setTimeout(() => document.getElementById('chatInput').focus(), 50);
  }
}

async function deleteChatConversation(sessionId) {
  const ok = await safeConfirm(
    '¿Eliminar esta conversación?',
    'Se borrará el historial de mensajes de esta sesión del asistente.'
  );
  if (!ok) return;

  const res = await API.deleteChatSession(sessionId);
  if (res && res.success) {
    if (String(State.chat.sessionId) === String(sessionId)) startNewChat();
    await loadChatSessions();
    showToast('Conversación eliminada', 'info');
  } else {
    showToast('No se pudo eliminar la conversación', 'error');
  }
}

function toggleChatHistory(force) {
  const drawer = document.getElementById('chatHistoryDrawer');
  State.chat.historyOpen = typeof force === 'boolean' ? force : !State.chat.historyOpen;
  drawer.classList.toggle('open', State.chat.historyOpen);
  if (State.chat.historyOpen) loadChatSessions();
}

function closeChatHistory() {
  toggleChatHistory(false);
}

function resetChatAfterRestore() {
  State.chat.sessionId = null;
  State.chat.sessions = [];
  localStorage.removeItem('pageneitor_chat_session');
  resetChatView();
  renderChatSessionList();
  loadChatSessions();

  // Restored data can reuse suggestion IDs; clear toast memory.
  State.domain.toastSeen = [];
  State.domain.suggestions = [];
  State.domain.groups = [];
  State.domain.currentRootDomain = null;
  localStorage.removeItem('pageneitor_domain_toast_seen');
  refreshDomainDashboard(false);
}

function autoResizeChatInput() {
  const input = document.getElementById('chatInput');
  if (!input) return;
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 110) + 'px';
}

// ============================================================
// MAIN VIEW SWITCHING
// ============================================================
function setMainView(view) {
  State.view = view;
  const workspace = document.querySelector('.main-workspace');
  if (workspace) workspace.dataset.view = view;
  const domainView = document.getElementById('domainDetailView');
  const analyticsView = document.getElementById('analyticsView');
  if (domainView) domainView.style.display = view === 'domain' ? 'flex' : 'none';
  if (analyticsView) analyticsView.style.display = view === 'analytics' ? 'flex' : 'none';
}

// ============================================================
// LINK INSERTION ASSISTANT
// ============================================================
function openLinkAssistant(preview = null, targetDomain = null) {
  State.linkAssistant.targetDomain = targetDomain || null;
  State.linkAssistant.preview = preview || null;
  State.linkAssistant.items = preview && preview.items ? [...preview.items] : [];
  State.linkAssistant.lastChatPreview = null;

  document.getElementById('linkAssistantStatus').textContent = targetDomain
    ? `Dominio destino: ${targetDomain}`
    : '';
  document.getElementById('btnLinkAssistantSave').disabled = !preview;

  if (preview) {
    renderAssistantPreview(preview);
  } else {
    document.getElementById('linkAssistantText').value = '';
    document.getElementById('linkAssistantResults').innerHTML =
      '<div class="db-empty">Las propuestas aparecerán aquí.</div>';
  }

  document.getElementById('linkAssistantModal').classList.add('active');
  setTimeout(() => document.getElementById('linkAssistantText').focus(), 100);
  API.trackEvent('assistant', 'open', { target_domain: targetDomain || '' });
}

function renderAssistantPreview(preview) {
  State.linkAssistant.preview = preview;
  State.linkAssistant.items = (preview.items || []).map(item => ({ ...item }));
  const container = document.getElementById('linkAssistantResults');
  const categories = preview.categories || [];
  const profiles = preview.profiles || [];
  const items = State.linkAssistant.items;

  document.getElementById('linkAssistantStatus').innerHTML =
    `<i class="fa-solid fa-circle-info"></i> ${items.length} enlace(s) · ` +
    `Clasificación: <strong>${escapeHtml(preview.source || 'Reglas locales')}</strong>`;

  if (!items.length) {
    container.innerHTML = '<div class="db-empty">No se detectaron enlaces válidos.</div>';
    document.getElementById('btnLinkAssistantSave').disabled = true;
    return;
  }

  container.innerHTML = items.map((item, index) => {
    const categoryOptions = categories.map(c =>
      `<option value="${c.id}" ${String(c.id) === String(item.category_id) ? 'selected' : ''}>${escapeHtml(c.name)}</option>`
    ).join('');
    const profileOptions = profiles.map(p =>
      `<option value="${p.id}" ${String(p.id) === String(item.profile_id) ? 'selected' : ''}>${escapeHtml(p.name)}</option>`
    ).join('');
    const newCategory = item.new_category
      ? `<div class="assistant-new-taxonomy">
           <i class="fa-solid fa-folder-plus"></i> Tema nuevo propuesto:
           <strong>${escapeHtml(item.new_category.name)}</strong>
           <span>${escapeHtml(item.new_category.reason || '')}</span>
         </div>`
      : '';
    const newProfile = item.new_profile
      ? `<div class="assistant-new-taxonomy">
           <i class="fa-solid fa-user-plus"></i> Perfil nuevo propuesto:
           <strong>${escapeHtml(item.new_profile.name)}</strong>
           <span>${escapeHtml(item.new_profile.reason || '')}</span>
         </div>`
      : '';
    const domainBadge = item.domain_exists
      ? `<span class="assistant-badge existing"><i class="fa-solid fa-globe"></i> Dominio existente · ${item.domain_count} enlaces</span>`
      : `<span class="assistant-badge new"><i class="fa-solid fa-star"></i> Dominio nuevo</span>`;
    const duplicateBadge = item.duplicate
      ? '<span class="assistant-badge duplicate"><i class="fa-solid fa-triangle-exclamation"></i> Posible duplicado</span>'
      : '';

    return `
      <div class="assistant-item" data-assistant-index="${index}">
        <div class="assistant-item-thumb">
          ${item.thumbnail_url
            ? `<img src="${escapeHtml(item.thumbnail_url)}" alt="" onerror="this.style.display='none'">`
            : '<i class="fa-solid fa-link"></i>'}
        </div>
        <div class="assistant-item-main">
          <div class="assistant-item-title">${escapeHtml(item.title || item.url)}</div>
          <div class="assistant-item-url">${escapeHtml(item.url)}</div>
          <div class="assistant-badges">${domainBadge}${duplicateBadge}
            <span class="assistant-badge confidence">Confianza ${Math.round((item.confidence || 0) * 100)}%</span>
          </div>
          <div class="assistant-selects">
            <label>Tema<select class="form-control assistant-category">${categoryOptions}</select></label>
            <label>Perfil<select class="form-control assistant-profile">${profileOptions}</select></label>
          </div>
          <div class="assistant-tags-row">
            <label>Etiquetas<input type="text" class="form-control assistant-tags" value="${escapeHtml((item.tags || []).join(', '))}"></label>
          </div>
          ${newCategory}
          ${newProfile}
        </div>
        <button type="button" class="icon-action-btn delete-btn assistant-remove" title="Quitar de la lista">
          <i class="fa-solid fa-xmark"></i>
        </button>
      </div>`;
  }).join('');

  document.getElementById('btnLinkAssistantSave').disabled = false;
}

function collectAssistantItems() {
  const cards = document.querySelectorAll('#linkAssistantResults .assistant-item');
  const result = [];
  cards.forEach(card => {
    const index = parseInt(card.getAttribute('data-assistant-index'), 10);
    const item = State.linkAssistant.items[index];
    if (!item) return;
    const category = card.querySelector('.assistant-category');
    const profile = card.querySelector('.assistant-profile');
    const tags = card.querySelector('.assistant-tags');
    const copy = { ...item };
    copy.category_id = category && category.value ? parseInt(category.value, 10) : null;
    copy.profile_id = profile && profile.value ? parseInt(profile.value, 10) : null;
    copy.tags = (tags ? tags.value : '')
      .split(',')
      .map(t => t.trim().replace(/^#/, ''))
      .filter(Boolean);
    result.push(copy);
  });
  return result;
}

async function analyzeAssistantLinks() {
  const text = document.getElementById('linkAssistantText').value.trim();
  if (!text) {
    showToast('Pega al menos una URL', 'info');
    return;
  }
  const btn = document.getElementById('btnLinkAssistantAnalyze');
  const status = document.getElementById('linkAssistantStatus');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Analizando...';
  status.textContent = 'Extrayendo metadatos y clasificando con IA local...';
  try {
    const preview = await API.previewLinks(text, true);
    if (!preview || preview.success === false) {
      status.textContent = (preview && preview.error) || 'No se pudo analizar.';
      showToast(status.textContent, 'error');
      return;
    }
    renderAssistantPreview(preview);
    API.trackEvent('assistant', 'preview', { count: (preview.items || []).length, source: preview.source });
  } catch (err) {
    status.textContent = 'Error al analizar los enlaces.';
    showToast('Error del asistente de enlaces', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-magnifying-glass-chart"></i> Analizar enlaces';
  }
}

async function saveAssistantLinks() {
  const items = collectAssistantItems();
  if (!items.length) {
    showToast('No hay enlaces para guardar', 'info');
    return;
  }
  const acceptCats = document.getElementById('chkAcceptNewCategories').checked;
  const acceptProfs = document.getElementById('chkAcceptNewProfiles').checked;
  const skipDup = document.getElementById('chkSkipDuplicates').checked;

  const btn = document.getElementById('btnLinkAssistantSave');
  btn.disabled = true;
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Guardando...';
  try {
    const res = await API.commitAssistantLinks(items, acceptCats, acceptProfs, skipDup);
    if (res && res.success) {
      const parts = [`${res.created_count || 0} guardados`];
      if (res.skipped_count) parts.push(`${res.skipped_count} omitidos`);
      if (res.error_count) parts.push(`${res.error_count} errores`);
      showToast(`Asistente: ${parts.join(' · ')}`, 'success');
      document.getElementById('linkAssistantModal').classList.remove('active');
      await refreshAllData();
      await refreshDomainDashboard(false);
      if (State.view === 'domain' && State.domainDetail) {
        await openDomainDetail(State.domainDetail.root_domain);
      }
      API.trackEvent('assistant', 'commit', {
        created: res.created_count,
        skipped: res.skipped_count,
        errors: res.error_count
      });
    } else {
      showToast((res && (res.error || 'No se pudieron guardar los enlaces')) || 'Error', 'error');
    }
  } catch (err) {
    showToast('Error al guardar los enlaces', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fa-solid fa-floppy-disk"></i> Guardar enlaces confirmados';
  }
}

// ============================================================
// DOMAIN DETAIL VIEW
// ============================================================
async function openDomainDetail(rootDomain) {
  if (!rootDomain) return;
  setMainView('domain');
  State.domain.currentRootDomain = rootDomain;
  renderSidebarDomains();
  updateFilterBanner();

  const detail = await API.getDomainDetail(rootDomain);
  if (!detail || detail.error) {
    showToast(detail && detail.error ? detail.error : 'No se pudo abrir el dominio', 'error');
    setMainView('links');
    return;
  }
  State.domainDetail = detail;
  renderDomainDetail(detail);
  API.trackEvent('domain', 'open_detail', { root_domain: rootDomain, count: detail.count });
}

function renderDomainDetail(detail) {
  document.getElementById('domainDetailName').textContent = detail.root_domain;
  document.getElementById('domainDetailSubtitle').textContent =
    `${detail.count} enlaces · ${detail.stats.total_visits} visitas · ` +
    `${detail.stats.thumbnail_coverage}% con miniatura`;

  const s = detail.stats;
  document.getElementById('domainDetailKpis').innerHTML = [
    ['Enlaces', detail.count],
    ['Visitas', s.total_visits],
    ['Favoritos', s.favorites],
    ['Pendientes', s.unread],
    ['Credenciales', s.credentials],
    ['Sub-enlaces', s.sublinks],
    ['Media visitas', s.avg_visits],
    ['Miniaturas', s.thumbnail_coverage + '%'],
  ].map(([label, value]) => `
    <div class="detail-kpi">
      <span>${escapeHtml(String(label))}</span>
      <strong>${escapeHtml(String(value))}</strong>
    </div>`).join('');

  renderDomainDetailCharts(detail);

  const linksBox = document.getElementById('domainDetailLinks');
  linksBox.innerHTML = '';
  (detail.links || []).forEach(link => linksBox.appendChild(createLinkCardElement(link)));
  document.getElementById('domainDetailLinkCount').textContent =
    `${detail.count} ${detail.count === 1 ? 'enlace' : 'enlaces'}`;
}

function renderDomainDetailCharts(detail) {
  if (typeof Chart === 'undefined') return;
  if (State.domainDetailCharts) {
    Object.values(State.domainDetailCharts).forEach(chart => {
      try { chart.destroy(); } catch (err) {}
    });
  }
  State.domainDetailCharts = {};

  const colors = ['#6366f1', '#06b6d4', '#ec4899', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444'];

  const catCanvas = document.getElementById('domainDetailCategoryChart');
  if (catCanvas && (detail.categories || []).length) {
    State.domainDetailCharts.category = new Chart(catCanvas, {
      type: 'doughnut',
      data: {
        labels: detail.categories.map(x => x.name),
        datasets: [{
          data: detail.categories.map(x => x.count),
          backgroundColor: detail.categories.map((_, i) => colors[i % colors.length]),
          borderWidth: 0
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '68%',
        plugins: { legend: { position: 'bottom', labels: { color: getComputedStyle(document.documentElement).getPropertyValue('--text-secondary') || '#94a3b8', boxWidth: 8, font: { size: 10 } } } }
      }
    });
  }

  const profCanvas = document.getElementById('domainDetailProfileChart');
  if (profCanvas && (detail.profiles || []).length) {
    State.domainDetailCharts.profile = new Chart(profCanvas, {
      type: 'bar',
      data: {
        labels: detail.profiles.map(x => x.name),
        datasets: [{
          data: detail.profiles.map(x => x.count),
          backgroundColor: colors,
          borderRadius: 5
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { color: '#94a3b8', font: { size: 10 } } },
          y: { grid: { color: 'rgba(255,255,255,0.06)' }, ticks: { precision: 0, color: '#94a3b8' } }
        }
      }
    });
  }
}

// ============================================================
// ANALYTICS & KPI SECTION
// ============================================================
async function openAnalyticsView() {
  setMainView('analytics');
  await loadAnalyticsView(false);
  API.trackEvent('analytics', 'open_view');
}

async function loadAnalyticsView(force = false) {
  const kpis = document.getElementById('analyticsKpis');
  if (kpis) kpis.innerHTML = '<div class="db-empty">Calculando métricas...</div>';
  try {
    const snapshot = await API.getAnalyticsOverview(force);
    State.analytics.snapshot = snapshot;
    applyAnalyticsMode();
    renderAnalyticsKpis(snapshot);
    renderAnalyticsCharts(snapshot);
    renderDescriptiveTable(snapshot);
    renderAnalyticsQuality(snapshot);
    await renderAnalyticsEvents();
  } catch (err) {
    console.error('Error cargando analíticas:', err);
    if (kpis) kpis.innerHTML = '<div class="db-empty">No se pudieron calcular las métricas.</div>';
  }
}

function renderAnalyticsKpis(snapshot) {
  const k = snapshot.kpis || {};
  const items = [
    ['Enlaces activos', k.total_links],
    ['Dominios', k.domains],
    ['Temas', k.categories],
    ['Perfiles', k.profiles],
    ['Favoritos', k.favorites],
    ['Pendientes', k.unread],
    ['Credenciales', k.credentials],
    ['Subenlaces', k.sublinks],
    ['Cobertura miniaturas', `${k.thumbnail_coverage}%`],
    ['Nivel', k.level],
    ['Trofeos', k.trophies],
    ['Sugerencias pendientes', k.pending_suggestions],
  ];
  document.getElementById('analyticsKpis').innerHTML = items.map(([label, value]) => `
    <div class="analytics-kpi">
      <span>${escapeHtml(String(label))}</span>
      <strong>${escapeHtml(String(value))}</strong>
    </div>`).join('');
}

function destroyAnalyticsCharts() {
  if (State.analytics.charts.chartjs) {
    Object.values(State.analytics.charts.chartjs).forEach(chart => {
      try { chart.destroy(); } catch (err) {}
    });
  }
  State.analytics.charts = { chartjs: {} };
}

function renderAnalyticsCharts(snapshot) {
  destroyAnalyticsCharts();
  const css = getComputedStyle(document.documentElement);
  const textColor = css.getPropertyValue('--text-secondary') || '#94a3b8';

  if (typeof Chart !== 'undefined') {
    const linksCanvas = document.getElementById('analyticsLinksChart');
    const linksData = snapshot.timeseries.links_added || [];
    if (linksCanvas) {
      State.analytics.charts.chartjs.links = new Chart(linksCanvas, {
        type: 'line',
        data: {
          labels: linksData.map(x => x.date.slice(5)),
          datasets: [{
            label: 'Enlaces añadidos',
            data: linksData.map(x => x.count),
            borderColor: '#6366f1',
            backgroundColor: 'rgba(99,102,241,0.16)',
            fill: true,
            tension: 0.35,
            pointRadius: 2
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { display: false }, ticks: { color: textColor, font: { size: 9 } } },
            y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.06)' }, ticks: { precision: 0, color: textColor } }
          }
        }
      });
    }

    const catCanvas = document.getElementById('analyticsCategoryChart');
    const cats = (snapshot.top.categories || []).filter(c => c.count > 0);
    if (catCanvas) {
      State.analytics.charts.chartjs.categories = new Chart(catCanvas, {
        type: 'doughnut',
        data: {
          labels: cats.map(c => c.name),
          datasets: [{
            data: cats.map(c => c.count),
            backgroundColor: cats.map(c => c.color || '#6366f1'),
            borderWidth: 0
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          cutout: '66%',
          plugins: {
            legend: { position: 'right', labels: { color: textColor, boxWidth: 8, font: { size: 9 } } }
          }
        }
      });
    }
  }

  if (typeof Highcharts !== 'undefined') {
    const domains = snapshot.top.domains || [];
    Highcharts.chart('analyticsDomainsChart', {
      chart: { type: 'bar', backgroundColor: 'transparent', height: 245 },
      title: { text: null },
      credits: { enabled: false },
      xAxis: {
        categories: domains.map(d => d.name),
        labels: { style: { color: '#94a3b8', fontSize: '9px' } }
      },
      yAxis: {
        title: { text: null },
        gridLineColor: 'rgba(255,255,255,0.06)',
        labels: { style: { color: '#94a3b8' } }
      },
      legend: { enabled: false },
      plotOptions: { bar: { borderRadius: 3, color: '#6366f1' } },
      series: [{ name: 'Enlaces', data: domains.map(d => d.count) }]
    });

    const hourly = snapshot.activity.hourly || [];
    Highcharts.chart('analyticsHeatmapChart', {
      chart: { type: 'heatmap', backgroundColor: 'transparent', height: 245 },
      title: { text: null },
      credits: { enabled: false },
      xAxis: {
        categories: hourly.map(h => `${String(h.hour).padStart(2, '0')}h`),
        labels: { style: { color: '#94a3b8', fontSize: '8px' } }
      },
      yAxis: {
        categories: ['Actividad'],
        title: { text: null },
        labels: { style: { color: '#94a3b8' } }
      },
      colorAxis: { min: 0, minColor: 'rgba(99,102,241,0.08)', maxColor: '#6366f1' },
      legend: { enabled: false },
      series: [{
        name: 'Eventos',
        borderWidth: 1,
        borderColor: 'rgba(0,0,0,0.15)',
        data: hourly.map((h, i) => [i, 0, h.count]),
        dataLabels: { enabled: false }
      }]
    });
  }

  if (typeof Plotly !== 'undefined') {
    const domains = snapshot.top.domains || [];
    const cats = (snapshot.top.categories || []).filter(c => c.count > 0);
    const labels = ['Dominios', ...domains.map(d => d.name), 'Temas', ...cats.map(c => c.name)];
    const parents = ['', ...domains.map(() => 'Dominios'), '', ...cats.map(() => 'Temas')];
    const values = [domains.reduce((a, d) => a + d.count, 0), ...domains.map(d => d.count), cats.reduce((a, c) => a + c.count, 0), ...cats.map(c => c.count)];
    Plotly.newPlot('analyticsTreemapChart', [{
      type: 'treemap',
      labels,
      parents,
      values,
      textinfo: 'label+value',
      marker: { colorscale: 'Blues', line: { color: 'rgba(10,15,28,0.5)', width: 1 } },
      hovertemplate: '%{label}: %{value}<extra></extra>'
    }], {
      margin: { t: 0, l: 0, r: 0, b: 0 },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      font: { color: '#cbd5e1', size: 10 }
    }, { displayModeBar: false, responsive: true });

    const scatter = snapshot.scatter || [];
    Plotly.newPlot('analyticsScatterChart', [{
      x: scatter.map(x => x.visits),
      y: scatter.map(x => x.tags),
      text: scatter.map(x => x.title),
      mode: 'markers',
      type: 'scatter',
      marker: {
        size: scatter.map(x => 8 + (x.credentials || 0) * 3 + (x.sublinks || 0) * 2),
        color: scatter.map(x => x.thumbnail),
        colorscale: [[0, '#ef4444'], [1, '#10b981']],
        opacity: 0.8,
        line: { width: 1, color: 'rgba(255,255,255,0.25)' }
      },
      hovertemplate: '%{text}<br>Visitas: %{x}<br>Etiquetas: %{y}<extra></extra>'
    }], {
      margin: { t: 10, l: 35, r: 10, b: 35 },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      font: { color: '#94a3b8', size: 10 },
      xaxis: { title: 'Visitas', gridcolor: 'rgba(255,255,255,0.06)' },
      yaxis: { title: 'Etiquetas', gridcolor: 'rgba(255,255,255,0.06)' }
    }, { displayModeBar: false, responsive: true });
  }
}

function renderDescriptiveTable(snapshot) {
  const table = document.getElementById('analyticsDescriptiveTable');
  const descriptive = snapshot.descriptive || {};
  const names = {
    links_per_domain: 'Enlaces por dominio',
    links_per_category: 'Enlaces por tema',
    links_per_profile: 'Enlaces por perfil',
    visits: 'Visitas por enlace',
    tags_per_link: 'Etiquetas por enlace',
    credentials_per_link: 'Credenciales por enlace',
    sublinks_per_link: 'Subenlaces por enlace',
  };
  const rows = Object.keys(names).map(key => {
    const d = descriptive[key] || {};
    return `<tr><td>${names[key]}</td><td>${d.mean ?? 0}</td><td>${d.median ?? 0}</td><td>${d.mode ?? 0}</td><td>${d.stddev ?? 0}</td><td>${d.p25 ?? 0}</td><td>${d.p75 ?? 0}</td><td>${d.p90 ?? 0}</td></tr>`;
  }).join('');
  table.innerHTML = `
    <table class="analytics-table">
      <thead><tr><th>Métrica</th><th>Media</th><th>Mediana</th><th>Moda</th><th>Desv.</th><th>P25</th><th>P75</th><th>P90</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function renderAnalyticsQuality(snapshot) {
  const q = snapshot.quality || {};
  const items = [
    ['Sin miniatura', q.missing_thumbnails, q.missing_thumbnails ? 'warning' : 'ok'],
    ['Sin tema', q.missing_category, q.missing_category ? 'warning' : 'ok'],
    ['Sin perfil', q.missing_profile, q.missing_profile ? 'warning' : 'ok'],
    ['Sin etiquetas', q.missing_tags, q.missing_tags ? 'warning' : 'ok'],
    ['Sin notas', q.missing_notes, 'info'],
    ['Duplicados', q.duplicate_count, q.duplicate_count ? 'danger' : 'ok'],
    ['Cobertura miniaturas', `${q.thumbnail_coverage}%`, 'info'],
  ];
  document.getElementById('analyticsQuality').innerHTML = items.map(([label, value, cls]) => `
    <div class="quality-card ${cls}">
      <span>${escapeHtml(String(label))}</span>
      <strong>${escapeHtml(String(value))}</strong>
    </div>`).join('');
}

async function renderAnalyticsEvents() {
  const box = document.getElementById('analyticsEventsTable');
  if (!box) return;
  const events = await API.getAnalyticsEvents(80);
  const snapshot = State.analytics.snapshot || {};
  const api = snapshot.api || {};
  const endpoints = (api.top_endpoints || []).map(e =>
    `<tr><td>${escapeHtml(e.path)}</td><td>${e.count}</td></tr>`
  ).join('');
  const rows = (events || []).slice(0, 50).map(e => `
    <tr>
      <td>${escapeHtml(e.event_type || '')}</td>
      <td>${escapeHtml(e.action || '')}</td>
      <td>${escapeHtml((e.created_at || '').slice(0, 19))}</td>
      <td>${escapeHtml(JSON.stringify(e.metadata || {}).slice(0, 80))}</td>
    </tr>`).join('');
  box.innerHTML = `
    <div class="analytics-subtitle">Rendimiento de la API</div>
    <div class="analytics-inline-metrics">
      <span>Latencia media: <strong>${api.avg_latency_ms || 0} ms</strong></span>
      <span>P95: <strong>${api.p95_latency_ms || 0} ms</strong></span>
      <span>Llamadas medidas: <strong>${api.count || 0}</strong></span>
    </div>
    <table class="analytics-table compact">
      <thead><tr><th>Endpoint</th><th>Llamadas</th></tr></thead>
      <tbody>${endpoints || '<tr><td colspan="2">Sin datos</td></tr>'}</tbody>
    </table>
    <div class="analytics-subtitle" style="margin-top:14px;">Últimos eventos</div>
    <table class="analytics-table compact">
      <thead><tr><th>Tipo</th><th>Acción</th><th>Fecha</th><th>Metadata</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="4">Sin eventos</td></tr>'}</tbody>
    </table>`;
}

async function generateAnalyticsInsights() {
  const box = document.getElementById('analyticsInsights');
  const source = document.getElementById('analyticsInsightSource');
  box.innerHTML = '<div class="db-empty"><i class="fa-solid fa-spinner fa-spin"></i> Ollama está analizando las métricas...</div>';
  const res = await API.getAnalyticsInsights(true);
  if (res && res.insights) {
    box.innerHTML = `<ul>${res.insights.map(x => `<li>${escapeHtml(x)}</li>`).join('')}</ul>`;
    source.textContent = `Fuente: ${res.source || 'local'} · ${res.generated_at || ''}`;
    State.analytics.insights = res;
  } else {
    box.innerHTML = '<div class="db-empty">No se pudo generar el análisis.</div>';
  }
}

function applyAnalyticsMode() {
  const view = document.getElementById('analyticsView');
  const advanced = State.analytics.mode === 'advanced';
  view.classList.toggle('mode-advanced', advanced);
  document.getElementById('btnAnalyticsMode').innerHTML = advanced
    ? '<i class="fa-solid fa-user"></i> Modo principiante'
    : '<i class="fa-solid fa-user-graduate"></i> Modo avanzado';
}

function toggleAnalyticsMode() {
  State.analytics.mode = State.analytics.mode === 'advanced' ? 'beginner' : 'advanced';
  localStorage.setItem('pageneitor_analytics_mode', State.analytics.mode);
  applyAnalyticsMode();
  if (State.analytics.mode === 'advanced' && State.analytics.snapshot) {
    setTimeout(() => {
      renderAnalyticsCharts(State.analytics.snapshot);
      renderAnalyticsEvents();
    }, 60);
  }
  API.trackEvent('analytics', 'toggle_mode', { mode: State.analytics.mode });
}

function exportAnalyticsJson() {
  const data = State.analytics.snapshot;
  if (!data) return;
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `pageneitor_analytics_${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  showToast('Estadísticas exportadas', 'success');
  API.trackEvent('analytics', 'export_json');
}

// ============================================================
// LAYERED BACKGROUND: LLM WORD CLOUD + SYSTEM INFO
// ============================================================
async function initBackgroundLayers() {
  await loadWordCloud();
  await refreshSystemInfoLayer();

  if (State.wordcloud.timer) clearInterval(State.wordcloud.timer);
  State.wordcloud.timer = setInterval(rotateWordCloud, Math.max(15, State.wordcloud.rotation) * 1000);

  if (!State.wordcloud.refreshTimer) {
    State.wordcloud.refreshTimer = setInterval(loadWordCloud, 5 * 60 * 1000);
  }
  if (!State.backgroundInfoTimer) {
    State.backgroundInfoTimer = setInterval(refreshSystemInfoLayer, 60 * 1000);
  }

  window.addEventListener('resize', () => {
    drawWordCloud();
    refreshSystemInfoLayer();
  });
}

async function loadWordCloud() {
  try {
    const data = await API.getWordCloud(false);
    State.wordcloud.sets = data.sets || [];
    State.wordcloud.index = 0;
    State.wordcloud.rotation = data.rotation || 60;
    State.wordcloud.source = data.source || '';
    if (State.wordcloud.timer) {
      clearInterval(State.wordcloud.timer);
      State.wordcloud.timer = setInterval(rotateWordCloud, Math.max(15, State.wordcloud.rotation) * 1000);
    }
    drawWordCloud();
  } catch (err) {
    console.warn('No se pudo cargar la nube de palabras:', err);
  }
}

function rotateWordCloud() {
  if (!State.wordcloud.sets.length) return;
  State.wordcloud.index = (State.wordcloud.index + 1) % State.wordcloud.sets.length;
  const canvas = document.getElementById('wordCloudCanvas');
  if (!canvas) return;
  canvas.style.opacity = '0';
  setTimeout(() => {
    drawWordCloud();
    canvas.style.opacity = '1';
  }, 450);
}

function drawWordCloud() {
  const canvas = document.getElementById('wordCloudCanvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const width = window.innerWidth;
  const height = window.innerHeight;
  canvas.width = width * dpr;
  canvas.height = height * dpr;
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);

  const sets = State.wordcloud.sets || [];
  if (!sets.length) return;
  const words = sets[State.wordcloud.index % sets.length] || [];
  if (!words.length) return;

  const css = getComputedStyle(document.documentElement);
  const palette = [
    css.getPropertyValue('--primary') || '#6366f1',
    '#38bdf8',
    '#a855f7',
    '#34d399',
    css.getPropertyValue('--text-bright') || '#f8fafc',
  ];
  const cols = 6;
  const rows = Math.max(3, Math.ceil(words.length / cols));
  const cellW = width / cols;
  const cellH = height / Math.max(rows + 1, 5);
  const rnd = mulberry32(State.wordcloud.index + 31);

  words.slice(0, cols * rows).forEach((word, index) => {
    const col = index % cols;
    const row = Math.floor(index / cols);
    const weight = Math.max(1, Math.min(100, word.weight || 40));
    const size = Math.max(14, Math.min(52, 14 + weight * 0.38));
    const x = col * cellW + cellW * (0.18 + rnd() * 0.64);
    const y = cellH * (row + 1) + cellH * (0.15 + rnd() * 0.7);
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate((rnd() - 0.5) * 0.12);
    ctx.globalAlpha = 0.10 + (weight / 100) * 0.11;
    ctx.font = `${weight >= 70 ? '800' : '600'} ${size}px 'Segoe UI', sans-serif`;
    ctx.fillStyle = palette[index % palette.length];
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(word.text || '', 0, 0);
    ctx.restore();
  });
  State.wordcloud.drawnAt = Date.now();
}

function mulberry32(seed) {
  let a = seed;
  return function () {
    a |= 0;
    a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

async function refreshSystemInfoLayer() {
  const layer = document.getElementById('systemInfoLayer');
  if (!layer) return;
  try {
    const [snapshot, ollama] = await Promise.all([
      API.getAnalyticsOverview(false),
      API.getOllamaStatus().catch(() => null),
    ]);
    const today = new Date().toISOString().slice(0, 10);
    const todayEvents = (snapshot.events.daily || []).find(d => d.date === today);
    const items = [
      ['ENLACES', snapshot.kpis.total_links],
      ['DOMINIOS', snapshot.kpis.domains],
      ['TEMAS', snapshot.kpis.categories],
      ['PERFILES', snapshot.kpis.profiles],
      ['NIVEL', snapshot.kpis.level],
      ['LOGROS', snapshot.kpis.trophies],
      ['ACTIVIDAD HOY', todayEvents ? todayEvents.count : 0],
      ['OLLAMA', ollama && ollama.is_running ? 'ACTIVO' : 'LOCAL'],
    ];
    layer.innerHTML = items.map(([label, value]) => `
      <div class="bg-info-item">
        <span>${escapeHtml(String(label))}</span>
        <strong>${escapeHtml(String(value))}</strong>
      </div>`).join('');
  } catch (err) {
    // Background layer is decorative; silent failure is intentional.
  }
}

async function handleLinkCardAction(action, id, target, url) {
  const findLink = () => (
    State.links.find(l => String(l.id) === String(id)) ||
    ((State.domainDetail && State.domainDetail.links) || []).find(l => String(l.id) === String(id))
  );

  if (action === 'open-link') {
    try {
      const res = await API.openInBrowser(id);
      showToast('Enlace abierto en el navegador', 'success');
      if (res && res._gamification) handleGamificationEventResult(res._gamification);
      const card = document.getElementById(`link-card-${id}`);
      if (card) {
        const readBtn = card.querySelector('[data-action="toggle-read"]');
        if (readBtn) readBtn.innerHTML = '<i class="fa-solid fa-check-double" style="color: #34d399;"></i>';
      }
      loadStats();
      API.trackEvent('link', 'open', { link_id: id }, 'link', id);
    } catch (err) {
      showToast('Error al abrir navegador', 'error');
    }
  } else if (action === 'toggle-fav') {
    const link = findLink();
    if (link) {
      const newVal = link.is_favorite ? 0 : 1;
      link.is_favorite = newVal;
      target.classList.toggle('active', newVal === 1);
      await API.updateLink(id, { is_favorite: newVal });
      loadStats();
      showToast(newVal ? 'Añadido a Favoritos' : 'Eliminado de Favoritos');
      API.trackEvent('link', 'toggle_favorite', { value: newVal }, 'link', id);
    }
  } else if (action === 'toggle-read') {
    const link = findLink();
    if (link) {
      const newVal = link.is_read ? 0 : 1;
      link.is_read = newVal;
      target.innerHTML = `<i class="fa-solid ${newVal ? 'fa-check-double' : 'fa-clock'}" style="${newVal ? 'color: #34d399;' : ''}"></i>`;
      await API.updateLink(id, { is_read: newVal });
      loadStats();
      loadGamification();
      showToast(newVal ? 'Marcado como leído' : 'Marcado como pendiente');
      API.trackEvent('link', 'toggle_read', { value: newVal }, 'link', id);
    }
  } else if (action === 'open-credentials') {
    openCredentialsModal(id);
  } else if (action === 'open-sublinks') {
    openSublinksModal(id);
  } else if (action === 'copy-url') {
    copyTextToClipboard(url);
  } else if (action === 'edit-link') {
    openEditLinkModal(id);
  } else if (action === 'delete-link') {
    const ok = await safeConfirm(
      '¿Podar este enlace?',
      'Eliminar enlaces obsoletos libera espacio y otorga +25 XP de Poda Saludable.'
    );
    if (ok) {
      const res = await API.deleteLink(id);
      const card = document.getElementById(`link-card-${id}`);
      if (card) card.remove();
      showToast('¡Enlace podado! (+25 XP)', 'success');
      if (res && res._gamification) handleGamificationEventResult(res._gamification);
      loadStats();
      loadAnalytics();
      API.trackEvent('link', 'delete', {}, 'link', id);
      if (State.view === 'domain' && State.domainDetail) {
        await openDomainDetail(State.domainDetail.root_domain);
      }
    }
  }
}

// ============================================================
// EVENT LISTENERS SETUP
// ============================================================
function setupEventListeners() {
  // Brand Home
  document.getElementById('btnLogoHome').addEventListener('click', () => {
    State.currentProfileId = null;
    State.currentCategoryId = null;
    State.domain.currentRootDomain = null;
    State.domainDetail = null;
    State.activeView = 'all';
    State.searchQuery = '';
    document.getElementById('searchInput').value = '';
    setMainView('links');
    loadLinks();
    renderSidebarProfiles();
    renderSidebarCategories();
    renderSidebarDomains();
  });

  // Level Details Modal Trigger
  document.getElementById('btnOpenLevelDetail').addEventListener('click', () => {
    renderLevelDetailModal();
    document.getElementById('levelDetailModal').classList.add('active');
  });
  document.getElementById('btnCloseLevelModal').addEventListener('click', () => {
    document.getElementById('levelDetailModal').classList.remove('active');
  });
  document.getElementById('btnCelebrateLevel').addEventListener('click', () => {
    playConsoleTrophySound();
    triggerConfettiBurst(0.5);
  });

  // Display Mode Buttons (Dark / Light / High-Contrast)
  document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const mode = btn.getAttribute('data-mode');
      State.currentMode = mode;
      localStorage.setItem('pageneitor_mode', mode);
      applyThemeAndMode();
      API.trackEvent('ui', 'change_mode', { mode });
    });
  });

  // Single Actions Dropdown Toggle
  const actionsMenuBtn = document.getElementById('btnToggleActionsMenu');
  const actionsDropdown = document.getElementById('actionsDropdownMenu');

  actionsMenuBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    actionsDropdown.classList.toggle('show');
  });

  document.addEventListener('click', (e) => {
    if (!actionsDropdown.contains(e.target) && e.target !== actionsMenuBtn) {
      actionsDropdown.classList.remove('show');
    }
  });

  // Actions Menu Items
  document.getElementById('menuActionNewLink').addEventListener('click', () => {
    actionsDropdown.classList.remove('show');
    openNewLinkModal();
  });
  document.getElementById('menuActionPaste').addEventListener('click', () => {
    actionsDropdown.classList.remove('show');
    handlePasteFromClipboard();
  });
  document.getElementById('menuActionBatch').addEventListener('click', () => {
    actionsDropdown.classList.remove('show');
    document.getElementById('batchModal').classList.add('active');
  });
  document.getElementById('menuActionLinkAssistant').addEventListener('click', () => {
    actionsDropdown.classList.remove('show');
    openLinkAssistant();
  });
  document.getElementById('menuActionAnalytics').addEventListener('click', () => {
    actionsDropdown.classList.remove('show');
    openAnalyticsView();
  });
  document.getElementById('menuActionToggleDashboard').addEventListener('click', () => {
    actionsDropdown.classList.remove('show');
    State.isDashboardOpen = !State.isDashboardOpen;
    const d = document.getElementById('dashboardSection');
    d.classList.toggle('show', State.isDashboardOpen);
    document.getElementById('menuDashboardText').textContent = State.isDashboardOpen ? 'Ocultar Gráficas & KPIs' : 'Ver Gráficas & KPIs';
    if (State.isDashboardOpen) renderChartsZeroFlicker();
  });
  document.getElementById('menuActionTrophies').addEventListener('click', () => {
    actionsDropdown.classList.remove('show');
    renderTrophiesModal();
    document.getElementById('trophiesModal').classList.add('active');
  });
  document.getElementById('kpiTrophiesCard').addEventListener('click', () => {
    renderTrophiesModal();
    document.getElementById('trophiesModal').classList.add('active');
  });
  document.getElementById('btnCloseTrophiesModal').addEventListener('click', () => {
    document.getElementById('trophiesModal').classList.remove('active');
  });
  document.getElementById('menuActionCyclicTip').addEventListener('click', () => {
    actionsDropdown.classList.remove('show');
    triggerAITip(true);
  });
  document.getElementById('btnRefreshTip').addEventListener('click', () => {
    triggerAITip(true);
  });

  // Control Panel Open & Tabs
  document.getElementById('menuActionControlPanel').addEventListener('click', () => {
    actionsDropdown.classList.remove('show');
    renderThemesSelector();
    renderControlPanelProfiles();
    renderControlPanelCategories();
    renderOllamaStatus();
    loadDatabasePanel();
    document.getElementById('controlPanelModal').classList.add('active');
  });
  document.getElementById('btnCloseControlPanel').addEventListener('click', () => {
    document.getElementById('controlPanelModal').classList.remove('active');
  });

  document.querySelectorAll('.cp-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.cp-tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.cp-tab-content').forEach(c => c.classList.remove('active'));

      btn.classList.add('active');
      const tabName = btn.getAttribute('data-cptab');
      if (tabName === 'themes') document.getElementById('cpTabThemes').classList.add('active');
      if (tabName === 'profiles') document.getElementById('cpTabProfiles').classList.add('active');
      if (tabName === 'categories') document.getElementById('cpTabCategories').classList.add('active');
      if (tabName === 'ollama') document.getElementById('cpTabOllama').classList.add('active');
      if (tabName === 'database') {
        document.getElementById('cpTabDatabase').classList.add('active');
        loadDatabasePanel();
      }
    });
  });

  // Sidebar Accordions Toggle
  document.getElementById('toggleProfilesAccordion').addEventListener('click', () => {
    document.getElementById('accordionProfiles').classList.toggle('collapsed');
  });
  document.getElementById('toggleCategoriesAccordion').addEventListener('click', () => {
    document.getElementById('accordionCategories').classList.toggle('collapsed');
  });

  // Control Panel Profile & Category creation triggers
  document.getElementById('btnCpNewProfile').addEventListener('click', () => {
    newProfileDialog();
  });
  document.getElementById('btnCpNewCategory').addEventListener('click', () => {
    newCategoryDialog();
  });

  // Ollama Start & Config
  document.getElementById('btnStartOllama').addEventListener('click', async () => {
    const btn = document.getElementById('btnStartOllama');
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Iniciando...';
    const res = await API.startOllama();
    btn.innerHTML = '<i class="fa-solid fa-play"></i> Iniciar Servidor Ollama';
    showToast(res.message, res.success ? 'success' : 'error');
    await loadOllamaStatus();
  });

  document.getElementById('btnTestOllamaTip').addEventListener('click', () => {
    triggerAITip(true);
  });

  document.getElementById('ollamaModelSelect').addEventListener('change', async (e) => {
    const model = e.target.value;
    const host = document.getElementById('ollamaHostInput').value;
    await API.configOllama(host, model);
    showToast(`Modelo activo: ${model}`, 'info');
  });

  // Filter chips in main view
  document.querySelectorAll('.filter-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      State.activeView = chip.getAttribute('data-chip');
      loadLinks();
      API.trackEvent('ui', 'filter', { filter: State.activeView });
    });
  });

  // Search input
  let searchTimeout = null;
  document.getElementById('searchInput').addEventListener('input', (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      State.searchQuery = e.target.value.trim();
      loadLinks();
      if (State.searchQuery) {
        API.trackEvent('ui', 'search', { length: State.searchQuery.length });
      }
    }, 250);
  });

  // Clear Filter banner button
  document.getElementById('btnClearFilter').addEventListener('click', () => {
    State.currentProfileId = null;
    State.currentCategoryId = null;
    State.domain.currentRootDomain = null;
    State.domainDetail = null;
    State.searchQuery = '';
    State.activeView = 'all';
    document.getElementById('searchInput').value = '';
    setMainView('links');
    loadLinks();
    renderSidebarProfiles();
    renderSidebarCategories();
    renderSidebarDomains();
  });

  // Card Delegation (Zero-flicker: updates only clicked element!)
  document.getElementById('linksGrid').addEventListener('click', async (e) => {
    const domainTarget = e.target.closest('[data-domain-action]');
    if (domainTarget) {
      handleDomainGroupAction(
        domainTarget.getAttribute('data-domain-action'),
        domainTarget.getAttribute('data-domain')
      );
      return;
    }

    const target = e.target.closest('[data-action]');
    if (!target) return;

    const action = target.getAttribute('data-action');
    const id = target.getAttribute('data-id');
    const url = target.getAttribute('data-url');
    await handleLinkCardAction(action, id, target, url);
  });

  // Modal Closers
  document.getElementById('btnCloseLinkModal').addEventListener('click', closeLinkModal);
  document.getElementById('btnCancelLink').addEventListener('click', closeLinkModal);
  document.getElementById('btnCloseBatchModal').addEventListener('click', () => document.getElementById('batchModal').classList.remove('active'));
  document.getElementById('btnCancelBatch').addEventListener('click', () => document.getElementById('batchModal').classList.remove('active'));

  // ---- Link form credentials repeater ----
  document.getElementById('btnAddFormCredential').addEventListener('click', () => {
    addFormCredentialRow();
    const rows = document.querySelectorAll('#formCredentialsList .form-credential-row');
    if (rows.length) rows[rows.length - 1].querySelector('.fcred-label').focus();
  });
  document.getElementById('formCredentialsList').addEventListener('click', (e) => {
    const btn = e.target.closest('.btn-remove-form-credential');
    if (!btn) return;
    btn.closest('.form-credential-row').remove();
    updateFormCredentialsEmpty();
  });

  // ---- Credentials vault modal ----
  document.getElementById('btnCloseCredentialsModal').addEventListener('click', () => {
    document.getElementById('credentialsModal').classList.remove('active');
  });
  document.getElementById('credentialForm').addEventListener('submit', saveCredentialForm);
  document.getElementById('btnCancelCredentialEdit').addEventListener('click', resetCredentialForm);
  document.getElementById('btnToggleCredPassword').addEventListener('click', () => {
    const input = document.getElementById('credPassword');
    input.type = input.type === 'password' ? 'text' : 'password';
    document.getElementById('btnToggleCredPassword').innerHTML = input.type === 'password'
      ? '<i class="fa-solid fa-eye"></i>'
      : '<i class="fa-solid fa-eye-slash"></i>';
  });

  document.getElementById('credentialsList').addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-cred-action]');
    if (!btn) return;
    const card = btn.closest('.credential-card');
    const credId = card.getAttribute('data-cred-id');
    const action = btn.getAttribute('data-cred-action');
    const link = State.currentCredentialsLink;
    const cred = ((link && link.credentials) || []).find(c => String(c.id) === String(credId));
    if (!cred) return;

    if (action === 'reveal') {
      const span = card.querySelector('.cred-password-value');
      const visible = span.getAttribute('data-visible') === '1';
      span.textContent = visible ? '••••••••' : (span.getAttribute('data-password') || '—');
      span.setAttribute('data-visible', visible ? '0' : '1');
      btn.innerHTML = visible ? '<i class="fa-solid fa-eye"></i>' : '<i class="fa-solid fa-eye-slash"></i>';
    } else if (action === 'copy-user') {
      copyTextToClipboard(cred.username || '');
    } else if (action === 'copy-pass') {
      copyTextToClipboard(cred.password || '');
    } else if (action === 'edit') {
      editCredential(credId);
    } else if (action === 'delete') {
      await deleteCredential(credId);
    }
  });

  // ---- Sublinks modal ----
  document.getElementById('btnCloseSublinksModal').addEventListener('click', () => {
    document.getElementById('sublinksModal').classList.remove('active');
  });
  document.getElementById('sublinkForm').addEventListener('submit', addSublink);
  document.getElementById('btnBatchAddSublinks').addEventListener('click', batchAddSublinks);
  document.getElementById('btnOpenAllSublinks').addEventListener('click', openAllSublinks);
  document.getElementById('sublinksList').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-sub-action]');
    if (!btn) return;
    const row = btn.closest('.sublink-item');
    handleSublinkAction(btn.getAttribute('data-sub-action'), row.getAttribute('data-sub-id'));
  });
  document.getElementById('sublinkSuggestions').addEventListener('click', (e) => {
    const btn = e.target.closest('.suggestion-chip');
    if (!btn) return;
    addSuggestionAsSublink(
      btn.getAttribute('data-suggest-url'),
      btn.getAttribute('data-suggest-title')
    );
  });

  // ---- Database export / import ----
  document.getElementById('btnExportDb').addEventListener('click', exportDatabaseFile);
  document.getElementById('btnExportJson').addEventListener('click', exportDatabaseJson);
  document.getElementById('btnCreateBackup').addEventListener('click', createBackupNow);
  document.getElementById('btnRefreshBackups').addEventListener('click', loadDatabasePanel);
  document.getElementById('autoBackupsList').addEventListener('click', (e) => {
    const btn = e.target.closest('.btn-restore-backup');
    if (!btn) return;
    restoreBackupFile(btn.getAttribute('data-filename'));
  });
  document.getElementById('btnImportDb').addEventListener('click', () => {
    document.getElementById('importDbFile').click();
  });
  document.getElementById('btnImportJson').addEventListener('click', () => {
    document.getElementById('importJsonFile').click();
  });
  document.getElementById('importDbFile').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    e.target.value = '';
    await importDatabaseFile(file);
  });
  document.getElementById('importJsonFile').addEventListener('change', async (e) => {
    const file = e.target.files[0];
    e.target.value = '';
    await importJsonPayload(file);
  });

  // Live Auto-Scrape when typing URL
  let urlDebounce = null;
  document.getElementById('inputUrl').addEventListener('input', (e) => {
    const val = e.target.value.trim();
    if (val.length > 7 && (val.startsWith('http') || val.includes('.'))) {
      clearTimeout(urlDebounce);
      urlDebounce = setTimeout(() => triggerScrapePreview(val), 600);
    }
  });

  document.getElementById('btnScrapeNow').addEventListener('click', () => {
    const val = document.getElementById('inputUrl').value.trim();
    if (val) triggerScrapePreview(val);
  });

  // Forms
  document.getElementById('linkForm').addEventListener('submit', handleSaveLink);
  document.getElementById('btnConfirmBatch').addEventListener('click', handleBatchImport);

  // ---- Floating assistant ----
  document.getElementById('chatFab').addEventListener('click', () => toggleChatPanel());
  document.getElementById('btnChatClose').addEventListener('click', () => toggleChatPanel(false));
  document.getElementById('btnChatNew').addEventListener('click', startNewChat);
  document.getElementById('btnChatHistory').addEventListener('click', () => toggleChatHistory());
  document.getElementById('btnCloseChatHistory').addEventListener('click', closeChatHistory);

  document.getElementById('chatSessionList').addEventListener('click', (e) => {
    const deleteBtn = e.target.closest('[data-delete-chat-session]');
    if (deleteBtn) {
      e.stopPropagation();
      deleteChatConversation(deleteBtn.getAttribute('data-delete-chat-session'));
      return;
    }
    const item = e.target.closest('.chat-session-item');
    if (item) restoreChatSession(item.getAttribute('data-session-id'), true);
  });

  document.getElementById('chatSuggestions').addEventListener('click', (e) => {
    const chip = e.target.closest('[data-chat-suggestion]');
    if (chip) sendChatMessage(chip.getAttribute('data-chat-suggestion'));
  });

  document.getElementById('chatForm').addEventListener('submit', (e) => {
    e.preventDefault();
    sendChatMessage(document.getElementById('chatInput').value);
  });

  const chatInput = document.getElementById('chatInput');
  chatInput.addEventListener('input', autoResizeChatInput);
  chatInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendChatMessage(chatInput.value);
    }
  });

  document.getElementById('chatMessages').addEventListener('click', async (e) => {
    const assistantBtn = e.target.closest('[data-open-link-assistant]');
    if (assistantBtn) {
      openLinkAssistant(State.linkAssistant.lastChatPreview);
      toggleChatPanel(false);
      return;
    }
    const applyDomainBtn = e.target.closest('[data-apply-domain-suggestion]');
    if (applyDomainBtn) {
      applyDomainSuggestionUI(applyDomainBtn.getAttribute('data-apply-domain-suggestion'));
      return;
    }
    const dismissDomainBtn = e.target.closest('[data-dismiss-domain-suggestion]');
    if (dismissDomainBtn) {
      dismissDomainSuggestionUI(dismissDomainBtn.getAttribute('data-dismiss-domain-suggestion'));
      return;
    }
    const openDomainBtn = e.target.closest('[data-open-domain-group]');
    if (openDomainBtn) {
      selectDomainGroup(openDomainBtn.getAttribute('data-open-domain-group'));
      toggleChatPanel(false);
      return;
    }
    const mergeDomainBtn = e.target.closest('[data-chat-merge-domain]');
    if (mergeDomainBtn) {
      const root = mergeDomainBtn.getAttribute('data-chat-merge-domain');
      const mainId = parseInt(mergeDomainBtn.getAttribute('data-chat-merge-main'), 10);
      const ids = (mergeDomainBtn.getAttribute('data-chat-merge-ids') || '')
        .split(',')
        .map(v => parseInt(v, 10))
        .filter(v => !Number.isNaN(v));
      const ok = await safeConfirm(
        `¿Fusionar enlaces de «${root}»?`,
        'Se creará una copia de seguridad y podrás deshacerlo.'
      );
      if (!ok) return;
      const res = await API.mergeDomain(root, mainId, ids, 'Fusión desde el asistente');
      if (res && res.success) {
        showToast('Grupo fusionado desde el asistente', 'success');
        await refreshAllData();
        await refreshDomainDashboard(false);
      } else {
        showToast((res && res.error) || 'No se pudo fusionar', 'error');
      }
      return;
    }
    const undoDomainBtn = e.target.closest('[data-chat-undo-domain]');
    if (undoDomainBtn) {
      undoDomainActionUI();
      return;
    }
    const dismissActionBtn = e.target.closest('[data-chat-dismiss-domain-action]');
    if (dismissActionBtn) {
      dismissActionBtn.closest('.chat-domain-action').remove();
      return;
    }

    const openBtn = e.target.closest('[data-chat-open-link]');
    if (openBtn) {
      const id = openBtn.getAttribute('data-chat-open-link');
      const res = await API.openInBrowser(id);
      if (res && res.success) {
        showToast('Enlace abierto en el navegador', 'success');
        if (res._gamification) handleGamificationEventResult(res._gamification);
        loadStats();
      } else {
        showToast('No se pudo abrir el enlace', 'error');
      }
      return;
    }

    const copyBtn = e.target.closest('[data-chat-copy-url]');
    if (copyBtn) {
      copyTextToClipboard(copyBtn.getAttribute('data-chat-copy-url'));
    }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && State.chat.open) toggleChatPanel(false);
  });

  // ---- Domain grouping / notifications ----
  document.getElementById('btnDomainNotifications').addEventListener('click', openDomainNotifications);
  document.getElementById('btnCloseDomainNotifications').addEventListener('click', () => {
    document.getElementById('domainNotificationsModal').classList.remove('active');
  });
  document.getElementById('btnDomainNotifScan').addEventListener('click', scanDomainsNow);
  document.getElementById('btnDomainNotifUndo').addEventListener('click', undoDomainActionUI);
  document.getElementById('btnDomainNotifReadAll').addEventListener('click', async () => {
    await API.markDomainSuggestionsRead(null);
    State.domain.counts.unread = 0;
    updateDomainBell();
    showToast('Sugerencias marcadas como leídas', 'info');
  });

  document.getElementById('domainNotificationsList').addEventListener('click', (e) => {
    const applyBtn = e.target.closest('[data-apply-domain-suggestion]');
    if (applyBtn) {
      applyDomainSuggestionUI(applyBtn.getAttribute('data-apply-domain-suggestion'));
      return;
    }
    const dismissBtn = e.target.closest('[data-dismiss-domain-suggestion]');
    if (dismissBtn) {
      dismissDomainSuggestionUI(dismissBtn.getAttribute('data-dismiss-domain-suggestion'));
      return;
    }
    const groupBtn = e.target.closest('[data-open-domain-group]');
    if (groupBtn) {
      document.getElementById('domainNotificationsModal').classList.remove('active');
      selectDomainGroup(groupBtn.getAttribute('data-open-domain-group'));
    }
  });

  document.getElementById('btnToggleDomainGrouping').addEventListener('click', () => {
    State.domain.groupByDomain = !State.domain.groupByDomain;
    localStorage.setItem('pageneitor_group_by_domain', State.domain.groupByDomain ? '1' : '0');
    document.getElementById('btnToggleDomainGrouping')
      .classList.toggle('active', State.domain.groupByDomain);
    renderLinksGridZeroFlicker();
    API.trackEvent('ui', 'toggle_domain_grouping', { enabled: State.domain.groupByDomain });
  });

  document.getElementById('toggleDomainsAccordion').addEventListener('click', () => {
    document.getElementById('accordionDomains').classList.toggle('collapsed');
  });

  document.getElementById('sidebarDomainsList').addEventListener('click', (e) => {
    const item = e.target.closest('[data-domain-root]');
    if (item) selectDomainGroup(item.getAttribute('data-domain-root'));
  });

  document.getElementById('domainToastContainer').addEventListener('click', (e) => {
    const apply = e.target.closest('[data-domain-toast-apply]');
    if (apply) {
      document.getElementById('domainToastContainer').innerHTML = '';
      applyDomainSuggestionUI(apply.getAttribute('data-domain-toast-apply'));
      return;
    }
    const review = e.target.closest('[data-domain-toast-review]');
    if (review) {
      openDomainNotifications().then(() => {
        const id = review.getAttribute('data-domain-toast-review');
        const card = document.querySelector(`#domainNotificationsList [data-suggestion-card="${id}"]`);
        if (card) card.scrollIntoView({ behavior: 'smooth', block: 'center' });
        document.getElementById('domainToastContainer').innerHTML = '';
      });
      return;
    }
    if (e.target.closest('[data-domain-toast-close]')) {
      document.getElementById('domainToastContainer').innerHTML = '';
    }
  });

  ['domainGroupSubdomains', 'domainScanEnabled', 'domainScanInterval',
   'domainMinConfidence', 'domainToastEnabled', 'wordcloudRotation',
   'analyticsRetentionDays'].forEach(id => {
    document.getElementById(id).addEventListener('change', saveDomainSettingsFromUI);
  });
  document.getElementById('btnDomainSettingsScan').addEventListener('click', scanDomainsNow);
  document.getElementById('btnDomainSettingsUndo').addEventListener('click', undoDomainActionUI);

  // ---- Link insertion assistant ----
  document.getElementById('btnCloseLinkAssistant').addEventListener('click', () => {
    document.getElementById('linkAssistantModal').classList.remove('active');
  });
  document.getElementById('btnCancelLinkAssistant').addEventListener('click', () => {
    document.getElementById('linkAssistantModal').classList.remove('active');
  });
  document.getElementById('btnLinkAssistantAnalyze').addEventListener('click', analyzeAssistantLinks);
  document.getElementById('btnLinkAssistantSave').addEventListener('click', saveAssistantLinks);
  document.getElementById('linkAssistantResults').addEventListener('click', (e) => {
    const remove = e.target.closest('.assistant-remove');
    if (remove) {
      const item = remove.closest('.assistant-item');
      if (item) item.remove();
      if (!document.querySelectorAll('#linkAssistantResults .assistant-item').length) {
        document.getElementById('btnLinkAssistantSave').disabled = true;
      }
    }
  });

  // ---- Domain detail view ----
  document.getElementById('btnDomainDetailBack').addEventListener('click', async () => {
    setMainView('links');
    State.domain.currentRootDomain = null;
    State.domainDetail = null;
    renderSidebarDomains();
    await loadLinks();
  });
  document.getElementById('btnDomainDetailAddLink').addEventListener('click', () => {
    openLinkAssistant(null, State.domainDetail ? State.domainDetail.root_domain : null);
  });
  document.getElementById('btnDomainDetailOpenAll').addEventListener('click', () => {
    if (State.domainDetail) handleDomainGroupAction('open-all', State.domainDetail.root_domain);
  });
  document.getElementById('btnDomainDetailMerge').addEventListener('click', async () => {
    if (State.domainDetail) {
      await mergeDomainGroupUI(State.domainDetail.root_domain);
      await openDomainDetail(State.domainDetail.root_domain);
    }
  });
  document.getElementById('btnDomainDetailSuggest').addEventListener('click', scanDomainsNow);
  document.getElementById('domainDetailLinks').addEventListener('click', async (e) => {
    const target = e.target.closest('[data-action]');
    if (!target) return;
    await handleLinkCardAction(
      target.getAttribute('data-action'),
      target.getAttribute('data-id'),
      target,
      target.getAttribute('data-url')
    );
  });

  // ---- Analytics view ----
  document.getElementById('btnAnalyticsBack').addEventListener('click', async () => {
    setMainView('links');
    State.domain.currentRootDomain = null;
    renderSidebarDomains();
    await loadLinks();
  });
  document.getElementById('btnAnalyticsRefresh').addEventListener('click', () => loadAnalyticsView(true));
  document.getElementById('btnAnalyticsMode').addEventListener('click', toggleAnalyticsMode);
  document.getElementById('btnAnalyticsExport').addEventListener('click', exportAnalyticsJson);
  document.getElementById('btnAnalyticsAI').addEventListener('click', generateAnalyticsInsights);
}

// Helpers for New Profile and Category Dialogs in Control Panel
async function newProfileDialog() {
  if (typeof Swal === 'undefined') return;
  const { value: formValues } = await Swal.fire({
    title: 'Nuevo Perfil de Navegador',
    html: `
      <div class="form-group" style="text-align: left;">
        <label>Nombre del Perfil:</label>
        <input id="swalNewProfName" class="form-control" placeholder="ej. Cliente A, Gaming">
      </div>
      <div class="form-group" style="text-align: left; margin-top: 10px;">
        <label>Color Identificador:</label>
        <input id="swalNewProfColor" type="color" value="#6366f1" style="width: 100%; height: 36px; border: none; border-radius: 6px; cursor: pointer;">
      </div>
    `,
    customClass: { popup: 'swal2-glass-popup', confirmButton: 'swal2-glass-confirm', cancelButton: 'swal2-glass-cancel' },
    showCancelButton: true,
    confirmButtonText: 'Crear Perfil (+50 XP)',
    cancelButtonText: 'Cancelar',
    preConfirm: () => {
      return {
        name: document.getElementById('swalNewProfName').value.trim(),
        color: document.getElementById('swalNewProfColor').value
      };
    }
  });

  if (formValues && formValues.name) {
    const res = await API.createProfile(formValues);
    showToast(`Perfil "${formValues.name}" creado (+50 XP)`, 'success');
    if (res && res._gamification) handleGamificationEventResult(res._gamification);
    await loadProfiles();
  }
}

async function newCategoryDialog() {
  if (typeof Swal === 'undefined') return;
  const { value: formValues } = await Swal.fire({
    title: 'Nuevo Tema / Categoría',
    html: `
      <div class="form-group" style="text-align: left;">
        <label>Nombre del Tema:</label>
        <input id="swalNewCatName" class="form-control" placeholder="ej. Cripto, Podcast, Recetas">
      </div>
      <div class="form-group" style="text-align: left; margin-top: 10px;">
        <label>Color Semántico:</label>
        <input id="swalNewCatColor" type="color" value="#06b6d4" style="width: 100%; height: 36px; border: none; border-radius: 6px; cursor: pointer;">
      </div>
    `,
    customClass: { popup: 'swal2-glass-popup', confirmButton: 'swal2-glass-confirm', cancelButton: 'swal2-glass-cancel' },
    showCancelButton: true,
    confirmButtonText: 'Crear Tema (+50 XP)',
    cancelButtonText: 'Cancelar',
    preConfirm: () => {
      return {
        name: document.getElementById('swalNewCatName').value.trim(),
        color: document.getElementById('swalNewCatColor').value
      };
    }
  });

  if (formValues && formValues.name) {
    const res = await API.createCategory(formValues);
    showToast(`Tema "${formValues.name}" creado (+50 XP)`, 'success');
    if (res && res._gamification) handleGamificationEventResult(res._gamification);
    await loadCategories();
  }
}

// Clipboard Paste
async function handlePasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText();
    if (text && (text.startsWith('http://') || text.startsWith('https://') || text.includes('.'))) {
      openNewLinkModal();
      document.getElementById('inputUrl').value = text.trim();
      triggerScrapePreview(text.trim());
      showToast('URL detectada desde el portapapeles');
    } else {
      showToast('No se encontró una URL válida en el portapapeles', 'info');
    }
  } catch (err) {
    showToast('Permite el acceso al portapapeles para pegar directo', 'info');
  }
}

// Scrape Preview
async function triggerScrapePreview(url) {
  const btn = document.getElementById('btnScrapeNow');
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Extrayendo...';
  try {
    const meta = await API.scrapeUrl(url);
    const titleInput = document.getElementById('inputTitle');
    const descInput = document.getElementById('inputDesc');
    const thumbInput = document.getElementById('inputThumbnail');
    const tagsInput = document.getElementById('inputTags');
    const catSelect = document.getElementById('selectCategory');

    if (!titleInput.value) titleInput.value = meta.title || '';
    if (!descInput.value) descInput.value = meta.description || '';
    if (meta.thumbnail_url && !thumbInput.value) thumbInput.value = meta.thumbnail_url;
    if (meta.suggested_tags && !tagsInput.value) tagsInput.value = meta.suggested_tags.join(', ');
    if (meta.category_id && catSelect) catSelect.value = meta.category_id;

    const preview = document.getElementById('liveScrapePreview');
    const img = document.getElementById('scrapePreviewImg');
    if (meta.thumbnail_url) {
      img.src = meta.thumbnail_url;
      img.style.display = 'block';
    } else {
      img.style.display = 'none';
    }
    document.getElementById('scrapePreviewTitle').textContent = meta.title || meta.domain;
    document.getElementById('scrapePreviewDesc').textContent = meta.description || `Sitio en ${meta.domain}`;
    preview.classList.add('visible');
  } catch (err) {
    console.warn('Scrape preview error:', err);
  } finally {
    btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles"></i> Auto-Detectar';
  }
}

// Link Modal
function openNewLinkModal() {
  document.getElementById('linkForm').reset();
  document.getElementById('editLinkId').value = '';
  document.getElementById('modalTitle').innerHTML = '<i class="fa-solid fa-link" style="color: var(--primary);"></i> Guardar Enlace';
  document.getElementById('liveScrapePreview').classList.remove('visible');
  renderFormCredentials([]);
  document.getElementById('linkModal').classList.add('active');
  setTimeout(() => document.getElementById('inputUrl').focus(), 100);
}

function openEditLinkModal(id) {
  const link = State.links.find(l => l.id == id) ||
    ((State.domainDetail && State.domainDetail.links) || []).find(l => l.id == id);
  if (!link) return;

  document.getElementById('editLinkId').value = link.id;
  document.getElementById('modalTitle').innerHTML = '<i class="fa-solid fa-pen" style="color: var(--primary);"></i> Editar Enlace (Renovación)';
  document.getElementById('inputUrl').value = link.url;
  document.getElementById('inputTitle').value = link.title;
  document.getElementById('inputDesc').value = link.description || '';
  document.getElementById('inputThumbnail').value = link.thumbnail_url || '';
  document.getElementById('inputTags').value = (link.tags || []).join(', ');
  document.getElementById('inputNotes').value = link.notes || '';
  if (link.profile_id) document.getElementById('selectProfile').value = link.profile_id;
  if (link.category_id) document.getElementById('selectCategory').value = link.category_id;
  renderFormCredentials(link.credentials || []);

  document.getElementById('linkModal').classList.add('active');
}

function closeLinkModal() {
  document.getElementById('linkModal').classList.remove('active');
}

// ============================================================
// MULTI-ACCOUNT CREDENTIALS (FORM REPEATER + VAULT MODAL)
// ============================================================
function updateFormCredentialsEmpty() {
  const list = document.getElementById('formCredentialsList');
  const empty = list.querySelector('.form-credentials-empty');
  const hasRows = list.querySelectorAll('.form-credential-row').length > 0;
  if (empty) empty.style.display = hasRows ? 'none' : 'block';
}

function addFormCredentialRow(cred = {}) {
  const list = document.getElementById('formCredentialsList');
  const row = document.createElement('div');
  row.className = 'form-credential-row';
  row.dataset.credId = cred.id || '';
  row.dataset.createdAt = cred.created_at || '';
  row.innerHTML = `
    <div class="form-credential-grid">
      <input type="text" class="form-control fcred-label" placeholder="Alias (Personal, Trabajo...)" value="${escapeHtml(cred.label || '')}">
      <input type="text" class="form-control fcred-username" placeholder="Usuario / correo" value="${escapeHtml(cred.username || '')}" autocomplete="off">
      <input type="password" class="form-control fcred-password" placeholder="Contraseña" value="${escapeHtml(cred.password || '')}" autocomplete="new-password">
      <input type="text" class="form-control fcred-notes" placeholder="Notas" value="${escapeHtml(cred.notes || '')}">
    </div>
    <button type="button" class="icon-action-btn delete-btn btn-remove-form-credential" title="Quitar esta cuenta">
      <i class="fa-solid fa-xmark"></i>
    </button>
  `;
  list.appendChild(row);
  updateFormCredentialsEmpty();
}

function renderFormCredentials(credentials) {
  const list = document.getElementById('formCredentialsList');
  list.innerHTML = '<div class="form-credentials-empty">Puedes guardar varias cuentas para el mismo sitio (usuario, contraseña y notas).</div>';
  (credentials || []).forEach(addFormCredentialRow);
  updateFormCredentialsEmpty();
}

function collectFormCredentials() {
  const rows = document.querySelectorAll('#formCredentialsList .form-credential-row');
  const credentials = [];
  rows.forEach((row, index) => {
    const label = row.querySelector('.fcred-label').value.trim();
    const username = row.querySelector('.fcred-username').value.trim();
    const password = row.querySelector('.fcred-password').value;
    const notes = row.querySelector('.fcred-notes').value.trim();
    if (!username && !password && !notes && !label) return;
    credentials.push({
      id: row.dataset.credId || `cred_${Date.now()}_${index}`,
      label: label || `Cuenta ${index + 1}`,
      username,
      password,
      notes,
      created_at: row.dataset.createdAt || undefined
    });
  });
  return credentials;
}

function findLinkInState(id) {
  return State.links.find(l => String(l.id) === String(id));
}

async function openCredentialsModal(linkId) {
  let link = findLinkInState(linkId);
  if (!link) link = await API.getLink(linkId);
  if (!link) {
    showToast('No se pudo cargar el enlace', 'error');
    return;
  }
  State.currentCredentialsLink = link;
  resetCredentialForm();
  renderCredentialsModal();
  document.getElementById('credentialsModal').classList.add('active');
}

function renderCredentialsModal() {
  const link = State.currentCredentialsLink;
  if (!link) return;

  document.getElementById('credModalLinkTitle').textContent = link.title || 'Enlace';
  document.getElementById('credModalLinkUrl').textContent = link.url || '';

  const list = document.getElementById('credentialsList');
  const creds = link.credentials || [];
  list.innerHTML = '';

  if (creds.length === 0) {
    list.innerHTML = `
      <div class="db-empty">
        <i class="fa-solid fa-key" style="font-size: 22px; opacity: .5; display:block; margin-bottom: 6px;"></i>
        Todavía no hay cuentas guardadas para este enlace. Añade la primera abajo.
      </div>`;
    return;
  }

  creds.forEach(cred => {
    const card = document.createElement('div');
    card.className = 'credential-card';
    card.dataset.credId = cred.id;
    card.innerHTML = `
      <div class="credential-main">
        <div class="credential-icon"><i class="fa-solid fa-user-shield"></i></div>
        <div class="credential-fields">
          <div class="credential-label">${escapeHtml(cred.label || 'Cuenta')}</div>
          <div class="credential-line"><i class="fa-solid fa-user"></i> <span>${escapeHtml(cred.username || '—')}</span></div>
          <div class="credential-line">
            <i class="fa-solid fa-lock"></i>
            <span class="cred-password-value" data-password="${escapeHtml(cred.password || '')}" data-visible="0">••••••••</span>
          </div>
          ${cred.notes ? `<div class="credential-notes">${escapeHtml(cred.notes)}</div>` : ''}
        </div>
      </div>
      <div class="credential-actions">
        <button class="icon-action-btn" data-cred-action="reveal" title="Mostrar/ocultar contraseña"><i class="fa-solid fa-eye"></i></button>
        <button class="icon-action-btn" data-cred-action="copy-user" title="Copiar usuario"><i class="fa-solid fa-at"></i></button>
        <button class="icon-action-btn" data-cred-action="copy-pass" title="Copiar contraseña"><i class="fa-regular fa-copy"></i></button>
        <button class="icon-action-btn" data-cred-action="edit" title="Editar cuenta"><i class="fa-solid fa-pen"></i></button>
        <button class="icon-action-btn delete-btn" data-cred-action="delete" title="Eliminar cuenta"><i class="fa-regular fa-trash-can"></i></button>
      </div>
    `;
    list.appendChild(card);
  });
}

function resetCredentialForm() {
  const form = document.getElementById('credentialForm');
  form.reset();
  document.getElementById('credEditId').value = '';
  document.getElementById('credFormTitle').innerHTML = '<i class="fa-solid fa-plus"></i> Añadir una cuenta';
  document.getElementById('btnCancelCredentialEdit').style.display = 'none';
  document.getElementById('credPassword').type = 'password';
  document.getElementById('btnToggleCredPassword').innerHTML = '<i class="fa-solid fa-eye"></i>';
}

async function saveCredentialForm(e) {
  e.preventDefault();
  const link = State.currentCredentialsLink;
  if (!link) return;

  const editId = document.getElementById('credEditId').value;
  const payload = {
    label: document.getElementById('credLabel').value.trim() || 'Cuenta',
    username: document.getElementById('credUsername').value.trim(),
    password: document.getElementById('credPassword').value,
    notes: document.getElementById('credNotes').value.trim()
  };

  if (!payload.username && !payload.password && !payload.notes) {
    showToast('Escribe al menos un usuario, contraseña o nota', 'info');
    return;
  }

  try {
    let res;
    if (editId) {
      res = await API.updateCredential(link.id, editId, payload);
    } else {
      res = await API.addCredential(link.id, payload);
    }

    if (res && res.all_credentials) {
      link.credentials = res.all_credentials;
    } else if (res && res.credential) {
      link.credentials = [...(link.credentials || []), res.credential];
    }

    resetCredentialForm();
    renderCredentialsModal();
    await loadLinks();
    if (res && res._gamification) handleGamificationEventResult(res._gamification);
    showToast(editId ? 'Cuenta actualizada' : 'Cuenta guardada', 'success');
  } catch (err) {
    showToast('Error al guardar la cuenta', 'error');
  }
}

async function deleteCredential(credId) {
  const link = State.currentCredentialsLink;
  if (!link) return;
  const ok = await safeConfirm('¿Eliminar esta cuenta guardada?', 'La contraseña se borrará del enlace.');
  if (!ok) return;

  const res = await API.deleteCredential(link.id, credId);
  if (res && res.all_credentials) link.credentials = res.all_credentials;
  renderCredentialsModal();
  await loadLinks();
  showToast('Cuenta eliminada', 'info');
}

function editCredential(credId) {
  const link = State.currentCredentialsLink;
  const cred = (link.credentials || []).find(c => String(c.id) === String(credId));
  if (!cred) return;

  document.getElementById('credEditId').value = cred.id;
  document.getElementById('credLabel').value = cred.label || '';
  document.getElementById('credUsername').value = cred.username || '';
  document.getElementById('credPassword').value = cred.password || '';
  document.getElementById('credNotes').value = cred.notes || '';
  document.getElementById('credFormTitle').innerHTML = '<i class="fa-solid fa-pen"></i> Editar cuenta';
  document.getElementById('btnCancelCredentialEdit').style.display = 'inline-flex';
  document.getElementById('credentialForm').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ============================================================
// SUB-ENLACES / ASSOCIATED TABS OF THE SAME SITE
// ============================================================
async function openSublinksModal(linkId) {
  let link = findLinkInState(linkId);
  if (!link) link = await API.getLink(linkId);
  if (!link) {
    showToast('No se pudo cargar el enlace', 'error');
    return;
  }
  State.currentSublinksLink = link;

  // Find other links of the same site already stored in Pageneitor so the
  // user can attach them with one click instead of copy/pasting.
  try {
    const all = await API.getLinks();
    const domain = link.domain || '';
    const existing = new Set((link.sublinks || []).map(s => s.url));
    link._suggestions = all.filter(item =>
      String(item.id) !== String(link.id) &&
      item.domain &&
      item.domain === domain &&
      !existing.has(item.url)
    );
  } catch (err) {
    link._suggestions = [];
  }

  document.getElementById('subModalLinkTitle').textContent = link.title || 'Enlace';
  document.getElementById('subModalLinkUrl').textContent = link.url || '';
  document.getElementById('sublinkForm').reset();
  renderSublinksModal();
  document.getElementById('sublinksModal').classList.add('active');
}

function renderSublinksModal() {
  const link = State.currentSublinksLink;
  if (!link) return;
  const list = document.getElementById('sublinksList');
  const subs = link.sublinks || [];
  list.innerHTML = '';

  renderSublinkSuggestions();

  if (subs.length === 0) {
    list.innerHTML = `
      <div class="db-empty">
        <i class="fa-solid fa-folder-open" style="font-size: 22px; opacity: .5; display:block; margin-bottom: 6px;"></i>
        No hay sub-enlaces guardados. Añade aquí las otras pestañas de esta misma página.
      </div>`;
    return;
  }

  subs.forEach(sub => {
    const row = document.createElement('div');
    row.className = `sublink-item ${sub.is_read ? 'is-read' : ''}`;
    row.dataset.subId = sub.id;
    row.innerHTML = `
      <div class="sublink-main">
        <i class="fa-solid ${sub.is_read ? 'fa-circle-check' : 'fa-link'}" style="color: ${sub.is_read ? '#34d399' : 'var(--primary)'};"></i>
        <div>
          <div class="sublink-title">${escapeHtml(sub.title || sub.url)}</div>
          <div class="sublink-url" title="${escapeHtml(sub.url)}">${escapeHtml(sub.url)}</div>
        </div>
      </div>
      <div class="sublink-actions">
        <button class="icon-action-btn" data-sub-action="open" title="Abrir en el navegador"><i class="fa-solid fa-up-right-from-square"></i></button>
        <button class="icon-action-btn" data-sub-action="toggle-read" title="Marcar como leído/pendiente"><i class="fa-solid ${sub.is_read ? 'fa-check-double' : 'fa-clock'}"></i></button>
        <button class="icon-action-btn" data-sub-action="copy" title="Copiar URL"><i class="fa-regular fa-copy"></i></button>
        <button class="icon-action-btn delete-btn" data-sub-action="delete" title="Eliminar sub-enlace"><i class="fa-regular fa-trash-can"></i></button>
      </div>
    `;
    list.appendChild(row);
  });
}

function renderSublinkSuggestions() {
  const link = State.currentSublinksLink;
  const container = document.getElementById('sublinkSuggestions');
  if (!link || !container) return;

  const existing = new Set((link.sublinks || []).map(s => s.url));
  const suggestions = (link._suggestions || []).filter(item => !existing.has(item.url));

  if (!suggestions.length) {
    container.innerHTML = '';
    return;
  }

  container.innerHTML = `
    <div class="suggestions-title">
      <i class="fa-solid fa-wand-magic-sparkles"></i>
      Encontrados en tu banco (${suggestions.length}) — pulsa para añadirlos a este sitio
    </div>
    <div class="suggestion-chips">
      ${suggestions.map(item => `
        <button type="button" class="suggestion-chip" data-suggest-url="${escapeHtml(item.url)}" data-suggest-title="${escapeHtml(item.title)}">
          <i class="fa-solid fa-plus"></i> ${escapeHtml(item.title)}
        </button>
      `).join('')}
    </div>
  `;
}

async function addSuggestionAsSublink(url, title) {
  const link = State.currentSublinksLink;
  if (!link) return;
  const res = await API.addSublink(link.id, { title, url });
  if (res && res.all_sublinks) link.sublinks = res.all_sublinks;
  renderSublinksModal();
  await loadLinks();
  if (res && res._gamification) handleGamificationEventResult(res._gamification);
  showToast('Sub-enlace añadido desde tu banco', 'success');
}

async function addSublink(e) {
  e.preventDefault();
  const link = State.currentSublinksLink;
  if (!link) return;

  const url = document.getElementById('subUrl').value.trim();
  if (!url) return;
  const title = document.getElementById('subTitle').value.trim();

  const res = await API.addSublink(link.id, { title, url });
  if (res && res.all_sublinks) link.sublinks = res.all_sublinks;
  document.getElementById('sublinkForm').reset();
  renderSublinksModal();
  await loadLinks();
  if (res && res._gamification) handleGamificationEventResult(res._gamification);
  showToast('Sub-enlace añadido', 'success');
}

async function batchAddSublinks() {
  const link = State.currentSublinksLink;
  if (!link) return;
  const text = document.getElementById('batchSublinksText').value.trim();
  if (!text) {
    showToast('Pega al menos una URL', 'info');
    return;
  }

  const res = await API.batchAddSublinks(link.id, text);
  if (res && res.all_sublinks) link.sublinks = res.all_sublinks;
  document.getElementById('batchSublinksText').value = '';
  renderSublinksModal();
  await loadLinks();
  if (res && res._gamification) handleGamificationEventResult(res._gamification);
  showToast(`${res.added_count || 0} sub-enlaces añadidos`, 'success');
}

async function handleSublinkAction(action, subId) {
  const link = State.currentSublinksLink;
  if (!link) return;
  const sub = (link.sublinks || []).find(s => String(s.id) === String(subId));

  if (action === 'open') {
    const res = await API.openSublink(link.id, subId);
    if (res && res.all_sublinks) link.sublinks = res.all_sublinks;
    else if (sub) sub.is_read = 1;
    renderSublinksModal();
    await loadLinks();
    if (res && res._gamification) handleGamificationEventResult(res._gamification);
    showToast('Sub-enlace abierto en el navegador', 'success');
  } else if (action === 'toggle-read') {
    const res = await API.toggleSublinkRead(link.id, subId);
    if (res && res.all_sublinks) link.sublinks = res.all_sublinks;
    renderSublinksModal();
  } else if (action === 'copy') {
    if (sub) copyTextToClipboard(sub.url);
  } else if (action === 'delete') {
    const ok = await safeConfirm('¿Eliminar este sub-enlace?');
    if (!ok) return;
    const res = await API.deleteSublink(link.id, subId);
    if (res && res.all_sublinks) link.sublinks = res.all_sublinks;
    renderSublinksModal();
    await loadLinks();
    showToast('Sub-enlace eliminado', 'info');
  }
}

async function openAllSublinks() {
  const link = State.currentSublinksLink;
  if (!link) return;
  if (!(link.sublinks || []).length) {
    showToast('No hay sub-enlaces para abrir', 'info');
    return;
  }
  const res = await API.openAllSublinks(link.id);
  if (res && res._gamification) handleGamificationEventResult(res._gamification);
  const fresh = await API.getLink(link.id);
  if (fresh) {
    link.sublinks = fresh.sublinks || [];
    renderSublinksModal();
  }
  showToast(`${res.opened_count || 0} sub-enlaces abiertos`, 'success');
}

// ============================================================
// CLIPBOARD / CONFIRM HELPERS (work even without CDN libraries)
// ============================================================
async function copyTextToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    showToast('Copiado al portapapeles');
  } catch (err) {
    try {
      const tmp = document.createElement('textarea');
      tmp.value = text;
      tmp.style.position = 'fixed';
      tmp.style.opacity = '0';
      document.body.appendChild(tmp);
      tmp.select();
      document.execCommand('copy');
      tmp.remove();
      showToast('Copiado al portapapeles');
    } catch (e2) {
      showToast('No se pudo copiar automáticamente', 'error');
    }
  }
}

async function safeConfirm(title, text = '') {
  if (typeof Swal !== 'undefined') {
    const result = await Swal.fire({
      title,
      text,
      icon: 'warning',
      showCancelButton: true,
      confirmButtonText: 'Sí, continuar',
      cancelButtonText: 'Cancelar',
      customClass: { popup: 'swal2-glass-popup', confirmButton: 'swal2-glass-confirm', cancelButton: 'swal2-glass-cancel' }
    });
    return !!result.isConfirmed;
  }
  return window.confirm(text ? `${title}\n\n${text}` : title);
}

async function handleSaveLink(e) {
  e.preventDefault();
  const editId = document.getElementById('editLinkId').value;
  const tags = document.getElementById('inputTags').value.split(',').map(t => t.trim().replace(/^#/, '')).filter(t => t);

  const payload = {
    url: document.getElementById('inputUrl').value.trim(),
    title: document.getElementById('inputTitle').value.trim(),
    description: document.getElementById('inputDesc').value.trim(),
    thumbnail_url: document.getElementById('inputThumbnail').value.trim(),
    category_id: document.getElementById('selectCategory').value ? parseInt(document.getElementById('selectCategory').value) : null,
    profile_id: document.getElementById('selectProfile').value ? parseInt(document.getElementById('selectProfile').value) : null,
    tags: tags,
    credentials: collectFormCredentials(),
    notes: document.getElementById('inputNotes').value.trim()
  };

  try {
    if (editId) {
      const res = await API.updateLink(editId, payload);
      showToast('Enlace renovado con éxito (+25 XP)', 'success');
      if (res && res._gamification) handleGamificationEventResult(res._gamification);
      API.trackEvent('link', 'edit', {}, 'link', editId);
    } else {
      const res = await API.createLink(payload);
      showToast('¡Enlace guardado en el banco visual!', 'success');
      if (res && res._gamification) handleGamificationEventResult(res._gamification);
      API.trackEvent('link', 'create', {}, 'link', res && res.id);
    }
    closeLinkModal();
    await loadLinks();
    await loadStats();
    await loadAnalytics();
    if (State.view === 'domain' && State.domainDetail) {
      await openDomainDetail(State.domainDetail.root_domain);
    }
  } catch (err) {
    showToast('Error al guardar enlace', 'error');
  }
}

// Batch Import
async function handleBatchImport() {
  const text = document.getElementById('batchTextarea').value.trim();
  if (!text) {
    showToast('Por favor pega al menos una URL', 'info');
    return;
  }

  const profileId = document.getElementById('batchSelectProfile').value ? parseInt(document.getElementById('batchSelectProfile').value) : null;
  const categoryId = document.getElementById('batchSelectCategory').value ? parseInt(document.getElementById('batchSelectCategory').value) : null;

  const btn = document.getElementById('btnConfirmBatch');
  btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Procesando...';
  try {
    const res = await API.batchImport(text, profileId, categoryId);
    showToast(`¡Se importaron ${res.imported_count} pestañas! Tu navegador está libre.`, 'success');
    API.trackEvent('link', 'batch_import', { count: res.imported_count });
    document.getElementById('batchModal').classList.remove('active');
    document.getElementById('batchTextarea').value = '';

    if (res && res._gamification) handleGamificationEventResult(res._gamification);
    await loadLinks();
    await loadStats();
    await loadAnalytics();
  } catch (err) {
    showToast('Error al importar pestañas', 'error');
  } finally {
    btn.innerHTML = '<i class="fa-solid fa-bolt"></i> Procesar & Vaciar Navegador';
  }
}

// ============================================================
// DATABASE EXPORT / IMPORT / BACKUPS (ZERO DATA LOSS)
// ============================================================
async function loadDatabasePanel() {
  try {
    const info = await API.getDbInfo();
    if (info && !info.error) {
      document.getElementById('dbPathText').textContent = info.db_path || '-';
      document.getElementById('dbInfoLinks').textContent = info.links ?? '-';
      document.getElementById('dbInfoCredentials').textContent = info.credentials ?? '-';
      document.getElementById('dbInfoSublinks').textContent = info.sublinks ?? '-';
      document.getElementById('dbInfoSize').textContent = info.size_kb ? `${info.size_kb} KB` : '-';
      document.getElementById('dbInfoModified').textContent = info.modified || '-';
      document.getElementById('dbInfoBackups').textContent = info.backup_count ?? '-';
    }
    await loadAutoBackups();
  } catch (err) {
    console.error('Error cargando información de la base de datos:', err);
  }
}

async function loadAutoBackups() {
  const container = document.getElementById('autoBackupsList');
  try {
    const backups = await API.listAutoBackups();
    container.innerHTML = '';

    if (!backups || backups.length === 0) {
      container.innerHTML = '<div class="db-empty">Todavía no hay copias. Crea una con el botón de arriba.</div>';
      return;
    }

    backups.slice(0, 30).forEach(backup => {
      const row = document.createElement('div');
      row.className = 'auto-backup-row';
      row.innerHTML = `
        <div class="auto-backup-info">
          <i class="fa-solid fa-database"></i>
          <div>
            <strong>${escapeHtml(backup.filename)}</strong>
            <span>${escapeHtml(backup.modified)} · ${backup.size_kb} KB</span>
          </div>
        </div>
        <button class="glass-btn btn-compact btn-restore-backup" data-filename="${escapeHtml(backup.filename)}">
          <i class="fa-solid fa-clock-rotate-left"></i> Restaurar
        </button>
      `;
      container.appendChild(row);
    });
  } catch (err) {
    container.innerHTML = '<div class="db-empty">No se pudo leer la lista de copias.</div>';
  }
}

async function exportDatabaseFile() {
  showToast('Preparando copia de seguridad...', 'info');
  window.location.href = API.getExportDbUrl();
}

async function exportDatabaseJson() {
  showToast('Preparando respaldo portable...', 'info');
  window.location.href = API.getExportJsonUrl();
}

async function createBackupNow() {
  const res = await API.createBackup();
  if (res && res.success) {
    showToast('Copia de seguridad creada', 'success');
    await loadDatabasePanel();
  } else {
    showToast((res && (res.error || res.message)) || 'No se pudo crear la copia', 'error');
  }
}

async function restoreBackupFile(filename) {
  const ok = await safeConfirm(
    '¿Restaurar esta copia?',
    'La base de datos actual se reemplazará. Antes se crea automáticamente una copia de seguridad adicional.'
  );
  if (!ok) return;

  showToast('Restaurando copia...', 'info');
  const res = await API.restoreAutoBackup(filename);
  if (res && res.success) {
    showToast('Base de datos restaurada', 'success');
    resetChatAfterRestore();
    await refreshAllData();
    await loadDatabasePanel();
  } else {
    showToast((res && res.message) || 'No se pudo restaurar', 'error');
  }
}

async function importDatabaseFile(file) {
  if (!file) return;
  const ok = await safeConfirm(
    '¿Importar esta base de datos?',
    'Se reemplazarán los datos actuales. Se guardará una copia automática antes de continuar.'
  );
  if (!ok) return;

  const formData = new FormData();
  formData.append('file', file);
  const res = await API.importDbFile(formData);

  if (res && res.success) {
    showToast('Base de datos importada correctamente', 'success');
    resetChatAfterRestore();
    await refreshAllData();
    await loadDatabasePanel();
  } else {
    showToast((res && (res.message || res.error)) || 'Importación fallida', 'error');
  }
}

async function importJsonPayload(file) {
  if (!file) return;

  let payload;
  try {
    payload = JSON.parse(await file.text());
  } catch (err) {
    showToast('El archivo no es un JSON válido', 'error');
    return;
  }

  let mode = 'merge';
  if (typeof Swal !== 'undefined') {
    const result = await Swal.fire({
      title: '¿Cómo quieres importar?',
      html: '<div style="font-size:13px; line-height:1.5;">' +
        '<strong>Fusionar</strong> conserva lo que ya tienes y añade lo que falte.<br>' +
        '<strong>Reemplazar</strong> borra la base actual y restaura el respaldo completo.</div>',
      icon: 'question',
      showDenyButton: true,
      showCancelButton: true,
      confirmButtonText: 'Fusionar (recomendado)',
      denyButtonText: 'Reemplazar todo',
      cancelButtonText: 'Cancelar',
      customClass: { popup: 'swal2-glass-popup', confirmButton: 'swal2-glass-confirm', cancelButton: 'swal2-glass-cancel' }
    });
    if (result.isConfirmed) mode = 'merge';
    else if (result.isDenied) mode = 'replace';
    else return;
  } else {
    mode = window.confirm(
      'Aceptar = Fusionar (recomendado)\nCancelar = Reemplazar todo (borra la base actual)'
    ) ? 'merge' : 'replace';
  }

  showToast('Importando respaldo...', 'info');
  const res = await API.importJsonData(payload, mode);
  if (res && res.success) {
    showToast(`Respaldo importado: ${res.imported_links || 0} enlaces`, 'success');
    resetChatAfterRestore();
    await refreshAllData();
    await loadDatabasePanel();
  } else {
    showToast((res && (res.error || res.message)) || 'Importación fallida', 'error');
  }
}

function updateFilterBanner() {
  const banner = document.getElementById('activeFilterNotice');
  const text = document.getElementById('activeFilterText');
  const parts = [];

  if (State.currentProfileId) {
    const p = State.profiles.find(x => x.id === State.currentProfileId);
    if (p) parts.push(`Perfil: <strong>${escapeHtml(p.name)}</strong>`);
  }
  if (State.currentCategoryId) {
    const c = State.categories.find(x => x.id === State.currentCategoryId);
    if (c) parts.push(`Tema: <strong>${escapeHtml(c.name)}</strong>`);
  }
  if (State.domain.currentRootDomain) {
    parts.push(`Dominio: <strong>${escapeHtml(State.domain.currentRootDomain)}</strong>`);
  }
  if (State.searchQuery) {
    parts.push(`Búsqueda: "<em>${escapeHtml(State.searchQuery)}</em>"`);
  }
  if (State.activeView === 'favorites') parts.push('⭐ <strong>Favoritos</strong>');
  if (State.activeView === 'unread') parts.push('⏳ <strong>Por Leer</strong>');

  if (parts.length > 0) {
    banner.style.display = 'flex';
    text.innerHTML = `Filtro activo: ${parts.join(' &bull; ')}`;
  } else {
    banner.style.display = 'none';
  }
}

// Toast
function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = 'toast animate__animated animate__fadeInUp';
  let icon = '<i class="fa-solid fa-info-circle" style="color: var(--primary);"></i>';
  if (type === 'success') icon = '<i class="fa-solid fa-circle-check" style="color: #34d399;"></i>';
  if (type === 'error') icon = '<i class="fa-solid fa-circle-xmark" style="color: #ef4444;"></i>';

  toast.innerHTML = `<span>${icon}</span><span>${escapeHtml(message)}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(8px)';
    toast.style.transition = 'all 0.25s ease';
    setTimeout(() => toast.remove(), 260);
  }, 2600);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
