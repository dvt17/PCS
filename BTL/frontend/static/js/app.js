/* ═══════════════════════════════════════════════════════════════════
   PCS Smart Parking — Common JavaScript Utilities
   ═══════════════════════════════════════════════════════════════════ */

const ZONE_CONFIG = {
  A: {label:'Zone A', description:'🚗 Ô tô', color:'var(--zone-a-head)', bgClass:'zone-group-a', badgeClass:'zone-badge-a', cols:5},
  B: {label:'Zone B', description:'🏍️ Xe máy', color:'var(--zone-b-head)', bgClass:'zone-group-b', badgeClass:'zone-badge-b', cols:4}
};

const ICON_MAP = {
  vehicle_entered: {icon:'fa-right-to-bracket', color:'#2ECC71'},
  vehicle_exited:  {icon:'fa-right-from-bracket', color:'#E74C3C'},
  ocr_failed:     {icon:'fa-triangle-exclamation', color:'#F39C12'},
  lot_full:       {icon:'fa-ban', color:'#E74C3C'}
};

const METHOD_COLORS = {
  cash: '#27AE60', momo: '#E74C3C', vnpay: '#4F8EF7', zalopay: '#9B59B6'
};

const ZONE_COLORS = {A: '#27AE60', B: '#4F8EF7'};
const ZONE_NAMES = {A: 'Zone A · 🚗 Ô tô', B: 'Zone B · 🏍️ Xe máy'};

/* ─── API HELPER ──────────────────────────────────────────────── */
async function api(url, method = 'GET', body = null) {
  const opts = {method, headers: {'Content-Type': 'application/json'}};
  if (body) opts.body = JSON.stringify(body);
  const resp = await fetch(url, opts);
  return resp.json();
}

