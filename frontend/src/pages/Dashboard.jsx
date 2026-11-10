import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AlertTriangle, ArrowRight, CheckCircle2, History } from 'lucide-react';
import { catalogAPI, opsAPI, searchAPI } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { errorMessage, formatAge, formatDateTime, formatLoadSpeed, formatPct, formatPrice, parseDate } from '@/lib/format';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ErrorState, EmptyState, KpiStrip, PageHeader, TableSkeleton } from '@/components/common';
import { HealthBadge, healthKey } from '@/components/badges';

function latestDate(values) {
  let best = null;
  values.forEach((v) => {
    const d = parseDate(v);
    if (d && (!best || d > best)) best = d;
  });
  return best;
}

const PARAM_LABELS = {
  brand: 'Marca', model: 'Modelo', load_index: 'Carga', speed_index: 'Vel.', xl: 'XL', runflat: 'RunFlat',
  season: 'Estação', min_price: 'Mín.', max_price: 'Máx.', in_stock: 'Só com stock', supplier_id: 'Fornecedor',
};

function paramsSummary(params) {
  return Object.entries(params || {})
    .map(([k, v]) => (v === true || v === 'true' ? PARAM_LABELS[k] || k : `${PARAM_LABELS[k] || k}: ${Array.isArray(v) ? v.length : v}`))
    .join(' · ');
}

