/* =========================================================
   SadCat Gamble — Frontend JS
   ========================================================= */

const API_BASE = '/api';
const REFRESH_INTERVAL = 60_000; // Auto-refresh every 60s

// ---- Pixel rocket cursor ----
(function initRocket() {
  const SZ = 4; // 1 pixel unit size in px
  // Rocket shape: [col, row, color] — origin top-left
  // Drawing a small pixel rocket pointing up, flying right (rotated 90deg via CSS)
  const pixels = [
    // nose
    [3,0,'#FF2222'],
    // body
    [2,1,'#FF4444'],[3,1,'#FF2222'],[4,1,'#FF4444'],
    [1,2,'#FF5555'],[2,2,'#FF2222'],[3,2,'#FF2222'],[4,2,'#FF2222'],[5,2,'#FF5555'],
    [1,3,'#FF4444'],[2,3,'#FF2222'],[3,3,'#FFFFFF'],[4,3,'#FF2222'],[5,3,'#FF4444'],
    [2,4,'#FF4444'],[3,4,'#FF2222'],[4,4,'#FF4444'],
    // wings
    [0,3,'#CC1111'],[6,3,'#CC1111'],
    [0,4,'#CC1111'],[6,4,'#CC1111'],
    // exhaust flame
    [2,5,'#FFA500'],[3,5,'#FFDD00'],[4,5,'#FFA500'],
    [3,6,'#FF6600'],
  ];

  const W = 7, H = 7;
  const canvas = document.createElement('canvas');
  canvas.width  = W * SZ;
  canvas.height = H * SZ;
  canvas.style.cssText = 'position:fixed;pointer-events:none;z-index:99999;display:none;image-rendering:pixelated;';
  document.body.appendChild(canvas);
  const ctx = canvas.getContext('2d');
  pixels.forEach(([c, r, color]) => {
    ctx.fillStyle = color;
    ctx.fillRect(c * SZ, r * SZ, SZ, SZ);
  });

  // Trail particles
  const trail = [];
  const TRAIL_LEN = 10;

  let mx = -200, my = -200;
  let rx = -200, ry = -200;
  let angle = 0;
  let targetAngle = 0;

  document.addEventListener('mousemove', e => {
    const dx = e.clientX - rx;
    const dy = e.clientY - ry;
    if (Math.abs(dx) > 1 || Math.abs(dy) > 1) {
      targetAngle = Math.atan2(dy, dx) * (180 / Math.PI) + 90;
    }
    mx = e.clientX;
    my = e.clientY;
    canvas.style.display = 'block';
  });

  document.addEventListener('mouseleave', () => { canvas.style.display = 'none'; });

  // Trail container
  const trailContainer = document.createElement('div');
  trailContainer.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:99998;';
  document.body.appendChild(trailContainer);

  function lerp(a, b, t) { return a + (b - a) * t; }
  function lerpAngle(a, b, t) {
    let diff = ((b - a + 540) % 360) - 180;
    return a + diff * t;
  }

  function spawnTrailPixel(x, y) {
    const p = document.createElement('div');
    const colors = ['#FF2222','#FF6600','#FFA500','#FFDD00'];
    const color  = colors[Math.floor(Math.random() * colors.length)];
    const size   = SZ * (Math.random() > 0.5 ? 2 : 1);
    p.style.cssText = `
      position:fixed;width:${size}px;height:${size}px;
      background:${color};
      left:${x - size/2}px;top:${y - size/2}px;
      pointer-events:none;
      image-rendering:pixelated;
      transition:opacity 0.35s linear, transform 0.35s linear;
    `;
    trailContainer.appendChild(p);
    trail.push(p);
    requestAnimationFrame(() => {
      p.style.opacity = '0';
      p.style.transform = `translate(${(Math.random()-0.5)*12}px,${(Math.random()-0.5)*12}px)`;
    });
    setTimeout(() => { if (p.parentNode) p.parentNode.removeChild(p); }, 400);
    if (trail.length > TRAIL_LEN * 3) {
      const old = trail.shift();
      if (old && old.parentNode) old.parentNode.removeChild(old);
    }
  }

  let lastTrail = 0;
  function animate(ts) {
    rx = lerp(rx, mx, 0.18);
    ry = lerp(ry, my, 0.18);
    angle = lerpAngle(angle, targetAngle, 0.12);

    const hw = canvas.width  / 2;
    const hh = canvas.height / 2;
    canvas.style.left = (rx - hw) + 'px';
    canvas.style.top  = (ry - hh) + 'px';
    canvas.style.transform = `rotate(${angle}deg)`;

    if (ts - lastTrail > 40) {
      // spawn trail at exhaust position (bottom center of rocket, rotated)
      const rad = (angle - 90) * Math.PI / 180;
      const ex = rx + Math.cos(rad + Math.PI) * hh * 0.9;
      const ey = ry + Math.sin(rad + Math.PI) * hh * 0.9;
      spawnTrailPixel(ex, ey);
      lastTrail = ts;
    }

    requestAnimationFrame(animate);
  }
  requestAnimationFrame(animate);
})();

