import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight, TrendingDown, TrendingUp } from 'lucide-react';
import { historyAPI } from '@/lib/api';
import { errorMessage, formatDateTime, formatPct, formatPrice } from '@/lib/format';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { EmptyState, ErrorState, Field, KpiStrip, NativeSelect, PageHeader, TableSkeleton } from '@/components/common';
import { ToneBadge } from '@/components/badges';
import { cn } from '@/lib/utils';

const PERIODS = [
  { days: 7, label: '7 dias' },
  { days: 30, label: '30 dias' },
  { days: 90, label: '90 dias' },
  { days: 365, label: '12 meses' },
];
const SOURCES = [
  { value: '', label: 'Todas as origens' },
  { value: 'app', label: 'Aplicação' },
  { value: 'tickets', label: 'PDPV Tickets' },
];
const TIER_LABELS = { premium: 'Premium', quality: 'Quality', budget: 'Budget', unclassified: 'Sem classificação' };
const TIER_TONES = { premium: 'purple', quality: 'blue', budget: 'green' };
const MODE_LABELS = { quick: 'Rápida', exact: 'Exacta' };
const FILTER_LABELS = {
  model: 'Modelo', load_index: 'Índice', speed_index: 'Velocidade', xl: 'XL', runflat: 'RunFlat', season: 'Estação',
  homologation: 'Homologação', ean: 'EAN', supplier_id: 'Fornecedor', supplier_ids: 'Fornecedores',
  min_price: 'Preço mín.', max_price: 'Preço máx.', in_stock: 'Só com stock', only_fresh: 'Só actuais',
};

const fmtInt = (n) => (n == null ? '—' : Number(n).toLocaleString('pt-PT'));

export function ChangeBadge({ pct, isNew }) {
  if (isNew) return <ToneBadge tone="blue">Nova</ToneBadge>;
  if (pct == null) return <span className="text-xs text-muted-foreground">—</span>;
  if (pct === 0) return <span className="text-xs tabular-nums text-muted-foreground">0%</span>;
  const up = pct > 0;
  const Icon = up ? TrendingUp : TrendingDown;
  return (
    <span className={cn('inline-flex items-center gap-1 text-xs font-semibold tabular-nums', up ? 'text-success' : 'text-danger')}>
      <Icon size={13} aria-hidden="true" />{up ? '+' : ''}{formatPct(pct, 0)}
    </span>
  );
}

function TierBadge({ tier }) {
  if (!tier) return <span className="text-xs text-muted-foreground">Sem classificação</span>;
  return <ToneBadge tone={TIER_TONES[tier] || 'slate'}>{TIER_LABELS[tier]}</ToneBadge>;
}

export function describeFilters(filters) {
  return Object.entries(filters || {})
    .map(([k, v]) => `${FILTER_LABELS[k] || k}: ${v === true ? 'sim' : Array.isArray(v) ? v.join(', ') : v}`)
    .join(' · ');
}

