"""
Phase 2, Step 3: connect to the legacy MySQL source (read-only) and print
its full schema — every table, column, type, nullability, and key info —
pulled from information_schema rather than hand-typed.
"""
from getpass import getpass
import mysql.connector

conn = mysql.connector.connect(
    host="localhost",
    user="migrator_ro",
    password=getpass("MySQL (migrator_ro) password: "),
    database="clinicflow_legacy",
)
cur = conn.cursor()

cur.execute("""
    SELECT table_name, column_name, data_type, is_nullable,
           character_maximum_length, numeric_precision, numeric_scale,
           column_key, column_default, extra
    FROM information_schema.columns
    WHERE table_schema = 'clinicflow_legacy'
    ORDER BY table_name, ordinal_position;
""")

rows = cur.fetchall()

current_table = None
for (table_name, col_name, data_type, is_nullable,
     max_len, num_prec, num_scale,
     col_key, col_default, extra) in rows:
    if table_name != current_table:
        print(f"\n=== {table_name} ===")
        current_table = table_name
    key_flag = f" [{col_key}]" if col_key else ""
    if max_len:
        size_flag = f"({max_len})"
    elif num_prec:
        size_flag = f"({num_prec},{num_scale})"
    else:
        size_flag = ""
    extra_flag = f" {extra}" if extra else ""
    print(f"  {col_name:<20} {data_type}{size_flag:<10} "
          f"null={is_nullable}{key_flag}{extra_flag}")
cur.close()
conn.close()
