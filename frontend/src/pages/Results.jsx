import React, { useEffect, useState } from 'react';
import { jobsAPI } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { Download, RefreshCw, TrendingDown, Trash2, Scale, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

const Results = () => {
  const [jobs, setJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingResults, setLoadingResults] = useState(false);
  const [comparing, setComparing] = useState(false);

  useEffect(() => {
    loadJobs();
  }, []);

  const loadJobs = async () => {
    try {
      const { data } = await jobsAPI.getAll();
      setJobs(data);
      if (data.length > 0) {
        loadJobResults(data[0].id);
      }
    } catch (error) {
      console.error('Error loading jobs:', error);
      toast.error('Erro ao carregar jobs');
    } finally {
      setLoading(false);
    }
  };

  const loadJobResults = async (jobId) => {
    setSelectedJob(jobId);
    setLoadingResults(true);
    try {
      const { data } = await jobsAPI.getResults(jobId);
      setResults(data);
    } catch (error) {
      console.error('Error loading results:', error);
      toast.error('Erro ao carregar resultados');
    } finally {
      setLoadingResults(false);
    }
  };

  const handleExport = async (jobId) => {
    try {
      const { data } = await jobsAPI.export(jobId);
      const url = window.URL.createObjectURL(new Blob([data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `results_${jobId.substring(0, 8)}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      toast.success('Excel exportado com sucesso!');
    } catch (error) {
      console.error('Error exporting:', error);
      toast.error('Erro ao exportar Excel');
    }
  };

  const handleDelete = async (jobId, filename) => {
    if (!window.confirm(`Tem certeza que deseja eliminar o job "${filename}"?`)) return;

    try {
      await jobsAPI.delete(jobId);
      toast.success('Job eliminado com sucesso!');
      
      // If deleted job was selected, clear selection
      if (selectedJob === jobId) {
        setSelectedJob(null);
        setResults([]);
      }
      
      // Reload jobs list
      loadJobs();
    } catch (error) {
      console.error('Error deleting job:', error);
      toast.error('Erro ao eliminar job');
    }
  };

  const handleCompare = async (jobId) => {
    setComparing(true);
    try {
      const { data } = await jobsAPI.compare(jobId);
      toast.success(`Comparação concluída! ${data.items_with_savings} itens com economia. Total: €${data.total_savings}`);
      loadJobResults(jobId);
      loadJobs();
    } catch (error) {
      console.error('Error comparing:', error);
      toast.error('Erro ao comparar preços');
    } finally {
      setComparing(false);
    }
  };

  const getStatusBadge = (status) => {
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
    return <div className="text-center py-12" data-testid="loading">A carregar...</div>;
  }

  const currentJob = jobs.find(j => j.id === selectedJob);

  return (
    <div className="space-y-6" data-testid="results-page">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold" style={{ fontFamily: 'Chivo, sans-serif' }}>Resultados</h2>
          <p className="text-sm text-slate-600 mt-1">{jobs.length} jobs encontrados</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={loadJobs} data-testid="refresh-btn">
            <RefreshCw size={18} className="mr-2" />
            Atualizar
          </Button>
          {selectedJob && (
            <Button 
              variant="outline" 
              onClick={() => handleCompare(selectedJob)} 
              disabled={comparing}
              data-testid="compare-btn"
            >
              {comparing ? (
                <Loader2 size={18} className="mr-2 animate-spin" />
              ) : (
                <Scale size={18} className="mr-2" />
              )}
              Comparar Preços
            </Button>
          )}
          {selectedJob && currentJob?.status === 'completed' && (
            <Button onClick={() => handleExport(selectedJob)} data-testid="export-btn">
              <Download size={18} className="mr-2" />
              Exportar Excel
            </Button>
          )}
        </div>
      </div>

      {/* Jobs List */}
      <Card className="border-slate-200">
        <CardHeader>
          <CardTitle>Selecionar Job</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {jobs.map((job) => (
              <div
                key={job.id}
                className={`flex items-center gap-3 p-4 border rounded-sm transition-colors ${
                  selectedJob === job.id
                    ? 'border-slate-900 bg-slate-50'
                    : 'border-slate-200 hover:border-slate-400'
                }`}
              >
                <button
                  onClick={() => loadJobResults(job.id)}
                  className="flex-1 text-left"
                  data-testid={`job-select-${job.id}`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <p className="font-medium text-sm">{job.filename}</p>
                      <p className="text-xs text-slate-500 mt-1">
                        {new Date(job.created_at).toLocaleString('pt-PT')} • {job.total_items} itens
                      </p>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="text-right">
                        <p className="text-sm font-mono font-bold text-green-700">
                          €{job.total_savings?.toFixed(2) || '0.00'}
                        </p>
                        <p className="text-xs text-slate-500">economia</p>
                      </div>
                      {getStatusBadge(job.status)}
                    </div>
                  </div>
                </button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleDelete(job.id, job.filename)}
                  data-testid={`delete-job-btn-${job.id}`}
                  className="flex-shrink-0"
                >
                  <Trash2 size={16} className="text-red-600" />
                </Button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Results Table */}
      {selectedJob && (
        <Card className="border-slate-200">
          <CardHeader>
            <div className="flex justify-between items-center">
              <CardTitle>Detalhes - {currentJob?.filename}</CardTitle>
              {currentJob?.status === 'running' && (
                <Badge variant="secondary">Processando: {currentJob.processed_items}/{currentJob.total_items}</Badge>
              )}
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {loadingResults ? (
              <div className="text-center py-12 text-slate-500">A carregar resultados...</div>
            ) : results.length === 0 ? (
              <div className="text-center py-12 text-slate-500">Nenhum resultado disponível</div>
            ) : (
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Ref</TableHead>
                      <TableHead>Medida</TableHead>
                      <TableHead>Marca</TableHead>
                      <TableHead>Modelo</TableHead>
                      <TableHead>Meu Preço</TableHead>
                      <TableHead>Melhor Preço</TableHead>
                      <TableHead>Fornecedor</TableHead>
                      <TableHead>Economia</TableHead>
                      <TableHead>Status</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {results.map((item) => (
                      <TableRow
                        key={item.id}
                        className={item.economia_euro > 0 ? 'bg-green-50' : ''}
                        data-testid={`result-row-${item.id}`}
                      >
                        <TableCell className="font-mono text-sm">{item.ref_id}</TableCell>
                        <TableCell>{item.medida}</TableCell>
                        <TableCell>{item.marca}</TableCell>
                        <TableCell className="max-w-xs truncate">{item.modelo}</TableCell>
                        <TableCell className="font-mono">€{item.meu_preco.toFixed(2)}</TableCell>
                        <TableCell className="font-mono font-bold">
                          {item.melhor_preco ? `€${item.melhor_preco.toFixed(2)}` : '-'}
                        </TableCell>
                        <TableCell>{item.melhor_fornecedor || '-'}</TableCell>
                        <TableCell>
                          {item.economia_euro > 0 ? (
                            <div className="flex items-center gap-1 text-green-700 font-bold">
                              <TrendingDown size={14} />
                              <span className="font-mono">€{item.economia_euro.toFixed(2)}</span>
                              <span className="text-xs">({item.economia_percent.toFixed(1)}%)</span>
                            </div>
                          ) : (
                            '-'
                          )}
                        </TableCell>
                        <TableCell>{getStatusBadge(item.status)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
};

export default Results;
