"""Migrate Employees -> employees."""
from getpass import getpass
import mysql.connector
from copy_helper import copy_rows
from common import parse_messy_date, reset_identity, QUARANTINE_COLUMNS, connect_pg

BATCH_SIZE = 20_000
COLUMNS = ["emp_id", "ppl_code", "responsibility", "hire_date", "is_active"]


def migrate(my_cur, pg_cur, **_):
    my_cur.execute("SELECT emp_id, ppl_code, responsibility, hire_date, is_active FROM Employees")
    total, quarantined = 0, 0

    while True:
        rows = my_cur.fetchmany(BATCH_SIZE)
        if not rows:
            break
        pg_rows, q_rows = [], []
        for emp_id, ppl_code, responsibility, hire_date_raw, is_active in rows:
            parsed, reason = parse_messy_date(hire_date_raw)
            if reason:
                q_rows.append(("Employees", emp_id, "hire_date", hire_date_raw, reason))
            pg_rows.append((emp_id, ppl_code, responsibility, parsed, bool(is_active)))
        copy_rows(pg_cur, "employees", COLUMNS, pg_rows)
        if q_rows:
            copy_rows(pg_cur, "migration_quarantine", QUARANTINE_COLUMNS, q_rows)
        total += len(rows); quarantined += len(q_rows)
        print(f"  employees: {total} processed, {quarantined} quarantined so far")

    reset_identity(pg_cur, "employees", "emp_id")
    print(f"  employees done: {total} rows, {quarantined} quarantined.")
    return {"total": total, "quarantined": quarantined}


if __name__ == "__main__":
    my_conn = mysql.connector.connect(host="localhost", user="migrator_ro",
        password=getpass("MySQL (migrator_ro) password: "), database="clinicflow_legacy")
    pg_conn = connect_pg()
    migrate(my_conn.cursor(), pg_conn.cursor())
    pg_conn.commit()
    my_conn.close(); pg_conn.close()
