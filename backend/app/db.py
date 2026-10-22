from sqlalchemy import create_engine, text
from app.config import settings

url = settings.database_url
if url.startswith('postgres://'):
    url = url.replace('postgres://', 'postgresql+psycopg://', 1)
elif url.startswith('postgresql://'):
    url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
engine = create_engine(url, pool_pre_ping=True)


def rows(sql, params=None):
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(text(sql), params or {}).mappings()]


def execute(sql, params=None):
    with engine.begin() as conn:
        result = conn.execute(text(sql), params or {})
        return [dict(row) for row in result.mappings()] if result.returns_rows else []


def snapshot():
    return rows('SELECT * FROM members ORDER BY id'), rows('SELECT * FROM interactions ORDER BY id')
