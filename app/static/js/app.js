/* Nakladiak front-end. No framework, no build step. DOM is built with el() — never innerHTML
   with user data. Routes live in the hash so the PWA works from a single shell. */
(() => {
'use strict';

// ---------- tiny helpers ----------
const $ = (sel, root = document) => root.querySelector(sel);
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'style' && typeof v === 'object') { for (const [sk, sv] of Object.entries(v)) { if (sv == null) continue; if (sk.startsWith('--')) node.style.setProperty(sk, String(sv)); else node.style[sk] = sv; } }
    else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
    else if (k === 'dataset') Object.assign(node.dataset, v);
    else if (k === 'html') node.innerHTML = v; // only static SVG markup from ICONS
    else if (v === true) node.setAttribute(k, '');
    else node.setAttribute(k, v);
  }
  for (const c of children.flat(Infinity)) {
    if (c == null || c === false) continue;
    node.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return node;
}
const S_ = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">';
const ICONS = {
  home: S_ + '<path d="M3 11 12 3l9 8v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z"/></svg>',
  doc: S_ + '<path d="M6 2h8l5 5v15H6z"/><path d="M14 2v5h5M9 13h6M9 17h6"/></svg>',
  plus: S_.replace('stroke-width="2"', 'stroke-width="2.6"') + '<path d="M12 5v14M5 12h14"/></svg>',
  places: S_ + '<rect x="3" y="3" width="8" height="8" rx="2"/><rect x="13" y="3" width="8" height="18" rx="2"/><rect x="3" y="13" width="8" height="8" rx="2"/></svg>',
  gear: S_ + '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/></svg>',
  close: S_ + '<path d="M18 6 6 18M6 6l12 12"/></svg>',
  left: S_ + '<path d="m15 18-6-6 6-6"/></svg>',
  right: S_ + '<path d="m9 18 6-6-6-6"/></svg>',
  camera: S_ + '<path d="M4 8h3l2-3h6l2 3h3v12H4z"/><circle cx="12" cy="13" r="3.5"/></svg>',
  upload: S_ + '<path d="M12 16V4m0 0-4 4m4-4 4 4M4 20h16"/></svg>',
  check: S_ + '<path d="m5 12 5 5L20 7"/></svg>',
  trash: S_ + '<path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/></svg>',
  edit: S_ + '<path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>',
  refresh: S_ + '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5"/></svg>',
  bolt: S_ + '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/></svg>',
  mail: S_ + '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></svg>',
  bell: S_ + '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10 21h4"/></svg>',
  user: S_ + '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
  open: S_ + '<path d="M14 4h6v6M20 4l-9 9M19 14v6H4V5h6"/></svg>',
  info: S_ + '<circle cx="12" cy="12" r="10"/><path d="M12 16v-5M12 8h.01"/></svg>',
};
const svg = (name, cls) => el('span', { class: cls || 'ico', html: ICONS[name] });
const mount = (parent, ...nodes) => parent.replaceChildren(...nodes.flat(Infinity).filter((n) => n != null && n !== false));

const SK_MONTHS = ['január', 'február', 'marec', 'apríl', 'máj', 'jún', 'júl', 'august', 'september', 'október', 'november', 'december'];
const SK_MONTHS_GEN = ['januára', 'februára', 'marca', 'apríla', 'mája', 'júna', 'júla', 'augusta', 'septembra', 'októbra', 'novembra', 'decembra'];
const SK_MONTHS_LOC = ['januáru', 'februáru', 'marcu', 'aprílu', 'máju', 'júnu', 'júlu', 'augustu', 'septembru', 'októbru', 'novembru', 'decembru'];
const SK_DAYS_SHORT = ['Po', 'Ut', 'St', 'Št', 'Pi', 'So', 'Ne'];
const fmtEur = (x, dec = 2) => (x == null || isNaN(x)) ? '–' : Number(x).toFixed(dec).replace('.', ',').replace(/\B(?=(\d{3})+(?!\d))/g, ' ') + ' €';
const fmtNum = (x, dec = 1) => (x == null || isNaN(x)) ? '–' : Number(x).toFixed(dec).replace('.', ',');
const parseISO = (s) => { const [y, m, d] = String(s).slice(0, 10).split('-').map(Number); return new Date(y, m - 1, d); };
const fmtDate = (s) => { if (!s) return ''; const d = parseISO(s); return `${d.getDate()}. ${SK_MONTHS_GEN[d.getMonth()]}${d.getFullYear() !== new Date().getFullYear() ? ' ' + d.getFullYear() : ''}`; };
const fmtDateShort = (s) => { if (!s) return ''; const d = parseISO(s); return `${d.getDate()}. ${d.getMonth() + 1}.`; };
const fmtDT = (s) => { if (!s) return ''; const d = new Date(s); return `${d.getDate()}. ${d.getMonth() + 1}. ${d.getFullYear()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`; };
const fmtMonth = (ym) => { const [y, m] = ym.split('-').map(Number); return `${SK_MONTHS[m - 1][0].toUpperCase()}${SK_MONTHS[m - 1].slice(1)} ${y}`; };
const monthLoc = (ym) => SK_MONTHS_LOC[Number(ym.split('-')[1]) - 1];
const addMonths = (ym, n) => { let [y, m] = ym.split('-').map(Number); m += n; while (m > 12) { m -= 12; y++; } while (m < 1) { m += 12; y--; } return `${y}-${String(m).padStart(2, '0')}`; };
const plural = (n, a, b, c) => `${n} ${n === 1 ? a : (n >= 2 && n <= 4 ? b : c)}`;
const fmtBytes = (b) => b > 1e6 ? `${(b / 1e6).toFixed(1).replace('.', ',')} MB` : `${Math.round(b / 1e3)} kB`;

// ---------- API ----------
async function api(method, url, body) {
  const opts = { method, headers: { 'X-Requested-With': 'nakladiak', Accept: 'application/json' }, credentials: 'same-origin' };
  if (body instanceof FormData) opts.body = body;
  else if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  const r = await fetch(url, opts);
  if (r.status === 401) { location.href = '/login?next=' + encodeURIComponent('/' + location.hash); throw new Error('Nie si prihlásený.'); }
  let data = null;
  try { data = await r.json(); } catch { data = null; }
  if (!r.ok) throw new Error((data && data.detail) || `Chyba ${r.status}`);
  return data;
}
const GET = (u) => api('GET', u), POST = (u, b) => api('POST', u, b || {}), PUT = (u, b) => api('PUT', u, b), DEL = (u) => api('DELETE', u);

// ---------- state ----------
const S = { me: null, meta: null, month: new Date().toISOString().slice(0, 7) };
const STATUS = { new: ['čaká v rade', 'pill'], processing: ['číta sa', 'pill pill--run'], needs_review: ['čaká na potvrdenie', 'pill pill--warn'], done: ['hotovo', 'pill pill--ok'], error: ['chyba', 'pill pill--err'] };
const DOC_KIND = { faktura: 'Faktúra', uctenka: 'Účtenka', vypis: 'Výpis z účtu', ine: 'Iné', auto: 'Nerozhodnuté' };
const SOURCE = { upload: 'nahrané', mail: 'z mailu', connector: 'konektor' };
const FLAT = new Set(['internet', 'tv', 'mobil', 'poistenie', 'najom', 'odpad']);
const placeById = (id) => (S.me?.places || []).find((p) => p.id === id);
const kindLabel = (k) => (S.meta?.service_kinds.find((x) => x.id === k) || S.meta?.categories.find((x) => x.id === k) || { label: k }).label;
const catLabel = (k) => (S.meta?.categories.find((x) => x.id === k) || S.meta?.service_kinds.find((x) => x.id === k) || { label: k || 'Iné' }).label;

async function loadMe() {
  const [me, meta] = await Promise.all([GET('/api/me'), S.meta ? Promise.resolve(S.meta) : GET('/api/meta')]);
  S.me = me; S.meta = meta;
  renderNav();
}

// ---------- toast / sheet ----------
let toastT;
function toast(msg, isErr = false) {
  const t = $('#toast'); t.textContent = msg;
  t.className = 'toast is-on' + (isErr ? ' is-err' : '') + ($('#sheet-root').firstChild ? ' is-top' : '');
  clearTimeout(toastT); toastT = setTimeout(() => { t.className = 'toast'; }, isErr ? 4500 : 2600);
}
function openSheet(title, body, { onClose } = {}) {
  closeSheet();
  const sheet = el('div', { class: 'sheet', role: 'dialog', 'aria-modal': 'true', 'aria-label': title },
    el('div', { class: 'sheet__grip' }),
    el('div', { class: 'sheet__head' }, el('h2', {}, title), el('button', { class: 'iconbtn', 'aria-label': 'Zavrieť', onclick: closeSheet }, svg('close'))),
    body);
  const back = el('div', { class: 'sheet-backdrop', onclick: (e) => { if (e.target === back) closeSheet(); } }, sheet);
  back._onClose = onClose;
  $('#sheet-root').replaceChildren(back);
  document.body.style.overflow = 'hidden';
  setTimeout(() => sheet.querySelector('input:not([type=file]),textarea,select,button:not(.iconbtn)')?.focus?.({ preventScroll: true }), 50);
}
function closeSheet() {
  const b = $('#sheet-root').firstChild; if (!b) return;
  b._onClose?.(); $('#sheet-root').replaceChildren(); document.body.style.overflow = '';
}
function confirmSheet(title, text, okLabel, danger = false) {
  return new Promise((resolve) => {
    let done = false;
    openSheet(title, el('div', {}, el('p', { style: { marginBottom: '14px' } }, text), el('div', { class: 'row-btns' },
      el('button', { class: 'btn ' + (danger ? 'btn--danger' : 'btn--primary'), onclick: () => { done = true; closeSheet(); resolve(true); } }, okLabel),
      el('button', { class: 'btn btn--ghost', onclick: closeSheet }, 'Zrušiť'))), { onClose: () => { if (!done) resolve(false); } });
  });
}
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') return closeSheet();
  if (e.key !== 'Tab') return;
  const sheet = $('#sheet-root .sheet'); if (!sheet) return;
  const f = [...sheet.querySelectorAll('a[href],button,input,select,textarea,[tabindex]:not([tabindex="-1"])')].filter((n) => !n.disabled && n.offsetParent !== null);
  if (!f.length) return;
  const first = f[0], last = f[f.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  else if (!sheet.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
});

// ---------- form helpers ----------
const field = (label, input, help) => el('label', { class: 'field' }, el('span', {}, label), input, help ? el('small', { class: 'help' }, help) : null);
const input = (name, value = '', attrs = {}) => el('input', { name, value: value ?? '', ...attrs });
const select = (name, options, value, attrs = {}) => el('select', { name, ...attrs }, ...options.map((o) => el('option', { value: o.id, selected: String(o.id) === String(value ?? '') }, o.label)));
const check = (name, label, checked, help) => el('label', { class: 'check' }, el('input', { type: 'checkbox', name, checked: !!checked }), el('span', {}, label, help ? el('small', { class: 'help' }, help) : null));
function formData(form) {
  const out = {};
  for (const n of form.querySelectorAll('input,select,textarea')) {
    if (!n.name) continue;
    if (n.type === 'checkbox') out[n.name] = n.checked;
    else if (n.type === 'file') continue;
    else out[n.name] = n.value;
  }
  return out;
}
async function submitForm(form, fn, btn) {
  const b = btn || form.querySelector('button[type=submit]');
  if (b) b.disabled = true;
  try { await fn(formData(form)); } catch (e) { toast(e.message, true); } finally { if (b) b.disabled = false; }
}
const placeOptions = (empty = '— vyber miesto —') => [{ id: '', label: empty }, ...(S.me?.places || []).map((p) => ({ id: p.id, label: p.name }))];

