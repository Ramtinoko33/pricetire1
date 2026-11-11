import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { ExternalLink, Loader2, Search } from 'lucide-react';
import { toast } from 'sonner';
import { brandsAPI } from '@/lib/api';
import { errorMessage, formatDateTime } from '@/lib/format';
import { TIER_OPTIONS } from '@/lib/tiers';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { EmptyState, ErrorState, PageHeader, TableSkeleton } from '@/components/common';
import { WithTooltip } from '@/components/badges';
import { cn } from '@/lib/utils';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import MarcasAssociacoes from './MarcasAssociacoes';

const TIER_STYLE = {
  premium: 'border-violet-300 bg-violet-50 text-violet-800 dark:bg-violet-500/15 dark:text-violet-200 dark:border-violet-500/40',
  quality: 'border-blue-300 bg-blue-50 text-blue-800 dark:bg-blue-500/15 dark:text-blue-200 dark:border-blue-500/40',
  budget: 'border-emerald-300 bg-emerald-50 text-emerald-800 dark:bg-emerald-500/15 dark:text-emerald-200 dark:border-emerald-500/40',
};

const FILTERS = [
  { key: 'all', label: 'Todas' },
  { key: 'premium', label: 'Premium' },
  { key: 'quality', label: 'Quality' },
  { key: 'budget', label: 'Budget' },
  { key: 'none', label: 'Sem classificação' },
];

export function filterBrands(rows, query, tier) {
  const q = String(query || '').trim().toUpperCase();
  return (rows || []).filter((r) => {
    if (q && !r.brand.toUpperCase().includes(q)) return false;
    if (tier === 'none') return !r.category;
    if (tier !== 'all') return r.category === tier;
    return true;
  });
}

const Marcas = () => {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [tier, setTier] = useState('all');
  const [saving, setSaving] = useState('');
  const [tab, setTab] = useState('tiers');
  const [pending, setPending] = useState(0);

  const load = useCallback(async () => {
    try {
      const { data } = await brandsAPI.overview();
      setRows(Array.isArray(data) ? data : []);
      setError('');
    } catch (err) {
      setRows([]);
      setError(errorMessage(err, 'Erro ao carregar as marcas'));
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const loadPending = useCallback(async () => {
    try {
      const { data } = await brandsAPI.aliases();
      setPending(data?.suggestions?.length || 0);
    } catch { /* o separador mostra o erro */ }
  }, []);

  useEffect(() => { loadPending(); }, [loadPending]);

  const counts = useMemo(() => {
    const c = { all: 0, premium: 0, quality: 0, budget: 0, none: 0 };
    (rows || []).forEach((r) => { c.all += 1; c[r.category || 'none'] += 1; });
    return c;
  }, [rows]);

  const visible = useMemo(() => filterBrands(rows, query, tier), [rows, query, tier]);

  const change = async (row, category) => {
    setSaving(row.brand);
    try {
      const { data } = await brandsAPI.setTier(row.brand, category);
      setRows((rs) => rs.map((r) => (r.brand === row.brand
        ? { ...r, category: data.category, updated_at: data.updated_at ?? null, updated_by: data.updated_by ?? null, note: data.note ?? r.note }
        : r)));
      toast.success(category ? `${row.brand}: ${TIER_OPTIONS.find((t) => t.value === category)?.label}` : `${row.brand}: sem classificação`);
    } catch (err) {
      toast.error(errorMessage(err, 'Erro ao gravar o tier'));
    } finally {
      setSaving('');
    }
  };

  return (
    <div className="space-y-4" data-testid="marcas">
      <PageHeader
        eyebrow="Administração"
        title="Marcas"
        description="Tier de cada marca, usado na vista comparativa da Pesquisa (Premium, Quality, Budget) e nos alertas por categoria. Cada alteração fica gravada de imediato."
      />
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="tiers" data-testid="tab-tiers">Tiers</TabsTrigger>
          <TabsTrigger value="associacoes" data-testid="tab-associacoes">
            Associações{pending > 0 && <span className="ml-1.5 rounded-full bg-amber-500 px-1.5 text-[11px] font-semibold text-white">{pending}</span>}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="associacoes" className="mt-4">
          <MarcasAssociacoes onChanged={() => { load(); loadPending(); }} />
        </TabsContent>
        <TabsContent value="tiers" className="mt-4 space-y-4">
      <Card>
        <CardContent className="p-4 flex flex-col md:flex-row md:items-center gap-3">
          <div className="relative md:w-72">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Procurar marca" className="pl-8" aria-label="Procurar marca" />
          </div>
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filtrar por tier">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                type="button"
                onClick={() => setTier(f.key)}
                aria-pressed={tier === f.key}
                className={cn('rounded-full border px-3 py-1 text-xs transition-colors',
                  tier === f.key ? 'bg-slate-900 text-white border-slate-900 dark:bg-white dark:text-slate-900' : 'hover:bg-muted',
                  f.key === 'none' && counts.none > 0 && tier !== f.key && 'border-amber-300 text-amber-800 dark:text-amber-300')}
              >
                {f.label} <span className="opacity-70">{counts[f.key]}</span>
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {error && <ErrorState message={error} onRetry={load} />}

      <Card>
        <CardContent className="p-0">
          {rows === null ? <TableSkeleton rows={8} cols={5} /> : visible.length === 0 ? (
            <EmptyState title="Nenhuma marca" description="Ajuste a pesquisa ou o filtro." />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Marca</TableHead>
                  <TableHead className="w-48">Tier</TableHead>
                  <TableHead className="text-right">Ofertas</TableHead>
                  <TableHead className="text-right hidden sm:table-cell">Fornecedores</TableHead>
                  <TableHead className="hidden lg:table-cell">Nota</TableHead>
                  <TableHead className="hidden md:table-cell">Alterado</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visible.map((r) => (
                  <TableRow key={r.brand} data-testid="marca-row">
                    <TableCell className="font-medium">{r.brand}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <select
                          value={r.category || ''}
                          onChange={(e) => change(r, e.target.value)}
                          disabled={saving === r.brand}
                          aria-label={`Tier de ${r.brand}`}
                          className={cn('h-8 w-40 rounded-md border px-2 text-xs font-medium',
                            r.category ? TIER_STYLE[r.category] : 'border-amber-300 bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:text-amber-300')}
                        >
                          <option value="">Sem classificação</option>
                          {TIER_OPTIONS.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
                        </select>
                        {saving === r.brand && <Loader2 size={14} className="animate-spin text-muted-foreground" />}
                      </div>
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs">{r.offers}</TableCell>
                    <TableCell className="text-right font-mono text-xs hidden sm:table-cell">{r.suppliers}</TableCell>
                    <TableCell className="hidden lg:table-cell max-w-[380px]">
                      {r.note ? (
                        <WithTooltip content={r.note}>
                          <span className="block truncate text-xs text-muted-foreground cursor-help">{r.note}</span>
                        </WithTooltip>
                      ) : <span className="text-xs text-muted-foreground">—</span>}
                      {r.source && (
                        <a href={r.source} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-[11px] text-blue-600 hover:underline">
                          fonte <ExternalLink size={10} />
                        </a>
                      )}
                    </TableCell>
                    <TableCell className="hidden md:table-cell text-xs text-muted-foreground whitespace-nowrap">
                      {r.updated_at ? <>{formatDateTime(r.updated_at)}<br />{r.updated_by}</> : '—'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
};

export default Marcas;
