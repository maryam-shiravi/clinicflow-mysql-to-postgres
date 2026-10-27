"""Migrate People -> people."""
from getpass import getpass
import mysql.connector
from copy_helper import copy_rows
from common import parse_messy_date, reset_identity, QUARANTINE_COLUMNS, connect_pg

BATCH_SIZE = 20_000
COLUMNS = ["ppl_id", "first_name", "last_name", "birth_date", "address", "phone"]


def migrate(my_cur, pg_cur, **_):
    my_cur.execute("SELECT ppl_id, firstName, last_name, birth_date, address, phone FROM People")
    total, quarantined = 0, 0

    while True:
        rows = my_cur.fetchmany(BATCH_SIZE)
        if not rows:
            break
        pg_rows, q_rows = [], []
        for ppl_id, first_name, last_name, birth_date_raw, address, phone in rows:
            parsed, reason = parse_messy_date(birth_date_raw)
            if reason:
                q_rows.append(("People", ppl_id, "birth_date", birth_date_raw, reason))
            pg_rows.append((ppl_id, first_name, last_name, parsed, address, phone))
        copy_rows(pg_cur, "people", COLUMNS, pg_rows)
        if q_rows:
            copy_rows(pg_cur, "migration_quarantine", QUARANTINE_COLUMNS, q_rows)
        total += len(rows); quarantined += len(q_rows)
        print(f"  people: {total} processed, {quarantined} quarantined so far")

    reset_identity(pg_cur, "people", "ppl_id")
    print(f"  people done: {total} rows, {quarantined} quarantined.")
    return {"total": total, "quarantined": quarantined}


if __name__ == "__main__":
    my_conn = mysql.connector.connect(host="localhost", user="migrator_ro",
        password=getpass("MySQL (migrator_ro) password: "), database="clinicflow_legacy")
    pg_conn = connect_pg()
    migrate(my_conn.cursor(), pg_conn.cursor())
    pg_conn.commit()
    my_conn.close(); pg_conn.close()
