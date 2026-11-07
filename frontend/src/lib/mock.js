// Mock da API para inspecção visual SEM backend. Só é carregado com VITE_USE_MOCK=1
// (ver index.jsx / vite.config.mjs). Todos os dados são FICTÍCIOS: fornecedores,
// marcas, modelos e preços não correspondem a nada real.
import { AxiosError } from 'axios';

const now = () => new Date();
const hoursAgo = (h) => new Date(Date.now() - h * 3600000).toISOString();
const minutesFromNow = (m) => new Date(Date.now() + m * 60000).toISOString();
let seq = 1000;
const nextId = () => ++seq;

const ADAPTERS = ['mp24', 'prismanil', 'dispnal', 'sjose', 'euromais', 'soledad'];

const db = {
  users: [
    { id: 1, email: 'admin@exemplo.test', name: 'Administrador (demo)', role: 'admin', workshop_id: 1, is_active: true },
    { id: 2, email: 'operador@exemplo.test', name: 'Operador (demo)', role: 'user', workshop_id: 1, is_active: true },
  ],
  apiKeys: [{ id: 1, name: 'Integração demo', prefix: 'pps_demo', created_at: hoursAgo(300), last_used_at: hoursAgo(5) }],
  suppliers: ['A', 'B', 'C', 'D', 'E', 'F'].map((l, i) => ({
    id: i + 1,
    name: `Fornecedor ${l}`,
    adapter_key: ADAPTERS[i],
    is_active: l !== 'F',
    url_login: `https://fornecedor-${l.toLowerCase()}.exemplo.test/login`,
    url_search: `https://fornecedor-${l.toLowerCase()}.exemplo.test/pesquisa`,
    username: `oficina_demo_${l.toLowerCase()}`,
    has_password: l !== 'E',
    health: l === 'C'
      ? { status: 'failing', last_success_at: hoursAgo(30), last_failure_at: hoursAgo(1), last_error: 'Credenciais rejeitadas pelo portal (demo)', last_error_kind: 'login_failed', consecutive_failures: 3 }
      : l === 'E'
        ? { status: 'never', last_success_at: null, last_failure_at: null, last_error: null, last_error_kind: null, consecutive_failures: 0 }
        : { status: 'ok', last_success_at: hoursAgo(i + 1), last_failure_at: l === 'B' ? hoursAgo(40) : null, last_error: l === 'B' ? 'Timeout ao carregar resultados (demo)' : null, last_error_kind: l === 'B' ? 'timeout' : null, consecutive_failures: 0 },
  })),
  catalog: [],
  rules: [
    { id: 1, name: 'Qualquer referência ≥ 5%', scope: 'all', min_saving_pct: 5, min_saving_eur: null, email_to: 'compras@exemplo.test', active: true },
    { id: 2, name: 'Marca Alfa ≥ 3 €', scope: 'brand', brand: 'MARCA ALFA', min_saving_pct: null, min_saving_eur: 3, email_to: null, active: false },
  ],
  brandCategories: [
    { brand: 'MARCA ALFA', category: 'Premium' },
    { brand: 'MARCA BETA', category: 'Qualidade/preço' },
    { brand: 'MARCA GAMA', category: 'Económica' },
  ],
  targets: [{ id: 1, size: '195/65R15', size_key: '1956515' }, { id: 2, size: '225/45R17', size_key: '2254517' }],
  jobs: [],
  refreshes: {},
  excelJobs: [
    { id: 'demo-job-0001', filename: 'exemplo_fictício.xlsx', created_at: hoursAgo(20), total_items: 4, found_items: 1, total_savings: 4.5, status: 'completed' },
  ],
};

const BRANDS = ['MARCA ALFA', 'MARCA BETA', 'MARCA GAMA'];
const MODELS = { 'MARCA ALFA': ['Modelo Um', 'Modelo Dois'], 'MARCA BETA': ['Modelo Três'], 'MARCA GAMA': ['Modelo Quatro', 'Modelo Cinco'] };

function sizeKeyOf(text) {
  const d = String(text || '').replace(/[^0-9.C]/gi, '').toUpperCase();
  return d || '2055516';
}

