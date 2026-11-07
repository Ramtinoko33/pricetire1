import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AlertTriangle, BookOpen, Clock, Database, TrendingDown, ArrowRight, CheckCircle2, History } from 'lucide-react';
import { catalogAPI, opsAPI, searchAPI } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { errorMessage, formatAge, formatDateTime, formatLoadSpeed, formatPct, formatPrice, parseDate } from '@/lib/format';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ErrorState, EmptyState, KpiCard, TableSkeleton } from '@/components/common';
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
    <Card data-testid="recent-searches">
      <CardHeader className="pb-2 flex flex-row items-center justify-between gap-3 space-y-0">
        <CardTitle className="text-base flex items-center gap-2"><History size={16} /> Últimas pesquisas</CardTitle>
        {isAdmin && (
          <div className="flex rounded-md border text-xs overflow-hidden">
            <button type="button" onClick={() => setEveryone(false)} className={`px-2 py-1 ${!everyone ? 'bg-muted font-medium' : ''}`}>As minhas</button>
            <button type="button" onClick={() => setEveryone(true)} className={`px-2 py-1 border-l ${everyone ? 'bg-muted font-medium' : ''}`}>Todos os utilizadores</button>
          </div>
        )}
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
                className="w-full text-left flex items-center justify-between gap-3 px-4 sm:px-6 py-2.5 hover:bg-muted/50"
                title="Repetir esta pesquisa"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium">
                    <span className="font-mono">{r.size_input || r.size_key}</span>
                    <span className="ml-2 text-xs font-normal text-muted-foreground">{r.mode === 'exact' ? 'Referência exacta' : 'Rápida'}</span>
                  </p>
                  <p className="text-xs text-muted-foreground truncate">
                    {formatDateTime(r.created_at)}
                    {everyone && (r.user_name || r.user_email) ? ` · ${r.user_name || r.user_email}` : ''}
                    {paramsSummary(r.params) ? ` · ${paramsSummary(r.params)}` : ''}
                  </p>
                </div>
                <div className="text-right flex-shrink-0">
                  <p className="text-sm font-mono font-semibold">{r.best_price != null ? formatPrice(r.best_price) : '—'}</p>
                  <p className="text-xs text-muted-foreground">{r.results ?? 0} resultado(s)</p>
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
    <div className="space-y-6 sm:space-y-8" data-testid="dashboard">
      {(errors.status || errors.comparison) && (
        <div className="space-y-2">
          {errors.status && <ErrorState message={errors.status} onRetry={load} />}
          {errors.comparison && <ErrorState message={errors.comparison} onRetry={load} />}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 sm:gap-6">
        <KpiCard
          title="Fornecedores OK"
          value={status ? `${okSuppliers.length}/${activeSuppliers.length}` : '—'}
          sub="activos com a última recolha bem-sucedida"
          icon={Database}
          tone="text-indigo-600 dark:text-indigo-400"
          bg="bg-indigo-100 dark:bg-indigo-900/30"
          loading={loading}
          testId="kpi-suppliers"
        />
        <KpiCard
          title="Última recolha"
          value={lastCollection ? formatAge(lastCollection) : '—'}
          sub={lastCollection ? formatDateTime(lastCollection) : 'sem recolhas registadas'}
          icon={Clock}
          tone="text-blue-600 dark:text-blue-400"
          bg="bg-blue-100 dark:bg-blue-900/30"
          loading={loading}
          testId="kpi-last-collection"
        />
        <KpiCard
          title="Oportunidades de poupança"
          value={comparison ? opportunities.length : '—'}
          sub="referências do catálogo com preço exacto abaixo do de referência"
          icon={TrendingDown}
          tone="text-green-600 dark:text-green-400"
          bg="bg-green-100 dark:bg-green-900/30"
          loading={loading}
          testId="kpi-opportunities"
        />
        <KpiCard
          title="Referências no catálogo"
          value={comparison ? comparison.length : '—'}
          sub={alarms.length ? `${alarms.length} alarme(s) activo(s)` : 'sem alarmes activos'}
          icon={BookOpen}
          loading={loading}
          testId="kpi-catalog"
        />
      </div>

      <RecentSearches isAdmin={isAdmin} />

      {alarms.length > 0 && (
        <Card className="border-amber-300 dark:border-amber-500/30">
          <CardHeader className="pb-2">
            <CardTitle className="text-base flex items-center gap-2"><AlertTriangle size={16} className="text-amber-600" /> Alarmes</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            {alarms.map((a, i) => (
              <div key={i} className="flex flex-wrap gap-x-2">
                <span className={['critical', 'error'].includes(String(a.level).toLowerCase()) ? 'text-red-700 dark:text-red-400 font-medium' : 'text-amber-700 dark:text-amber-300 font-medium'}>{a.message}</span>
                {a.since && <span className="text-xs text-muted-foreground">desde {formatDateTime(a.since)}</span>}
              </div>
            ))}
            {isAdmin && <Link to="/operacao" className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline mt-2">Ver operação <ArrowRight size={12} /></Link>}
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 sm:gap-6">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Maiores oportunidades (correspondência exacta)</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {loading ? <TableSkeleton rows={4} cols={3} /> : opportunities.length === 0 ? (
              <EmptyState
                title="Sem oportunidades neste momento"
                description="Quando um fornecedor tiver uma referência do catálogo abaixo do seu preço de referência, aparece aqui."
                action={isAdmin ? <Link to="/catalogo" className="text-sm text-blue-600 hover:underline">Gerir catálogo</Link> : undefined}
              />
            ) : (
              <div className="divide-y divide-border">
                {opportunities.slice(0, 8).map((r) => (
                  <div key={r.item?.id ?? r.item?.reference} className="flex items-center justify-between gap-3 px-4 sm:px-6 py-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{[r.item?.brand, r.item?.model].filter(Boolean).join(' ') || r.item?.reference}</p>
                      <p className="text-xs text-muted-foreground font-mono">{r.item?.size_display || r.item?.size_key} {formatLoadSpeed(r.item)} · {r.best_exact?.supplier_name}</p>
                    </div>
                    <div className="text-right flex-shrink-0">
                      <p className="text-sm font-mono font-bold text-green-700 dark:text-green-400">{formatPrice(r.saving_eur)}</p>
                      <p className="text-xs text-muted-foreground">{formatPct(r.saving_pct)} · {formatPrice(r.best_exact?.price)}</p>
                    </div>
                  </div>
                ))}
                {isAdmin && <div className="px-4 sm:px-6 py-3">
                  <Link to="/catalogo" className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline">Ver comparação completa <ArrowRight size={12} /></Link>
                </div>}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-base">Fornecedores</CardTitle></CardHeader>
          <CardContent className="p-0">
            {loading ? <TableSkeleton rows={4} cols={3} /> : suppliers.length === 0 ? (
              <EmptyState title="Sem fornecedores" action={isAdmin ? <Link to="/suppliers" className="text-sm text-blue-600 hover:underline">Configurar fornecedores</Link> : undefined} />
            ) : (
              <div className="divide-y divide-border">
                {suppliers.map((s) => {
                  const h = s.health || s;
                  return (
                    <div key={s.supplier_id ?? s.id ?? s.supplier_name ?? s.name} className="flex items-center justify-between gap-3 px-4 sm:px-6 py-2.5">
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

      {!loading && !errors.status && alarms.length === 0 && (
        <p className="text-xs text-muted-foreground flex items-center gap-1"><CheckCircle2 size={14} className="text-emerald-600" /> Operação sem alarmes.</p>
      )}
    </div>
  );
};

export default Dashboard;
