/* Job Monitor dashboard — fetches jobs.json and renders a filterable table. */

// Mirrors config.json criteria.keywords — used only to highlight/rank promising
// leads on the dashboard (the backend does the real gating for Discord).
const FOCUS_KEYWORDS = [
  'rotation', 'intern', 'junior', 'new grad', 'entry level', 'graduate',
  'co-op', 'coop', 'summer student', 'associate',
  'developer', 'programmer', 'software engineer', 'software developer',
  'data scientist', 'data analyst', 'machine learning', 'ml engineer',
  'ai engineer', 'full stack', 'front-end', 'back-end'
];

// One-click quick filters. Each just drives the search box.
const CHIPS = [
  { label: 'Intern', term: 'intern' },
  { label: 'New grad', term: 'new grad' },
  { label: 'Co-op', term: 'co-op' },
  { label: 'Software', term: 'software' },
  { label: 'Developer', term: 'developer' },
  { label: 'Data', term: 'data' },
  { label: 'AI / ML', term: 'machine learning' },
  { label: 'Remote', term: 'remote' },
];

// Jobs older than this drop off the dashboard. Workday/Greenhouse carry a real
// posted_days (capped at scrape time); date-less boards (Rippling/BambooHR) fall
// back to days-since-first_seen — "scraped >6 days ago = too late".
const MAX_AGE_DAYS = 6;

const hiddenLocations = getHiddenLocations();
const keptLocations = getKeptLocations();

const state = {
  jobs: [],
  tab: 'all',          // 'all' | 'new'
  search: '',
  company: '',
  maxDays: null,       // null = any time, otherwise posted_days <= maxDays
  locations: new Set() // empty = all locations
};

const els = {
  status: document.getElementById('status'),
  tabs: document.getElementById('tabs'),
  chips: document.getElementById('chips'),
  search: document.getElementById('search'),
  company: document.getElementById('company-filter'),
  date: document.getElementById('date-filter'),
  locationTrigger: document.getElementById('location-trigger'),
  locationLabel: document.getElementById('location-label'),
  locationPanel: document.getElementById('location-panel'),
  rows: document.getElementById('job-rows'),
  tableCard: document.getElementById('table-card'),
  emptyState: document.getElementById('empty-state'),
  clearFilters: document.getElementById('clear-filters'),
  jobCount: document.getElementById('job-count'),
};

const modalEls = {
  backdrop: document.getElementById('job-modal-backdrop'),
  modal: document.getElementById('job-modal'),
  close: document.getElementById('modal-close'),
  title: document.getElementById('modal-title'),
  company: document.getElementById('modal-company'),
  location: document.getElementById('modal-location'),
  posted: document.getElementById('modal-posted'),
  summarySection: document.getElementById('modal-summary-section'),
  summary: document.getElementById('modal-summary'),
  blurbSection: document.getElementById('modal-blurb-section'),
  blurbHeading: document.getElementById('modal-blurb-heading'),
  blurb: document.getElementById('modal-blurb'),
  descriptionSection: document.getElementById('modal-description-section'),
  description: document.getElementById('modal-description'),
  similarSection: document.getElementById('modal-similar-section'),
  similarList: document.getElementById('modal-similar-list'),
  externalLink: document.getElementById('modal-external-link'),
};
let lastFocusedEl = null;

init();

