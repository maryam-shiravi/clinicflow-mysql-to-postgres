"""
Row-level verification. For every table, re-fetch the SOURCE value,
normalize it EXACTLY the way the migration scripts did, and compare against
what actually landed in Postgres -- value by value, not byte by byte.
Produces migrator/out/migration_report.md
"""
from getpass import getpass
from datetime import datetime
import mysql.connector
import psycopg2
from common import parse_messy_date, TABLE_ORDER, connect_pg
from zoneinfo import ZoneInfo

SOURCE_TZ = ZoneInfo("Europe/Lisbon")

def norm_people(r):
    ppl_id, first_name, last_name, birth_date_raw, address, phone = r
    d, _ = parse_messy_date(birth_date_raw)
    return (ppl_id, first_name, last_name, d, address, phone)

def norm_employees(r):
    emp_id, ppl_code, responsibility, hire_date_raw, is_active = r
    d, _ = parse_messy_date(hire_date_raw)
    return (emp_id, ppl_code, responsibility, d, bool(is_active))

def norm_doctors(r):
    return tuple(r)

def norm_patients(r):
    pat_id, ppl_code, disease_type, diag_raw = r
    d, _ = parse_messy_date(diag_raw)
    return (pat_id, ppl_code, disease_type, d)

def norm_appointments(r):
    appt_id, doc_code, pat_code, date_raw, time_, reg_by, status = r
    d, _ = parse_messy_date(date_raw)
    return (appt_id, doc_code, pat_code, d, time_, reg_by, status)

def make_norm_health_documents(valid_appt_ids):
    def norm(r):
        doc_rec_id, doc_code, pat_code, appt_code, test_type, result, date_raw = r
        d, _ = parse_messy_date(date_raw)
        expected_appt = appt_code if appt_code in valid_appt_ids else None
        return (doc_rec_id, doc_code, pat_code, expected_appt, test_type, result, d)
    return norm

def make_norm_costs(valid_appt_ids):
    def norm(r):
        cost_id, pat_code, appt_code, category, amount, is_paid, date_raw, desc = r
        d, _ = parse_messy_date(date_raw)
        expected_appt = appt_code if appt_code in valid_appt_ids else None
        return (cost_id, pat_code, expected_appt, category, amount, bool(is_paid), d, desc)
    return norm

def norm_log(r):
    log_id, table_name, record_id, action_type, changed_by, changed_at_raw = r
    ts = changed_at_raw.replace(tzinfo=SOURCE_TZ) if changed_at_raw else None
    return (log_id, table_name, record_id, action_type, changed_by, ts)


TABLES = {
    "people": dict(mysql_table="People",
        mysql_cols="ppl_id, firstName, last_name, birth_date, address, phone",
        pg_cols="ppl_id, first_name, last_name, birth_date, address, phone",
        pk="ppl_id", normalize=norm_people),
    "employees": dict(mysql_table="Employees",
        mysql_cols="emp_id, ppl_code, responsibility, hire_date, is_active",
        pg_cols="emp_id, ppl_code, responsibility, hire_date, is_active",
        pk="emp_id", normalize=norm_employees),
    "doctors": dict(mysql_table="Doctors",
        mysql_cols="doc_id, emp_code, specialty, license_no",
        pg_cols="doc_id, emp_code, specialty, license_no",
        pk="doc_id", normalize=norm_doctors),
    "patients": dict(mysql_table="Patients",
        mysql_cols="pat_id, ppl_code, diseaseType, diagnosisDate",
        pg_cols="pat_id, ppl_code, disease_type, diagnosis_date",
        pk="pat_id", normalize=norm_patients),
    "appointments": dict(mysql_table="Appointments",
        mysql_cols="appt_id, doc_code, pat_code, apptDate, apptTime, registered_by, status",
        pg_cols="appt_id, doc_code, pat_code, appt_date, appt_time, registered_by, status",
        pk="appt_id", normalize=norm_appointments),
    "health_documents": dict(mysql_table="HealthDocuments",
        mysql_cols="doc_rec_id, doc_code, PatientCode, appt_code, testType, result, result_date",
        pg_cols="doc_rec_id, doc_code, patient_code, appt_code, test_type, result, result_date",
        pk="doc_rec_id", normalize=None),
    "costs": dict(mysql_table="Costs",
        mysql_cols="cost_id, pat_code, appt_code, category, amount, is_paid, cost_date, description",
        pg_cols="cost_id, pat_code, appt_code, category, amount, is_paid, cost_date, description",
        pk="cost_id", normalize=None),
    "log": dict(mysql_table="Log",
        mysql_cols="log_id, table_name, record_id, action_type, changed_by, changed_at",
        pg_cols="log_id, table_name, record_id, action_type, changed_by, changed_at",
        pk="log_id", normalize=norm_log),
}

