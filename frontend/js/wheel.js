'use strict';

// ── CONFIG ────────────────────────────────────────────────────────────────────
const CARD_W       = 134;   // px: card width + gap (128 + 6)
const TOP_N        = 20;    // take top-N from leaderboard
const POOL_REPS    = 4;     // how many full pools in the strip (reduced for perf)
const SPIN_MS      = 6000;  // spin duration ms
const SPIN_SECONDS = 5 * 60; // countdown interval (fallback only)

const SEG_COLORS = [
  '#0066ff','#00ccff','#9900ff','#ff6600','#00cc44',
  '#ff0066','#ffcc00','#00ffcc','#ff3300','#6600ff',
  '#00ff66','#ff9900','#3366ff','#ff0099','#33ff00',
  '#ff3366','#00ff99','#cc00ff','#ff9966','#0099ff',
];

let PARTICIPANTS  = [];
let totalTickets  = 0;
let spinning      = false;
let autoSpun      = false;
let stripData     = [];

// ── Load top-N from /api/leaderboard ─────────────────────────────────────────
async function loadParticipants() {
  try {
    const res  = await fetch('/api/leaderboard');
    const data = await res.json();
    const top  = (data.entries || []).slice(0, TOP_N);
    if (!top.length) throw new Error('empty');

    const maxScore = top[0].score || 1;
    PARTICIPANTS = top.map((e, i) => ({
      name:    e.display_name || e.username || ('Player ' + (i + 1)),
      username: e.username,
      tickets: Math.max(1, Math.round((e.score / maxScore) * 100)),
      // avatar_b64 is stored in DB — served straight from API
      avatar:  e.avatar_b64 ? 'data:image/jpeg;base64,' + e.avatar_b64 : null,
      color:   SEG_COLORS[i % SEG_COLORS.length],
    }));
    totalTickets = PARTICIPANTS.reduce((s, p) => s + p.tickets, 0);

  } catch (err) {
    console.warn('Leaderboard unavailable, using placeholders:', err);
    PARTICIPANTS = Array.from({ length: 20 }, (_, i) => ({
      name:    'Player ' + (i + 1),
      username: '',
      tickets: Math.max(1, 100 - i * 4),
      avatar:  null,
      color:   SEG_COLORS[i % SEG_COLORS.length],
    }));
    totalTickets = PARTICIPANTS.reduce((s, p) => s + p.tickets, 0);
  }

  // Assign sequential ticket ranges
  let _cum = 0;
  PARTICIPANTS.forEach(p => {
    p.ticketStart = _cum + 1;
    p.ticketEnd   = _cum + p.tickets;
    _cum = p.ticketEnd;
  });
  buildRoulette();
  renderParticipants();
}

// ── Build weighted pool (shuffle) ─────────────────────────────────────────────
function makePool() {
  const pool = [];
  PARTICIPANTS.forEach(p => {
    const slots = Math.max(1, Math.round(5 * p.tickets / 100)); // max 5 per participant
    for (let i = 0; i < slots; i++) pool.push(p);
  });
  for (let i = pool.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [pool[i], pool[j]] = [pool[j], pool[i]];
  }
  return pool;
}

// ── Create single roulette card ───────────────────────────────────────────────
function makeCard(p) {
  const el = document.createElement('div');
  el.className = 'r-card';
  el.style.borderColor = p.color + '88';
  const initials = p.name.slice(0, 1).toUpperCase();
  const avaHtml = p.avatar
    ? `<img class="r-card-avatar" src="${p.avatar}" alt="" loading="lazy" />`
    : `<div class="r-card-avatar no-pic" style="background:${p.color}22;border-color:${p.color}">${initials}</div>`;
  const rangeStr = p.ticketStart === p.ticketEnd
    ? `#${p.ticketStart}`
    : `#${p.ticketStart}–${p.ticketEnd}`;
  el.innerHTML = `
    ${avaHtml}
    <div class="r-card-name">${p.name}</div>
    <div class="r-card-tickets">${rangeStr}</div>`;
  return el;
}

// ── Build the full strip (POOL_REPS copies) ───────────────────────────────────
function buildRoulette() {
  const inner = document.getElementById('rouletteInner');
  inner.innerHTML = '';
  inner.style.transition = 'none';
  inner.style.transform  = 'translateX(0)';
  stripData = [];
  for (let rep = 0; rep < POOL_REPS; rep++) {
    makePool().forEach(p => {
      stripData.push(p);
      inner.appendChild(makeCard(p));
    });
  }
}

