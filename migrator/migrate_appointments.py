"""Migrate Appointments -> appointments. Orphan doc_code/pat_code -> quarantine whole row."""
from getpass import getpass
import mysql.connector
from copy_helper import copy_rows
from common import parse_messy_date, reset_identity, QUARANTINE_COLUMNS, connect_pg

BATCH_SIZE = 20_000
COLUMNS = ["appt_id", "doc_code", "pat_code", "appt_date", "appt_time", "registered_by", "status"]


def migrate(my_cur, pg_cur, **_):
    pg_cur.execute("SELECT doc_id FROM doctors")
    valid_doc_ids = {r[0] for r in pg_cur.fetchall()}
    pg_cur.execute("SELECT pat_id FROM patients")
    valid_pat_ids = {r[0] for r in pg_cur.fetchall()}

    my_cur.execute("SELECT appt_id, doc_code, pat_code, apptDate, apptTime, registered_by, status FROM Appointments")
    total, quarantined = 0, 0

    while True:
        rows = my_cur.fetchmany(BATCH_SIZE)
        if not rows:
            break
        pg_rows, q_rows = [], []
        for appt_id, doc_code, pat_code, appt_date_raw, appt_time, registered_by, status in rows:
            if doc_code not in valid_doc_ids:
                q_rows.append(("Appointments", appt_id, "doc_code", str(doc_code), "references a doctor that does not exist"))
                continue
            if pat_code not in valid_pat_ids:
                q_rows.append(("Appointments", appt_id, "pat_code", str(pat_code), "references a patient that does not exist"))
                continue
            parsed_date, reason = parse_messy_date(appt_date_raw)
            if reason:
                q_rows.append(("Appointments", appt_id, "apptDate", appt_date_raw, reason))
            pg_rows.append((appt_id, doc_code, pat_code, parsed_date, appt_time, registered_by, status))
        if pg_rows:
            copy_rows(pg_cur, "appointments", COLUMNS, pg_rows)
        if q_rows:
            copy_rows(pg_cur, "migration_quarantine", QUARANTINE_COLUMNS, q_rows)
        total += len(rows); quarantined += len(q_rows)
        print(f"  appointments: {total} processed, {quarantined} quarantine entries so far")

    reset_identity(pg_cur, "appointments", "appt_id")
    print(f"  appointments done: {total} rows, {quarantined} quarantine entries.")
    return {"total": total, "quarantined": quarantined}


if __name__ == "__main__":
    my_conn = mysql.connector.connect(host="localhost", user="migrator_ro",
        password=getpass("MySQL (migrator_ro) password: "), database="clinicflow_legacy")
    pg_conn = connect_pg()
    migrate(my_conn.cursor(), pg_conn.cursor())
    pg_conn.commit()
    my_conn.close(); pg_conn.close()
