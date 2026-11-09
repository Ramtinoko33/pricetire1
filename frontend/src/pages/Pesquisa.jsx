import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CloudDownload, Columns3, List, Loader2, Search, Target, Trophy, X } from 'lucide-react';
import { toast } from 'sonner';
import { useSearchParams } from 'react-router-dom';
import { alertsAPI, searchAPI, suppliersAPI } from '@/lib/api';
import TierColumns from '@/components/TierColumns';
import { buildTierMap } from '@/lib/tiers';
import { errorMessage, formatAge, formatDateTime, formatLoadSpeed, formatPrice, parseSize } from '@/lib/format';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Progress } from '@/components/ui/progress';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { EmptyState, ErrorState, Field, NativeSelect, PageHeader, TableSkeleton } from '@/components/common';
import { ERROR_KIND_LABELS, JOB_FINISHED, JobStatusBadge, OfferFlags, StaleBadge, StockBadge, ToneBadge } from '@/components/badges';
import OffersTable, { sortOffersByPrice } from '@/components/OffersTable';
import BrandInput from '@/components/BrandInput';
import MultiBrandSelect from '@/components/MultiBrandSelect';
import { groupOffers } from '@/lib/groupOffers';

const POLL_MS = 3000;
const REFRESH_TIMEOUT_MS = 30 * 60 * 1000;
const FINISHED = JOB_FINISHED;

const EMPTY_FILTERS = {
  brand: [], model: '', load_index: '', speed_index: '', xl: '', runflat: '', season: '',
  supplier_id: '', min_price: '', max_price: '', in_stock: false, show_stale: true, include_unlisted: false, include_incompatible: false,
};

const EMPTY_WANTED = { brand: '', model: '', load_index: '', speed_index: '', xl: '', runflat: '', season: '' };

const triToBool = (v) => (v === 'true' ? true : v === 'false' ? false : undefined);
const numOrUndef = (v) => (v === '' || v === null || v === undefined ? undefined : Number(String(v).replace(',', '.')));

function TriSelect({ id, value, onChange, anyLabel = 'Qualquer' }) {
  return (
    <NativeSelect id={id} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{anyLabel}</option>
      <option value="true">Sim</option>
      <option value="false">Não</option>
    </NativeSelect>
  );
}

function SeasonSelect({ id, value, onChange }) {
  return (
    <NativeSelect id={id} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">Qualquer</option>
      <option value="summer">Verão</option>
      <option value="winter">Inverno</option>
      <option value="all_season">Todo o ano</option>
    </NativeSelect>
  );
}