// ── Spin! (winner comes from server) ──────────────────────────────────────────────
function doSpin(winner) {
  if (spinning || !PARTICIPANTS.length) return;
  spinning = true;

  // Rebuild strip so winner lands in the last third under the pointer
  const inner = document.getElementById('rouletteInner');
  inner.innerHTML = '';
  inner.style.transition = 'none';
  inner.style.transform  = 'translateX(0)';
  stripData = [];

  for (let rep = 0; rep < POOL_REPS - 1; rep++) {
    makePool().forEach(p => { stripData.push(p); inner.appendChild(makeCard(p)); });
  }

  // Final pool: insert winner at 60-85% through it
  const finalPool = makePool();
  const insertAt  = Math.floor(finalPool.length * 0.6 + Math.random() * finalPool.length * 0.25);
  finalPool.splice(insertAt, 0, winner);
  finalPool.forEach(p => { stripData.push(p); inner.appendChild(makeCard(p)); });

  // Find winner card index — pick one from last 40% of strip
  let wIdx = stripData.lastIndexOf(winner);
  const cutoff = Math.floor(stripData.length * 0.6);
  const candidates = [];
  for (let i = cutoff; i < stripData.length; i++) {
    if (stripData[i] === winner) candidates.push(i);
  }
  if (candidates.length) wIdx = candidates[Math.floor(Math.random() * candidates.length)];

  const track   = document.getElementById('rouletteTrack');
  const centerX = track.clientWidth / 2;
  const offset  = (Math.random() - 0.5) * (CARD_W * 0.6); // slight randomness
  const targetTX = -(wIdx * CARD_W + CARD_W / 2 - centerX + offset);

  requestAnimationFrame(() => requestAnimationFrame(() => {
    inner.style.transition = `transform ${SPIN_MS}ms cubic-bezier(0.05, 0.9, 0.12, 1)`;
    inner.style.transform  = `translateX(${targetTX}px)`;
  }));

  setTimeout(() => {
    const cards = inner.querySelectorAll('.r-card');
    if (cards[wIdx]) cards[wIdx].classList.add('winner');
    setTimeout(() => showWinner(winner), 700);
    spinning = false;
    setTimeout(() => {
      buildRoulette();
      autoSpun = false; // allow next auto-spin only after strip is rebuilt
    }, 4000);
  }, SPIN_MS + 150);
}

// ── Winner modal ──────────────────────────────────────────────────────────────
function showWinner(p) {
  const chance = ((p.tickets / totalTickets) * 100).toFixed(1);
  document.getElementById('winnerName').textContent = p.name;
  document.getElementById('winnerSub').textContent  = p.tickets + ' TICKETS · ' + chance + '% CHANCE';

  const wrap = document.getElementById('modalAvatarWrap');
  wrap.innerHTML = p.avatar
    ? `<img class="modal-avatar" src="${p.avatar}" alt="${p.name}" />`
    : `<div class="modal-avatar-ph" style="background:${p.color}22;border-color:${p.color}">${p.name.slice(0,1)}</div>`;

  // Ticket number from random.org
  const stubEl  = document.getElementById('winnerTicketStub');
  const numEl   = document.getElementById('winnerTicketNum');
  const rangeEl = document.getElementById('winnerTicketRange');
  const proofEl = document.getElementById('winnerProof');
  if (p.winnerTicket && p.totalTickets) {
    numEl.textContent   = `TICKET #${p.winnerTicket}`;
    const rangeStr = (p.rangeStart && p.rangeEnd)
      ? `RANGE: #${p.rangeStart}\u2013#${p.rangeEnd} of ${p.totalTickets}`
      : `DRAWN FROM 1 TO ${p.totalTickets}`;
    rangeEl.textContent = rangeStr;
    stubEl.style.display  = '';
    numEl.style.display   = '';
    rangeEl.style.display = '';
  } else {
    stubEl.style.display = 'none';
  }
  if (p.verifyLink || p.randorgUrl) {
    const href = p.verifyLink || p.randorgUrl;
    proofEl.href        = href;
    proofEl.textContent = p.verifyLink
      ? `[ VERIFY DRAW #${p.spinId || ''} ON RANDOM.ORG \u2192 ]`
      : '[ VERIFY ON RANDOM.ORG ]';
    proofEl.style.display = '';
  } else {
    proofEl.style.display = 'none';
  }

  // Save winner to localStorage for display on main page
  const proofHref = p.verifyLink || p.randorgUrl || null;
  try {
    const winners = JSON.parse(localStorage.getItem('sadcat_raffle_winners') || '[]');
    winners.unshift({
      name:       p.name,
      avatar:     p.avatar || null,
      color:      p.color  || '#1e3a8a',
      prize:      '10 SOL',
      ticket:     p.winnerTicket  || null,
      total:      p.totalTickets  || null,
      rangeStart: p.rangeStart    || null,
      rangeEnd:   p.rangeEnd      || null,
      spinId:     p.spinId        || null,
      proof:      proofHref,
      date:       new Date().toISOString(),
    });
    winners.splice(3);
    localStorage.setItem('sadcat_raffle_winners', JSON.stringify(winners));
  } catch(e) {}

  document.getElementById('winnerModal').classList.add('show');
  launchSparkles();
}

