import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronRight, CloudDownload, Columns3, List, Loader2, Search, Trophy, X } from 'lucide-react';
import { toast } from 'sonner';
import { useSearchParams } from 'react-router-dom';
import { alertsAPI, searchAPI, suppliersAPI } from '@/lib/api';
import TierColumns from '@/components/TierColumns';
import { buildTierMap } from '@/lib/tiers';
import { errorMessage, formatAge, formatDateTime, formatLoadSpeed, formatPrice, parseSize } from '@/lib/format';
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
import { cn } from '@/lib/utils';

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

function Panel({ className, children, ...props }) {
  return <section className={cn('rounded-lg border bg-card text-card-foreground shadow-panel', className)} {...props}>{children}</section>;
}

function PanelHeader({ title, meta, children, className }) {
  return (
    <div className={cn('flex flex-col gap-3 px-4 py-4 sm:flex-row sm:items-start sm:justify-between sm:px-5', className)}>
      <div className="min-w-0">
        <h2 className="text-base font-bold leading-snug">{title}</h2>
        {meta && <p className="mt-1 text-xs text-muted-foreground">{meta}</p>}
      </div>
      {children}
    </div>
  );
}

function SupplierFreshnessPanel({ suppliers }) {
  if (!suppliers?.length) return null;
  return (
    <Panel>
      <PanelHeader title="Frescura por fornecedor" meta="Última recolha bem-sucedida de cada fornecedor para esta medida." />
      <div className="grid grid-cols-1 gap-px border-t bg-border sm:grid-cols-2 xl:grid-cols-3" data-testid="freshness-panel">
        {suppliers.map((s) => (
          <div key={s.supplier_id ?? s.supplier_name} className="space-y-1 bg-card px-4 py-3 text-xs sm:px-5">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-sm font-semibold">{s.supplier_name}</span>
              {s.is_active === false ? <ToneBadge>Inactivo</ToneBadge> : s.fresh ? <ToneBadge tone="green">Actual</ToneBadge> : <StaleBadge />}
            </div>
            <div className="text-muted-foreground">
              Último sucesso: <span className="tabular-nums">{formatDateTime(s.last_success_at)}</span> ({formatAge(s.last_success_at)})
            </div>
            <div className="flex flex-wrap gap-x-3 text-muted-foreground">
              <span>Ofertas: <span className="tabular-nums">{s.offers ?? 0}</span></span>
              {s.last_run_status && <span>Última execução: {s.last_run_status} {s.last_run_at ? `(${formatAge(s.last_run_at)})` : ''}</span>}
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function RefreshProgress({ refresh, onClose }) {
  if (!refresh) return null;
  const jobs = refresh.jobs || [];
  const finished = jobs.filter((j) => FINISHED.has(j.status)).length;
  const pct = jobs.length ? Math.round((finished / jobs.length) * 100) : 0;
  return (
    <Panel className="border-l-[3px] border-l-info" data-testid="refresh-progress">
      <div className="px-4 pt-4 sm:px-5">
        <div className="flex items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-base font-bold">
            {!refresh.done && !refresh.timedOut && <Loader2 size={16} className="animate-spin text-info" />}
            Actualização nos fornecedores
          </h2>
          {(refresh.done || refresh.timedOut) && (
            <Button variant="ghost" size="sm" onClick={onClose} aria-label="Fechar"><X size={14} /></Button>
          )}
        </div>
        <p className="mt-1 text-xs text-muted-foreground" role="status">
          {refresh.timedOut
            ? 'O pedido ultrapassou 30 min. Os jobs continuam na fila; acompanhe-os em Operação.'
            : refresh.done
              ? `Concluído: ${finished}/${jobs.length} fornecedores.`
              : `${finished}/${jobs.length} fornecedores concluídos. Os resultados são actualizados à medida que cada fornecedor termina.`}
        </p>
        <Progress value={pct} className="mt-3 h-1.5" aria-label="Progresso da actualização" />
      </div>
      <div className="mt-3 divide-y divide-border border-t text-sm">
        {jobs.map((j) => (
          <div key={j.job_id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 sm:px-5">
            <span className="min-w-[120px] font-semibold">{j.supplier_name}</span>
            <JobStatusBadge status={j.status} />
            {j.deduplicated && <ToneBadge tone="sky" title="Já existia um pedido igual na fila">Reaproveitado</ToneBadge>}
            {j.products != null && <span className="text-xs text-muted-foreground">{j.products} produtos</span>}
            {j.error && (
              <span className="w-full text-xs text-danger sm:w-auto">
                {ERROR_KIND_LABELS[j.error_kind] ? `${ERROR_KIND_LABELS[j.error_kind]}: ` : ''}{j.error}
              </span>
            )}
          </div>
        ))}
      </div>
    </Panel>
  );
}

function BestExactCard({ offer }) {
  if (!offer) return null;
  return (
    <Panel className="border-l-[3px] border-l-success" data-testid="best-exact">
      <div className="flex flex-col justify-between gap-3 px-4 py-4 sm:flex-row sm:items-center sm:px-5">
        <div className="flex items-start gap-3">
          <Trophy className="mt-0.5 flex-shrink-0 text-success" size={20} aria-hidden="true" />
          <div>
            <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-success">Melhor preço — correspondência exacta</p>
            <p className="mt-0.5 font-bold">{offer.brand} {offer.model} <span className="text-sm font-semibold tabular-nums text-muted-foreground">{formatLoadSpeed(offer)}</span></p>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
              <span className="font-semibold">{offer.supplier_name}</span>
              <StockBadge status={offer.stock_status} qty={offer.stock_qty} />
              <OfferFlags offer={offer} />
              <span className="tabular-nums text-muted-foreground">{formatDateTime(offer.last_seen_at)}</span>
              {offer.fresh === false && <StaleBadge />}
            </div>
          </div>
        </div>
        <p className="whitespace-nowrap text-[28px] font-extrabold tracking-[-0.03em] tabular-nums text-success">{formatPrice(offer.price, offer.currency)}</p>
      </div>
    </Panel>
  );
}

function Section({ title, description, offers, sortDir, onToggleSort, emptyText, tone, highlightId, grouped }) {
  return (
    <Panel className="overflow-hidden">
      <PanelHeader
        title={<span className="flex items-center gap-2">{title} <ToneBadge tone={tone}>{offers?.length || 0}</ToneBadge></span>}
        meta={description}
      />
      {offers?.length ? (
        <div className="border-t">
          <OffersTable offers={sortOffersByPrice(offers, sortDir)} sortDir={sortDir} onToggleSort={onToggleSort} showMatch highlightId={highlightId} grouped={grouped} />
        </div>
      ) : (
        <p className="border-t px-4 py-4 text-sm text-muted-foreground sm:px-5">{emptyText}</p>
      )}
    </Panel>
  );
}

function CheckOption({ checked, onChange, children, testId }) {
  return (
    <label className="inline-flex min-h-8 cursor-pointer items-center gap-2 text-[13px] text-foreground">
      <input type="checkbox" className="h-4 w-4 cursor-pointer rounded-sm border-input" checked={checked} onChange={(e) => onChange(e.target.checked)} data-testid={testId} />
      {children}
    </label>
  );
}

function ViewToggle({ layout, onChange }) {
  const opt = (value, Icon, label, testId) => (
    <button
      type="button"
      onClick={() => onChange(value)}
      aria-pressed={layout === value}
      data-testid={testId}
      className={cn(
        'inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-xs font-semibold transition-colors',
        layout === value ? 'bg-card text-primary shadow-panel ring-1 ring-primary/40' : 'text-muted-foreground hover:text-foreground',
      )}
    >
      <Icon size={14} aria-hidden="true" /> {label}
    </button>
  );
  return (
    <div className="inline-flex flex-shrink-0 self-start rounded-lg bg-muted p-0.5" role="group" aria-label="Vista dos resultados">
      {opt('list', List, 'Lista', 'layout-list')}
      {opt('tiers', Columns3, 'Comparativa', 'layout-tiers')}
    </div>
  );
}

const fmtCount = (n) => Number(n || 0).toLocaleString('pt-PT');

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

  const quickGroups = grouped && quickOffers.length ? groupOffers(quickOffers).length : null;
  const shownSize = quickResult?.size || lastQuery?.size;

  return (
    <div className="space-y-6" data-testid="pesquisa-page">
      <PageHeader
        eyebrow="Preços de compra"
        title="Pesquisa"
        description="Compare preços de compra, stock e datas de recolha nos fornecedores."
      />

      <Panel className="border-t-[3px] border-t-primary px-4 pb-4 pt-4 sm:px-6 sm:pb-5">
        <form onSubmit={handleSubmit}>
          <Tabs value={mode} onValueChange={setMode}>
            <TabsList className="w-full justify-start" aria-label="Tipo de pesquisa">
              <TabsTrigger value="quick">Rápida</TabsTrigger>
              <TabsTrigger value="exact">Referência exacta</TabsTrigger>
            </TabsList>
          </Tabs>

          <div className="mt-5">
            <label htmlFor="size-input" className="mb-1.5 block text-xs font-semibold">Medida do pneu</label>
            <div className="flex flex-col gap-2.5 md:flex-row md:items-start">
              <div className="min-w-0 flex-1">
                <Input
                  id="size-input"
                  placeholder="205/55R16, 205 55 16 ou 2055516"
                  value={sizeInput}
                  onChange={(e) => setSizeInput(e.target.value)}
                  aria-invalid={sizeInvalid}
                  aria-describedby="size-preview"
                  autoComplete="off"
                  className="h-11 text-base tabular-nums md:h-10 md:text-[15px]"
                  data-testid="size-input"
                />
                <p id="size-preview" className="mt-1.5 min-h-[18px] text-xs text-muted-foreground" data-testid="size-preview" aria-live="polite">
                  {sizeInvalid ? <span className="font-medium text-danger">Medida não reconhecida</span> : parsed ? <>Medida: <span className="font-semibold tabular-nums text-foreground">{parsed.display}</span></> : ' '}
                </p>
              </div>
              <div className="grid grid-cols-2 gap-2.5 md:flex">
                <Button type="submit" disabled={loading} className="h-11 md:h-10 md:px-5" data-testid="search-btn">
                  {loading ? <Loader2 size={16} className="animate-spin" /> : <Search size={16} />}
                  Pesquisar
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={startRefresh}
                  disabled={Boolean(requestId) || !parsed}
                  title="Pede uma recolha nova a todos os fornecedores activos para esta medida"
                  className="h-11 whitespace-normal px-3 leading-tight md:h-10 md:whitespace-nowrap md:px-4"
                  data-testid="refresh-btn"
                >
                  {requestId ? <Loader2 size={16} className="animate-spin" /> : <CloudDownload size={16} />}
                  Actualizar nos fornecedores
                </Button>
              </div>
            </div>
          </div>

          {mode === 'exact' && (
            <fieldset className="mt-4 rounded-lg border border-dashed border-input/60 bg-muted/40 p-3 sm:p-4">
              <legend className="px-1 text-xs font-semibold">Referência pretendida</legend>
              <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
                <Field label="Marca" htmlFor="w-brand"><BrandInput id="w-brand" value={wanted.brand} onChange={setW('brand')} options={brandOptions} /></Field>
                <Field label="Modelo" htmlFor="w-model"><Input id="w-model" value={wanted.model} onChange={(e) => setW('model')(e.target.value)} /></Field>
                <Field label="Carga" htmlFor="w-load"><Input id="w-load" value={wanted.load_index} onChange={(e) => setW('load_index')(e.target.value)} /></Field>
                <Field label="Velocidade" htmlFor="w-speed"><Input id="w-speed" maxLength={2} value={wanted.speed_index} onChange={(e) => setW('speed_index')(e.target.value)} /></Field>
                <Field label="XL" htmlFor="w-xl"><TriSelect id="w-xl" value={wanted.xl} onChange={setW('xl')} anyLabel="Indiferente" /></Field>
                <Field label="RunFlat" htmlFor="w-rf"><TriSelect id="w-rf" value={wanted.runflat} onChange={setW('runflat')} anyLabel="Indiferente" /></Field>
                <Field label="Estação" htmlFor="w-season"><SeasonSelect id="w-season" value={wanted.season} onChange={setW('season')} /></Field>
              </div>
            </fieldset>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-1 border-t pt-3">
            <CheckOption checked={grouped} onChange={setGrouped} testId="group-toggle">Agrupar por modelo</CheckOption>
            <CheckOption checked={filters.in_stock} onChange={setF('in_stock')}>Só com stock</CheckOption>
            <CheckOption checked={filters.show_stale} onChange={setF('show_stale')}>Mostrar desactualizados</CheckOption>
            {mode === 'exact' && (
              <CheckOption checked={filters.include_incompatible} onChange={setF('include_incompatible')}>Mostrar incompatíveis</CheckOption>
            )}
            {mode === 'quick' && (
              <CheckOption checked={filters.include_unlisted} onChange={setF('include_unlisted')}>Incluir artigos já não listados</CheckOption>
            )}
            <button type="button" className="ml-auto min-h-8 rounded-md px-2 text-xs font-semibold text-primary hover:bg-accent" onClick={() => { setFilters(EMPTY_FILTERS); setWanted(EMPTY_WANTED); }}>
              Limpar filtros
            </button>
          </div>

          <details className="group mt-1" open>
            <summary className="flex min-h-9 cursor-pointer list-none items-center gap-1.5 rounded-md text-[13px] font-bold select-none [&::-webkit-details-marker]:hidden">
              <ChevronRight size={15} className="transition-transform group-open:rotate-90" aria-hidden="true" />
              Mais filtros
              <span className="hidden font-medium text-muted-foreground sm:inline">· {mode === 'quick' ? 'marca, modelo, índice, fornecedor e preço' : 'fornecedor e preço'}</span>
            </summary>
            <div className="mt-2 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
              {mode === 'quick' && (
                <>
                  <Field label="Marca" htmlFor="f-brand" className="col-span-2"><MultiBrandSelect id="f-brand" value={filters.brand} onChange={setF('brand')} options={brandOptions.map((b) => ({ value: b }))} placeholder="" showAllOnFocus={false} /></Field>
                  <Field label="Modelo" htmlFor="f-model" className="col-span-2 xl:col-span-1"><Input id="f-model" value={filters.model} onChange={(e) => setF('model')(e.target.value)} /></Field>
                  <Field label="Carga" htmlFor="f-load"><Input id="f-load" value={filters.load_index} onChange={(e) => setF('load_index')(e.target.value)} /></Field>
                  <Field label="Velocidade" htmlFor="f-speed"><Input id="f-speed" maxLength={2} value={filters.speed_index} onChange={(e) => setF('speed_index')(e.target.value)} /></Field>
                  <Field label="XL" htmlFor="f-xl"><TriSelect id="f-xl" value={filters.xl} onChange={setF('xl')} /></Field>
                  <Field label="RunFlat" htmlFor="f-rf"><TriSelect id="f-rf" value={filters.runflat} onChange={setF('runflat')} /></Field>
                  <Field label="Estação" htmlFor="f-season"><SeasonSelect id="f-season" value={filters.season} onChange={setF('season')} /></Field>
                </>
              )}
              <Field label="Fornecedor" htmlFor="f-sup" className={mode === 'quick' ? 'xl:col-span-2' : 'col-span-2 md:col-span-2'}>
                <NativeSelect id="f-sup" value={filters.supplier_id} onChange={(e) => setF('supplier_id')(e.target.value)}>
                  <option value="">Todos</option>
                  {supplierChoices.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </NativeSelect>
              </Field>
              <Field label="Preço mín. (€)" htmlFor="f-min"><Input id="f-min" inputMode="decimal" value={filters.min_price} onChange={(e) => setF('min_price')(e.target.value)} /></Field>
              <Field label="Preço máx. (€)" htmlFor="f-max"><Input id="f-max" inputMode="decimal" value={filters.max_price} onChange={(e) => setF('max_price')(e.target.value)} /></Field>
            </div>
          </details>
        </form>
      </Panel>

      {error && <ErrorState message={error} onRetry={lastQuery ? handleSubmit : undefined} />}

      <RefreshProgress refresh={refresh} onClose={() => setRefresh(null)} />

      {loading && <Panel className="overflow-hidden"><TableSkeleton rows={6} cols={6} /></Panel>}

      {!loading && !hasResult && !error && (
        <Panel>
          <EmptyState
            icon={Search}
            title="Indique uma medida para pesquisar"
            description="A pesquisa rápida mostra todas as ofertas guardadas para a medida. Use 'Referência exacta' para separar correspondências exactas de alternativas, e 'Actualizar nos fornecedores' para pedir preços novos."
          />
        </Panel>
      )}

      {!loading && mode === 'quick' && quickResult && (
        <Panel className="overflow-hidden" data-testid="quick-results">
          <PanelHeader
            title={<>Ofertas para <span className="tabular-nums">{shownSize}</span></>}
            meta={(
              <>
                {fmtCount(quickOffers.length)} ofertas
                {quickGroups != null && ` · ${fmtCount(quickGroups)} pneus`}
                {' · Pesquisa rápida · Gerado '}{formatDateTime(quickResult.generated_at)}
                {hiddenStale > 0 && ` · ${hiddenStale} ofertas desactualizadas ocultas`}
              </>
            )}
          >
            <ViewToggle layout={layout} onChange={changeLayout} />
          </PanelHeader>
          <div className="border-t">
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
          </div>
          {quickOffers.length > 0 && (
            <p className="border-t px-4 py-3 text-xs text-muted-foreground sm:px-5">
              Pesquisa rápida: o menor preço não confirma correspondência exacta. Use 'Referência exacta' para comparar a mesma referência.
            </p>
          )}
        </Panel>
      )}

      {!loading && mode === 'exact' && exactResult && (
        <div className="space-y-4">
          {exactResult.warnings?.length > 0 && (
            <div className="rounded-lg border border-warning/30 bg-warning-subtle p-3 text-sm text-warning" role="status">
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
            <div className="rounded-lg border bg-card px-4 py-3 text-sm text-muted-foreground sm:px-5">Nenhuma oferta com correspondência exacta.</div>
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