// ---------- navigation ----------
const TABS = [
  ['#/', 'Prehľad', 'home', (h) => h === '#/' || h.startsWith('#/month')],
  ['#/documents', 'Dokumenty', 'doc', (h) => h.startsWith('#/documents') || h.startsWith('#/transactions')],
  ['#/upload', 'Nahrať účet', 'plus', (h) => h.startsWith('#/upload'), 'fab'],
  ['#/places', 'Miesta', 'places', (h) => h.startsWith('#/places') || h.startsWith('#/services')],
];
function renderNav() {
  const h = location.hash || '#/';
  const n = (S.me?.pending?.documents || 0) + (S.me?.pending?.transactions || 0);
  const badge = n ? el('span', { class: 'badge' }, n) : null;
  mount($('#tabbar'), TABS.map(([href, label, icon, act, extra]) => el('a', { href, class: (act(h) ? 'is-active ' : '') + (extra || ''), 'aria-label': label }, extra ? svg(icon) : null, el('span', { class: 'lbl' }, label), href === '#/documents' ? badge?.cloneNode(true) : null)));
  mount($('#nav-top'), TABS.filter(([, , , , extra]) => !extra).map(([href, label, , act]) => el('a', { href, class: act(h) ? 'is-active' : '' }, label, href === '#/documents' ? badge?.cloneNode(true) : null)),
    el('a', { href: '#/upload', class: h.startsWith('#/upload') ? 'is-active' : '' }, 'Nahrať účet'));
  if (S.me) mount($('#top-right'), el('button', { class: 'avatar', title: S.me.user.name + ' · profil a nastavenia', 'aria-label': 'Profil a nastavenia', onclick: openUserMenu }, (S.me.user.name || '?').trim().charAt(0).toUpperCase()));
}
function openUserMenu() {
  openSheet(S.me.user.name, el('div', {},
    el('p', { class: 'muted', style: { marginBottom: '14px' } }, '@' + S.me.user.username),
    el('a', { class: 'btn btn--block', href: '#/profile', onclick: closeSheet, style: { marginBottom: '8px' } }, svg('user'), 'Profil'),
    S.me.user.is_admin ? el('a', { class: 'btn btn--block', href: '#/settings', onclick: closeSheet, style: { marginBottom: '8px' } }, svg('gear'), 'Nastavenia') : null,
    el('a', { class: 'btn btn--block', href: '#/about', onclick: closeSheet, style: { marginBottom: '8px' } }, svg('info'), 'O appke'),
    el('form', { method: 'post', action: '/logout', style: { marginTop: '10px' } }, el('button', { class: 'btn btn--ghost btn--block', type: 'submit' }, 'Odhlásiť sa'))));
}