/* ─── DOM HELPERS ─────────────────────────────────────────────── */
function setEl(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function fmtMoney(n) {
  return Number(n || 0).toLocaleString('vi-VN') + 'đ';
}

/* ─── CLOCK ────────────────────────────────────────────────────── */
function initClock() {
  function update() {
    const n = new Date();
    const el = document.getElementById('clock');
    if (el) el.textContent = n.toLocaleDateString('vi-VN') + '  ' + n.toLocaleTimeString('vi-VN');
  }
  update();
  setInterval(update, 1000);
}

/* ─── TAB SWITCHING ────────────────────────────────────────────── */
function switchTab(name, btn, tabs) {
  const tabList = tabs || ['dashboard', 'lot', 'camera', 'report', 'admin', 'checkin', 'checkout', 'history', 'payment'];
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  tabList.forEach(t => {
    const el = document.getElementById('tab-' + t);
    if (el) el.style.display = 'none';
  });
  if (btn) btn.classList.add('active');
  const panel = document.getElementById('tab-' + name);
  if (panel) panel.style.display = 'flex';
  if (name === 'report') loadReport('today');
}

/* ─── SLOT RENDERING ───────────────────────────────────────────── */
function renderSlotsByZone(containerId, slots, compact) {
  const el = document.getElementById(containerId);
  if (!el) return;

  const groups = {A: [], B: []};
  slots.forEach(s => { if (groups[s.zone]) groups[s.zone].push(s); });

  el.innerHTML = Object.keys(groups).map(zone => {
    const config = ZONE_CONFIG[zone];
    const zoneSlots = groups[zone];
    if (!zoneSlots.length) return '';

    const total = zoneSlots.length;
    const occ = zoneSlots.filter(s => s.state === 'occupied' || s.state === 'entering' || s.state === 'exiting').length;
    const pct = total ? Math.round(occ / total * 100) : 0;

    const slotsHtml = zoneSlots.map(s => {
      const plateHtml = s.plate ? `<div class="slot-plate">${s.plate.length > 6 ? s.plate.slice(-6) : s.plate}</div>` : '';
      return `<div class="slot ${s.state}" title="[${s.id}] ${s.state.toUpperCase()}${s.plate ? ' · ' + s.plate : ''}" onclick="showToast('${s.id} — ${s.state.toUpperCase()}${s.plate ? ' · ' + s.plate : ''}','info')">
        <div class="slot-id">${s.id}</div>${plateHtml}</div>`;
    }).join('');

    const cols = compact ? Math.min(config.cols, 4) : config.cols;

    return `<div class="zone-group ${config.bgClass}">
      <div class="zone-header">
        <div class="zone-title">
          <span class="zone-badge ${config.badgeClass}">${zone}</span>
          <div><div class="zone-name">${config.label}</div><div class="zone-desc">${config.description}</div></div>
        </div>
        <div class="zone-stats"><strong>${occ}</strong>/${total} · <strong>${pct}%</strong></div>
      </div>
      <div class="zone-grid" style="grid-template-columns:repeat(${cols},1fr)">${slotsHtml}</div>
    </div>`;
  }).join('');
}

/* ─── ZONE OCCUPANCY BARS ──────────────────────────────────────── */
function renderZoneOcc(zones, containerId) {
  const el = document.getElementById(containerId || 'zone-occ');
  if (!el) return;

  el.innerHTML = Object.entries(zones).map(([z, info]) => {
    const pct = info.total ? Math.round(info.occupied / info.total * 100) : 0;
    const color = pct > 80 ? '#E74C3C' : pct > 50 ? '#F39C12' : (ZONE_COLORS[z] || '#4F8EF7');
    return `<div class="zone-row">
      <div class="zone-header-occ"><span>${ZONE_NAMES[z] || 'Zone ' + z}</span><span>${info.occupied}/${info.total}</span></div>
      <div class="zone-track"><div class="zone-fill" style="width:${pct}%;background:${color}"></div></div>
    </div>`;
  }).join('');
}

/* ─── FEED ──────────────────────────────────────────────────────── */
function renderFeed(items, containerId) {
  const el = document.getElementById(containerId || 'feed');
  if (!el || !items.length) return;

  el.innerHTML = items.slice(0, 15).map(f => {
    const ic = ICON_MAP[f.event] || {icon: 'fa-circle-info', color: '#4F8EF7'};
    const p = f.payload || {};
    let detail = '';
    if (f.event === 'vehicle_entered') detail = `→ ${p.slot_id} · Zone ${p.zone} · ${p.vehicle_label || ''}`;
    else if (f.event === 'vehicle_exited') detail = `← ${p.slot_id} · ${fmtMoney(p.fee)} · ${p.method}`;
    else detail = p.message || '';
    return `<div class="feed-item">
      <i class="fa ${ic.icon} feed-icon" style="color:${ic.color}"></i>
      <div class="feed-body">
        <div class="feed-plate">${p.plate || 'Hệ thống'}</div>
        <div class="feed-detail">${detail}</div>
      </div>
      <span class="feed-time">${f.time}</span>
    </div>`;
  }).join('');
}

/* ─── TOAST ─────────────────────────────────────────────────────── */
let toastTimer = null;

function showToast(msg, type = 'info') {
  let el = document.getElementById('toast');
  if (!el) {
    el = document.createElement('div');
    el.id = 'toast';
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.className = 'toast toast-' + type;
  el.style.display = 'block';
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.style.display = 'none'; }, 3500);
}

/* ─── MODALS ────────────────────────────────────────────────────── */
function openModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.add('open');
}

function closeModal(id) {
  const el = document.getElementById(id);
  if (el) el.classList.remove('open');
}

// Close modals on backdrop click
document.addEventListener('click', function (e) {
  if (e.target.classList.contains('modal-overlay')) {
    e.target.classList.remove('open');
  }
});

/* ─── ENTRY / EXIT ──────────────────────────────────────────────── */
async function simEntry() {
  const r = await api('/api/simulate_entry', 'POST');
  showToast(r.message, r.success ? 'success' : 'error');
  if (typeof refreshStatus === 'function') refreshStatus();
}

async function simExit() {
  const r = await api('/api/simulate_exit', 'POST');
  showToast(r.message, r.success ? 'success' : 'error');
  if (typeof refreshStatus === 'function') refreshStatus();
}