function makeOffers(sizeKey) {
  const out = [];
  let n = 0;
  db.suppliers.filter((s) => s.is_active).forEach((s, si) => {
    BRANDS.forEach((b, bi) => {
      MODELS[b].forEach((m, mi) => {
        n += 1;
        const stale = s.health.status === 'failing';
        const xl = (si + mi) % 3 === 0;
        out.push({
          id: `${sizeKey}-${s.id}-${bi}-${mi}`,
          supplier_id: s.id,
          supplier_name: s.name,
          size_key: sizeKey,
          brand: b,
          model: m,
          description: `${b} ${m} ${sizeKey} 91V${xl ? ' XL' : ''} (descrição fictícia)`,
          load_index_1: xl ? 94 : 91,
          load_index_2: null,
          speed_index: 'V',
          xl,
          runflat: mi === 1 && bi === 0 ? true : (si === 3 ? null : false),
          runflat_tech: mi === 1 && bi === 0 ? 'RFT' : null,
          homologation: bi === 0 && mi === 0 && si % 2 === 0 ? 'MO' : null,
          season: bi === 2 ? 'all_season' : 'summer',
          condition: n % 11 === 0 ? 'demo' : 'new',
          flags: [],
          ean: null,
          supplier_ref: `REF-${s.id}${bi}${mi}`,
          price: Math.round((50 + bi * 12 + mi * 4 + si * 1.5 + (n % 5)) * 100) / 100,
          currency: 'EUR',
          stock_status: n % 7 === 0 ? 'unavailable' : n % 5 === 0 ? 'unknown' : 'available',
          stock_qty: n % 3 === 0 ? (n % 9) + 2 : null,
          stock_location: null,
          delivery_info: n % 4 === 0 ? '24 h (demo)' : null,
          last_seen_at: stale ? hoursAgo(30) : hoursAgo(si + 1),
          listed: true,
          fresh: !stale,
          age_hours: stale ? 30 : si + 1,
        });
      });
    });
  });
  return out;
}

function freshness() {
  return db.suppliers.map((s) => ({
    supplier_id: s.id,
    supplier_name: s.name,
    is_active: s.is_active,
    last_success_at: s.health.last_success_at,
    last_run_status: s.health.status === 'failing' ? 'failed' : s.health.status === 'never' ? null : 'done',
    last_run_at: s.health.last_failure_at || s.health.last_success_at,
    offers: s.is_active ? 5 : 0,
    fresh: s.health.status === 'ok',
  }));
}

function classify(wanted, o) {
  const details = [];
  const reasons = [];
  if (wanted.brand && o.brand !== String(wanted.brand).toUpperCase()) { reasons.push('brand_mismatch'); details.push(`Marca diferente (${o.brand})`); }
  if (wanted.model && !o.model.toLowerCase().includes(String(wanted.model).toLowerCase())) { reasons.push('model_mismatch'); details.push(`Modelo diferente (${o.model})`); }
  if (wanted.xl === true && o.xl === false) { reasons.push('xl_mismatch'); details.push('Pedido XL; oferta não é XL'); }
  if (wanted.xl === false && o.xl === true) { reasons.push('xl_mismatch'); details.push('Oferta é XL (carga superior)'); }
  if (wanted.runflat === true && o.runflat === null) {
    return { match_class: 'INFORMACAO_INSUFICIENTE', reasons: ['runflat_unknown'], details: ['O fornecedor não indica se é RunFlat'] };
  }
  if (wanted.runflat !== undefined && o.runflat !== null && wanted.runflat !== o.runflat) { reasons.push('runflat_mismatch'); details.push('RunFlat diferente'); }
  if (o.condition === 'demo') { reasons.push('condition_mismatch'); details.push('Pneu DEMO'); }
  if (!reasons.length) return { match_class: 'MATCH_EXACTO', reasons: [], details: [] };
  const incompat = reasons.includes('runflat_mismatch') && wanted.runflat === true;
  return { match_class: incompat ? 'INCOMPATIVEL' : 'ALTERNATIVA_COMPATIVEL', reasons, details };
}

