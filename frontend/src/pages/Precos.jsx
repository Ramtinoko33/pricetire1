import React, { useState, useEffect, useCallback } from 'react';
import { scrapedPricesAPI, scrapeAPI, suppliersAPI, workerAPI } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { Progress } from '../components/ui/progress';
import { Search, RefreshCw, TrendingDown, Loader2, Zap, CheckCircle, XCircle, Clock } from 'lucide-react';
import { toast } from 'sonner';

const Precos = () => {
  const [medida, setMedida] = useState('');
const [marca, setMarca] = useState('');
const [modelo, setModelo] = useState('');
const [loadIndex, setLoadIndex] = useState('');
  const [prices, setPrices] = useState([]);
  const [loading, setLoading] = useState(false);
  const [scraping, setScraping] = useState(false);
  const [suppliers, setSuppliers] = useState([]);
  const [stats, setStats] = useState(null);
  
  // Scraping progress state
  const [scrapingProgress, setScrapingProgress] = useState(null);
  const [jobIds, setJobIds] = useState([]);

  useEffect(() => {
    loadSuppliers();
    loadAllPrices();
  }, []);

  // Poll for job progress
  useEffect(() => {
    if (!scraping || jobIds.length === 0) return;
    
    const pollInterval = setInterval(async () => {
      try {
        const { data: jobs } = await scrapeAPI.getJobs(null, 20);
        
        // Filter our jobs
        const ourJobs = jobs.filter(j => jobIds.includes(j._id));
        
        const completed = ourJobs.filter(j => j.status === 'done').length;
        const failed = ourJobs.filter(j => j.status === 'error').length;
        const running = ourJobs.filter(j => j.status === 'running').length;
        const queued = ourJobs.filter(j => j.status === 'queued').length;
        
        setScrapingProgress({
          total: ourJobs.length,
          completed,
          failed,
          running,
          queued,
          percent: Math.round((completed / ourJobs.length) * 100),
          jobs: ourJobs
        });
        
        // All done
        if (queued === 0 && running === 0) {
          clearInterval(pollInterval);
          setScraping(false);
          
          if (completed === ourJobs.length) {
            toast.success(`Scraping concluído! ${completed} fornecedores processados.`);
          } else {
            toast.warning(`Scraping concluído com ${failed} erros.`);
          }
          
          // Reload prices
          searchPrices();
        }
      } catch (error) {
        console.error('Error polling jobs:', error);
      }
    }, 3000);
    
    return () => clearInterval(pollInterval);
  }, [scraping, jobIds]);

  const loadSuppliers = async () => {
    try {
      const { data } = await suppliersAPI.getAll();
      setSuppliers(data.filter(s => s.is_active));
    } catch (error) {
      console.error('Error loading suppliers:', error);
    }
  };

  const loadAllPrices = async () => {
    setLoading(true);
    try {
      const { data } = await scrapedPricesAPI.getAll();
      processPrices(data);
    } catch (error) {
      console.error('Error loading prices:', error);
      toast.error('Erro ao carregar preços');
    } finally {
      setLoading(false);
    }
  };

  const searchPrices = async () => {
    // Check if at least one field has a value
    const hasMedida = medida.trim();
    const hasMarca = marca.trim();
    const hasModelo = modelo.trim();
    const hasLoadIndex = loadIndex.trim();
    
    if (!hasMedida && !hasMarca && !hasModelo && !hasLoadIndex) {
      loadAllPrices();
      return;
    }

    setLoading(true);
    try {
      // Normalize medida if provided
      const medidaNorm = hasMedida ? medida.split(',').map(s => s.trim().replace(/\//g, '').replace(/R/gi, '')).filter(s => s)[0] : null;
      
      // Call API with all filters
      const { data } = await scrapedPricesAPI.getAll(
        medidaNorm || null,
        hasMarca ? marca.trim() : null,
        hasModelo ? modelo.trim() : null,
        hasLoadIndex ? loadIndex.trim() : null
      );
      
      // If multiple medidas, filter client-side
      if (hasMedida && medida.includes(',')) {
        const sizes = medida.split(',').map(s => s.trim().replace(/\//g, '').replace(/R/gi, '')).filter(s => s);
        const filtered = data.filter(p => sizes.includes(p.medida));
        processPrices(filtered);
      } else {
        processPrices(data);
      }
      
      if (prices.length === 0) {
        toast.info(`Nenhum preço encontrado. Execute um novo scraping.`);
      }
    } catch (error) {
      console.error('Error searching prices:', error);
      toast.error('Erro ao pesquisar preços');
    } finally {
      setLoading(false);
    }
  };

  const processPrices = (data) => {
    const sorted = [...data].sort((a, b) => (a.price || 999) - (b.price || 999));
    setPrices(sorted);

    const withPrice = sorted.filter(p => p.price && p.price > 0);
    if (withPrice.length > 0) {
      const minPrice = Math.min(...withPrice.map(p => p.price));
      const maxPrice = Math.max(...withPrice.map(p => p.price));
      const best = withPrice.find(p => p.price === minPrice);
      
      setStats({
        total: sorted.length,
        withPrice: withPrice.length,
        minPrice,
        maxPrice,
        difference: maxPrice - minPrice,
        bestSupplier: best?.supplier_name,
        bestBrand: best?.marca,
      });
    } else {
      setStats(null);
    }
  };

  const startScraping = async () => {
    if (!medida.trim()) {
      toast.error('Introduza uma ou mais medidas separadas por vírgula');
      return;
    }

    setScraping(true);
    setScrapingProgress(null);
    setJobIds([]);
    
    try {
      // Check worker status and start if needed
      const { data: workerStatus } = await workerAPI.getStatus();
      
      if (!workerStatus.running) {
        toast.info('A iniciar o worker...');
        const { data: startResult } = await workerAPI.start();
        
        if (!startResult.ok) {
          toast.error('Erro ao iniciar o worker');
          setScraping(false);
          return;
        }
        
        // Wait a bit for worker to fully initialize
        await new Promise(resolve => setTimeout(resolve, 2000));
      }
      
      // Parse sizes (comma-separated)
      const sizes = medida.split(',').map(s => s.trim()).filter(s => s);
      
      if (sizes.length === 0) {
        toast.error('Nenhuma medida válida');
        setScraping(false);
        return;
      }
      
      // Enqueue batch job for all active suppliers
      const { data } = await scrapeAPI.enqueueBatch(sizes);
      
      if (data.ok) {
        setJobIds(data.job_ids);
        
        setScrapingProgress({
          total: data.jobs_created,
          completed: 0,
          failed: 0,
          running: 0,
          queued: data.jobs_created,
          percent: 0,
          jobs: []
        });
        
        toast.success(`Scraping iniciado: ${data.jobs_created} jobs para ${data.suppliers.length} fornecedores`);
      } else {
        toast.error('Erro ao criar jobs de scraping');
        setScraping(false);
      }
    } catch (error) {
      console.error('Error starting scraping:', error);
      toast.error('Erro ao iniciar scraping: ' + (error.response?.data?.detail || error.message));
      setScraping(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      searchPrices();
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('pt-PT', { 
      day: '2-digit', 
      month: '2-digit', 
      year: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  return (
    <div className="space-y-6" data-testid="precos-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Pesquisa de Preços</h1>
          <p className="text-slate-500">Pesquise e compare preços de pneus dos fornecedores</p>
        </div>
      </div>

      {/* Search Bar */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex gap-4">
            <div className="flex-1">
              <Input
                placeholder="Medidas separadas por vírgula (ex: 205/55R16, 195/65R15)"
                value={medida}
                onChange={(e) => setMedida(e.target.value)}
                onKeyPress={handleKeyPress}
                className="text-lg"
                data-testid="medida-input"
              />
            </div>
            <div className="w-36">
              <Input
                placeholder="Marca (ex: Michelin)"
                value={marca}
                onChange={(e) => setMarca(e.target.value)}
                onKeyPress={handleKeyPress}
              />
            </div>
            <div className="w-40">
              <Input
                placeholder="Modelo (ex: Primacy)"
                value={modelo}
                onChange={(e) => setModelo(e.target.value)}
                onKeyPress={handleKeyPress}
              />
            </div>
            <div className="w-28">
              <Input
                placeholder="Índice (ex: 91V)"
                value={loadIndex}
                onChange={(e) => setLoadIndex(e.target.value)}
                onKeyPress={handleKeyPress}
              />
            </div>
            <Button onClick={searchPrices} disabled={loading} data-testid="search-btn">
              {loading ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Search className="w-4 h-4 mr-2" />
              )}
              Pesquisar
            </Button>
            <Button variant="outline" onClick={loadAllPrices} disabled={loading} data-testid="refresh-btn">
              <RefreshCw className="w-4 h-4 mr-2" />
              Ver Todos
            </Button>
            <Button 
              variant="default"
              className="bg-amber-500 hover:bg-amber-600"
              onClick={startScraping} 
              disabled={scraping || !medida.trim()}
              data-testid="scrape-btn"
            >
              {scraping ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Zap className="w-4 h-4 mr-2" />
              )}
              Novo Scraping
            </Button>
          </div>
          
          {/* Scraping Progress */}
          {scraping && scrapingProgress && (
            <div className="mt-4 p-4 bg-slate-50 rounded-lg border">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-slate-700">
                  Scraping em progresso...
                </span>
                <span className="text-sm text-slate-500">
                  {scrapingProgress.completed} / {scrapingProgress.total} fornecedores
                </span>
              </div>
              
              <Progress value={scrapingProgress.percent} className="h-2 mb-3" />
              
              <div className="flex gap-4 text-sm">
                <div className="flex items-center gap-1 text-emerald-600">
                  <CheckCircle className="w-4 h-4" />
                  {scrapingProgress.completed} concluídos
                </div>
                <div className="flex items-center gap-1 text-blue-600">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  {scrapingProgress.running} a executar
                </div>
                <div className="flex items-center gap-1 text-slate-500">
                  <Clock className="w-4 h-4" />
                  {scrapingProgress.queued} em fila
                </div>
                {scrapingProgress.failed > 0 && (
                  <div className="flex items-center gap-1 text-red-600">
                    <XCircle className="w-4 h-4" />
                    {scrapingProgress.failed} erros
                  </div>
                )}
              </div>
              
              {/* Per-supplier status */}
              {scrapingProgress.jobs && scrapingProgress.jobs.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {scrapingProgress.jobs.map((job, idx) => (
                    <Badge 
                      key={job._id || idx}
                      variant="outline"
                      className={
                        job.status === 'done' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' :
                        job.status === 'running' ? 'bg-blue-50 text-blue-700 border-blue-200' :
                        job.status === 'error' ? 'bg-red-50 text-red-700 border-red-200' :
                        'bg-slate-50 text-slate-500'
                      }
                    >
                      {job.supplier_name || job.supplier_id}
                      {job.status === 'running' && <Loader2 className="w-3 h-3 ml-1 animate-spin" />}
                      {job.status === 'done' && <CheckCircle className="w-3 h-3 ml-1" />}
                      {job.status === 'error' && <XCircle className="w-3 h-3 ml-1" />}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Stats Card */}
      {stats && (
        <Card className="bg-gradient-to-r from-emerald-50 to-teal-50 border-emerald-200">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-8">
                <div>
                  <p className="text-sm text-slate-600">Melhor Preço</p>
                  <p className="text-3xl font-bold text-emerald-600">€{stats.minPrice.toFixed(2)}</p>
                  <p className="text-sm text-slate-500">{stats.bestSupplier} • {stats.bestBrand}</p>
                </div>
                <div className="h-16 w-px bg-slate-200"></div>
                <div>
                  <p className="text-sm text-slate-600">Pior Preço</p>
                  <p className="text-2xl font-semibold text-red-500">€{stats.maxPrice.toFixed(2)}</p>
                </div>
                <div className="h-16 w-px bg-slate-200"></div>
                <div>
                  <p className="text-sm text-slate-600">Diferença</p>
                  <p className="text-2xl font-semibold text-amber-600">€{stats.difference.toFixed(2)}</p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-sm text-slate-600">Total Produtos</p>
                <p className="text-2xl font-semibold text-slate-700">{stats.total}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Results Table */}
      <Card>
        <CardHeader>
          <CardTitle>Preços Encontrados ({prices.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
            </div>
          ) : prices.length === 0 ? (
            <div className="text-center py-12 text-slate-500">
              <p>Nenhum preço encontrado.</p>
              <p className="text-sm mt-2">Introduza uma medida e clique em "Novo Scraping" para obter preços.</p>
            </div>
          ) : (
            <div className="max-h-[600px] overflow-auto">
              <Table>
                <TableHeader className="sticky top-0 bg-white z-10">
                  <TableRow>
                    <TableHead>Medida</TableHead>
                    <TableHead>Marca</TableHead>
                    <TableHead>Modelo</TableHead>
                    <TableHead>Fornecedor</TableHead>
                    <TableHead className="text-right">Preço</TableHead>
                    <TableHead>Atualizado</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {prices.map((item, index) => {
                    const isBest = stats && item.price === stats.minPrice;
                    
                    return (
                      <TableRow 
                        key={item._id || index}
                        className={isBest ? 'bg-emerald-50 hover:bg-emerald-100' : ''}
                        data-testid={`price-row-${index}`}
                      >
                        <TableCell className="font-mono font-medium">{item.medida}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className="font-medium">
                            {item.marca || '-'}
                          </Badge>
                        </TableCell>
                        <TableCell className="max-w-[200px] truncate text-slate-600" title={item.modelo}>
                          {item.modelo || '-'}
                        </TableCell>
                        <TableCell>
                          <Badge 
                            variant={item.supplier_name === stats?.bestSupplier && isBest ? 'default' : 'secondary'}
                            className={isBest ? 'bg-emerald-600' : ''}
                          >
                            {item.supplier_name}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <span className={`font-bold ${isBest ? 'text-emerald-600 text-lg' : ''}`}>
                            {isBest && <TrendingDown className="inline w-4 h-4 mr-1" />}
                            €{item.price?.toFixed(2) || '-'}
                          </span>
                        </TableCell>
                        <TableCell className="text-slate-500 text-sm">
                          {formatDate(item.scraped_at)}
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
    </div>
  );
};

export default Precos;