document.getElementById('modalClose').addEventListener('click', () => {
  document.getElementById('winnerModal').classList.remove('show');
});

// ── Sparkles ──────────────────────────────────────────────────────────────────
function launchSparkles() {
  const container = document.getElementById('sparkleContainer');
  const colors = ['#ffd700','#00e5ff','#d500f9','#00e676','#ff1744'];
  for (let i = 0; i < 80; i++) {
    const el = document.createElement('div');
    el.style.cssText = `position:absolute;width:${4+Math.random()*6}px;height:${4+Math.random()*6}px;background:${colors[Math.floor(Math.random()*colors.length)]};left:${Math.random()*100}vw;top:${Math.random()*60+20}vh;border-radius:${Math.random()>.5?'50%':'2px'};opacity:1;pointer-events:none;transition:all ${1.5+Math.random()}s ease-out;box-shadow:0 0 6px currentColor;`;
    container.appendChild(el);
    setTimeout(() => { el.style.transform = `translateY(${-100-Math.random()*200}px) rotate(${Math.random()*720}deg)`; el.style.opacity = '0'; }, 50);
    setTimeout(() => el.remove(), 2500);
  }
}

// ── Participants table ────────────────────────────────────────────────────────
function renderParticipants() {
  const list = document.getElementById('participantsList');
  list.innerHTML = PARTICIPANTS.map((p, i) => {
    const chance  = ((p.tickets / totalTickets) * 100).toFixed(1);
    const rangeStr = p.ticketStart === p.ticketEnd
      ? `#${p.ticketStart}`
      : `#${p.ticketStart}–${p.ticketEnd}`;
    const avaHtml = p.avatar
      ? `<img class="part-ava" src="${p.avatar}" alt="" loading="lazy" />`
      : `<div class="part-ava-ph" style="background:${p.color}22;border:1px solid ${p.color}">${p.name.slice(0,1)}</div>`;
    return `<div class="part-row">
      <div class="part-rank">${i + 1}</div>
      ${avaHtml}
      <div class="part-info">
        <div class="part-name">${p.name}</div>
        <div class="part-tickets">${rangeStr} &middot; ${p.tickets} TICKETS</div>
      </div>
      <div class="part-chance">${chance}%</div>
    </div>`;
  }).join('');
  document.getElementById('totalTicketsInfo').textContent = 'TOTAL: ' + totalTickets + ' TICKETS';
}

// ── Countdown timer — synced to server (/api/wheel/state) ────────────────────
let serverNextSpinsAt = 0;  // unix ms, set from /api/wheel/state
let timeLeft = SPIN_SECONDS;

async function fetchWheelState() {
  try {
    const res = await fetch('/api/wheel/state');
    return await res.json();
  } catch (e) {
    return null;
  }
}

function syncTimerFromState(state) {
  if (state && state.next_spins_at) {
    const t = state.next_spins_at;
    if (t > Date.now() + 2000) {
      // Server gave us a future time — use it
      serverNextSpinsAt = t;
    } else {
      // Server time is in the past (or within 2s): advance to next cycle
      // so the timer doesn't immediately hit 0 and re-trigger a spin
      const elapsed   = Math.max(0, Date.now() - t);
      const cyclesAgo = Math.floor(elapsed / (SPIN_SECONDS * 1000));
      serverNextSpinsAt = t + (cyclesAgo + 1) * SPIN_SECONDS * 1000;
    }
  }
}

