import asyncio
from app.data_sources.fetchers import CompositeFetcher
import logging

logging.basicConfig(level=logging.DEBUG)

async def main():
    cf = CompositeFetcher()
    df, source = await cf.fetch("EURUSD", "5m", otc=False)
    print("Source:", source)
    print("Rows:", len(df))
    print(df.head().to_dict(orient="records"))

asyncio.run(main())
