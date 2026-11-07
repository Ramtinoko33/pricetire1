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

function parseFlotation(text, digits) {
  const m = digits.match(/^(?:LT)?(\d{2})[X×](\d{1,2}(?:\.\d{1,2})?)(?:LT)?(?:ZR|R|-)?(\d{2}(?:\.5)?)(?:LT)?$/);
  if (m) return flotationSize(parseInt(m[1], 10), parseFloat(m[2]), parseFloat(m[3]));
  const c = digits.match(/^(\d{2})(\d{2,4})(\d{2})$/);
  if (!c) return null;
  const wd = c[2];
  const w = wd.length === 4 ? parseInt(wd, 10) / 100 : wd.length === 3 ? parseInt(wd, 10) / 10 : parseInt(wd, 10) + 0.5;
  return flotationSize(parseInt(c[1], 10), w, parseInt(c[3], 10));
}

export function parseSize(input) {
  if (input === null || input === undefined) return null;
  const text = String(input).trim().toUpperCase().replace(',', '.');
  if (!text) return null;
  const digits = text.replace(/\s+/g, '');

  // Polegadas (jipe): 37x12.5R17 · 37X12.50 R17 · 37125017 · 3712517 · 371217
  const flot = parseFlotation(text, digits);
  if (flot) return flot;

  // Camião sem perfil: 12R22.5, 13 R 22.5
  const truck = digits.match(/^(1[0-4]|[7-9])R((?:17|19|22|24)\.5)$/);
  if (truck) {
    const width = parseInt(truck[1], 10);
    return {
      width, aspect: null, rim: parseFloat(truck[2]), construction: 'R', commercial: false,
      display: `${width}R${truck[2]}`, key: `${width}-${truck[2]}`,
    };
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
  if (width < 100 || width > 495 || aspect < 20 || aspect > 95 || rim < 10 || rim > 26) return null;
  const construction = m[3] && m[3] !== '-' ? m[3] : 'R';
  const commercial = Boolean(m[5]);
  const rimStr = String(rim);
  return {
    width,
    aspect,
    rim,
    construction,
    commercial,
    display: `${width}/${aspect}${construction}${rimStr}${commercial ? 'C' : ''}`,
    key: `${width}${aspect}${rimStr}${commercial ? 'C' : ''}`,
  };
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