function SupplierFreshnessPanel({ suppliers }) {
  if (!suppliers?.length) return null;
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="text-base">Frescura por fornecedor</CardTitle></CardHeader>
      <CardContent className="pt-0">
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-2" data-testid="freshness-panel">
          {suppliers.map((s) => (
            <div key={s.supplier_id ?? s.supplier_name} className="rounded-md border p-2 text-xs space-y-1">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-sm truncate">{s.supplier_name}</span>
                {s.is_active === false ? <ToneBadge>Inactivo</ToneBadge> : s.fresh ? <ToneBadge tone="green">Actual</ToneBadge> : <StaleBadge />}
              </div>
              <div className="text-muted-foreground">
                Último sucesso: {formatDateTime(s.last_success_at)} ({formatAge(s.last_success_at)})
              </div>
              <div className="text-muted-foreground flex flex-wrap gap-x-3">
                <span>Ofertas: {s.offers ?? 0}</span>
                {s.last_run_status && <span>Última execução: {s.last_run_status} {s.last_run_at ? `(${formatAge(s.last_run_at)})` : ''}</span>}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function RefreshProgress({ refresh, onClose }) {
  if (!refresh) return null;
  const jobs = refresh.jobs || [];
  const finished = jobs.filter((j) => FINISHED.has(j.status)).length;
  const pct = jobs.length ? Math.round((finished / jobs.length) * 100) : 0;
  return (
    <Card className="border-blue-300 dark:border-blue-500/30" data-testid="refresh-progress">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base flex items-center gap-2">
            {!refresh.done && !refresh.timedOut && <Loader2 size={16} className="animate-spin" />}
            Actualização nos fornecedores
          </CardTitle>
          {(refresh.done || refresh.timedOut) && (
            <Button variant="ghost" size="sm" onClick={onClose} aria-label="Fechar"><X size={14} /></Button>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          {refresh.timedOut
            ? 'O pedido ultrapassou 30 min. Os jobs continuam na fila; acompanhe-os em Operação.'
            : refresh.done
              ? `Concluído: ${finished}/${jobs.length} fornecedores.`
              : `${finished}/${jobs.length} fornecedores concluídos. Os resultados são actualizados à medida que cada fornecedor termina.`}
        </p>
        <Progress value={pct} className="h-2 mt-2" />
      </CardHeader>
      <CardContent className="pt-0">
        <div className="divide-y divide-border text-sm">
          {jobs.map((j) => (
            <div key={j.job_id} className="py-2 flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="font-medium min-w-[120px]">{j.supplier_name}</span>
              <JobStatusBadge status={j.status} />
              {j.deduplicated && <ToneBadge tone="sky" title="Já existia um pedido igual na fila">Reaproveitado</ToneBadge>}
              {j.products != null && <span className="text-xs text-muted-foreground">{j.products} produtos</span>}
              {j.error && (
                <span className="text-xs text-red-600 dark:text-red-400 w-full sm:w-auto">
                  {ERROR_KIND_LABELS[j.error_kind] ? `${ERROR_KIND_LABELS[j.error_kind]}: ` : ''}{j.error}
                </span>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function BestExactCard({ offer }) {
  if (!offer) return null;
  return (
    <Card className="border-emerald-300 bg-emerald-50/60 dark:bg-emerald-500/10 dark:border-emerald-500/30" data-testid="best-exact">
      <CardContent className="pt-5 flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
        <div className="flex items-start gap-3">
          <Trophy className="text-emerald-600 mt-1 flex-shrink-0" size={22} />
          <div>
            <p className="text-xs uppercase tracking-wide text-emerald-700 dark:text-emerald-300 font-semibold">Melhor preço — correspondência exacta</p>
            <p className="font-semibold">{offer.brand} {offer.model} <span className="font-mono text-sm">{formatLoadSpeed(offer)}</span></p>
            <div className="flex flex-wrap items-center gap-1 mt-1 text-xs">
              <span>{offer.supplier_name}</span>
              <StockBadge status={offer.stock_status} qty={offer.stock_qty} />
              <OfferFlags offer={offer} />
              <span className="text-muted-foreground">{formatDateTime(offer.last_seen_at)}</span>
              {offer.fresh === false && <StaleBadge />}
            </div>
          </div>
        </div>
        <p className="text-3xl font-bold font-mono text-emerald-700 dark:text-emerald-300">{formatPrice(offer.price, offer.currency)}</p>
      </CardContent>
    </Card>
  );
}

function Section({ title, description, offers, sortDir, onToggleSort, emptyText, tone, highlightId, grouped }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base flex items-center gap-2">
          {title} <ToneBadge tone={tone}>{offers?.length || 0}</ToneBadge>
        </CardTitle>
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </CardHeader>
      <CardContent className="p-0">
        {offers?.length ? (
          <OffersTable offers={sortOffersByPrice(offers, sortDir)} sortDir={sortDir} onToggleSort={onToggleSort} showMatch highlightId={highlightId} grouped={grouped} />
        ) : (
          <p className="text-sm text-muted-foreground px-6 pb-6">{emptyText}</p>
        )}
      </CardContent>
    </Card>
  );
}

const Pesquisa = () => {
  const [mode, setMode] = useState('quick');
  const [sizeInput, setSizeInput] = useState('');
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [wanted, setWanted] = useState(EMPTY_WANTED);
  const [supplierOptions, setSupplierOptions] = useState([]);
  const [brandOptions, setBrandOptions] = useState([]);
  const [tierMap, setTierMap] = useState(() => new Map());
  const [layout, setLayout] = useState(() => {
    try { return window.localStorage.getItem('pesquisa-layout') === 'tiers' ? 'tiers' : 'list'; } catch { return 'list'; }
  });
  const changeLayout = (v) => {
    setLayout(v);
    try { window.localStorage.setItem('pesquisa-layout', v); } catch { /* storage indisponível */ }
  };
  const [sortDir, setSortDir] = useState('asc');
  const [grouped, setGrouped] = useState(true);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [quickResult, setQuickResult] = useState(null);
  const [exactResult, setExactResult] = useState(null);
  const [lastQuery, setLastQuery] = useState(null);
  const [searchParams] = useSearchParams();
  const [autoRun, setAutoRun] = useState(false);

  const [refresh, setRefresh] = useState(null);
  const finishedRef = useRef(new Set());
  const mountedRef = useRef(true);

  const parsed = useMemo(() => parseSize(sizeInput), [sizeInput]);
  const sizeInvalid = sizeInput.trim() !== '' && !parsed;

  useEffect(() => {
    mountedRef.current = true;
    suppliersAPI.getAll()
      .then(({ data }) => { if (mountedRef.current && Array.isArray(data)) setSupplierOptions(data); })
      .catch(() => { /* filtro de fornecedores usa os da resposta */ });
    alertsAPI.getBrandCategories()
      .then(({ data }) => { if (mountedRef.current) setTierMap(buildTierMap(Array.isArray(data) ? data : [])); })
      .catch(() => { /* sem tiers: tudo fica em "Sem classificação" */ });
    searchAPI.brands()
      .then(({ data }) => { if (mountedRef.current) setBrandOptions((data?.brands || []).map((b) => b.brand)); })
      .catch(() => { /* sem sugestões, o campo continua livre */ });
    return () => { mountedRef.current = false; };
  }, []);

  const setF = (k) => (v) => setFilters((f) => ({ ...f, [k]: v }));
  const setW = (k) => (v) => setWanted((w) => ({ ...w, [k]: v }));

  const runQuick = useCallback(async (size, f, { silent = false } = {}) => {
    if (!silent) { setLoading(true); setError(''); }
    try {
      const { data } = await searchAPI.offers({
        size,
        brand: (f.brand || []).join(','),
        model: f.model.trim(),
        load_index: f.load_index.trim(),
        speed_index: f.speed_index.trim().toUpperCase(),
        xl: f.xl,
        runflat: f.runflat,
        season: f.season,
        supplier_id: f.supplier_id,
        min_price: numOrUndef(f.min_price),
        max_price: numOrUndef(f.max_price),
        in_stock: f.in_stock ? true : undefined,
        include_unlisted: f.include_unlisted,
      });
      if (mountedRef.current) setQuickResult(data);
    } catch (err) {
      const msg = errorMessage(err, 'Erro ao pesquisar ofertas');
      if (mountedRef.current && !silent) { setError(msg); toast.error(msg); }
    } finally {
      if (mountedRef.current && !silent) setLoading(false);
    }
  }, []);

  const runExact = useCallback(async (size, w, f, { silent = false } = {}) => {
    if (!silent) { setLoading(true); setError(''); }
    try {
      const body = {
        size,
        brand: w.brand.trim() || undefined,
        model: w.model.trim() || undefined,
        load_index: w.load_index.trim() || undefined,
        speed_index: w.speed_index.trim().toUpperCase() || undefined,
        xl: triToBool(w.xl),
        runflat: triToBool(w.runflat),
        season: w.season || undefined,
        refresh: 'never',
        include_incompatible: f.include_incompatible || undefined,
        filters: {
          supplier_ids: f.supplier_id ? [f.supplier_id] : undefined,
          min_price: numOrUndef(f.min_price),
          max_price: numOrUndef(f.max_price),
          in_stock: f.in_stock ? true : undefined,
        },
      };
      const { data } = await searchAPI.search(body);
      if (mountedRef.current) setExactResult(data);
    } catch (err) {
      const msg = errorMessage(err, 'Erro na pesquisa exacta');
      if (mountedRef.current && !silent) { setError(msg); toast.error(msg); }
    } finally {
      if (mountedRef.current && !silent) setLoading(false);
    }
  }, []);

  const handleSubmit = (e) => {
    e?.preventDefault();
    if (!parsed) {
      setError('Indique uma medida válida, por exemplo 205/55R16, 205 55 16 ou 2055516.');
      return;
    }
    const q = { mode, size: parsed.display, filters, wanted };
    setLastQuery(q);
    if (mode === 'quick') runQuick(q.size, filters);
    else runExact(q.size, wanted, filters);
  };

  // Vindo do dashboard ("Últimas pesquisas"): /precos?size=205/55R16&mode=quick
  useEffect(() => {
    const size = searchParams.get('size');
    if (!size) return;
    const m = searchParams.get('mode');
    if (m === 'quick' || m === 'exact') setMode(m);
    setSizeInput(size);
    setAutoRun(true);
  }, [searchParams]);
  useEffect(() => {
    if (autoRun && parsed) {
      setAutoRun(false);
      handleSubmit();
    }
  });

  const reloadLast = useCallback(() => {
    if (!lastQuery) return;
    if (lastQuery.mode === 'quick') runQuick(lastQuery.size, lastQuery.filters, { silent: true });
    else runExact(lastQuery.size, lastQuery.wanted, lastQuery.filters, { silent: true });
  }, [lastQuery, runQuick, runExact]);

  // Filtros alterados depois de uma pesquisa: repetir a pesquisa sem carregar em "Pesquisar".
  const lastQueryRef = useRef(lastQuery);
  useEffect(() => { lastQueryRef.current = lastQuery; }, [lastQuery]);
  useEffect(() => {
    const last = lastQueryRef.current;
    if (!last || (last.filters === filters && last.wanted === wanted)) return undefined;
    const t = setTimeout(() => {
      const q = { ...last, filters, wanted };
      setLastQuery(q);
      if (q.mode === 'quick') runQuick(q.size, filters, { silent: true });
      else runExact(q.size, wanted, filters, { silent: true });
    }, 450);
    return () => clearTimeout(t);
  }, [filters, wanted, runQuick, runExact]);

  const reloadRef = useRef(reloadLast);
  useEffect(() => { reloadRef.current = reloadLast; }, [reloadLast]);

  const startRefresh = async () => {
    if (!parsed) {
      setError('Indique uma medida válida antes de actualizar nos fornecedores.');
      return;
    }
    if (!lastQuery || lastQuery.size !== parsed.display) {
      const q = { mode, size: parsed.display, filters, wanted };
      setLastQuery(q);
      if (mode === 'quick') runQuick(q.size, filters);
      else runExact(q.size, wanted, filters);
    }
    try {
      const supplierIds = filters.supplier_id ? [filters.supplier_id] : undefined;
      const { data } = await searchAPI.refresh([parsed.display], supplierIds);
      finishedRef.current = new Set();
      setRefresh({ request_id: data.request_id, jobs: data.jobs || [], done: false, startedAt: Date.now(), timedOut: false });
      toast.info('Pedido enviado aos fornecedores. Pode demorar alguns minutos.');
    } catch (err) {
      toast.error(errorMessage(err, 'Erro ao pedir actualização'));
    }
  };

  const requestId = refresh && !refresh.done && !refresh.timedOut ? refresh.request_id : null;
  const startedAt = refresh?.startedAt;

  useEffect(() => {
    if (!requestId) return undefined;
    let stopped = false;
    let timer = null;

    const tick = async () => {
      if (stopped) return;
      if (Date.now() - startedAt > REFRESH_TIMEOUT_MS) {
        setRefresh((r) => (r ? { ...r, timedOut: true } : r));
        return;
      }
      try {
        const { data } = await searchAPI.refreshStatus(requestId);
        if (stopped) return;
        const jobs = data.jobs || [];
        let newlyFinished = false;
        jobs.forEach((j) => {
          if (FINISHED.has(j.status) && !finishedRef.current.has(j.job_id)) {
            finishedRef.current.add(j.job_id);
            newlyFinished = true;
          }
        });
        setRefresh((r) => (r ? { ...r, jobs, done: Boolean(data.done) } : r));
        if (newlyFinished) reloadRef.current();
        if (data.done) {
          toast.success('Actualização concluída');
          return;
        }
      } catch {
        /* erro transitório: tentar no próximo ciclo */
      }
      if (!stopped) timer = setTimeout(tick, POLL_MS);
    };

    timer = setTimeout(tick, POLL_MS);
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [requestId, startedAt]);

  const toggleSort = () => setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));

  const quickOffers = useMemo(() => {
    const list = quickResult?.offers || [];
    const visible = filters.show_stale ? list : list.filter((o) => o.fresh !== false);
    return sortOffersByPrice(visible, sortDir);
  }, [quickResult, filters.show_stale, sortDir]);

  const hiddenStale = (quickResult?.offers?.length || 0) - quickOffers.length;

  const exactFilter = (list) => (filters.show_stale ? list : (list || []).filter((o) => o.fresh !== false));

  const supplierChoices = supplierOptions.length
    ? supplierOptions.map((s) => ({ id: s.id, name: s.name }))
    : (quickResult?.suppliers || exactResult?.suppliers || []).map((s) => ({ id: s.supplier_id, name: s.supplier_name }));

  const freshness = mode === 'quick' ? quickResult?.suppliers : exactResult?.suppliers;
  const hasResult = mode === 'quick' ? Boolean(quickResult) : Boolean(exactResult);

  return (
    <div className="space-y-6" data-testid="pesquisa-page">
      <PageHeader
        title="Pesquisa"
        description="Preços de compra recolhidos nos fornecedores, com data da última actualização."
      />

      <Card>
        <CardContent className="pt-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            <Tabs value={mode} onValueChange={setMode}>
              <TabsList>
                <TabsTrigger value="quick"><Search size={14} className="mr-1" /> Rápida</TabsTrigger>
                <TabsTrigger value="exact"><Target size={14} className="mr-1" /> Referência exacta</TabsTrigger>
              </TabsList>
            </Tabs>

            <div className="flex flex-col sm:flex-row gap-2">
              <div className="flex-1">
                <Input
                  placeholder="Medida: 205/55R16, 205 55 16 ou 2055516"
                  value={sizeInput}
                  onChange={(e) => setSizeInput(e.target.value)}
                  aria-invalid={sizeInvalid}
                  className={sizeInvalid ? 'border-red-400' : undefined}
                  data-testid="size-input"
                />
                <p className="text-xs mt-1 text-muted-foreground" data-testid="size-preview">
                  {sizeInvalid ? <span className="text-red-600">Medida não reconhecida</span> : parsed ? <>Medida: <span className="font-mono">{parsed.display}</span></> : ' '}
                </p>
              </div>
              <Button type="submit" disabled={loading} data-testid="search-btn">
                {loading ? <Loader2 size={16} className="mr-2 animate-spin" /> : <Search size={16} className="mr-2" />}
                Pesquisar
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={startRefresh}
                disabled={Boolean(requestId) || !parsed}
                title="Pede uma recolha nova a todos os fornecedores activos para esta medida"
                data-testid="refresh-btn"
              >
                {requestId ? <Loader2 size={16} className="mr-2 animate-spin" /> : <CloudDownload size={16} className="mr-2" />}
                Actualizar nos fornecedores
              </Button>
            </div>

            {mode === 'exact' && (
              <div className="rounded-md border border-dashed p-3 space-y-2">
                <p className="text-xs font-medium">Referência pretendida</p>
                <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3">
                  <Field label="Marca" htmlFor="w-brand"><BrandInput id="w-brand" value={wanted.brand} onChange={setW('brand')} options={brandOptions} /></Field>
                  <Field label="Modelo" htmlFor="w-model"><Input id="w-model" value={wanted.model} onChange={(e) => setW('model')(e.target.value)} /></Field>
                  <Field label="Carga" htmlFor="w-load"><Input id="w-load" value={wanted.load_index} onChange={(e) => setW('load_index')(e.target.value)} /></Field>
                  <Field label="Velocidade" htmlFor="w-speed"><Input id="w-speed" maxLength={2} value={wanted.speed_index} onChange={(e) => setW('speed_index')(e.target.value)} /></Field>
                  <Field label="XL" htmlFor="w-xl"><TriSelect id="w-xl" value={wanted.xl} onChange={setW('xl')} anyLabel="Indiferente" /></Field>
                  <Field label="RunFlat" htmlFor="w-rf"><TriSelect id="w-rf" value={wanted.runflat} onChange={setW('runflat')} anyLabel="Indiferente" /></Field>
                  <Field label="Estação" htmlFor="w-season"><SeasonSelect id="w-season" value={wanted.season} onChange={setW('season')} /></Field>
                </div>
              </div>
            )}

            <details className="group" open>
              <summary className="cursor-pointer text-sm font-medium select-none">Filtros</summary>
              <div className="mt-3 grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-3">
                {mode === 'quick' && (
                  <>
                    <Field label="Marca" htmlFor="f-brand"><MultiBrandSelect id="f-brand" value={filters.brand} onChange={setF('brand')} options={brandOptions.map((b) => ({ value: b }))} placeholder="" showAllOnFocus={false} /></Field>
                    <Field label="Modelo" htmlFor="f-model"><Input id="f-model" value={filters.model} onChange={(e) => setF('model')(e.target.value)} /></Field>
                    <Field label="Carga" htmlFor="f-load"><Input id="f-load" value={filters.load_index} onChange={(e) => setF('load_index')(e.target.value)} /></Field>
                    <Field label="Velocidade" htmlFor="f-speed"><Input id="f-speed" maxLength={2} value={filters.speed_index} onChange={(e) => setF('speed_index')(e.target.value)} /></Field>
                    <Field label="XL" htmlFor="f-xl"><TriSelect id="f-xl" value={filters.xl} onChange={setF('xl')} /></Field>
                    <Field label="RunFlat" htmlFor="f-rf"><TriSelect id="f-rf" value={filters.runflat} onChange={setF('runflat')} /></Field>
                    <Field label="Estação" htmlFor="f-season"><SeasonSelect id="f-season" value={filters.season} onChange={setF('season')} /></Field>
                  </>
                )}
                <Field label="Fornecedor" htmlFor="f-sup">
                  <NativeSelect id="f-sup" value={filters.supplier_id} onChange={(e) => setF('supplier_id')(e.target.value)}>
                    <option value="">Todos</option>
                    {supplierChoices.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                  </NativeSelect>
                </Field>
                <Field label="Preço mín. (€)" htmlFor="f-min"><Input id="f-min" inputMode="decimal" value={filters.min_price} onChange={(e) => setF('min_price')(e.target.value)} /></Field>
                <Field label="Preço máx. (€)" htmlFor="f-max"><Input id="f-max" inputMode="decimal" value={filters.max_price} onChange={(e) => setF('max_price')(e.target.value)} /></Field>
                <div className="col-span-2 md:col-span-4 xl:col-span-6 flex flex-wrap gap-x-5 gap-y-2 text-sm">
                  <label className="flex items-center gap-2"><input type="checkbox" checked={grouped} onChange={(e) => setGrouped(e.target.checked)} data-testid="group-toggle" /> Agrupar por modelo</label>
                  <label className="flex items-center gap-2"><input type="checkbox" checked={filters.in_stock} onChange={(e) => setF('in_stock')(e.target.checked)} /> Só com stock</label>
                  <label className="flex items-center gap-2"><input type="checkbox" checked={filters.show_stale} onChange={(e) => setF('show_stale')(e.target.checked)} /> Mostrar desactualizados</label>
                  {mode === 'exact' && (
                    <label className="flex items-center gap-2"><input type="checkbox" checked={filters.include_incompatible} onChange={(e) => setF('include_incompatible')(e.target.checked)} /> Mostrar incompatíveis</label>
                  )}
                  {mode === 'quick' && (
                    <label className="flex items-center gap-2"><input type="checkbox" checked={filters.include_unlisted} onChange={(e) => setF('include_unlisted')(e.target.checked)} /> Incluir artigos já não listados</label>
                  )}
                  <button type="button" className="text-xs text-muted-foreground hover:underline" onClick={() => { setFilters(EMPTY_FILTERS); setWanted(EMPTY_WANTED); }}>
                    Limpar filtros
                  </button>
                </div>
              </div>
            </details>
          </form>
        </CardContent>
      </Card>

      {error && <ErrorState message={error} onRetry={lastQuery ? handleSubmit : undefined} />}

      <RefreshProgress refresh={refresh} onClose={() => setRefresh(null)} />

      {loading && <Card><CardContent className="p-0"><TableSkeleton rows={6} cols={6} /></CardContent></Card>}

      {!loading && !hasResult && !error && (
        <Card>
          <EmptyState
            title="Indique uma medida para pesquisar"
            description="A pesquisa rápida mostra todas as ofertas guardadas para a medida. Use 'Referência exacta' para separar correspondências exactas de alternativas, e 'Actualizar nos fornecedores' para pedir preços novos."
          />
        </Card>
      )}

      {!loading && mode === 'quick' && quickResult && (
        <Card>
          <CardHeader className="pb-2 flex flex-row items-start justify-between gap-3 space-y-0">
            <div className="min-w-0">
            <CardTitle className="text-base">
              {quickOffers.length} ofertas{grouped && quickOffers.length ? ` em ${groupOffers(quickOffers).length} pneus` : ''} para <span className="font-mono">{quickResult.size || lastQuery?.size}</span>
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              Gerado {formatDateTime(quickResult.generated_at)}
              {hiddenStale > 0 && ` · ${hiddenStale} ofertas desactualizadas ocultas`}
            </p>
            </div>
            <div className="flex rounded-md border text-xs overflow-hidden flex-shrink-0" role="group" aria-label="Vista dos resultados">
              <button type="button" onClick={() => changeLayout('list')} aria-pressed={layout === 'list'} data-testid="layout-list"
                className={`inline-flex items-center gap-1 px-2 py-1 ${layout === 'list' ? 'bg-muted font-medium' : ''}`}>
                <List size={14} /> Lista
              </button>
              <button type="button" onClick={() => changeLayout('tiers')} aria-pressed={layout === 'tiers'} data-testid="layout-tiers"
                className={`inline-flex items-center gap-1 px-2 py-1 border-l ${layout === 'tiers' ? 'bg-muted font-medium' : ''}`}>
                <Columns3 size={14} /> Comparativa
              </button>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {quickOffers.length ? (
              layout === 'tiers'
                ? <TierColumns offers={quickOffers} tierMap={tierMap} sortDir={sortDir} grouped={grouped} />
                : <OffersTable offers={quickOffers} sortDir={sortDir} onToggleSort={toggleSort} grouped={grouped} />
            ) : (
              <EmptyState
                title="Sem ofertas para estes critérios"
                description="Alargue os filtros ou use 'Actualizar nos fornecedores' para pedir uma recolha nova."
              />
            )}
          </CardContent>
        </Card>
      )}

      {!loading && mode === 'exact' && exactResult && (
        <div className="space-y-4">
          {exactResult.warnings?.length > 0 && (
            <div className="rounded-md border border-amber-300 bg-amber-50 dark:bg-amber-500/10 dark:border-amber-500/30 p-3 text-sm text-amber-800 dark:text-amber-300">
              <ul className="list-disc pl-5">{exactResult.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
            </div>
          )}
          {exactResult.status && exactResult.status !== 'complete' && (
            <p className="text-xs text-muted-foreground">
              Estado: {exactResult.status === 'partial' ? 'resultados parciais (há fornecedores sem dados actuais)' : exactResult.status === 'refreshing' ? 'a actualizar' : exactResult.status}
            </p>
          )}
          {exactResult.best_exact ? (
            <BestExactCard offer={exactResult.best_exact} />
          ) : (
            <div className="rounded-md border p-3 text-sm text-muted-foreground">Nenhuma oferta com correspondência exacta.</div>
          )}
          <Section
            grouped={grouped}
            title="Correspondência exacta"
            tone="green"
            offers={exactFilter(exactResult.results?.exact)}
            sortDir={sortDir}
            onToggleSort={toggleSort}
            highlightId={exactResult.best_exact?.id}
            emptyText="Sem ofertas exactas para a referência indicada."
          />
          <Section
            grouped={grouped}
            title="Alternativas compatíveis"
            tone="blue"
            description="Pneus que servem na mesma medida mas diferem da referência pedida (ver motivos). Não são comparáveis em preço com a referência."
            offers={exactFilter(exactResult.results?.alternatives)}
            sortDir={sortDir}
            onToggleSort={toggleSort}
            emptyText="Sem alternativas compatíveis."
          />
          <Section
            grouped={grouped}
            title="Informação insuficiente"
            tone="amber"
            description="Ofertas em que o fornecedor não indica atributos suficientes para confirmar a correspondência."
            offers={exactFilter(exactResult.results?.insufficient)}
            sortDir={sortDir}
            onToggleSort={toggleSort}
            emptyText="Nenhuma."
          />
          {exactResult.results?.incompatible && (
            <Section
              grouped={grouped}
              title="Incompatíveis"
              tone="red"
              description="Não servem como substituto da referência pedida (ver motivos)."
              offers={exactFilter(exactResult.results.incompatible)}
              sortDir={sortDir}
              onToggleSort={toggleSort}
              emptyText="Nenhuma."
            />
          )}
        </div>
      )}

      {!loading && hasResult && <SupplierFreshnessPanel suppliers={freshness} />}
    </div>
  );
};

export default Pesquisa;
