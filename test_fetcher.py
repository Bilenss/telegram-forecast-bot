import asyncio
from app.data_sources.fetchers import CompositeFetcher

async def main():
    cf = CompositeFetcher()
    df = await cf.fetch("EURUSD", "5m", otc=False)
    print("Rows:", len(df))
    print(df.head().to_dict(orient="records"))

asyncio.run(main())
