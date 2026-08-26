/* Dashboard display preferences, persisted in the browser's localStorage.
 *
 * These are view-only: hidden locations declutter the website for THIS browser
 * and never touch the scraper or Discord notifications (those are gated by
 * config.json on the backend). Shared by the dashboard (app.js) and /admin.
 */

const HIDDEN_LOCATIONS_KEY = 'jobmonitor.hiddenLocations';  // 'unsure' locations the user hid
const KEPT_LOCATIONS_KEY = 'jobmonitor.keptLocations';      // 'foreign' locations the user rescued

function loadSet(key) {
  try {
    return new Set(JSON.parse(localStorage.getItem(key)) || []);
  } catch {
    return new Set();
  }
}

function getHiddenLocations() {
  return loadSet(HIDDEN_LOCATIONS_KEY);
}

function setHiddenLocations(locations) {
  localStorage.setItem(HIDDEN_LOCATIONS_KEY, JSON.stringify([...locations]));
}

function getKeptLocations() {
  return loadSet(KEPT_LOCATIONS_KEY);
}

function setKeptLocations(locations) {
  localStorage.setItem(KEPT_LOCATIONS_KEY, JSON.stringify([...locations]));
}