function SegmentedButtons({ options, value, onChange, label }) {
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label={label}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          aria-pressed={value === o.value}
          className={cn('min-h-8 rounded-full border px-3 py-1 text-xs transition-colors',
            value === o.value ? 'border-primary bg-primary text-primary-foreground' : 'border-input hover:bg-muted')}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function BrandList({ title, rows, empty, onBrand, showPrev }) {
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-sm font-bold">{title}</p>
        {rows.length === 0 ? <p className="mt-2 text-xs text-muted-foreground">{empty}</p> : (
          <ul className="mt-2 divide-y">
            {rows.map((b) => (
              <li key={b.brand} className="flex items-center justify-between gap-2 py-1.5 text-sm">
                <button type="button" className="truncate font-medium hover:text-primary hover:underline" onClick={() => onBrand(b.brand)}>{b.brand}</button>
                <span className="flex items-center gap-3 text-xs tabular-nums text-muted-foreground">
                  {showPrev ? `${fmtInt(b.previous)} → ${fmtInt(b.searches)}` : fmtInt(b.searches)}
                  <ChangeBadge pct={b.change_pct} isNew={b.new} />
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

function Tendencias({ onBrand }) {
  const [days, setDays] = useState(30);
  const [source, setSource] = useState('');
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setData(null);
    try {
      const { data: d } = await historyAPI.trends({ days, source: source || undefined, limit: 50 });
      setData(d);
      setError('');
    } catch (err) {
      setError(errorMessage(err, 'Erro ao carregar as tendências'));
      setData({});
    }
  }, [days, source]);

  useEffect(() => { load(); }, [load]);

  const t = data?.totals;
  const loading = data === null;
  const kpis = [
    { title: 'Pesquisas', value: fmtInt(t?.searches), sub: t ? <>Período anterior: {fmtInt(t.previous)} <ChangeBadge pct={t.change_pct} /></> : null, testId: 'kpi-searches' },
    { title: 'Com marca indicada', value: fmtInt(t?.with_brand), sub: t?.with_brand_pct != null ? `${formatPct(t.with_brand_pct, 0)} das pesquisas` : null, testId: 'kpi-brand' },
    { title: 'Marcas pesquisadas', value: fmtInt(t?.brands), testId: 'kpi-brands' },
    { title: 'Medidas distintas', value: fmtInt(t?.sizes), sub: t ? `${fmtInt(t.users)} utilizador(es)/origens` : null, testId: 'kpi-sizes' },
  ];

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="flex flex-col gap-3 p-4 md:flex-row md:items-center md:justify-between">
          <SegmentedButtons label="Período" value={days} onChange={setDays} options={PERIODS.map((p) => ({ value: p.days, label: p.label }))} />
          <NativeSelect className="h-9 md:w-52" value={source} onChange={(e) => setSource(e.target.value)} aria-label="Origem">
            {SOURCES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </NativeSelect>
        </CardContent>
      </Card>

      {error && <ErrorState message={error} onRetry={load} />}
      <KpiStrip items={kpis} loading={loading} />
      <p className="text-xs text-muted-foreground">
        As marcas contam quando a pesquisa indica uma marca (filtro da Pesquisa ou marca pedida no ticket). A variação compara com o período anterior de igual duração.
      </p>

      <div className="grid gap-3 lg:grid-cols-3">
        <BrandList title="Marcas em subida" rows={data?.rising_brands || []} empty="Sem subidas face ao período anterior." onBrand={onBrand} showPrev />
        <BrandList title="Marcas novas no período" rows={data?.new_brands || []} empty="Nenhuma marca nova." onBrand={onBrand} />
        <BrandList title="Deixaram de ser pesquisadas" rows={data?.falling_brands || []} empty="Nenhuma." onBrand={onBrand} showPrev />
      </div>

      <Card>
        <CardContent className="p-0">
          <div className="flex flex-wrap items-baseline justify-between gap-2 border-b px-4 py-3">
            <p className="text-sm font-bold">Marcas mais pesquisadas</p>
            {data?.tiers?.length > 0 && (
              <p className="text-xs text-muted-foreground">
                {data.tiers.map((x) => `${TIER_LABELS[x.tier] || x.tier}: ${fmtInt(x.searches)}`).join(' · ')}
              </p>
            )}
          </div>
          {loading ? <TableSkeleton rows={6} cols={6} /> : !data?.brands?.length ? (
            <EmptyState title="Sem pesquisas com marca neste período" />
          ) : (
            <Table data-stack="true">
              <TableHeader>
                <TableRow>
                  <TableHead>Marca</TableHead>
                  <TableHead>Gama</TableHead>
                  <TableHead className="text-right">Pesquisas</TableHead>
                  <TableHead className="text-right">Quota</TableHead>
                  <TableHead className="text-right">Anterior</TableHead>
                  <TableHead>Variação</TableHead>
                  <TableHead className="text-right">Utilizadores</TableHead>
                  <TableHead>Medidas mais pedidas</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.brands.map((b) => (
                  <TableRow key={b.brand} data-testid="trend-brand-row">
                    <TableCell data-label="Marca">
                      <button type="button" className="font-semibold hover:text-primary hover:underline" onClick={() => onBrand(b.brand)}>{b.brand}</button>
                    </TableCell>
                    <TableCell data-label="Gama"><TierBadge tier={b.tier} /></TableCell>
                    <TableCell data-label="Pesquisas" className="text-right font-semibold tabular-nums">{fmtInt(b.searches)}</TableCell>
                    <TableCell data-label="Quota" className="text-right tabular-nums">{formatPct(b.share_pct, 0)}</TableCell>
                    <TableCell data-label="Anterior" className="text-right tabular-nums text-muted-foreground">{fmtInt(b.previous)}</TableCell>
                    <TableCell data-label="Variação"><ChangeBadge pct={b.change_pct} isNew={b.new} /></TableCell>
                    <TableCell data-label="Utilizadores" className="text-right tabular-nums">{fmtInt(b.users)}</TableCell>
                    <TableCell data-label="Medidas mais pedidas" className="text-xs">
                      {b.top_sizes.map((s) => `${s.size} (${s.searches})`).join(', ')}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <p className="border-b px-4 py-3 text-sm font-bold">Medidas mais pesquisadas</p>
          {loading ? <TableSkeleton rows={6} cols={5} /> : !data?.sizes?.length ? (
            <EmptyState title="Sem pesquisas neste período" />
          ) : (
            <Table data-stack="true">
              <TableHeader>
                <TableRow>
                  <TableHead>Medida</TableHead>
                  <TableHead className="text-right">Pesquisas</TableHead>
                  <TableHead className="text-right">Anterior</TableHead>
                  <TableHead>Variação</TableHead>
                  <TableHead>Marcas mais pedidas</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.sizes.map((s) => (
                  <TableRow key={s.size_key} data-testid="trend-size-row">
                    <TableCell data-label="Medida">
                      <Link className="font-semibold tabular-nums hover:text-primary hover:underline" to={`/precos?size=${encodeURIComponent(s.size)}&mode=quick`}>{s.size}</Link>
                    </TableCell>
                    <TableCell data-label="Pesquisas" className="text-right font-semibold tabular-nums">{fmtInt(s.searches)}</TableCell>
                    <TableCell data-label="Anterior" className="text-right tabular-nums text-muted-foreground">{fmtInt(s.previous)}</TableCell>
                    <TableCell data-label="Variação"><ChangeBadge pct={s.change_pct} isNew={s.new} /></TableCell>
                    <TableCell data-label="Marcas mais pedidas" className="text-xs">
                      {s.top_brands.length ? s.top_brands.map((b) => `${b.brand} (${b.searches})`).join(', ') : <span className="text-muted-foreground">sem marca indicada</span>}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

const EMPTY_FILTERS = { user_id: '', source: '', size: '', brand: '', date_from: '', date_to: '' };

function TodasPesquisas({ brandFilter }) {
  const [draft, setDraft] = useState({ ...EMPTY_FILTERS, brand: brandFilter || '' });
  const [filters, setFilters] = useState(draft);
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [users, setUsers] = useState([]);
  const [error, setError] = useState('');

  useEffect(() => {
    if (brandFilter) {
      const next = { ...EMPTY_FILTERS, brand: brandFilter };
      setDraft(next);
      setFilters(next);
      setPage(1);
    }
  }, [brandFilter]);

  useEffect(() => {
    historyAPI.users().then(({ data: d }) => setUsers(d?.users || [])).catch(() => { /* filtro fica só com "Todos" */ });
  }, []);

  const load = useCallback(async () => {
    setData(null);
    try {
      const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v));
      const { data: d } = await historyAPI.list({ ...params, page, page_size: 50 });
      setData(d);
      setError('');
    } catch (err) {
      setError(errorMessage(err, 'Erro ao carregar o histórico'));
      setData({ items: [], total: 0, pages: 0 });
    }
  }, [filters, page]);

  useEffect(() => { load(); }, [load]);

  const set = (k) => (e) => setDraft((d) => ({ ...d, [k]: e.target.value }));
  const apply = (e) => { e.preventDefault(); setPage(1); setFilters(draft); };
  const clear = () => { setDraft(EMPTY_FILTERS); setFilters(EMPTY_FILTERS); setPage(1); };
  const active = useMemo(() => Object.values(filters).some(Boolean), [filters]);

  return (
    <div className="space-y-4">
      <Card>
        <CardContent className="p-4">
          <form onSubmit={apply} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6 lg:items-end">
            <Field label="Utilizador" htmlFor="h-user">
              <NativeSelect id="h-user" className="h-9" value={draft.user_id} onChange={set('user_id')}>
                <option value="">Todos</option>
                {users.map((u) => <option key={u.user_id} value={u.user_id}>{u.user_name} ({u.searches})</option>)}
              </NativeSelect>
            </Field>
            <Field label="Origem" htmlFor="h-source">
              <NativeSelect id="h-source" className="h-9" value={draft.source} onChange={set('source')}>
                {SOURCES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </NativeSelect>
            </Field>
            <Field label="Medida" htmlFor="h-size">
              <Input id="h-size" className="h-9" value={draft.size} onChange={set('size')} placeholder="205/55R16" />
            </Field>
            <Field label="Marca" htmlFor="h-brand">
              <Input id="h-brand" className="h-9" value={draft.brand} onChange={set('brand')} placeholder="Michelin" />
            </Field>
            <Field label="De" htmlFor="h-from">
              <Input id="h-from" type="date" className="h-9" value={draft.date_from} onChange={set('date_from')} />
            </Field>
            <Field label="Até" htmlFor="h-to">
              <Input id="h-to" type="date" className="h-9" value={draft.date_to} onChange={set('date_to')} />
            </Field>
            <div className="flex gap-2 sm:col-span-2 lg:col-span-6">
              <Button type="submit" size="sm">Filtrar</Button>
              {active && <Button type="button" size="sm" variant="outline" onClick={clear}>Limpar</Button>}
            </div>
          </form>
        </CardContent>
      </Card>

      {error && <ErrorState message={error} onRetry={load} />}

      <Card>
        <CardContent className="p-0">
          <div className="flex items-center justify-between gap-2 border-b px-4 py-3">
            <p className="text-sm font-bold">{data ? `${fmtInt(data.total)} pesquisa(s)` : 'A carregar…'}</p>
            {data?.pages > 1 && (
              <div className="flex items-center gap-2 text-xs tabular-nums">
                <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} aria-label="Página anterior"><ChevronLeft size={14} /></Button>
                {page} / {data.pages}
                <Button size="sm" variant="outline" disabled={page >= data.pages} onClick={() => setPage((p) => p + 1)} aria-label="Página seguinte"><ChevronRight size={14} /></Button>
              </div>
            )}
          </div>
          {data === null ? <TableSkeleton rows={8} cols={7} /> : !data.items.length ? (
            <EmptyState title="Sem pesquisas" description={active ? 'Ajuste os filtros.' : 'Ainda não há pesquisas registadas.'} />
          ) : (
            <Table data-stack="true">
              <TableHeader>
                <TableRow>
                  <TableHead>Data</TableHead>
                  <TableHead>Utilizador</TableHead>
                  <TableHead>Modo</TableHead>
                  <TableHead>Medida</TableHead>
                  <TableHead>Marca</TableHead>
                  <TableHead>Outros filtros</TableHead>
                  <TableHead className="text-right">Resultados</TableHead>
                  <TableHead className="text-right">Melhor preço</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((i) => (
                  <TableRow key={`${i.source}-${i.id}`} data-testid="history-row">
                    <TableCell data-label="Data" className="whitespace-nowrap text-xs tabular-nums">{formatDateTime(i.created_at)}</TableCell>
                    <TableCell data-label="Utilizador" className="text-sm">
                      {i.user_name || '(utilizador removido)'}
                      {i.source === 'tickets' && <ToneBadge tone="purple" className="ml-1.5">Tickets</ToneBadge>}
                    </TableCell>
                    <TableCell data-label="Modo" className="text-xs">{MODE_LABELS[i.mode] || i.mode}</TableCell>
                    <TableCell data-label="Medida">
                      <Link className="font-semibold tabular-nums hover:text-primary hover:underline" to={`/precos?size=${encodeURIComponent(i.size)}&mode=quick`}>{i.size}</Link>
                      {i.quantity ? <span className="ml-1 text-xs text-muted-foreground">× {i.quantity}</span> : null}
                    </TableCell>
                    <TableCell data-label="Marca" className="text-xs font-medium">{i.brands.length ? i.brands.join(', ') : <span className="text-muted-foreground">—</span>}</TableCell>
                    <TableCell data-label="Outros filtros" className="max-w-[280px] text-xs text-muted-foreground">{describeFilters(i.filters) || '—'}</TableCell>
                    <TableCell data-label="Resultados" className="text-right tabular-nums">{i.results != null ? fmtInt(i.results) : '—'}</TableCell>
                    <TableCell data-label="Melhor preço" className="text-right tabular-nums">{formatPrice(i.best_price)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

const HistoricoPesquisas = () => {
  const [tab, setTab] = useState('tendencias');
  const [brandFilter, setBrandFilter] = useState('');
  const openBrand = (brand) => { setBrandFilter(brand); setTab('todas'); };

  return (
    <div className="space-y-4" data-testid="historico-pesquisas">
      <PageHeader
        eyebrow="Administração"
        title="Histórico de pesquisas"
        description="Todas as pesquisas feitas na aplicação e pelo PDPV Tickets, guardadas sem limite de tempo, com as marcas e medidas mais procuradas."
      />
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="tendencias" data-testid="tab-tendencias">Tendências</TabsTrigger>
          <TabsTrigger value="todas" data-testid="tab-todas">Todas as pesquisas</TabsTrigger>
        </TabsList>
        <TabsContent value="tendencias" className="mt-4"><Tendencias onBrand={openBrand} /></TabsContent>
        <TabsContent value="todas" className="mt-4"><TodasPesquisas brandFilter={brandFilter} /></TabsContent>
      </Tabs>
    </div>
  );
};

export default HistoricoPesquisas;
