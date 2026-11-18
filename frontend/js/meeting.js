layout('meetings.html', 'Chi tiết cuộc họp');

function minutesHtml(m) {
  const d = m.summary;
  if (!d || typeof d !== 'object') return `<pre class="txt">${esc(m.minutes || 'Chưa có biên bản')}</pre>`;
  const meta = d.metadata || {};
  const arr = value => Array.isArray(value) ? value : [];
  const list = values => arr(values).length
    ? `<ul class="minutes-list">${arr(values).map(x => `<li>${esc(x)}</li>`).join('')}</ul>`
    : '<p class="muted">Chưa có thông tin được xác nhận.</p>';
  const topics = arr(d.noi_dung_thao_luan).map((t, i) => `
    <section class="minutes-topic"><h4>${i + 1}. ${esc(t.chu_de)}</h4>${list(t.chi_tiet)}</section>`).join('');
  const tasks = arr(d.action_items);
  return `<article class="minutes-sheet">
    <div class="minutes-title"><span>BIÊN BẢN CUỘC HỌP</span><h2>${esc(meta.tieu_de || m.title)}</h2><p>Bản tổng hợp tự động · Cần đối chiếu với nội dung ghi âm</p></div>
    <div class="minutes-info">
      <div><b>Ngày thực hiện</b><span>${esc(meta.ngay_thuc_hien || 'Chưa rõ')}</span></div>
      <div><b>Thời lượng</b><span>${esc(m.sec ? fmtDur(m.sec) : (meta.thoi_luong || 'Chưa rõ'))}</span></div>
      <div class="full"><b>Người tham dự</b><span>${arr(meta.thanh_phan_tham_du).length ? arr(meta.thanh_phan_tham_du).map(esc).join(' · ') : 'Chưa rõ'}</span></div>
    </div>
    <section class="minutes-section"><h3>01 / Tổng quan</h3><p>${esc(d.tong_quan || 'Chưa rõ')}</p></section>
    <section class="minutes-section"><h3>02 / Nội dung thảo luận</h3>${topics || '<p class="muted">Chưa có dữ liệu.</p>'}</section>
    <section class="minutes-section"><h3>03 / Quyết định đã thống nhất</h3>${list(d.quyet_dinh)}</section>
    <section class="minutes-section"><h3>04 / Công việc cần thực hiện</h3>
      ${tasks.length ? `<div class="minutes-table-wrap"><table class="minutes-table"><thead><tr><th>STT</th><th>Công việc</th><th>Phụ trách</th><th>Hạn hoàn thành</th><th>Ưu tiên</th></tr></thead><tbody>${tasks.map((it, i) => `<tr><td>${i + 1}</td><td>${esc(it.cong_viec)}</td><td>${esc(it.nguoi_phu_trach || 'Chưa rõ')}</td><td>${esc(it.deadline || 'Chưa rõ')}</td><td>${esc(it.uu_tien || '—')}</td></tr>`).join('')}</tbody></table></div>` : '<p class="muted">Chưa có đầu việc được xác nhận.</p>'}
    </section>
  </article>`;
}

const id = new URLSearchParams(location.search).get('id');
const meetingUrl = `${API}/api/meetings/${encodeURIComponent(id || '')}`;
let timer = null, editorOpen = false, saving = false, currentMeeting = null, notice = null;
const isBusy = m => m.status === 'processing' || m.summary_status === 'processing' || m.pipeline_status === 'processing';
const seconds = value => typeof value === 'number' && Number.isFinite(value)
  ? `${value.toLocaleString('vi-VN', {maximumFractionDigits: 2})} giây` : '—';

