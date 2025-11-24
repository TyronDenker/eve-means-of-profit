"""SQLite database schemas for historical asset and price tracking.

This module defines the SQL table schemas used to track:
1. Asset snapshots and their history (delta-based to save space)
2. Historical market prices from Fuzzwork (Jita buy/sell prices)
"""

from __future__ import annotations

# Asset tracking tables
CREATE_ASSET_SNAPSHOTS_TABLE = """
CREATE TABLE IF NOT EXISTS asset_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL,
    snapshot_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_items INTEGER NOT NULL,
    notes TEXT,
    UNIQUE(character_id, snapshot_time)
);
"""

CREATE_ASSET_SNAPSHOTS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_asset_snapshots_character_time
ON asset_snapshots(character_id, snapshot_time DESC);
"""

CREATE_CURRENT_ASSETS_TABLE = """
CREATE TABLE IF NOT EXISTS current_assets (
    character_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    type_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    location_id INTEGER NOT NULL,
    location_type TEXT NOT NULL,
    location_flag TEXT NOT NULL,
    is_singleton INTEGER NOT NULL,
    is_blueprint_copy INTEGER,
    last_updated TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (character_id, item_id)
);
"""

CREATE_CURRENT_ASSETS_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_current_assets_character
ON current_assets(character_id);

CREATE INDEX IF NOT EXISTS idx_current_assets_type
ON current_assets(type_id);

CREATE INDEX IF NOT EXISTS idx_current_assets_location
ON current_assets(location_id);
"""

CREATE_ASSET_CHANGES_TABLE = """
CREATE TABLE IF NOT EXISTS asset_changes (
    change_id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL,
    character_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    type_id INTEGER NOT NULL,
    change_type TEXT NOT NULL CHECK(change_type IN ('added', 'removed', 'modified')),
    old_quantity INTEGER,
    new_quantity INTEGER,
    old_location_id INTEGER,
    new_location_id INTEGER,
    old_location_flag TEXT,
    new_location_flag TEXT,
    change_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (snapshot_id) REFERENCES asset_snapshots(snapshot_id) ON DELETE CASCADE
);
"""

CREATE_ASSET_CHANGES_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_asset_changes_snapshot
ON asset_changes(snapshot_id);

CREATE INDEX IF NOT EXISTS idx_asset_changes_character
ON asset_changes(character_id);

CREATE INDEX IF NOT EXISTS idx_asset_changes_type
ON asset_changes(type_id);

CREATE INDEX IF NOT EXISTS idx_asset_changes_time
ON asset_changes(change_time DESC);
"""

# Market price history tables
CREATE_PRICE_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS price_history (
    price_id INTEGER PRIMARY KEY AUTOINCREMENT,
    type_id INTEGER NOT NULL,
    region_id INTEGER NOT NULL,
    snapshot_id INTEGER NOT NULL,

    -- Buy order statistics
    buy_weighted_average REAL,
    buy_max_price REAL,
    buy_min_price REAL,
    buy_stddev REAL,
    buy_median REAL,
    buy_volume INTEGER,
    buy_num_orders INTEGER,
    buy_five_percent REAL,

    -- Sell order statistics
    sell_weighted_average REAL,
    sell_max_price REAL,
    sell_min_price REAL,
    sell_stddev REAL,
    sell_median REAL,
    sell_volume INTEGER,
    sell_num_orders INTEGER,
    sell_five_percent REAL,

    -- Custom price override (if user has set one at snapshot time)
    custom_buy_price REAL,
    custom_sell_price REAL,

    UNIQUE(type_id, region_id, snapshot_id),
    FOREIGN KEY (snapshot_id) REFERENCES price_snapshots(snapshot_id) ON DELETE CASCADE
);
"""

CREATE_PRICE_HISTORY_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_price_history_type_region
ON price_history(type_id, region_id, snapshot_id DESC);

CREATE INDEX IF NOT EXISTS idx_price_history_type
ON price_history(type_id, snapshot_id DESC);

