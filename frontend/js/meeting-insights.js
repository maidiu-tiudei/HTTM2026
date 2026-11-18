let speakerFilter = '';
let chatBusy = false;
const chatTurns = [];

function clockText(seconds) {
  const total = Math.floor(seconds);
  const minutes = Math.floor(total / 60);
  return `${String(minutes).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
}

function speakerName(id) {
  return id ? `Người ${id.slice(1)} · ${id}` : 'Chưa rõ người nói';
}

function speakersHtml(m) {
  const rows = m.speaker_segments || [];
  const labels = [...new Set(rows.map(row => row.speaker_id || 'unknown'))];
  const busy = m.speaker_status === 'processing';
  const playback = m.audio_available
    ? `<audio id="meeting-audio" controls preload="metadata" src="${esc(meetingUrl)}/audio" aria-label="Audio cuộc họp"></audio>`
    : '';
  const canAnalyze = !rows.length || m.speaker_status === 'error' || rows.some(row => !row.speaker_id);
  const analyzeLabel = busy ? 'Đang tách người nói…'
    : rows.length ? 'Phân tích lại người nói' : 'Phân tích người nói';
  const action = m.audio_available && canAnalyze
    ? `<button type="button" class="btn out" id="analyze-speakers" ${isBusy(m) ? 'disabled' : ''}>${analyzeLabel}</button>`
    : '';
  return `<section class="card speaker-card" id="speakers"><div class="transcript-head">
    <h3>Lời nói theo từng người</h3>${action}</div>${playback}
    ${busy ? '<p class="muted" role="status">Đang xác định các lượt nói từ audio.</p>' : ''}
    ${m.speaker_error ? `<p class="meeting-notice error" role="alert">${esc(m.speaker_error)}</p>` : ''}
    ${rows.length ? `<div class="speaker-toolbar">
      <p class="muted">ID giọng nói trong cuộc họp. Mốc thời gian dẫn đến audio gốc.</p>
      <label for="speaker-filter">Lọc người nói</label>
      <select id="speaker-filter"><option value="">Tất cả</option>${labels.map(label =>
        `<option value="${esc(label)}">${esc(speakerName(label === 'unknown' ? null : label))}</option>`).join('')}</select>
    </div><ol id="speaker-turns" class="speaker-turns">${rows.map(row => {
      const color = row.speaker_id ? (Number(row.speaker_id.slice(1)) - 1) % 4 : 4;
      const time = `${clockText(row.start)} – ${clockText(row.end)}`;
      return `<li class="speaker-turn speaker-color-${color}" data-speaker="${esc(row.speaker_id || 'unknown')}" id="speaker-turn-${esc(row.id)}">
        <div class="speaker-turn-header"><strong>${esc(speakerName(row.speaker_id))}</strong>
          ${m.audio_available ? `<button type="button" class="speaker-time" data-seek="${esc(row.start)}" aria-label="Phát audio từ ${clockText(row.start)}">${time}</button>` : `<span class="speaker-time">${time}</span>`}
        </div><p>${esc(row.text)}</p></li>`;
    }).join('')}</ol>` : !busy && !m.speaker_error ? `<p class="muted">${m.audio_available ? 'Phân tích audio để xem ai nói ở từng đoạn.' : 'Cuộc họp này chưa có dữ liệu người nói hoặc audio để phân tích.'}</p>` : ''}
    </section>`;
}

function applySpeakerFilter() {
  const filter = document.getElementById('speaker-filter');
  if (filter) filter.value = speakerFilter;
  document.querySelectorAll('.speaker-turn').forEach(row => {
    row.hidden = Boolean(speakerFilter && row.dataset.speaker !== speakerFilter);
  });
}

function playFrom(seconds) {
  const audio = document.getElementById('meeting-audio');
  if (!audio || !Number.isFinite(seconds)) return;
  audio.currentTime = seconds;
  audio.play().catch(() => {});
}

function setupSpeakers() {
  const section = document.getElementById('speakers');
  if (!section) return;
  const filter = document.getElementById('speaker-filter');
  if (filter && !Array.from(filter.options).some(option => option.value === speakerFilter)) speakerFilter = '';
  applySpeakerFilter();
  filter?.addEventListener('change', () => {
    speakerFilter = filter.value;
    applySpeakerFilter();
  });
  section.addEventListener('click', event => {
    const button = event.target.closest('button[data-seek]');
    if (button) playFrom(Number(button.dataset.seek));
  });
  const analyze = document.getElementById('analyze-speakers');
  analyze?.addEventListener('click', async () => {
    analyze.disabled = true;
    try {
      await request(`${meetingUrl}/speakers`, {method: 'POST'});
      notice = null;
    } catch (error) {
      notice = {kind: 'error', text: error.message};
    }
    await show();
  });
}

function chatHtml() {
  const icon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 11.5a7.5 7.5 0 0 1-7.5 7.5H9l-5 3v-5a7.5 7.5 0 0 1-2-5.5A7.5 7.5 0 0 1 9.5 4h4a7.5 7.5 0 0 1 7.5 7.5Z"/><path d="M7.5 11.5h8"/></svg>';
  return `<div class="meeting-chat-widget" id="meeting-chat-widget">
    <button type="button" class="chat-launcher" id="chat-launcher" aria-haspopup="dialog" aria-expanded="false" aria-controls="meeting-chat">
      ${icon}<span>Hỏi đáp cuộc họp</span>
    </button>
    <section class="meeting-chat" id="meeting-chat" role="dialog" aria-labelledby="chat-title" hidden>
      <div class="chat-header">${icon}<h3 id="chat-title">Hỏi đáp cuộc họp</h3>
        <button type="button" class="chat-close" id="chat-close" aria-label="Thu gọn hỏi đáp">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg>
        </button>
      </div>
      <div class="chat-scroll" id="chat-scroll">
        <p class="muted">Hỏi về nội dung cuộc họp này và xem đoạn trích làm căn cứ cho câu trả lời.</p>
        <div class="chat-suggestions">
          <button type="button" class="btn out" data-question="Tóm tắt các ý chính của cuộc họp.">Tóm tắt ý chính</button>
          <button type="button" class="btn out" data-question="Cuộc họp đã chốt những quyết định nào?">Các quyết định</button>
          <button type="button" class="btn out" data-question="Ai được giao việc gì và hạn hoàn thành là khi nào?">Việc cần làm</button>
        </div>
        <ol class="chat-messages" id="chat-messages" aria-live="polite"></ol>
      </div>
      <form id="chat-form" class="chat-form">
        <label for="chat-question">Câu hỏi của bạn</label>
        <textarea id="chat-question" maxlength="1200" rows="2" required placeholder="Nhập câu hỏi…"></textarea>
        <button type="submit" class="btn pri" id="chat-send">Gửi</button>
        <p class="edit-message" id="chat-error" role="alert"></p>
      </form>
    </section>
  </div>`;
}

function syncMeetingChat(previousMeeting) {
  const widget = document.getElementById('meeting-chat-widget');
  if (widget) {
    widget.hidden = !currentMeeting.transcript;
    if (previousMeeting?.speaker_version !== currentMeeting.speaker_version ||
        previousMeeting?.transcript_revision !== currentMeeting.transcript_revision) renderChat();
  } else if (currentMeeting.transcript) {
    document.body.insertAdjacentHTML('beforeend', chatHtml());
    setupChat();
  }
}

function renderChat(scrollToLatest = false) {
  const messages = document.getElementById('chat-messages');
  if (!messages) return;
  messages.innerHTML = chatTurns.map((turn, index) => `<li>
    <p class="chat-question"><strong>Bạn</strong> ${esc(turn.question)}</p>
    <div class="chat-answer"><p>${esc(turn.answer)}</p>
    ${turn.partial_context ? '<small>Câu trả lời dựa trên các đoạn liên quan đã chọn.</small>' : ''}
    ${turn.citations.map((source, sourceIndex) => {
      const label = Number.isFinite(source.start) ? `${speakerName(source.speaker_id)} · ${clockText(source.start)}` : `Đoạn ${source.id}`;
      const canJump = Number.isFinite(source.start) && turn.speaker_version === currentMeeting?.speaker_version
        && turn.transcript_revision === (currentMeeting?.transcript_revision || 0);
      return `<blockquote class="chat-source">${canJump
        ? `<button type="button" data-chat-turn="${index}" data-chat-source="${sourceIndex}">${esc(label)}</button>`
        : `<strong>${esc(label)}</strong>`}<p>${esc(source.quote)}</p></blockquote>`;
    }).join('')}</div>
  </li>`).join('');
  if (chatBusy) messages.insertAdjacentHTML('beforeend', '<li class="muted">Đang tìm câu trả lời…</li>');
  if (scrollToLatest) {
    const scroll = document.getElementById('chat-scroll');
    if (document.getElementById('meeting-chat').hidden) scroll.dataset.pendingScroll = 'true';
    else scroll.scrollTop = scroll.scrollHeight;
  }
}

function setupChat() {
  const chat = document.getElementById('meeting-chat');
  const launcher = document.getElementById('chat-launcher');
  const close = document.getElementById('chat-close');
  const scroll = document.getElementById('chat-scroll');
  const input = document.getElementById('chat-question');
  const send = document.getElementById('chat-send');
  const errorBox = document.getElementById('chat-error');
  function setOpen(open) {
    chat.hidden = !open;
    launcher.hidden = open;
    launcher.setAttribute('aria-expanded', String(open));
    if (open && scroll.dataset.pendingScroll) {
      scroll.scrollTop = scroll.scrollHeight;
      delete scroll.dataset.pendingScroll;
    }
    (open ? close : launcher).focus({preventScroll: true});
  }
  launcher.addEventListener('click', () => setOpen(true));
  close.addEventListener('click', () => setOpen(false));
  chat.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      event.preventDefault();
      setOpen(false);
    }
  });
  chat.addEventListener('click', event => {
    const suggestion = event.target.closest('button[data-question]');
    if (suggestion && !chatBusy) {
      input.value = suggestion.dataset.question;
      input.focus();
    }
    const citation = event.target.closest('button[data-chat-source]');
    if (!citation) return;
    const source = chatTurns[Number(citation.dataset.chatTurn)].citations[Number(citation.dataset.chatSource)];
    speakerFilter = '';
    applySpeakerFilter();
    setOpen(false);
    const row = document.getElementById(`speaker-turn-${source.id}`);
    row?.querySelector('button[data-seek]')?.focus({preventScroll: true});
    row?.scrollIntoView({block: 'nearest', behavior: 'smooth'});
    playFrom(source.start);
  });
  document.getElementById('chat-form').addEventListener('submit', async event => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question || chatBusy) return;
    chatBusy = true;
    send.disabled = true;
    errorBox.textContent = '';
    renderChat(true);
    try {
      const history = chatTurns.filter(turn => turn.transcript_revision === (currentMeeting.transcript_revision || 0))
        .slice(-4).map(turn => ({question: turn.question, answer: turn.answer.slice(0, 6000)}));
      const answer = await request(`${meetingUrl}/chat`, {method: 'POST',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify({question, history})});
      chatTurns.push({question, ...answer});
      if (input.value.trim() === question) input.value = '';
    } catch (error) {
      errorBox.textContent = error.message || 'Chưa hỏi đáp được. Hãy thử lại.';
    } finally {
      chatBusy = false;
      send.disabled = false;
      renderChat(true);
    }
  });
}
