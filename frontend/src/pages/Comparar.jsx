import React, { useState, useEffect } from 'react';
import { jobsAPI } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { Upload as UploadIcon, FileSpreadsheet, Loader2, Scale, Download, TrendingDown, CheckCircle, ArrowRight } from 'lucide-react';
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

  const handleCompare = async () => {
    if (!job?.id) return;

    setComparing(true);
    try {
      const { data } = await jobsAPI.compare(job.id);
      setStats({
        total: data.items_processed,
        found: data.items_with_savings,
        savings: data.total_savings
      });
      setStep(3);
      toast.success(`Comparação concluída! ${data.items_with_savings} itens com preço melhor.`);
      await loadResults();
    } catch (error) {
      console.error('Compare error:', error);
      toast.error(error.response?.data?.detail || 'Erro ao comparar preços');
    } finally {
      setComparing(false);
    }
  };

  const loadResults = async () => {
    try {
      const { data } = await jobsAPI.getResults(job.id);
      // Sort by economia_euro descending
      const sorted = [...data].sort((a, b) => (b.economia_euro || 0) - (a.economia_euro || 0));
      setResults(sorted);
      
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
    setStep(1);
    setFile(null);
    setJob(null);
    setResults([]);
    setStats(null);
  };

  return (
    <div className="space-y-6" data-testid="comparar-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Comparar Preços Excel</h1>
          <p className="text-slate-500">Carregue um ficheiro Excel e compare com os preços dos fornecedores</p>
        </div>
        {step > 1 && (
          <Button variant="outline" onClick={resetFlow}>
            Nova Comparação
          </Button>
        )}
      </div>

      {/* Progress Steps */}
      <div className="flex items-center justify-center gap-4 py-4">
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
              Colunas esperadas: Medida | Marca | Modelo | Indice | MeuPreço
            </p>
          </CardHeader>
          <CardContent className="space-y-6">
            <div>
              <div className="border-2 border-dashed border-slate-300 rounded-lg p-8 text-center hover:border-emerald-400 transition-colors">
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
                        <p className="font-medium text-slate-900">{file.name}</p>
                        <p className="text-sm text-slate-500">{(file.size / 1024).toFixed(2)} KB</p>
                      </div>
                    </div>
                  ) : (
                    <div>
                      <UploadIcon className="mx-auto text-slate-400 mb-3" size={48} />
                      <p className="text-slate-600">Clique para selecionar ou arraste o ficheiro</p>
                      <p className="text-xs text-slate-500 mt-1">Apenas .xlsx ou .xls</p>
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
          </CardContent>
        </Card>
      )}

      {/* Step 3: Results */}
      {step === 3 && (
        <>
          {/* Stats Card */}
          {stats && (
            <Card className="bg-gradient-to-r from-emerald-50 to-teal-50 border-emerald-200">
              <CardContent className="pt-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-8">
                    <div>
                      <p className="text-sm text-slate-600">Total de Itens</p>
                      <p className="text-3xl font-bold text-slate-700">{stats.total}</p>
                    </div>
                    <div className="h-16 w-px bg-slate-200"></div>
                    <div>
                      <p className="text-sm text-slate-600">Com Preço Melhor</p>
                      <p className="text-3xl font-bold text-emerald-600">{stats.found}</p>
                    </div>
                    <div className="h-16 w-px bg-slate-200"></div>
                    <div>
                      <p className="text-sm text-slate-600">Poupança Total</p>
                      <p className="text-3xl font-bold text-emerald-600">€{stats.savings?.toFixed(2)}</p>
                    </div>
                  </div>
                  <Button onClick={handleExport} disabled={exporting} data-testid="export-btn">
                    {exporting ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <Download className="mr-2 h-4 w-4" />
                    )}
                    Exportar Excel
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Results Table */}
          <Card>
            <CardHeader>
              <CardTitle>Resultados da Comparação</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="max-h-[500px] overflow-auto">
                <Table>
                  <TableHeader className="sticky top-0 bg-white">
                    <TableRow>
                      <TableHead>Medida</TableHead>
                      <TableHead>Marca</TableHead>
                      <TableHead>Modelo</TableHead>
                      <TableHead>Modelo Encontrado</TableHead>
                      <TableHead className="text-right">Meu Preço</TableHead>
                      <TableHead className="text-right">Melhor Preço</TableHead>
                      <TableHead>Fornecedor</TableHead>
                      <TableHead className="text-right">Economia €</TableHead>
                      <TableHead className="text-right">Economia %</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {results.map((item, index) => {
                      const hasSavings = item.status === 'found' && item.economia_euro && item.economia_euro > 0;
                      const isOtherBrand = item.status === 'no_brand_match';
                      const matchType = item.match_type;
                      
                      // Define badge styles based on match type
                      const getMatchBadge = () => {
                        switch(matchType) {
                          case 'modelo_exato':
                            return <Badge variant="outline" className="text-xs bg-green-100 text-green-800 border-green-300">modelo exato</Badge>;
                          case 'modelo_parcial':
                            return <Badge variant="outline" className="text-xs bg-emerald-50 text-emerald-700 border-emerald-300">modelo parcial</Badge>;
                          case 'marca':
                            return <Badge variant="outline" className="text-xs bg-blue-50 text-blue-700 border-blue-300">marca</Badge>;
                          case 'marca_parcial':
                            return <Badge variant="outline" className="text-xs bg-sky-50 text-sky-700 border-sky-300">marca parcial</Badge>;
                          case 'medida':
                            return <Badge variant="outline" className="text-xs bg-amber-50 text-amber-700 border-amber-300">só medida</Badge>;
                          case 'sem_dados':
                            return <Badge variant="outline" className="text-xs bg-red-50 text-red-700 border-red-300">sem dados</Badge>;
                          default:
                            return null;
                        }
                      };
                      
                      return (
                        <TableRow
                          key={item.id || index}
                          className={hasSavings ? 'bg-emerald-50 hover:bg-emerald-100' : isOtherBrand ? 'bg-amber-50/30' : ''}
                          data-testid={`result-row-${index}`}
                        >
                          <TableCell className="font-mono">{item.medida}</TableCell>
                          <TableCell>
                            <div className="flex items-center gap-2">
                              <span>{item.marca}</span>
                              {getMatchBadge()}
                            </div>
                          </TableCell>
                          <TableCell className="max-w-[120px] truncate text-slate-600" title={item.modelo}>
                            {item.modelo || '-'}
                          </TableCell>
                          <TableCell className="max-w-[150px] truncate font-medium" title={item.modelo_encontrado}>
                            {item.modelo_encontrado || '-'}
                          </TableCell>
                          <TableCell className="text-right font-medium">
                            {item.meu_preco ? `€${item.meu_preco.toFixed(2)}` : '-'}
                          </TableCell>
                          <TableCell className="text-right font-medium">
                            {item.melhor_preco ? (
                              <span className={hasSavings ? 'text-emerald-600' : ''}>
                                €{item.melhor_preco.toFixed(2)}
                              </span>
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
                              <span className="text-xs text-amber-600">outra marca</span>
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
