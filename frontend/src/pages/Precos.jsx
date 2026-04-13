import React, { useState, useEffect, useRef } from 'react';
import { scrapedPricesAPI } from '../lib/api';
import api from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { Search, RefreshCw, TrendingDown, Loader2, Zap, Database } from 'lucide-react';
import { toast } from 'sonner';

const Precos = () => {
  const [medida, setMedida]     = useState('');
  const [marca, setMarca]       = useState('');
  const [modelo, setModelo]     = useState('');
  const [loadIndex, setLoadIndex] = useState('');

  const [prices, setPrices]   = useState([]);
  const [stats, setStats]     = useState(null);
  const [loading, setLoading] = useState(false);

  // Live scraping state
  const [scraping, setScraping]         = useState(false);
  const [scrapeProgress, setScrapeProgress] = useState('');
  const pollRef = useRef(null);

  // ── helpers ────────────────────────────────────────────────────────────────

  const normMedida = (s) => s.trim().replace(/\//g, '').replace(/[Rr]/g, '');

  const processPrices = (data) => {
    const sorted = [...data].sort((a, b) => (a.price ?? 999) - (b.price ?? 999));
    setPrices(sorted);
    const withPrice = sorted.filter(p => p.price > 0);
    if (withPrice.length > 0) {
      const minPrice = Math.min(...withPrice.map(p => p.price));
      const maxPrice = Math.max(...withPrice.map(p => p.price));
      const best = withPrice.find(p => p.price === minPrice);
      setStats({ total: sorted.length, withPrice: withPrice.length, minPrice, maxPrice,
                 difference: maxPrice - minPrice, bestSupplier: best?.supplier_name, bestBrand: best?.marca });
    } else {
      setStats(null);
    }
  };

  const formatDate = (d) => d ? new Date(d).toLocaleDateString('pt-PT', {
    day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit'
  }) : '-';

  // ── Pesquisar no Banco Local ───────────────────────────────────────────────

  const searchLocal = async () => {
    setLoading(true);
    try {
      const hasMultiple = medida.includes(',');
      // With multiple medidas don't filter server-side — fetch broadly and filter client-side
      const medidaNorm = medida.trim() && !hasMultiple ? normMedida(medida) : null;
      const { data } = await scrapedPricesAPI.getAll(
        medidaNorm || null,
        marca.trim() || null,
        modelo.trim() || null,
        loadIndex.trim() || null,
      );
      if (hasMultiple) {
        const sizes = medida.split(',').map(s => normMedida(s)).filter(Boolean);
        processPrices(data.filter(p => sizes.includes(normMedida(p.medida || ''))));
      } else {
        processPrices(data);
      }
      if (data.length === 0) toast.info('Nenhum preço no banco local. Use "Pesquisar nos Fornecedores".');
    } catch (e) {
      toast.error('Erro ao pesquisar no banco local');
    } finally {
      setLoading(false);
    }
  };

  // ── Pesquisar nos Fornecedores (live scrape) ──────────────────────────────

  const startLiveScrape = async () => {
    if (!medida.trim()) {
      toast.error('Introduza pelo menos uma medida');
      return;
    }
    const sizes = medida.split(',').map(s => normMedida(s)).filter(Boolean);
    if (!sizes.length) { toast.error('Medida inválida'); return; }

    setScraping(true);
    setScrapeProgress('A iniciar scraper...');
    setPrices([]);
    setStats(null);

    try {
      await api.post('/scraper/run', { medidas: sizes }, { timeout: 660000 });
    } catch (e) {
      // 409 = already running — that's fine
      if (e.response?.status !== 409) {
        toast.error('Erro ao iniciar scraper: ' + (e.response?.data?.detail ?? e.message));
        setScraping(false);
        return;
      }
    }

    // Poll /scraper/status until done
    pollRef.current = setInterval(async () => {
      try {
        const { data: status } = await api.get('/scraper/status');
        if (status.progress) setScrapeProgress(status.progress);

        if (!status.running) {
          clearInterval(pollRef.current);
          setScraping(false);
          setScrapeProgress('');
          toast.success('Scraping concluído!');
          // Load fresh results for ALL searched medidas
          const { data } = await scrapedPricesAPI.getAll(
            null,
            marca.trim() || null,
            modelo.trim() || null,
            loadIndex.trim() || null,
          );
          // Filter client-side for all searched sizes
          const filtered = data.filter(p => sizes.includes(normMedida(p.medida || '')));
          processPrices(filtered.length > 0 ? filtered : data);
        }
      } catch (_) {}
    }, 2500);
  };

  // stop poll on unmount
  useEffect(() => () => clearInterval(pollRef.current), []);

  const handleKey = (e) => { if (e.key === 'Enter') searchLocal(); };

  // ── render ─────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6" data-testid="precos-page">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Pesquisa de Preços</h1>
        <p className="text-slate-500">Pesquise preços nos fornecedores ou no banco de dados local</p>
      </div>

      {/* Search Bar */}
      <Card>
        <CardContent className="pt-6 space-y-3">
          <div className="flex gap-3 flex-wrap">
            <Input
              className="flex-1 min-w-[220px] text-base"
              placeholder="Medida(s) — ex: 205/55R16, 195/65R15"
              value={medida}
              onChange={e => setMedida(e.target.value)}
              onKeyDown={handleKey}
              data-testid="medida-input"
            />
            <Input className="w-36" placeholder="Marca (ex: Michelin)"
              value={marca} onChange={e => setMarca(e.target.value)} onKeyDown={handleKey} />
            <Input className="w-40" placeholder="Modelo (ex: Primacy)"
              value={modelo} onChange={e => setModelo(e.target.value)} onKeyDown={handleKey} />
            <Input className="w-28" placeholder="Índice (91V)"
              value={loadIndex} onChange={e => setLoadIndex(e.target.value)} onKeyDown={handleKey} />
          </div>

          <div className="flex gap-3 flex-wrap">
            {/* Live scrape */}
            <Button
              className="bg-amber-500 hover:bg-amber-600"
              onClick={startLiveScrape}
              disabled={scraping || loading}
              data-testid="live-scrape-btn"
            >
              {scraping ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Zap className="w-4 h-4 mr-2" />}
              Pesquisar nos Fornecedores
            </Button>

            {/* Local DB search */}
            <Button
              variant="outline"
              onClick={searchLocal}
              disabled={loading || scraping}
              data-testid="search-local-btn"
            >
              {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Database className="w-4 h-4 mr-2" />}
              Pesquisar no Banco Local
            </Button>

            <Button variant="ghost" onClick={() => { setMedida(''); setMarca(''); setModelo(''); setLoadIndex(''); setPrices([]); setStats(null); }}>
              <RefreshCw className="w-4 h-4 mr-2" />
              Limpar
            </Button>
          </div>

          {/* Scraping progress */}
          {scraping && (
            <div className="flex items-center gap-3 p-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
              <Loader2 className="w-4 h-4 animate-spin shrink-0" />
              <span className="font-mono truncate">{scrapeProgress || 'A iniciar...'}</span>
              <span className="ml-auto text-xs text-amber-600 shrink-0">pode demorar alguns minutos</span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Stats */}
      {stats && (
        <Card className="bg-gradient-to-r from-emerald-50 to-teal-50 border-emerald-200">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between flex-wrap gap-6">
              <div className="flex items-center gap-8">
                <div>
                  <p className="text-sm text-slate-600">Melhor Preço</p>
                  <p className="text-3xl font-bold text-emerald-600">€{stats.minPrice.toFixed(2)}</p>
                  <p className="text-sm text-slate-500">{stats.bestSupplier} · {stats.bestBrand}</p>
                </div>
                <div className="h-16 w-px bg-slate-200" />
                <div>
                  <p className="text-sm text-slate-600">Pior Preço</p>
                  <p className="text-2xl font-semibold text-red-500">€{stats.maxPrice.toFixed(2)}</p>
                </div>
                <div className="h-16 w-px bg-slate-200" />
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
          {prices.length === 0 ? (
            <div className="text-center py-12 text-slate-500">
              <Search className="w-12 h-12 mx-auto mb-4 opacity-30" />
              <p>Nenhum resultado.</p>
              <p className="text-sm mt-2">Use "Pesquisar nos Fornecedores" para uma pesquisa ao vivo, ou "Banco Local" para dados guardados.</p>
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
                  {prices.map((item, idx) => {
                    const isBest = stats && item.price === stats.minPrice;
                    return (
                      <TableRow key={item.id || idx} className={isBest ? 'bg-emerald-50 hover:bg-emerald-100' : ''}>
                        <TableCell className="font-mono font-medium">{item.medida}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className="font-medium">{item.marca || '-'}</Badge>
                        </TableCell>
                        <TableCell className="max-w-[200px] truncate text-slate-600" title={item.modelo}>
                          {item.modelo || '-'}
                        </TableCell>
                        <TableCell>
                          <Badge variant={isBest ? 'default' : 'secondary'} className={isBest ? 'bg-emerald-600' : ''}>
                            {item.supplier_name}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          <span className={`font-bold ${isBest ? 'text-emerald-600 text-lg' : ''}`}>
                            {isBest && <TrendingDown className="inline w-4 h-4 mr-1" />}
                            €{item.price?.toFixed(2) ?? '-'}
                          </span>
                        </TableCell>
                        <TableCell className="text-slate-500 text-sm">{formatDate(item.scraped_at)}</TableCell>
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