function RecentSearches({ isAdmin }) {
  const navigate = useNavigate();
  const [everyone, setEveryone] = useState(false);
  const [rows, setRows] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    searchAPI.recent({ limit: 10, all_users: everyone || undefined })
      .then(({ data }) => { if (alive) { setRows(data?.searches || []); setError(''); } })
      .catch((err) => { if (alive) { setRows([]); setError(errorMessage(err, 'Erro ao carregar as últimas pesquisas')); } });
    return () => { alive = false; };
  }, [everyone]);

  const open = (r) => {
    const q = new URLSearchParams({ size: r.size_input || r.size_key, mode: r.mode });
    navigate(`/precos?${q.toString()}`);
  };

  return (
    <Card className="overflow-hidden" data-testid="recent-searches">
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0 border-b px-4 py-4 sm:px-5">
        <CardTitle className="flex items-center gap-2"><History size={16} className="text-muted-foreground" aria-hidden="true" /> Últimas pesquisas</CardTitle>
        {isAdmin ? (
          <div className="inline-flex rounded-lg bg-muted p-0.5 text-xs" role="group" aria-label="Pesquisas a mostrar">
            <button type="button" aria-pressed={!everyone} onClick={() => setEveryone(false)} className={`h-7 rounded-md px-2.5 font-semibold ${!everyone ? 'bg-card text-primary shadow-panel ring-1 ring-primary/40' : 'text-muted-foreground hover:text-foreground'}`}>As minhas</button>
            <button type="button" aria-pressed={everyone} onClick={() => setEveryone(true)} className={`h-7 rounded-md px-2.5 font-semibold ${everyone ? 'bg-card text-primary shadow-panel ring-1 ring-primary/40' : 'text-muted-foreground hover:text-foreground'}`}>Todos os utilizadores</button>
          </div>
        ) : <span className="text-xs text-muted-foreground">As minhas</span>}
      </CardHeader>
      <CardContent className="p-0">
        {error && <ErrorState className="m-4" message={error} />}
        {rows === null ? <TableSkeleton rows={4} cols={4} /> : rows.length === 0 ? (
          !error && <EmptyState title="Ainda sem pesquisas" description="As pesquisas feitas na página Pesquisa aparecem aqui." />
        ) : (
          <div className="divide-y divide-border">
            {rows.map((r) => (
              <button
                key={r.id}
                type="button"
                onClick={() => open(r)}
                className="flex w-full items-center justify-between gap-3 px-4 py-3.5 text-left hover:bg-accent/60 focus-visible:bg-accent sm:px-5"
                title="Repetir esta pesquisa"
              >
                <div className="min-w-0">
                  <p className="text-sm font-bold tabular-nums">{r.size_input || r.size_key}</p>
                  <p className="mt-0.5 truncate text-xs text-muted-foreground">
                    <span className="tabular-nums">{formatDateTime(r.created_at)}</span>
                    {' · '}{r.mode === 'exact' ? 'Referência exacta' : 'Rápida'}
                    {everyone && (r.user_name || r.user_email) ? ` · ${r.user_name || r.user_email}` : ''}
                    {paramsSummary(r.params) ? ` · ${paramsSummary(r.params)}` : ''}
                  </p>
                </div>
                <div className="text-right flex-shrink-0">
                  <p className="text-[15px] font-extrabold tabular-nums tracking-[-0.02em]">{r.best_price != null ? formatPrice(r.best_price) : '—'}</p>
                  <p className="mt-0.5 text-xs tabular-nums text-muted-foreground">{r.results ?? 0} resultado(s)</p>
                </div>
              </button>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

const Dashboard = () => {
  const { isAdmin } = useAuth();
  const [status, setStatus] = useState(null);
  const [comparison, setComparison] = useState(null);
  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    const [st, cmp] = await Promise.allSettled([opsAPI.status(), catalogAPI.comparison(false)]);
    const errs = {};
    if (st.status === 'fulfilled') setStatus(st.value.data); else errs.status = errorMessage(st.reason, 'Erro ao carregar o estado da operação');
    if (cmp.status === 'fulfilled') setComparison(Array.isArray(cmp.value.data) ? cmp.value.data : []); else errs.comparison = errorMessage(cmp.reason, 'Erro ao carregar a comparação do catálogo');
    setErrors(errs);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const suppliers = status?.suppliers || [];
  const activeSuppliers = suppliers.filter((s) => s.is_active !== false);
  const okSuppliers = activeSuppliers.filter((s) => healthKey(s.health || s) === 'ok');
  const lastCollection = status?.scheduler?.last_finished_at
    || latestDate(suppliers.map((s) => (s.health || s).last_success_at));
  const alarms = status?.alarms || [];

  const opportunities = useMemo(
    () => (comparison || []).filter((r) => r.status === 'saving').sort((a, b) => (b.saving_eur || 0) - (a.saving_eur || 0)),
    [comparison],
  );

  return (
    <div className="space-y-6" data-testid="dashboard">
      <PageHeader
        eyebrow="Visão geral"
        title="Dashboard"
        description="Estado das recolhas, pesquisas recentes e oportunidades do catálogo."
      />
      {(errors.status || errors.comparison) && (
        <div className="space-y-2">
          {errors.status && <ErrorState message={errors.status} onRetry={load} />}
          {errors.comparison && <ErrorState message={errors.comparison} onRetry={load} />}
        </div>
      )}

      <KpiStrip
        loading={loading}
        items={[
          {
            title: 'Fornecedores OK',
            value: status ? `${okSuppliers.length} / ${activeSuppliers.length}` : '—',
            sub: 'Activos com a última recolha bem-sucedida',
            testId: 'kpi-suppliers',
          },
          {
            title: 'Última recolha',
            value: lastCollection ? formatAge(lastCollection) : '—',
            sub: lastCollection ? formatDateTime(lastCollection) : 'Sem recolhas registadas',
            testId: 'kpi-last-collection',
          },
          {
            title: 'Oportunidades de poupança',
            value: comparison ? opportunities.length : '—',
            sub: 'Referências do catálogo com preço exacto abaixo do de referência',
            testId: 'kpi-opportunities',
          },
          {
            title: 'Referências no catálogo',
            value: comparison ? comparison.length : '—',
            sub: alarms.length ? `${alarms.length} alarme(s) activo(s)` : 'Sem alarmes activos',
            testId: 'kpi-catalog',
          },
        ]}
      />


      {alarms.length > 0 && (
        <Card className="border-l-[3px] border-l-warning">
          <CardHeader className="px-4 pb-2 pt-4 sm:px-5">
            <CardTitle className="flex items-center gap-2"><AlertTriangle size={16} className="text-warning" aria-hidden="true" /> Alarmes</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 px-4 pb-4 text-sm sm:px-5">
            {alarms.map((a, i) => (
              <div key={i} className="flex flex-wrap gap-x-2">
                <span className={['critical', 'error'].includes(String(a.level).toLowerCase()) ? 'text-red-700 dark:text-red-400 font-medium' : 'text-amber-700 dark:text-amber-300 font-medium'}>{a.message}</span>
                {a.since && <span className="text-xs text-muted-foreground">desde {formatDateTime(a.since)}</span>}
              </div>
            ))}
            {isAdmin && <Link to="/operacao" className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline mt-2">Ver operação <ArrowRight size={12} /></Link>}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] lg:items-start">
        <RecentSearches isAdmin={isAdmin} />
        <div className="space-y-5">
        <Card className="overflow-hidden">
          <CardHeader className="space-y-1 border-b px-4 py-4 sm:px-5">
            <CardTitle>Maiores oportunidades</CardTitle>
            <p className="text-xs text-muted-foreground">Apenas correspondências exactas.</p>
          </CardHeader>
          <CardContent className="p-0">
            {loading ? <TableSkeleton rows={4} cols={3} /> : opportunities.length === 0 ? (
              <EmptyState
                title="Sem oportunidades neste momento"
                description="Quando um fornecedor tiver uma referência do catálogo abaixo do seu preço de referência, aparece aqui."
                action={isAdmin ? <Link to="/catalogo" className="text-sm font-semibold text-primary hover:underline">Gerir catálogo</Link> : undefined}
              />
            ) : (
              <div className="divide-y divide-border">
                {opportunities.slice(0, 8).map((r) => (
                  <div key={r.item?.id ?? r.item?.reference} className="flex items-center justify-between gap-3 px-4 sm:px-5 py-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{[r.item?.brand, r.item?.model].filter(Boolean).join(' ') || r.item?.reference}</p>
                      <p className="text-xs text-muted-foreground tabular-nums">{r.item?.size_display || r.item?.size_key} {formatLoadSpeed(r.item)} · {r.best_exact?.supplier_name}</p>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className="text-sm font-extrabold tabular-nums text-success">{formatPrice(r.saving_eur)}</p>
                      <p className="text-xs text-muted-foreground">{formatPct(r.saving_pct)} · {formatPrice(r.best_exact?.price)}</p>
                    </div>
                  </div>
                ))}
                {isAdmin && <div className="px-4 sm:px-5 py-3">
                  <Link to="/catalogo" className="inline-flex items-center gap-1 text-xs font-semibold text-primary hover:underline">Ver comparação completa <ArrowRight size={12} /></Link>
                </div>}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="overflow-hidden">
          <CardHeader className="border-b px-4 py-4 sm:px-5"><CardTitle>Fornecedores</CardTitle></CardHeader>
          <CardContent className="p-0">
            {loading ? <TableSkeleton rows={4} cols={3} /> : suppliers.length === 0 ? (
              <EmptyState title="Sem fornecedores" action={isAdmin ? <Link to="/suppliers" className="text-sm font-semibold text-primary hover:underline">Configurar fornecedores</Link> : undefined} />
            ) : (
              <div className="divide-y divide-border">
                {suppliers.map((s) => {
                  const h = s.health || s;
                  return (
                    <div key={s.supplier_id ?? s.id ?? s.supplier_name ?? s.name} className="flex items-center justify-between gap-3 px-4 sm:px-5 py-2.5">
                      <div className="min-w-0">
                        <p className="text-sm font-medium truncate">{s.supplier_name || s.name}{s.is_active === false && <span className="text-xs text-muted-foreground"> (inactivo)</span>}</p>
                        <p className="text-xs text-muted-foreground">
                          {h.last_success_at ? `Último sucesso ${formatAge(h.last_success_at)}` : 'Sem sucesso registado'}
                          {(h.consecutive_failures || 0) > 0 && ` · ${h.consecutive_failures} falhas seguidas`}
                        </p>
                      </div>
                      <HealthBadge health={h} />
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>
        </div>
      </div>

      {!loading && !errors.status && alarms.length === 0 && (
        <p className="text-xs text-muted-foreground flex items-center gap-1"><CheckCircle2 size={14} className="text-success" aria-hidden="true" /> Operação sem alarmes.</p>
      )}
    </div>
  );
};

export default Dashboard;