const routes = [
  [/^#\/?$/, () => renderDashboard(S.month)],
  [/^#\/month\/(\d{4}-\d{2})$/, (m) => renderDashboard(m[1])],
  [/^#\/upload$/, () => renderUpload()],
  [/^#\/documents\/?$/, () => renderDocuments('open')],
  [/^#\/documents\/all$/, () => renderDocuments('all')],
  [/^#\/documents\/(\d+)$/, (m) => renderDocument(Number(m[1]))],
  [/^#\/transactions$/, () => renderTransactions()],
  [/^#\/places\/?$/, () => renderPlaces()],
  [/^#\/places\/(\d+)$/, (m) => renderPlace(Number(m[1]))],
  [/^#\/services\/(\d+)$/, (m) => renderService(Number(m[1]))],
  [/^#\/settings\/?$/, () => renderSettings('reading')],
  [/^#\/settings\/(\w+)$/, (m) => renderSettings(m[1])],
  [/^#\/profile$/, () => renderProfile()],
  [/^#\/about$/, () => renderAbout()],
];
async function route() {
  const h = location.hash || '#/';
  closeSheet();
  renderNav();
  const main = $('#main');
  for (const [re, fn] of routes) {
    const m = h.match(re);
    if (m) {
      mount(main, el('div', { class: 'skel' }), el('div', { class: 'skel' }));
      try { await fn(m); } catch (e) { mount(main, el('div', { class: 'alert alert--err', style: { marginTop: '16px' } }, e.message)); }
      window.scrollTo(0, 0);
      return;
    }
  }
  location.hash = '#/';
}
window.addEventListener('hashchange', route);

// ---------- Prehľad ----------
async function renderDashboard(month) {
  S.month = month;
  const d = await GET('/api/dashboard?month=' + month);
  const main = $('#main');
  const prev = d.history.length >= 2 ? d.history[d.history.length - 2] : null;
  const byInvoice = Math.max(0, d.total - d.estimated);
  const nPlaces = d.places.length;
  const sentence = [];
  const WORDS = { 1: 'Jedna domácnosť', 2: 'Dve domácnosti', 3: 'Tri domácnosti', 4: 'Štyri domácnosti' };
  if (nPlaces) sentence.push((WORDS[nPlaces] || plural(nPlaces, 'domácnosť', 'domácnosti', 'domácností')) + '. ');
  if (d.total > 0) {
    sentence.push(el('span', {}, 'Podľa faktúr a platieb ', el('b', {}, fmtEur(byInvoice)), d.estimated > 0 ? [', odhad ', d.is_current ? 'do konca mesiaca ' : '', 'ďalších ', el('b', {}, fmtEur(d.estimated))] : null, '.'));
    if (prev && prev.total > 0) { const pct = Math.round((d.total / prev.total - 1) * 100); sentence.push(` Oproti ${monthLoc(prev.month)} o ${Math.abs(pct)} % ${pct <= 0 ? 'menej' : 'viac'}.`); }
  } else if (nPlaces) sentence.push(' Zatiaľ žiadne náklady v tomto mesiaci.');
  const pend = d.pending;
  const todo = [
    pend.documents ? el('a', { class: 'chip', href: '#/documents' }, `${plural(pend.documents, 'dokument čaká', 'dokumenty čakajú', 'dokumentov čaká')} na potvrdenie`) : null,
    pend.transactions ? el('a', { class: 'chip chip--soft', href: '#/transactions' }, `${plural(pend.transactions, 'platba', 'platby', 'platieb')} na zaradenie`) : null,
    pend.processing ? el('span', { class: 'chip chip--soft' }, el('span', { class: 'pill pill--run', style: { padding: 0, background: 'transparent' } }), `${plural(pend.processing, 'dokument sa číta', 'dokumenty sa čítajú', 'dokumentov sa číta')}`) : null,
    pend.errors ? el('a', { class: 'chip chip--warn', href: '#/documents' }, `${plural(pend.errors, 'dokument sa nedá', 'dokumenty sa nedajú', 'dokumentov sa nedá')} prečítať`) : null,
    !S.me.claude_ready && S.me.user.is_admin ? el('a', { class: 'chip chip--warn', href: '#/settings/reading' }, 'Nastav kľúč Claude API, inak sa dokumenty nečítajú') : null,
  ];
  const maxH = Math.max(1, ...d.history.map((h) => h.total));
  mount(main,
    el('div', { class: 'monthnav' },
      el('button', { 'aria-label': 'Predošlý mesiac', onclick: () => { location.hash = '#/month/' + addMonths(month, -1); } }, '‹'),
      el('span', { class: 'lbl' }, fmtMonth(month)),
      el('button', { 'aria-label': 'Ďalší mesiac', onclick: () => { location.hash = '#/month/' + addMonths(month, 1); } }, '›'),
      month !== new Date().toISOString().slice(0, 7) ? el('a', { href: '#/', class: 'btn btn--sm btn--ghost' }, 'Dnes') : null),
    el('section', { class: 'hero' },
      el('div', {},
        el('h1', { class: 'num' }, fmtEur(d.total).replace(' €', ''), el('small', {}, '€')),
        el('p', {}, ...sentence)),
      todo.some(Boolean) ? el('div', { class: 'todo' }, ...todo) : null),
    d.history.some((h) => h.total > 0) ? el('div', {},
      el('div', { class: 'hist' }, ...d.history.map((h) => el('button', { class: h.month === month ? 'is-on' : '', title: `${fmtMonth(h.month)}: ${fmtEur(h.total)}`, 'aria-label': `${fmtMonth(h.month)}: ${fmtEur(h.total)}`, style: { height: Math.max(6, Math.round(h.total / maxH * 100)) + '%' }, onclick: () => { location.hash = '#/month/' + h.month; } }))),
      el('div', { class: 'hist-l' }, ...d.history.map((h) => el('span', {}, h.label)))) : null,
    nPlaces ? el('section', { class: 'houses' }, ...d.places.map(houseNode)) :
      el('div', { class: 'empty', style: { marginTop: '16px' } }, el('p', {}, 'Zatiaľ tu nie je žiadne miesto. Začni bytom alebo domom, potom k nemu pridaj služby a nahraj prvý účet.'), el('a', { class: 'btn btn--primary', href: '#/places' }, 'Pridať prvé miesto')),
    d.due.length ? el('section', { class: 'section' }, el('h2', {}, 'Splatné'), el('div', { class: 'card' }, el('ul', { class: 'rows' }, ...d.due.map((i) =>
      el('a', { href: '#/documents/' + i.document_id },
        el('span', { class: 'k' }, `${i.supplier || 'faktúra'}${i.service ? ' · ' + i.service : ''}${i.place ? ' · ' + i.place : ''}`, el('span', { class: 's' + (i.overdue ? ' pill--err' : '') , style: i.overdue ? { color: 'var(--err)' } : null }, i.overdue ? `po splatnosti (${fmtDate(i.due_at)})` : `do ${fmtDate(i.due_at)}`)),
        el('span', { class: 'v' }, fmtEur(i.amount))))))) : null,
  );
}
function houseNode(p) {
  const metered = p.services.filter((s) => s.month && s.month.days);
  const noteParts = [];
  const nInv = p.services.filter((s) => s.source === 'faktura').length, nEst = p.services.filter((s) => s.source === 'odhad').length;
  if (metered.length) { const m = metered[0]; noteParts.push(`${fmtNum(m.month.value, 0)} ${m.unit || 'kWh'} tento mesiac, ${fmtNum(m.week.value, 0)} za týždeň`); }
  else if (nInv || nEst) noteParts.push([nInv ? plural(nInv, 'faktúra', 'faktúry', 'faktúr') : null, nEst ? plural(nEst, 'odhad', 'odhady', 'odhadov') : null].filter(Boolean).join(', '));
  else if (!p.services.length) noteParts.push('zatiaľ bez služieb');
  else noteParts.push('tento mesiac bez účtov');
  const spark = metered.length && metered[0].days ? (() => {
    const vals = metered[0].days; const mx = Math.max(1, ...vals.map((x) => x.value || 0));
    return el('div', { class: 'spark', title: 'spotreba za posledných 14 dní' }, ...vals.map((x) => el('i', { class: x.value == null ? 'none' : '', style: { height: x.value == null ? '20%' : Math.max(8, Math.round(x.value / mx * 100)) + '%' }, title: `${fmtDateShort(x.date)} ${x.value == null ? 'bez dát' : fmtNum(x.value) + ' kWh'}` })));
  })() : null;
  const rows = [
    ...p.services.map((s) => el('a', { class: 'row', href: '#/services/' + s.id },
      el('span', { class: 'k' }, s.label, el('small', {}, [s.supplier, s.name && s.name !== s.supplier ? s.name : null, s.source === 'odhad' ? (s.how === 'zaloha' ? (FLAT.has(s.kind) ? 'paušál' : 'záloha') : 'odhad') : null].filter(Boolean).join(' · ')),
        s.source === 'odhad' && s.consumption != null ? el('span', { class: 'sub' }, `${fmtNum(s.consumption, 0)} ${s.unit}${s.how === 'bez_ceny' ? ' · doplň cenu za jednotku' : ''}`) : null),
      s.amount != null ? el('span', { class: 'v' + (s.source === 'odhad' ? ' est' : '') }, fmtEur(s.amount)) : el('span', { class: 'v none' }, s.source === 'odhad' ? 'bez ceny' : 'bez faktúry'))),
    ...p.other.map((c) => el('a', { class: 'row', href: c.document_id ? '#/documents/' + c.document_id : '#/places/' + p.id },
      el('span', { class: 'k' }, c.label, el('small', {}, [c.counterparty, c.kind === 'prevod' ? 'prevod' : c.kind === 'uctenka' ? 'účtenka' : null].filter(Boolean).join(' · '))),
      el('span', { class: 'v' }, fmtEur(c.amount)))),
  ];
  return el('article', { class: 'house', style: { '--c': p.color } },
    el('a', { class: 'house__h', href: '#/places/' + p.id }, el('h2', {}, p.name), null),
    el('div', { class: 'big' }, fmtEur(p.total).replace(' €', ''), el('small', {}, ' €')),
    el('div', { class: 'note' }, noteParts.join(' · ')),
    spark,
    rows.length ? el('div', { class: 'list' }, ...rows) : el('div', { class: 'list' }, el('a', { class: 'row', href: '#/places/' + p.id }, el('span', { class: 'k muted' }, 'Pridaj elektrinu, plyn, vodu, internet…'), el('span', { class: 'v' }, '+'))));
}

// ---------- Nahrať ----------
function renderUpload() {
  const main = $('#main');
  const fileIn = el('input', { type: 'file', accept: 'application/pdf,image/*', multiple: true, id: 'file-in' });
  const camIn = el('input', { type: 'file', accept: 'image/*', capture: 'environment', id: 'cam-in' });
  const kind = select('kind', S.meta.doc_kinds, 'auto');
  const place = select('place_id', placeOptions('— appka určí sama —'), '');
  const hint = el('textarea', { name: 'hint', placeholder: 'napr. „účtenka za kosačku, dom v Belej“ (nepovinné)' });
  const results = el('div', { class: 'section' });
  const drop = el('div', { class: 'drop' },
    svg('upload', 'ico'),
    el('p', {}, 'Pretiahni sem PDF alebo fotku, alebo vyber súbor. Faktúry, účtenky aj výpisy z účtu.'),
    el('div', { class: 'btns' },
      el('button', { class: 'btn btn--primary', type: 'button', onclick: () => fileIn.click() }, svg('doc'), 'Vybrať súbor'),
      el('button', { class: 'btn', type: 'button', onclick: () => camIn.click() }, svg('camera'), 'Odfotiť')),
    fileIn, camIn);
  const onFiles = (files) => { for (const f of files) uploadOne(f, formData(form), results); };
  fileIn.addEventListener('change', () => { onFiles([...fileIn.files]); fileIn.value = ''; });
  camIn.addEventListener('change', () => { onFiles([...camIn.files]); camIn.value = ''; });
  ['dragenter', 'dragover'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('is-over'); }));
  ['dragleave', 'drop'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove('is-over'); }));
  drop.addEventListener('drop', (e) => onFiles([...e.dataTransfer.files]));
  const form = el('form', { onsubmit: (e) => e.preventDefault() },
    el('div', { class: 'grid2' }, field('Čo to je', kind, 'Nechaj na appku, rozpozná faktúru, účtenku aj výpis.'), field('Miesto', place, 'Len ak to appka nevie určiť z dokumentu.')),
    field('Poznámka pre čítanie', hint));
  mount(main,
    el('div', { class: 'page-h' }, el('h1', {}, 'Nahrať účet'), S.me.mailbox_ready ? el('span', { class: 'pill pill--ok' }, 'schránka beží') : null),
    !S.me.claude_ready ? el('div', { class: 'alert alert--err' }, 'Čítanie dokumentov potrebuje kľúč Claude API. ', S.me.user.is_admin ? el('a', { href: '#/settings/reading' }, 'Nastaviť') : 'Napíš adminovi.') : null,
    drop, form, results,
    el('p', { class: 'sub', style: { marginTop: '16px' } }, 'Tip: maily od dodávateľov presmeruj do schránky appky a účty sa nahrajú samy. ', S.me.user.is_admin ? el('a', { href: '#/settings/mailbox' }, 'Nastavenia schránky') : null));
}
async function uploadOne(file, opts, results) {
  const card = el('div', { class: 'file-prev' }, file.type.startsWith('image/') ? el('img', { src: URL.createObjectURL(file), alt: '' }) : svg('doc', 'ico'),
    el('div', { style: { flex: 1, minWidth: 0 } }, el('div', { style: { fontWeight: 700 } }, file.name), el('div', { class: 'muted', style: { fontSize: '13px' } }, `${fmtBytes(file.size)} · nahráva sa`), el('div', { class: 'progress' }, el('i'))));
  results.prepend(card);
  const fd = new FormData();
  fd.append('file', file, file.name); fd.append('kind', opts.kind || 'auto'); fd.append('hint', opts.hint || ''); fd.append('place_id', opts.place_id || '');
  try {
    const r = await POST('/api/documents', fd);
    if (r.duplicate) { mount(card, svg('info', 'ico'), el('div', {}, el('b', {}, 'Tento súbor už máš.'), ' ', el('a', { href: '#/documents/' + r.document.id }, 'Otvoriť'))); return; }
    const d = await pollDocument(r.document.id, (doc) => { card.querySelector('.muted').textContent = `${fmtBytes(file.size)} · ${STATUS[doc.status][0]}`; });
    mount(card, docCard(d, true));
    loadMe();
  } catch (e) { mount(card, el('div', { class: 'alert alert--err', style: { margin: 0 } }, e.message)); }
}
async function pollDocument(id, onTick) {
  for (let i = 0; i < 90; i++) {
    const d = await GET('/api/documents/' + id);
    onTick?.(d);
    if (['done', 'needs_review', 'error'].includes(d.status)) return d;
    await new Promise((r) => setTimeout(r, i < 10 ? 1500 : 3000));
  }
  return GET('/api/documents/' + id);
}

// ---------- Dokumenty ----------
function docCard(d, wide = false) {
  const [lbl, cls] = STATUS[d.status] || [d.status, 'pill'];
  const place = placeById(d.place_id);
  return el('a', { class: 'doc', href: '#/documents/' + d.id, style: wide ? { width: '100%' } : null },
    svg(d.mime === 'application/pdf' ? 'doc' : 'camera', 'ico'),
    el('div', { style: { minWidth: 0, flex: 1 } },
      el('div', { class: 't' }, d.summary || d.filename),
      el('div', { class: 'm' }, [DOC_KIND[d.doc_kind || d.kind] !== 'Nerozhodnuté' ? DOC_KIND[d.doc_kind || d.kind] : null, place?.name, fmtDT(d.received_at), SOURCE[d.source]].filter(Boolean).join(' · ')),
      d.status === 'error' ? el('div', { class: 'm', style: { color: 'var(--err)' } }, d.error) : null),
    el('span', { class: cls + ' st' }, lbl));
}
async function renderDocuments(filter) {
  const r = await GET('/api/documents?status=' + (filter === 'open' ? 'open' : '') + '&limit=100');
  const docs = r.documents;
  const pend = S.me.pending;
  mount($('#main'),
    el('div', { class: 'page-h' }, el('h1', {}, 'Dokumenty'), el('div', { class: 'actions' }, el('a', { class: 'btn btn--accent btn--sm', href: '#/upload' }, svg('plus'), 'Nahrať'))),
    el('div', { class: 'tabs' },
      el('a', { href: '#/documents', class: filter === 'open' ? 'is-on' : '' }, 'Otvorené'),
      el('a', { href: '#/documents/all', class: filter === 'all' ? 'is-on' : '' }, 'Všetky'),
      el('a', { href: '#/transactions', class: '' }, 'Platby na zaradenie', pend.transactions ? el('span', { class: 'badge', style: { marginLeft: '6px' } }, pend.transactions) : null)),
    docs.length ? el('div', {}, ...docs.map((d) => docCard(d))) :
      el('div', { class: 'empty' }, el('p', {}, filter === 'open' ? 'Nič nečaká. Všetky dokumenty sú spracované.' : 'Zatiaľ žiadny dokument.'), el('a', { class: 'btn btn--primary', href: '#/upload' }, 'Nahrať prvý účet')));
}
async function renderDocument(id) {
  let d = await GET('/api/documents/' + id);
  const main = $('#main');
  const draw = () => {
    const [lbl, cls] = STATUS[d.status] || [d.status, 'pill'];
    const data = d.data || {};
    const inv = d.invoice;
    const facts = [];
    if (data.supplier) facts.push(['Dodávateľ', data.supplier]);
    if (inv) {
      facts.push(['Typ', { vyuctovanie: 'Vyúčtovanie', zalohova: 'Zálohový predpis', pravidelna: 'Pravidelná faktúra', dobropis: 'Dobropis', ine: 'Faktúra' }[inv.kind] || 'Faktúra']);
      if (inv.number) facts.push(['Číslo', inv.number]);
      if (inv.period_from || inv.period_to) facts.push(['Obdobie', `${fmtDate(inv.period_from)} – ${fmtDate(inv.period_to)}`]);
      facts.push(['Suma', fmtEur(inv.total) + (inv.to_pay != null && inv.to_pay !== inv.total ? ` (na úhradu ${fmtEur(inv.to_pay)})` : '')]);
      if (inv.consumption != null) facts.push(['Spotreba', `${fmtNum(inv.consumption, 1)} ${inv.unit || ''}${inv.unit_price ? ` · ${fmtNum(inv.unit_price, 4)} €/${inv.unit || 'j.'}` : ''}`]);
      if (inv.due_at) facts.push(['Splatnosť', fmtDate(inv.due_at) + (inv.paid_at ? ` · zaplatená ${fmtDate(inv.paid_at)}` : ' · nezaplatená')]);
      if (inv.variable_symbol) facts.push(['VS', inv.variable_symbol]);
    }
    if (data.receipt) { facts.push(['Obchod', data.receipt.merchant || '–']); facts.push(['Dátum', fmtDate(data.receipt.date)]); facts.push(['Suma', fmtEur(data.receipt.total)]); }
    if (data.statement) { facts.push(['Účet', data.statement.account_iban || '–']); facts.push(['Obdobie', `${fmtDate(data.statement.period_from)} – ${fmtDate(data.statement.period_to)}`]); facts.push(['Platby', String((d.transactions || []).length)]); }
    if (data.identifiers?.length) facts.push(['Identifikátory', data.identifiers.map((i) => `${i.kind}: ${i.value}`).join(', ')]);
    const place = placeById(d.place_id);
    const svc = d.service_id;
    mount(main,
      el('div', { class: 'page-h' }, el('div', {}, el('h1', {}, d.summary || d.filename), el('div', { class: 'sub' }, [d.filename, fmtBytes(d.size), SOURCE[d.source], d.mail_from ? `od ${d.mail_from}` : null, fmtDT(d.received_at)].filter(Boolean).join(' · '))), el('span', { class: cls }, lbl)),
      d.status === 'error' ? el('div', { class: 'alert alert--err' }, d.error, d.attempts >= 4 ? ' Skúsi sa znova len na požiadanie.' : ' Skúsi sa znova automaticky.') : null,
      d.status === 'needs_review' ? el('div', { class: 'card' }, el('h3', { style: { marginBottom: '8px' } }, 'Kam to patrí?'), el('p', { class: 'sub', style: { marginBottom: '10px' } }, data.doc_kind === 'faktura' ? 'Appka si nie je istá, ktorej službe faktúra patrí. Vyber ju a nabudúce to už bude vedieť.' : data.doc_kind === 'uctenka' ? 'Vyber miesto a kategóriu. Rovnaký obchod nabudúce zaradí sama.' : 'Povedz appke, čo to je a kam to patrí.'), reviewForm(d, (nd) => { d = nd; draw(); loadMe(); })) : null,
      facts.length ? el('div', { class: 'card', style: { marginTop: '10px' } }, el('dl', { class: 'kv' }, ...facts.map(([k, v]) => [el('dt', {}, k), el('dd', {}, v)]))) : null,
      d.status === 'done' ? el('div', { class: 'card', style: { marginTop: '10px' } },
        el('dl', { class: 'kv' },
          el('dt', {}, 'Miesto'), el('dd', {}, place ? el('a', { href: '#/places/' + place.id }, place.name) : '–'),
          svc ? [el('dt', {}, 'Služba'), el('dd', {}, el('a', { href: '#/services/' + svc }, 'otvoriť službu'))] : null,
          d.costs?.length ? [el('dt', {}, 'Do nákladov'), el('dd', {}, d.costs.map((c) => `${fmtEur(c.amount)} (${catLabel(c.category)}, ${fmtDate(c.date)})`).join(', '))] : null,
          d.match_how ? [el('dt', {}, 'Priradené'), el('dd', {}, { identifier: 'podľa identifikátora', rule: 'podľa naučeného pravidla', supplier: 'podľa dodávateľa', model: 'odhadom z dokumentu' }[d.match_how] || d.match_how)] : null),
        el('div', { class: 'row-btns' },
          (data.doc_kind === 'faktura' || data.doc_kind === 'uctenka' || data.doc_kind === 'ine') ? el('button', { class: 'btn btn--sm', onclick: () => openSheet('Zmeniť priradenie', reviewForm(d, (nd) => { closeSheet(); d = nd; draw(); loadMe(); })) }, svg('edit'), 'Zmeniť priradenie') : null,
          inv ? el('button', { class: 'btn btn--sm', onclick: async () => { try { d.invoice = await POST(`/api/invoices/${inv.id}/paid`, { paid: !inv.paid_at }); toast(inv.paid_at ? 'Faktúra označená ako nezaplatená' : 'Faktúra označená ako zaplatená'); draw(); } catch (e) { toast(e.message, true); } } }, svg('check'), inv.paid_at ? 'Označiť ako nezaplatenú' : 'Označiť ako zaplatenú') : null)) : null,
      d.transactions?.length ? el('section', { class: 'section' }, el('h2', {}, 'Platby z výpisu'), el('div', { class: 'card' }, ...d.transactions.map((t) => txNode(t, () => renderDocument(id))))) : null,
      el('section', { class: 'section' }, el('h2', {}, 'Súbor'),
        d.mime.startsWith('image/') ? el('div', { class: 'preview' }, el('img', { src: `/api/documents/${d.id}/file`, alt: d.filename, loading: 'lazy' })) : null,
        el('div', { class: 'row-btns' },
          el('a', { class: 'btn btn--sm', href: `/api/documents/${d.id}/file`, target: '_blank', rel: 'noopener' }, svg('open'), 'Otvoriť súbor'),
          el('button', { class: 'btn btn--sm', onclick: () => openSheet('Prečítať znova', reprocessForm(d)) }, svg('refresh'), 'Prečítať znova'),
          el('button', { class: 'btn btn--sm btn--danger', onclick: async () => { if (await confirmSheet('Zmazať dokument?', 'Zmaže sa súbor aj náklady, ktoré z neho vznikli. Platby z výpisu sa dajú nahrať znova.', 'Zmazať', true)) { await DEL('/api/documents/' + d.id); toast('Dokument zmazaný'); location.hash = '#/documents'; } } }, svg('trash'), 'Zmazať'))));
  };
  draw();
  if (['new', 'processing'].includes(d.status) || (d.status === 'error' && d.attempts < 4)) {
    pollDocument(id, (nd) => { if (nd.status !== d.status) { d = nd; draw(); } }).then((nd) => { d = nd; draw(); loadMe(); });
  }
}
function reviewForm(d, onDone) {
  const data = d.data || {};
  const kindSel = select('kind', [{ id: 'faktura', label: 'Faktúra / vyúčtovanie' }, { id: 'uctenka', label: 'Účtenka' }, { id: 'vypis', label: 'Výpis z účtu' }, { id: 'ine', label: 'Iné (bez nákladu)' }], data.doc_kind || 'ine');
  const placeSel = select('place_id', placeOptions(), d.place_id || d.suggested_place_id || '');
  const svcSel = select('service_id', [{ id: '', label: '— bez služby —' }], d.service_id || d.suggested_service_id || '');
  const catSel = select('category', [{ id: '', label: '— kategória —' }, ...S.meta.categories], (data.receipt && data.receipt.category_hint) || '');
  const remember = check('remember', 'Zapamätať si to', true, 'Nabudúce rovnaký dodávateľ alebo obchod pôjde bez pýtania.');
  const svcWrap = field('Služba', svcSel, 'Pri faktúre povinné: elektrina, plyn, voda… na danom mieste.');
  const catWrap = field('Kategória', catSel);
  async function fillServices() {
    const pid = placeSel.value;
    let opts = [{ id: '', label: '— bez služby —' }];
    if (pid) { const p = (await GET('/api/places/' + pid)); opts = opts.concat(p.services.filter((s) => s.active).map((s) => ({ id: s.id, label: `${s.kind_label}${s.supplier ? ' · ' + s.supplier : ''}${s.label ? ' (' + s.label + ')' : ''}` }))); }
    const cur = svcSel.value || d.suggested_service_id || '';
    mount(svcSel, ...opts.map((o) => el('option', { value: o.id, selected: String(o.id) === String(cur) }, o.label)));
  }
  const refresh = () => { const k = kindSel.value; svcWrap.hidden = !(k === 'faktura' || k === 'uctenka'); catWrap.hidden = k !== 'uctenka' && k !== 'ine'; };
  kindSel.addEventListener('change', refresh); placeSel.addEventListener('change', fillServices);
  if (d.suggested_service_id && !placeSel.value) { /* service suggests the place */ }
  refresh(); fillServices();
  const form = el('form', { onsubmit: (e) => { e.preventDefault(); submitForm(form, async (v) => { const nd = await POST(`/api/documents/${d.id}/review`, { kind: v.kind, place_id: v.place_id || null, service_id: v.service_id || null, category: v.category || '', remember: v.remember }); toast('Priradené'); onDone(nd); }); } },
    field('Čo to je', kindSel), field('Miesto', placeSel), svcWrap, catWrap, remember,
    el('div', { class: 'row-btns' }, el('button', { class: 'btn btn--primary', type: 'submit' }, svg('check'), 'Potvrdiť')));
  if (d.suggested_service_id && d.match_confidence) form.prepend(el('div', { class: 'alert' }, `Návrh appky: istota ${Math.round(d.match_confidence * 100)} %. Skontroluj a potvrď.`));
  return form;
}
function reprocessForm(d) {
  const form = el('form', { onsubmit: (e) => { e.preventDefault(); submitForm(form, async (v) => { await POST(`/api/documents/${d.id}/reprocess`, { hint: v.hint }); closeSheet(); toast('Dokument sa číta znova'); renderDocument(d.id); }); } },
    el('p', { class: 'sub', style: { marginBottom: '10px' } }, 'Dokument sa pošle na prečítanie znova. Poznámka pomôže, keď niečo chýba (napr. ktoré miesto, že je to záloha a nie vyúčtovanie).'),
    field('Poznámka pre čítanie', el('textarea', { name: 'hint' }, d.review_note || '')),
    el('div', { class: 'row-btns' }, el('button', { class: 'btn btn--primary', type: 'submit' }, 'Prečítať znova'), el('button', { class: 'btn btn--ghost', type: 'button', onclick: closeSheet }, 'Zrušiť')));
  return form;
}

// ---------- Platby ----------
function txNode(t, onChange) {
  const st = { pending: ['na zaradenie', 'pill pill--warn'], assigned: ['zaradená', 'pill pill--ok'], invoice: ['platba faktúry', 'pill pill--ok'], ignored: ['ignorovaná', 'pill'] }[t.status] || [t.status, 'pill'];
  return el('div', { class: 'tx' },
    el('div', {}, el('div', { class: 'who' }, t.counterparty || t.note || 'bez názvu'), el('div', { class: 'm' }, [fmtDate(t.date), t.note && t.counterparty ? t.note : null, t.variable_symbol ? 'VS ' + t.variable_symbol : null].filter(Boolean).join(' · '))),
    el('div', { class: 'amt' }, fmtEur(t.amount), el('div', {}, el('span', { class: st[1] }, st[0]))),
    t.status === 'pending' ? el('div', { class: 'act' },
      el('button', { class: 'btn btn--sm btn--primary', onclick: () => openSheet('Zaradiť platbu', assignForm(t, onChange)) }, 'Zaradiť'),
      el('button', { class: 'btn btn--sm btn--ghost', onclick: async () => { try { await POST(`/api/transactions/${t.id}/assign`, { ignore: true, remember: true }); toast('Platba sa bude ignorovať'); onChange(); } catch (e) { toast(e.message, true); } } }, 'Ignorovať')) : null);
}
function assignForm(t, onDone) {
  const placeSel = select('place_id', placeOptions(), '');
  const svcSel = select('service_id', [{ id: '', label: '— bez služby —' }], '');
  const catSel = select('category', S.meta.categories, 'udrzba');
  placeSel.addEventListener('change', async () => {
    const pid = placeSel.value; let opts = [{ id: '', label: '— bez služby —' }];
    if (pid) { const p = await GET('/api/places/' + pid); opts = opts.concat(p.services.filter((s) => s.active).map((s) => ({ id: s.id, label: `${s.kind_label}${s.supplier ? ' · ' + s.supplier : ''}` }))); }
    mount(svcSel, ...opts.map((o) => el('option', { value: o.id }, o.label)));
  });
  const form = el('form', { onsubmit: (e) => { e.preventDefault(); submitForm(form, async (v) => { await POST(`/api/transactions/${t.id}/assign`, { place_id: v.place_id || null, service_id: v.service_id || null, category: v.category, label: v.label, remember: v.remember }); closeSheet(); toast('Platba zaradená'); onDone(); loadMe(); }); } },
    el('div', { class: 'card', style: { marginBottom: '12px' } }, el('b', {}, t.counterparty || t.note), el('div', { class: 'sub' }, `${fmtEur(t.amount)} · ${fmtDate(t.date)}${t.counterparty_iban ? ' · ' + t.counterparty_iban : ''}`)),
    field('Miesto', placeSel), field('Služba (nepovinné)', svcSel, 'Ak je to platba za službu, ktorú už sleduješ cez faktúry, appka ju nebude počítať dvakrát.'),
    field('Kategória', catSel), field('Pomenovanie', input('label', t.counterparty || '', { placeholder: 'napr. Peter, kosenie' })),
    check('remember', 'Zapamätať si to', true, 'Ďalšie platby tejto protistrane (podľa IBAN alebo názvu) sa zaradia samy.'),
    el('div', { class: 'row-btns' }, el('button', { class: 'btn btn--primary', type: 'submit' }, svg('check'), 'Zaradiť'), el('button', { class: 'btn btn--ghost', type: 'button', onclick: closeSheet }, 'Zrušiť')));
  return form;
}
async function renderTransactions() {
  const r = await GET('/api/transactions?status=pending');
  mount($('#main'),
    el('div', { class: 'page-h' }, el('h1', {}, 'Platby na zaradenie'), el('a', { class: 'btn btn--sm', href: '#/documents' }, 'Dokumenty')),
    el('p', { class: 'sub', style: { marginBottom: '12px' } }, 'Platby z výpisov, ktoré appka nevedela priradiť k faktúre ani k naučenému pravidlu. Zaraď ich raz, ďalšie od rovnakej protistrany pôjdu samy.'),
    r.transactions.length ? el('div', { class: 'card' }, ...r.transactions.map((t) => txNode(t, renderTransactions))) :
      el('div', { class: 'empty' }, el('p', {}, 'Všetky platby sú zaradené.'), el('a', { class: 'btn btn--primary', href: '#/upload' }, 'Nahrať výpis z účtu')));
}

// ---------- Miesta ----------
async function renderPlaces() {
  const r = await GET('/api/places');
  mount($('#main'),
    el('div', { class: 'page-h' }, el('h1', {}, 'Miesta'), el('button', { class: 'btn btn--primary btn--sm', onclick: () => openSheet('Nové miesto', placeForm(null, () => { closeSheet(); loadMe().then(renderPlaces); })) }, svg('plus'), 'Pridať miesto')),
    r.places.length ? el('section', { class: 'houses' }, ...r.places.map((p) => el('article', { class: 'house', style: { '--c': p.color } },
      el('a', { class: 'house__h', href: '#/places/' + p.id }, el('h2', {}, p.name), el('span', { class: 'note' }, p.kind_label)),
      el('div', { class: 'note' }, p.address || ''),
      el('div', { class: 'list' }, ...(p.services.length ? p.services.map((s) => el('a', { class: 'row', href: '#/services/' + s.id }, el('span', { class: 'k' }, s.kind_label, el('small', {}, [s.supplier, s.label].filter(Boolean).join(' · '))), el('span', { class: 'v' }, s.connector ? el('span', { class: 'pill' }, 'ZSD') : s.monthly_estimate ? fmtEur(s.monthly_estimate) + '/mes.' : '')))
        : [el('a', { class: 'row', href: '#/places/' + p.id }, el('span', { class: 'k muted' }, 'Zatiaľ bez služieb'), el('span', { class: 'v' }, '+'))]))))) :
      el('div', { class: 'empty' }, el('p', {}, 'Miesto je byt, dom alebo chalupa. Ku každému patria služby: elektrina, plyn, voda, internet…'), el('button', { class: 'btn btn--primary', onclick: () => openSheet('Nové miesto', placeForm(null, () => { closeSheet(); loadMe().then(renderPlaces); })) }, 'Pridať prvé miesto')));
}
function placeForm(p, onDone) {
  const colors = ['#3461a8', '#2f7d4f', '#b5572a', '#7a4f9e', '#b3822a', '#2a8a8a', '#8a3a5a'];
  const form = el('form', { onsubmit: (e) => { e.preventDefault(); submitForm(form, async (v) => { const body = { name: v.name, kind: v.kind, address: v.address, color: v.color }; if (p) { if ('archived' in v) body.archived = v.archived; await PUT('/api/places/' + p.id, body); } else await POST('/api/places', body); toast(p ? 'Miesto upravené' : 'Miesto pridané'); onDone(); }); } },
    field('Názov', input('name', p?.name || '', { required: true, placeholder: 'napr. Dom v Belej', maxlength: 60 })),
    el('div', { class: 'grid2' }, field('Typ', select('kind', S.meta.place_kinds, p?.kind || 'byt')), field('Farba', select('color', colors.map((c) => ({ id: c, label: c })), p?.color || colors[(S.me.places || []).length % colors.length]))),
    field('Adresa', input('address', p?.address || '', { placeholder: 'pomáha pri priraďovaní faktúr' })),
    p ? check('archived', 'Archivovať miesto', !!p.archived, 'Zmizne z prehľadu, dáta ostanú.') : null,
    el('div', { class: 'row-btns' }, el('button', { class: 'btn btn--primary', type: 'submit' }, p ? 'Uložiť' : 'Pridať'), el('button', { class: 'btn btn--ghost', type: 'button', onclick: closeSheet }, 'Zrušiť')));
  const colorSel = form.querySelector('select[name=color]');
  const sw = el('span', { class: 'dot', style: { '--c': colorSel.value, marginLeft: '8px', width: '18px', height: '18px' } });
  colorSel.parentNode.querySelector('span').append(sw);
  colorSel.addEventListener('change', () => sw.style.setProperty('--c', colorSel.value));
  return form;
}
async function renderPlace(id) {
  const p = await GET('/api/places/' + id);
  const maxM = Math.max(1, ...p.months.map((m) => m.total));
  mount($('#main'),
    el('div', { class: 'page-h' }, el('div', {}, el('h1', {}, el('span', { class: 'dot', style: { '--c': p.color, marginRight: '8px', width: '16px', height: '16px' } }), p.name), el('div', { class: 'sub' }, [p.kind_label, p.address].filter(Boolean).join(' · '))),
      el('div', { class: 'actions' }, el('button', { class: 'btn btn--sm', onclick: () => openSheet('Upraviť miesto', placeForm(p, () => { closeSheet(); loadMe().then(() => renderPlace(id)); })) }, svg('edit'), 'Upraviť'))),
    el('div', { class: 'cols2' },
      el('div', {},
        el('section', { class: 'section', style: { marginTop: 0 } }, el('h2', {}, 'Služby', el('button', { class: 'btn btn--sm btn--primary', onclick: () => openSheet('Nová služba', serviceForm(id, null, () => { closeSheet(); renderPlace(id); })) }, svg('plus'), 'Pridať')),
          p.services.length ? el('div', { class: 'card' }, el('ul', { class: 'rows' }, ...p.services.map((s) => el('a', { href: '#/services/' + s.id },
            el('span', { class: 'k' }, s.kind_label, el('span', { class: 's' }, [s.supplier, s.label, s.identifier, s.connector ? 'ZSD dáta' : null, s.active ? null : 'neaktívna'].filter(Boolean).join(' · '))),
            el('span', { class: 'v' }, s.monthly_estimate ? fmtEur(s.monthly_estimate) : (s.unit_price ? `${fmtNum(s.unit_price, 3)} €/${s.unit}` : ''), el('span', { class: 's' }, s.monthly_estimate ? 'mesačne' : (s.unit_price ? 'cena za jednotku' : ''))))))) :
            el('div', { class: 'empty' }, el('p', {}, 'Pridaj elektrinu, plyn, vodu, internet… Pri každej dodávateľa a číslo odberného miesta (EIC, POD), aby sa faktúry priraďovali samy.'))),
        el('section', { class: 'section' }, el('h2', {}, 'Náklady za 12 mesiacov'),
          el('div', { class: 'card' },
            el('div', { class: 'months' }, ...p.months.map((m) => el('a', { href: '#/month/' + m.month, title: `${fmtMonth(m.month)}: ${fmtEur(m.by_place[String(id)] || 0)}`, class: m.month === S.month ? 'is-on' : '', style: { height: Math.max(4, Math.round((m.by_place[String(id)] || 0) / Math.max(1, ...p.months.map((x) => x.by_place[String(id)] || 0)) * 100)) + '%' } }))),
            el('div', { class: 'hist-l' }, ...p.months.map((m) => el('span', {}, m.label)))))),
      el('div', {},
        el('section', { class: 'section', style: { marginTop: 0 } }, el('h2', {}, 'Posledné výdavky', el('button', { class: 'btn btn--sm', onclick: () => openSheet('Výdavok ručne', costForm(p, () => { closeSheet(); renderPlace(id); })) }, svg('plus'), 'Ručne')),
          p.costs.length ? el('div', { class: 'card' }, el('ul', { class: 'rows' }, ...p.costs.slice(0, 30).map((c) => el('li', {},
            el('span', { class: 'k' }, catLabel(c.category), el('span', { class: 's' }, [c.counterparty, { faktura: 'faktúra', uctenka: 'účtenka', prevod: 'prevod', rucne: 'ručne' }[c.kind], fmtDate(c.date)].filter(Boolean).join(' · '))),
            el('span', { class: 'v' }, fmtEur(c.amount), c.kind === 'rucne' ? el('button', { class: 'iconbtn', style: { width: '32px', height: '32px' }, 'aria-label': 'Zmazať', onclick: async () => { if (await confirmSheet('Zmazať výdavok?', `${catLabel(c.category)} ${fmtEur(c.amount)}`, 'Zmazať', true)) { await DEL('/api/costs/' + c.id); renderPlace(id); } } }, svg('trash')) : null))))) :
            el('div', { class: 'empty' }, el('p', {}, 'Zatiaľ žiadne výdavky. Nahraj účet alebo pridaj výdavok ručne.'))),
        p.documents.length ? el('section', { class: 'section' }, el('h2', {}, 'Dokumenty'), ...p.documents.slice(0, 10).map((d) => docCard(d))) : null)));
}
function costForm(p, onDone) {
  const form = el('form', { onsubmit: (e) => { e.preventDefault(); submitForm(form, async (v) => { await POST('/api/costs', { place_id: p.id, service_id: v.service_id || null, amount: v.amount, category: v.category, date: v.date, counterparty: v.counterparty, note: v.note }); toast('Výdavok pridaný'); onDone(); }); } },
    el('div', { class: 'grid2' }, field('Suma (€)', input('amount', '', { inputmode: 'decimal', required: true, placeholder: '0,00' })), field('Dátum', input('date', new Date().toISOString().slice(0, 10), { type: 'date', required: true }))),
    field('Kategória', select('category', S.meta.categories, 'udrzba')),
    field('Služba (nepovinné)', select('service_id', [{ id: '', label: '— žiadna —' }, ...p.services.map((s) => ({ id: s.id, label: s.kind_label + (s.supplier ? ' · ' + s.supplier : '') }))], '')),
    field('Komu / čo', input('counterparty', '', { placeholder: 'napr. kominár' })), field('Poznámka', el('textarea', { name: 'note' })),
    el('div', { class: 'row-btns' }, el('button', { class: 'btn btn--primary', type: 'submit' }, 'Pridať'), el('button', { class: 'btn btn--ghost', type: 'button', onclick: closeSheet }, 'Zrušiť')));
  return form;
}
function serviceForm(placeId, s, onDone) {
  const zsd = S.meta.connectors.find((c) => c.id === 'zsd');
  const dps = zsd?.delivery_points || [];
  const connSel = select('connector', [{ id: '', label: 'žiadny (len faktúry)' }, { id: 'zsd', label: zsd?.label || 'ZSD diportal' }], s?.connector || '');
  const refIn = dps.length ? select('connector_ref', [{ id: '', label: '— vyber odberné miesto —' }, ...dps.map((d) => ({ id: d.id, label: `${d.eic || d.id}${d.address ? ' · ' + d.address : ''}` }))], s?.connector_ref || '') : input('connector_ref', s?.connector_ref || '', { placeholder: 'deliveryPointId z diportálu' });
  const ref2In = input('connector_ref2', s?.connector_ref2 || '', { placeholder: 'kód profilu alebo ID výrobného odberného miesta' });
  const connBox = el('div', {}, field('Odberné miesto na diportáli', refIn, dps.length ? 'Zoznam sa naplní po prvom spustení ZSD v Nastaveniach → Zdroje dát.' : 'Zoznam odberných miest sa objaví po prvom spustení ZSD (Nastavenia → Zdroje dát).'), field('Dodávka do siete (nepovinné)', ref2In, 'Len ak máš fotovoltiku. Nechaj prázdne, appka skúsi profil dodávky nájsť sama.'));
  const refreshConn = () => { connBox.hidden = connSel.value !== 'zsd'; };
  connSel.addEventListener('change', refreshConn); refreshConn();
  const form = el('form', { onsubmit: (e) => { e.preventDefault(); submitForm(form, async (v) => { const body = { ...v, place_id: placeId, active: s ? v.active : true }; if (s) await PUT('/api/services/' + s.id, body); else await POST('/api/services', body); toast(s ? 'Služba upravená' : 'Služba pridaná'); onDone(); }); } },
    el('div', { class: 'grid2' }, field('Druh', select('kind', S.meta.service_kinds, s?.kind || 'elektrina')), field('Dodávateľ', input('supplier', s?.supplier || '', { placeholder: 'ZSE, SPP, ZsVS, O2…' }))),
    field('Pomenovanie (nepovinné)', input('label', s?.label || '', { placeholder: 'napr. garáž, 2. elektromer' })),
    el('div', { class: 'grid2' }, field('Identifikátor', input('identifier', s?.identifier || '', { placeholder: 'EIC, POD, číslo zmluvy' }), 'Z faktúry. Podľa neho sa faktúry priradia samy.'), field('Druhý identifikátor', input('identifier2', s?.identifier2 || '', { placeholder: 'číslo zákazníka, telefón' }))),
    el('div', { class: 'grid2' }, field('Jednotka', input('unit', s?.unit || '', { placeholder: 'kWh, m3, GB' })), field('Cena za jednotku (€)', input('unit_price', s?.unit_price ?? '', { inputmode: 'decimal', placeholder: 'napr. 0,21' }), 'Doplní sa z faktúry.')),
    el('div', { class: 'grid2' }, field('Fixný mesačný poplatok (€)', input('fixed_monthly', s?.fixed_monthly ?? '', { inputmode: 'decimal' })), field('Mesačná záloha / paušál (€)', input('monthly_estimate', s?.monthly_estimate ?? '', { inputmode: 'decimal' }), 'Odhad, keď v mesiaci nie je faktúra.')),
    field('Zdroj dát', connSel), connBox,
    field('Poznámka', el('textarea', { name: 'note' }, s?.note || '')),
    s ? check('active', 'Aktívna služba', !!s.active, 'Neaktívna sa nezobrazuje v prehľade, história ostane.') : null,
    el('div', { class: 'row-btns' }, el('button', { class: 'btn btn--primary', type: 'submit' }, s ? 'Uložiť' : 'Pridať'), el('button', { class: 'btn btn--ghost', type: 'button', onclick: closeSheet }, 'Zrušiť')));
  return form;
}
async function renderService(id) {
  const s = await GET('/api/services/' + id);
  const place = placeById(s.place_id) || { name: '', color: '#888' };
  const days = s.readings.slice(-60);
  const mx = Math.max(1, ...days.map((d) => Math.max(d.consumption || 0, d.generation || 0)));
  mount($('#main'),
    el('div', { class: 'page-h' }, el('div', {}, el('h1', {}, s.kind_label, s.label ? ` · ${s.label}` : ''), el('div', { class: 'sub' }, [el('a', { href: '#/places/' + s.place_id }, place.name), s.supplier, s.identifier, s.active ? null : 'neaktívna'].filter(Boolean).flatMap((x, i) => i ? [' · ', x] : [x]))),
      el('div', { class: 'actions' },
        el('button', { class: 'btn btn--sm', onclick: () => openSheet('Upraviť službu', serviceForm(s.place_id, s, () => { closeSheet(); renderService(id); })) }, svg('edit'), 'Upraviť'),
        el('button', { class: 'btn btn--sm btn--danger', onclick: async () => { if (await confirmSheet('Odstrániť službu?', 'Ak už má faktúry alebo náklady, len sa deaktivuje.', 'Odstrániť', true)) { const r = await DEL('/api/services/' + id); toast(r.deactivated ? 'Služba deaktivovaná' : 'Služba odstránená'); location.hash = '#/places/' + s.place_id; } } }, svg('trash')))),
    el('div', { class: 'cols2' },
      el('div', {},
        s.estimate || s.week?.days ? el('div', { class: 'card' },
          el('dl', { class: 'kv' },
            s.week?.days ? [el('dt', {}, 'Tento týždeň'), el('dd', {}, `${fmtNum(s.week.value)} ${s.unit || 'kWh'} (${plural(s.week.days, 'deň', 'dni', 'dní')} s dátami)`)] : null,
            s.estimate ? [el('dt', {}, 'Tento mesiac'), el('dd', {}, s.estimate.consumption != null ? `${fmtNum(s.estimate.consumption, 0)} ${s.estimate.unit}` : '–', s.estimate.amount != null ? ` · odhad ${fmtEur(s.estimate.amount)}` : s.estimate.how === 'bez_ceny' ? ' · doplň cenu za jednotku pre odhad v €' : '')] : null,
            s.unit_price ? [el('dt', {}, 'Cena'), el('dd', {}, `${fmtNum(s.unit_price, 4)} €/${s.unit}${s.fixed_monthly ? ` + ${fmtEur(s.fixed_monthly)} mesačne` : ''}`)] : null)) : null,
        s.connector ? el('section', { class: 'section' }, el('h2', {}, 'Spotreba po dňoch'),
          el('div', { class: 'card', style: { '--c': place.color } },
            days.length ? [el('div', { class: 'bars' }, ...days.map((d) => el('div', { class: 'b' + (d.consumption == null ? ' none' : ''), title: `${fmtDate(d.date)}: ${fmtNum(d.consumption)} ${s.unit || 'kWh'}${d.generation != null ? ` · dodávka ${fmtNum(d.generation)}` : ''}` },
                el('i', { style: { height: Math.max(2, Math.round((d.consumption || 0) / mx * 100)) + '%' } }),
                d.generation != null ? el('i', { class: 'gen', style: { height: Math.max(1, Math.round(d.generation / mx * 100)) + '%' } }) : null))),
              el('div', { class: 'bars-l' }, ...days.map((d, i) => el('span', {}, i % 7 === 0 ? fmtDateShort(d.date) : ''))),
              el('div', { class: 'legend' }, el('span', {}, el('i'), 'odber'), days.some((d) => d.generation != null) ? el('span', {}, el('i', { class: 'gen' }), 'dodávka do siete') : null)]
              : el('p', { class: 'muted' }, 'Zatiaľ žiadne dáta. Spustia sa po nastavení ZSD (Nastavenia → Zdroje dát) a prvom stiahnutí.'))) : null,
        s.monthly_readings.length ? el('section', { class: 'section' }, el('h2', {}, 'Po mesiacoch'), el('div', { class: 'card' }, el('ul', { class: 'rows' }, ...Object.values(s.monthly_readings.reduce((acc, r) => { (acc[r.ym] = acc[r.ym] || { ym: r.ym }); acc[r.ym][r.kind] = r.v; acc[r.ym].n = r.n; return acc; }, {})).reverse().map((m) =>
          el('li', {}, el('span', { class: 'k' }, fmtMonth(m.ym), el('span', { class: 's' }, plural(m.n, 'deň', 'dni', 'dní'))), el('span', { class: 'v' }, `${fmtNum(m.consumption, 0)} ${s.unit || 'kWh'}`, m.generation ? el('span', { class: 's' }, `dodávka ${fmtNum(m.generation, 0)}`) : null)))))) : null),
      el('div', {},
        el('section', { class: 'section', style: { marginTop: 0 } }, el('h2', {}, 'Faktúry'),
          s.invoices.length ? el('div', { class: 'card' }, el('ul', { class: 'rows' }, ...s.invoices.map((i) => el('a', { href: '#/documents/' + i.document_id },
            el('span', { class: 'k' }, `${{ vyuctovanie: 'Vyúčtovanie', zalohova: 'Zálohový predpis', pravidelna: 'Faktúra', dobropis: 'Dobropis', ine: 'Faktúra' }[i.kind] || 'Faktúra'}${i.number ? ' ' + i.number : ''}`, el('span', { class: 's' }, [i.period_from ? `${fmtDate(i.period_from)} – ${fmtDate(i.period_to)}` : fmtDate(i.issued_at), i.consumption != null ? `${fmtNum(i.consumption, 0)} ${i.unit}` : null].filter(Boolean).join(' · '))),
            el('span', { class: 'v' }, fmtEur(i.total), el('span', { class: 's' }, i.paid_at ? 'zaplatená' : i.due_at ? `do ${fmtDateShort(i.due_at)}` : '')))))) :
            el('div', { class: 'empty' }, el('p', {}, 'Zatiaľ žiadna faktúra. Nahraj ju alebo presmeruj maily od dodávateľa do schránky appky.'), el('a', { class: 'btn btn--primary', href: '#/upload' }, 'Nahrať faktúru'))),
        s.costs.length ? el('section', { class: 'section' }, el('h2', {}, 'Náklady'), el('div', { class: 'card' }, el('ul', { class: 'rows' }, ...s.costs.slice(0, 24).map((c) => el('li', {}, el('span', { class: 'k' }, fmtDate(c.date), el('span', { class: 's' }, [c.counterparty, { faktura: 'faktúra', uctenka: 'účtenka', prevod: 'prevod', rucne: 'ručne' }[c.kind]].filter(Boolean).join(' · '))), el('span', { class: 'v' }, fmtEur(c.amount))))))) : null)));
}

// ---------- Nastavenia ----------
const SETTINGS_TABS = [['reading', 'Čítanie'], ['mailbox', 'Schránka'], ['sources', 'Zdroje dát'], ['rules', 'Pravidlá'], ['users', 'Používatelia'], ['mail', 'E-mail'], ['notify', 'Notifikácie'], ['history', 'História'], ['about', 'O appke']];
async function renderSettings(tab) {
  if (!S.me.user.is_admin) { location.hash = '#/profile'; return; }
  const main = $('#main');
  const body = el('div');
  mount(main, el('div', { class: 'page-h' }, el('h1', {}, 'Nastavenia')), el('div', { class: 'tabs' }, ...SETTINGS_TABS.map(([id, label]) => el('a', { href: '#/settings/' + id, class: id === tab ? 'is-on' : '' }, label))), body);
  const fn = { reading: settingsReading, mailbox: settingsMailbox, sources: settingsSources, rules: settingsRules, users: settingsUsers, mail: settingsMail, notify: settingsNotify, history: settingsHistory, about: aboutBody }[tab] || settingsReading;
  mount(body, el('div', { class: 'skel' }));
  mount(body, await fn());
}
function secretField(label, key, st, help) {
  const v = st.settings[key];
  return field(label, input(key, '', { type: 'password', autocomplete: 'off', placeholder: v.set ? 'nastavené · zadaj nové, ak chceš zmeniť' : 'nenastavené' }), help);
}
function settingsForm(st, fieldsNode, onSaved) {
  const form = el('form', { onsubmit: (e) => { e.preventDefault(); submitForm(form, async (v) => { const body = {}; for (const [k, val] of Object.entries(v)) body[k] = typeof val === 'boolean' ? (val ? '1' : '0') : val; await PUT('/api/settings', body); toast('Uložené'); onSaved?.(); }); } },
    fieldsNode, el('div', { class: 'row-btns' }, el('button', { class: 'btn btn--primary', type: 'submit' }, 'Uložiť')));
  return form;
}
async function testBtn(label, what, extra) {
  const b = el('button', { class: 'btn btn--sm', type: 'button' }, label);
  b.addEventListener('click', async () => { b.disabled = true; try { const r = await POST('/api/settings/test', { what, ...(extra?.() || {}) }); toast(r.message); } catch (e) { toast(e.message, true); } finally { b.disabled = false; } });
  return b;
}
async function settingsReading() {
  const st = await GET('/api/settings');
  return el('div', {},
    el('p', { class: 'sub', style: { marginBottom: '12px' } }, 'Dokumenty číta Claude API. Kľúč získaš na console.anthropic.com. Jedno prečítanie faktúry stojí zvyčajne pár centov.'),
    settingsForm(st, el('div', {},
      secretField('Kľúč Claude API', 'anthropic_api_key', st),
      field('Model', input('claude_model', st.settings.claude_model.value), 'Default claude-sonnet-5-5. Pri zložitých dokumentoch skús claude-opus-5-5.'),
      field('Pripomienka na výpis z účtu (dni)', input('statement_reminder_days', st.settings.statement_reminder_days.value, { inputmode: 'numeric' }), '0 = vypnuté. Pripomienka príde na ntfy, keď od posledného výpisu uplynie viac dní.')), () => loadMe()),
    el('div', { class: 'row-btns' }, await testBtn('Otestovať spojenie', 'claude')));
}
async function settingsMailbox() {
  const st = await GET('/api/settings');
  const sv = st.settings;
  return el('div', {},
    el('p', { class: 'sub', style: { marginBottom: '12px' } }, 'Vyhradená schránka na účty (IMAP). Appka ju číta každých 15 minút, prílohy PDF a fotky spracuje a správu označí ako prečítanú. Maily od dodávateľov si do nej presmeruj.'),
    st.status.imap_last_error ? el('div', { class: 'alert alert--err' }, 'Posledná chyba: ' + st.status.imap_last_error) : st.status.imap_last_ok ? el('div', { class: 'alert alert--ok' }, 'Naposledy prečítané ' + fmtDT(st.status.imap_last_ok)) : null,
    settingsForm(st, el('div', {},
      el('div', { class: 'grid2' }, field('IMAP server', input('imap_host', sv.imap_host.value, { placeholder: 'imap.m1.websupport.sk' })), field('Port', input('imap_port', sv.imap_port.value, { inputmode: 'numeric' }), '993 = SSL')),
      field('Prihlasovacie meno', input('imap_user', sv.imap_user.value, { placeholder: 'uctenky@gordulic.sk' })),
      secretField('Heslo', 'imap_password', st),
      field('Priečinok', input('imap_folder', sv.imap_folder.value)),
      check('imap_enabled', 'Čítať schránku automaticky', sv.imap_enabled.value === '1', 'Každých 15 minút. Ak vypneš, dá sa spustiť ručne tlačidlom.')), () => loadMe()),
    el('div', { class: 'row-btns' }, await testBtn('Otestovať prihlásenie', 'imap'),
      el('button', { class: 'btn btn--sm', onclick: async (e) => { e.target.disabled = true; try { const r = await POST('/api/mailbox/poll'); toast(r.message); } catch (err) { toast(err.message, true); } finally { e.target.disabled = false; } } }, svg('refresh'), 'Prečítať schránku teraz')));
}
async function settingsSources() {
  const [st, cs] = await Promise.all([GET('/api/settings'), GET('/api/connectors/status')]);
  const sv = st.settings;
  const last = cs.zsd.last_run;
  return el('div', {},
    el('h3', { style: { marginBottom: '6px' } }, 'ZSD diportal.sk'),
    el('p', { class: 'sub', style: { marginBottom: '12px' } }, '15-minútové dáta elektriny (odber aj dodávka do siete) pre všetky odberné miesta jedného konta. Prihlásenie chráni reCAPTCHA, rieši ju služba 2captcha.com. Po prvom stiahnutí sa pri službách objaví zoznam odberných miest na priradenie.'),
    last ? el('div', { class: last.ok ? 'alert alert--ok' : 'alert alert--err' }, `${fmtDT(last.started_at)}: ${last.message}${last.finished_at ? '' : ' (beží)'}`) : null,
    settingsForm(st, el('div', {},
      el('div', { class: 'grid2' }, field('Prihlasovacie meno', input('zsd_user', sv.zsd_user.value)), secretField('Heslo', 'zsd_password', st)),
      el('div', { class: 'grid2' }, field('Business partner ID', input('zsd_business_partner_id', sv.zsd_business_partner_id.value), 'Rovnaké ako v spotreba_bela (.env).'), secretField('2captcha API kľúč', 'twocaptcha_api_key', st)),
      el('div', { class: 'grid2' }, field('Čas denného sťahovania', input('zsd_time', sv.zsd_time.value, { placeholder: '14:35' }), 'Dáta za včerajšok sú na portáli po 14:00.'), check('zsd_enabled', 'Sťahovať denne', sv.zsd_enabled.value === '1')))),
    el('div', { class: 'row-btns' },
      el('button', { class: 'btn btn--sm btn--primary', disabled: !cs.zsd.configured, onclick: async (e) => { e.target.disabled = true; try { const r = await POST('/api/connectors/zsd/run', { days: 8 }); toast(r.message); } catch (err) { toast(err.message, true); } finally { e.target.disabled = false; } } }, svg('bolt'), 'Stiahnuť teraz (8 dní)'),
      el('button', { class: 'btn btn--sm', disabled: !cs.zsd.configured, onclick: async (e) => { e.target.disabled = true; try { const r = await POST('/api/connectors/zsd/run', { days: 60 }); toast(r.message); } catch (err) { toast(err.message, true); } finally { e.target.disabled = false; } } }, 'Dotiahnuť 60 dní')),
    cs.zsd.delivery_points.length ? el('section', { class: 'section' }, el('h2', {}, `Odberné miesta na portáli (${cs.zsd.delivery_points.length})`), el('div', { class: 'card' }, el('ul', { class: 'rows' }, ...cs.zsd.delivery_points.map((d) => el('li', {}, el('span', { class: 'k' }, d.eic || d.id, el('span', { class: 's' }, [d.address, d.name, 'ID ' + d.id].filter(Boolean).join(' · '))))))), el('p', { class: 'sub', style: { marginTop: '8px' } }, `Priradené služby: ${cs.zsd.mapped}. Priradenie sa robí pri službe (Miesta → služba → Upraviť → Zdroj dát).`)) : null,
    cs.runs.length ? el('section', { class: 'section' }, el('h2', {}, 'Posledné behy'), el('div', { class: 'card' }, el('ul', { class: 'rows' }, ...cs.runs.slice(0, 10).map((r) => el('li', {}, el('span', { class: 'k' }, fmtDT(r.started_at), el('span', { class: 's' }, r.message || '…')), el('span', { class: r.ok == null ? 'pill pill--run' : r.ok ? 'pill pill--ok' : 'pill pill--err' }, r.ok == null ? 'beží' : r.ok ? 'ok' : 'chyba')))))) : null);
}
async function settingsRules() {
  const r = await GET('/api/rules');
  const KIND = { identifier: 'identifikátor', supplier: 'dodávateľ', merchant: 'obchod', iban: 'IBAN', counterparty: 'protistrana' };
  return el('div', {},
    el('p', { class: 'sub', style: { marginBottom: '12px' } }, 'Čo sa appka naučila z tvojich potvrdení. Zmaž pravidlo, ak zaraďuje zle; pri ďalšom dokumente sa opýta znova.'),
    r.rules.length ? el('div', { class: 'card' }, el('ul', { class: 'rows' }, ...r.rules.map((x) => el('li', {},
      el('span', { class: 'k' }, x.label || x.pattern, el('span', { class: 's' }, [KIND[x.match_kind] || x.match_kind, x.pattern !== x.label ? x.pattern : null, x.action === 'ignore' ? 'ignorovať' : [x.place_name, x.service_kind ? kindLabel(x.service_kind) : null, x.category ? catLabel(x.category) : null].filter(Boolean).join(' → '), `použité ${x.hits}×`].filter(Boolean).join(' · '))),
      el('button', { class: 'iconbtn', 'aria-label': 'Zmazať pravidlo', onclick: async () => { await DEL('/api/rules/' + x.id); toast('Pravidlo zmazané'); renderSettings('rules'); } }, svg('trash')))))) :
      el('div', { class: 'empty' }, el('p', {}, 'Zatiaľ žiadne pravidlá. Vzniknú, keď potvrdíš dokument alebo zaradíš platbu so zaškrtnutým „Zapamätať si to“.')));
}
async function settingsUsers() {
  const r = await GET('/api/users');
  const wrap = el('div');
  const draw = () => mount(wrap,
    el('div', { class: 'card' }, el('ul', { class: 'rows' }, ...r.users.map((u) => el('li', {},
      el('span', { class: 'k' }, u.name, el('span', { class: 's' }, [`@${u.username}`, u.email, u.is_admin ? 'administrátor' : null, !u.active ? 'deaktivovaný' : u.invited ? 'pozvaný, bez hesla' : u.last_login_at ? `naposledy ${fmtDT(u.last_login_at)}` : null].filter(Boolean).join(' · '))),
      el('button', { class: 'btn btn--sm', onclick: () => openSheet('Upraviť používateľa', userForm(u, async () => { closeSheet(); Object.assign(r, await GET('/api/users')); draw(); })) }, 'Upraviť'))))),
    el('div', { class: 'row-btns' }, el('button', { class: 'btn btn--primary btn--sm', onclick: () => openSheet('Pridať používateľa', userForm(null, async () => { closeSheet(); Object.assign(r, await GET('/api/users')); draw(); })) }, svg('plus'), 'Pridať')));
  draw();
  return wrap;
}
function userForm(u, onDone) {
  const modeSel = select('mode', [{ id: 'invite', label: 'Pozvať odkazom (e-mail s „Nastaviť heslo“)' }, { id: 'password', label: 'Nastaviť heslo hneď' }], 'invite');
  const pwBox = el('div', {}, field('Heslo (aspoň 8 znakov)', input('password', '', { type: 'password', autocomplete: 'new-password' })), check('must_change_password', 'Pri prvom prihlásení si heslo zmení', true));
  const refresh = () => { pwBox.hidden = !u && modeSel.value !== 'password'; };
  modeSel.addEventListener('change', refresh);
  const form = el('form', { onsubmit: (e) => { e.preventDefault(); submitForm(form, async (v) => {
    if (u) { const r = await PUT('/api/users/' + u.id, { name: v.name, email: v.email, is_admin: v.is_admin, active: v.active, password: v.password || undefined, must_change_password: v.must_change_password, send_invite: v.send_invite }); if (v.send_invite) toast(r.mail_sent ? 'Pozvánka odoslaná' : 'Mail sa nepodarilo poslať, skopíruj odkaz: ' + r.invite_url); else toast('Uložené'); }
    else { const r = await POST('/api/users', { username: v.username, name: v.name, email: v.email, is_admin: v.is_admin, mode: v.mode, password: v.password, must_change_password: v.must_change_password }); if (v.mode === 'invite') { if (r.mail_sent) toast('Pozvánka odoslaná'); else openSheet('Odkaz na nastavenie hesla', el('div', {}, el('p', { class: 'sub' }, 'Mail sa neposlal (SMTP nie je nastavené alebo zlyhal). Pošli odkaz sám, platí 7 dní:'), el('div', { class: 'card', style: { wordBreak: 'break-all', margin: '10px 0' } }, r.invite_url), el('button', { class: 'btn btn--primary', onclick: () => navigator.clipboard?.writeText(r.invite_url).then(() => toast('Skopírované')) }, 'Skopírovať odkaz'))); return; } else toast('Používateľ pridaný'); }
    onDone(); }); } },
    !u ? field('Prihlasovacie meno', input('username', '', { required: true, autocapitalize: 'none', pattern: '[a-z0-9._-]{2,40}' }), 'malé písmená, číslice, . _ -') : null,
    field('Meno', input('name', u?.name || '', { required: true })), field('E-mail', input('email', u?.email || '', { type: 'email' }), 'Povinný pri pozvánke odkazom.'),
    check('is_admin', 'Administrátor', !!u?.is_admin, 'Môže pridávať ľudí a meniť nastavenia.'),
    u ? check('active', 'Aktívny', !!u.active, 'Deaktivovaný sa nemôže prihlásiť; mazanie nie je.') : field('Ako dostane prístup', modeSel),
    u ? check('send_invite', 'Poslať nový odkaz na nastavenie hesla', false) : null,
    pwBox,
    el('div', { class: 'row-btns' }, el('button', { class: 'btn btn--primary', type: 'submit' }, u ? 'Uložiť' : 'Pridať'), el('button', { class: 'btn btn--ghost', type: 'button', onclick: closeSheet }, 'Zrušiť')));
  if (u) { pwBox.querySelector('label.field span').textContent = 'Nové heslo (nepovinné)'; pwBox.querySelector('input[name=password]').required = false; }
  refresh();
  return form;
}
async function settingsMail() {
  const st = await GET('/api/settings'); const sv = st.settings;
  return el('div', {},
    el('p', { class: 'sub', style: { marginBottom: '12px' } }, 'Odosielanie mailov: pozvánky, „Zabudol som heslo“ a upozornenia e-mailom (ak si ich v Profile zapneš). websupport: smtp.m1.websupport.sk, port 465, meno = celá adresa.'),
    settingsForm(st, el('div', {},
      el('div', { class: 'grid2' }, field('SMTP server', input('smtp_host', sv.smtp_host.value)), field('Port', input('smtp_port', sv.smtp_port.value, { inputmode: 'numeric' }))),
      el('div', { class: 'grid2' }, field('Prihlasovacie meno', input('smtp_user', sv.smtp_user.value)), secretField('Heslo', 'smtp_password', st)),
      el('div', { class: 'grid2' }, field('Odosielateľ', input('smtp_from', sv.smtp_from.value, { type: 'email' })), field('Meno odosielateľa', input('smtp_from_name', sv.smtp_from_name.value))))),
    el('div', { class: 'row-btns' }, await testBtn('Poslať skúšobný e-mail', 'smtp')));
}
async function settingsNotify() {
  const st = await GET('/api/settings'); const sv = st.settings;
  return el('div', {},
    el('p', { class: 'sub', style: { marginBottom: '12px' } }, 'Push notifikácie idú cez ntfy. Tému pre seba si nastavíš v Profile. Tu je server a téma pre chyby appky (rovnaká ako infra alerty niko1).'),
    settingsForm(st, el('div', {}, field('ntfy server', input('ntfy_server', sv.ntfy_server.value)), field('Téma pre chyby appky', input('alert_ntfy_topic', sv.alert_ntfy_topic.value), 'Spadnutý job, chyba 500, nestiahnuté ZSD. Prázdne = vypnuté.'))),
    el('div', { class: 'row-btns' }, await testBtn('Poslať skúšobnú notifikáciu', 'ntfy')));
}
async function settingsHistory(before) {
  const r = await GET('/api/history?limit=60' + (before ? '&before=' + before : ''));
  const wrap = el('div', {}, el('div', { class: 'card' }, el('ul', { class: 'rows' }, ...r.history.map((h) => el('li', {},
    el('span', { class: 'k' }, h.label, el('span', { class: 's' }, [fmtDT(h.at), h.user_name || 'systém', Object.entries(h.details || {}).filter(([k]) => !['ip'].includes(k)).map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).join(', ')].filter(Boolean).join(' · '))))))));
  if (r.history.length === 60) wrap.append(el('div', { class: 'row-btns' }, el('button', { class: 'btn btn--sm', onclick: async (e) => { const more = await settingsHistory(r.history[r.history.length - 1].id); e.target.replaceWith(more); } }, 'Staršie')));
  return wrap;
}
async function aboutBody() {
  const a = await GET('/api/about');
  const rel = (iso) => { if (!iso) return 'neznáme'; const days = Math.floor((Date.now() - new Date(iso)) / 864e5); return days === 0 ? 'dnes' : days === 1 ? 'včera' : `pred ${plural(days, 'dňom', 'dňami', 'dňami')}`; };
  return el('div', {},
    el('div', { class: 'card' }, el('dl', { class: 'kv' }, el('dt', {}, 'Nasadené'), el('dd', {}, rel(a.built_at), a.built_at ? ` (${fmtDT(a.built_at)})` : ''), el('dt', {}, 'Dokumenty'), el('dd', {}, `${a.documents} · ${fmtBytes(a.docs_bytes)}`), el('dt', {}, 'Databáza'), el('dd', {}, fmtBytes(a.db_bytes)), el('dt', {}, 'Model'), el('dd', {}, a.model))),
    el('section', { class: 'section' }, el('h2', {}, 'Čo je nové'), ...a.changes.map((c) => el('div', { class: 'card' }, el('h3', { style: { fontSize: '16px', marginBottom: '6px' } }, `${fmtDate(c.date)} · ${c.title}`), el('ul', { style: { margin: 0, paddingLeft: '18px' } }, ...c.items.map((it) => el('li', { style: { margin: '4px 0' } }, ...it.map((x) => typeof x === 'string' ? x : el('b', {}, x.b)))))))),
    el('section', { class: 'section' }, el('h2', {}, 'Ako to funguje'), el('div', { class: 'card' }, el('ul', { style: { margin: 0, paddingLeft: '18px', lineHeight: 1.5 } },
      el('li', {}, 'Nahraj faktúru, účtenku alebo výpis (PDF alebo fotka). Appka ich prečíta a priradí k miestu; keď si nie je istá, opýta sa raz.'),
      el('li', {}, 'Maily od dodávateľov presmeruj do schránky appky, účty sa potom nahrávajú samy.'),
      el('li', {}, 'Platby z výpisu sa spárujú s faktúrami. Záhradníka či správcu zaradíš raz, ďalej sa zarátavajú samy.'),
      el('li', {}, 'Elektrina zo ZSD sa sťahuje denne po 15 minútach; v prehľade je odhad ceny do konca mesiaca.'),
      el('li', {}, 'Na mobile: Zdieľať → Pridať na plochu. Appka potom beží ako ikona.')))));
}
async function renderAbout() {
  mount($('#main'), el('div', { class: 'page-h' }, el('h1', {}, 'O appke')), await aboutBody());
  if (S.me.changelog_new) PUT('/api/profile', { seen_changelog: true }).then(() => loadMe());
}

// ---------- Profil ----------
async function renderProfile() {
  const p = await GET('/api/profile');
  const form = el('form', { onsubmit: (e) => { e.preventDefault(); submitForm(form, async (v) => { await PUT('/api/profile', { name: v.name, email: v.email, ntfy_topic: v.ntfy_topic, notify_ntfy: v.notify_ntfy, notify_email: v.notify_email }); toast('Uložené'); loadMe(); }); } },
    field('Meno', input('name', p.name, { required: true })), field('E-mail', input('email', p.email, { type: 'email' }), 'Na obnovu hesla a upozornenia e-mailom.'),
    field('ntfy téma', input('ntfy_topic', p.ntfy_topic, { placeholder: 'napr. nakladiak-jano-x7k2' }), `V appke ntfy sa prihlás na odber tejto témy (server ${p.ntfy_server}). Vyber si ťažko uhádnuteľnú.`),
    check('notify_ntfy', 'Upozornenia cez ntfy', p.notify_ntfy, 'Nový spracovaný dokument, faktúra pred splatnosťou, týždenná spotreba, pripomienka na výpis.'),
    check('notify_email', 'Upozornenia aj e-mailom', p.notify_email),
    el('div', { class: 'row-btns' }, el('button', { class: 'btn btn--primary', type: 'submit' }, 'Uložiť'), await testBtn('Poslať skúšobnú notifikáciu', 'ntfy', () => ({ topic: form.querySelector('input[name=ntfy_topic]').value }))));
  const pw = el('form', { onsubmit: (e) => { e.preventDefault(); submitForm(pw, async (v) => { if (v.new !== v.new2) throw new Error('Nové heslá sa nezhodujú.'); await POST('/api/profile/password', { current: v.current, new: v.new }); toast('Heslo zmenené, ostatné zariadenia sú odhlásené'); pw.reset(); }); } },
    field('Súčasné heslo', input('current', '', { type: 'password', autocomplete: 'current-password', required: true })),
    el('div', { class: 'grid2' }, field('Nové heslo', input('new', '', { type: 'password', autocomplete: 'new-password', required: true, minlength: 8 })), field('Nové heslo znova', input('new2', '', { type: 'password', autocomplete: 'new-password', required: true, minlength: 8 }))),
    el('div', { class: 'row-btns' }, el('button', { class: 'btn btn--primary', type: 'submit' }, 'Zmeniť heslo'),
      el('button', { class: 'btn btn--ghost', type: 'button', onclick: async () => { if (await confirmSheet('Odhlásiť všetky zariadenia?', 'Toto zariadenie ostane prihlásené, ostatné sa odhlásia.', 'Odhlásiť všade')) { await POST('/api/profile/logout-all'); toast('Ostatné zariadenia sú odhlásené'); } } }, 'Odhlásiť všetky zariadenia')));
  mount($('#main'),
    el('div', { class: 'page-h' }, el('h1', {}, 'Profil'), el('span', { class: 'sub' }, '@' + p.username)),
    el('div', { class: 'cols2' },
      el('div', {}, el('div', { class: 'card' }, form)),
      el('div', {}, el('div', { class: 'card' }, el('h3', { style: { marginBottom: '10px' } }, 'Heslo'), pw),
        el('div', { class: 'card', style: { marginTop: '10px' } }, el('h3', { style: { marginBottom: '6px' } }, 'Pridať na plochu'), el('p', { class: 'sub' }, 'iPhone: Safari → Zdieľať → Pridať na plochu. Android: menu ⋮ → Inštalovať aplikáciu. Appka potom beží ako ikona bez lišty prehliadača.')))));
}

// ---------- boot ----------
(async () => {
  try { await loadMe(); } catch (e) { mount($('#main'), el('div', { class: 'alert alert--err' }, e.message)); return; }
  route();
  if ('serviceWorker' in navigator && location.protocol === 'https:') navigator.serviceWorker.register('/sw.js').catch(() => {});
  document.addEventListener('visibilitychange', () => { if (!document.hidden) loadMe().catch(() => {}); });
})();
})();
