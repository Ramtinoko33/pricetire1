import { Link } from 'react-router-dom';
import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Ban, Clock, Loader2, Plus, RefreshCw, RotateCcw, Trash2, XCircle, CheckCircle2, PlayCircle, CalendarClock } from 'lucide-react';
import { useAuth } from '@/lib/auth';
import { toast } from 'sonner';
import { opsAPI, suppliersAPI } from '@/lib/api';
import { errorMessage, formatAge, formatDateTime, parseSize } from '@/lib/format';
import { useInterval } from '@/hooks/useInterval';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ConfirmDialog, EmptyState, ErrorState, Field, KpiCard, NativeSelect, PageHeader, TableSkeleton } from '@/components/common';
import { ERROR_KIND_LABELS, HealthBadge, HealthDetails, JOB_STATUS, JobStatusBadge, ToneBadge, WithTooltip } from '@/components/badges';

const AUTO_REFRESH_MS = 15000;
const JOB_TYPES = ['scrape', 'test_login', 'compare', 'refresh'];
const CANCELLABLE = new Set(['queued', 'pending', 'running']);
const RETRYABLE = new Set(['failed', 'partial', 'error', 'cancelled', 'canceled', 'timeout']);

const asList = (data, key) => (Array.isArray(data) ? data : Array.isArray(data?.[key]) ? data[key] : []);

function jobTarget(j) {
  const p = j.payload || {};
  return j.size || p.size || (Array.isArray(p.sizes) ? p.sizes.join(', ') : '') || '';
}