async function init() {
  try {
    const resp = await fetch('jobs.json', { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    state.jobs = data.jobs || [];
    els.status.textContent = `Updated ${relativeTime(data.updated_at)}`;
    renderChips();
    populateFilters();
    bindEvents();
    render();
  } catch (err) {
    els.status.classList.replace('success', 'error');
    els.status.textContent = 'Failed to load jobs.json';
    console.error(err);
  }
}

function allLocations(job) {
  return (job.locations && job.locations.length) ? job.locations : [job.location].filter(Boolean);
}

// A single location is shown when it isn't a foreign country (unless rescued),
// is always shown if it's clearly Quebec/Ontario, and otherwise shows unless the
// user hid it in /admin. See locations.js for the classifier.
function locationShown(loc) {
  if (keptLocations.has(loc)) return true;
  const bucket = classifyLocation(loc);
  if (bucket === 'foreign') return false;
  if (bucket === 'good') return true;
  return !hiddenLocations.has(loc);
}

// Locations of a job that should appear on the dashboard.
function shownLocations(job) {
  return allLocations(job).filter(locationShown);
}

// A job drops off the dashboard only when none of its locations are shown — a
// job in "Montreal + Berlin" still shows (for Montreal) even though Berlin is foreign.
function isHiddenJob(job) {
  const locs = allLocations(job);
  return locs.length > 0 && !locs.some(locationShown);
}

function relevance(job) {
  const title = job.title.toLowerCase();
  return FOCUS_KEYWORDS.reduce((n, k) => n + (title.includes(k) ? 1 : 0), 0);
}

function renderChips() {
  els.chips.replaceChildren(...CHIPS.map(({ label, term }) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'chip';
    btn.dataset.term = term;
    btn.textContent = label;
    btn.addEventListener('click', () => {
      const active = state.search === term;
      state.search = active ? '' : term;
      els.search.value = state.search;
      render();
    });
    return btn;
  }));
}

function populateFilters() {
  for (const company of uniqueSorted(state.jobs.map(j => j.company))) {
    els.company.append(new Option(company, company));
  }

  // Location checkboxes, most common first, then alphabetical. Hidden ones omitted.
  const counts = new Map();
  for (const j of state.jobs) {
    for (const loc of shownLocations(j)) {
      counts.set(loc, (counts.get(loc) || 0) + 1);
    }
  }
  const locations = [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([loc]) => loc);

  const clear = document.createElement('button');
  clear.className = 'multiselect-clear';
  clear.type = 'button';
  clear.textContent = 'Clear selection';
  clear.addEventListener('click', () => {
    state.locations.clear();
    els.locationPanel.querySelectorAll('input').forEach(cb => { cb.checked = false; });
    updateLocationLabel();
    render();
  });
  els.locationPanel.append(clear);

  for (const loc of locations) {
    const label = document.createElement('label');
    label.className = 'multiselect-option';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = loc;
    cb.addEventListener('change', () => {
      cb.checked ? state.locations.add(loc) : state.locations.delete(loc);
      updateLocationLabel();
      render();
    });
    const text = document.createElement('span');
    text.textContent = `${loc} (${counts.get(loc)})`;
    label.append(cb, text);
    els.locationPanel.append(label);
  }
}

function updateLocationLabel() {
  const n = state.locations.size;
  els.locationLabel.textContent =
    n === 0 ? 'All locations' : n === 1 ? [...state.locations][0] : `${n} locations`;
}

function bindEvents() {
  els.tabs.addEventListener('click', e => {
    const btn = e.target.closest('.tab');
    if (!btn) return;
    state.tab = btn.dataset.tab;
    els.tabs.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t === btn));
    render();
  });
  els.search.addEventListener('input', () => {
    state.search = els.search.value.trim().toLowerCase();
    render();
  });
  els.company.addEventListener('change', () => { state.company = els.company.value; render(); });
  els.date.addEventListener('change', () => {
    state.maxDays = els.date.value === '' ? null : Number(els.date.value);
    render();
  });

  els.locationTrigger.addEventListener('click', () => {
    const open = els.locationPanel.hidden;
    els.locationPanel.hidden = !open;
    els.locationTrigger.setAttribute('aria-expanded', String(open));
  });
  document.addEventListener('click', e => {
    if (!e.target.closest('.multiselect')) {
      els.locationPanel.hidden = true;
      els.locationTrigger.setAttribute('aria-expanded', 'false');
    }
  });

  els.clearFilters.addEventListener('click', () => {
    state.search = state.company = '';
    state.maxDays = null;
    state.locations.clear();
    els.search.value = els.company.value = els.date.value = '';
    els.locationPanel.querySelectorAll('input').forEach(cb => { cb.checked = false; });
    updateLocationLabel();
    render();
  });

  modalEls.close.addEventListener('click', closeModal);
  modalEls.backdrop.addEventListener('click', e => {
    if (e.target === modalEls.backdrop) closeModal();
  });
}