function initCatalog() {
  const sizes = ['2055516', '2254517', '1956515'];
  db.catalog = sizes.map((sk, i) => ({
    id: i + 1,
    reference: `CAT-00${i + 1}`,
    description: `Referência fictícia ${i + 1}`,
    size_key: sk,
    size_display: `${sk.slice(0, 3)}/${sk.slice(3, 5)}R${sk.slice(5)}`,
    brand: BRANDS[i % 3],
    model: MODELS[BRANDS[i % 3]][0],
    load_index_1: 91,
    load_index_2: null,
    speed_index: 'V',
    xl: false,
    runflat: i === 1 ? null : false,
    homologation: null,
    season: 'summer',
    ean: null,
    manufacturer_ref: null,
    last_purchase_price: [58, 60, 75][i],
    last_purchase_date: hoursAgo(24 * (20 + i)).slice(0, 10),
    price_updated_at: hoursAgo(24 * (20 + i)),
    usual_supplier_id: i + 1,
    category: ['Premium', 'Qualidade/preço', 'Económica'][i],
    active: i !== 2,
    notes: null,
    updated_at: hoursAgo(10),
  }));
}
initCatalog();

function initJobs() {
  const statuses = ['done', 'partial', 'failed', 'running', 'queued', 'done', 'cancelled'];
  db.jobs = statuses.map((st, i) => {
    const s = db.suppliers[i % db.suppliers.length];
    return {
      id: 500 + i,
      type: i === 5 ? 'test_login' : 'scrape',
      status: st,
      supplier_id: s.id,
      supplier_name: s.name,
      payload: { size: '205/55R16' },
      attempts: st === 'failed' ? 3 : 1,
      max_attempts: 3,
      created_at: hoursAgo(i + 0.5),
      started_at: st === 'queued' ? null : hoursAgo(i + 0.4),
      finished_at: ['done', 'failed', 'cancelled'].includes(st) ? hoursAgo(i + 0.2) : null,
      error: st === 'failed' ? 'Credenciais rejeitadas pelo portal (demo)' : null,
      error_kind: st === 'failed' ? 'login_failed' : null,
    };
  });
}
initJobs();

function comparisonRows(onlySavings) {
  const rows = db.catalog.filter((c) => c.active).map((item) => {
    const offers = makeOffers(item.size_key);
    const wanted = { brand: item.brand, model: item.model, xl: item.xl ?? undefined, runflat: item.runflat ?? undefined };
    const classified = offers.map((o) => ({ ...o, match: classify(wanted, o) }));
    const exact = classified.filter((o) => o.match.match_class === 'MATCH_EXACTO').sort((a, b) => a.price - b.price);
    const best = exact[0] || null;
    const saving = best ? Math.round((item.last_purchase_price - best.price) * 100) / 100 : null;
    let status = 'no_data';
    if (best) status = best.fresh === false ? 'stale' : saving > 0 ? 'saving' : 'no_saving';
    else if (offers.length) status = 'no_exact_match';
    return {
      item,
      reference_price: item.last_purchase_price,
      reference_date: item.last_purchase_date,
      best_exact: best,
      saving_eur: saving,
      saving_pct: saving !== null ? Math.round((saving / item.last_purchase_price) * 1000) / 10 : null,
      exact_count: exact.length,
      alternatives_count: classified.filter((o) => o.match.match_class === 'ALTERNATIVA_COMPATIVEL').length,
      insufficient_count: classified.filter((o) => o.match.match_class === 'INFORMACAO_INSUFICIENTE').length,
      status,
      prices_at: best?.last_seen_at || null,
    };
  });
  return onlySavings ? rows.filter((r) => r.status === 'saving') : rows;
}

function excelResults() {
  return [
    { id: 1, ref_id: 'L1', medida: '205/55R16', marca: 'MARCA ALFA', modelo: 'Modelo Um', indice: '91V', modelo_encontrado: 'Modelo Um', indice_encontrado: '91V', meu_preco: 58, melhor_preco: 53.5, melhor_fornecedor: 'Fornecedor A', economia_euro: 4.5, economia_percent: 7.8, match_class: 'MATCH_EXACTO', match_reasons: [], prices_at: hoursAgo(2) },
    { id: 2, ref_id: 'L2', medida: '205/55R16', marca: 'MARCA BETA', modelo: 'Modelo Três', indice: '91V', modelo_encontrado: 'Modelo Três', indice_encontrado: '94V XL', meu_preco: 64, melhor_preco: 60, melhor_fornecedor: 'Fornecedor B', economia_euro: null, economia_percent: null, match_class: 'ALTERNATIVA_COMPATIVEL', match_reasons: ['xl_mismatch'], prices_at: hoursAgo(3) },
    { id: 3, ref_id: 'L3', medida: '225/45R17', marca: 'MARCA GAMA', modelo: 'Modelo Quatro', indice: '94W', modelo_encontrado: 'Modelo Quatro', indice_encontrado: '94W', meu_preco: 70, melhor_preco: null, melhor_fornecedor: null, economia_euro: null, economia_percent: null, match_class: 'INFORMACAO_INSUFICIENTE', match_reasons: ['runflat_unknown'], prices_at: hoursAgo(30) },
    { id: 4, ref_id: 'L4', medida: '195/65R15', marca: 'MARCA ALFA', modelo: 'Modelo Dois', indice: '91H', modelo_encontrado: 'Modelo Dois RFT', indice_encontrado: '91H', meu_preco: 66, melhor_preco: 61, melhor_fornecedor: 'Fornecedor D', economia_euro: null, economia_percent: null, match_class: 'INCOMPATIVEL', match_reasons: ['runflat_mismatch'], prices_at: hoursAgo(4) },
  ];
}

