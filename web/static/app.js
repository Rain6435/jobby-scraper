const $ = (sel) => document.querySelector(sel);

document.querySelectorAll('.tab').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach((b) => b.classList.remove('active'));
    document.querySelectorAll('.panel').forEach((p) => { p.hidden = true; });
    btn.classList.add('active');
    $(`#tab-${btn.dataset.tab}`).hidden = false;
  });
});

async function api(url, opts = {}) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

async function loadProfileAndSettings() {
  const data = await api('/api/profile');
  const p = data.profile || {};
  const s = data.settings || {};
  $('#prof-full-name').value = p.full_name || '';
  $('#prof-email').value = p.email || data.primary_email || '';
  $('#prof-phone').value = p.phone || '';
  $('#prof-location').value = p.location || '';
  $('#prof-linkedin').value = p.linkedin_url || '';
  $('#prof-github').value = p.github_url || '';
  $('#prof-skills').value = (p.skills || []).join(', ');

  $('#set-email').value = data.primary_email || p.email || '';
  $('#set-alias').value = data.email_alias_strategy || 'direct';
  $('#set-verify').value = data.verification_provider || 'manual_prompt';
  $('#imap-fields').hidden = $('#set-verify').value !== 'imap';
  $('#set-mode').value = s.execution_mode || 'copilot';
  $('#set-limit').value = s.daily_limit ?? 15;
  $('#set-score').value = s.min_match_score ?? 55;
  $('#set-autocreate').checked = s.auto_create_accounts !== false;
}

$('#set-verify').addEventListener('change', () => {
  $('#imap-fields').hidden = $('#set-verify').value !== 'imap';
});

async function loadJobs() {
  const q = encodeURIComponent($('#job-search').value.trim());
  const jobs = await api(`/api/jobs?limit=30&search=${q}`);
  const root = $('#jobs-list');
  root.innerHTML = '';
  if (!jobs.length) {
    root.innerHTML = '<p class="muted">No jobs found in jobs.db. Run scraper.main first.</p>';
    return;
  }
  for (const job of jobs) {
    const el = document.createElement('div');
    el.className = 'item';
    el.innerHTML = `
      <div class="item-row">
        <div><strong>${job.title}</strong><div class="muted">${job.company} · ${job.source}</div></div>
        <button class="btn primary">Prepare</button>
      </div>
    `;
    el.querySelector('button').addEventListener('click', async () => {
      await api('/api/applications/prepare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(job),
      });
      await loadApplications();
    });
    root.appendChild(el);
  }
}

async function loadApplications() {
  const apps = await api('/api/applications');
  const root = $('#apps-list');
  root.innerHTML = '';
  if (!apps.length) {
    root.innerHTML = '<p class="muted">No applications queued yet.</p>';
    return;
  }
  for (const app of apps) {
    const snap = app.job_snapshot || {};
    const shots = (app.screenshot_paths || []).map((p) => {
      const name = p.split('/').pop();
      return `<img src="/api/screenshots/${encodeURIComponent(name)}" alt="Review screenshot" style="max-width:100%;border-radius:6px;border:1px solid var(--border);margin-top:6px;" />`;
    }).join('');
    const el = document.createElement('div');
    el.className = 'item';
    el.innerHTML = `
      <div class="item-row">
        <div>
          <strong>${snap.title || app.job_id}</strong>
          <div class="muted">${snap.company || ''} · Score ${Math.round(app.match_score)}% · ${app.current_step}</div>
        </div>
        <span class="badge ${app.status}">${app.status}</span>
      </div>
      ${app.error_detail ? `<div class="muted">${app.error_detail}</div>` : ''}
      <pre class="payload">${JSON.stringify(app.filled_payload || {}, null, 2)}</pre>
      ${shots}
      <div class="inline-form">
        ${app.status === 'ready_for_review' ? '<button class="btn ok btn-approve">Approve & Submit</button>' : ''}
        ${app.status === 'awaiting_email_otp' ? '<input class="otp-input" placeholder="6-digit OTP" /><button class="btn primary btn-otp">Verify OTP</button>' : ''}
        ${app.status === 'awaiting_user_qa' ? '<input class="qa-q" placeholder="Question" /><input class="qa-a" placeholder="Your answer" /><button class="btn primary btn-qa">Save & Resume</button>' : ''}
        ${(app.status === 'awaiting_auth' || app.status === 'awaiting_captcha') && snap.url ? '<button class="btn primary btn-live-auth">Open Live Browser</button>' : ''}
      </div>
    `;
    const approveBtn = el.querySelector('.btn-approve');
    if (approveBtn) {
      approveBtn.addEventListener('click', async () => {
        await api(`/api/applications/${app.id}/approve`, { method: 'POST' });
        await loadApplications();
      });
    }
    const otpBtn = el.querySelector('.btn-otp');
    if (otpBtn) {
      otpBtn.addEventListener('click', async () => {
        const otp = el.querySelector('.otp-input').value.trim();
        await api(`/api/applications/${app.id}/answer`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ otp_code: otp }),
        });
        await loadApplications();
        await loadCredentials();
      });
    }
    const qaBtn = el.querySelector('.btn-qa');
    if (qaBtn) {
      qaBtn.addEventListener('click', async () => {
        const question_text = el.querySelector('.qa-q').value.trim() || app.error_detail;
        const answer_value = el.querySelector('.qa-a').value.trim();
        await api(`/api/applications/${app.id}/answer`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question_text, answer_value }),
        });
        await loadApplications();
        await loadAnswers();
      });
    }
    const liveAuthBtn = el.querySelector('.btn-live-auth');
    if (liveAuthBtn) {
      liveAuthBtn.addEventListener('click', () => openScreencast(snap.url));
    }
    root.appendChild(el);
  }
}