function updateTimer() {
  // Recalculate every tick from server timestamp → all tabs stay in sync
  if (serverNextSpinsAt) {
    timeLeft = Math.max(0, Math.ceil((serverNextSpinsAt - Date.now()) / 1000));
  } else {
    // Server state not yet received — count down locally as fallback
    timeLeft = Math.max(0, timeLeft - 1);
  }
  const m   = Math.floor(timeLeft / 60).toString().padStart(2, '0');
  const s   = (timeLeft % 60).toString().padStart(2, '0');
  const str = m + ':' + s;
  document.getElementById('timerDisplay').textContent = str;
  document.getElementById('cardTimer').textContent    = str;
  if (timeLeft <= 10) document.getElementById('timerDisplay').classList.add('urgent');
  else                document.getElementById('timerDisplay').classList.remove('urgent');

  if (timeLeft <= 0 && !spinning && !autoSpun) {
    autoSpun = true;
    // Immediately push timer forward so no second trigger fires while we wait
    serverNextSpinsAt = Date.now() + SPIN_SECONDS * 1000;
    timeLeft = SPIN_SECONDS;
    // Wait 1.5s so backend scheduler has time to pick winner, then fetch & spin
    setTimeout(async () => {
      const state = await fetchWheelState();
      if (state && state.next_spins_at && state.next_spins_at > Date.now()) {
        serverNextSpinsAt = state.next_spins_at; // sync only if server gave a future time
        // else: keep our optimistic push (Date.now() + SPIN_SECONDS*1000)
      }
      let winner = null;
      if (state && state.winner_username) {
        winner = PARTICIPANTS.find(p => p.username === state.winner_username) || null;
      }
      // Attach ticket proof data to winner object
      if (winner && state) {
        winner.winnerTicket = state.winner_ticket  || null;
        winner.totalTickets = state.total_tickets  || null;
        winner.randorgUrl   = state.verify_link    || state.randorg_url || null;
        winner.verifyLink   = state.verify_link    || null;
        winner.rangeStart   = state.winner_range_start || null;
        winner.rangeEnd     = state.winner_range_end   || null;
        winner.spinId       = state.spin_id        || null;
        winner.randSerial   = state.randorg_serial || null;
      }
      // Update last-draw proof link on page
      if (state && state.verify_link) {
        updateProofLink(state.verify_link, state.winner_ticket, state.total_tickets,
                        state.randorg_serial, state.winner_range_start, state.winner_range_end);
      }
      // Fallback: weighted random local pick if server winner not in our list
      if (!winner && PARTICIPANTS.length) {
        const r = Math.random() * totalTickets;
        let acc = 0;
        for (const p of PARTICIPANTS) { acc += p.tickets; if (r < acc) { winner = p; break; } }
        if (!winner) winner = PARTICIPANTS[PARTICIPANTS.length - 1];
      }
      if (winner) {
        doSpin(winner);
      } else {
        // No participants loaded — can't spin, release the lock so next cycle works
        autoSpun = false;
      }
      // autoSpun reset happens inside doSpin after animation completes
    }, 1500);
  }
}
updateTimer();
setInterval(updateTimer, 1000);

// ── Update on-page proof link ───────────────────────────────────────────────
function buildRandorgUrl(total) {
  return `https://www.random.org/integers/?num=1&min=1&max=${total}&col=1&base=10&format=plain&rnd=new`;
}

function updateProofLink(verifyLink, ticket, total, serial, rangeStart, rangeEnd) {
  const el = document.getElementById('pageProofLink');
  if (!el) return;
  const href = verifyLink || (total ? buildRandorgUrl(total) : null);
  if (!href) return;
  el.href = href;
  if (ticket && total) {
    const rangePart = (rangeStart && rangeEnd) ? ` (RANGE #${rangeStart}\u2013${rangeEnd})` : '';
    const serialPart = serial ? ` SERIAL #${serial}` : '';
    el.textContent = `[ LAST DRAW: TICKET #${ticket}/${total}${rangePart}${serialPart} \u2014 VERIFY ON RANDOM.ORG ]`;
  } else {
    el.textContent = '[ VERIFY LAST DRAW ON RANDOM.ORG ]';
  }
  el.style.display = '';
}

// Load participants AND sync timer + proof link from server in parallel
Promise.all([
  loadParticipants(),
  fetchWheelState().then(state => {
    syncTimerFromState(state);
    if (state && state.verify_link) {
      updateProofLink(state.verify_link, state.winner_ticket, state.total_tickets,
                      state.randorg_serial, state.winner_range_start, state.winner_range_end);
    }
  })
]);

// ── Background pixel particles (same as index) ────────────────────────────────
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
    p.style.cssText = `position:absolute;width:${size}px;height:${size}px;left:${Math.random()*100}%;top:${Math.random()*100}%;background:${color};box-shadow:0 0 ${size*2}px ${color};opacity:0;animation:pixelBlink ${dur}s ${delay}s infinite steps(2);`;
    container.appendChild(p);
  }
  if (!document.getElementById('pixelBlink-style')) {
    const s = document.createElement('style');
    s.id = 'pixelBlink-style';
    s.textContent = '@keyframes pixelBlink{0%{opacity:0}50%{opacity:0.9}100%{opacity:0}}';
    document.head.appendChild(s);
  }
})();