function visibleJobs() {
  return state.jobs.filter(j => {
    if (isHiddenJob(j)) return false;
    const age = effectiveAge(j);
    // Baseline freshness cap — drops date-less jobs scraped >6 days ago.
    if (age != null && age > MAX_AGE_DAYS) return false;
    if (state.tab === 'new' && !j.is_new) return false;
    if (state.company && j.company !== state.company) return false;
    if (state.maxDays !== null && (age == null || age > state.maxDays)) return false;
    if (state.locations.size
        && !shownLocations(j).some(loc => state.locations.has(loc))) return false;
    if (state.search) {
      const haystack = `${j.title} ${shownLocations(j).join(' ')} ${j.company}`.toLowerCase();
      if (!haystack.includes(state.search)) return false;
    }
    return true;
  });
}

function render() {
  const jobs = visibleJobs();
  // Surface the best leads first: keyword relevance, then new, then most recent.
  jobs.sort((a, b) =>
    relevance(b) - relevance(a)
    || Number(b.is_new) - Number(a.is_new)
    || (effectiveAge(a) ?? 99) - (effectiveAge(b) ?? 99)
    || a.title.localeCompare(b.title));

  const newCount = state.jobs.filter(j => j.is_new && !isHiddenJob(j)).length;
  const tracked = state.jobs.filter(j => !isHiddenJob(j)).length;

  els.tabs.querySelector('[data-tab="all"]').textContent = `All (${tracked})`;
  els.tabs.querySelector('[data-tab="new"]').textContent = `New (${newCount})`;
  els.jobCount.textContent = `${tracked} jobs tracked`;

  els.chips.querySelectorAll('.chip').forEach(c =>
    c.classList.toggle('active', c.dataset.term === state.search));

  els.tableCard.hidden = jobs.length === 0;
  els.emptyState.hidden = jobs.length > 0;

  els.rows.replaceChildren(...jobs.map(rowFor));
}

function rowFor(job) {
  const tr = document.createElement('tr');
  if (relevance(job) > 0) tr.className = 'row-match';

  const title = document.createElement('td');
  if (relevance(job) > 0) {
    const dot = document.createElement('span');
    dot.className = 'match-dot';
    dot.title = 'Matches your focus keywords';
    title.append(dot);
  }
  const titleBtn = document.createElement('button');
  titleBtn.type = 'button';
  titleBtn.className = 'row-title-btn';
  titleBtn.textContent = job.title;
  titleBtn.addEventListener('click', () => openModal(job));
  title.append(titleBtn);
  if (job.is_new) {
    const badge = document.createElement('span');
    badge.className = 'badge-new';
    badge.textContent = 'NEW';
    title.append(badge);
  }

  const company = document.createElement('td');
  company.className = 'col-secondary';
  company.textContent = job.company;

  const location = document.createElement('td');
  location.className = 'col-secondary';
  const locs = shownLocations(job);
  location.textContent = locs[0] || '';
  if (locs.length > 1) {
    const more = document.createElement('span');
    more.className = 'loc-more';
    more.textContent = `+${locs.length - 1} more`;
    location.title = locs.join('\n');
    location.append(more);
  }

  const posted = document.createElement('td');
  posted.className = 'col-muted col-posted';
  posted.textContent = postedLabel(job);

  tr.append(title, company, location, posted);
  return tr;
}

function uniqueSorted(values) {
  return [...new Set(values)].sort((a, b) => a.localeCompare(b));
}

function daysSince(iso) {
  if (!iso) return null;
  const ms = Date.now() - new Date(iso).getTime();
  return Number.isNaN(ms) ? null : Math.max(Math.floor(ms / 86400000), 0);
}

