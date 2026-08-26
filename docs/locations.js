/* Location classifier — sorts a Workday location string into one of three buckets:
 *
 *   'foreign' — clearly another country (USA, UK, India, US states...). Auto-hidden.
 *   'good'    — clearly Quebec or Ontario. Always shown, protected in /admin.
 *   'unsure'  — everything else (other Canadian provinces, bare city/building
 *               names). Shown by default; user can hide individually in /admin.
 *
 * Foreign is checked FIRST so namesakes resolve correctly: "Ottawa, IL, USA" and
 * "Ontario, CA, USA" are foreign even though they contain Canadian-looking words.
 *
 * KEEP THE FOREIGN RULES IN SYNC with scraper/locations.py — the scraper uses a
 * Python port of the foreign branch to drop all-foreign jobs before writing
 * jobs.json. When you edit FOREIGN_SUBSTRINGS / FOREIGN_CODES / FOREIGN_WORD_TOKENS
 * here, mirror it there (and vice versa). A shared rules JSON is the future DRY fix.
 */

// Clearly Quebec / Ontario (substring, case-insensitive). Ambiguous cities
// (London, Windsor, Kingston, Waterloo…) are intentionally left out — they're
// caught by their "ON"/"QC" code token instead, or fall through to 'unsure'.
const QC_ON_SUBSTRINGS = [
  'quebec', 'québec', 'ontario',
  'montreal', 'montréal', 'toronto', 'ottawa', 'gatineau', 'laval', 'longueuil',
  'sherbrooke', 'terrebonne', 'brossard', 'boucherville', 'dorval',
  'mississauga', 'brampton', 'scarborough', 'etobicoke', 'north york',
  'vaughan', 'markham', 'oshawa', 'kanata', 'nepean', 'drummondville',
];
const QC_ON_CODES = new Set(['QC', 'ON']);

// Clearly foreign (substring, case-insensitive). Long, unambiguous strings only.
const FOREIGN_SUBSTRINGS = [
  // North America (non-Canada)
  'usa', 'u.s.a', 'u.s.', 'us-', 'united states', 'america',
  // US state names
  'alabama', 'alaska', 'arizona', 'arkansas', 'california', 'colorado',
  'connecticut', 'delaware', 'florida', 'georgia', 'hawaii', 'idaho',
  'illinois', 'indiana', 'iowa', 'kansas', 'kentucky', 'louisiana',
  'maryland', 'massachusetts', 'michigan', 'minnesota', 'mississippi',
  'missouri', 'montana', 'nebraska', 'nevada', 'new hampshire', 'new jersey',
  'new mexico', 'new york', 'north carolina', 'north dakota', 'ohio',
  'oklahoma', 'oregon', 'pennsylvania', 'rhode island', 'south carolina',
  'south dakota', 'tennessee', 'texas', 'utah', 'vermont', 'virginia',
  'washington', 'wisconsin', 'wyoming', 'district of columbia',
  // UK / Europe
  'united kingdom', 'england', 'scotland', 'wales', 'ireland', 'britain',
  'germany', 'berlin', 'munich', 'frankfurt', 'ratingen',
  'netherlands', 'amsterdam', 'schiphol', 'hengelo', 'rotterdam',
  'france', 'paris', 'toulouse', 'toulon', 'villebon', 'lyon',
  'belgium', 'brussels', 'tubize',
  'italy', 'roma', 'rome', 'milan', 'milano', 'sesto calende', 'torino',
  'spain', 'madrid', 'barcelona', 'portugal', 'lisbon',
  'poland', 'warsaw', 'krakow', 'czech', 'prague', 'praha',
  'hungary', 'budapest', 'serbia', 'belgrade', 'romania', 'bulgaria',
  'greece', 'athens', 'sweden', 'stockholm', 'norway', 'oslo',
  'denmark', 'copenhagen', 'finland', 'helsinki', 'switzerland', 'zurich',
  'geneva', 'austria', 'vienna', 'turkey', 'istanbul',
  // Asia / Pacific / ME / others
  'india', 'pakistan', 'bangladesh',
  'hong kong', 'shenzhen', 'shanghai', 'beijing', 'zhubei',
  'taiwan', 'taipei', 'japan', 'tokyo', 'yokohama', 'osaka',
  'singapore', 'malaysia', 'vietnam', 'hanoi', 'cambodia', 'pursat',
  'preah vihear', 'indonesia', 'jakarta', 'yogyakarta', 'philippines',
  'manila', 'makati', 'thailand', 'bangkok', 'seoul',
  'australia', 'sydney', 'melbourne', 'brisbane', 'perth', 'new zealand',
  'israel', 'tel aviv', 'dubai', 'abu dhabi', 'qatar', 'doha', 'kuwait',
  'egypt', 'cairo', 'morocco', 'casablanca', 'south africa', 'johannesburg',
  'nigeria', 'lagos', 'brazil', 'sao paulo', 'são paulo', 'mexico',
  'argentina', 'chile', 'colombia',
];

// Short / collision-prone foreign markers — matched as whole tokens only, so
// "China" hits but "Chinatown" doesn't, and "Maine" hits but "Domaine" doesn't.
const FOREIGN_WORD_TOKENS = new Set([
  'us', 'uk', 'china', 'maine', 'oman', 'iran', 'iraq', 'peru', 'cuba', 'fiji', 'mali',
]);

// US state + country codes — matched as whole tokens. None collide with the
// Canadian province codes (QC, ON, AB, BC, MB, SK, NS, NB, NL, PE, NU, YT, NT).
// Deliberately OMITTED:
//   DE / LA — collide with the French words "de"/"la" in Quebec addresses.
//   CA      — it's Canada's country code as well as California's. We never want to
//             lose a Canadian "…, CA" job, so we accept a few bare "City, CA"
//             California jobs slipping through (real California ones almost always
//             also say "California" or "USA", which still match FOREIGN_SUBSTRINGS).
// Those three states are still caught by their full names in FOREIGN_SUBSTRINGS.
const FOREIGN_CODES = new Set([
  'AL', 'AK', 'AZ', 'AR', 'CO', 'CT', 'FL', 'GA', 'HI', 'ID',
  'IL', 'IN', 'IA', 'KS', 'KY', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS',
  'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK',
  'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV',
  'WI', 'WY', 'DC',
]);

function locationTokens(loc) {
  return loc.split(/[\s,.\-()/]+/).filter(Boolean);
}

function classifyLocation(loc) {
  const lower = loc.toLowerCase();
  const tokens = locationTokens(loc);
  const upperTokens = tokens.map(t => t.toUpperCase());

  // 1. Foreign wins outright, so namesakes resolve correctly — "Burlington,
  //    Vermont", "Ottawa, IL" and "Ontario, CA, USA" are foreign even though
  //    they contain Canadian-looking words. (DE/LA are excluded from the codes
  //    above to avoid tripping on French "de"/"la".)
  if (FOREIGN_SUBSTRINGS.some(s => lower.includes(s))) return 'foreign';
  if (upperTokens.some(t => FOREIGN_CODES.has(t))) return 'foreign';
  if (tokens.some(t => FOREIGN_WORD_TOKENS.has(t.toLowerCase()))) return 'foreign';

  // 2. Clearly Quebec / Ontario.
  if (QC_ON_SUBSTRINGS.some(s => lower.includes(s))) return 'good';
  if (upperTokens.some(t => QC_ON_CODES.has(t))) return 'good';

  // 3. Everything else (other Canadian provinces, bare names).
  return 'unsure';
}
