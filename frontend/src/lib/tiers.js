// Tiers de marca: 1 premium, 2 quality, 3 budget (tabela brand_categories).

export const TIERS = [
  { key: 1, label: 'Premium', sub: 'Tier 1', tone: 'border-t-violet-500' },
  { key: 2, label: 'Quality', sub: 'Tier 2', tone: 'border-t-blue-500' },
  { key: 3, label: 'Budget', sub: 'Tier 3', tone: 'border-t-emerald-500' },
];

export const UNCLASSIFIED = { key: 0, label: 'Sem classificação', sub: 'marcas sem tier', tone: 'border-t-slate-400' };

export const TIER_OPTIONS = [
  { value: 'premium', label: 'Premium (tier 1)' },
  { value: 'quality', label: 'Quality (tier 2)' },
  { value: 'budget', label: 'Budget (tier 3)' },
];

export function tierFromCategory(category) {
  const c = String(category || '').trim().toLowerCase();
  if (['premium', 'tier 1', 'tier1', '1'].includes(c)) return 1;
  if (['quality', 'mid', 'mid-range', 'tier 2', 'tier2', '2'].includes(c)) return 2;
  if (['budget', 'economy', 'tier 3', 'tier3', '3'].includes(c)) return 3;
  return 0;
}

const key = (b) => String(b || '').toUpperCase().replace(/[^A-Z0-9]/g, '');

export function buildTierMap(rows) {
  const map = new Map();
  (rows || []).forEach((r) => {
    const t = tierFromCategory(r.category);
    if (t) map.set(key(r.brand), t);
  });
  return map;
}

export function tierOf(brand, map) {
  return map?.get(key(brand)) || 0;
}

// Divide ofertas pelos tiers; a coluna "Sem classificação" só existe se tiver ofertas.
export function splitByTier(offers, map) {
  const cols = new Map([[1, []], [2, []], [3, []], [0, []]]);
  (offers || []).forEach((o) => cols.get(tierOf(o.brand, map)).push(o));
  return [...TIERS, UNCLASSIFIED]
    .map((t) => ({ ...t, offers: cols.get(t.key) }))
    .filter((t) => t.key !== 0 || t.offers.length > 0);
}