function progressHtml(m) {
  const stage = m.stage || (m.status === 'error' ? 'error' : m.status === 'processing' ? 'transcribing' : m.summary_status === 'processing' ? 'summarizing' : m.summary_status === 'error' ? 'summary_error' : 'done');
  const failed = stage === 'error' || stage === 'summary_error';
  const stepIndex = {queued: 0, converting: 0, waiting_asr: 1, transcribing: 1, summarizing: 2, summary_error: 2, done: 3};
  const active = stepIndex[stage === 'error' ? m.failed_stage : stage] ?? 0;
  const labels = ['Chuẩn hóa audio', 'Phiên âm', 'Tạo biên bản', 'Hoàn thành'];
  const times = m.timings || {};
  const runtime = m.asr_runtime;
  return `<section class="card processing-card" aria-live="polite"><h3>Tiến trình xử lý</h3>
    <p class="progress-caption">${esc(STAGES[stage] || 'Đã phiên âm')}${stage === 'summary_error' && m.summary ? ' · Biên bản cũ vẫn được giữ lại.' : ''}</p>
    ${runtime ? `<p class="muted">${esc(runtime.model)} · ${esc(runtime.backend)} · ${esc(runtime.device)} · ${esc(runtime.compute_type)}</p>` : ''}
    <ol class="processing-steps">${labels.map((label, i) => `<li class="${i < active || stage === 'done' ? 'complete' : i === active ? failed ? 'failed' : 'active' : ''}"><span>${i + 1}</span>${label}</li>`).join('')}</ol>
    <dl class="processing-times">
      <div><dt>Chuẩn hóa audio</dt><dd>${seconds(times.conversion_seconds)}</dd></div>
      <div><dt>Chờ phiên âm</dt><dd>${seconds(times.queue_seconds)}</dd></div>
      <div><dt>Phiên âm</dt><dd>${seconds(times.asr_seconds)}</dd></div>
      <div><dt>Nhận diện người nói</dt><dd>${seconds(times.diarization_seconds)}</dd></div>
      <div><dt>Tạo biên bản gần nhất</dt><dd>${m.summary_status === 'processing' ? 'Đang đo…' : seconds(times.summary_seconds)}</dd></div>
      <div><dt>Tổng lượt xử lý audio ban đầu</dt><dd>${seconds(times.initial_pipeline_seconds)}</dd></div>
    </dl>${!Object.keys(times).length ? '<p class="muted">Các số đo sẽ xuất hiện khi từng bước hoàn tất. Cuộc họp cũ có thể chưa có số đo.</p>' : ''}
    </section>`;
}

function transcriptHtml(m) {
  const edited = m.transcript_edited;
  const cleaned = !edited && m.transcript_clean;
  const hasSpeakers = speakerTurns(m).length > 0;
  return `<section class="card"><div class="transcript-head"><h3>Transcript</h3>
    <button id="edit-transcript" class="btn out" type="button" ${isBusy(m) ? 'disabled' : ''}>Chỉnh sửa transcript</button></div>
    <p class="transcript-note">Bản ASR gốc luôn được giữ lại. Sau khi lưu chỉnh sửa, lần tạo biên bản tiếp theo sẽ dùng bản đã chỉnh.</p>
    ${speakerPanelHtml(m)}
    <div id="transcript-tabs" class="tab-pair transcript-tabs">
      ${edited ? '<button type="button" class="tab-btn selected" data-transcript="edited">Bản đã chỉnh</button>' : ''}
      ${cleaned ? '<button type="button" class="tab-btn selected" data-transcript="clean">Bản AI chỉnh dấu câu</button>' : ''}
      <button type="button" class="tab-btn ${!edited && !cleaned ? 'selected' : ''}" data-transcript="raw">Bản gốc ASR</button>
    </div>
    <div id="transcript-content" class="readable-transcript" ${hasSpeakers && !edited && !cleaned ? 'hidden' : ''}>${speakerHtml(edited || cleaned || m.transcript || '')}</div>
    <div id="transcript-editor" hidden>
      <label for="transcript-input">Nội dung transcript chỉnh sửa</label>
      <textarea id="transcript-input" class="in transcript-input" maxlength="200000">${esc(edited || m.transcript || '')}</textarea>
      <p id="edit-message" class="edit-message" role="status"></p>
      <div class="transcript-actions"><button id="cancel-edit" class="btn out" type="button">Hủy</button>
      <button id="save-transcript" class="btn out" type="button">Lưu chỉnh sửa</button>
      <button id="save-and-retry" class="btn pri" type="button">Lưu và tạo lại biên bản</button></div>
    </div></section>`;
}
async function request(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Dữ liệu không hợp lệ hoặc yêu cầu chưa thực hiện được.');
  return data;
}

async function retrySummary() {
  const button = document.getElementById('retry-summary');
  if (button) button.disabled = true;
  try {
    await request(`${meetingUrl}/retry-summary`, {method: 'POST'});
    notice = {kind: 'info', text: 'Đã gửi yêu cầu tạo lại biên bản từ transcript đã lưu.'};
  } catch (error) {
    notice = {kind: 'error', text: error.message || 'Không kết nối được backend.'};
  }
  await show();
}

function setupTranscript(m) {
  document.querySelectorAll('[data-transcript]').forEach(button => button.addEventListener('click', () => {
    const source = button.dataset.transcript;
    const content = document.getElementById('transcript-content');
    content.hidden = false;
    content.innerHTML = speakerHtml(source === 'edited' ? m.transcript_edited : source === 'clean' ? m.transcript_clean : m.transcript);
    document.querySelectorAll('[data-transcript]').forEach(tab => tab.classList.toggle('selected', tab === button));
  }));
  const edit = document.getElementById('edit-transcript');
  if (!edit || edit.disabled) return;
  edit.addEventListener('click', () => {
    editorOpen = true;
    clearTimeout(timer);
    document.getElementById('transcript-editor').hidden = false;
    document.getElementById('transcript-content').hidden = true;
    document.getElementById('transcript-tabs').hidden = true;
    const sp = document.getElementById('speaker-panel');
    if (sp) sp.hidden = true;
    edit.hidden = true;
    const retry = document.getElementById('retry-summary');
    if (retry) retry.disabled = true;
    document.getElementById('transcript-input').focus();
  });
  document.getElementById('cancel-edit').addEventListener('click', () => {
    if (saving) return;
    editorOpen = false;
    show();
  });
  document.getElementById('save-transcript').addEventListener('click', () => saveTranscript(m, false));
  document.getElementById('save-and-retry').addEventListener('click', () => saveTranscript(m, true));
}

