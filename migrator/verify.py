"""One report: row counts (source vs target), quarantine summary."""
from getpass import getpass
import mysql.connector
import psycopg2
from common import TABLE_ORDER, connect_pg

MYSQL_TABLES = {"people": "People", "employees": "Employees", "doctors": "Doctors",
    "patients": "Patients", "appointments": "Appointments",
    "health_documents": "HealthDocuments", "costs": "Costs", "log": "Log"}

if __name__ == "__main__":
    my_conn = mysql.connector.connect(host="localhost", user="migrator_ro",
        password=getpass("MySQL (migrator_ro) password: "), database="clinicflow_legacy")
    pg_conn = connect_pg()
    my_cur, pg_cur = my_conn.cursor(), pg_conn.cursor()

    print("\n=== Row counts: source vs target ===")
    all_match = True
    for t in TABLE_ORDER:
        my_cur.execute(f"SELECT COUNT(*) FROM {MYSQL_TABLES[t]}")
        src = my_cur.fetchone()[0]
        pg_cur.execute(f"SELECT COUNT(*) FROM {t}")
        tgt = pg_cur.fetchone()[0]
        flag = "OK" if src == tgt else "MISMATCH"
        if src != tgt:
            all_match = False
        print(f"  {t:<20} source={src:<10} target={tgt:<10} {flag}")

    print("\n=== Quarantine summary ===")
    pg_cur.execute("SELECT source_table, reason, COUNT(*) FROM migration_quarantine GROUP BY source_table, reason ORDER BY source_table")
    rows = pg_cur.fetchall()
    if not rows:
        print("  (empty — no quarantined rows)")
    for table, reason, count in rows:
        print(f"  {table:<20} {count:<8} {reason}")

    print("\n=== Overall ===")
    print("Row counts: " + ("ALL MATCH" if all_match else "MISMATCHES FOUND — investigate above"))

    my_cur.close(); my_conn.close()
    pg_cur.close(); pg_conn.close()
