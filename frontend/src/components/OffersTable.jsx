import React, { useState } from 'react';
import { ArrowDown, ArrowUp, ChevronDown, ChevronUp } from 'lucide-react';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { FreshnessCell, MatchBadge, OfferFlags, StockBadge, WithTooltip, StaleBadge } from './badges';
import { formatAge, formatDateTime, formatLoadSpeed, formatPrice } from '@/lib/format';
import SupplierLink from './SupplierLink';
import { cn } from '@/lib/utils';
import { groupOffers } from '@/lib/groupOffers';

export function sortOffersByPrice(offers, dir = 'asc') {
  const mult = dir === 'desc' ? -1 : 1;
  return [...(offers || [])].sort((a, b) => {
    const pa = a.price ?? null;
    const pb = b.price ?? null;
    if (pa === null && pb === null) return 0;
    if (pa === null) return 1;
    if (pb === null) return -1;
    return (pa - pb) * mult;
  });
}

function SupplierCell({ offer }) {
  return <SupplierLink offer={offer} />;
}

function MatchCell({ offer }) {
  if (!offer.match) return null;
  return (
    <div className="space-y-1">
      <MatchBadge matchClass={offer.match.match_class} details={offer.match.details} reasons={offer.match.reasons} />
      {offer.match.match_class !== 'MATCH_EXACTO' && offer.match.details?.length > 0 && (
        <ul className="text-xs text-muted-foreground list-disc pl-4">
          {offer.match.details.map((d, i) => <li key={i}>{d}</li>)}
        </ul>
      )}
    </div>
  );
}

const offerKey = (o) => o.id ?? `${o.supplier_id}-${o.supplier_ref}-${o.price}`;

function MoreButton({ count, open, onClick }) {
  if (!count) return null;
  const Icon = open ? ChevronUp : ChevronDown;
  return (
    <button type="button" onClick={onClick} aria-expanded={open} data-testid="offers-more"
      className={cn(
        'inline-flex min-h-8 items-center gap-1 whitespace-nowrap rounded-md border px-2.5 text-xs font-semibold transition-colors',
        open ? 'border-primary bg-primary text-primary-foreground hover:bg-primary-hover' : 'border-input bg-card text-foreground hover:border-primary hover:bg-accent',
      )}>
      {open ? 'Ver menos' : `Ver mais (${count})`} <Icon size={13} aria-hidden="true" />
    </button>
  );
}

function TyreName({ o, sub }) {
  return (
    <div className="min-w-0">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        {sub
          ? <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-primary">Outro fornecedor</span>
          : <span className="font-bold uppercase tracking-[0.01em]">{o.brand || '—'}</span>}
        {!sub && <OfferFlags offer={o} />}
      </div>
      <WithTooltip content={o.description}>
        <span className="mt-0.5 block max-w-[280px] truncate text-xs uppercase text-muted-foreground cursor-help" title={o.description || undefined}>
          {o.model || o.description || '—'}
        </span>
      </WithTooltip>
    </div>
  );
}

