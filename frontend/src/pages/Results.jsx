import React, { useEffect, useState } from 'react';
import { jobsAPI } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { Download, TrendingDown, Trash2, Loader2, RotateCcw } from 'lucide-react';
import { toast } from 'sonner';

const Results = () => {
  const [jobs, setJobs] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingResults, setLoadingResults] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [indiceObrigatorio, setIndiceObrigatorio] = useState(false);
  const [sortOrder, setSortOrder] = useState('original');
  const [originalResults, setOriginalResults] = useState([]);

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
      setOriginalResults(data);
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

  const handleCompare = async (jobId, force = false) => {
    setComparing(true);
    try {
      const { data } = force ? await jobsAPI.forceCompare(jobId) : await jobsAPI.compare(jobId);
      toast.success(`Comparação concluída! ${data.items_with_savings} itens com economia. Total: €${(data.total_savings ?? 0).toFixed(2)}`);
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
    return <div className="text-center py-12" data-testid="loading">A carregar...</div>;
  }

  const currentJob = jobs.find(j => j.id === selectedJob);

  const getSortedResults = (list) => {
    switch(sortOrder) {
      case 'economia_desc':
        return [...list].sort((a, b) => (b.economia_euro || -99999) - (a.economia_euro || -99999));
      case 'economia_asc':
        return [...list].sort((a, b) => (a.economia_euro || 99999) - (b.economia_euro || 99999));
      case 'original':
        return originalResults.filter(r => list.includes(r));
      case 'medida_asc':
        return [...list].sort((a, b) => {
          const ma = (a.medida || '').replace(/\D/g, '');
          const mb = (b.medida || '').replace(/\D/g, '');
          return parseInt(ma) - parseInt(mb);
        });
      default:
        return list;
    }
  };

  return (
    <div className="space-y-6" data-testid="results-page">
      <div className="flex justify-between items-center">
        <div>
          <h2 className="text-2xl font-bold" style={{ fontFamily: 'Chivo, sans-serif' }}>Resultados</h2>
          <p className="text-sm text-muted-foreground mt-1">{jobs.length} jobs encontrados</p>
        </div>
        <div className="flex gap-2">
          {selectedJob && (
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
          {selectedJob && currentJob?.status === 'completed' && (
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
                  selectedJob === job.id
                    ? 'border-primary bg-muted'
                    : 'border-border hover:border-muted-foreground'
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
                      <p className="text-xs text-muted-foreground mt-1">
                        {new Date(job.created_at).toLocaleString('pt-PT')} • {job.total_items} itens
                      </p>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="text-right">
                        <p className="text-sm font-mono font-bold text-green-700">
                          €{job.total_savings?.toFixed(2) || '0.00'}
                        </p>
                        <p className="text-xs text-muted-foreground">economia</p>
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
        <Card className="border-border">
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
              <div className="text-center py-12 text-muted-foreground">A carregar resultados...</div>
            ) : results.length === 0 ? (
              <div className="text-center py-12 text-muted-foreground">Nenhum resultado disponível</div>
            ) : (
              <div className="max-h-[600px] overflow-auto">
                <Table>
                  <TableHeader className="sticky top-0 bg-card">
                    <TableRow>
                      <TableHead>Ref</TableHead>
                      <TableHead colSpan={11}>
                        <div className="flex items-center gap-2 py-1">
                          <span className="text-xs text-muted-foreground">Índice obrigatório</span>
                          <button
                            onClick={() => setIndiceObrigatorio(!indiceObrigatorio)}
                            className="text-xs px-2 py-0.5 rounded-full border"
                            style={{
                              background: indiceObrigatorio ? '#10B981' : '#D1D5DB',
                              color: indiceObrigatorio ? 'white' : '#374151',
                              borderColor: indiceObrigatorio ? '#10B981' : '#D1D5DB',
                            }}
                          >
                            {indiceObrigatorio ? '✓ Activo' : '✗ Inactivo'}
                          </button>
                          <span className="text-xs text-slate-400">
                            {indiceObrigatorio ? 'Só mostra resultados com índice igual ao Excel' : 'Mostra todos os resultados'}
                            <select
                          value={sortOrder}
                          onChange={e => setSortOrder(e.target.value)}
                          className="ml-4 text-xs border border-border rounded px-2 py-0.5 bg-background text-foreground"
                        >
                          <option value="original">Ordem original</option>
                          <option value="economia_desc">↓ Maior economia</option>
                          <option value="economia_asc">↑ Menor economia</option>
                          <option value="medida_asc">Medida (menor → maior)</option>
                        </select>
                          </span>
                        </div>
                      </TableHead>
                    </TableRow>
                    <TableRow>
                      <TableHead>Medida</TableHead>
                      <TableHead>Marca</TableHead>
                      <TableHead>Modelo</TableHead>
                      <TableHead>Índice</TableHead>
                      <TableHead>Modelo Encontrado</TableHead>
                      <TableHead>Índice Encontrado</TableHead>
                      <TableHead className="text-right">Meu Preço</TableHead>
                      <TableHead className="text-right">Melhor Preço</TableHead>
                      <TableHead>Fornecedor</TableHead>
                      <TableHead className="text-right">Economia €</TableHead>
                      <TableHead className="text-right">Economia %</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                  {getSortedResults(indiceObrigatorio ? results.filter(r => r.match_type === 'modelo_exato') : results).map((item, index) => {
                      const hasSavings = item.status === 'found' && item.economia_euro && item.economia_euro > 0;
                      const isOtherBrand = item.status === 'no_brand_match';
                      const matchType = item.match_type;

                      const getMatchBadge = () => {
                        switch(matchType) {
                          case 'modelo_exato': return <Badge variant="outline" className="text-xs bg-green-500/15 text-green-700 dark:text-green-400 border-green-500/30">modelo exato</Badge>;
                          case 'modelo_sem_indice': return <Badge variant="outline" className="text-xs bg-yellow-500/15 text-yellow-700 dark:text-yellow-400 border-yellow-500/30">sem índice</Badge>;
                          case 'modelo_parcial': return <Badge variant="outline" className="text-xs bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30">modelo parcial</Badge>;
                          case 'marca': return <Badge variant="outline" className="text-xs bg-blue-500/15 text-blue-700 dark:text-blue-400 border-blue-500/30">marca</Badge>;
                          case 'marca_parcial': return <Badge variant="outline" className="text-xs bg-sky-500/15 text-sky-700 dark:text-sky-400 border-sky-500/30">marca parcial</Badge>;
                          case 'medida': return <Badge variant="outline" className="text-xs bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30">só medida</Badge>;
                          case 'sem_dados': return <Badge variant="outline" className="text-xs bg-red-500/15 text-red-700 dark:text-red-400 border-red-500/30">sem dados</Badge>;
                          default: return null;
                        }
                      };

                      return (
                        <TableRow
                          key={item.id || index}
                          className={hasSavings ? 'bg-emerald-500/10 hover:bg-emerald-500/20' : isOtherBrand ? 'bg-amber-500/10' : ''}
                        >
                          <TableCell className="font-mono text-sm">{item.ref_id}</TableCell>
                          <TableCell className="font-mono">{item.medida}</TableCell>
                          <TableCell>
                            <div className="flex items-center gap-2">
                              <span>{item.marca}</span>
                              {getMatchBadge()}
                            </div>
                          </TableCell>
                          <TableCell className="max-w-[120px] truncate text-muted-foreground" title={item.modelo}>{item.modelo || '-'}</TableCell>
                          <TableCell className="font-mono text-muted-foreground">{item.indice || '-'}</TableCell>
                          <TableCell className="max-w-[150px] truncate font-medium" title={item.modelo_encontrado}>{item.modelo_encontrado || '-'}</TableCell>
                          <TableCell className="font-mono text-muted-foreground text-xs">{item.indice_encontrado || '-'}</TableCell>
                          <TableCell className="text-right font-medium">{item.meu_preco ? `€${item.meu_preco.toFixed(2)}` : '-'}</TableCell>
                          <TableCell className="text-right font-medium">
                            {item.melhor_preco ? (
                              <div className="flex flex-col items-end">
                                <span className={hasSavings ? 'text-emerald-600' : isOtherBrand ? 'text-amber-700' : ''}>
                                  €{item.melhor_preco.toFixed(2)}
                                </span>
                                {isOtherBrand && item.melhor_marca && (
                                  <span className="text-xs text-amber-500 font-normal">({item.melhor_marca})</span>
                                )}
                              </div>
                            ) : '-'}
                          </TableCell>
                          <TableCell>{item.melhor_fornecedor ? <Badge variant="outline">{item.melhor_fornecedor}</Badge> : '-'}</TableCell>
                          <TableCell className="text-right">
                            {hasSavings ? (
                              <span className="text-emerald-600 font-bold">
                                <TrendingDown className="inline w-3 h-3 mr-1" />
                                €{item.economia_euro.toFixed(2)}
                              </span>
                            ) : isOtherBrand ? (
                              <span className="text-xs text-amber-600 italic">outra marca</span>
                            ) : '-'}
                          </TableCell>
                          <TableCell className="text-right">
                            {hasSavings ? (
                              <span className="text-emerald-600 font-bold">{item.economia_percent.toFixed(1)}%</span>
                            ) : '-'}
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
      )}
    </div>
  );
};

export default Results;
