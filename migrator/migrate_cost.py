"""Migrate Costs -> costs. pat_code required -> quarantine row. appt_code optional -> null link."""
from getpass import getpass
import mysql.connector
from copy_helper import copy_rows
from common import parse_messy_date, reset_identity, QUARANTINE_COLUMNS, connect_pg

BATCH_SIZE = 20_000
COLUMNS = ["cost_id", "pat_code", "appt_code", "category", "amount", "is_paid", "cost_date", "description"]


def migrate(my_cur, pg_cur, **_):
    pg_cur.execute("SELECT pat_id FROM patients")
    valid_pat_ids = {r[0] for r in pg_cur.fetchall()}
    pg_cur.execute("SELECT appt_id FROM appointments")
    valid_appt_ids = {r[0] for r in pg_cur.fetchall()}

    my_cur.execute("SELECT cost_id, pat_code, appt_code, category, amount, is_paid, cost_date, description FROM Costs")
    total, quarantined, nulled = 0, 0, 0

    while True:
        rows = my_cur.fetchmany(BATCH_SIZE)
        if not rows:
            break
        pg_rows, q_rows = [], []
        for cost_id, pat_code, appt_code, category, amount, is_paid, cost_date_raw, description in rows:
            if pat_code not in valid_pat_ids:
                q_rows.append(("Costs", cost_id, "pat_code", str(pat_code), "references a patient that does not exist"))
                quarantined += 1
                continue
            if appt_code is not None and appt_code not in valid_appt_ids:
                q_rows.append(("Costs", cost_id, "appt_code", str(appt_code), "referenced appointment does not exist; link set to NULL"))
                appt_code = None
                nulled += 1
            parsed_date, reason = parse_messy_date(cost_date_raw)
            if reason:
                q_rows.append(("Costs", cost_id, "cost_date", cost_date_raw, reason))
            pg_rows.append((cost_id, pat_code, appt_code, category, amount, bool(is_paid), parsed_date, description))
        if pg_rows:
            copy_rows(pg_cur, "costs", COLUMNS, pg_rows)
        if q_rows:
            copy_rows(pg_cur, "migration_quarantine", QUARANTINE_COLUMNS, q_rows)
        total += len(rows)
        print(f"  costs: {total} processed")

    reset_identity(pg_cur, "costs", "cost_id")
    print(f"  costs done: {total} rows, {quarantined} quarantined, {nulled} appt links nulled.")
    return {"total": total, "quarantined": quarantined, "nulled": nulled}


if __name__ == "__main__":
    my_conn = mysql.connector.connect(host="localhost", user="migrator_ro",
        password=getpass("MySQL (migrator_ro) password: "), database="clinicflow_legacy")
    pg_conn = connect_pg()
    migrate(my_conn.cursor(), pg_conn.cursor())
    pg_conn.commit()
    my_conn.close(); pg_conn.close()