function AlarmList({ alarms }) {
  if (!alarms?.length) {
    return <p className="text-sm text-muted-foreground flex items-center gap-2"><CheckCircle2 size={16} className="text-emerald-600" /> Sem alarmes activos.</p>;
  }
  return (
    <div className="space-y-2" data-testid="alarms">
      {alarms.map((a, i) => {
        const critical = ['critical', 'error'].includes(String(a.level).toLowerCase());
        return (
          <div
            key={i}
            className={`flex items-start gap-2 rounded-md border p-2 text-sm ${critical
              ? 'border-red-300 bg-red-50 text-red-800 dark:bg-red-500/10 dark:border-red-500/30 dark:text-red-300'
              : 'border-amber-300 bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:border-amber-500/30 dark:text-amber-300'}`}
          >
            <AlertTriangle size={16} className="mt-0.5 flex-shrink-0" />
            <div className="flex-1">
              <div>{a.message}</div>
              {a.since && <div className="text-xs opacity-80">Desde {formatDateTime(a.since)} ({formatAge(a.since)})</div>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

const RUN_STATUS = {
  ok: { label: 'OK', tone: 'green' },
  empty: { label: 'Sem produtos', tone: 'amber' },
  error: { label: 'Erro', tone: 'red' },
};

function RunsHistory({ suppliers }) {
  const [supplierId, setSupplierId] = useState('');
  const [size, setSize] = useState('');
  const [runs, setRuns] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async (e) => {
    e?.preventDefault();
    const parsed = parseSize(size);
    setLoading(true);
    setError('');
    try {
      const { data } = await opsAPI.runs({ supplier_id: supplierId, size: parsed ? parsed.display : size.trim() });
      setRuns(asList(data, 'runs'));
      setLoaded(true);
    } catch (err) {
      setError(errorMessage(err, 'Erro ao carregar o histórico de recolhas'));
    } finally {
      setLoading(false);
    }
  }, [supplierId, size]);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Histórico de recolhas</CardTitle>
        <p className="text-xs text-muted-foreground">Resultado de cada recolha por fornecedor e medida.</p>
      </CardHeader>
      <CardContent className="space-y-3">
        <form onSubmit={load} className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto] gap-2 items-end">
          <Field label="Fornecedor" htmlFor="rh-sup">
            <NativeSelect id="rh-sup" value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
              <option value="">Todos</option>
              {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </NativeSelect>
          </Field>
          <Field label="Medida" htmlFor="rh-size"><Input id="rh-size" placeholder="205/55R16 (opcional)" value={size} onChange={(e) => setSize(e.target.value)} /></Field>
          <Button type="submit" variant="outline" disabled={loading}>
            {loading ? <Loader2 size={14} className="mr-2 animate-spin" /> : <RefreshCw size={14} className="mr-2" />} Ver histórico
          </Button>
        </form>
        {error && <ErrorState message={error} onRetry={load} />}
        {loaded && !loading && (runs.length === 0 ? (
          <p className="text-sm text-muted-foreground">Sem recolhas registadas para estes filtros.</p>
        ) : (
          <div className="max-h-[400px] overflow-auto border rounded-md">
            <Table>
              <TableHeader><TableRow><TableHead>Fim</TableHead><TableHead>Fornecedor</TableHead><TableHead>Medida</TableHead><TableHead>Estado</TableHead><TableHead className="text-right">Produtos</TableHead><TableHead>Erro</TableHead></TableRow></TableHeader>
              <TableBody>
                {runs.map((r, i) => {
                  const meta = RUN_STATUS[r.status] || { label: r.status || '—', tone: 'slate' };
                  return (
                    <TableRow key={r.id ?? i}>
                      <TableCell className="text-xs whitespace-nowrap">{formatDateTime(r.finished_at)} <span className="text-muted-foreground">({formatAge(r.finished_at)})</span></TableCell>
                      <TableCell className="text-sm whitespace-nowrap">{r.supplier_name || suppliers.find((s) => String(s.id) === String(r.supplier_id))?.name || '—'}</TableCell>
                      <TableCell className="font-mono text-xs">{r.size || r.size_key || '—'}</TableCell>
                      <TableCell><ToneBadge tone={meta.tone}>{meta.label}</ToneBadge></TableCell>
                      <TableCell className="text-right">{r.products ?? '—'}</TableCell>
                      <TableCell className="text-xs">{r.error_kind ? (ERROR_KIND_LABELS[r.error_kind] || r.error_kind) : ''}{r.error ? `${r.error_kind ? ': ' : ''}${r.error}` : ''}{!r.error_kind && !r.error ? '—' : ''}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

const Operacao = () => {
  const { isAdmin } = useAuth();
  const [runningScheduled, setRunningScheduled] = useState(false);
  const [confirmRun, setConfirmRun] = useState(false);
  const [status, setStatus] = useState(null);
  const [statusError, setStatusError] = useState('');
  const [jobs, setJobs] = useState([]);
  const [jobsError, setJobsError] = useState('');
  const [failures, setFailures] = useState([]);
  const [failuresError, setFailuresError] = useState('');
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [jobFilters, setJobFilters] = useState({ status: '', type: '', supplier_id: '', limit: 100 });
  const [busyJob, setBusyJob] = useState(null);

  const loadAll = useCallback(async () => {
    setRefreshing(true);
    const [st, jb, fl] = await Promise.allSettled([
      opsAPI.status(),
      opsAPI.jobs(jobFilters),
      opsAPI.failures({ limit: 50 }),
    ]);
    if (st.status === 'fulfilled') { setStatus(st.value.data); setStatusError(''); } else setStatusError(errorMessage(st.reason, 'Erro ao carregar o estado'));
    if (jb.status === 'fulfilled') { setJobs(asList(jb.value.data, 'jobs')); setJobsError(''); } else setJobsError(errorMessage(jb.reason, 'Erro ao carregar jobs'));
    if (fl.status === 'fulfilled') { setFailures(asList(fl.value.data, 'failures')); setFailuresError(''); } else setFailuresError(errorMessage(fl.reason, 'Erro ao carregar falhas'));
    setLastRefresh(new Date());
    setLoading(false);
    setRefreshing(false);
  }, [jobFilters]);

  useEffect(() => { loadAll(); }, [loadAll]);
  useInterval(loadAll, AUTO_REFRESH_MS);

  useEffect(() => {
    suppliersAPI.getAll().then(({ data }) => setSuppliers(Array.isArray(data) ? data : [])).catch(() => {});
  }, []);

  const jobAction = async (job, action) => {
    const id = job.id ?? job.job_id;
    setBusyJob(id);
    try {
      if (action === 'retry') await opsAPI.retryJob(id);
      else await opsAPI.cancelJob(id);
      toast.success(action === 'retry' ? 'Job reenfileirado' : 'Cancelamento pedido');
      loadAll();
    } catch (err) {
      toast.error(errorMessage(err, 'Erro na operação'));
    } finally {
      setBusyJob(null);
    }
  };

  const runScheduledNow = async () => {
    setConfirmRun(false);
    setRunningScheduled(true);
    try {
      const { data } = await opsAPI.runScheduledNow();
      const n = data?.enqueued ?? data?.jobs?.length;
      toast.success(typeof n === 'number' ? `Recolha agendada iniciada: ${n} job(s) enfileirados` : 'Recolha agendada iniciada');
      loadAll();
    } catch (err) {
      toast.error(errorMessage(err, 'Erro ao iniciar a recolha agendada'));
    } finally {
      setRunningScheduled(false);
    }
  };

  const q = status?.queue || {};
  const workers = status?.workers || [];
  const sched = status?.scheduler || {};
  const healthRows = status?.suppliers || [];
  const aliveWorkers = workers.filter((w) => w.alive).length;
  const setJF = (k) => (e) => setJobFilters((f) => ({ ...f, [k]: e.target.value }));

  return (
    <div className="space-y-6" data-testid="operacao-page">
      <PageHeader
        title="Operação"
        description={`Fila, workers, agendador e saúde dos fornecedores · actualização automática a cada 15 s${lastRefresh ? ` · ${lastRefresh.toLocaleTimeString('pt-PT')}` : ''}`}
        actions={(
          <>
            {isAdmin && (
              <Button onClick={() => setConfirmRun(true)} disabled={runningScheduled} data-testid="run-scheduled-now">
                {runningScheduled ? <Loader2 size={16} className="mr-2 animate-spin" /> : <CalendarClock size={16} className="mr-2" />}
                Correr recolha agendada agora
              </Button>
            )}
            <Button variant="outline" onClick={loadAll} disabled={refreshing}>
              <RefreshCw size={16} className={`mr-2 ${refreshing ? 'animate-spin' : ''}`} /> Actualizar
            </Button>
          </>
        )}
      />

      {statusError && <ErrorState message={statusError} onRetry={loadAll} />}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <KpiCard title="Em espera" value={q.queued ?? '—'} icon={Clock} loading={loading} />
        <KpiCard title="A correr" value={q.running ?? '—'} icon={PlayCircle} tone="text-blue-600 dark:text-blue-400" bg="bg-blue-100 dark:bg-blue-900/30" loading={loading} />
        <KpiCard title="Falhados (24 h)" value={q.failed_24h ?? '—'} icon={XCircle} tone="text-red-600 dark:text-red-400" bg="bg-red-100 dark:bg-red-900/30" loading={loading} />
        <KpiCard title="Concluídos (24 h)" value={q.done_24h ?? '—'} icon={CheckCircle2} tone="text-green-600 dark:text-green-400" bg="bg-green-100 dark:bg-green-900/30" loading={loading} />
      </div>

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Alarmes</CardTitle></CardHeader>
        <CardContent>{loading ? <TableSkeleton rows={1} cols={1} /> : <AlarmList alarms={status?.alarms} />}</CardContent>
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Workers <span className="text-sm font-normal text-muted-foreground">({aliveWorkers}/{workers.length} vivos)</span></CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            {loading ? <TableSkeleton rows={2} cols={4} /> : workers.length === 0 ? (
              <EmptyState title="Nenhum worker registado" description="Sem workers, os jobs ficam em espera. Verifique o serviço worker." />
            ) : (
              <Table>
                <TableHeader><TableRow><TableHead>Worker</TableHead><TableHead>Estado</TableHead><TableHead>Último sinal</TableHead><TableHead>Job actual</TableHead></TableRow></TableHeader>
                <TableBody>
                  {workers.map((w) => (
                    <TableRow key={w.worker_id}>
                      <TableCell className="font-mono text-xs">{w.worker_id}</TableCell>
                      <TableCell>{w.alive ? <ToneBadge tone="green">Vivo</ToneBadge> : <ToneBadge tone="red">Sem sinal</ToneBadge>}</TableCell>
                      <TableCell className="text-xs whitespace-nowrap">{formatDateTime(w.seen_at)} <span className="text-muted-foreground">({formatAge(w.seen_at)})</span></TableCell>
                      <TableCell className="font-mono text-xs">{w.current_job_id ?? '—'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2"><CardTitle className="text-base">Agendador</CardTitle></CardHeader>
          <CardContent className="text-sm space-y-2">
            {loading ? <TableSkeleton rows={3} cols={2} /> : (
              <>
                <div><span className="text-muted-foreground">Fuso horário: </span>{sched.timezone || '—'}</div>
                <div><span className="text-muted-foreground">Horários: </span>{sched.times?.length ? sched.times.join(' · ') : '—'}</div>
                <div>
                  <span className="text-muted-foreground">Próximas recolhas: </span>
                  {sched.next_categories?.length
                    ? sched.next_categories.map((r) => `${formatDateTime(r.at)} ${r.category}`).join(' · ')
                    : (sched.next_runs?.length ? sched.next_runs.map((r) => formatDateTime(r)).join(' · ') : '—')}
                </div>
                <Link to="/monitorizacao" className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline">Medidas e horários por categoria →</Link>
                <div><span className="text-muted-foreground">Último início: </span>{formatDateTime(sched.last_started_at)}{sched.last_started_at && <span className="text-muted-foreground"> ({formatAge(sched.last_started_at)})</span>}</div>
                <div><span className="text-muted-foreground">Último fim: </span>{sched.last_finished_at ? formatDateTime(sched.last_finished_at) : sched.last_started_at ? 'em curso…' : '—'}</div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Saúde dos fornecedores</CardTitle></CardHeader>
        <CardContent className="p-0">
          {loading ? <TableSkeleton rows={4} cols={4} /> : healthRows.length === 0 ? (
            <EmptyState title="Sem dados de saúde" />
          ) : (
            <Table>
              <TableHeader><TableRow><TableHead>Fornecedor</TableHead><TableHead>Saúde</TableHead><TableHead>Detalhe</TableHead><TableHead>Activo</TableHead></TableRow></TableHeader>
              <TableBody>
                {healthRows.map((s) => {
                  const health = s.health || s;
                  return (
                    <TableRow key={s.supplier_id ?? s.id ?? s.supplier_name ?? s.name}>
                      <TableCell className="font-medium whitespace-nowrap">{s.supplier_name || s.name}</TableCell>
                      <TableCell><HealthBadge health={health} /></TableCell>
                      <TableCell><HealthDetails health={health} /></TableCell>
                      <TableCell>{s.is_active === false ? <ToneBadge>Inactivo</ToneBadge> : <ToneBadge tone="green">Activo</ToneBadge>}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Jobs</CardTitle>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 pt-2">
            <Field label="Estado" htmlFor="jf-status">
              <NativeSelect id="jf-status" value={jobFilters.status} onChange={setJF('status')}>
                <option value="">Todos</option>
                {['queued', 'running', 'done', 'partial', 'failed', 'cancelled'].map((s) => <option key={s} value={s}>{JOB_STATUS[s]?.label || s}</option>)}
              </NativeSelect>
            </Field>
            <Field label="Tipo" htmlFor="jf-type">
              <NativeSelect id="jf-type" value={jobFilters.type} onChange={setJF('type')}>
                <option value="">Todos</option>
                {JOB_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              </NativeSelect>
            </Field>
            <Field label="Fornecedor" htmlFor="jf-sup">
              <NativeSelect id="jf-sup" value={jobFilters.supplier_id} onChange={setJF('supplier_id')}>
                <option value="">Todos</option>
                {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </NativeSelect>
            </Field>
            <Field label="Limite" htmlFor="jf-limit">
              <NativeSelect id="jf-limit" value={jobFilters.limit} onChange={setJF('limit')}>
                {[50, 100, 250, 500].map((n) => <option key={n} value={n}>{n}</option>)}
              </NativeSelect>
            </Field>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {jobsError && <ErrorState className="m-4" message={jobsError} onRetry={loadAll} />}
          {loading ? <TableSkeleton rows={5} cols={6} /> : jobs.length === 0 ? (
            <EmptyState title="Sem jobs para estes filtros" />
          ) : (
            <div className="max-h-[520px] overflow-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>ID</TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Fornecedor</TableHead>
                    <TableHead>Alvo</TableHead>
                    <TableHead>Estado</TableHead>
                    <TableHead>Tentativas</TableHead>
                    <TableHead>Criado</TableHead>
                    <TableHead>Fim</TableHead>
                    <TableHead>Erro</TableHead>
                    <TableHead className="text-right">Acções</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {jobs.map((j) => {
                    const id = j.id ?? j.job_id;
                    return (
                      <TableRow key={id}>
                        <TableCell className="font-mono text-xs">{id}</TableCell>
                        <TableCell className="text-xs">{j.type}</TableCell>
                        <TableCell className="text-sm whitespace-nowrap">{j.supplier_name || '—'}</TableCell>
                        <TableCell className="font-mono text-xs">{jobTarget(j) || '—'}</TableCell>
                        <TableCell><JobStatusBadge status={j.status} /></TableCell>
                        <TableCell className="text-xs">{j.attempts != null ? `${j.attempts}${j.max_attempts ? `/${j.max_attempts}` : ''}` : '—'}</TableCell>
                        <TableCell className="text-xs whitespace-nowrap">{formatDateTime(j.created_at)}</TableCell>
                        <TableCell className="text-xs whitespace-nowrap">{formatDateTime(j.finished_at)}</TableCell>
                        <TableCell className="text-xs max-w-[240px]">
                          {j.error || j.last_error ? (
                            <WithTooltip content={j.error || j.last_error}>
                              <span className="block truncate text-red-700 dark:text-red-400 cursor-help" title={j.error || j.last_error}>
                                {ERROR_KIND_LABELS[j.error_kind] ? `${ERROR_KIND_LABELS[j.error_kind]}: ` : ''}{j.error || j.last_error}
                              </span>
                            </WithTooltip>
                          ) : '—'}
                        </TableCell>
                        <TableCell>
                          <div className="flex justify-end gap-1">
                            {RETRYABLE.has(j.status) && (
                              <Button variant="outline" size="sm" onClick={() => jobAction(j, 'retry')} disabled={busyJob === id} title="Repetir" aria-label="Repetir">
                                <RotateCcw size={14} />
                              </Button>
                            )}
                            {CANCELLABLE.has(j.status) && (
                              <Button variant="outline" size="sm" onClick={() => jobAction(j, 'cancel')} disabled={busyJob === id} title="Cancelar" aria-label="Cancelar">
                                <Ban size={14} className="text-red-600" />
                              </Button>
                            )}
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2"><CardTitle className="text-base">Falhas recentes</CardTitle></CardHeader>
        <CardContent className="p-0">
          {failuresError && <ErrorState className="m-4" message={failuresError} onRetry={loadAll} />}
          {loading ? <TableSkeleton rows={3} cols={4} /> : failures.length === 0 ? (
            <EmptyState title="Sem falhas recentes" />
          ) : (
            <Table>
              <TableHeader><TableRow><TableHead>Quando</TableHead><TableHead>Fornecedor</TableHead><TableHead>Alvo</TableHead><TableHead>Tipo de erro</TableHead><TableHead>Mensagem</TableHead></TableRow></TableHeader>
              <TableBody>
                {failures.map((f, i) => (
                  <TableRow key={f.id ?? f.job_id ?? i}>
                    <TableCell className="text-xs whitespace-nowrap">{formatDateTime(f.finished_at || f.failed_at || f.at || f.created_at)}</TableCell>
                    <TableCell className="text-sm whitespace-nowrap">{f.supplier_name || '—'}</TableCell>
                    <TableCell className="font-mono text-xs">{jobTarget(f) || '—'}</TableCell>
                    <TableCell className="text-xs">{ERROR_KIND_LABELS[f.error_kind] || f.error_kind || '—'}</TableCell>
                    <TableCell className="text-xs max-w-[360px] break-words">{f.error || f.last_error || f.message || '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <RunsHistory suppliers={suppliers} />


      <ConfirmDialog
        open={confirmRun}
        onOpenChange={setConfirmRun}
        title="Correr a recolha agendada agora?"
        description="Enfileira a recolha de todas as medidas monitorizadas (todas as categorias) em todos os fornecedores activos. Pode demorar horas e ocupar os workers; para uma só categoria use Medidas monitorizadas."
        confirmLabel="Correr agora"
        onConfirm={runScheduledNow}
      />
    </div>
  );
};

export default Operacao;
