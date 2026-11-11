import React, { useMemo, useState } from 'react';
import { TrendingDown } from 'lucide-react';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from './ui/table';
import { MatchBadge, StaleBadge, ToneBadge } from './badges';
import { NativeSelect } from './common';
import { formatAge, formatDateTime, formatPct, formatPrice } from '@/lib/format';
import { supplierSearchUrl } from '@/lib/supplierLinks';

export const REASON_LABELS = {
  size_mismatch: 'Medida diferente',
  brand_mismatch: 'Marca diferente',
  model_mismatch: 'Modelo diferente',
  load_mismatch: 'Índice de carga diferente',
  load_index_mismatch: 'Índice de carga diferente',
  speed_mismatch: 'Índice de velocidade diferente',
  speed_index_mismatch: 'Índice de velocidade diferente',
  xl_mismatch: 'XL diferente',
  runflat_mismatch: 'RunFlat diferente',
  season_mismatch: 'Estação diferente',
  homologation_mismatch: 'Homologação diferente',
  condition_mismatch: 'Estado (DEMO/usado) diferente',
  commercial_mismatch: 'Tipo C (comercial) diferente',
};

export function reasonText(code) {
  return REASON_LABELS[code] || code;
}

export const isExact = (item) => item?.match_class === 'MATCH_EXACTO';

// Poupança só é válida para correspondência exacta (contrato da recuperação).
export function exactSaving(item) {
  if (!isExact(item)) return null;
  const eur = item.economia_euro;
  if (eur === null || eur === undefined) return null;
  return { eur, pct: item.economia_percent ?? null };
}

export function summarizeResults(results) {
  const list = results || [];
  const exact = list.filter(isExact);
  const withSaving = exact.filter((r) => (exactSaving(r)?.eur || 0) > 0);
  return {
    total: list.length,
    exact: exact.length,
    found: withSaving.length,
    savings: withSaving.reduce((acc, r) => acc + (r.economia_euro || 0), 0),
  };
}

function sortResults(list, order) {
  switch (order) {
    case 'poupanca_desc':
      return [...list].sort((a, b) => (exactSaving(b)?.eur ?? -Infinity) - (exactSaving(a)?.eur ?? -Infinity));
    case 'medida_asc':
      return [...list].sort((a, b) => parseInt((a.medida || '').replace(/\D/g, '') || '0', 10) - parseInt((b.medida || '').replace(/\D/g, '') || '0', 10));
    default:
      return list;
  }
}

function SupplierLink({ name, medida }) {
  if (!name) return '—';
  const url = supplierSearchUrl(name, medida);
  return url ? (
    <a href={url} target="_blank" rel="noopener noreferrer" title="Abrir pesquisa no fornecedor" className="hover:underline whitespace-nowrap">{name}</a>
  ) : <span className="whitespace-nowrap">{name}</span>;
}

export default function ComparisonResultsTable({ results, showRef = false }) {
  const [onlyExact, setOnlyExact] = useState(false);
  const [order, setOrder] = useState('original');

  const rows = useMemo(() => {
    const base = onlyExact ? (results || []).filter(isExact) : (results || []);
    return sortResults(base, order);
  }, [results, onlyExact, order]);

  return (
    <div className="space-y-3">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={onlyExact} onChange={(e) => setOnlyExact(e.target.checked)} data-testid="only-exact" />
          Só correspondências exactas
        </label>
        <NativeSelect value={order} onChange={(e) => setOrder(e.target.value)} className="sm:w-56" aria-label="Ordenação">
          <option value="original">Ordem original</option>
          <option value="poupanca_desc">Maior poupança (exactos)</option>
          <option value="medida_asc">Medida (menor → maior)</option>
        </NativeSelect>
        <span className="text-xs text-muted-foreground">{rows.length} linhas</span>
      </div>
      <div className="max-h-[600px] overflow-auto border rounded-md">
        <Table>
          <TableHeader className="sticky top-0 bg-card z-10">
            <TableRow>
              {showRef && <TableHead>Ref</TableHead>}
              <TableHead>Medida</TableHead>
              <TableHead>Marca</TableHead>
              <TableHead>Modelo</TableHead>
              <TableHead>Índice</TableHead>
              <TableHead>Correspondência</TableHead>
              <TableHead>Encontrado</TableHead>
              <TableHead className="text-right">Meu preço</TableHead>
              <TableHead className="text-right">Melhor preço</TableHead>
              <TableHead>Fornecedor</TableHead>
              <TableHead className="text-right">Poupança</TableHead>
              <TableHead>Preços de</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((item, index) => {
              const saving = exactSaving(item);
              const positive = saving && saving.eur > 0;
              const reasons = (item.match_details?.length ? item.match_details : (item.match_reasons || []).map(reasonText));
              return (
                <TableRow
                  key={item.id || index}
                  className={positive ? 'bg-emerald-50 dark:bg-emerald-500/10 hover:bg-emerald-100 dark:hover:bg-emerald-500/20' : ''}
                  data-testid={`result-row-${index}`}
                >
                  {showRef && <TableCell className="font-mono text-xs">{item.ref_id}</TableCell>}
                  <TableCell className="font-mono whitespace-nowrap">{item.medida}</TableCell>
                  <TableCell className="whitespace-nowrap">{item.marca || '—'}</TableCell>
                  <TableCell className="max-w-[140px] truncate text-muted-foreground" title={item.modelo}>{item.modelo || '—'}</TableCell>
                  <TableCell className="font-mono text-muted-foreground">{item.indice || '—'}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {item.match_class
                        ? <MatchBadge matchClass={item.match_class} details={reasons} />
                        : !item.updating && <ToneBadge>Sem ofertas</ToneBadge>}
                      {item.status === 'stale' && !item.updating && <StaleBadge />}
                      {item.updating && <ToneBadge tone="blue">A actualizar</ToneBadge>}
                    </div>
                  </TableCell>
                  <TableCell className="max-w-[180px]">
                    <div className="truncate font-medium" title={item.modelo_encontrado}>
                      {[item.melhor_marca && item.melhor_marca !== item.marca ? item.melhor_marca : null, item.modelo_encontrado].filter(Boolean).join(' ') || '—'}
                    </div>
                    {item.indice_encontrado && <div className="font-mono text-xs text-muted-foreground">{item.indice_encontrado}</div>}
                  </TableCell>
                  <TableCell className="text-right font-mono whitespace-nowrap">{formatPrice(item.meu_preco)}</TableCell>
                  <TableCell className="text-right font-mono whitespace-nowrap">{formatPrice(item.melhor_preco)}</TableCell>
                  <TableCell className="text-sm"><SupplierLink name={item.melhor_fornecedor} medida={item.medida} /></TableCell>
                  <TableCell className="text-right whitespace-nowrap">
                    {saving ? (
                      <span className={positive ? 'text-emerald-700 dark:text-emerald-400 font-bold' : 'text-muted-foreground'}>
                        {positive && <TrendingDown className="inline w-3 h-3 mr-1" />}
                        {formatPrice(saving.eur)}
                        {saving.pct !== null && <span className="text-xs font-normal"> ({formatPct(saving.pct)})</span>}
                      </span>
                    ) : item.match_class && !isExact(item) ? (
                      <span className="text-xs text-muted-foreground italic">não comparável</span>
                    ) : '—'}
                  </TableCell>
                  <TableCell className="text-xs whitespace-nowrap">
                    {item.prices_at ? (
                      <>
                        <div className="font-mono">{formatDateTime(item.prices_at)}</div>
                        <div className="text-muted-foreground">{formatAge(item.prices_at)}</div>
                      </>
                    ) : '—'}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
