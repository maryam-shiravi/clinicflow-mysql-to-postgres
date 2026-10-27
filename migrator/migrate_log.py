"""Migrate Log -> log. changed_at gets labeled with source_tz (not converted)."""
from getpass import getpass
import mysql.connector
from copy_helper import copy_rows
from common import reset_identity, QUARANTINE_COLUMNS, connect_pg
from zoneinfo import ZoneInfo

BATCH_SIZE = 20_000
COLUMNS = ["log_id", "table_name", "record_id", "action_type", "changed_by", "changed_at"]


def migrate(my_cur, pg_cur, source_tz="Europe/Lisbon", **_):
    tz = ZoneInfo(source_tz)
    my_cur.execute("SELECT log_id, table_name, record_id, action_type, changed_by, changed_at FROM Log")
    total = 0

    while True:
        rows = my_cur.fetchmany(BATCH_SIZE)
        if not rows:
            break
        pg_rows = []
        for log_id, table_name, record_id, action_type, changed_by, changed_at_raw in rows:
            changed_at = changed_at_raw.replace(tzinfo=tz) if changed_at_raw else None
            pg_rows.append((log_id, table_name, record_id, action_type, changed_by, changed_at))
        copy_rows(pg_cur, "log", COLUMNS, pg_rows)
        total += len(rows)
        print(f"  log: {total} processed")

    reset_identity(pg_cur, "log", "log_id")
    print(f"  log done: {total} rows.")
    return {"total": total, "quarantined": 0}


if __name__ == "__main__":
    my_conn = mysql.connector.connect(host="localhost", user="migrator_ro",
        password=getpass("MySQL (migrator_ro) password: "), database="clinicflow_legacy")
    pg_conn = connect_pg()
    migrate(my_conn.cursor(), pg_conn.cursor())
    pg_conn.commit()
    my_conn.close(); pg_conn.close()
