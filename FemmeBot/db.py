import asyncpg
import os

DATABASE_URL = os.getenv("DATABASE_URL")

async def connect_db():
    return await asyncpg.connect(DATABASE_URL)

async def get_user_level(user_id):
    conn = await connect_db()
    row = await conn.fetchrow("SELECT level FROM user_levels WHERE user_id = $1;", str(user_id))
    await conn.close()
    return row["level"] if row else 0

async def set_user_level(user_id, level):
    conn = await connect_db()
    await conn.execute("""
        INSERT INTO user_levels (user_id, level, xp)
        VALUES ($1, $2, 0)
        ON CONFLICT (user_id) DO UPDATE SET level = $2;
    """, str(user_id), level)
    await conn.close()

async def add_xp(user_id, amount):
    conn = await connect_db()
    await conn.execute("""
        INSERT INTO user_levels (user_id, xp, level)
        VALUES ($1, $2, 0)
        ON CONFLICT (user_id) DO UPDATE SET xp = user_levels.xp + $2;
    """, str(user_id), amount)
    await conn.close()
