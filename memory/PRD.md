# Pneu Price Scout - PRD

## Problema Original
O utilizador pretende criar uma aplicação para pesquisar automaticamente os preços de pneus nos websites B2B dos seus fornecedores.

### Requisitos Principais
1. **Entrada**: Carregar ficheiro Excel com detalhes dos pneus (marca, medida, modelo) e o preço de custo atual
2. **Processo**: Iniciar sessão nos websites de múltiplos fornecedores, procurar os pneus listados e comparar preços
3. **Saída**: Identificar se algum fornecedor oferece preço mais baixo e gerar relatório com o fornecedor e a poupança

## O Que Foi Implementado

### Sessão 25/02/2026 - FINAL

#### 1. Scrapers Actualizados com Extração de Marca/Modelo
- **MP24**: Usa API interception para extrair todos os produtos (~800 por medida)
- **Prismanil**: Extrai de atributos `data-produto` e `data-preco` (~30-50 por medida)
- **Dispnal**: Extrai de `.prod-list-row` e `.prod-list-brand-wrapper img[alt]` (~20-50 por medida)

#### 2. Scraping Completo de Todas as Medidas do Excel
Medidas scrapedas: 1955516, 1956515, 2055516, 2056016, 2155517, 2254018, 2254517, 2354518, 2454019, 2553519

**Total: 1111 produtos com marca/modelo**
- MP24: 886 produtos
- Prismanil: 122 produtos  
- Dispnal: 101 produtos

#### 3. Comparação por MEDIDA + MARCA
- **100% match exacto** - todos os 30 items do Excel encontraram correspondência exacta
- **€1063.77 de economia total** identificada
- **25 items com preço mais baixo** nos fornecedores

### Arquitectura Final

```
/app/backend/
├── server.py          # API REST FastAPI
├── worker.py          # Processo de scraping em background
├── run_scraper.py     # Lógica de scraping com extração de marca/modelo
│   ├── scrape_mp24()       # API interception
│   ├── scrape_prismanil()  # data-* attributes
│   └── scrape_dispnal()    # DOM extraction

/app/frontend/
├── pages/
│   ├── Results.jsx    # Comparação e economia
│   ├── Suppliers.jsx  # Gestão + Seletores CSS
│   └── Scraper.jsx    # Interface de scraping manual
```

### Schema scraped_prices
```json
{
  "supplier_name": "MP24",
  "medida": "2055516",
  "marca": "MICHELIN",
  "modelo": "PRIMACY 4",
  "price": 67.75,
  "scraped_at": "2026-02-25T00:00:00Z"
}
```

### Schema job_items (após comparação)
```json
{
  "medida": "2055516",
  "marca": "Michelin",
  "meu_preco": 118.21,
  "melhor_preco": 97.76,
  "melhor_fornecedor": "MP24",
  "melhor_marca": "MICHELIN",
  "match_type": "exact",
  "economia_euro": 20.45,
  "economia_percent": 17.3
}
```

## Resultados Demonstrados
- Upload de Excel com 30 pneus
- Scraping de 3 fornecedores (MP24, Prismanil, Dispnal)
- 1111 produtos extraídos com marca/modelo
- 100% de matches exactos na comparação
- €1063.77 de economia potencial identificada

## Backlog

### P1 (Prioritário)
- [ ] Corrigir scrapers S. José e Euromais

### P2 (Melhorias)
- [ ] Cronjob para scraping periódico automático
- [ ] Barra de progresso real-time
- [ ] Usar seletores CSS configurados na UI

### P3 (Futuro)
- [ ] Adicionar mais fornecedores
- [ ] Histórico de preços
- [ ] Alertas de variação de preço