async function loadCredentials() {
  const creds = await api('/api/credentials');
  const root = $('#creds-list');
  root.innerHTML = '';
  for (const c of creds) {
    const el = document.createElement('div');
    el.className = 'item';
    el.innerHTML = `
      <div class="item-row">
        <div><strong>${c.domain_key}</strong><div class="muted">${c.board} · ${c.email_used} · ${c.provision_method}</div></div>
        <span class="badge ${c.status}">${c.status}</span>
      </div>
    `;
    root.appendChild(el);
  }
}

async function loadAnswers() {
  const answers = await api('/api/answers');
  const root = $('#answers-list');
  root.innerHTML = '';
  for (const a of answers) {
    const el = document.createElement('div');
    el.className = 'item';
    el.innerHTML = `<strong>${a.question_text}</strong><div class="muted">${a.answer_value} (reused ${a.times_reused}x)</div>`;
    root.appendChild(el);
  }
}

$('#resume-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData();
  fd.append('file', $('#resume-file').files[0]);
  $('#resume-status').textContent = 'Extracting profile...';
  await api('/api/profile/resume', { method: 'POST', body: fd });
  $('#resume-status').textContent = 'Profile extracted and saved!';
  await loadProfileAndSettings();
});

$('#profile-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fullName = $('#prof-full-name').value.trim();
  const parts = fullName.split(/\s+/);
  await api('/api/profile', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      display_name: fullName,
      primary_email: $('#prof-email').value.trim(),
      email_alias_strategy: $('#set-alias').value,
      profile: {
        full_name: fullName,
        first_name: parts[0] || '',
        last_name: parts.slice(1).join(' '),
        email: $('#prof-email').value.trim(),
        phone: $('#prof-phone').value.trim(),
        location: $('#prof-location').value.trim(),
        linkedin_url: $('#prof-linkedin').value.trim(),
        github_url: $('#prof-github').value.trim(),
        skills: $('#prof-skills').value.split(',').map((s) => s.trim()).filter(Boolean),
      },
    }),
  });
});

$('#settings-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  await api('/api/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      primary_email: $('#set-email').value.trim(),
      email_alias_strategy: $('#set-alias').value,
      verification_provider: $('#set-verify').value,
      imap_host: $('#imap-host').value.trim(),
      imap_port: Number($('#imap-port').value || 993),
      imap_username: $('#imap-user').value.trim(),
      imap_password: $('#imap-pass').value,
      execution_mode: $('#set-mode').value,
      daily_limit: Number($('#set-limit').value),
      min_match_score: Number($('#set-score').value),
      auto_create_accounts: $('#set-autocreate').checked,
      blocked_companies: [],
    }),
  });
});

let ws = null;
function openScreencast(url) {
  if (!url) return;
  const domain = new URL(url).host;
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const canvas = $('#screencast-canvas');
  const ctx = canvas.getContext('2d');
  $('#screencast-modal').hidden = false;

  ws = new WebSocket(`${proto}//${location.host}/ws/browser/${encodeURIComponent(domain)}?url=${encodeURIComponent(url)}`);
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === 'frame') {
      const img = new Image();
      img.onload = () => ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      img.src = `data:image/jpeg;base64,${msg.data}`;
    } else if (msg.type === 'captured') {
      $('#screencast-modal').hidden = true;
      loadCredentials();
      loadApplications();
    }
  };
  canvas.onclick = (ev) => {
    const rect = canvas.getBoundingClientRect();
    const x = (ev.clientX - rect.left) * (canvas.width / rect.width);
    const y = (ev.clientY - rect.top) * (canvas.height / rect.height);
    ws?.send(JSON.stringify({ type: 'mouse', event: 'mousePressed', x, y }));
    ws?.send(JSON.stringify({ type: 'mouse', event: 'mouseReleased', x, y }));
  };
  canvas.onkeydown = (ev) => {
    if (ev.key.length === 1) ws?.send(JSON.stringify({ type: 'key', text: ev.key }));
  };
}

$('#btn-open-screencast').addEventListener('click', () => {
  openScreencast($('#login-url').value.trim());
});

$('#btn-capture-session').addEventListener('click', () => {
  ws?.send(JSON.stringify({ type: 'capture_session', email_used: $('#set-email').value.trim() }));
});
$('#btn-close-screencast').addEventListener('click', () => {
  ws?.close();
  $('#screencast-modal').hidden = true;
});

$('#btn-load-jobs').addEventListener('click', loadJobs);
$('#btn-refresh-apps').addEventListener('click', loadApplications);

Promise.all([loadProfileAndSettings(), loadJobs(), loadApplications(), loadCredentials(), loadAnswers()]);