// ── Pixel rocket cursor ───────────────────────────────────────────────────────
(function initRocket() {
  const SZ = 4;
  const pixels = [
    [3,0,'#FF2222'],
    [2,1,'#FF4444'],[3,1,'#FF2222'],[4,1,'#FF4444'],
    [1,2,'#FF5555'],[2,2,'#FF2222'],[3,2,'#FF2222'],[4,2,'#FF2222'],[5,2,'#FF5555'],
    [1,3,'#FF4444'],[2,3,'#FF2222'],[3,3,'#FFFFFF'],[4,3,'#FF2222'],[5,3,'#FF4444'],
    [2,4,'#FF4444'],[3,4,'#FF2222'],[4,4,'#FF4444'],
    [0,3,'#CC1111'],[6,3,'#CC1111'],
    [0,4,'#CC1111'],[6,4,'#CC1111'],
    [2,5,'#FFA500'],[3,5,'#FFDD00'],[4,5,'#FFA500'],
    [3,6,'#FF6600'],
  ];
  const W = 7, H = 7;
  const rCanvas = document.createElement('canvas');
  rCanvas.width  = W * SZ;
  rCanvas.height = H * SZ;
  rCanvas.style.cssText = 'position:fixed;pointer-events:none;z-index:99999;display:none;image-rendering:pixelated;';
  document.body.appendChild(rCanvas);
  const rctx = rCanvas.getContext('2d');
  pixels.forEach(([c, r, color]) => { rctx.fillStyle = color; rctx.fillRect(c*SZ, r*SZ, SZ, SZ); });

  const trail = [];
  const TRAIL_LEN = 10;
  let mx = -200, my = -200, rx = -200, ry = -200;
  let angle = 0, targetAngle = 0;

  document.addEventListener('mousemove', e => {
    const dx = e.clientX - rx, dy = e.clientY - ry;
    if (Math.abs(dx) > 1 || Math.abs(dy) > 1)
      targetAngle = Math.atan2(dy, dx) * (180 / Math.PI) + 90;
    mx = e.clientX; my = e.clientY;
    rCanvas.style.display = 'block';
  });
  document.addEventListener('mouseleave', () => { rCanvas.style.display = 'none'; });

  const trailContainer = document.createElement('div');
  trailContainer.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:99998;';
  document.body.appendChild(trailContainer);

  function lerp(a, b, t) { return a + (b - a) * t; }
  function lerpAngle(a, b, t) { let d = ((b - a + 540) % 360) - 180; return a + d * t; }

  function spawnTrail(x, y) {
    const p = document.createElement('div');
    const c = ['#FF2222','#FF6600','#FFA500','#FFDD00'][Math.floor(Math.random()*4)];
    const sz = SZ * (Math.random() > 0.5 ? 2 : 1);
    p.style.cssText = `position:fixed;width:${sz}px;height:${sz}px;background:${c};left:${x-sz/2}px;top:${y-sz/2}px;pointer-events:none;image-rendering:pixelated;transition:opacity 0.35s linear,transform 0.35s linear;`;
    trailContainer.appendChild(p);
    trail.push(p);
    requestAnimationFrame(() => { p.style.opacity='0'; p.style.transform=`translate(${(Math.random()-.5)*12}px,${(Math.random()-.5)*12}px)`; });
    setTimeout(() => { if (p.parentNode) p.parentNode.removeChild(p); }, 400);
    if (trail.length > TRAIL_LEN*3) { const old = trail.shift(); if (old && old.parentNode) old.parentNode.removeChild(old); }
  }

  let lastTrail = 0;
  function animate(ts) {
    rx = lerp(rx, mx, 0.18);
    ry = lerp(ry, my, 0.18);
    angle = lerpAngle(angle, targetAngle, 0.12);
    const hw = rCanvas.width/2, hh = rCanvas.height/2;
    rCanvas.style.left      = (rx - hw) + 'px';
    rCanvas.style.top       = (ry - hh) + 'px';
    rCanvas.style.transform = `rotate(${angle}deg)`;
    if (ts - lastTrail > 40) {
      const rad = (angle - 90) * Math.PI / 180;
      spawnTrail(rx + Math.cos(rad + Math.PI)*hh*0.9,
                 ry + Math.sin(rad + Math.PI)*hh*0.9);
      lastTrail = ts;
    }
    requestAnimationFrame(animate);
  }
  requestAnimationFrame(animate);
})();