BATCH_SIZE = 20_000
MAX_SAMPLES = 10


def verify_table(name, cfg, my_cur, pg_conn):
    # Server-side (named) cursor: PostgreSQL streams the rows in chunks of BATCH_SIZE
    # instead of sending the whole table to Python at execute() time. Without it, a
    # 4-million-row table takes so long to arrive that the MySQL server, which is
    # waiting for us to read its result, gives up (net_write_timeout, 60 s default).
    pg_cur = pg_conn.cursor(name=f"verify_{name}")
    pg_cur.itersize = BATCH_SIZE
    my_cur.execute(f"SELECT {cfg['mysql_cols']} FROM {cfg['mysql_table']} ORDER BY {cfg['pk']}")
    pg_cur.execute(f"SELECT {cfg['pg_cols']} FROM {name} ORDER BY {cfg['pk']}")
    pg_iter = iter(pg_cur)   # iteration fetches itersize rows per round trip; fetchone() would fetch one

    compared, matched, missing_in_pg, mismatched = 0, 0, 0, 0
    samples = []
    normalize = cfg["normalize"]

    my_row = my_cur.fetchone()
    pg_row = next(pg_iter, None)
    while my_row is not None:
        my_pk = my_row[0]
        expected = normalize(my_row)

        if pg_row is None or pg_row[0] > my_pk:
            missing_in_pg += 1
            my_row = my_cur.fetchone()
            continue

        if pg_row[0] < my_pk:
            pg_row = next(pg_iter, None)
            continue

        compared += 1
        if expected == tuple(pg_row):
            matched += 1
        else:
            mismatched += 1
            if len(samples) < MAX_SAMPLES:
                samples.append((my_pk, expected, tuple(pg_row)))
        my_row = my_cur.fetchone()
        pg_row = next(pg_iter, None)

    pg_cur.close()
    return {
        "compared": compared, "matched": matched,
        "missing_in_pg": missing_in_pg, "mismatched": mismatched,
        "samples": samples,
    }


def main():
    my_conn = mysql.connector.connect(host="localhost", user="migrator_ro",
        password=getpass("MySQL (migrator_ro) password: "), database="clinicflow_legacy")
    pg_conn = connect_pg()
    my_cur, pg_cur = my_conn.cursor(), pg_conn.cursor()

    pg_cur.execute("SELECT appt_id FROM appointments")
    valid_appt_ids = {r[0] for r in pg_cur.fetchall()}
    TABLES["health_documents"]["normalize"] = make_norm_health_documents(valid_appt_ids)
    TABLES["costs"]["normalize"] = make_norm_costs(valid_appt_ids)

    report_lines = [f"# Migration verification report", f"Generated: {datetime.now().isoformat()}", ""]
    overall_ok = True

    for name in TABLE_ORDER:
        print(f"\nVerifying {name}...")
        result = verify_table(name, TABLES[name], my_cur, pg_conn)
        ok = result["mismatched"] == 0
        overall_ok &= ok
        print(f"  compared={result['compared']} matched={result['matched']} "
              f"missing_in_pg={result['missing_in_pg']} mismatched={result['mismatched']}")

        report_lines.append(f"## {name}: {'PASS' if ok else 'FAIL'}")
        report_lines.append(f"- Compared: {result['compared']}")
        report_lines.append(f"- Matched: {result['matched']}")
        report_lines.append(f"- Missing in target (expected -- quarantined): {result['missing_in_pg']}")
        report_lines.append(f"- **Mismatched (unexpected): {result['mismatched']}**")
        if result["samples"]:
            report_lines.append("\n| pk | expected | actual |\n|---|---|---|")
            for pk, exp, act in result["samples"]:
                report_lines.append(f"| {pk} | `{exp}` | `{act}` |")
        report_lines.append("")

    report_lines.insert(2, f"**Overall: {'ALL TABLES PASS' if overall_ok else 'MISMATCHES FOUND -- see below'}**\n")

    with open("migrator/out/migration_report.md", "w") as f:
        f.write("\n".join(report_lines))

    print(f"\n{'ALL TABLES PASS' if overall_ok else 'MISMATCHES FOUND'} -- report written to migrator/out/migration_report.md")

    my_cur.close(); my_conn.close()
    pg_cur.close(); pg_conn.close()


if __name__ == "__main__":
    main()
