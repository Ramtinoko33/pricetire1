import React, { useMemo, useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { OfferFlags, StaleBadge, StockBadge } from './badges';
import { formatAge, formatLoadSpeed, formatPrice } from '@/lib/format';
import { groupOffers } from '@/lib/groupOffers';
import { splitByTier } from '@/lib/tiers';
import { cn } from '@/lib/utils';

function OtherRow({ o }) {
  return (
    <div className="flex items-center justify-between gap-2 py-1 text-xs" data-testid="tier-other">
      <span className="truncate">{o.supplier_name}</span>
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
    <div className={cn('rounded-md border bg-card p-3 space-y-1.5', o.fresh === false && 'opacity-75')} data-testid="tier-card">
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
        <span className="truncate">{o.supplier_name}</span>
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
        <div className="border-t pt-1 divide-y divide-border">
          {group.others.map((x) => <OtherRow key={x.id ?? `${x.supplier_id}-${x.price}`} o={x} />)}
        </div>
      )}
    </div>
  );
}

// Vista comparativa: uma coluna por tier, cada uma com scroll próprio.
export default function TierColumns({ offers, tierMap, sortDir = 'asc', grouped = true }) {
  const columns = useMemo(() => splitByTier(offers, tierMap).map((c) => ({
    ...c,
    groups: grouped
      ? groupOffers(c.offers, sortDir)
      : groupOffers(c.offers, sortDir).flatMap((g) => [g.best, ...g.others]).map((o) => ({ key: o.id, best: o, others: [] })),
  })), [offers, tierMap, sortDir, grouped]);

  return (
    <div
      className="grid gap-3 p-3 overflow-x-auto"
      style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(260px, 1fr))` }}
      data-testid="tier-columns"
    >
      {columns.map((c) => {
        const best = c.offers.reduce((m, o) => (o.price != null && (m == null || o.price < m) ? o.price : m), null);
        return (
          <section key={c.key} className={cn('rounded-md border border-t-4 bg-muted/30 flex flex-col min-w-0', c.tone)} data-testid={`tier-col-${c.key}`}>
            <header className="px-3 py-2 border-b bg-card rounded-t-md">
              <p className="text-sm font-semibold">{c.label} <span className="text-xs font-normal text-muted-foreground">{c.sub}</span></p>
              <p className="text-xs text-muted-foreground">
                {c.groups.length} pneu(s) · {c.offers.length} oferta(s){best != null ? ` · desde ${formatPrice(best)}` : ''}
              </p>
            </header>
            <div className="p-2 space-y-2 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 260px)', minHeight: '200px' }}>
              {c.groups.length === 0
                ? <p className="text-xs text-muted-foreground p-2">Sem ofertas nesta categoria.</p>
                : c.groups.map((g) => <TyreCard key={g.key} group={g} />)}
            </div>
          </section>
        );
      })}
    </div>
  );
}
