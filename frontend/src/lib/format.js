// Utilitários de formatação e parsing usados em toda a UI.

const eurFmt = new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' });

export function formatPrice(value, currency = 'EUR') {
  if (value === null || value === undefined || value === '' || Number.isNaN(Number(value))) return '—';
  if (currency && currency !== 'EUR') {
    return new Intl.NumberFormat('pt-PT', { style: 'currency', currency }).format(Number(value));
  }
  return eurFmt.format(Number(value));
}

export function formatPct(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return `${Number(value).toFixed(digits).replace('.', ',')}%`;
}

export function parseDate(value) {
  if (!value) return null;
  const d = value instanceof Date ? value : new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatDateTime(value) {
  const d = parseDate(value);
  if (!d) return '—';
  return d.toLocaleString('pt-PT', {
    day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

export function formatDate(value) {
  const d = parseDate(value);
  if (!d) return '—';
  return d.toLocaleDateString('pt-PT', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

// Idade relativa em PT-PT: "agora mesmo", "há 5 min", "há 3 h", "há 2 dias".
// Aceita uma data (string/Date) ou um número de horas (age_hours).
export function formatAge(value, now = new Date()) {
  let hours;
  if (typeof value === 'number') {
    hours = value;
  } else {
    const d = parseDate(value);
    if (!d) return '—';
    hours = (now.getTime() - d.getTime()) / 3600000;
  }
  if (!Number.isFinite(hours)) return '—';
  if (hours < 0) hours = 0;
  const minutes = Math.floor(hours * 60);
  if (minutes < 1) return 'agora mesmo';
  if (minutes < 60) return `há ${minutes} min`;
  const h = Math.floor(hours);
  if (h < 24) return `há ${h} h`;
  const days = Math.floor(h / 24);
  if (days === 1) return 'há 1 dia';
  if (days < 30) return `há ${days} dias`;
  const months = Math.floor(days / 30);
  return months === 1 ? 'há 1 mês' : `há ${months} meses`;
}

// Normaliza a medida introduzida pelo utilizador.
// Aceita "205/55R16", "205/55 R16", "205 55 16", "2055516", "205/55ZR17", "215/65R16C", "205/55R16.5".
// Devolve { width, aspect, rim, construction, commercial, display, key } ou null.
function flotationSize(d, w, rim) {
  if (!(d >= 26 && d <= 44 && w >= 7 && w <= 16.5 && Number.isInteger(w * 2) && rim >= 14 && rim <= 24)) return null;
  const ws = w.toFixed(2);
  const rs = String(rim);
  return {
    width: d, aspect: Math.round(w * 100), rim, construction: 'R', commercial: false, flotation: true,
    display: `${d}x${ws}R${rs}`, key: `${d}X${ws}R${rs}`,
  };
}

const num = (v) => (Number.isInteger(v) ? String(v) : String(parseFloat(v.toFixed(2))));

// Empilhador: 18x7-8 · 28x9-15 (largura inteira, diagonal)
function forkliftSize(d, w, rim) {
  if (!(d >= 10 && d <= 40 && Number.isInteger(w) && w >= 4 && w <= 20 && rim >= 8 && rim <= 24)) return null;
  return {
    width: d, aspect: w * 100, rim, construction: 'D', commercial: false, flotation: true,
    display: `${d}x${w}-${num(rim)}`, key: `${d}X${w}-${num(rim)}`,
  };
}

function parseFlotation(text, digits) {
  const m = digits.match(/^(?:LT)?(\d{2})[X×](\d{1,2}(?:\.\d{1,2})?)(?:LT)?(ZR|R|-)?(\d{1,2}(?:\.5)?)(?:LT)?$/);
  if (m) {
    const w = parseFloat(m[2]);
    if (Number.isInteger(w)) return forkliftSize(parseInt(m[1], 10), w, parseFloat(m[4]));
    return flotationSize(parseInt(m[1], 10), w, parseFloat(m[4]));
  }
  const c = digits.match(/^(\d{2})(\d{2,4})(\d{2})$/);
  if (!c) return null;
  const wd = c[2];
  const w = wd.length === 4 ? parseInt(wd, 10) / 100 : wd.length === 3 ? parseInt(wd, 10) / 10 : parseInt(wd, 10) + 0.5;
  return flotationSize(parseInt(c[1], 10), w, parseInt(c[3], 10));
}

function parseSizeText(input) {
  if (input === null || input === undefined) return null;
  const text = String(input).trim().toUpperCase().replace(',', '.');
  if (!text) return null;
  const digits = text.replace(/\s+/g, '');

  // Polegadas (jipe): 37x12.5R17 · 37X12.50 R17 · 37125017 · 3712517 · 371217
  const flot = parseFlotation(text, digits);
  if (flot) return flot;

  // Largura em polegadas, sem perfil (camião, agrícola, OTR, empilhador):
  // 12R22.5 · 11.2R24 · 16.9-28 · 7.50-20 · 12.00R20 · 10-16.5
  const inch = digits.match(/^(\d{1,2}(?:\.\d{1,2})?)(R|-)(\d{1,2}(?:\.5)?)$/);
  if (inch) {
    const w = parseFloat(inch[1]);
    const rim = parseFloat(inch[3]);
    if (w >= 4 && w <= 40 && rim >= 8 && rim <= 54) {
      return {
        width: w, aspect: null, rim, construction: inch[2] === '-' ? 'D' : 'R', commercial: false,
        display: `${inch[1]}${inch[2]}${inch[3]}`, key: `${num(w)}R${num(rim)}`,
      };
    }
  }

  // Métrica com largura decimal ou em polegadas: 10.5/80-18 · 16/70-20
  const dec = digits.match(/^(\d{1,2}(?:\.\d)?)\/(\d{2})(R|-)(\d{2}(?:\.5)?)$/);
  if (dec) {
    const w = parseFloat(dec[1]);
    const a = parseInt(dec[2], 10);
    const rim = parseFloat(dec[4]);
    if (w >= 4 && w <= 40 && a >= 25 && a <= 95 && rim >= 10 && rim <= 54) {
      return {
        width: w, aspect: a, rim, construction: dec[3] === '-' ? 'D' : 'R', commercial: false,
        display: `${dec[1]}/${a}${dec[3]}${dec[4]}`, key: `${num(w)}/${a}R${num(rim)}`,
      };
    }
  }

  // Sem perfil (195R14C) e industrial (250-15)
  const noAsp = digits.match(/^(\d{3})R(\d{2})(C)?$/);
  if (noAsp) {
    const width = parseInt(noAsp[1], 10);
    const rim = parseInt(noAsp[2], 10);
    if (width >= 125 && width <= 235 && width % 5 === 0 && rim >= 10 && rim <= 24) {
      const c = noAsp[3] ? 'C' : '';
      return { width, aspect: null, rim, construction: 'R', commercial: Boolean(c), display: `${width}R${rim}${c}`, key: `${width}-${rim}${c}` };
    }
  }
  const ind = digits.match(/^(\d{3})-(\d{1,2})$/);
  if (ind) {
    const width = parseInt(ind[1], 10);
    const rim = parseInt(ind[2], 10);
    if (width >= 140 && width <= 355 && width % 5 === 0 && rim >= 8 && rim <= 20) {
      return { width, aspect: null, rim, construction: 'D', commercial: false, display: `${width}-${rim}`, key: `${width}-${rim}` };
    }
  }

  let m = text.match(/^(\d{3})\s*[/\s-]?\s*(\d{2})\s*(ZR|R|D|B|-)?\s*(\d{2}(?:\.\d)?)\s*(C)?$/);
  if (!m) m = digits.match(/^(\d{3})(\d{2})(ZR|R|D|B)?(\d{2}(?:\.\d)?)(C)?$/);
  if (!m) {
    // Compacto de 8 dígitos com jante .5: 31570225 → 315/70R22.5
    const c = digits.match(/^(\d{3})(\d{2})(\d{2})5(C)?$/);
    if (c) m = [c[0], c[1], c[2], undefined, `${c[3]}.5`, c[4]];
  }
  if (!m) return null;

  const width = parseInt(m[1], 10);
  const aspect = parseInt(m[2], 10);
  const rim = parseFloat(m[4]);
  if (width < 100 || width > 900 || aspect < 20 || aspect > 95 || rim < 10 || rim > 54) return null;
  if (rim > 26 && aspect < 60) return null;   // jantes grandes só com perfil alto (agrícolas)
  const bias = m[3] === '-' && width >= 300;   // agrícola/industrial: 400/70-20 é diagonal
  const construction = m[3] && m[3] !== '-' ? m[3] : 'R';
  const commercial = Boolean(m[5]);
  const rimStr = String(rim);
  return {
    width,
    aspect,
    rim,
    construction,
    commercial,
    display: `${width}/${aspect}${bias ? '-' : construction}${rimStr}${commercial ? 'C' : ''}`,
    key: `${width}${aspect}${rimStr}${commercial ? 'C' : ''}`,
  };
}

// Medidas escritas só com algarismos (igual a expand_compact_digits no backend):
// 951750 → 9.5R17.5 · 28915 → 28x9-15 · 25015 → 250-15 · 65010 → 6.50-10.
export function expandCompactDigits(text) {
  const d = String(text ?? '').replace(/\s+/g, '');
  if (!/^\d{4,6}$/.test(d)) return null;
  let m = d.match(/^([7-9])5(175|195|225)0?$/);
  if (m) return `${m[1]}.5R${m[2].slice(0, 2)}.5`;
  m = d.match(/^(1[5-9]|[23]\d|40)(\d{2,4})$/);
  if (m) {
    const rest = m[2];
    const ok = [1, 2]
      .filter((i) => i < rest.length)
      .map((i) => [rest.slice(0, i), rest.slice(i)])
      .filter(([a, b]) => a[0] !== '0' && b[0] !== '0' && +a >= 4 && +a <= 16 && +b >= 5 && +b <= 24);
    if (ok.length === 1) return `${m[1]}x${ok[0][0]}-${ok[0][1]}`;
  }
  m = d.match(/^(1[4-9]0|2\d0|3[0-5]0)(\d{1,2})$/);
  if (m && +m[2] >= 8 && +m[2] <= 24) return `${m[1]}-${m[2]}`;
  m = d.match(/^([4-9]|1[0-2])(00|25|50|75)(\d{1,2})$/);
  if (m && m[3][0] !== '0' && +m[3] >= 4 && +m[3] <= 24) return `${m[1]}.${m[2]}-${m[3]}`;
  m = d.match(/^(\d{1,2})(175|195|225|245)$/); // camião: 13225 → 13R22.5
  if (m && +m[1] >= 7 && +m[1] <= 13) return `${m[1]}R${m[2].slice(0, 2)}.5`;
  m = d.match(/^(\d{2})(\d)(\d{2})$/); // agrícola: 18430 → 18.4-30
  if (m && +m[1] >= 9 && +m[1] <= 30 && +m[3] % 2 === 0 && +m[3] >= 20 && +m[3] <= 54) return `${m[1]}.${m[2]}-${m[3]}`;
  return null;
}

// Medidas de empilhador com duas designações (igual a SIZE_ALIASES no backend): 180/70-8 = 18x7-8.
const SIZE_ALIASES = [{ re: /^180\s*\/\s*70\s*(?:R|-|\s)?\s*8$/, digits: '180708', to: '18x7-8' }];

export function parseSize(input) {
  const raw = String(input ?? '').trim().toUpperCase();
  const alias = SIZE_ALIASES.find((a) => a.re.test(raw) || raw.replace(/\s+/g, '') === a.digits);
  if (alias) return parseSizeText(alias.to);
  const parsed = parseSizeText(input);
  if (parsed) return parsed;
  const expanded = expandCompactDigits(input);
  return expanded ? parseSizeText(expanded) : null;
}

// Lista de medidas separadas por vírgula, ponto e vírgula ou quebra de linha.
export function parseSizeList(text) {
  if (!text) return { sizes: [], invalid: [] };
  const parts = String(text).split(/[;,\n]+/).map((s) => s.trim()).filter(Boolean);
  const sizes = [];
  const invalid = [];
  parts.forEach((p) => {
    const s = parseSize(p);
    if (s) {
      if (!sizes.some((x) => x.key === s.key)) sizes.push(s);
    } else {
      invalid.push(p);
    }
  });
  return { sizes, invalid };
}

export function formatLoadSpeed(o) {
  if (!o) return '—';
  const load = o.load_index_1
    ? `${o.load_index_1}${o.load_index_2 ? `/${o.load_index_2}` : ''}`
    : '';
  const s = `${load}${o.speed_index || ''}`;
  return s || '—';
}

export function errorMessage(err, fallback = 'Ocorreu um erro') {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length) {
    return detail.map((d) => d?.msg || String(d)).join('; ');
  }
  if (err?.code === 'ECONNABORTED') return 'O servidor demorou demasiado a responder';
  if (err?.message === 'Network Error') return 'Sem ligação ao servidor';
  return fallback;
}

export const SEASON_LABELS = { summer: 'Verão', winter: 'Inverno', all_season: 'Todo o ano' };
export const CONDITION_LABELS = { new: 'Novo', demo: 'DEMO', used: 'Usado', retread: 'Recauchutado' };
