import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Play, RefreshCw, CheckCircle, XCircle, Clock, Loader2 } from 'lucide-react';
import api from '../lib/api';

const ScraperPage = () => {
  const [scraperStatus, setScraperStatus] = useState(null);
  const [scrapedPrices, setScrapedPrices] = useState([]);
  const [medida, setMedida] = useState('205/55R16');
  const [filterMedida, setFilterMedida] = useState('');
  const [loading, setLoading] = useState(false);
  const [polling, setPolling] = useState(false);

  useEffect(() => {
    loadScraperStatus();
    loadScrapedPrices();
  }, []);

  useEffect(() => {
    let interval;
    if (polling) {
      interval = setInterval(() => {
        loadScraperStatus();
      }, 3000);
    }
    return () => clearInterval(interval);
  }, [polling]);

  const loadScraperStatus = async () => {
    try {
      const { data } = await api.get('/scraper/status');
      setScraperStatus(data);
      setPolling(data.running);
    } catch (error) {
      console.error('Error loading scraper status:', error);
    }
  };

  const loadScrapedPrices = async () => {
    try {
      const { data } = await api.get('/scraped-prices');
      setScrapedPrices(data);
    } catch (error) {
      console.error('Error loading scraped prices:', error);
    }
  };

  const startScraper = async () => {
    setLoading(true);
    try {
      const medidaNorm = medida.replace('/', '').replace('R', '');
      await api.post('/scraper/run', { medidas: [medidaNorm] });
      setPolling(true);
      loadScraperStatus();
    } catch (error) {
      console.error('Error starting scraper:', error);
      const detail = error.response?.data?.detail;
      const msg = typeof detail === 'string' ? detail : JSON.stringify(detail) ?? error.message;
      alert('Erro ao iniciar scraper: ' + msg);
    } finally {
      setLoading(false);
    }
  };

  const getBestPrice = async () => {
    try {
      const { data } = await api.get(`/scraped-prices/best/${medida}`);
      if (data.best_price) {
        alert(`Melhor preço para ${medida}: €${data.best_price} (${data.best_supplier})`);
      } else {
        alert(`Nenhum preço encontrado para ${medida}. Execute o scraper primeiro.`);
      }
    } catch (error) {
      console.error('Error getting best price:', error);
    }
  };

  // Group prices by medida, with optional filter
  const norm = (s) => s.replace(/\//g, '').replace(/r/gi, '').toLowerCase();
  const pricesByMedida = scrapedPrices.reduce((acc, price) => {
    if (filterMedida && !norm(price.medida).includes(norm(filterMedida))) return acc;
    const key = price.medida;
    if (!acc[key]) acc[key] = [];
    acc[key].push(price);
    return acc;
  }, {});

  return (
    <div className="space-y-6" data-testid="scraper-page">
      {/* Control Panel */}
      <Card className="border-slate-200">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Play className="w-5 h-5" />
            Scraper Manual
          </CardTitle>
          <CardDescription>
            Execute o scraper para obter os preços mais recentes dos fornecedores
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex gap-4 items-end">
            <div className="flex-1">
              <label className="text-sm text-slate-600 mb-2 block">Medida do Pneu</label>
              <Input
                value={medida}
                onChange={(e) => setMedida(e.target.value)}
                placeholder="Ex: 205/55R16"
                data-testid="medida-input"
              />
            </div>
            <Button
              onClick={startScraper}
              disabled={loading || scraperStatus?.running}
              data-testid="start-scraper-btn"
              className="bg-indigo-600 hover:bg-indigo-700"
            >
              {(loading || scraperStatus?.running) ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  A executar...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 mr-2" />
                  Executar Scraper
                </>
              )}
            </Button>
            <Button
              variant="outline"
              onClick={() => { loadScraperStatus(); loadScrapedPrices(); }}
              data-testid="refresh-btn"
            >
              <RefreshCw className="w-4 h-4" />
            </Button>
          </div>

          {/* Scraper Status */}
          {scraperStatus && (
            <div className="p-4 bg-slate-50 rounded-sm border border-slate-200">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-sm font-medium">Estado:</span>
                {scraperStatus.running ? (
                  <Badge variant="secondary" className="bg-yellow-100 text-yellow-800">
                    <Loader2 className="w-3 h-3 mr-1 animate-spin" />
                    Em execução
                  </Badge>
                ) : (
                  <Badge variant="outline">
                    <Clock className="w-3 h-3 mr-1" />
                    Parado
                  </Badge>
                )}
              </div>
              {scraperStatus.progress && (
                <p className="text-sm text-slate-600 font-mono">
                  {scraperStatus.progress}
                </p>
              )}
              {scraperStatus.started_at && (
                <p className="text-xs text-slate-500 mt-2">
                  Iniciado: {new Date(scraperStatus.started_at).toLocaleString('pt-PT')}
                </p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Scraped Prices */}
      <Card className="border-slate-200">
        <CardHeader>
          <div className="flex items-center justify-between gap-4">
            <div>
              <CardTitle>Preços Obtidos</CardTitle>
              <CardDescription>Preços mais recentes obtidos pelo scraper</CardDescription>
            </div>
            <Input
              value={filterMedida}
              onChange={(e) => setFilterMedida(e.target.value)}
              placeholder="Filtrar por medida (ex: 195/65R15)"
              className="max-w-xs"
            />
          </div>
        </CardHeader>
        <CardContent>
          {Object.keys(pricesByMedida).length > 0 ? (
            <div className="space-y-6">
              {Object.entries(pricesByMedida).map(([medidaKey, prices]) => (
                <div key={medidaKey} className="border border-slate-200 rounded-sm p-4">
                  <h3 className="font-medium text-lg mb-3">
                    Medida: {medidaKey}
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {prices.sort((a, b) => (a.price || 999) - (b.price || 999)).map((price, idx) => (
                      <div
                        key={idx}
                        className={`p-3 rounded-sm border ${
                          idx === 0 && price.price ? 'border-green-300 bg-green-50' : 'border-slate-200 bg-white'
                        }`}
                        data-testid={`price-${price.supplier_name}`}
                      >
                        <div className="flex items-center justify-between mb-2">
                          <span className="font-medium text-sm">{price.supplier_name}</span>
                          {idx === 0 && price.price && (
                            <Badge className="bg-green-600">Melhor</Badge>
                          )}
                        </div>
                        {price.price ? (
                          <p className="text-2xl font-bold font-mono text-green-700">
                            €{price.price.toFixed(2)}
                          </p>
                        ) : (
                          <div className="flex items-center gap-2 text-slate-500">
                            <XCircle className="w-4 h-4" />
                            <span className="text-sm">
                              {price.error || 'Não encontrado'}
                            </span>
                          </div>
                        )}
                        {price.scraped_at && (
                          <p className="text-xs text-slate-500 mt-2">
                            {new Date(price.scraped_at).toLocaleString('pt-PT')}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-12 text-slate-500">
              <Clock className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>Nenhum preço obtido ainda.</p>
              <p className="text-sm mt-2">Execute o scraper para obter preços.</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default ScraperPage;
