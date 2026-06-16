import sqlite3
c = sqlite3.connect('stock_data.db')
tables = c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print('Tables:', [t[0] for t in tables])
for t in tables:
    cols = c.execute("PRAGMA table_info(%s)" % t[0]).fetchall()
    print(t[0], ':', [col[1] for col in cols])
cur = c.execute("SELECT * FROM market_data LIMIT 1")
cols = [d[0] for d in cur.description]
row = cur.fetchone()
if row:
    for k, v in zip(cols, row):
        print(f"  {k}: {v}")
c.close()
