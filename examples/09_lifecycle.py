import asyncio
from contextlib import asynccontextmanager

@asynccontextmanager
async def demo_room():
    print("进入：开门")
    try:
        yield "一张桌子"
    finally:
        print("退出：关门")

async def demo():
    async with demo_room() as desk:
        print("使用期间：", desk)

asyncio.run(demo())
