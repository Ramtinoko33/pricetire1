import React, { useState, useEffect, useRef } from 'react';
import { jobsAPI } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Upload as UploadIcon, FileSpreadsheet, Loader2, Scale, Download, CheckCircle, ArrowRight, RefreshCw, Clock, CheckCircle2, XCircle, AlertCircle, RotateCw, Save } from 'lucide-react';
import { toast } from 'sonner';
import ComparisonResultsTable, { summarizeResults } from '../components/ComparisonResultsTable';
import { errorMessage, formatPrice } from '../lib/format';
import { ERROR_KIND_LABELS } from '../components/badges';

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
  const pollingTimerRef = useRef(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  // (bloqueio de navegação entre abas removido — usa-se apenas o aviso beforeunload)

  // Limpar timer ao desmontar componente
  useEffect(() => {
    return () => {
      if (pollingTimerRef.current) {
        clearTimeout(pollingTimerRef.current);
        pollingTimerRef.current = null;
      }
    };
  }, []);

  // Ao montar: se havia uma comparação em curso (guardada em sessionStorage),
  // retomar — re-ligar ao job e continuar a mostrar o progresso. Isto resolve
  // o caso de sair da aba e voltar enquanto o scraper ainda corre.
  useEffect(() => {
    const savedJobId = sessionStorage.getItem('comparing_job_id');
    if (!savedJobId) return;
    (async () => {
      try {
        const { data: progress } = await jobsAPI.getProgress(savedJobId);
        if (progress?.status === 'running') {
          // Ainda a correr — retomar o ecrã de comparação e o polling
          setJob({ id: savedJobId, total_items: progress.total_items });
          setStep(2);
          setComparing(true);
          if (progress?.suppliers_status?.length) {
            setSuppliersStatus(progress.suppliers_status);
          }
          await _pollUntilDone(savedJobId);
        } else {
          // Já terminou enquanto estavas fora — limpar marca
          sessionStorage.removeItem('comparing_job_id');
        }
      } catch (e) {
        sessionStorage.removeItem('comparing_job_id');
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Aviso nativo do browser ao fechar/recarregar a janela com tabela por guardar
  useEffect(() => {
    const handleBeforeUnload = (e) => {
      if (step === 3 && job?.id && !saved) {
        e.preventDefault();
        e.returnValue = '';
        return '';
      }
    };
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [step, job?.id, saved]);

  // Load job results if we have a job
  useEffect(() => {
    if (job?.id && step === 3) {
      loadResults();
    }
  }, [job?.id, step]);

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (selectedFile) {
      if (!/\.(xlsx|xls|csv)$/i.test(selectedFile.name)) {
        toast.error('Por favor, selecione um ficheiro Excel ou CSV (.xlsx, .xls ou .csv)');
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
      if (data?.error_message) toast.warning(data.error_message);
    } catch (error) {
      console.error('Upload error:', error);
      toast.error(errorMessage(error, 'Erro ao fazer upload'));
    } finally {
      setUploading(false);
    }
  };

  const handleCompare = async (force = false) => {
    if (!job?.id) return;

    setComparing(true);
    sessionStorage.setItem('comparing_job_id', job.id);
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
        setStep(3);
        toast.success('Comparação concluída!');
        await loadResults();
      }
    } catch (error) {
      console.error('Compare error:', error);
      toast.error(errorMessage(error, 'Erro ao comparar preços'));
      setComparing(false);
    }
  };

  const handleCancel = async () => {
    const jobId = job?.id;
    if (!jobId) return;
    try {
      await jobsAPI.cancel(jobId);
      toast.info('A cancelar comparação...');
      // O polling vai detectar status='failed' e parar; limpamos o estado.
      if (pollingTimerRef.current) {
        clearTimeout(pollingTimerRef.current);
        pollingTimerRef.current = null;
      }
      sessionStorage.removeItem('comparing_job_id');
      setComparing(false);
      setStep(1);
      setFile(null);
      setJob(null);
      setResults([]);
      setStats(null);
      setSuppliersStatus([]);
      toast.success('Comparação cancelada.');
    } catch (error) {
      console.error('Cancel error:', error);
      toast.error('Erro ao cancelar a comparação.');
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
            sessionStorage.removeItem('comparing_job_id');
            await loadResults(jobId);
            setStep(3);
            toast.success('Comparação concluída!');
            setComparing(false);
            resolve();
            return;
          } else if (status === 'failed') {
            pollingTimerRef.current = null;
            sessionStorage.removeItem('comparing_job_id');
            toast.error('Erro na comparação de preços. Tente novamente.');
            setComparing(false);
            resolve();
            return;
          } else if (Date.now() - started > MAX_WAIT_MS) {
            pollingTimerRef.current = null;
            sessionStorage.removeItem('comparing_job_id');
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

  const loadResults = async (jobId = job?.id) => {
    if (!jobId) return;
    try {
      const { data } = await jobsAPI.getResults(jobId);
      const list = Array.isArray(data) ? data : [];
      setResults(list);
      setStats(summarizeResults(list));
    } catch (error) {
      toast.error(errorMessage(error, 'Erro ao carregar resultados'));
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

  const handleSave = async () => {
    if (!job?.id) return;
    setSaving(true);
    try {
      await jobsAPI.save(job.id);
      setSaved(true);
      toast.success('Tabela guardada! Disponível no Histórico de campanhas.');
    } catch (error) {
      console.error('Save error:', error);
      toast.error('Erro ao guardar a tabela');
    } finally {
      setSaving(false);
    }
  };

  const resetFlow = () => {
    if (pollingTimerRef.current) {
      clearTimeout(pollingTimerRef.current);
      pollingTimerRef.current = null;
    }
    sessionStorage.removeItem('comparing_job_id');
    setStep(1);
    setFile(null);
    setJob(null);
    setResults([]);
    setStats(null);
    setSuppliersStatus([]);
    setComparing(false);
  };

  const statusMeta = {
    waiting: { icon: <Clock size={14} />,         label: 'A aguardar', cls: 'text-slate-400' },
    running: { icon: <RotateCw size={14} className="animate-spin" />, label: 'A correr', cls: 'text-blue-600' },
    done:    { icon: <CheckCircle2 size={14} />,  label: 'Concluído',  cls: 'text-emerald-600' },
    partial: { icon: <AlertCircle size={14} />,   label: 'Parcial',    cls: 'text-amber-600' },
    failed:  { icon: <XCircle size={14} />,       label: 'Erro',       cls: 'text-red-600' },
    error:   { icon: <XCircle size={14} />,       label: 'Erro',       cls: 'text-red-600' },
    timeout: { icon: <AlertCircle size={14} />,   label: 'Timeout',    cls: 'text-orange-500' },
  };

  const SupplierStatusTable = () => (
    <div className="mt-4 rounded-lg border border-slate-200 dark:border-border overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 dark:bg-emerald-500/10 text-slate-500 dark:text-muted-foreground text-xs uppercase">
          <tr>
            <th className="px-4 py-2 text-left">Fornecedor</th>
            <th className="px-4 py-2 text-left">Estado</th>
            <th className="px-4 py-2 text-right">Tempo</th>
            <th className="px-4 py-2 text-right">Produtos</th>
            <th className="px-4 py-2 text-right">Melhor Preço</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 dark:divide-border">
          {suppliersStatus.map((s) => {
            const m = statusMeta[s.status] || statusMeta.waiting;
            return (
              <tr key={s.name} className="bg-white dark:bg-card hover:bg-slate-50 dark:hover:bg-emerald-500/10">
                <td className="px-4 py-2 font-medium text-slate-700 dark:text-foreground">{s.name}</td>
                <td className={`px-4 py-2 ${m.cls}`}>
                  <span className="flex items-center gap-1">{m.icon} {m.label}</span>
                  {s.error && (
                    <span className="block text-xs text-red-600 dark:text-red-400 max-w-[260px]" title={s.error}>
                      {ERROR_KIND_LABELS[s.error_kind] ? `${ERROR_KIND_LABELS[s.error_kind]}: ` : ''}{s.error}
                    </span>
                  )}
                </td>
                <td className="px-4 py-2 text-right text-slate-500 dark:text-muted-foreground">
                  {s.duration_s != null ? `${s.duration_s}s` : '-'}
                </td>
                <td className="px-4 py-2 text-right text-slate-600 dark:text-muted-foreground">
                  {s.products != null ? s.products : '-'}
                </td>
                <td className="px-4 py-2 text-right font-medium text-slate-700 dark:text-foreground">
                  {s.best_price != null ? formatPrice(s.best_price) : '-'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );

  return (
    <div className="space-y-6" data-testid="comparar-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
        <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.16em] text-primary">Campanhas de fornecedores</p>
        <h1 className="text-2xl sm:text-[28px] font-extrabold leading-tight tracking-[-0.02em] text-foreground">Comparar campanhas</h1>
         <p className="text-slate-500 dark:text-slate-400">Carregue a lista da campanha do fornecedor e compare com o seu preço</p>
        </div>
        {step > 1 && (
          <Button variant="outline" onClick={resetFlow}>
            Nova Comparação
          </Button>
        )}
      </div>

      {/* Progress Steps */}
      <div className="flex flex-wrap items-center justify-center gap-2 sm:gap-4 py-4 text-sm sm:text-base">
        <div className={`flex items-center gap-2 ${step >= 1 ? 'text-emerald-600' : 'text-slate-400'}`}>
          <div className={`w-8 h-8 rounded-full flex items-center justify-center ${step >= 1 ? 'bg-emerald-100' : 'bg-slate-100'}`}>
            {step > 1 ? <CheckCircle className="w-5 h-5" /> : '1'}
          </div>
          <span className="font-medium">Upload</span>
        </div>
        <ArrowRight className="w-4 h-4 text-slate-300" />
        <div className={`flex items-center gap-2 ${step >= 2 ? 'text-emerald-600' : 'text-slate-400'}`}>
          <div className={`w-8 h-8 rounded-full flex items-center justify-center ${step >= 2 ? 'bg-emerald-100' : 'bg-slate-100'}`}>
            {step > 2 ? <CheckCircle className="w-5 h-5" /> : '2'}
          </div>
          <span className="font-medium">Comparar</span>
        </div>
        <ArrowRight className="w-4 h-4 text-slate-300" />
        <div className={`flex items-center gap-2 ${step >= 3 ? 'text-emerald-600' : 'text-slate-400'}`}>
          <div className={`w-8 h-8 rounded-full flex items-center justify-center ${step >= 3 ? 'bg-emerald-100' : 'bg-slate-100'}`}>
            {step === 3 ? <CheckCircle className="w-5 h-5" /> : '3'}
          </div>
          <span className="font-medium">Resultados</span>
        </div>
      </div>

      {/* Step 1: Upload */}
      {step === 1 && (
        <Card className="border-slate-200 max-w-2xl mx-auto">
          <CardHeader>
            <CardTitle>Passo 1: Carregar Ficheiro Excel</CardTitle>
            <p className="text-sm text-slate-600 mt-2">
              Colunas: Medida e MeuPreço (obrigatórias) | Marca | Modelo | Indice. Formatos .xlsx, .xls ou .csv
            </p>
          </CardHeader>
          <CardContent className="space-y-6">
            <div>
              <div className="border-2 border-dashed border-slate-300 rounded-lg p-8 text-center hover:border-emerald-400 transition-colors">
                <input
                  id="file-upload"
                  type="file"
                  accept=".xlsx,.xls,.csv"
                  onChange={handleFileChange}
                  className="hidden"
                  data-testid="file-input"
                />
                <label htmlFor="file-upload" className="cursor-pointer">
                  {file ? (
                    <div className="flex items-center justify-center gap-3">
                      <FileSpreadsheet className="text-emerald-600" size={40} />
                      <div className="text-left">
                        <p className="font-medium text-slate-900">{file.name}</p>
                        <p className="text-sm text-slate-500">{(file.size / 1024).toFixed(2)} KB</p>
                      </div>
                    </div>
                  ) : (
                    <div>
                      <UploadIcon className="mx-auto text-slate-400 mb-3" size={48} />
                      <p className="text-slate-600">Clique para selecionar ou arraste o ficheiro</p>
                      <p className="text-xs text-slate-500 mt-1">.xlsx, .xls ou .csv</p>
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
        <Card className="border-slate-200 max-w-2xl mx-auto">
          <CardHeader>
            <CardTitle>Passo 2: Comparar com Preços Scraped</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="p-4 bg-emerald-50 border border-emerald-200 rounded-lg">
              <div className="flex items-center gap-3">
                <CheckCircle className="text-emerald-600 w-6 h-6" />
                <div>
                  <p className="font-medium text-emerald-800">Ficheiro carregado com sucesso!</p>
                  <p className="text-sm text-emerald-600">{job.total_items} itens encontrados</p>
                  {job.error_message && <p className="text-sm text-amber-700 dark:text-amber-400 mt-1">{job.error_message}</p>}
                </div>
              </div>
            </div>

            <div className="text-center py-4">
              <p className="text-slate-600 mb-4">
                Clique no botão abaixo para comparar os seus preços com os preços dos fornecedores.
              </p>
              <p className="text-sm text-slate-500">
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
            
            {comparing && (
              <Button
                onClick={handleCancel}
                variant="outline"
                className="w-full border-red-300 text-red-600 hover:bg-red-50 dark:hover:bg-red-500/10"
                size="lg"
              >
                <XCircle className="mr-2 h-5 w-5" />
                Cancelar comparação
              </Button>
            )}

            {suppliersStatus.length > 0 && <SupplierStatusTable />}
          </CardContent>
        </Card>
      )}

      {/* Step 3: Results */}
      {step === 3 && (
        <>
          {/* Stats Card */}
          {stats && (
            <Card className="bg-gradient-to-r from-emerald-50 to-teal-50 dark:from-emerald-500/10 dark:to-emerald-500/10 border-emerald-200 dark:border-emerald-500/20">
            <CardContent className="pt-6">
              <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-4">
                <div className="flex flex-wrap items-center gap-4 sm:gap-8">
                  <div>
                    <p className="text-sm text-slate-600 dark:text-muted-foreground">Total de Itens</p>
                    <p className="text-3xl font-bold text-slate-700 dark:text-foreground">{stats.total}</p>
                  </div>
                  <div className="h-16 w-px bg-slate-200 dark:bg-emerald-500/20"></div>
                  <div>
                    <p className="text-sm text-slate-600 dark:text-muted-foreground">Correspondência exacta</p>
                    <p className="text-3xl font-bold text-slate-700 dark:text-foreground">{stats.exact}</p>
                  </div>
                  <div className="h-16 w-px bg-slate-200 dark:bg-emerald-500/20"></div>
                  <div>
                    <p className="text-sm text-slate-600 dark:text-muted-foreground">Exactos com preço melhor</p>
                    <p className="text-3xl font-bold text-emerald-600 dark:text-emerald-400">{stats.found}</p>
                  </div>
                  <div className="h-16 w-px bg-slate-200 dark:bg-emerald-500/20"></div>
                  <div>
                    <p className="text-sm text-slate-600 dark:text-muted-foreground">Poupança (só exactos)</p>
                    <p className="text-3xl font-bold text-emerald-600 dark:text-emerald-400">{formatPrice(stats.savings)}</p>
                  </div>
                </div>

                  <div className="flex flex-wrap gap-2">
                    {!saved && (
                      <Button
                        onClick={handleSave}
                        disabled={saving}
                        className="bg-emerald-600 hover:bg-emerald-700 ring-2 ring-emerald-300 ring-offset-1"
                        data-testid="save-table-btn"
                      >
                        {saving ? (
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        ) : (
                          <Save className="mr-2 h-4 w-4" />
                        )}
                        Guardar tabela
                      </Button>
                    )}
                    {saved && (
                      <Badge variant="outline" className="self-center bg-emerald-100 text-emerald-800 border-emerald-400">
                        <CheckCircle className="inline w-3 h-3 mr-1" /> Guardada
                      </Badge>
                    )}
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

          <Card>
            <CardHeader>
              <CardTitle>Resultados da comparação</CardTitle>
              <p className="text-xs text-muted-foreground">
                A poupança só é calculada para correspondências exactas. Alternativas e linhas com informação insuficiente aparecem identificadas, sem poupança.
              </p>
            </CardHeader>
            <CardContent>
              <ComparisonResultsTable results={results} />
            </CardContent>
          </Card>
</>
      )}

</div>
  );
};

export default Comparar;