/* ─── AUTO MODE ─────────────────────────────────────────────────── */
let autoRunning = false;
let autoTimer = null;
let simSpeed = 3;

function toggleAuto() {
  autoRunning = !autoRunning;
  const btn = document.getElementById('auto-btn');
  if (autoRunning) {
    btn.innerHTML = '<i class="fa fa-pause"></i> Pause';
    btn.classList.add('btn-warn');
    scheduleAuto();
  } else {
    btn.innerHTML = '<i class="fa fa-play"></i> Auto';
    btn.classList.remove('btn-warn');
    if (autoTimer) clearTimeout(autoTimer);
  }
}

function scheduleAuto() {
  if (!autoRunning) return;
  const delay = Math.round(3000 / simSpeed * (0.6 + Math.random() * 0.8));
  autoTimer = setTimeout(async () => {
    if (Math.random() < 0.5) await simEntry();
    else await simExit();
    scheduleAuto();
  }, delay);
}

function setSpeed(val) {
  simSpeed = Number(val);
  const el = document.getElementById('speed-val');
  if (el) el.textContent = val + '×';
}

/* ─── ENTRY / EXIT MODAL HELPERS ──────────────────────────────── */
async function doEntry() {
  const plate = document.getElementById('e-plate')?.value?.trim()?.toUpperCase();
  const vtype = document.getElementById('e-type')?.value;
  if (!plate) { showToast('Nhập biển số', 'warn'); return; }
  const r = await api('/api/entry', 'POST', {plate, vehicle_type: vtype || 'car'});
  showToast(r.message, r.success ? 'success' : 'error');
  if (r.success) { closeModal('entry-modal'); if (typeof refreshStatus === 'function') refreshStatus(); }
}

async function doExit() {
  const plate = document.getElementById('x-plate')?.value?.trim()?.toUpperCase();
  const method = document.getElementById('x-method')?.value;
  if (!plate) { showToast('Nhập biển số', 'warn'); return; }
  const r = await api('/api/exit', 'POST', {plate, method});
  showToast(r.message, r.success ? 'success' : 'error');
  if (r.success && r.receipt) {
    const rt = document.getElementById('receipt-text');
    const rb = document.getElementById('receipt-box');
    if (rt) rt.textContent = r.receipt;
    if (rb) rb.style.display = 'block';
    if (typeof refreshStatus === 'function') refreshStatus();
  }
}

/* ─── ADMIN ACTIONS ──────────────────────────────────────────────── */
async function saveRates() {
  const rates = [
    {zone: 'A', id: 'rate-a'},
    {zone: 'B', id: 'rate-b'}
  ];
  for (const {zone, id} of rates) {
    const val = parseInt(document.getElementById(id)?.value);
    if (!val || val <= 0) { showToast('Giá Zone ' + zone + ' không hợp lệ', 'error'); return; }
    await api('/api/admin/set_rate', 'POST', {zone, rate: val});
  }
  showToast('Đã lưu giá!', 'success');
}

async function slotAction(action) {
  const slotId = document.getElementById('slot-id-input')?.value?.trim()?.toUpperCase();
  if (!slotId) { showToast('Nhập ID ô đỗ', 'warn'); return; }
  const r = await api('/api/admin/slot_action', 'POST', {action, slot_id: slotId});
  showToast(r.message || (r.success ? 'Thành công' : 'Thất bại'), r.success ? 'success' : 'error');
  if (r.success && typeof refreshStatus === 'function') refreshStatus();
}

/* ─── AUTO SLOT SUGGESTION ──────────────────────────────────────── */
let pendingSlotInfo = null;

