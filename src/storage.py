"""Base ligera (SQLite) para alertas y acciones."""
import sqlite3
from pathlib import Path


def save(db_path, **tables):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        for name, df in tables.items():
            df.to_sql(name, con, if_exists="replace", index=False)
    finally:
        con.close()
