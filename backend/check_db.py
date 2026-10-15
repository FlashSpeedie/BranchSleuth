from app.db.session import get_engine
from sqlalchemy import text

e = get_engine()
c = e.connect()
rows = c.execute(text("select table_name from information_schema.tables where table_schema='public' order by 1")).fetchall()
for r in rows:
    print(r[0])
print("---")
print("alembic:", c.execute(text("select version_num from alembic_version")).fetchall())
c.close()