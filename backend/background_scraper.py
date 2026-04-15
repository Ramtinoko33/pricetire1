#!/usr/bin/env python3
"""
Background scraper runner - uses file-based communication
"""
import asyncio
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, '/app/backend')
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/pw-browsers'

# Import scraper functions
from isolated_scraper import (
    scrape_mp24, scrape_prismanil, scrape_dispnal,
    scrape_sjose, scrape_euromais, scrape_tugapneus
)

async def run_scraper(config_file: str, result_file: str):
    """Run scraper and save result to file"""
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    supplier = config.get('supplier', '').lower()
    username = config.get('username', '')
    password = config.get('password', '')
    medida = config.get('medida', '')
    
    if 'mp24' in supplier:
        result = await scrape_mp24(username, password, medida)
    elif 'prismanil' in supplier:
        result = await scrape_prismanil(username, password, medida)
    elif 'dispnal' in supplier:
        result = await scrape_dispnal(username, password, medida)
    elif 'sjose' in supplier or 'josé' in supplier:
        result = await scrape_sjose(username, password, medida)
    elif 'euromais' in supplier or 'eurotyre' in supplier:
        result = await scrape_euromais(username, password, medida)
    elif 'tugapneus' in supplier or 'tuga' in supplier:
        result = await scrape_tugapneus(username, password, medida)
    else:
        result = {"supplier": supplier, "price": None, "error": f"Unknown supplier: {supplier}"}
    
    with open(result_file, 'w') as f:
        json.dump(result, f)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: background_scraper.py <config_file> <result_file>")
        sys.exit(1)
    
    asyncio.run(run_scraper(sys.argv[1], sys.argv[2]))
