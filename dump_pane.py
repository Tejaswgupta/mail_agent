import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        # connect to the running browser if possible? No, we don't have remote debugging port.
        pass

if __name__ == "__main__":
    asyncio.run(main())