CREATE INDEX IF NOT EXISTS idx_price_history_region
ON price_history(region_id, snapshot_id DESC);

CREATE INDEX IF NOT EXISTS idx_price_history_snapshot
ON price_history(snapshot_id DESC);
"""

CREATE_PRICE_SNAPSHOTS_TABLE = """
CREATE TABLE IF NOT EXISTS price_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL DEFAULT 'fuzzwork',
    total_items INTEGER NOT NULL,
    notes TEXT,
    UNIQUE(snapshot_time, source)
);
"""

CREATE_PRICE_SNAPSHOTS_INDEX = """
CREATE INDEX IF NOT EXISTS idx_price_snapshots_time
ON price_snapshots(snapshot_time DESC);
"""

CREATE_CUSTOM_PRICES_TABLE = """
CREATE TABLE IF NOT EXISTS custom_price_overrides (
    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL,
    type_id INTEGER NOT NULL,
    custom_buy_price REAL,
    custom_sell_price REAL,
    UNIQUE(snapshot_id, type_id),
    FOREIGN KEY (snapshot_id) REFERENCES price_snapshots(snapshot_id) ON DELETE CASCADE
);
"""

CREATE_CUSTOM_PRICES_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_custom_prices_snapshot
ON custom_price_overrides(snapshot_id DESC);

CREATE INDEX IF NOT EXISTS idx_custom_prices_type
ON custom_price_overrides(type_id);
"""

# Wallet transactions tables
CREATE_WALLET_TRANSACTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS wallet_transactions (
    transaction_id INTEGER PRIMARY KEY,
    character_id INTEGER NOT NULL,
    date TIMESTAMP NOT NULL,
    type_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    client_id INTEGER NOT NULL,
    location_id INTEGER NOT NULL,
    is_buy INTEGER NOT NULL,
    is_personal INTEGER NOT NULL,
    journal_ref_id INTEGER
);
"""

CREATE_WALLET_TRANSACTIONS_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_transactions_character_date
ON wallet_transactions(character_id, date DESC);

CREATE INDEX IF NOT EXISTS idx_transactions_type
ON wallet_transactions(type_id);
"""

# Wallet journal tables
CREATE_WALLET_JOURNAL_TABLE = """
CREATE TABLE IF NOT EXISTS wallet_journal (
    entry_id INTEGER PRIMARY KEY,
    character_id INTEGER NOT NULL,
    date TIMESTAMP NOT NULL,
    ref_type TEXT NOT NULL,
    first_party_id INTEGER NOT NULL,
    second_party_id INTEGER,
    amount REAL NOT NULL,
    balance REAL NOT NULL,
    reason TEXT,
    description TEXT,
    context_id INTEGER,
    context_id_type TEXT
);
"""

CREATE_WALLET_JOURNAL_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_journal_character_date
ON wallet_journal(character_id, date DESC);

CREATE INDEX IF NOT EXISTS idx_journal_ref_type
ON wallet_journal(ref_type);
"""

# Market orders tables
CREATE_MARKET_ORDERS_TABLE = """
CREATE TABLE IF NOT EXISTS market_orders (
    order_id INTEGER PRIMARY KEY,
    character_id INTEGER NOT NULL,
    type_id INTEGER NOT NULL,
    location_id INTEGER NOT NULL,
    volume_total INTEGER NOT NULL,
    volume_remain INTEGER NOT NULL,
    min_volume INTEGER NOT NULL,
    price REAL NOT NULL,
    is_buy_order INTEGER NOT NULL,
    duration INTEGER NOT NULL,
    issued TIMESTAMP NOT NULL,
    range TEXT NOT NULL,
    state TEXT NOT NULL,
    region_id INTEGER NOT NULL,
    is_corporation INTEGER NOT NULL,
    escrow REAL,
    last_updated TIMESTAMP NOT NULL
);
"""

CREATE_MARKET_ORDERS_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_orders_character_state
ON market_orders(character_id, state);

CREATE INDEX IF NOT EXISTS idx_orders_type
ON market_orders(type_id);

CREATE INDEX IF NOT EXISTS idx_orders_issued
ON market_orders(issued DESC);
"""

