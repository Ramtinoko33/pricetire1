import React, { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { jobsAPI } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Download, Trash2, Loader2, RotateCcw, X } from 'lucide-react';
import { toast } from 'sonner';
import ComparisonResultsTable from '../components/ComparisonResultsTable';
import { ConfirmDialog, EmptyState, TableSkeleton } from '../components/common';
import { downloadBlob } from '../lib/api';
import { errorMessage, formatDateTime, formatPrice } from '../lib/format';

const Results = () => {
  const [jobs, setJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingResults, setLoadingResults] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const pollRef = useRef(null);
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState([]);
  const [searchParams] = useSearchParams();

  useEffect(() => {
    loadJobs();
    return () => { if (pollRef.current) clearTimeout(pollRef.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadJobs = async () => {
    try {
      const { data } = await jobsAPI.getAll();
      setJobs(data);
      const jobParam = searchParams.get('job');
      if (jobParam) {
        loadJobResults(jobParam);
      } else if (data.length > 0) {
        loadJobResults(data[0].id);
      }
    } catch (error) {
      console.error('Error loading jobs:', error);
      toast.error(errorMessage(error, 'Erro ao carregar comparações'));
    } finally {
      setLoading(false);
    }
  };

  const loadJobResults = async (jobId) => {
    setSelectedJob(jobId);
    setLoadingResults(true);
    try {
      const { data } = await jobsAPI.getResults(jobId);
      setResults(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error('Error loading results:', error);
      toast.error(errorMessage(error, 'Erro ao carregar resultados'));
    } finally {
      setLoadingResults(false);
    }
  };

  const handleExport = async (jobId) => {
    try {
      const { data } = await jobsAPI.export(jobId);
      downloadBlob(data, `resultados_${String(jobId).substring(0, 8)}.xlsx`, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
      toast.success('Excel exportado');
    } catch (error) {
      toast.error(errorMessage(error, 'Erro ao exportar Excel'));
    }
  };

  const toggleSelectMode = () => {
    setSelectMode((v) => !v);
    setSelectedIds([]);
  };

  const toggleSelectId = (jobId) => {
    setSelectedIds((prev) =>
      prev.includes(jobId) ? prev.filter((id) => id !== jobId) : [...prev, jobId]
    );
  };

  const handleDeleteSelected = async () => {
    if (selectedIds.length === 0) return;
    setConfirmDelete(false);

    try {
      await Promise.all(selectedIds.map((id) => jobsAPI.delete(id)));
      toast.success(`${selectedIds.length} ${selectedIds.length === 1 ? 'tabela eliminada' : 'tabelas eliminadas'}!`);
      if (selectedIds.includes(selectedJob)) {
        setSelectedJob(null);
        setResults([]);
      }
      setSelectMode(false);
      setSelectedIds([]);
      loadJobs();
    } catch (error) {
      console.error('Error deleting jobs:', error);
      toast.error('Erro ao eliminar tabelas');
    }
  };

  const pollJob = (jobId) => {
    const started = Date.now();
    const tick = async () => {
      try {
        const { data: progress } = await jobsAPI.getProgress(jobId);
        if (progress?.status === 'completed') {
          setComparing(false);
          toast.success('Comparação concluída');
          loadJobResults(jobId);
          loadJobs();
          return;
        }
        if (progress?.status === 'failed') {
          setComparing(false);
          toast.error('A comparação falhou');
          return;
        }
      } catch {
        /* tentar de novo */
      }
      if (Date.now() - started > 60 * 60 * 1000) {
        setComparing(false);
        toast.error('A comparação excedeu 60 min');
        return;
      }
      pollRef.current = setTimeout(tick, 3000);
    };
    pollRef.current = setTimeout(tick, 3000);
  };

  const handleCompare = async (jobId, force = false) => {
    setComparing(true);
    try {
      const { data } = force ? await jobsAPI.forceCompare(jobId) : await jobsAPI.compare(jobId);
      if (data?.async) {
        toast.info('A actualizar preços nos fornecedores... pode demorar alguns minutos.');
        pollJob(jobId);
        return;
      }
      toast.success('Comparação concluída');
      loadJobResults(jobId);
      loadJobs();
      setComparing(false);
    } catch (error) {
      toast.error(errorMessage(error, 'Erro ao comparar preços'));
      setComparing(false);
    }
  };

  const getStatusBadge = (status) => {
    if (status === 'no_brand_match') {
      return <Badge variant="outline" className="text-amber-700 border-amber-400 bg-amber-50">OUTRA MARCA</Badge>;
    }
    if (status === 'no_data') {
      return <Badge variant="outline" className="text-muted-foreground">SEM DADOS</Badge>;
    }
    const variants = {
      completed: 'default',
      running: 'secondary',
      pending: 'outline',
      failed: 'destructive',
      found: 'default',
      not_found: 'secondary',
      processing: 'secondary',
      error: 'destructive',
    };
    return <Badge variant={variants[status] || 'outline'}>{status.toUpperCase()}</Badge>;
  };

  if (loading) {
    return <TableSkeleton rows={6} cols={4} />;
  }

  const currentJob = jobs.find(j => j.id === selectedJob);

  return (
    <div className="space-y-6" data-testid="results-page">
      <div className="flex flex-col md:flex-row md:justify-between md:items-center gap-3">
        <div>
          <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.16em] text-primary">Comparações por ficheiro</p>
          <h1 className="text-2xl sm:text-[28px] font-extrabold leading-tight tracking-[-0.02em]">Resultados</h1>
          <p className="text-sm text-muted-foreground mt-1">{jobs.length} comparações guardadas</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {!selectMode && jobs.length > 0 && (
            <Button
              variant="outline"
              onClick={toggleSelectMode}
              title="Selecionar tabelas para eliminar"
              data-testid="trash-mode-btn"
            >
              <Trash2 size={18} className="mr-2 text-red-600" />
              Eliminar tabelas
            </Button>
          )}
          {selectMode && (
            <>
              <Button
                onClick={() => setConfirmDelete(true)}
                disabled={selectedIds.length === 0}
                className="bg-red-600 hover:bg-red-700"
                data-testid="delete-selected-btn"
              >
                <Trash2 size={18} className="mr-2" />
                Eliminar selecionadas ({selectedIds.length})
              </Button>
              <Button variant="outline" onClick={toggleSelectMode}>
                <X size={18} className="mr-2" />
                Cancelar
              </Button>
            </>
          )}
          {!selectMode && selectedJob && (
            <>
              <Button
                variant="outline"
                onClick={() => handleCompare(selectedJob, true)}
                disabled={comparing}
                title="Apaga o cache e re-scrape para obter preços e stock actualizados"
                data-testid="force-compare-btn"
              >
                {comparing ? (
                  <Loader2 size={18} className="mr-2 animate-spin" />
                ) : (
                  <RotateCcw size={18} className="mr-2" />
                )}
                Atualizar Preços
              </Button>
            </>
          )}
          {!selectMode && selectedJob && currentJob?.status === 'completed' && (
            <Button onClick={() => handleExport(selectedJob)} data-testid="export-btn">
              <Download size={18} className="mr-2" />
              Exportar Excel
            </Button>
          )}
        </div>
      </div>

      {/* Jobs List */}
      <Card className="border-border">
        <CardHeader>
          <CardTitle>Selecionar Job</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {jobs.map((job) => (
              <div
              key={job.id}
              className={`flex items-center gap-3 p-4 border rounded-sm transition-colors ${
                selectMode && selectedIds.includes(job.id)
                  ? 'border-red-400 bg-red-50 dark:bg-red-500/10'
                  : selectedJob === job.id
                  ? 'border-primary bg-muted'
                  : 'border-border hover:border-muted-foreground'
              }`}
            >
              {selectMode && (
                <input
                  type="checkbox"
                  checked={selectedIds.includes(job.id)}
                  onChange={() => toggleSelectId(job.id)}
                  className="w-4 h-4 flex-shrink-0 accent-red-600 cursor-pointer"
                  data-testid={`select-checkbox-${job.id}`}
                />
              )}
              <button
                onClick={() => selectMode ? toggleSelectId(job.id) : loadJobResults(job.id)}
                className="flex-1 text-left"
                data-testid={`job-select-${job.id}`}
              >
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <p className="font-medium text-sm">{job.filename}</p>
                      <p className="text-xs text-muted-foreground mt-1">
                        {formatDateTime(job.created_at)} • {job.total_items} itens
                      </p>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="text-right">
                        <p className="text-sm font-mono font-bold text-green-700 dark:text-green-400">
                          {formatPrice(job.total_savings ?? 0)}
                        </p>
                        <p className="text-xs text-muted-foreground">poupança (exactos)</p>
                      </div>
                      {getStatusBadge(job.status)}
                    </div>
                  </div>
                </button>
                </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Results Table */}
      {selectedJob && (
        <Card className="border-border">
          <CardHeader>
            <div className="flex justify-between items-center">
              <CardTitle>Detalhes - {currentJob?.filename}</CardTitle>
              {currentJob?.status === 'running' && (
                <Badge variant="secondary">Processando: {currentJob.processed_items}/{currentJob.total_items}</Badge>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {loadingResults ? (
              <TableSkeleton rows={6} cols={6} />
            ) : results.length === 0 ? (
              <EmptyState title="Sem resultados" description="Esta comparação ainda não tem resultados. Use 'Atualizar Preços' para correr a comparação." />
            ) : (
              <ComparisonResultsTable results={results} showRef />
            )}
          </CardContent>
        </Card>
      )}
      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Eliminar ${selectedIds.length} ${selectedIds.length === 1 ? 'tabela' : 'tabelas'}?`}
        description="Esta acção é permanente."
        confirmLabel="Eliminar"
        destructive
        onConfirm={handleDeleteSelected}
      />
    </div>
  );
};

export default Results;
