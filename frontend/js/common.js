const API = "http://localhost:8080";

const I = {
  home:'<path d="M3 11l9-8 9 8M5 10v10h14V10"/>', cal:'<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M8 3v4M16 3v4M4 10h16"/>',
  edit:'<path d="M12 4H6a2 2 0 00-2 2v12a2 2 0 002 2h12a2 2 0 002-2v-6M18 3l3 3-9 9H9v-3z"/>',
  gear:'<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>',
  users:'<circle cx="9" cy="8" r="3"/><path d="M3 20c0-4 3-6 6-6s6 2 6 6M16 5a3 3 0 010 6M18 14c2 1 3 3 3 6"/>',
  mic:'<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0014 0M12 18v3"/>',
  up:'<path d="M12 16V4M7 9l5-5 5 5M4 20h16"/>', arr:'<path d="M5 12h14M13 6l6 6-6 6"/>', back:'<path d="M19 12H5M11 6l-6 6 6 6"/>',
  plus:'<path d="M12 5v14M5 12h14"/>', search:'<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
  clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>', bolt:'<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
  chk:'<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M8 3v4M16 3v4M9 14l2 2 4-4"/>'
};
const ic = (n, s) => `<svg viewBox="0 0 24 24"${s ? ` style="width:${s}px;height:${s}px"` : ''}>${I[n]}</svg>`;

const NAV = [
  ['index.html', 'Tổng quan', 'home'], ['meetings.html', 'Cuộc họp', 'cal'], ['notes.html', 'Ghi chú', 'edit'],
  ['settings.html', 'Cài đặt', 'gear'], ['users.html', 'Người dùng', 'users']
];
const STATUS = {done: ['Đã phiên âm', ''], processing: ['Đang phiên âm', 'wait'], error: ['Lỗi', 'err']};
const STAGES = {queued: 'Đã tiếp nhận audio', converting: 'Đang chuẩn hóa audio', waiting_asr: 'Đang chờ phiên âm', transcribing: 'Đang phiên âm', summarizing: 'Đang tạo biên bản', done: 'Hoàn thành', summary_error: 'Lỗi tạo biên bản', error: 'Xử lý thất bại'};
function meetingStatus(m) {
  if (m.status === 'processing') return [STAGES[m.stage] || 'Đang xử lý', 'wait'];
  if (m.status === 'error') return ['Lỗi xử lý audio', 'err'];
  if (m.summary_status === 'processing') return ['Đang tạo biên bản', 'wait'];
  if (m.summary_status === 'error') return [m.summary ? 'Tạo lại lỗi · Có bản cũ' : 'Chưa có biên bản', 'err'];
  if (m.summary_outdated) return ['Transcript đã sửa · Cần tạo lại', 'wait'];
  return m.summary ? ['Hoàn thành', ''] : ['Đã phiên âm', ''];
}

const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
const fmtDur = s => !s ? '—' : s < 60 ? `${s}s` : `${Math.round(s / 60)} min`;
const fmtDate = iso => new Date(iso).toLocaleString('vi-VN', {dateStyle: 'medium', timeStyle: 'short'});

let meetings = [], backendDown = false;
async function loadMeetings() {
  try {
    const r = await fetch(API + '/api/meetings');
    meetings = await r.json();
    backendDown = false;
  } catch (e) { meetings = []; backendDown = true; }
}
const warn = () => backendDown
  ? '<div class="card" style="margin-bottom:24px;color:#b7791f"><b>Chưa kết nối được backend.</b> Hãy chạy: uvicorn backend.app:app --port 8000</div>' : '';

function layout(active, title) {
  document.getElementById('app').innerHTML = `
  <aside>
    <div class="brand"><div class="logo">${ic('mic', 22)}</div><div><b>TinaMeetNote</b><span class="eyebrow">Trợ lý cuộc họp bảo mật</span></div></div>
    <nav>${NAV.map(([href, label, icon]) => `<a href="${href}" class="${href === active ? 'on' : ''}">${ic(icon)}<span>${label}</span></a>`).join('')}</nav>
    <div class="me"><div class="av">SA</div><div><b>System Admin</b><small>Quản trị viên</small></div></div>
  </aside>
  <main>
    <header><div><span class="eyebrow">Không gian làm việc</span><h1>${title}</h1></div>
    <a class="btn pri" href="new-meeting.html">${ic('plus')}Cuộc họp mới</a></header>
    <div class="wrap" id="view"></div>
  </main>`;
}