async function suggestSlotAfterOCR(plate, vehicleType) {
  if (!plate) return;
  const result = await api('/api/suggest_slot', 'POST', {plate, vehicle_type: vehicleType});

  const card = document.getElementById('auto-slot-card');
  const icon = document.getElementById('auto-slot-icon');
  const title = document.getElementById('auto-slot-title');
  const detail = document.getElementById('auto-slot-detail');
  const confirmBtn = document.getElementById('auto-confirm-btn');

  if (!card) return;

  if (result.success && result.has_slot && result.suggested_slot) {
    pendingSlotInfo = {plate, vehicle_type: vehicleType, slot_info: result.suggested_slot};
    icon.textContent = vehicleType === 'motorbike' ? '🏍' : '🚗';
    title.textContent = '✅ Đã tìm thấy chỗ đỗ trống!';
    detail.textContent = `🔹 ${result.vehicle_label} ${plate} → ${result.suggested_slot.zone_label} · ${result.suggested_slot.slot_id}  |  Giá: ${fmtMoney(result.suggested_slot.hourly_rate)}/giờ`;
    card.className = 'auto-slot-card show';
    confirmBtn.disabled = false;
    confirmBtn.innerHTML = '<i class="fa fa-check"></i> Xác nhận xe vào';
  } else if (!result.success && result.has_slot && result.suggested_slot) {
    icon.textContent = '⚠️';
    title.textContent = 'Xe đã đỗ trong bãi';
    detail.textContent = result.message;
    card.className = 'auto-slot-card show error';
    confirmBtn.disabled = true;
    confirmBtn.innerHTML = 'Đã đỗ';
  } else {
    icon.textContent = '❌';
    title.textContent = 'Bãi đỗ đầy!';
    detail.textContent = result.message || 'Không còn chỗ trống cho loại xe này';
    card.className = 'auto-slot-card show error';
    confirmBtn.disabled = true;
    confirmBtn.innerHTML = 'Hết chỗ';
  }
}

function hideAutoSlot() {
  const card = document.getElementById('auto-slot-card');
  if (card) card.className = 'auto-slot-card';
  pendingSlotInfo = null;
}

async function confirmAutoEntry() {
  if (!pendingSlotInfo) { showToast('Không có thông tin xe để xác nhận', 'warn'); return; }
  const {plate, vehicle_type} = pendingSlotInfo;
  const r = await api('/api/auto_entry', 'POST', {plate, vehicle_type: vehicle_type});
  showToast(r.message, r.success ? 'success' : 'error');
  if (r.success) { hideAutoSlot(); if (typeof refreshStatus === 'function') refreshStatus(); }
}

/* ─── CAMERA ────────────────────────────────────────────────────── */
const cameraStreams = {};

async function toggleCamera(videoId, statusId, streamKey) {
  const video = document.getElementById(videoId);
  const statusEl = document.getElementById(statusId);
  const key = streamKey || videoId;

  // Turn off preview overlays
  document.querySelectorAll(`#${videoId}_preview, #${videoId}_preview2`).forEach(el => el.style.display = 'none');

  if (cameraStreams[key]) {
    cameraStreams[key].getTracks().forEach(t => t.stop());
    delete cameraStreams[key];
    video.srcObject = null;
    if (statusEl) { statusEl.textContent = 'Đã tắt'; statusEl.style.color = 'var(--muted)'; }
    showToast('Camera đã tắt', 'info');
    return;
  }

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    showToast('Trình duyệt không hỗ trợ camera', 'error');
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: {facingMode: 'environment'},
      audio: false
    });
    cameraStreams[key] = stream;
    video.srcObject = stream;
    await video.play();
    if (statusEl) { statusEl.textContent = '📷 Đang phát'; statusEl.style.color = 'var(--success)'; }
    showToast('Camera đã bật', 'success');
  } catch (err) {
    showToast('⚠ Lỗi camera: ' + err.name + '. Dùng tải ảnh lên thay thế.', 'warn');
    if (statusEl) { statusEl.textContent = '⚠ Lỗi'; statusEl.style.color = 'var(--danger)'; }
  }
}