function parseBody(config) {
  if (!config.data || typeof config.data !== 'string') return config.data || {};
  try { return JSON.parse(config.data); } catch { return {}; }
}

function fail(config, status, detail) {
  const response = { data: { detail }, status, statusText: String(status), headers: {}, config };
  return Promise.reject(new AxiosError(detail, String(status), config, null, response));
}

function ok(config, data, status = 200) {
  return new Promise((resolve) => {
    setTimeout(() => resolve({ data, status, statusText: 'OK', headers: {}, config, request: {} }), 250);
  });
}

function refreshState(id) {
  const r = db.refreshes[id];
  if (!r) return null;
  const elapsed = (Date.now() - r.started) / 1000;
  const jobs = r.jobs.map((j, i) => {
    const doneAt = 4 + i * 3;
    if (elapsed < 1.5 + i) return { ...j, status: 'queued' };
    if (elapsed < doneAt) return { ...j, status: 'running', started_at: hoursAgo(0) };
    const failed = j.supplier_name === 'Fornecedor C';
    return {
      ...j,
      status: failed ? 'failed' : 'done',
      error: failed ? 'Credenciais rejeitadas pelo portal (demo)' : null,
      error_kind: failed ? 'login_failed' : null,
      products: failed ? 0 : 5,
      finished_at: hoursAgo(0),
    };
  });
  return { request_id: id, done: jobs.every((j) => ['done', 'failed'].includes(j.status)), jobs };
}

