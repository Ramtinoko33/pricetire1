// Agrupa ofertas do mesmo pneu (marca, modelo normalizado, índices, XL, RunFlat, C, estado).
// Cada grupo traz a oferta mais barata em `best` e as restantes em `others`, por preço.

const norm = (v) => String(v ?? '').toUpperCase().replace(/[^A-Z0-9+]/g, '');

export function offerGroupKey(o) {
  const model = o.model_key || norm(o.model) || norm(o.description);
  return [
    norm(o.brand), model, o.load_index_1 ?? '', o.load_index_2 ?? '', norm(o.speed_index),
    o.xl ? 'XL' : '', o.runflat ? 'RF' : '',
    o.commercial || /C$/.test(o.size_key || '') ? 'C' : '',
    o.condition && o.condition !== 'new' ? o.condition : '',
  ].join('|');
}

const priceOf = (o) => (o.price ?? null);

function byPrice(a, b) {
  const pa = priceOf(a);
  const pb = priceOf(b);
  if (pa === null && pb === null) return 0;
  if (pa === null) return 1;
  if (pb === null) return -1;
  return pa - pb;
}

export function groupOffers(offers, dir = 'asc') {
  const map = new Map();
  for (const o of offers || []) {
    const k = offerGroupKey(o);
    if (!map.has(k)) map.set(k, []);
    map.get(k).push(o);
  }
  const groups = [...map.entries()].map(([key, list]) => {
    const sorted = [...list].sort(byPrice);
    return {
      key,
      best: sorted[0],
      others: sorted.slice(1),
      suppliers: new Set(sorted.map((o) => o.supplier_id ?? o.supplier_name)).size,
    };
  });
  const mult = dir === 'desc' ? -1 : 1;
  groups.sort((a, b) => {
    const r = byPrice(a.best, b.best);
    return r === 0 ? 0 : (priceOf(a.best) === null || priceOf(b.best) === null ? r : r * mult);
  });
  return groups;
}