async function captureFrame(videoId, canvasId, endpoint) {
  const video = document.getElementById(videoId);
  const key = Object.keys(cameraStreams).find(k => k.includes(videoId.replace('video-', '')));
  // if (!cameraStreams[key] || !video.videoWidth) {
  //   showToast('Bật camera trước', 'warn');
  //   return null;
  // }
  const canvas = document.getElementById(canvasId);
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  canvas.getContext('2d').drawImage(video, 0, 0);

  const r = await fetch(endpoint || '/api/process_frame', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({image: canvas.toDataURL('image/jpeg', 0.9)})
  });
  return r.json();
}

function showAnnotatedPreview(data, previewId) {
  const img = document.getElementById(previewId);
  if (!img) return;
  if (data.annotated_b64) {
    img.src = 'data:image/jpeg;base64,' + data.annotated_b64;
    img.style.display = 'block';
  } else if (data.image_b64) {
    img.src = 'data:image/jpeg;base64,' + data.image_b64;
    img.style.display = 'block';
  }
}

function updateOCRResult(data, prefix) {
  setEl(prefix + '-plate', data.plate || '—');
  setEl(prefix + '-conf', data.confidence != null ? String(data.confidence) : '—');
  setEl(prefix + '-type', data.vehicle_type || 'unknown');
  const statusEl = document.getElementById(prefix + '-status');
  if (statusEl) {
    if (data.valid) {
      statusEl.textContent = '✓ Hợp lệ';
      statusEl.style.color = 'var(--success)';
    } else {
      statusEl.textContent = '⚠ Cần nhập tay';
      statusEl.style.color = 'var(--warn)';
    }
  }
}

/* ─── OCR + UPLOAD ──────────────────────────────────────────────── */
async function uploadAndProcessImage(inputId, prefix) {
  const input = document.getElementById(inputId);
  if (!input?.files?.[0]) return;

  const fd = new FormData();
  fd.append('image', input.files[0]);
  const data = await (await fetch('/api/process_image', {method: 'POST', body: fd})).json();

  updateOCRResult(data, prefix);
  showAnnotatedPreview(data, prefix + '-cam-preview');
  showToast(data.message || 'Đã xử lý ảnh', data.valid ? 'success' : 'warn');
  return data;
}

/* ─── HISTORY ────────────────────────────────────────────────────── */
async function loadRecognitionHistory(plate, containerId) {
  const el = document.getElementById(containerId || 'history-panel');
  if (!el) return;
  const items = plate ? await api('/api/image_history/' + encodeURIComponent(plate)) : await api('/api/recent_history');
  el.innerHTML = items.length
    ? items.slice(0, 15).map(i => {
        const vb = i.valid ? '<span class="badge valid">Hợp lệ</span>' : '<span class="badge warn">Cần nhập tay</span>';
        return `<tr><td>${i.created_at || '—'}</td><td style="font-weight:700">${i.plate || '—'}</td><td>${i.vehicle_type || '—'}</td><td>${Number(i.confidence || 0).toFixed(2)}</td><td>${vb}</td></tr>`;
      }).join('')
    : '<tr><td colspan="5" style="color:var(--muted);text-align:center;padding:14px">Chưa có lịch sử</td></tr>';
}

/* ─── REFRESH STATUS ────────────────────────────────────────────── */
async function refreshStatus() {
  try {
    const [s, sl] = await Promise.all([api('/api/status'), api('/api/slots')]);

    setEl('m-total', s.total);
    setEl('m-occ', s.occupied);
    setEl('m-occ-pct', s.occupancy_pct + '% lấp đầy');
    setEl('m-avail', s.available);

    // Revenue (if element exists - admin/staff pages)
    if (document.getElementById('m-rev')) {
      setEl('m-rev', fmtMoney(s.revenue_today));
      setEl('m-txn', s.txn_count + ' giao dịch');
    }

    if (s.zones) renderZoneOcc(s.zones);

    renderSlotsByZone('lot-mini-zones', sl, true);
    renderSlotsByZone('lot-full-zones', sl, false);

    const f = await api('/api/feed');
    renderFeed(f);

    const t = await api('/api/last_transaction');
    if (t && t.plate) {
      setEl('t-plate', t.plate);
      setEl('t-slot', t.slot_id);
      setEl('t-time', (t.entry || '—') + ' → ' + (t.exit || '—'));
      setEl('t-dur', t.hours + ' giờ');
      setEl('t-method', t.method);
      setEl('t-fee', t.fee + 'đ');
    }
  } catch (e) {
    console.error('refreshStatus error:', e);
  }
}

