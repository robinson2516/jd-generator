/* ── State ───────────────────────────────────────────────────── */
let currentJdId = null;

/* ── Init ────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  const token = localStorage.getItem('jd_token');
  if (token) {
    document.getElementById('landing-page').classList.add('hidden');
    showApp();
  }
  // Landing page is visible by default (no hidden class needed)
});

function showAuth(tab) {
  document.getElementById('landing-page').classList.add('hidden');
  document.getElementById('auth-screen').classList.remove('hidden');
  showAuthTab(tab);
}

/* ── Auth Tabs ───────────────────────────────────────────────── */
function showAuthTab(tab) {
  document.getElementById('auth-login').classList.toggle('hidden', tab !== 'login');
  document.getElementById('auth-register').classList.toggle('hidden', tab !== 'register');
  document.getElementById('tab-login').classList.toggle('active', tab === 'login');
  document.getElementById('tab-register').classList.toggle('active', tab === 'register');
}

/* ── Register ────────────────────────────────────────────────── */
async function doRegister() {
  const email    = document.getElementById('reg-email').value.trim();
  const password = document.getElementById('reg-password').value;
  const confirm  = document.getElementById('reg-confirm').value;

  if (!email || !password) return showToast('Please fill in all fields.', 'error');
  if (password !== confirm)  return showToast('Passwords do not match.', 'error');
  if (password.length < 8)   return showToast('Password must be at least 8 characters.', 'error');

  try {
    const res  = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Registration failed.');
    localStorage.setItem('jd_token', data.token);
    showApp();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

/* ── Login ───────────────────────────────────────────────────── */
async function doLogin() {
  const email    = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;

  if (!email || !password) return showToast('Please fill in all fields.', 'error');

  try {
    const res  = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Login failed.');
    localStorage.setItem('jd_token', data.token);
    showApp();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

/* ── Logout ──────────────────────────────────────────────────── */
function doLogout() {
  localStorage.removeItem('jd_token');
  location.reload(); // reloads to landing page
}

/* ── Show App ────────────────────────────────────────────────── */
function showApp() {
  document.getElementById('auth-screen').classList.add('hidden');
  document.getElementById('app-shell').classList.remove('hidden');
  showView('generate');
}

/* ── Navigation ──────────────────────────────────────────────── */
function showView(view) {
  document.getElementById('view-generate').classList.toggle('hidden', view !== 'generate');
  document.getElementById('view-history').classList.toggle('hidden',  view !== 'history');
  document.getElementById('nav-generate').classList.toggle('active', view === 'generate');
  document.getElementById('nav-history').classList.toggle('active',  view === 'history');
  if (view === 'history') loadHistory();
}

/* ── Generate ────────────────────────────────────────────────── */
async function doGenerate() {
  const company    = document.getElementById('f-company').value.trim();
  const title      = document.getElementById('f-title').value.trim();
  const website    = document.getElementById('f-website').value.trim();
  const skills     = document.getElementById('f-skills').value.trim();
  const experience = document.getElementById('f-experience').value.trim();

  if (!company || !title || !skills || !experience) {
    return showToast('Please fill in all fields.', 'error');
  }

  document.getElementById('gen-form-card').classList.add('hidden');
  document.getElementById('gen-result').classList.add('hidden');
  document.getElementById('gen-processing').classList.remove('hidden');

  try {
    const res  = await fetch('/api/generate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + localStorage.getItem('jd_token'),
      },
      body: JSON.stringify({
        company_name: company,
        job_title: title,
        skills,
        experience_level: experience,
        company_website: website,
      }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Generation failed.');

    currentJdId = data.id;
    document.getElementById('result-title').textContent = `${title} — ${company}`;
    document.getElementById('result-text').textContent  = data.text;
    document.getElementById('gen-processing').classList.add('hidden');
    document.getElementById('gen-result').classList.remove('hidden');
  } catch (err) {
    document.getElementById('gen-processing').classList.add('hidden');
    document.getElementById('gen-form-card').classList.remove('hidden');
    showToast('Error: ' + err.message, 'error');
  }
}

/* ── Reset ───────────────────────────────────────────────────── */
function resetForm() {
  currentJdId = null;
  document.getElementById('gen-result').classList.add('hidden');
  document.getElementById('gen-form-card').classList.remove('hidden');
}

/* ── Download PDF ────────────────────────────────────────────── */
async function downloadPdf(id) {
  const jdId = id || currentJdId;
  if (!jdId) return;

  try {
    const res = await fetch(`/api/history/${jdId}/pdf`, {
      headers: { 'Authorization': 'Bearer ' + localStorage.getItem('jd_token') },
    });
    if (!res.ok) throw new Error(await res.text());

    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    const disp = res.headers.get('Content-Disposition') || '';
    const match = disp.match(/filename=(.+)/);
    a.href     = url;
    a.download = match ? match[1] : 'job-description.pdf';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast('PDF downloaded!', 'success');
  } catch (err) {
    showToast('Download failed: ' + err.message, 'error');
  }
}

/* ── History ─────────────────────────────────────────────────── */
async function loadHistory() {
  const tbody = document.getElementById('history-body');
  tbody.innerHTML = '';
  document.getElementById('history-empty').classList.add('hidden');
  document.getElementById('history-loading').classList.remove('hidden');

  try {
    const res  = await fetch('/api/history', {
      headers: { 'Authorization': 'Bearer ' + localStorage.getItem('jd_token') },
    });
    const rows = await res.json();
    document.getElementById('history-loading').classList.add('hidden');

    if (!rows.length) {
      document.getElementById('history-empty').classList.remove('hidden');
      return;
    }

    tbody.innerHTML = rows.map(r => {
      const date = new Date(r.created_at).toLocaleDateString('en-US', {
        month: 'numeric', day: 'numeric', year: '2-digit',
      });
      return `
        <tr>
          <td>${escHtml(r.job_title)}</td>
          <td>${escHtml(r.company_name)}</td>
          <td style="color:var(--text-muted)">${date}</td>
          <td style="text-align:right">
            <button class="btn btn-ghost" style="padding:6px 14px;font-size:12px"
              onclick="downloadPdf(${r.id})">
              <svg viewBox="0 0 24 24"><path d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1M7 10l5 5 5-5M12 15V3"/></svg>
              PDF
            </button>
          </td>
        </tr>`;
    }).join('');
  } catch (err) {
    document.getElementById('history-loading').classList.add('hidden');
    showToast('Failed to load history.', 'error');
  }
}

/* ── Helpers ─────────────────────────────────────────────────── */
function escHtml(str) {
  return (str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function showToast(msg, type = 'success') {
  const toast = document.getElementById('toast');
  toast.textContent = msg;
  toast.className   = `toast ${type}`;
  toast.classList.remove('hidden');
  setTimeout(() => toast.classList.add('hidden'), 3500);
}

/* ── Enter key support ───────────────────────────────────────── */
document.addEventListener('keydown', e => {
  if (e.key !== 'Enter') return;
  const authLogin    = !document.getElementById('auth-login').classList.contains('hidden');
  const authRegister = !document.getElementById('auth-register').classList.contains('hidden');
  const authVisible  = !document.getElementById('auth-screen').classList.contains('hidden');
  if (authVisible && authLogin)    doLogin();
  if (authVisible && authRegister) doRegister();
});