async function saveTranscript(m, retry) {
  if (saving) return;
  const input = document.getElementById('transcript-input');
  const message = document.getElementById('edit-message');
  const text = input.value.trim();
  if (!text) {message.textContent = 'Transcript không được để trống.'; return;}
  saving = true;
  const controls = ['cancel-edit', 'save-transcript', 'save-and-retry', 'transcript-input'];
  controls.forEach(key => {document.getElementById(key).disabled = true;});
  message.textContent = 'Đang lưu…';
  try {
    currentMeeting = await request(`${meetingUrl}/transcript`, {
      method: 'PATCH', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text, expected_revision: m.transcript_revision || 0})
    });
    editorOpen = false;
    notice = {kind: 'info', text: 'Đã lưu transcript chỉnh sửa. Bản ASR gốc được giữ nguyên.'};
    if (retry) await retrySummary();
    else await show();
  } catch (error) {
    message.textContent = error.message || 'Không lưu được. Nội dung đang sửa vẫn được giữ trong ô nhập.';
    controls.forEach(key => {document.getElementById(key).disabled = false;});
  } finally {
    saving = false;
  }
}

async function show() {
  clearTimeout(timer);
  if (editorOpen) return;
  const view = document.getElementById('view');
  if (!id) {view.innerHTML = '<div class="card empty">Đường dẫn thiếu mã cuộc họp.</div>'; return;}
  let m;
  try {
    m = await request(meetingUrl);
  } catch (error) {
    if (editorOpen) return;
    view.innerHTML = `<div class="card empty"><b>Không tải được cuộc họp</b>${esc(error.message)}<br><button class="btn out" id="reload-meeting" type="button">Thử tải lại</button></div>`;
    document.getElementById('reload-meeting').addEventListener('click', show);
    return;
  }
  if (editorOpen) return;
  currentMeeting = m;
  const [label, cls] = meetingStatus(m);
  let body = progressHtml(m);
  if (notice) body += `<p class="meeting-notice ${notice.kind === 'error' ? 'error' : ''}" role="status">${esc(notice.text)}</p>`;
  if (m.status === 'error') body += `<section class="card"><h3>Có lỗi khi xử lý audio</h3><pre class="txt">${esc(m.error)}</pre></section>`;
  if (m.transcript) {
    const ready = m.summary && typeof m.summary === 'object';
    const making = m.summary_status === 'processing';
    const error = m.summary_status === 'error' ? `<p class="meeting-notice error" role="alert">${esc(m.summary_error || 'Chưa tạo được biên bản. Hãy thử lại.')}${ready ? ' Biên bản thành công trước đó vẫn được giữ lại.' : ''}</p>` : '';
    const outdated = m.summary_outdated && ready ? '<p class="meeting-notice">Biên bản dưới đây thuộc phiên bản transcript trước. Hãy tạo lại để cập nhật nội dung đã chỉnh.</p>' : '';
    body += `<section class="card"><h3>Biên bản</h3>${error}${outdated}${ready ? minutesHtml(m) : `<p class="muted">${making ? 'Đang tạo biên bản. Transcript đã được lưu.' : 'Chưa có biên bản. Bạn có thể sửa transcript hoặc thử tạo lại.'}</p>`}
      <div class="transcript-actions"><button id="retry-summary" class="btn pri" type="button" ${isBusy(m) ? 'disabled' : ''}>${making ? 'Đang tạo biên bản…' : 'Tạo lại biên bản từ transcript'}</button></div></section>${transcriptHtml(m)}`;
  }
  view.innerHTML = `<a class="back" href="meetings.html">${ic('back', 18)} Quay lại danh sách</a>
    <h2 class="h1">${esc(m.title)}</h2><p class="meeting-meta"><span class="badge ${cls}">${esc(label)}</span> ${fmtDate(m.created)} · ${fmtDur(m.sec)}</p><div class="meeting-sections">${body}</div>`;
  if (m.transcript) setupTranscript(m);
  const retry = document.getElementById('retry-summary');
  if (retry && !retry.disabled) retry.addEventListener('click', retrySummary);
  if (isBusy(m)) timer = setTimeout(show, 3000);
}

window.addEventListener('beforeunload', event => {
  if (editorOpen) {event.preventDefault(); event.returnValue = '';}
});
show();
