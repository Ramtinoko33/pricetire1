import React, { useState, useEffect, useRef } from 'react';
import { jobsAPI } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { Upload as UploadIcon, FileSpreadsheet, Loader2, Scale, Download, TrendingDown, CheckCircle, ArrowRight, RefreshCw, Clock, CheckCircle2, XCircle, AlertCircle, RotateCw } from 'lucide-react';
import { toast } from 'sonner';

const Comparar = () => {
  // State
  const [step, setStep] = useState(1); // 1: upload, 2: compare, 3: results
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [comparing, setComparing] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [job, setJob] = useState(null);
  const [results, setResults] = useState([]);
  const [stats, setStats] = useState(null);
  const [suppliersStatus, setSuppliersStatus] = useState([]);
  const [indiceObrigatorio, setIndiceObrigatorio] = useState(false);
  const [sortOrder, setSortOrder] = useState('economia_desc');
  const [originalOrder, setOriginalOrder] = useState([]);
  const pollingTimerRef = useRef(null);

  // Limpar timer ao desmontar componente
  useEffect(() => {
    return () => {
      if (pollingTimerRef.current) {
        clearTimeout(pollingTimerRef.current);
        pollingTimerRef.current = null;
      }
    };
  }, []);

  // Load job results if we have a job
  useEffect(() => {
    if (job?.id && step === 3) {
      loadResults();
    }
  }, [job?.id, step]);

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      if (!selectedFile.name.endsWith('.xlsx') && !selectedFile.name.endsWith('.xls')) {
        toast.error('Por favor, selecione um ficheiro Excel (.xlsx ou .xls)');
        return;
      }
      setFile(selectedFile);
      toast.success(`Ficheiro selecionado: ${selectedFile.name}`);
    }
  };

  const handleUpload = async () => {
    if (!file) {
      toast.error('Por favor, selecione um ficheiro');
      return;
    }

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);

      const { data } = await jobsAPI.upload(formData);
      setJob(data);
      setStep(2);
      toast.success(`Ficheiro carregado com ${data.total_items} itens!`);
    } catch (error) {
      console.error('Upload error:', error);
      toast.error(error.response?.data?.detail || 'Erro ao fazer upload');
    } finally {
      setUploading(false);
    }
  };

  const handleCompare = async (force = false) => {
    if (!job?.id) return;

    setComparing(true);
    try {
      // Iniciar compare (retorna imediatamente com status='running')
      const { data } = force
        ? await jobsAPI.forceCompare(job.id)
        : await jobsAPI.compare(job.id);

      if (data?.async) {
        // Backend a processar em background — fazer polling até terminar
        toast.info('A pesquisar preços nos fornecedores... pode demorar alguns minutos.');
        await _pollUntilDone(job.id);
      } else {
        // Resposta síncrona (compatibilidade)
        setStats({
          total: data.items_processed,
          found: data.items_with_savings,
          savings: data.total_savings,
        });
        setStep(3);
        toast.success(`Comparação concluída! ${data.items_with_savings} itens com preço melhor.`);
        await loadResults();
      }
    } catch (error) {
      console.error('Compare error:', error);
      toast.error(error.response?.data?.detail || 'Erro ao comparar preços');
      setComparing(false);
    }
  };

  const _pollUntilDone = (jobId) => {
    const INTERVAL_MS = 2500;
    const MAX_WAIT_MS = 60 * 60 * 1000;
    const started = Date.now();

    if (pollingTimerRef.current) {
      clearTimeout(pollingTimerRef.current);
      pollingTimerRef.current = null;
    }

    return new Promise((resolve) => {
      const tick = async () => {
        try {
          const { data: progress } = await jobsAPI.getProgress(jobId);
          const status = progress?.status;

          if (progress?.suppliers_status?.length) {
            setSuppliersStatus(progress.suppliers_status);
          }

          if (status === 'completed') {
            pollingTimerRef.current = null;
            await loadResults();
            setStep(3);
            const found = progress.found_items ?? 0;
            toast.success(`Comparação concluída! ${found} itens com preço melhor.`);
            setComparing(false);
            resolve();
            return;
          } else if (status === 'failed') {
            pollingTimerRef.current = null;
            toast.error('Erro na comparação de preços. Tente novamente.');
            setComparing(false);
            resolve();
            return;
          } else if (Date.now() - started > MAX_WAIT_MS) {
            pollingTimerRef.current = null;
            toast.error('Timeout: a comparação demorou demasiado. Tente novamente.');
            setComparing(false);
            resolve();
            return;
          }
          pollingTimerRef.current = setTimeout(tick, INTERVAL_MS);
        } catch (err) {
          console.error('Polling error:', err);
          pollingTimerRef.current = setTimeout(tick, INTERVAL_MS);
        }
      };

      pollingTimerRef.current = setTimeout(tick, INTERVAL_MS);
    });
  };

  const loadResults = async () => {
    try {
      const { data } = await jobsAPI.getResults(job.id);
      // Sort by economia_euro descending
      setOriginalOrder(data.map((_, i) => i));
      const sorted = [...data].sort((a, b) => (b.economia_euro || 0) - (a.economia_euro || 0));
      setResults(data);
      
      // Calculate stats if not set
      if (!stats) {
        const withSavings = sorted.filter(r => r.economia_euro && r.economia_euro > 0);
        const totalSavings = withSavings.reduce((acc, r) => acc + (r.economia_euro || 0), 0);
        setStats({
          total: sorted.length,
          found: withSavings.length,
          savings: totalSavings
        });
      }
    } catch (error) {
      console.error('Error loading results:', error);
    }
  };

  const handleExport = async () => {
    if (!job?.id) return;

    setExporting(true);
    try {
      const response = await jobsAPI.export(job.id);
      const blob = new Blob([response.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `comparacao_precos_${job.id.substring(0, 8)}.xlsx`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      a.remove();
      toast.success('Excel exportado com sucesso!');
    } catch (error) {
      console.error('Export error:', error);
      toast.error('Erro ao exportar Excel');
    } finally {
      setExporting(false);
    }
  };

  const resetFlow = () => {
    if (pollingTimerRef.current) {
      clearTimeout(pollingTimerRef.current);
      pollingTimerRef.current = null;
    }
    setStep(1);
    setFile(null);
    setJob(null);
    setResults([]);
    setStats(null);
    setSuppliersStatus([]);
    setComparing(false);
  };

  const statusMeta = {
    waiting: { icon: <Clock size={14} />,         label: 'A aguardar', cls: 'text-muted-foreground' },
    running: { icon: <RotateCw size={14} className="animate-spin" />, label: 'A correr', cls: 'text-blue-600' },
    done:    { icon: <CheckCircle2 size={14} />,  label: 'Concluído',  cls: 'text-emerald-600' },
    error:   { icon: <XCircle size={14} />,       label: 'Erro',       cls: 'text-red-600' },
    timeout: { icon: <AlertCircle size={14} />,   label: 'Timeout',    cls: 'text-orange-500' },
  };

  const SupplierStatusTable = () => (
    <div className="mt-4 rounded-lg border border-border overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-muted text-muted-foreground text-xs uppercase">
          <tr>
            <th className="px-4 py-2 text-left">Fornecedor</th>
            <th className="px-4 py-2 text-left">Estado</th>
            <th className="px-4 py-2 text-right">Tempo</th>
            <th className="px-4 py-2 text-right">Produtos</th>
            <th className="px-4 py-2 text-right">Melhor Preço</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {suppliersStatus.map((s) => {
            const m = statusMeta[s.status] || statusMeta.waiting;
            return (
              <tr key={s.name} className="bg-card hover:bg-muted/50">
                <td className="px-4 py-2 font-medium text-foreground">{s.name}</td>
                <td className={`px-4 py-2 ${m.cls}`}><span className="flex items-center gap-1">{m.icon} {m.label}</span></td>
                <td className="px-4 py-2 text-right text-muted-foreground">
                  {s.duration_s != null ? `${s.duration_s}s` : '-'}
                </td>
                <td className="px-4 py-2 text-right text-muted-foreground">
                  {s.products != null ? s.products : '-'}
                </td>
                <td className="px-4 py-2 text-right font-medium text-foreground">
                  {s.best_price != null ? `€${s.best_price.toFixed(2)}` : '-'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );

  const getSortedResults = (list) => {
    switch(sortOrder) {
      case 'economia_desc':
        return [...list].sort((a, b) => (b.economia_euro || -99999) - (a.economia_euro || -99999));
      case 'economia_asc':
        return [...list].sort((a, b) => (a.economia_euro || 99999) - (b.economia_euro || 99999));
      case 'original':
        return list;
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
    <div className="space-y-6" data-testid="comparar-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        {step > 1 && (
          <Button variant="outline" onClick={resetFlow}>
            Nova Comparação
          </Button>
        )}
      </div>

      {/* Progress Steps */}
      <div className="flex items-center justify-center gap-4 py-4">
        <div className={`flex items-center gap-2 ${step >= 1 ? 'text-emerald-600 dark:text-emerald-400' : 'text-muted-foreground'}`}>
          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold ring-2 ${step >= 1 ? 'ring-emerald-500 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'ring-border bg-muted text-muted-foreground'}`}>
            {step > 1 ? <CheckCircle className="w-5 h-5" /> : '1'}
          </div>
          <span className="font-medium">Upload</span>
        </div>
        <ArrowRight className="w-4 h-4 text-muted-foreground" />
        <div className={`flex items-center gap-2 ${step >= 2 ? 'text-emerald-600 dark:text-emerald-400' : 'text-muted-foreground'}`}>
          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold ring-2 ${step >= 2 ? 'ring-emerald-500 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'ring-border bg-muted text-muted-foreground'}`}>
            {step > 2 ? <CheckCircle className="w-5 h-5" /> : '2'}
          </div>
          <span className="font-medium">Comparar</span>
        </div>
        <ArrowRight className="w-4 h-4 text-muted-foreground" />
        <div className={`flex items-center gap-2 ${step >= 3 ? 'text-emerald-600 dark:text-emerald-400' : 'text-muted-foreground'}`}>
          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-semibold ring-2 ${step >= 3 ? 'ring-emerald-500 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' : 'ring-border bg-muted text-muted-foreground'}`}>
            {step === 3 ? <CheckCircle className="w-5 h-5" /> : '3'}
          </div>
          <span className="font-medium">Resultados</span>
        </div>
      </div>

      {/* Step 1: Upload */}
      {step === 1 && (
        <Card className="border-border max-w-2xl mx-auto">
          <CardHeader>
            <CardTitle>Passo 1: Carregar Ficheiro Excel</CardTitle>
            <p className="text-sm text-muted-foreground mt-2">
              Colunas esperadas: Medida | Marca | Modelo | Indice | MeuPreço
            </p>
          </CardHeader>
          <CardContent className="space-y-6">
            <div>
              <div className="border-2 border-dashed border-border rounded-lg p-8 text-center hover:border-emerald-400 transition-colors">
                <input
                  id="file-upload"
                  type="file"
                  accept=".xlsx,.xls"
                  onChange={handleFileChange}
                  className="hidden"
                  data-testid="file-input"
                />
                <label htmlFor="file-upload" className="cursor-pointer">
                  {file ? (
                    <div className="flex items-center justify-center gap-3">
                      <FileSpreadsheet className="text-emerald-600" size={40} />
                      <div className="text-left">
                        <p className="font-medium text-foreground">{file.name}</p>
                        <p className="text-sm text-muted-foreground">{(file.size / 1024).toFixed(2)} KB</p>
                      </div>
                    </div>
                  ) : (
                    <div>
                      <UploadIcon className="mx-auto text-muted-foreground mb-3" size={48} />
                      <p className="text-muted-foreground">Clique para selecionar ou arraste o ficheiro</p>
                      <p className="text-xs text-muted-foreground mt-1">Apenas .xlsx ou .xls</p>
                    </div>
                  )}
                </label>
              </div>
            </div>

            <Button
              onClick={handleUpload}
              disabled={!file || uploading}
              className="w-full bg-emerald-600 hover:bg-emerald-700"
              size="lg"
              data-testid="upload-btn"
            >
              {uploading ? (
                <>
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  A carregar...
                </>
              ) : (
                <>
                  <UploadIcon className="mr-2 h-5 w-5" />
                  Carregar Ficheiro
                </>
              )}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Step 2: Compare */}
      {step === 2 && job && (
        <Card className="border-border max-w-2xl mx-auto">
          <CardHeader>
            <CardTitle>Passo 2: Comparar com Preços Scraped</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-lg">
              <div className="flex items-center gap-3">
                <CheckCircle className="text-emerald-600 w-6 h-6" />
                <div>
                  <p className="font-medium text-emerald-700 dark:text-emerald-300">Ficheiro carregado com sucesso!</p>
                  <p className="text-sm text-emerald-600">{job.total_items} itens encontrados</p>
                </div>
              </div>
            </div>

            <div className="text-center py-4">
              <p className="text-muted-foreground mb-4">
                Clique no botão abaixo para comparar os seus preços com os preços dos fornecedores.
              </p>
              <p className="text-sm text-muted-foreground">
                Na primeira execução, o scraper vai pesquisar preços em tempo real (pode demorar 2–5 minutos).
                Execuções seguintes serão instantâneas.
              </p>
            </div>

            <Button
              onClick={handleCompare}
              disabled={comparing}
              className="w-full bg-blue-600 hover:bg-blue-700"
              size="lg"
              data-testid="compare-btn"
            >
              {comparing ? (
                <>
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  A pesquisar preços nos fornecedores... (pode demorar alguns minutos)
                </>
              ) : (
                <>
                  <Scale className="mr-2 h-5 w-5" />
                  Comparar Preços
                </>
              )}
            </Button>

            {suppliersStatus.length > 0 && <SupplierStatusTable />}
          </CardContent>
        </Card>
      )}

      {/* Step 3: Results */}
      {step === 3 && (
        <>
          {/* Stats Card */}
          {stats && (
            <Card className="bg-emerald-500/10 border-emerald-500/30">
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-8">
                    <div>
                      <p className="text-sm text-muted-foreground">Total de Itens</p>
                      <p className="text-3xl font-bold text-foreground">{stats.total}</p>
                    </div>
                    <div className="h-16 w-px bg-border"></div>
                    <div>
                      <p className="text-sm text-muted-foreground">Com Preço Melhor</p>
                      <p className="text-3xl font-bold text-emerald-600">{stats.found}</p>
                    </div>
                    <div className="h-16 w-px bg-border"></div>
                    <div>
                      <p className="text-sm text-muted-foreground">Poupança Total</p>
                      <p className="text-3xl font-bold text-emerald-600">€{stats.savings?.toFixed(2)}</p>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      onClick={() => handleCompare(true)}
                      disabled={comparing}
                      title="Apaga dados em cache e raspa tudo de novo"
                    >
                      {comparing ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : (
                        <RefreshCw className="mr-2 h-4 w-4" />
                      )}
                      Actualizar dados
                    </Button>
                    <Button onClick={handleExport} disabled={exporting} data-testid="export-btn">
                      {exporting ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : (
                        <Download className="mr-2 h-4 w-4" />
                      )}
                      Exportar Excel
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Supplier Status Summary */}
          {suppliersStatus.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Estado dos Fornecedores</CardTitle>
              </CardHeader>
              <CardContent className="pt-0">
                <SupplierStatusTable />
              </CardContent>
            </Card>
          )}

          {/* Results Table */}
          <Card>
            <CardHeader>
              <CardTitle>Resultados da Comparação</CardTitle>
            </CardHeader>
            <CardContent>
              {/* Toggle índice obrigatório */}
              <div className="flex items-center gap-2 mb-3">
                <span className="text-sm text-muted-foreground">Índice obrigatório</span>
                <button
                  onClick={() => setIndiceObrigatorio(!indiceObrigatorio)}
                  className="text-xs px-3 py-1 rounded-full font-semibold cursor-pointer border-0"
                  style={{
                    background: indiceObrigatorio ? '#10B981' : '#3F3F46',
                    color: indiceObrigatorio ? 'white' : '#D4D4D8',
                  }}
                >
                  {indiceObrigatorio ? '✓ Activo' : '✗ Inactivo'}
                </button>
                <span className="text-xs text-muted-foreground">
                  {indiceObrigatorio ? 'Só mostra resultados com índice igual ao Excel' : 'Mostra todos os resultados'}
                  <select
                    value={sortOrder}
                    onChange={e => setSortOrder(e.target.value)}
                    className="ml-4 text-xs border border-border rounded px-2 py-0.5 bg-background text-foreground"
                  >
                    <option value="economia_desc">↓ Maior economia</option>
                    <option value="economia_asc">↑ Menor economia</option>
                    <option value="original">Ordem original</option>
                    <option value="medida_asc">Medida (menor → maior)</option>
                  </select>
                </span>
              </div>

              <div className="max-h-[500px] overflow-auto">
                <Table>
                  <TableHeader className="sticky top-0 bg-card">
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
                      
                      // Define badge styles based on match type
                      const getMatchBadge = () => {
                        switch(matchType) {
                          case 'modelo_exato':
                            return <Badge variant="outline" className="text-xs bg-green-500/15 text-green-700 dark:text-green-400 border-green-500/30">modelo exato</Badge>;
                          case 'modelo_sem_indice':
                            return <Badge variant="outline" className="text-xs bg-yellow-500/15 text-yellow-700 dark:text-yellow-400 border-yellow-500/30">sem índice</Badge>;
                          case 'modelo_parcial':
                            return <Badge variant="outline" className="text-xs bg-emerald-500/15 text-emerald-700 dark:text-emerald-400 border-emerald-500/30">modelo parcial</Badge>;
                          case 'marca':
                            return <Badge variant="outline" className="text-xs bg-blue-500/15 text-blue-700 dark:text-blue-400 border-blue-500/30">marca</Badge>;
                          case 'marca_parcial':
                            return <Badge variant="outline" className="text-xs bg-sky-500/15 text-sky-700 dark:text-sky-400 border-sky-500/30">marca parcial</Badge>;
                          case 'medida':
                            return <Badge variant="outline" className="text-xs bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30">só medida</Badge>;
                          case 'sem_dados':
                            return <Badge variant="outline" className="text-xs bg-red-500/15 text-red-700 dark:text-red-400 border-red-500/30">sem dados</Badge>;
                          default:
                            return null;
                        }
                      };
                      
                      return (
                        <TableRow
                          key={item.id || index}
                          className={hasSavings ? 'bg-emerald-500/10 hover:bg-emerald-500/20' : isOtherBrand ? 'bg-amber-500/10' : ''}
                          data-testid={`result-row-${index}`}
                        >
                          <TableCell className="font-mono">{item.medida}</TableCell>
                          <TableCell>
                            <div className="flex items-center gap-2">
                              <span>{item.marca}</span>
                              {getMatchBadge()}
                            </div>
                          </TableCell>
                          <TableCell className="max-w-[120px] truncate text-muted-foreground" title={item.modelo}>
                            {item.modelo || '-'}
                          </TableCell>
                          <TableCell className="font-mono text-muted-foreground">
                            {item.indice || '-'}
                          </TableCell>
                          <TableCell className="max-w-[150px] truncate font-medium" title={item.modelo_encontrado}>
                            {item.modelo_encontrado || '-'}
                          </TableCell>
                          <TableCell className="font-mono text-muted-foreground text-xs">
                            {item.indice_encontrado || '-'}
                          </TableCell>
                          <TableCell className="text-right font-medium">
                            {item.meu_preco ? `€${item.meu_preco.toFixed(2)}` : '-'}
                          </TableCell>
                          <TableCell className="text-right font-medium">
                            {item.melhor_preco ? (
                              <div className="flex flex-col items-end">
                                <span className={hasSavings ? 'text-emerald-600' : isOtherBrand ? 'text-amber-700' : ''}>
                                  €{item.melhor_preco.toFixed(2)}
                                </span>
                                {isOtherBrand && item.melhor_marca && (
                                  <span className="text-xs text-amber-500 font-normal">
                                    ({item.melhor_marca})
                                  </span>
                                )}
                              </div>
                            ) : '-'}
                          </TableCell>
                          <TableCell>
                            {item.melhor_fornecedor ? (
                              <Badge variant="outline">{item.melhor_fornecedor}</Badge>
                            ) : '-'}
                          </TableCell>
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
                              <span className="text-emerald-600 font-bold">
                                {item.economia_percent.toFixed(1)}%
                              </span>
                            ) : '-'}
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>

                </Table>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
};

export default Comparar;