function route(config) {
  const method = (config.method || 'get').toLowerCase();
  const url = (config.url || '').split('?')[0];
  const params = config.params || {};
  const body = parseBody(config);
  const m = (re) => url.match(re);
  let mm;

  if (url === '/auth/login' && method === 'post') {
    if (!body.email || !body.password) return fail(config, 400, 'Email e password obrigatórios');
    if (body.password === 'errada') return fail(config, 401, 'Email ou password incorrectos');
    return ok(config, { token: 'mock-token', user: db.users[0] });
  }
  if (url === '/auth/me') return ok(config, db.users[0]);
  if (url === '/auth/change-password') {
    if (body.current_password === 'errada') return fail(config, 400, 'Password actual incorrecta');
    return ok(config, { ok: true });
  }

  if (url === '/users' && method === 'get') return ok(config, db.users);
  if (url === '/users' && method === 'post') { const u = { id: nextId(), ...body, password: undefined, is_active: true }; db.users.push(u); return ok(config, u, 201); }
  if ((mm = m(/^\/users\/(\d+)$/)) && method === 'put') {
    const u = db.users.find((x) => x.id === Number(mm[1]));
    Object.assign(u, { ...body, password: undefined });
    return ok(config, u);
  }

  if (url === '/api-keys' && method === 'get') return ok(config, db.apiKeys);
  if (url === '/api-keys' && method === 'post') {
    const k = { id: nextId(), name: body.name, prefix: 'pps_mock', created_at: now().toISOString(), last_used_at: null };
    db.apiKeys.push(k);
    return ok(config, { ...k, key: `pps_mock_${Math.random().toString(36).slice(2)}${Math.random().toString(36).slice(2)}` }, 201);
  }
  if ((mm = m(/^\/api-keys\/(\d+)$/)) && method === 'delete') { db.apiKeys = db.apiKeys.filter((k) => k.id !== Number(mm[1])); return ok(config, { ok: true }); }

  if (url === '/v1/brands') return ok(config, { brands: BRANDS.map((brand) => ({ brand, offers: 10 })) });
  if (url === '/v1/offers') {
    const sk = sizeKeyOf(params.size);
    let offers = makeOffers(sk);
    if (params.brand) offers = offers.filter((o) => o.brand.includes(String(params.brand).toUpperCase()));
    if (params.model) offers = offers.filter((o) => o.model.toLowerCase().includes(String(params.model).toLowerCase()));
    if (params.xl) offers = offers.filter((o) => String(o.xl) === String(params.xl));
    if (params.runflat) offers = offers.filter((o) => String(o.runflat) === String(params.runflat));
    if (params.season) offers = offers.filter((o) => o.season === params.season);
    if (params.supplier_id) offers = offers.filter((o) => String(o.supplier_id) === String(params.supplier_id));
    if (params.min_price) offers = offers.filter((o) => o.price >= Number(params.min_price));
    if (params.max_price) offers = offers.filter((o) => o.price <= Number(params.max_price));
    if (params.in_stock) offers = offers.filter((o) => o.stock_status === 'available');
    return ok(config, { size: params.size, size_key: sk, generated_at: now().toISOString(), offers, suppliers: freshness() });
  }
  if (url === '/v1/search' && method === 'post') {
    const sk = sizeKeyOf(body.size);
    const offers = makeOffers(sk).map((o) => ({ ...o, match: classify(body, o) }));
    const by = (c) => offers.filter((o) => o.match.match_class === c);
    const exact = by('MATCH_EXACTO').sort((a, b) => a.price - b.price);
    return ok(config, {
      parsed: { sizes: [body.size] },
      wanted: body,
      status: 'partial',
      results: { exact, alternatives: by('ALTERNATIVA_COMPATIVEL'), insufficient: by('INFORMACAO_INSUFICIENTE') },
      best_exact: exact[0] || null,
      suppliers: freshness(),
      warnings: ['Dados fictícios (modo demonstração).', 'Fornecedor C sem recolha bem-sucedida nas últimas 24 h.'],
    });
  }
  if (url === '/v1/refresh' && method === 'post') {
    const id = `req-${nextId()}`;
    const jobs = db.suppliers.filter((s) => s.is_active).map((s) => ({ job_id: nextId(), supplier_id: s.id, supplier_name: s.name, status: 'queued', deduplicated: s.name === 'Fornecedor B' }));
    db.refreshes[id] = { started: Date.now(), jobs };
    return ok(config, { request_id: id, jobs });
  }
  if ((mm = m(/^\/v1\/refresh\/(.+)$/))) {
    const st = refreshState(decodeURIComponent(mm[1]));
    return st ? ok(config, st) : fail(config, 404, 'Pedido não encontrado');
  }

  if (url === '/suppliers' && method === 'get') return ok(config, db.suppliers);
  if (url === '/suppliers/adapters') {
    return ok(config, ['mp24', 'prismanil', 'dispnal', 'sjose', 'euromais', 'soledad', 'andres', 'aguesport', 'abtyres', 'tugapneus', 'intersprint', 'cruzeiro']
      .map((key, i) => ({ key, name: `Conector ${i + 1}`, notes: 'Notas fictícias do conector (demo)', brand_aware: i % 3 === 0 })));
  }
  if (url === '/suppliers' && method === 'post') {
    const s = { id: nextId(), ...body, has_password: Boolean(body.password), health: { status: 'never', consecutive_failures: 0 } };
    delete s.password;
    db.suppliers.push(s);
    return ok(config, s, 201);
  }
  if ((mm = m(/^\/suppliers\/(\d+)\/test$/)) && method === 'post') {
    const s = db.suppliers.find((x) => x.id === Number(mm[1]));
    const job = { id: nextId(), type: 'test_login', status: 'queued', supplier_id: s.id, supplier_name: s.name, created_at: now().toISOString(), _t: Date.now() };
    db.jobs.unshift(job);
    return ok(config, { job_id: job.id, status: 'queued', deduplicated: false });
  }
  if ((mm = m(/^\/suppliers\/(\d+)$/))) {
    const id = Number(mm[1]);
    const s = db.suppliers.find((x) => x.id === id);
    if (method === 'delete') { s.is_active = false; return ok(config, s); }
    const { password, ...rest } = body;
    Object.assign(s, rest);
    if (password) s.has_password = true;
    return ok(config, s);
  }

  if (url === '/ops/status') {
    return ok(config, {
      queue: { queued: 1, running: 1, failed_24h: 1, done_24h: 3 },
      workers: [
        { worker_id: 'worker-demo-1', seen_at: hoursAgo(0.01), current_job_id: 503, alive: true },
        { worker_id: 'worker-demo-2', seen_at: hoursAgo(2), current_job_id: null, alive: false },
      ],
      scheduler: { timezone: 'Europe/Lisbon', times: ['07:00', '13:00'], next_runs: [minutesFromNow(90), minutesFromNow(450)], last_started_at: hoursAgo(3), last_finished_at: hoursAgo(2.5) },
      suppliers: db.suppliers.map((s) => ({ supplier_id: s.id, supplier_name: s.name, is_active: s.is_active, health: s.health })),
      alarms: [
        { level: 'warning', message: 'Fornecedor C: 3 falhas consecutivas (login_failed) — demo', since: hoursAgo(3) },
        { level: 'critical', message: 'worker-demo-2 sem sinal há mais de 1 h — demo', since: hoursAgo(2) },
      ],
    });
  }
  if (url === '/ops/jobs') {
    db.jobs.forEach((j) => {
      if (j._t && j.status !== 'done') {
        const el = (Date.now() - j._t) / 1000;
        j.status = el > 7 ? 'done' : el > 3 ? 'running' : 'queued';
        if (j.status === 'done') j.finished_at = now().toISOString();
      }
    });
    let list = db.jobs;
    if (params.status) list = list.filter((j) => j.status === params.status);
    if (params.type) list = list.filter((j) => j.type === params.type);
    if (params.supplier_id) list = list.filter((j) => String(j.supplier_id) === String(params.supplier_id));
    return ok(config, list.slice(0, Number(params.limit) || 100));
  }
  if ((mm = m(/^\/ops\/jobs\/(\d+)\/(retry|cancel)$/))) {
    const j = db.jobs.find((x) => x.id === Number(mm[1]));
    if (j) j.status = mm[2] === 'retry' ? 'queued' : 'cancelled';
    return ok(config, { ok: true });
  }
  if (url === '/ops/run-scheduled-now' && method === 'post') return ok(config, { enqueued: 12 });
  if (url === '/ops/runs') {
    const list = db.suppliers.filter((s) => !params.supplier_id || String(s.id) === String(params.supplier_id)).flatMap((s, i) => [0, 1, 2].map((k) => ({
      id: `${s.id}-${k}`, supplier_id: s.id, supplier_name: s.name, size: params.size || '205/55R16',
      status: s.health.status === 'failing' ? 'error' : k === 2 && i % 2 ? 'empty' : 'ok',
      products: s.health.status === 'failing' ? 0 : 5 - k, error_kind: s.health.status === 'failing' ? 'login_failed' : null,
      error: s.health.status === 'failing' ? 'Credenciais rejeitadas (demo)' : null, finished_at: hoursAgo(k * 6 + i),
    })));
    return ok(config, list);
  }
  if (url === '/ops/failures') return ok(config, db.jobs.filter((j) => j.status === 'failed'));

  if (url === '/scheduled-targets' && method === 'get') return ok(config, db.targets);
  if (url === '/scheduled-targets' && method === 'post') { const t = { id: nextId(), size: body.size, size_key: sizeKeyOf(body.size) }; db.targets.push(t); return ok(config, t, 201); }
  if ((mm = m(/^\/scheduled-targets\/(.+)$/)) && method === 'delete') { db.targets = db.targets.filter((t) => String(t.id) !== decodeURIComponent(mm[1])); return ok(config, { ok: true }); }

  if (url === '/catalog/comparison') return ok(config, comparisonRows(String(params.only_savings) === 'true'));
  if (url === '/catalog/template') return ok(config, new Blob(['modelo fictício'], { type: 'application/octet-stream' }));
  if (url === '/catalog/import' && method === 'post') {
    return ok(config, { created: 2, updated: 1, rejected: [{ row: 4, reason: 'Medida não reconhecida: "205-55"' }, { row: 7, reason: 'Referência em falta' }] });
  }
  if (url === '/catalog' && method === 'get') {
    let list = db.catalog;
    if (params.active !== undefined && params.active !== '') list = list.filter((c) => String(c.active) === String(params.active));
    if (params.q) {
      const q = String(params.q).toLowerCase();
      list = list.filter((c) => [c.reference, c.brand, c.model, c.size_key, c.size_display, c.description].some((v) => String(v || '').toLowerCase().includes(q)));
    }
    return ok(config, list);
  }
  if (url === '/catalog' && method === 'post') { const c = { id: nextId(), ...body, updated_at: now().toISOString() }; db.catalog.push(c); return ok(config, c, 201); }
  if ((mm = m(/^\/catalog\/(\d+)$/))) {
    const id = Number(mm[1]);
    if (method === 'delete') { db.catalog = db.catalog.filter((c) => c.id !== id); return ok(config, { ok: true }); }
    const c = db.catalog.find((x) => x.id === id);
    Object.assign(c, body, { updated_at: now().toISOString() });
    return ok(config, c);
  }

  if (url === '/alerts/rules' && method === 'get') return ok(config, db.rules);
  if (url === '/alerts/rules' && method === 'post') { const r = { id: nextId(), ...body }; db.rules.push(r); return ok(config, r, 201); }
  if ((mm = m(/^\/alerts\/rules\/(\d+)$/))) {
    const id = Number(mm[1]);
    if (method === 'delete') { db.rules = db.rules.filter((r) => r.id !== id); return ok(config, { ok: true }); }
    Object.assign(db.rules.find((r) => r.id === id), body);
    return ok(config, { ok: true });
  }
  if (url === '/alerts/events') {
    const c = db.catalog[0];
    return ok(config, [
      { id: 1, rule_name: db.rules[0].name, item: { reference: c.reference, description: c.description, size_key: c.size_key, brand: c.brand, model: c.model }, supplier_name: 'Fornecedor A', reference_price: 58, offer_price: 53.5, saving_eur: 4.5, saving_pct: 7.8, observed_at: hoursAgo(2), notified_at: hoursAgo(1.9), notify_error: null },
      { id: 2, rule_name: db.rules[0].name, item: { reference: c.reference, description: c.description, size_key: c.size_key, brand: c.brand, model: c.model }, supplier_name: 'Fornecedor D', reference_price: 58, offer_price: 54, saving_eur: 4, saving_pct: 6.9, observed_at: hoursAgo(26), notified_at: null, notify_error: 'SMTP indisponível (demo)' },
    ]);
  }
  if (url === '/alerts/test-email') return ok(config, { ok: true });
  if (url === '/alerts/evaluate') return ok(config, { created: 0 });
  if (url === '/brand-categories' && method === 'get') return ok(config, db.brandCategories);
  if (url === '/brand-categories' && method === 'put') { db.brandCategories = Array.isArray(body) ? body : []; return ok(config, db.brandCategories); }

  if (url === '/jobs' && method === 'get') return ok(config, db.excelJobs);
  if (url === '/jobs/upload') {
    const j = { id: `demo-job-${nextId()}`, filename: 'carregado_demo.xlsx', created_at: now().toISOString(), total_items: 4, status: 'pending' };
    db.excelJobs.unshift(j);
    return ok(config, j);
  }
  if ((mm = m(/^\/jobs\/([^/]+)\/compare$/))) return ok(config, { async: true });
  if ((mm = m(/^\/jobs\/([^/]+)\/progress$/))) {
    return ok(config, { status: 'completed', total_items: 4, found_items: 1, suppliers_status: db.suppliers.filter((s) => s.is_active).map((s) => ({ name: s.name, status: s.name === 'Fornecedor C' ? 'error' : 'done', duration_s: 12, products: 5, best_price: 53.5 })) });
  }
  if ((mm = m(/^\/jobs\/([^/]+)\/results$/))) return ok(config, excelResults());
  if ((mm = m(/^\/jobs\/([^/]+)\/export$/))) return ok(config, new Blob(['export fictício']));
  if ((mm = m(/^\/jobs\/([^/]+)\/(save|cancel)$/))) return ok(config, { ok: true });
  if ((mm = m(/^\/jobs\/([^/]+)$/)) && method === 'delete') { db.excelJobs = db.excelJobs.filter((j) => j.id !== mm[1]); return ok(config, { ok: true }); }

  return fail(config, 404, `Mock: rota não implementada ${method.toUpperCase()} ${url}`);
}

export function installMock(api) {
  // eslint-disable-next-line no-console
  console.info('[mock] API simulada activa (VITE_USE_MOCK=1) — dados fictícios');
  api.defaults.adapter = (config) => route(config);
}