# Contracts tables
CREATE_CONTRACTS_TABLE = """
CREATE TABLE IF NOT EXISTS contracts (
    contract_id INTEGER PRIMARY KEY,
    character_id INTEGER NOT NULL,
    issuer_id INTEGER NOT NULL,
    issuer_corporation_id INTEGER NOT NULL,
    assignee_id INTEGER NOT NULL,
    acceptor_id INTEGER NOT NULL,
    start_location_id INTEGER NOT NULL,
    end_location_id INTEGER,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    title TEXT,
    for_corporation INTEGER NOT NULL,
    availability TEXT NOT NULL,
    date_issued TIMESTAMP NOT NULL,
    date_expired TIMESTAMP NOT NULL,
    date_accepted TIMESTAMP,
    date_completed TIMESTAMP,
    days_to_complete INTEGER,
    price REAL,
    reward REAL,
    collateral REAL,
    buyout REAL,
    volume REAL
);
"""

CREATE_CONTRACTS_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_contracts_character_status
ON contracts(character_id, status);

CREATE INDEX IF NOT EXISTS idx_contracts_date_issued
ON contracts(date_issued DESC);
"""

CREATE_CONTRACT_ITEMS_TABLE = """
CREATE TABLE IF NOT EXISTS contract_items (
    record_id INTEGER PRIMARY KEY,
    contract_id INTEGER NOT NULL,
    type_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    is_included INTEGER NOT NULL,
    is_singleton INTEGER NOT NULL,
    FOREIGN KEY (contract_id) REFERENCES contracts(contract_id) ON DELETE CASCADE
);
"""

CREATE_CONTRACT_ITEMS_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_contract_items_contract
ON contract_items(contract_id);

CREATE INDEX IF NOT EXISTS idx_contract_items_type
ON contract_items(type_id);
"""

# Industry jobs tables
CREATE_INDUSTRY_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS industry_jobs (
    job_id INTEGER PRIMARY KEY,
    character_id INTEGER NOT NULL,
    installer_id INTEGER NOT NULL,
    facility_id INTEGER NOT NULL,
    activity_id INTEGER NOT NULL,
    blueprint_id INTEGER NOT NULL,
    blueprint_type_id INTEGER NOT NULL,
    blueprint_location_id INTEGER NOT NULL,
    output_location_id INTEGER NOT NULL,
    runs INTEGER NOT NULL,
    cost REAL NOT NULL,
    licensed_runs INTEGER,
    probability REAL,
    product_type_id INTEGER,
    status TEXT NOT NULL,
    duration INTEGER NOT NULL,
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    pause_date TIMESTAMP,
    completed_date TIMESTAMP,
    completed_character_id INTEGER,
    successful_runs INTEGER,
    last_updated TIMESTAMP NOT NULL
);
"""

CREATE_INDUSTRY_JOBS_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_industry_jobs_character_status
ON industry_jobs(character_id, status);

CREATE INDEX IF NOT EXISTS idx_industry_jobs_activity
ON industry_jobs(activity_id);

CREATE INDEX IF NOT EXISTS idx_industry_jobs_end_date
ON industry_jobs(end_date);
"""

# Net worth tracking tables
CREATE_NETWORTH_SNAPSHOTS_TABLE = """
CREATE TABLE IF NOT EXISTS networth_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    character_id INTEGER NOT NULL,
    snapshot_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_asset_value REAL NOT NULL DEFAULT 0,
    hangar_value REAL NOT NULL DEFAULT 0,
    ship_value REAL NOT NULL DEFAULT 0,
    wallet_balance REAL NOT NULL DEFAULT 0,
    market_escrow REAL NOT NULL DEFAULT 0,
    market_sell_value REAL NOT NULL DEFAULT 0,
    contract_collateral REAL NOT NULL DEFAULT 0,
    contract_value REAL NOT NULL DEFAULT 0,
    industry_job_value REAL NOT NULL DEFAULT 0,
    total_liquid REAL NOT NULL DEFAULT 0,
    total_net_worth REAL NOT NULL DEFAULT 0
);
"""