function meetingTable(list) {
  if (!list.length) return '<div class="empty">Chưa có cuộc họp nào. Bấm “Cuộc họp mới” để bắt đầu.</div>';
  const rows = list.map(m => {
    const [label, cls] = meetingStatus(m);
    return `<tr><td><b><a href="meeting.html?id=${m.id}">${esc(m.title)}</a></b></td><td>${fmtDate(m.created)}</td>
    <td><span class="who">${ic('users', 16)} ${m.people}</span></td><td>${fmtDur(m.sec)}</td>
    <td><span class="badge ${cls}">${label}</span></td><td>${ic('arr', 18)}</td></tr>`;
  }).join('');
  return `<table><thead><tr><th>Cuộc họp</th><th>Ngày</th><th>Người tham gia</th><th>Thời lượng</th><th>Trạng thái</th><th></th></tr></thead><tbody>${rows}</tbody></table>`;
}

// ---------- Người nói ----------
const SPK_COLORS = ['#2563eb', '#dc2626', '#16a34a', '#9333ea', '#ea580c'];
const fmtTime = s => {
  s = Math.max(0, Math.round(s || 0));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
};

// Hiển thị transcript theo từng người nói, mỗi người một màu (đã esc nội dung)
function speakerHtml(text) {
  const index = {};
  return String(text || '').split('\n').filter(l => l.trim()).map(line => {
    const m = line.match(/^\[([^\]]+)\]\s*(.*)$/);
    if (!m) return `<p class="spk-line">${esc(line)}</p>`;
    if (!(m[1] in index)) index[m[1]] = Object.keys(index).length;
    const color = SPK_COLORS[index[m[1]] % SPK_COLORS.length];
    return `<p class="spk-line"><strong style="color:${color}">${esc(m[1])}:</strong> ${esc(m[2])}</p>`;
  }).join('');
}

// Gộp các đoạn liên tiếp của cùng một người thành một lượt lời
function speakerTurns(m) {
  const edited = m.transcript_edited;
  const segs = !edited && Array.isArray(m.segments) ? m.segments : null;
  const turns = [];
  if (segs && segs.length && segs.every(s => s.speaker)) {
    segs.forEach(s => {
      const last = turns[turns.length - 1];
      if (last && last.speaker === s.speaker) { last.text += ' ' + s.text; last.end = s.end; }
      else turns.push({speaker: s.speaker, start: s.start, end: s.end, text: s.text});
    });
    return turns;
  }
  // Không có segments (hoặc transcript đã chỉnh sửa): đọc nhãn [Người N] trong văn bản
  String(edited || m.transcript || '').split('\n').forEach(line => {
    const x = line.match(/^\[([^\]]+)\]\s*(.*)$/);
    if (x) turns.push({speaker: x[1], text: x[2]});
  });
  return turns;
}

function speakerPanelHtml(m) {
  const turns = speakerTurns(m);
  if (!turns.length) {
    return m.diarization === 'error'
      ? '<p class="meeting-notice error">Chưa nhận diện được người nói. Transcript vẫn được giữ nguyên.</p>' : '';
  }
  const names = [], stats = {};
  turns.forEach(t => {
    if (!stats[t.speaker]) { stats[t.speaker] = {turns: 0, sec: 0}; names.push(t.speaker); }
    stats[t.speaker].turns++;
    if (t.end != null) stats[t.speaker].sec += t.end - t.start;
  });
  const real = names.filter(n => n !== 'Chưa rõ');
  const color = n => SPK_COLORS[names.indexOf(n) % SPK_COLORS.length];
  const chips = names.map(n => `<span class="spk-chip" style="border-color:${color(n)};color:${color(n)}">
    <b>${esc(n)}</b> · ${stats[n].turns} lượt${stats[n].sec ? ' · ' + fmtTime(stats[n].sec) : ''}</span>`).join('');
  const rows = turns.map(t => `<div class="spk-turn">
    <span class="spk-time">${t.start != null ? fmtTime(t.start) : ''}</span>
    <div><strong style="color:${color(t.speaker)}">${esc(t.speaker)}</strong><p>${esc(t.text)}</p></div></div>`).join('');
  return `<div id="speaker-panel" class="spk-panel">
    <p class="spk-count">Phát hiện <b>${real.length}</b> người nói · ${turns.length} lượt lời</p>
    <div class="spk-chips">${chips}</div>
    <div class="spk-turns">${rows}</div></div>`;
}