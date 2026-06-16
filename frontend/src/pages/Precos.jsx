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
import { supplierSearchUrl } from '../lib/supplierLinks';

const MARCAS_FIXAS = [

  'APOLLO','AVON','BARUM','BF GOODRICH','BRIDGESTONE','CEAT','CONTINENTAL',
  'COOPER','DUNLOP','FALKEN','FIRESTONE','FULDA','GOODYEAR','HANKOOK',
  'KLEBER','KUMHO','LAUFENN','LINGLONG','MAXXIS','MICHELIN','NANKANG',
  'NEXEN','NOKIAN','PIRELLI','RADAR','SAILUN','SAVA','TOYO','UNIROYAL',
  'VREDESTEIN','WESTLAKE','YOKOHAMA',
];
const MARCAS_FIXAS_SET = new Set(MARCAS_FIXAS.map(m => m.toUpperCase()));

const Precos = () => {
  const [medida, setMedida]     = useState('');
  const [marca, setMarca]       = useState('');
  const [modelo, setModelo]     = useState('');
  const [loadIndex, setLoadIndex] = useState('');
  const [marcasOutras, setMarcasOutras] = useState([]);

  const [prices, setPrices]   = useState([]);
  const [stats, setStats]     = useState(null);
  const [loading, setLoading] = useState(false);

  // Live scraping state
  const [scraping, setScraping]         = useState(false);
  const [scrapeProgress, setScrapeProgress] = useState('');
  const pollRef = useRef(null);
  const [expanded, setExpanded] = useState(new Set());
  const toggleExpand = (key) => setExpanded(prev => {
    const next = new Set(prev);
    next.has(key) ? next.delete(key) : next.add(key);
    return next;
  });

  useEffect(() => {
    api.get('/marcas').then(res => {
      const outras = (res.data || []).filter(m => !MARCAS_FIXAS_SET.has(m.toUpperCase()));
      setMarcasOutras(outras);
    }).catch(() => {});
  }, []);

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
          // Fetch results filtering server-side by each medida searched
          // Use original format (with slash and R) to match DB values
          const originalSizes = medida.split(',').map(s => s.trim()).filter(Boolean);
          let allResults = [];
          for (const sz of originalSizes) {
            try {
              const { data } = await scrapedPricesAPI.getAll(
                sz,
                marca.trim() || null,
                modelo.trim() || null,
                loadIndex.trim() || null,
              );
              allResults = allResults.concat(data);
            } catch (_) {}
          }
          // Deduplicate by id
          const seen = new Set();
          const deduped = allResults.filter(p => {
            const key = p.id || `${p.supplier_name}|${p.medida}|${p.marca}|${p.modelo}|${p.price}`;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
          });
          processPrices(deduped.length > 0 ? deduped : allResults);
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
        <h1 className="text-2xl font-bold text-foreground">Pesquisa de Preços</h1>
        <p className="text-muted-foreground">Pesquise preços nos fornecedores ou no banco de dados local</p>
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
            <select
              className="w-36 h-10 rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              value={marca}
              onChange={e => setMarca(e.target.value)}
            >
              <option value="">-- Marca --</option>
              {MARCAS_FIXAS.map(m => <option key={m} value={m}>{m}</option>)}
              {marcasOutras.length > 0 && (
                <>
                  <option disabled>──── Outras ────</option>
                  {marcasOutras.map(m => <option key={m} value={m}>{m}</option>)}
                </>
              )}
            </select>
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
            <div className="flex items-center gap-3 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-sm text-amber-400">
              <Loader2 className="w-4 h-4 animate-spin shrink-0" />
              <span className="font-mono truncate">{scrapeProgress || 'A iniciar...'}</span>
              <span className="ml-auto text-xs text-amber-400/70 shrink-0">pode demorar alguns minutos</span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Stats */}
      {stats && (
        <Card className="border-border">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between flex-wrap gap-6">
              <div className="flex items-center gap-8">
                <div>
                  <p className="text-sm text-muted-foreground">Melhor Preço</p>
                  <p className="text-3xl font-bold text-emerald-500">€{stats.minPrice.toFixed(2)}</p>
                  <p className="text-sm text-muted-foreground">{stats.bestSupplier} · {stats.bestBrand}</p>
                </div>
                <div className="h-16 w-px bg-border" />
                <div>
                  <p className="text-sm text-muted-foreground">Pior Preço</p>
                  <p className="text-2xl font-semibold text-red-400">€{stats.maxPrice.toFixed(2)}</p>
                </div>
                <div className="h-16 w-px bg-border" />
                <div>
                  <p className="text-sm text-muted-foreground">Diferença</p>
                  <p className="text-2xl font-semibold text-amber-400">€{stats.difference.toFixed(2)}</p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-sm text-muted-foreground">Total Produtos</p>
                <p className="text-2xl font-semibold text-foreground">{stats.total}</p>
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
            <div className="text-center py-12 text-muted-foreground">
              <Search className="w-12 h-12 mx-auto mb-4 opacity-30" />
              <p>Nenhum resultado.</p>
              <p className="text-sm mt-2">Use "Pesquisar nos Fornecedores" para uma pesquisa ao vivo, ou "Banco Local" para dados guardados.</p>
            </div>
          ) : (
            <div className="max-h-[600px] overflow-auto">
              <Table>
                <TableHeader className="sticky top-0 bg-card z-10">
                  <TableRow>
                    <TableHead>Medida</TableHead>
                    <TableHead>Marca</TableHead>
                    <TableHead>Modelo</TableHead>
                    <TableHead>Índice</TableHead>
                    <TableHead>Fornecedor</TableHead>
                    <TableHead className="text-right">Preço</TableHead>
                    <TableHead>Atualizado</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(() => {
                    // Agrupar por marca+modelo+medida
                    const groups = {};
                    prices.forEach(r => {
                      const key = `${r.medida}|${r.marca}|${r.modelo}`;
                      if (!groups[key]) groups[key] = [];
                      groups[key].push(r);
                    });
                    // Ordenar cada grupo por preço
                    Object.values(groups).forEach(g => g.sort((a, b) => (a.price ?? 999) - (b.price ?? 999)));
                    const groupEntries = Object.entries(groups);
                    return groupEntries.map(([key, items]) => {
                      const best = items[0];
                      const isBest = stats && best.price === stats.minPrice;
                      const hasMultiple = items.length > 1;
                      const isExpanded = expanded.has(key);
                      return (
                        <React.Fragment key={key}>
                          <TableRow
                            className={`${isBest ? 'bg-emerald-500/10 hover:bg-emerald-500/15' : 'hover:bg-muted/40'} ${hasMultiple ? 'cursor-pointer' : ''}`}
                            onClick={hasMultiple ? () => toggleExpand(key) : undefined}
                          >
                            <TableCell className="font-mono font-medium">{best.medida}</TableCell>
                            <TableCell>
                              <Badge variant="outline" className="font-medium">{best.marca || '-'}</Badge>
                            </TableCell>
                            <TableCell className="max-w-[200px] truncate text-muted-foreground" title={best.modelo}>
                              {best.modelo || '-'}
                            </TableCell>
                            <TableCell className="font-mono text-sm text-muted-foreground">
                              {best.load_index || '-'}
                            </TableCell>
                            <TableCell>
                              <div className="flex items-center gap-2">
                              {(() => {
                                  const _u = supplierSearchUrl(best.supplier_name, best.medida);
                                  const _b = (
                                    <Badge variant={isBest ? 'default' : 'secondary'} className={`${isBest ? 'bg-emerald-500/80' : ''} ${_u ? 'cursor-pointer hover:opacity-80' : ''}`}>
                                      {best.supplier_name}
                                    </Badge>
                                  );
                                  return _u ? <a href={_u} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} title="Abrir pesquisa no fornecedor">{_b}</a> : _b;
                                })()}

                                {hasMultiple && (
                                  <span className="text-xs text-amber-500 font-medium border border-amber-400 rounded px-1.5 py-0.5">
                                    +{items.length - 1} {isExpanded ? '▲' : '▼'}
                                  </span>
                                )}
                              </div>
                            </TableCell>
                            <TableCell className="text-right">
                              <span className={`font-bold ${isBest ? 'text-emerald-500 text-lg' : 'text-foreground'}`}>
                                {isBest && <TrendingDown className="inline w-4 h-4 mr-1" />}
                                €{best.price?.toFixed(2) ?? '-'}
                              </span>
                            </TableCell>
                            <TableCell className="text-muted-foreground text-sm">{formatDate(best.scraped_at)}</TableCell>
                          </TableRow>
                          {hasMultiple && isExpanded && items.slice(1).map((item, i) => (
                            <TableRow key={item.id || i} className="bg-muted/20 border-l-2 border-amber-400">
                              <TableCell className="font-mono text-xs text-muted-foreground pl-6">↳</TableCell>
                              <TableCell></TableCell>
                              <TableCell className="max-w-[200px] truncate text-muted-foreground text-xs" title={item.modelo}>
                                {item.modelo || '-'}
                              </TableCell>
                              <TableCell className="font-mono text-xs text-muted-foreground">
                                {item.load_index || '-'}
                              </TableCell>
                              <TableCell>
                                {(() => {
                                  const _u = supplierSearchUrl(item.supplier_name, item.medida);
                                  return _u ? (
                                    <a href={_u} target="_blank" rel="noopener noreferrer" title="Abrir pesquisa no fornecedor">
                                      <Badge variant="secondary" className="cursor-pointer hover:opacity-80">{item.supplier_name}</Badge>
                                    </a>
                                  ) : <Badge variant="secondary">{item.supplier_name}</Badge>;
                                })()}
                              </TableCell>
                              <TableCell className="text-right">
                                <span className="font-semibold text-muted-foreground">€{item.price?.toFixed(2) ?? '-'}</span>
                              </TableCell>
                              <TableCell className="text-muted-foreground text-sm">{formatDate(item.scraped_at)}</TableCell>
                            </TableRow>
                          ))}
                        </React.Fragment>
                      );
                    });
                  })()}
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
