/* Admin: review locations, grouped into good / unsure / foreign buckets. */

const state = {
  counts: new Map(),                 // location -> number of jobs
  hidden: getHiddenLocations(),      // 'unsure' locations the user hid
  kept: getKeptLocations(),          // 'foreign' locations the user rescued
  search: '',
  showForeign: false,
};

const els = {
  status: document.getElementById('status'),
  search: document.getElementById('search'),
  goodGrid: document.getElementById('good-grid'),
  unsureGrid: document.getElementById('unsure-grid'),
  foreignGrid: document.getElementById('foreign-grid'),
  goodCount: document.getElementById('good-count'),
  unsureCount: document.getElementById('unsure-count'),
  foreignCount: document.getElementById('foreign-count'),
  foreignToggle: document.getElementById('foreign-toggle'),
};

init();

async function init() {
  try {
    const resp = await fetch('../jobs.json', { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    countLocations(data.jobs || []);
    els.status.textContent = `${state.counts.size} locations`;
    bindEvents();
    render();
  } catch (err) {
    els.status.classList.replace('success', 'error');
    els.status.textContent = 'Failed to load jobs.json';
    console.error(err);
  }
}

function countLocations(jobs) {
  for (const job of jobs) {
    const locs = (job.locations && job.locations.length) ? job.locations : [job.location];
    for (const loc of locs.filter(Boolean)) {
      state.counts.set(loc, (state.counts.get(loc) || 0) + 1);
    }
  }
}

function bindEvents() {
  els.search.addEventListener('input', () => {
    state.search = els.search.value.trim().toLowerCase();
    render();
  });
  els.foreignToggle.addEventListener('click', () => {
    state.showForeign = !state.showForeign;
    els.foreignGrid.hidden = !state.showForeign;
    els.foreignToggle.textContent = state.showForeign ? 'Hide' : 'Show';
    render();
  });
}

function toggleHidden(loc) {
  state.hidden.has(loc) ? state.hidden.delete(loc) : state.hidden.add(loc);
  setHiddenLocations(state.hidden);
  render();
}

function toggleKept(loc) {
  state.kept.has(loc) ? state.kept.delete(loc) : state.kept.add(loc);
  setKeptLocations(state.kept);
  render();
}

function sortedEntries(bucket) {
  return [...state.counts.entries()]
    .filter(([loc]) => classifyLocation(loc) === bucket
      && loc.toLowerCase().includes(state.search))
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

function card(loc, count, variant, { hidden = false, action = null } = {}) {
  const el = document.createElement('div');
  el.className = `loc-card ${variant}` + (hidden ? ' is-hidden' : '');

  const name = document.createElement('span');
  name.className = 'loc-name';
  name.textContent = loc;
  name.title = loc;

  const meta = document.createElement('span');
  meta.className = 'loc-count';
  meta.textContent = count;

  el.append(name, meta);

  if (action) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = action.className;
    btn.textContent = action.label;
    btn.addEventListener('click', action.onClick);
    el.append(btn);
  } else {
    const badge = document.createElement('span');
    badge.className = 'loc-badge good';
    badge.textContent = 'Safe';
    el.append(badge);
  }
  return el;
}

function render() {
  const good = sortedEntries('good');
  const unsure = sortedEntries('unsure');
  const foreign = sortedEntries('foreign');

  els.goodCount.textContent = good.length;
  els.unsureCount.textContent = unsure.length;
  els.foreignCount.textContent = foreign.length;

  // Good: protected, no hide button.
  els.goodGrid.replaceChildren(...good.map(([loc, n]) => card(loc, n, 'good')));

  // Unsure: hide / show toggle.
  els.unsureGrid.replaceChildren(...unsure.map(([loc, n]) => {
    const isHidden = state.hidden.has(loc);
    return card(loc, n, 'unsure', {
      hidden: isHidden,
      action: {
        label: isHidden ? 'Show' : 'Hide',
        className: isHidden ? 'btn-secondary btn-mini' : 'btn-primary btn-mini',
        onClick: () => toggleHidden(loc),
      },
    });
  }));

  // Foreign: auto-hidden; "Rescue" re-adds to the dashboard.
  if (state.showForeign) {
    els.foreignGrid.replaceChildren(...foreign.map(([loc, n]) => {
      const isKept = state.kept.has(loc);
      return card(loc, n, 'foreign', {
        hidden: !isKept,
        action: {
          label: isKept ? 'Hide' : 'Rescue',
          className: isKept ? 'btn-secondary btn-mini' : 'btn-primary btn-mini',
          onClick: () => toggleKept(loc),
        },
      });
    }));
  }
}
