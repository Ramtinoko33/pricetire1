import React, { useMemo, useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { OfferFlags, StaleBadge, StockBadge } from './badges';
import { formatAge, formatLoadSpeed, formatPrice } from '@/lib/format';
import { groupOffers } from '@/lib/groupOffers';
import { splitByTier } from '@/lib/tiers';
import { cn } from '@/lib/utils';
import SupplierLink from './SupplierLink';

function OtherRow({ o }) {
  return (
    <div className="flex items-center justify-between gap-2 py-1 text-xs" data-testid="tier-other">
      <SupplierLink offer={o} className="truncate" />
      <span className="flex items-center gap-2 flex-shrink-0">
        <StockBadge status={o.stock_status} qty={o.stock_qty} location={o.stock_location || o.delivery_info} />
        <span className="font-mono font-semibold">{formatPrice(o.price, o.currency)}</span>
      </span>
    </div>
  );
}

function TyreCard({ group }) {
  const [open, setOpen] = useState(false);
  const o = group.best;
  const Icon = open ? ChevronUp : ChevronDown;
  return (
    <div className={cn('rounded-md border bg-card p-3 space-y-1.5 transition-shadow', o.fresh === false && !open && 'opacity-75', open && 'ring-2 ring-indigo-500/70 shadow-md')} data-testid="tier-card">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold truncate" title={o.description || undefined}>{o.brand} <span className="font-normal">{o.model}</span></p>
          <div className="flex flex-wrap items-center gap-1 text-xs">
            <span className="font-mono">{formatLoadSpeed(o)}</span>
            <OfferFlags offer={o} />
          </div>
        </div>
        <p className="font-mono font-bold whitespace-nowrap">{formatPrice(o.price, o.currency)}</p>
      </div>
      <div className="flex items-center justify-between gap-2 text-xs">
        <SupplierLink offer={o} className="truncate" />
        <StockBadge status={o.stock_status} qty={o.stock_qty} location={o.stock_location || o.delivery_info} />
      </div>
      <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">{o.age_hours != null ? formatAge(o.age_hours) : formatAge(o.last_seen_at)}{o.fresh === false && <StaleBadge />}</span>
        {group.others.length > 0 && (
          <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} data-testid="tier-more"
            className="inline-flex items-center gap-1 rounded border px-1.5 py-0.5 hover:bg-muted text-foreground">
            {open ? 'Ver menos' : `Ver mais (${group.others.length})`} <Icon size={12} />
          </button>
        )}
      </div>
      {open && (
        <div className="-mx-3 -mb-3 mt-2 px-3 pb-2 pt-1 rounded-b-md bg-indigo-100/70 dark:bg-indigo-500/15 border-t border-indigo-200 dark:border-indigo-500/30 divide-y divide-indigo-100 dark:divide-indigo-500/15">
          <p className="text-[10px] uppercase tracking-wide text-indigo-700/80 dark:text-indigo-300/80 pt-1">Outros fornecedores</p>
          {group.others.map((x) => <OtherRow key={x.id ?? `${x.supplier_id}-${x.price}`} o={x} />)}
        </div>
      )}
    </div>
  );
}

// Marcas de uma coluna, por ordem alfabética, com o número de ofertas.
export function brandCounts(offers) {
  const m = new Map();
  (offers || []).forEach((o) => {
    const b = o.brand || '—';
    m.set(b, (m.get(b) || 0) + 1);
  });
  return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0], 'pt')).map(([brand, count]) => ({ brand, count }));
}

function TierColumn({ col, sortDir, grouped }) {
  const [brand, setBrand] = useState('');
  const brands = useMemo(() => brandCounts(col.offers), [col.offers]);
  const active = brand && brands.some((b) => b.brand === brand) ? brand : '';
  const offers = useMemo(() => (active ? col.offers.filter((o) => (o.brand || '—') === active) : col.offers), [col.offers, active]);
  const groups = useMemo(() => {
    const g = groupOffers(offers, sortDir);
    return grouped ? g : g.flatMap((x) => [x.best, ...x.others]).map((o) => ({ key: o.id, best: o, others: [] }));
  }, [offers, sortDir, grouped]);
  const best = offers.reduce((m, o) => (o.price != null && (m == null || o.price < m) ? o.price : m), null);

  return (
    <section className={cn('rounded-md border border-t-4 bg-muted/30 flex flex-col min-w-0', col.tone)} data-testid={`tier-col-${col.key}`}>
      <header className="px-3 py-2 border-b bg-card rounded-t-md space-y-1.5">
        <p className="text-sm font-semibold">{col.label} <span className="text-xs font-normal text-muted-foreground">{col.sub}</span></p>
        <p className="text-xs text-muted-foreground">
          {groups.length} pneu(s) · {offers.length} oferta(s){best != null ? ` · desde ${formatPrice(best)}` : ''}
        </p>
        <select
          value={active}
          onChange={(e) => setBrand(e.target.value)}
          aria-label={`Filtrar ${col.label} por marca`}
          data-testid={`tier-brand-${col.key}`}
          className={cn('w-full h-8 rounded-md border bg-background px-2 text-xs', active && 'border-indigo-400 ring-1 ring-indigo-300 font-medium')}
        >
          <option value="">Todas as marcas ({brands.length})</option>
          {brands.map((b) => <option key={b.brand} value={b.brand}>{b.brand} ({b.count})</option>)}
        </select>
      </header>
      <div className="p-2 space-y-2 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 260px)', minHeight: '200px' }}>
        {groups.length === 0
          ? <p className="text-xs text-muted-foreground p-2">Sem ofertas nesta categoria.</p>
          : groups.map((g) => <TyreCard key={g.key} group={g} />)}
      </div>
    </section>
  );
}

// Vista comparativa: uma coluna por tier, cada uma com scroll e filtro de marca próprios.
export default function TierColumns({ offers, tierMap, sortDir = 'asc', grouped = true }) {
  const columns = useMemo(() => splitByTier(offers, tierMap), [offers, tierMap]);
  return (
    <div
      className="grid gap-3 p-3 overflow-x-auto"
      style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(260px, 1fr))` }}
      data-testid="tier-columns"
    >
      {columns.map((c) => <TierColumn key={c.key} col={c} sortDir={sortDir} grouped={grouped} />)}
    </div>
  );
}