// ---- Pixel star particles ----
(function spawnParticles() {
  const container = document.getElementById('bgParticles');
  if (!container) return;
  const colors = ['#00E5FF', '#4D9FFF', '#1E5CFF', '#FFD700', '#00FF88'];
  for (let i = 0; i < 40; i++) {
    const p = document.createElement('div');
    const size = (Math.random() > 0.5) ? 2 : 4;
    const color = colors[Math.floor(Math.random() * colors.length)];
    const dur = (2 + Math.random() * 4).toFixed(1);
    const delay = -(Math.random() * 4).toFixed(1);
    p.style.cssText = `
      position:absolute;
      width:${size}px; height:${size}px;
      left:${Math.random() * 100}%;
      top:${Math.random() * 100}%;
      background:${color};
      box-shadow:0 0 ${size * 2}px ${color};
      opacity:0;
      animation:pixelBlink ${dur}s ${delay}s infinite steps(2);
    `;
    container.appendChild(p);
  }
  // inject keyframes once
  if (!document.getElementById('pixelBlink-style')) {
    const s = document.createElement('style');
    s.id = 'pixelBlink-style';
    s.textContent = '@keyframes pixelBlink{0%{opacity:0}50%{opacity:0.9}100%{opacity:0}}';
    document.head.appendChild(s);
  }
})();

// ---- Utilities ----
function formatScore(n) {
  if (n == null) return '—';
  return n.toString();
}

function formatDate(iso) {
  if (!iso) return 'N/A';
  return new Intl.DateTimeFormat('en-US', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  }).format(new Date(iso));
}

function avatarHtml(entry) {
  if (entry.avatar_b64) {
    return `<img src="data:image/jpeg;base64,${entry.avatar_b64}" alt="@${entry.username}" style="width:100%;height:100%;object-fit:cover;display:block;image-rendering:pixelated;">`;
  }
  return avatarInitials(entry.username);
}

function avatarInitials(name) {
  if (!name) return '?';
  return name.replace('@', '').slice(0, 2).toUpperCase();
}

function rankIcon(rank) {
  return rank;
}

function getPrize(rank) {
  if (rank === 1) return '25 SOL + PRIVATE';
  if (rank === 2) return '15 SOL + PRIVATE';
  if (rank === 3) return '10 SOL + PRIVATE';
  if (rank >= 4 && rank <= 18) return '5 SOL';
  if (rank >= 19 && rank <= 30) return 'PRIVATE';
  return null;
}

function getRefPrize(rank) {
  if (rank === 1) return '50 SOL';
  if (rank === 2) return '30 SOL';
  if (rank >= 3 && rank <= 5) return '15 SOL';
  return null;
}

