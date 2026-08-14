from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if Path(".env").exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(".env"))
    except Exception:
        pass

import httpx


async def main():
    urls = [
        "https://source.unsplash.com/random/900x600/?senegal,dakar&sig=1",
        "https://source.unsplash.com/random/900x600/?senegal&sig=2",
        "https://images.unsplash.com/photo-1523805009345-7448845a9e53?w=900&q=80",
    ]
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/127.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/jpeg,image/png,image/*,*/*;q=0.8",
        "Accept-Language": "fr,en;q=0.9",
    }
    async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(40), http2=False, headers=headers) as c:
        for u in urls:
            try:
                resp = await c.get(u)
                ct = resp.headers.get("Content-Type", "")
                print(f"URL {u}")
                print(f"  status={resp.status_code} len={len(resp.content)} ct={ct}")
                try:
                    print(f"  final_url={resp.url}")
                except Exception as e:
                    print(f"  final_url err={e}")
                if len(resp.content) > 10:
                    print(f"  first bytes: {resp.content[:20]!r}")
            except Exception as e:
                print(f"URL {u} EXC: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