/* ─── REPORT ────────────────────────────────────────────────────── */
let occChart = null;

async function loadReport(period) {
  try {
    const [rep, ts] = await Promise.all([
      api('/api/report/' + period),
      api('/api/top_slots')
    ]);

    setEl('r-txn', rep.txn_count || 0);
    setEl('r-rev', fmtMoney(rep.total_revenue || 0));
    setEl('r-avg', fmtMoney(rep.avg_fee || 0));

    // Zone bars
    const zb = document.getElementById('zone-bars');
    const byZ = rep.by_zone || {};
    const mz = Math.max(...Object.values(byZ), 1);
    if (zb) {
      zb.innerHTML = Object.entries(byZ).length
        ? Object.entries(byZ).map(([z, v]) =>
            `<div class="bar-row"><span class="bar-label">${z}</span><div class="bar-track"><div class="bar-fill" style="width:${v / mz * 100}%;background:${ZONE_COLORS[z] || '#4F8EF7'}">${fmtMoney(v)}</div></div></div>`
          ).join('')
        : '<div style="color:var(--muted)">Chưa có dữ liệu</div>';
    }

    // Method bars
    const mb = document.getElementById('method-bars');
    const byM = rep.by_method || {};
    const mm = Math.max(...Object.values(byM), 1);
    if (mb) {
      mb.innerHTML = Object.entries(byM).length
        ? Object.entries(byM).map(([m, v]) =>
            `<div class="bar-row"><span class="bar-label" style="width:52px;font-size:10px">${m.toUpperCase()}</span><div class="bar-track"><div class="bar-fill" style="width:${v / mm * 100}%;background:${METHOD_COLORS[m] || '#8B8FA8'}">${fmtMoney(v)}</div></div></div>`
          ).join('')
        : '<div style="color:var(--muted)">Chưa có dữ liệu</div>';
    }

    // Top slots
    const te = document.getElementById('top-slots');
    if (te) {
      te.innerHTML = ts.length
        ? ts.map((s, i) =>
            `<div class="bar-row" style="font-size:12px"><span style="width:24px;color:var(--muted)">${i + 1}.</span><span style="width:48px;font-weight:600">${s.slot_id}</span><span style="flex:1;color:var(--muted)">${s.uses} lượt</span><span style="color:var(--success)">${fmtMoney(s.revenue || 0)}</span></div>`
          ).join('')
        : '<div style="color:var(--muted)">Chưa có dữ liệu</div>';
    }

    // Occupancy chart
    const trend = rep.occupancy_trend || [];
    const labels = trend.map(d => d.date.slice(5));
    const values = trend.map(d => d.occupancy_pct);

    if (occChart) occChart.destroy();
    const ctx = document.getElementById('occ-chart');
    if (ctx) {
      occChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels,
          datasets: [{
            label: 'Lấp đầy %',
            data: values,
            borderColor: '#4F8EF7',
            backgroundColor: 'rgba(79,142,247,0.12)',
            tension: 0.4,
            fill: true,
            pointRadius: 3
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {legend: {display: false}},
          scales: {
            x: {ticks: {color: '#8B8FA8', font: {size: 10}}},
            y: {min: 0, max: 100, ticks: {color: '#8B8FA8', font: {size: 10}, callback: v => v + '%'}}
          }
        }
      });
    }
  } catch (e) {
    console.error('loadReport error:', e);
  }
}

/* ─── INIT ───────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', function () {
  initClock();

  // Close modals on backdrop
  document.querySelectorAll('.modal-overlay').forEach(el => {
    el.addEventListener('click', function (e) {
      if (e.target === this) this.classList.remove('open');
    });
  });

  console.log('PCS Smart Parking — JS loaded');
});