// Real posting age when the board provides it, else days since we first saw it.
function effectiveAge(job) {
  return job.posted_days != null ? job.posted_days : daysSince(job.first_seen);
}

// What to show in the Posted column: the board's text, or "Scraped Nd ago" for
// date-less boards (Rippling/BambooHR) derived from first_seen.
function postedLabel(job) {
  if (job.posted_on) return job.posted_on;
  const d = daysSince(job.first_seen);
  if (d == null) return '';
  if (d === 0) return 'Scraped today';
  if (d === 1) return 'Scraped yesterday';
  return `Scraped ${d}d ago`;
}

function relativeTime(iso) {
  if (!iso) return 'recently';
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

function openModal(job) {
  lastFocusedEl = document.activeElement;

  modalEls.title.textContent = job.title;
  modalEls.company.textContent = job.company;
  modalEls.location.textContent = shownLocations(job)[0] || job.location || '';
  modalEls.posted.textContent = postedLabel(job);
  modalEls.externalLink.href = job.url;

  setSection(modalEls.summarySection, modalEls.summary, job.role_summary);
  modalEls.blurbHeading.textContent = `About ${job.company}`;
  setSection(modalEls.blurbSection, modalEls.blurb, job.company_blurb);
  setSection(modalEls.descriptionSection, modalEls.description, job.description);

  const similar = similarJobs(job);
  modalEls.similarSection.hidden = similar.length === 0;
  modalEls.similarList.replaceChildren(...similar.map(similarRow));

  modalEls.backdrop.hidden = false;
  document.body.style.overflow = 'hidden';
  modalEls.close.focus();
  document.addEventListener('keydown', onModalKeydown);
}

function setSection(section, el, text) {
  section.hidden = !text;
  el.textContent = text || '';
}

function closeModal() {
  modalEls.backdrop.hidden = true;
  document.body.style.overflow = '';
  document.removeEventListener('keydown', onModalKeydown);
  if (lastFocusedEl) lastFocusedEl.focus();
}

function onModalKeydown(e) {
  if (e.key === 'Escape') { closeModal(); return; }
  if (e.key !== 'Tab') return;
  // Minimal focus trap: cycle between the modal's focusable elements.
  const focusable = modalEls.modal.querySelectorAll('button, a[href]');
  if (focusable.length === 0) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault(); last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault(); first.focus();
  }
}

function similarRow(job) {
  const li = document.createElement('li');
  const a = document.createElement('a');
  a.href = job.url;
  a.target = '_blank';
  a.rel = 'noopener';
  const label = document.createElement('span');
  label.textContent = `${job.title} — ${job.company}`;
  const meta = document.createElement('span');
  meta.className = 'sim-meta';
  meta.textContent = shownLocations(job)[0] || job.location || '';
  a.append(label, meta);
  li.append(a);
  return li;
}

// Same company is a strong same-team-different-role signal (+2); shared
// title keywords longer than 3 chars (skips noise words like "of"/"in") each
// add +1. Ties broken by freshness; hidden jobs (per the location filter)
// never surface here, consistent with the rest of the dashboard.
function similarJobs(job, limit = 5) {
  const titleWords = new Set(
    job.title.toLowerCase().split(/\W+/).filter(w => w.length > 3)
  );
  const scored = state.jobs
    .filter(j => j.id !== job.id && !isHiddenJob(j))
    .map(j => {
      let score = j.company === job.company ? 2 : 0;
      const otherWords = new Set(j.title.toLowerCase().split(/\W+/).filter(w => w.length > 3));
      for (const w of titleWords) if (otherWords.has(w)) score += 1;
      return { job: j, score };
    })
    .filter(({ score }) => score > 0)
    .sort((a, b) => b.score - a.score || (effectiveAge(a.job) ?? 99) - (effectiveAge(b.job) ?? 99));
  return scored.slice(0, limit).map(({ job }) => job);
}
