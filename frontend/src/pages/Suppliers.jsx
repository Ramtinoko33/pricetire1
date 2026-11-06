import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, Pencil, Plus, Power, PowerOff, TestTube } from 'lucide-react';
import { toast } from 'sonner';
import { opsAPI, suppliersAPI } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { errorMessage } from '@/lib/format';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import SupplierForm from '@/components/SupplierForm';
import { ConfirmDialog, EmptyState, ErrorState, PageHeader, TableSkeleton } from '@/components/common';
import { ERROR_KIND_LABELS, HealthBadge, HealthDetails, JOB_FINISHED, JOB_SUCCESS, JobStatusBadge, ToneBadge } from '@/components/badges';

const TEST_POLL_MS = 3000;
const TEST_TIMEOUT_MS = 5 * 60 * 1000;
const FINISHED = JOB_FINISHED;

const Suppliers = () => {
  const { isAdmin } = useAuth();
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [form, setForm] = useState({ open: false, initial: null });
  const [formLoading, setFormLoading] = useState(false);
  const [tests, setTests] = useState({});
  const [toDelete, setToDelete] = useState(null);
  const timers = useRef({});

  const load = useCallback(async () => {
    setError('');
    try {
      const { data } = await suppliersAPI.getAll();
      setSuppliers(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(errorMessage(err, 'Erro ao carregar fornecedores'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  useEffect(() => () => {
    Object.values(timers.current).forEach((t) => clearTimeout(t));
    timers.current = {};
  }, []);

  const handleSubmit = async (payload) => {
    setFormLoading(true);
    try {
      if (form.initial?.id) {
        await suppliersAPI.update(form.initial.id, payload);
        toast.success('Fornecedor actualizado');
      } else {
        await suppliersAPI.create(payload);
        toast.success('Fornecedor adicionado');
      }
      setForm({ open: false, initial: null });
      load();
    } catch (err) {
      toast.error(errorMessage(err, 'Erro ao guardar fornecedor'));
    } finally {
      setFormLoading(false);
    }
  };

  // DELETE /api/suppliers/{id} desactiva (não apaga) — reservado a admin.
  const handleDeactivate = async () => {
    const s = toDelete;
    setToDelete(null);
    try {
      if (isAdmin) await suppliersAPI.delete(s.id);
      else await suppliersAPI.update(s.id, { is_active: false });
      toast.success(`${s.name} desactivado`);
      load();
    } catch (err) {
      toast.error(errorMessage(err, 'Erro ao desactivar fornecedor'));
    }
  };

  const handleActivate = async (s) => {
    try {
      await suppliersAPI.update(s.id, { is_active: true });
      toast.success(`${s.name} activado`);
      load();
    } catch (err) {
      toast.error(errorMessage(err, 'Erro ao activar fornecedor'));
    }
  };

  const pollTest = (supplier, jobId, started) => {
    const tick = async () => {
      if (Date.now() - started > TEST_TIMEOUT_MS) {
        setTests((t) => ({ ...t, [supplier.id]: { ...t[supplier.id], status: 'timeout', error: 'Sem resposta do worker em 5 min. Veja a Operação.' } }));
        delete timers.current[supplier.id];
        return;
      }
      try {
        const { data } = await opsAPI.jobs({ supplier_id: supplier.id, type: 'test_login', limit: 1 });
        const list = Array.isArray(data) ? data : data?.jobs || [];
        const job = list.find((j) => String(j.id ?? j.job_id) === String(jobId)) || list[0];
        if (job) {
          setTests((t) => ({ ...t, [supplier.id]: { jobId, status: job.status, error: job.error || job.last_error, error_kind: job.error_kind } }));
          if (FINISHED.has(job.status)) {
            delete timers.current[supplier.id];
            if (JOB_SUCCESS.has(job.status)) toast.success(`Login OK: ${supplier.name}`);
            else toast.error(`Teste de login falhou: ${supplier.name}`);
            load();
            return;
          }
        }
      } catch {
        /* tentar de novo */
      }
      timers.current[supplier.id] = setTimeout(tick, TEST_POLL_MS);
    };
    timers.current[supplier.id] = setTimeout(tick, TEST_POLL_MS);
  };

  const handleTest = async (s) => {
    setTests((t) => ({ ...t, [s.id]: { status: 'queued' } }));
    try {
      const { data } = await suppliersAPI.testLogin(s.id);
      const jobId = data?.job_id;
      setTests((t) => ({ ...t, [s.id]: { jobId, status: data?.status || 'queued' } }));
      toast.info(data?.deduplicated ? `Já havia um teste em curso para ${s.name}; a acompanhar.` : `Teste de login enfileirado para ${s.name}`);
      if (jobId !== undefined && jobId !== null) pollTest(s, jobId, Date.now());
    } catch (err) {
      setTests((t) => ({ ...t, [s.id]: { status: 'failed', error: errorMessage(err, 'Erro ao pedir teste') } }));
      toast.error(errorMessage(err, 'Erro ao pedir teste de login'));
    }
  };

  const testRunning = (id) => tests[id] && !FINISHED.has(tests[id].status);

  return (
    <div className="space-y-6" data-testid="suppliers-page">
      <PageHeader
        title="Fornecedores"
        description={`${suppliers.length} fornecedores · estado de saúde das recolhas e credenciais`}
        actions={(
          <Button onClick={() => setForm({ open: true, initial: null })} data-testid="add-supplier-btn">
            <Plus size={18} className="mr-2" /> Adicionar fornecedor
          </Button>
        )}
      />

      {error && <ErrorState message={error} onRetry={load} />}

      <Card>
        <CardContent className="p-0">
          {loading ? <TableSkeleton rows={6} cols={5} /> : suppliers.length === 0 ? (
            <EmptyState title="Sem fornecedores" description="Adicione um fornecedor e escolha o conector correspondente." />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>Saúde</TableHead>
                  <TableHead>Detalhe</TableHead>
                  <TableHead>Conector</TableHead>
                  <TableHead>Credenciais</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="text-right">Acções</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {suppliers.map((s) => {
                  const test = tests[s.id];
                  return (
                    <TableRow key={s.id} data-testid={`supplier-row-${s.id}`} className={s.is_active === false ? 'opacity-70' : undefined}>
                      <TableCell className="font-medium whitespace-nowrap">
                        {s.name}
                        {s.url_login && <div className="text-xs text-muted-foreground truncate max-w-[200px]" title={s.url_login}>{s.url_login}</div>}
                      </TableCell>
                      <TableCell><HealthBadge health={s.health} /></TableCell>
                      <TableCell>
                        <HealthDetails health={s.health} />
                        {test && (
                          <div className="mt-1 flex flex-wrap items-center gap-1 text-xs">
                            <span>Teste{test.jobId != null ? ` #${test.jobId}` : ''}:</span>
                            <JobStatusBadge status={test.status} />
                            {test.error && <span className="text-red-600 dark:text-red-400">{ERROR_KIND_LABELS[test.error_kind] ? `${ERROR_KIND_LABELS[test.error_kind]}: ` : ''}{test.error}</span>}
                          </div>
                        )}
                      </TableCell>
                      <TableCell className="font-mono text-xs">{s.adapter_key || <span className="text-red-600">sem conector</span>}</TableCell>
                      <TableCell className="text-xs">
                        <div className="font-mono">{s.username || '—'}</div>
                        {s.has_password ? <ToneBadge tone="green">Password guardada</ToneBadge> : <ToneBadge tone="amber">Sem password</ToneBadge>}
                      </TableCell>
                      <TableCell>{s.is_active ? <ToneBadge tone="green">Activo</ToneBadge> : <ToneBadge>Inactivo</ToneBadge>}</TableCell>
                      <TableCell>
                        <div className="flex items-center justify-end gap-1">
                          <Button variant="outline" size="sm" onClick={() => setForm({ open: true, initial: s })} title="Editar" aria-label="Editar" data-testid={`edit-btn-${s.id}`}>
                            <Pencil size={14} />
                          </Button>
                          <Button variant="outline" size="sm" onClick={() => handleTest(s)} disabled={testRunning(s.id)} title="Testar login" aria-label="Testar login" data-testid={`test-login-btn-${s.id}`}>
                            {testRunning(s.id) ? <Loader2 size={14} className="animate-spin" /> : <TestTube size={14} />}
                          </Button>
                          {s.is_active ? (
                            <Button variant="outline" size="sm" onClick={() => setToDelete(s)} title="Desactivar" data-testid={`deactivate-btn-${s.id}`}>
                              <PowerOff size={14} className="text-red-600 sm:mr-1" /> <span className="hidden sm:inline">Desactivar</span>
                            </Button>
                          ) : (
                            <Button variant="outline" size="sm" onClick={() => handleActivate(s)} title="Activar" data-testid={`activate-btn-${s.id}`}>
                              <Power size={14} className="text-green-600 sm:mr-1" /> <span className="hidden sm:inline">Activar</span>
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <SupplierForm
        open={form.open}
        initialData={form.initial}
        onClose={() => setForm({ open: false, initial: null })}
        onSubmit={handleSubmit}
        isLoading={formLoading}
      />
      <ConfirmDialog
        open={Boolean(toDelete)}
        onOpenChange={(v) => !v && setToDelete(null)}
        title={`Desactivar ${toDelete?.name || ''}?`}
        description="O fornecedor deixa de entrar nas recolhas. As ofertas e o histórico mantêm-se e pode voltar a activá-lo a qualquer momento."
        confirmLabel="Desactivar"
        destructive
        onConfirm={handleDeactivate}
      />
    </div>
  );
};

export default Suppliers;
