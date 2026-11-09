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
      className="inline-flex items-center gap-1 rounded border px-2 py-0.5 text-xs whitespace-nowrap hover:bg-muted">
      {open ? 'Ver menos' : `Ver mais (${count})`} <Icon size={12} />
    </button>
  );
}

// Tabela de ofertas (desktop) + cartões (mobile). Com `grouped`, uma linha por pneu (a oferta
// mais barata) e "Ver mais" mostra os restantes fornecedores desse pneu.
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
        o.fresh === false && !sub && 'opacity-75',
        expanded && 'bg-indigo-100/80 dark:bg-indigo-500/20 border-b-0 font-semibold hover:bg-indigo-100/80 dark:hover:bg-indigo-500/20',
        sub && 'bg-indigo-50 dark:bg-indigo-500/10 hover:bg-indigo-100/60 dark:hover:bg-indigo-500/15 text-sm border-b border-indigo-100 dark:border-indigo-500/20',
        sub && last && 'border-b-2 border-b-indigo-200 dark:border-b-indigo-500/30',
        highlightId && o.id === highlightId && 'bg-emerald-50 dark:bg-emerald-500/10',
      )}
    >
      <TableCell className={cn('font-medium whitespace-nowrap', expanded && 'border-l-4 border-l-indigo-600 dark:border-l-indigo-400', sub && 'border-l-4 border-l-indigo-600/70 dark:border-l-indigo-400/70 pl-6 font-normal text-indigo-700/80 dark:text-indigo-300/80 text-xs uppercase tracking-wide')}>{sub ? 'outro fornecedor' : (o.brand || '—')}</TableCell>
      <TableCell className="max-w-[220px]">
        <WithTooltip content={o.description}>
          <span className={cn('block truncate cursor-help', sub && 'text-muted-foreground')} title={o.description || undefined}>{o.model || o.description || '—'}</span>
        </WithTooltip>
      </TableCell>
      <TableCell className="font-mono text-xs whitespace-nowrap">{formatLoadSpeed(o)}</TableCell>
      <TableCell><OfferFlags offer={o} /></TableCell>
      {showMatch && <TableCell className="max-w-[260px]"><MatchCell offer={o} /></TableCell>}
      <TableCell className="text-sm"><SupplierCell offer={o} /></TableCell>
      <TableCell className="text-right font-mono font-semibold whitespace-nowrap">{formatPrice(o.price, o.currency)}</TableCell>
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

  const mobileCard = (o, { sub = false, group = null } = {}) => (
    <div
      key={offerKey(o)}
      className={cn('p-3 space-y-2', sub && 'bg-indigo-50/50 dark:bg-indigo-500/[0.07] border-l-[3px] border-indigo-300 dark:border-indigo-400/60 pl-5', group && open.has(group.key) && 'bg-indigo-50/70 dark:bg-indigo-500/10 border-l-[3px] border-indigo-500', highlightId && o.id === highlightId && 'bg-emerald-50 dark:bg-emerald-500/10')}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold">{o.brand || '—'} <span className="font-normal">{o.model || ''}</span></p>
          <p className="text-xs text-muted-foreground break-words">{o.description}</p>
        </div>
        <p className="font-mono font-bold text-lg whitespace-nowrap">{formatPrice(o.price, o.currency)}</p>
      </div>
      <div className="flex flex-wrap items-center gap-1 text-xs">
        <span className="font-mono">{formatLoadSpeed(o)}</span>
        <OfferFlags offer={o} />
      </div>
      {showMatch && <MatchCell offer={o} />}
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <SupplierCell offer={o} />
        <StockBadge status={o.stock_status} qty={o.stock_qty} location={o.stock_location || o.delivery_info} />
      </div>
      <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span className="flex items-center gap-2">
          {formatDateTime(o.last_seen_at)} · {o.age_hours != null ? formatAge(o.age_hours) : formatAge(o.last_seen_at)}
          {o.fresh === false && <StaleBadge />}
        </span>
        {group && <MoreButton count={group.others.length} open={open.has(group.key)} onClick={() => toggle(group.key)} />}
      </div>
    </div>
  );

  return (
    <div data-testid={testId}>
      <div className="hidden md:block">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Marca</TableHead>
              <TableHead>Modelo</TableHead>
              <TableHead>Índice</TableHead>
              <TableHead>Características</TableHead>
              {showMatch && <TableHead>Correspondência</TableHead>}
              <TableHead>Fornecedor</TableHead>
              <TableHead className="text-right">
                {onToggleSort ? (
                  <button className="inline-flex items-center gap-1 hover:text-foreground" onClick={onToggleSort} data-testid="sort-price">
                    Preço <SortIcon size={12} />
                  </button>
                ) : 'Preço'}
              </TableHead>
              <TableHead>Stock</TableHead>
              <TableHead>Actualizado</TableHead>
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

      <div className="md:hidden divide-y divide-border">
        {onToggleSort && (
          <div className="flex justify-end p-2">
            <button className="inline-flex items-center gap-1 text-xs text-muted-foreground" onClick={onToggleSort}>
              Ordenar por preço <SortIcon size={12} />
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
