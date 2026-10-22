from pathlib import Path
from sqlalchemy import text
from app.db import engine


def main():
    with engine.begin() as conn:
        conn.execute(text('SELECT pg_advisory_xact_lock(7349851)'))
        conn.execute(text('CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY)'))
        conn.execute(text('ALTER TABLE schema_migrations ENABLE ROW LEVEL SECURITY'))
        for path in sorted((Path(__file__).parent.parent / 'migrations').glob('*.sql')):
            if not conn.execute(text('SELECT 1 FROM schema_migrations WHERE name=:name'), {'name': path.name}).scalar():
                conn.exec_driver_sql(path.read_text())
                conn.execute(text('INSERT INTO schema_migrations VALUES (:name)'), {'name': path.name})
                print(f'Applied {path.name}')


if __name__ == '__main__':
    main()
