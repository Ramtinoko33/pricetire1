-- =============================================================
-- schema.sql — Pneu Price Scout (PostgreSQL)
-- Executado automaticamente ao iniciar o servidor (db.init_schema)
-- =============================================================

-- Fornecedores
CREATE TABLE IF NOT EXISTS suppliers (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    url_login    TEXT NOT NULL,
    url_search   TEXT NOT NULL,
    username     TEXT NOT NULL,
    password     TEXT NOT NULL,
    password_raw TEXT,
    selectors    JSONB    DEFAULT '{}',
    is_active    BOOLEAN  DEFAULT TRUE,
    status       TEXT     DEFAULT 'active',
    last_test    TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Jobs (comparação de preços + fila de scraping do worker)
CREATE TABLE IF NOT EXISTS jobs (
    id               TEXT PRIMARY KEY,
    filename         TEXT,
    status           TEXT    DEFAULT 'pending',
    total_items      INTEGER DEFAULT 0,
    processed_items  INTEGER DEFAULT 0,
    found_items      INTEGER DEFAULT 0,
    matched_items    INTEGER DEFAULT 0,
    total_savings    FLOAT   DEFAULT 0.0,
    threshold_euro   FLOAT   DEFAULT 5.0,
    threshold_percent FLOAT  DEFAULT 10.0,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    finished_at      TIMESTAMPTZ,
    error_message    TEXT,
    last_error       TEXT,
    -- Campos exclusivos dos jobs de scraping (worker)
    type             TEXT,
    supplier_id      TEXT,
    supplier_name    TEXT,
    payload          JSONB,
    attempts         INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_type  ON jobs(status, type);
CREATE INDEX IF NOT EXISTS idx_jobs_type         ON jobs(type);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at   ON jobs(created_at DESC);

-- Itens de cada job (um pneu por linha)
CREATE TABLE IF NOT EXISTS job_items (
    id                 TEXT PRIMARY KEY,
    job_id             TEXT NOT NULL,
    ref_id             TEXT,
    medida             TEXT,
    marca              TEXT,
    modelo             TEXT,
    indice             TEXT,
    meu_preco          FLOAT,
    melhor_preco       FLOAT,
    melhor_fornecedor  TEXT,
    melhor_marca       TEXT,
    modelo_encontrado  TEXT,
    match_type         TEXT,
    economia_euro      FLOAT,
    economia_percent   FLOAT,
    status             TEXT  DEFAULT 'pending',
    supplier_prices    JSONB DEFAULT '{}',
    created_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_items_job_id ON job_items(job_id);
CREATE INDEX IF NOT EXISTS idx_job_items_medida ON job_items(medida);

-- Preços encontrados por fornecedor por item
CREATE TABLE IF NOT EXISTS prices (
    id            TEXT PRIMARY KEY,
    job_id        TEXT,
    item_id       TEXT,
    supplier_id   TEXT,
    supplier_name TEXT,
    price         FLOAT,
    status        TEXT,
    found_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prices_job_id  ON prices(job_id);
CREATE INDEX IF NOT EXISTS idx_prices_item_id ON prices(item_id);

-- Preços raspados em massa pelo scraper (base de comparação)
CREATE TABLE IF NOT EXISTS scraped_prices (
    id            TEXT PRIMARY KEY,
    medida        TEXT,
    marca         TEXT,
    modelo        TEXT,
    price         FLOAT,
    supplier_name TEXT,
    supplier_id   TEXT,
    load_index    TEXT,
    scraped_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scraped_prices_medida ON scraped_prices(medida);
CREATE INDEX IF NOT EXISTS idx_scraped_prices_marca  ON scraped_prices(marca);

-- Logs de operações
CREATE TABLE IF NOT EXISTS logs (
    id              TEXT PRIMARY KEY,
    job_id          TEXT,
    supplier_id     TEXT,
    level           TEXT,
    message         TEXT,
    screenshot_path TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_logs_job_id     ON logs(job_id);
CREATE INDEX IF NOT EXISTS idx_logs_created_at ON logs(created_at DESC);

-- Locks distribuídos para o worker
CREATE TABLE IF NOT EXISTS locks (
    id         TEXT PRIMARY KEY,
    locked     BOOLEAN DEFAULT FALSE,
    expires_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
