import React, { useMemo, useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { OfferFlags, StaleBadge, StockBadge } from './badges';
import { formatAge, formatLoadSpeed, formatPrice } from '@/lib/format';
import { groupOffers } from '@/lib/groupOffers';
import { splitByTier } from '@/lib/tiers';
import { cn } from '@/lib/utils';
import SupplierLink from './SupplierLink';
import MultiBrandSelect from './MultiBrandSelect';

function OtherRow({ o }) {
  return (
    <div className="flex items-center justify-between gap-2 py-1.5 text-xs" data-testid="tier-other">
      <SupplierLink offer={o} className="truncate" />
      <span className="flex items-center gap-2 flex-shrink-0">
        <StockBadge status={o.stock_status} qty={o.stock_qty} location={o.stock_location || o.delivery_info} />
        <span className="font-bold tabular-nums">{formatPrice(o.price, o.currency)}</span>
      </span>
    </div>
  );
}

function TyreCard({ group }) {
  const [open, setOpen] = useState(false);
  const o = group.best;
  const Icon = open ? ChevronUp : ChevronDown;
  return (
    <div className={cn('rounded-lg border bg-card p-3 space-y-2 transition-shadow', o.fresh === false && !open && 'text-foreground/80', open && 'border-primary ring-1 ring-primary shadow-overlay')} data-testid="tier-card">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-bold uppercase" title={o.description || undefined}>{o.brand}</p>
          <p className="truncate text-xs uppercase text-muted-foreground" title={o.description || undefined}>{o.model}</p>
          <div className="mt-1 flex flex-wrap items-center gap-1 text-xs">
            <span className="mr-1 font-semibold tabular-nums">{formatLoadSpeed(o)}</span>
            <OfferFlags offer={o} />
          </div>
        </div>
        <p className="whitespace-nowrap text-base font-extrabold tabular-nums tracking-[-0.02em]">{formatPrice(o.price, o.currency)}</p>
      </div>
      <div className="flex items-center justify-between gap-2 text-xs">
        <SupplierLink offer={o} className="truncate" />
        <StockBadge status={o.stock_status} qty={o.stock_qty} location={o.stock_location || o.delivery_info} />
      </div>
      <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">{o.age_hours != null ? formatAge(o.age_hours) : formatAge(o.last_seen_at)}{o.fresh === false && <StaleBadge />}</span>
        {group.others.length > 0 && (
          <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} data-testid="tier-more"
            className={cn('inline-flex min-h-7 items-center gap-1 rounded-md border px-2 font-semibold', open ? 'border-primary bg-primary text-primary-foreground hover:bg-primary-hover' : 'border-input text-foreground hover:border-primary hover:bg-accent')}>
            {open ? 'Ver menos' : `Ver mais (${group.others.length})`} <Icon size={12} />
          </button>
        )}
      </div>
      {open && (
        <div className="-mx-3 -mb-3 mt-2 divide-y divide-primary/10 rounded-b-lg border-t border-primary/20 bg-accent px-3 pb-2 pt-1.5">
          <p className="pb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-primary">Outros fornecedores</p>
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
  const [picked, setPicked] = useState([]);
  const brands = useMemo(() => brandCounts(col.offers), [col.offers]);
  const active = useMemo(() => picked.filter((b) => brands.some((x) => x.brand === b)), [picked, brands]);
  const offers = useMemo(() => {
    if (!active.length) return col.offers;
    const set = new Set(active);
    return col.offers.filter((o) => set.has(o.brand || '—'));
  }, [col.offers, active]);
  const groups = useMemo(() => {
    const g = groupOffers(offers, sortDir);
    return grouped ? g : g.flatMap((x) => [x.best, ...x.others]).map((o) => ({ key: o.id, best: o, others: [] }));
  }, [offers, sortDir, grouped]);
  const best = offers.reduce((m, o) => (o.price != null && (m == null || o.price < m) ? o.price : m), null);

  return (
    <section className={cn('flex min-w-0 flex-col rounded-lg border border-t-[3px] bg-muted/50', col.tone)} data-testid={`tier-col-${col.key}`}>
      <header className="space-y-2 rounded-t-lg border-b bg-card px-3 py-3">
        <p className="text-sm font-bold">{col.label} <span className="ml-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">{col.sub}</span></p>
        <p className="text-xs tabular-nums text-muted-foreground">
          {groups.length} pneu(s) · {offers.length} oferta(s){best != null ? ` · desde ${formatPrice(best)}` : ''}
        </p>
        <MultiBrandSelect
          id={`tier-brand-${col.key}`}
          testId={`tier-brand-${col.key}`}
          value={active}
          onChange={setPicked}
          options={brands.map((b) => ({ value: b.brand, count: b.count }))}
          placeholder={`Todas as marcas (${brands.length})`}
          compact
        />
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