function showToast(msg, isError = false) {
  const existing = document.querySelector('.toast');
  if (existing) existing.remove();

  const t = document.createElement('div');
  t.className = 'toast' + (isError ? ' error' : '');
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

// ---- Leaderboard rendering ----
function renderPodium(entries) {
  const podium = document.getElementById('podium');
  podium.innerHTML = '';

  const top3 = entries.slice(0, 3);
  // Reorder: 2nd, 1st, 3rd for visual podium
  const order = [top3[1], top3[0], top3[2]].filter(Boolean);
  const actualRanks = [2, 1, 3];

  order.forEach((entry, i) => {
    if (!entry) return;
    const rank = entry.rank;
    const item = document.createElement('div');
    item.className = 'podium-item';
    item.dataset.rank = rank;
    item.innerHTML = `
      <div class="podium-avatar">${entry.avatar_b64
        ? `<img src="data:image/jpeg;base64,${entry.avatar_b64}" style="width:100%;height:100%;object-fit:cover;display:block;image-rendering:pixelated;">`
        : avatarInitials(entry.username)}
      </div>
      <div class="podium-name">@${entry.username}</div>
      <div class="podium-score">${formatScore(entry.score)}</div>
      <div class="podium-block">${rank}</div>
    `;
    podium.appendChild(item);
  });
}

function renderTable(entries) {
  const body = document.getElementById('leaderboardBody');
  body.innerHTML = '';

  if (!entries || entries.length === 0) {
    body.innerHTML = `
      <div class="empty-state">
        <p>NO DATA YET...</p>
      </div>`;
    return;
  }

  const maxScore = Math.max(...entries.map(e => e.score || 0), 1);

  entries.forEach((entry, idx) => {
    const rankClass = entry.rank <= 3 ? `rank-${entry.rank}` : '';
    const barWidth = Math.round((entry.score / maxScore) * 100);

    const row = document.createElement('div');
    row.className = 'leaderboard-row';
    row.style.animationDelay = `${idx * 0.04}s`;
    row.innerHTML = `
      <div class="rank-badge ${rankClass}">${rankIcon(entry.rank)}</div>
      <div class="player-info">
        <div class="player-ava${entry.rank <= 3 ? ' rank-ava-' + entry.rank : ''}">${avatarHtml(entry)}</div>
        <div>
          <div class="player-name">@${entry.username}</div>
        </div>
      </div>
      <div class="score-cell">
        ${formatScore(entry.score)}
        ${getPrize(entry.rank) ? `<div class="prize-tag ${entry.rank <= 3 ? 'prize-r' + entry.rank : ''}">» ${getPrize(entry.rank)}</div>` : ''}
        <div class="score-bar-wrap">
          <div class="score-bar" style="width:${barWidth}%"></div>
        </div>
      </div>
    `;
    body.appendChild(row);
  });
}

function updateStatus(lastUpdated) {
  const dot = document.getElementById('statusDot');
  const label = document.getElementById('lastUpdated');

  if (lastUpdated) {
    dot.className = 'dot green';
    label.textContent = 'Updated ' + formatDate(lastUpdated);
  } else {
    dot.className = 'dot red';
    label.textContent = 'No data';
  }
}

// ---- Fetch leaderboard ----
async function fetchLeaderboard() {
  try {
    const res = await fetch(`${API_BASE}/leaderboard`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error('Leaderboard fetch error:', err);
    return null;
  }
}

async function loadLeaderboard() {
  const data = await fetchLeaderboard();

  if (!data) {
    document.getElementById('leaderboardBody').innerHTML = `
      <div class="empty-state">
        <p>API UNAVAILABLE</p>
      </div>`;
    updateStatus(null);
    return;
  }

  renderPodium(data.entries || []);
  renderTable(data.entries || []);
  updateStatus(data.last_updated);
}

// ---- Fetch ref leaderboard ----
async function fetchRefLeaderboard() {
  try {
    const res = await fetch(`${API_BASE}/refleaderboard`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error('Ref leaderboard fetch error:', err);
    return null;
  }
}

function renderRefTable(entries) {
  const body = document.getElementById('refLeaderboardBody');
  body.innerHTML = '';

  if (!entries || entries.length === 0) {
    body.innerHTML = `<div class="empty-state"><p>NO REF DATA YET...</p></div>`;
    return;
  }

  const maxRefs = Math.max(...entries.map(e => e.refs || 0), 1);

  entries.forEach((entry, idx) => {
    const rankClass = entry.rank <= 3 ? `rank-${entry.rank}` : '';
    const barWidth = Math.round((entry.refs / maxRefs) * 100);
    const row = document.createElement('div');
    row.className = 'leaderboard-row';
    row.style.animationDelay = `${idx * 0.04}s`;
    row.innerHTML = `
      <div class="rank-badge ${rankClass}">${entry.rank}</div>
      <div class="player-info">
        <div class="player-ava${entry.rank <= 3 ? ' rank-ava-' + entry.rank : ''}">${avatarHtml(entry)}</div>
        <div>
          <div class="player-name">${entry.display_name && entry.display_name !== entry.username ? entry.display_name : '@' + entry.username}</div>
          ${entry.display_name && entry.display_name !== entry.username ? `<div class="player-handle">@${entry.username}</div>` : ''}
        </div>
      </div>
      <div class="score-cell">
        ${entry.refs}
        ${getRefPrize(entry.rank) ? `<div class="prize-tag ${entry.rank <= 3 ? 'prize-r' + entry.rank : ''}">» ${getRefPrize(entry.rank)}</div>` : ''}
        <div class="score-bar-wrap"><div class="score-bar" style="width:${barWidth}%"></div></div>
      </div>
    `;
    body.appendChild(row);
  });
}

async function loadRefLeaderboard() {
  const data = await fetchRefLeaderboard();
  const dot = document.getElementById('refStatusDot');
  const label = document.getElementById('refLastUpdated');

  if (!data) {
    document.getElementById('refLeaderboardBody').innerHTML =
      `<div class="empty-state"><p>API UNAVAILABLE</p></div>`;
    if (dot) dot.className = 'dot red';
    if (label) label.textContent = 'ERROR';
    return;
  }

  renderRefTable(data.entries || []);

  if (data.last_updated) {
    if (dot) dot.className = 'dot green';
    if (label) label.textContent = 'Updated ' + formatDate(data.last_updated);
  } else {
    if (dot) dot.className = 'dot red';
    if (label) label.textContent = 'NO DATA';
  }
}

// ---- Fetch contest info ----
async function loadContest() {
  try {
    const res = await fetch(`${API_BASE}/contest`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const items = await res.json();

    if (!items || items.length === 0) return; // keep placeholder

    const grid = document.getElementById('contestGrid');
    if (!grid) return;
    grid.innerHTML = '';

    items.forEach(c => {
      const card = document.createElement('div');
      card.className = 'contest-card';
      card.innerHTML = `
        <div class="contest-card-title">${c.title}</div>
        <div class="contest-card-desc">${c.description || 'Details coming soon...'}</div>
        <div class="contest-meta">
          ${c.prize_pool ? `<div class="contest-meta-item"><span class="meta-label">Prize Pool</span><span class="meta-value">${c.prize_pool}</span></div>` : ''}
          ${c.start_date ? `<div class="contest-meta-item"><span class="meta-label">Starts</span><span class="meta-value">${formatDate(c.start_date)}</span></div>` : ''}
          ${c.end_date ? `<div class="contest-meta-item"><span class="meta-label">Ends</span><span class="meta-value">${formatDate(c.end_date)}</span></div>` : ''}
        </div>
      `;
      grid.appendChild(card);
    });
  } catch (err) {
    console.warn('Contest fetch error:', err);
  }
}

// ---- Gamble Room ----
function fmtMcap(v) {
  if (!v || v === 0) return 'N/A';
  if (v >= 1e9) return '$' + (v / 1e9).toFixed(2) + 'B';
  if (v >= 1e6) return '$' + (v / 1e6).toFixed(2) + 'M';
  if (v >= 1e3) return '$' + (v / 1e3).toFixed(1) + 'K';
  return '$' + v.toFixed(0);
}

function fmtPrice(v) {
  if (!v || v === 0) return 'N/A';
  if (v < 0.000001) return '$' + v.toExponential(2);
  if (v < 0.01) return '$' + v.toFixed(6);
  if (v < 1) return '$' + v.toFixed(4);
  return '$' + v.toFixed(2);
}

function timeAgo(iso) {
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
  return Math.floor(diff / 86400) + 'd ago';
}

function truncateCA(ca) {
  if (!ca) return '';
  return ca.slice(0, 6) + '...' + ca.slice(-4);
}

function renderCallCard(call) {
  const ath = call.ath_x && call.ath_x > 0 ? call.ath_x.toFixed(2) + 'x' : '—';
  const symbol = call.token_symbol ? '$' + call.token_symbol : '???';
  const name = call.token_name || call.ca_address.slice(0, 12) + '...';
  const excerpt = call.msg_text ? call.msg_text.replace(/\n+/g, ' ').slice(0, 120) : '';
  const ch = call.price_change_24h;
  const chClass = ch > 0 ? 'up' : ch < 0 ? 'down' : '';
  const chStr = ch ? (ch > 0 ? '+' : '') + ch.toFixed(1) + '%' : 'N/A';

  const card = document.createElement('div');
  card.className = 'call-card' + (call.is_live ? ' is-live' : '');
  card.innerHTML = `
    <div class="call-card-header">
      <div class="call-token-info">
        <div class="call-symbol">${symbol}</div>
        <div class="call-name">${name}</div>
      </div>
      ${call.is_live ? '<div class="call-live-badge">LIVE</div>' : ''}
      <div class="call-ath">${ath}</div>
    </div>
    ${excerpt ? `<div class="call-excerpt">${excerpt}</div>` : ''}
    <div class="call-ca">
      <span class="call-ca-addr" title="${call.ca_address}">${truncateCA(call.ca_address)}</span>
      <button class="call-copy-btn" onclick="navigator.clipboard.writeText('${call.ca_address}').then(()=>this.textContent='OK').catch(()=>{});event.stopPropagation()">COPY</button>
    </div>
    <div class="call-stats">
      <div class="call-stat"><span>MCAP</span><span class="call-stat-val">${fmtMcap(call.current_mcap)}</span></div>
      <div class="call-stat"><span>24H</span><span class="call-stat-val ${chClass}">${chStr}</span></div>
      <div class="call-stat"><span>VOL</span><span class="call-stat-val">${fmtMcap(call.volume_24h)}</span></div>
      <div class="call-stat"><span>LIQ</span><span class="call-stat-val">${fmtMcap(call.liquidity_usd)}</span></div>
    </div>
    <div class="call-footer">
      <span class="call-date">${timeAgo(call.msg_date)}</span>
      ${call.dex_url ? `<a class="call-dex-btn" href="${call.dex_url}" target="_blank" rel="noopener">[ DEXSCREENER ]</a>` : '<span class="call-date">NO PAIR YET</span>'}
    </div>
  `;
  return card;
}

async function loadGambleCalls() {
  const dot = document.getElementById('gambleStatusDot');
  const label = document.getElementById('gambleLastUpdated');
  const liveEl = document.getElementById('gambleLiveCalls');
  const oldEl = document.getElementById('gambleOldCalls');
  const liveGroup = document.getElementById('gambleLiveGroup');
  const oldGroup = document.getElementById('gambleOldGroup');
  if (!liveEl || !oldEl) return;
  try {
    const res = await fetch(`${API_BASE}/gamble`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (dot) dot.className = 'dot green';
    if (label) label.textContent = data.last_updated ? 'Updated ' + formatDate(data.last_updated) : 'LIVE';

    // Live calls
    liveEl.innerHTML = '';
    if (data.live && data.live.length > 0) {
      data.live.forEach(c => liveEl.appendChild(renderCallCard(c)));
      liveGroup.style.display = '';
    } else {
      liveEl.innerHTML = '<div class="call-no-data">NO LIVE CALLS RIGHT NOW</div>';
    }

    // Old calls
    oldEl.innerHTML = '';
    if (data.old && data.old.length > 0) {
      data.old.forEach(c => oldEl.appendChild(renderCallCard(c)));
      oldGroup.style.display = '';
    } else {
      oldGroup.style.display = 'none';
    }
  } catch (err) {
    console.error('Gamble fetch error:', err);
    if (dot) dot.className = 'dot red';
    if (label) label.textContent = 'ERROR';
    liveEl.innerHTML = '<div class="call-no-data">API UNAVAILABLE</div>';
  }
}

// ---- Manual refresh button ----
window.refreshLeaderboard = async function () {
  const btn = document.getElementById('refreshBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="btn-icon">↻</span> Refreshing...';

  try {
    await fetch(`${API_BASE}/leaderboard/refresh`, { method: 'POST' });
    await loadLeaderboard();
    showToast('REFRESHED!');
  } catch (err) {
    showToast('ERROR: ' + err.message, true);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span class="btn-icon">↻</span> Refresh';
  }
};

// ---- Raffle Winners ----
function _renderWinnerCards(winners) {
  const list = document.getElementById('raffleWinnersList');
  if (!list || !winners.length) return;
  list.innerHTML = winners.map(w => {
    const date    = new Date(w.date || w.created_at || Date.now());
    const dateStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                  + ' ' + date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
    const avaHtml = (w.avatar || w.winner_avatar)
      ? `<img class="rw-avatar" src="${w.avatar || ('data:image/jpeg;base64,' + w.winner_avatar)}" alt="" />`
      : `<div class="rw-avatar-ph" style="background:${w.color||w.winner_color||'#1e3a8a'}22;border-color:${w.color||w.winner_color||'#4d9fff'}">${(w.name||w.winner_name||'?').slice(0,1)}</div>`;
    const ticket = w.ticket || w.winning_ticket;
    const total  = w.total  || w.total_tickets;
    const rangeStart = w.rangeStart || w.winner_range_start;
    const rangeEnd   = w.rangeEnd   || w.winner_range_end;
    const spinId     = w.spinId     || w.id;
    const rangeStr   = (rangeStart && rangeEnd) ? ` (${rangeStart}\u2013${rangeEnd})` : '';
    const ticketHtml = ticket && total
      ? `<div class="rw-ticket">TICKET #${ticket}/${total}${rangeStr}</div>`
      : '';
    const proof = w.proof || w.verify_url || (spinId ? `/api/wheel/verify/${spinId}` : null);
    const proofHtml = proof
      ? `<a class="rw-proof" href="${proof}" target="_blank" rel="noopener">VERIFY → RANDOM.ORG</a>`
      : '';
    return `<div class="rw-card">
      ${avaHtml}
      <div class="rw-info">
        <div class="rw-name">${w.name || w.winner_name}</div>
        <div class="rw-date">${dateStr}</div>
        ${ticketHtml}${proofHtml}
      </div>
      <div class="rw-prize">${w.prize || '10 SOL'}</div>
    </div>`;
  }).join('');
}

async function renderRaffleWinners() {
  const list = document.getElementById('raffleWinnersList');
  if (!list) return;

  // Try API first (authoritative, survives browser/localStorage resets)
  try {
    const res = await fetch('/api/wheel/history?limit=3');
    if (res.ok) {
      const rows = await res.json();
      if (rows && rows.length) {
        _renderWinnerCards(rows);
        return;
      }
    }
  } catch(e) { /* fallthrough to localStorage */ }

  // Fallback: localStorage (populated by wheel.js after spin animation)
  let winners = [];
  try { winners = JSON.parse(localStorage.getItem('sadcat_raffle_winners') || '[]'); } catch(e) {}
  _renderWinnerCards(winners);
}

// ---- Smooth scroll for nav links ----
document.querySelectorAll('.nav-link[href^="#"]').forEach(link => {
  link.addEventListener('click', e => {
    e.preventDefault();
    const target = document.querySelector(link.getAttribute('href'));
    if (target) target.scrollIntoView({ behavior: 'smooth' });
    document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
    link.classList.add('active');
  });
});

// ---- Init ----
(async function init() {
  await Promise.all([
    renderRaffleWinners(),
    loadLeaderboard(),
    loadRefLeaderboard(),
    loadContest(),
    loadGambleCalls(),
  ]);

  // Auto-refresh every minute
  setInterval(loadLeaderboard, REFRESH_INTERVAL);
  setInterval(loadRefLeaderboard, REFRESH_INTERVAL);
  setInterval(loadGambleCalls, REFRESH_INTERVAL);
})();