// Tabela de ofertas (ecrãs largos) + cartões (tablet/mobile). Com `grouped`, uma linha por pneu
// (a oferta mais barata) e "Ver mais" mostra os restantes fornecedores desse pneu.
export default function OffersTable({ offers, sortDir = 'asc', onToggleSort, showMatch = false, highlightId = null, grouped = false, testId = 'offers-table' }) {
  const rows = offers || [];
  const SortIcon = sortDir === 'desc' ? ArrowDown : ArrowUp;
  const [open, setOpen] = useState(() => new Set());
  const groups = grouped
    ? groupOffers(rows, sortDir)
    : rows.map((o) => ({ key: offerKey(o), best: o, others: [] }));
  const toggle = (k) => setOpen((prev) => {
    const next = new Set(prev);
    if (next.has(k)) next.delete(k); else next.add(k);
    return next;
  });

  const desktopRow = (o, { sub = false, group = null, last = false } = {}) => {
    const expanded = Boolean(group && open.has(group.key));
    return (
    <TableRow
      key={offerKey(o)}
      data-testid={sub ? 'offer-subrow' : 'offer-row'}
      className={cn(
        o.fresh === false && !sub && !expanded && 'text-foreground/80',
        expanded && 'bg-accent hover:bg-accent border-b-0',
        sub && 'bg-accent/45 hover:bg-accent/70 border-b border-primary/10',
        sub && last && 'border-b-2 border-b-primary/30',
        highlightId && o.id === highlightId && 'bg-success-subtle hover:bg-success-subtle',
      )}
    >
      <TableCell className={cn('py-3', expanded && 'shadow-[inset_4px_0_0_hsl(var(--primary))]', sub && 'pl-8 shadow-[inset_4px_0_0_hsl(var(--primary)/0.55)]')}>
        <TyreName o={o} sub={sub} />
      </TableCell>
      <TableCell className="whitespace-nowrap text-[13px] font-medium tabular-nums">{formatLoadSpeed(o)}</TableCell>
      {showMatch && <TableCell className="min-w-[260px] max-w-[340px]"><MatchCell offer={o} /></TableCell>}
      <TableCell className="text-[13px]"><SupplierCell offer={o} /></TableCell>
      <TableCell className={cn('whitespace-nowrap text-right tabular-nums tracking-[-0.02em]', sub ? 'text-[15px] font-bold' : 'text-base font-extrabold')}>{formatPrice(o.price, o.currency)}</TableCell>
      <TableCell><StockBadge status={o.stock_status} qty={o.stock_qty} location={o.stock_location || o.delivery_info} /></TableCell>
      <TableCell><FreshnessCell at={o.last_seen_at} ageHours={o.age_hours} fresh={o.fresh} /></TableCell>
      {grouped && (
        <TableCell className="text-right">
          {group && <MoreButton count={group.others.length} open={open.has(group.key)} onClick={() => toggle(group.key)} />}
        </TableCell>
      )}
    </TableRow>
    );
  };

  const mobileCard = (o, { sub = false, group = null } = {}) => {
    const expanded = Boolean(group && open.has(group.key));
    return (
    <div
      key={offerKey(o)}
      data-testid={sub ? 'offer-card-sub' : 'offer-card'}
      className={cn(
        'grid gap-x-6 gap-y-2.5 px-4 py-3.5 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_auto] sm:items-center sm:px-5',
        sub && 'bg-accent/45 pl-7 shadow-[inset_3px_0_0_hsl(var(--primary)/0.55)] sm:pl-8',
        expanded && 'bg-accent shadow-[inset_3px_0_0_hsl(var(--primary))]',
        highlightId && o.id === highlightId && 'bg-success-subtle',
      )}
    >
      <div className="flex min-w-0 items-start justify-between gap-3 sm:block">
        <div className="min-w-0">
          {sub
            ? <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-primary">Outro fornecedor</p>
            : <p className="font-bold uppercase">{o.brand || '—'}</p>}
          <p className="text-xs uppercase text-muted-foreground">{o.model || ''}</p>
          <p className="mt-0.5 text-xs text-muted-foreground break-words">{o.description}</p>
          <div className="mt-1.5 flex flex-wrap items-center gap-1 text-xs">
            <span className="mr-1 font-semibold tabular-nums">{formatLoadSpeed(o)}</span>
            <OfferFlags offer={o} />
          </div>
          {showMatch && <div className="mt-2"><MatchCell offer={o} /></div>}
        </div>
        <p className="whitespace-nowrap text-lg font-extrabold tabular-nums tracking-[-0.02em] sm:hidden">{formatPrice(o.price, o.currency)}</p>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5 text-xs sm:flex-col sm:items-start sm:justify-center">
        <span className="text-[13px] font-medium"><SupplierCell offer={o} /></span>
        <StockBadge status={o.stock_status} qty={o.stock_qty} location={o.stock_location || o.delivery_info} />
        <span className="flex w-full flex-wrap items-center gap-2 text-muted-foreground sm:w-auto">
          <span className="tabular-nums">{formatDateTime(o.last_seen_at)}</span> · {o.age_hours != null ? formatAge(o.age_hours) : formatAge(o.last_seen_at)}
          {o.fresh === false && <StaleBadge />}
        </span>
      </div>
      <div className="flex items-center justify-end gap-3 sm:flex-col sm:items-end sm:justify-center">
        <p className="hidden whitespace-nowrap text-lg font-extrabold tabular-nums tracking-[-0.02em] sm:block">{formatPrice(o.price, o.currency)}</p>
        {group && <MoreButton count={group.others.length} open={expanded} onClick={() => toggle(group.key)} />}
      </div>
    </div>
    );
  };

  return (
    <div data-testid={testId}>
      <div className={showMatch ? 'hidden 2xl:block' : 'hidden xl:block'}>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Pneu / Modelo</TableHead>
              <TableHead>Índice</TableHead>
              {showMatch && <TableHead>Correspondência</TableHead>}
              <TableHead>Fornecedor</TableHead>
              <TableHead className="text-right" aria-sort={onToggleSort ? (sortDir === 'desc' ? 'descending' : 'ascending') : undefined}>
                {onToggleSort ? (
                  <button className="inline-flex items-center gap-1 rounded-sm hover:text-foreground" onClick={onToggleSort} data-testid="sort-price">
                    Preço de compra <SortIcon size={12} aria-hidden="true" />
                  </button>
                ) : 'Preço de compra'}
              </TableHead>
              <TableHead>Stock</TableHead>
              <TableHead>Recolha do preço</TableHead>
              {grouped && <TableHead className="text-right">Fornecedores</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {groups.map((g) => (
              <React.Fragment key={g.key}>
                {desktopRow(g.best, { group: grouped ? g : null })}
                {open.has(g.key) && g.others.map((o, i) => desktopRow(o, { sub: true, last: i === g.others.length - 1 }))}
              </React.Fragment>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className={cn('divide-y divide-border', showMatch ? '2xl:hidden' : 'xl:hidden')}>
        {onToggleSort && (
          <div className="flex items-center justify-between bg-muted/70 px-4 py-2 sm:px-5">
            <span className="text-xs font-semibold text-muted-foreground">{groups.length} {grouped ? 'pneus' : 'ofertas'}</span>
            <button className="inline-flex min-h-8 items-center gap-1 rounded-md px-2 text-xs font-semibold text-muted-foreground hover:text-foreground" onClick={onToggleSort}>
              Preço de compra <SortIcon size={12} aria-hidden="true" />
            </button>
          </div>
        )}
        {groups.map((g) => (
          <React.Fragment key={g.key}>
            {mobileCard(g.best, { group: grouped ? g : null })}
            {open.has(g.key) && g.others.map((o) => mobileCard(o, { sub: true }))}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}
