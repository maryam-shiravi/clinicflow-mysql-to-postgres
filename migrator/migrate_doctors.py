"""Migrate Doctors -> doctors. No dates, no booleans."""
from getpass import getpass
import mysql.connector
from copy_helper import copy_rows
from common import reset_identity, QUARANTINE_COLUMNS, connect_pg

BATCH_SIZE = 20_000
COLUMNS = ["doc_id", "emp_code", "specialty", "license_no"]


def migrate(my_cur, pg_cur, **_):
    my_cur.execute("SELECT doc_id, emp_code, specialty, license_no FROM Doctors")
    total = 0

    while True:
        rows = my_cur.fetchmany(BATCH_SIZE)
        if not rows:
            break
        copy_rows(pg_cur, "doctors", COLUMNS, rows)
        total += len(rows)
        print(f"  doctors: {total} processed")

    reset_identity(pg_cur, "doctors", "doc_id")
    print(f"  doctors done: {total} rows.")
    return {"total": total, "quarantined": 0}


if __name__ == "__main__":
    my_conn = mysql.connector.connect(host="localhost", user="migrator_ro",
        password=getpass("MySQL (migrator_ro) password: "), database="clinicflow_legacy")
    pg_conn = connect_pg()
    migrate(my_conn.cursor(), pg_conn.cursor())
    pg_conn.commit()
    my_conn.close(); pg_conn.close()