CREATE_NETWORTH_SNAPSHOTS_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_networth_character_time
ON networth_snapshots(character_id, snapshot_time DESC);
"""

CREATE_NETWORTH_COMPONENTS_TABLE = """
CREATE TABLE IF NOT EXISTS networth_components (
    component_id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id INTEGER NOT NULL,
    character_id INTEGER NOT NULL,
    component_type TEXT NOT NULL CHECK(component_type IN ('asset', 'wallet', 'order', 'contract', 'job')),
    component_ref_id INTEGER,
    type_id INTEGER,
    quantity INTEGER NOT NULL DEFAULT 0,
    unit_value REAL NOT NULL DEFAULT 0,
    total_value REAL NOT NULL DEFAULT 0,
    notes TEXT,
    FOREIGN KEY (snapshot_id) REFERENCES networth_snapshots(snapshot_id) ON DELETE CASCADE
);
"""

CREATE_NETWORTH_COMPONENTS_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_networth_components_snapshot
ON networth_components(snapshot_id);

CREATE INDEX IF NOT EXISTS idx_networth_components_type
ON networth_components(component_type);
"""

# All table creation statements in order
ALL_TABLES = [
    CREATE_ASSET_SNAPSHOTS_TABLE,
    CREATE_ASSET_SNAPSHOTS_INDEX,
    CREATE_CURRENT_ASSETS_TABLE,
    CREATE_CURRENT_ASSETS_INDEXES,
    CREATE_ASSET_CHANGES_TABLE,
    CREATE_ASSET_CHANGES_INDEXES,
    CREATE_PRICE_HISTORY_TABLE,
    CREATE_PRICE_HISTORY_INDEXES,
    CREATE_PRICE_SNAPSHOTS_TABLE,
    CREATE_PRICE_SNAPSHOTS_INDEX,
    CREATE_CUSTOM_PRICES_TABLE,
    CREATE_CUSTOM_PRICES_INDEXES,
    CREATE_WALLET_TRANSACTIONS_TABLE,
    CREATE_WALLET_TRANSACTIONS_INDEXES,
    CREATE_WALLET_JOURNAL_TABLE,
    CREATE_WALLET_JOURNAL_INDEXES,
    CREATE_MARKET_ORDERS_TABLE,
    CREATE_MARKET_ORDERS_INDEXES,
    CREATE_CONTRACTS_TABLE,
    CREATE_CONTRACTS_INDEXES,
    CREATE_CONTRACT_ITEMS_TABLE,
    CREATE_CONTRACT_ITEMS_INDEXES,
    CREATE_INDUSTRY_JOBS_TABLE,
    CREATE_INDUSTRY_JOBS_INDEXES,
    CREATE_NETWORTH_SNAPSHOTS_TABLE,
    CREATE_NETWORTH_SNAPSHOTS_INDEXES,
    CREATE_NETWORTH_COMPONENTS_TABLE,
    CREATE_NETWORTH_COMPONENTS_INDEXES,
]

__all__ = [
    "ALL_TABLES",
    "CREATE_ASSET_CHANGES_INDEXES",
    "CREATE_ASSET_CHANGES_TABLE",
    "CREATE_ASSET_SNAPSHOTS_INDEX",
    "CREATE_ASSET_SNAPSHOTS_TABLE",
    "CREATE_CURRENT_ASSETS_INDEXES",
    "CREATE_CURRENT_ASSETS_TABLE",
    "CREATE_PRICE_HISTORY_INDEXES",
    "CREATE_PRICE_HISTORY_TABLE",
    "CREATE_PRICE_SNAPSHOTS_INDEX",
    "CREATE_PRICE_SNAPSHOTS_TABLE",
]
