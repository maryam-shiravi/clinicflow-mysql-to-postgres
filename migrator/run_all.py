"""Run all 8 migration scripts in dependency order, in one pass, one set of passwords.
Usage:
  python migrator/run_all.py
  python migrator/run_all.py --dry-run
  python migrator/run_all.py --tables people,doctors
  python migrator/run_all.py --max-error-rate 0.10
  python migrator/run_all.py --source-timezone Europe/Lisbon
  python migrator/run_all.py --truncate-first
"""
import argparse
import time
from getpass import getpass
import mysql.connector
import psycopg2

from common import TABLE_ORDER, connect_pg
import migrate_people, migrate_employees, migrate_doctors, migrate_patients
import migrate_appointments, migrate_health_documents, migrate_cost, migrate_log

MIGRATORS = {
    "people": migrate_people.migrate,
    "employees": migrate_employees.migrate,
    "doctors": migrate_doctors.migrate,
    "patients": migrate_patients.migrate,
    "appointments": migrate_appointments.migrate,
    "health_documents": migrate_health_documents.migrate,
    "costs": migrate_cost.migrate,
    "log": migrate_log.migrate,
}


def truncate_all(pg_cur, tables):
    for t in reversed(tables):
        pg_cur.execute(f"TRUNCATE TABLE {t} RESTART IDENTITY CASCADE")
    pg_cur.execute("TRUNCATE TABLE migration_quarantine RESTART IDENTITY")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                     help="Run everything, print the report, but ROLL BACK instead of commit.")
    ap.add_argument("--tables", default=None,
                     help="Comma-separated subset, e.g. people,doctors. Default: all 8, in order.")
    ap.add_argument("--max-error-rate", type=float, default=0.10,
                     help="Abort (and rollback) if any table's quarantine rate exceeds this fraction. Default 0.10.")
    ap.add_argument("--source-timezone", default="Europe/Lisbon",
                     help="IANA timezone the legacy datetime values were written in.")
    ap.add_argument("--truncate-first", action="store_true",
                     help="Empty all target tables before migrating (for reruns).")
    args = ap.parse_args()

    selected = args.tables.split(",") if args.tables else TABLE_ORDER
    selected = [t for t in TABLE_ORDER if t in selected]

    my_conn = mysql.connector.connect(host="localhost", user="migrator_ro",
        password=getpass("MySQL (migrator_ro) password: "), database="clinicflow_legacy")
    pg_conn = connect_pg()
    my_cur, pg_cur = my_conn.cursor(), pg_conn.cursor()

    # Always show WHERE this run is writing before anything happens.
    pg_cur.execute("SELECT current_database(), current_user, inet_server_addr(), "
                   "split_part(version(), ' ', 2)")
    db, usr, addr, ver = pg_cur.fetchone()
    print(f"Target: database={db} user={usr} server={addr} postgres={ver}")

    if args.truncate_first:
        print("Truncating target tables...")
        truncate_all(pg_cur, TABLE_ORDER)
        pg_conn.commit()

    summary = []
    aborted = False
    for table in selected:
        print(f"\n--- {table} ---")
        started = time.perf_counter()
        result = MIGRATORS[table](my_cur, pg_cur, source_tz=args.source_timezone)
        print(f"  {table}: {time.perf_counter() - started:.1f} seconds")
        total = result["total"]
        quarantined = result.get("quarantined", 0)
        rate = quarantined / total if total else 0
        summary.append((table, total, quarantined, rate))
        if rate > args.max_error_rate:
            print(f"\n!! ABORTING: {table} error rate {rate:.2%} exceeds --max-error-rate {args.max_error_rate:.2%}")
            aborted = True
            break

    print("\n=== Summary ===")
    for table, total, quarantined, rate in summary:
        print(f"  {table:<20} {total:<10} rows, {quarantined:<8} quarantined ({rate:.2%})")

    if aborted:
        pg_conn.rollback()
        print("\nRolled back. Nothing was committed.")
    elif args.dry_run:
        pg_conn.rollback()
        print("\nDRY RUN complete. Nothing was committed — rolled back intentionally.")
    else:
        pg_conn.commit()
        print("\nCommitted. Migration complete.")

    my_cur.close(); my_conn.close()
    pg_cur.close(); pg_conn.close()


if __name__ == "__main__":
    main()
