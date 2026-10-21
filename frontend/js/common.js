const API = "http://localhost:8000";

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
const meetingStatus = m => m.status === 'done' ? (m.summary_status === 'processing' ? ['Đang tạo biên bản','wait'] : m.summary_status === 'error' || (!m.summary && m.minutes && m.minutes.startsWith('Chưa có')) ? ['Chưa có biên bản','err'] : m.summary ? ['Hoàn thành',''] : ['Đã phiên âm','']) : (STATUS[m.status] || STATUS.error);

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