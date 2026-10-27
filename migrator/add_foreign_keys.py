"""Run once, after all 8 tables are loaded. Adds real FOREIGN KEY constraints
that the legacy MySQL schema never had."""
from getpass import getpass
import psycopg2
from common import connect_pg

STATEMENTS = [
    "ALTER TABLE employees ADD CONSTRAINT fk_employees_people FOREIGN KEY (ppl_code) REFERENCES people(ppl_id)",
    "ALTER TABLE doctors ADD CONSTRAINT fk_doctors_employees FOREIGN KEY (emp_code) REFERENCES employees(emp_id)",
    "ALTER TABLE patients ADD CONSTRAINT fk_patients_people FOREIGN KEY (ppl_code) REFERENCES people(ppl_id)",
    "ALTER TABLE appointments ADD CONSTRAINT fk_appt_doctors FOREIGN KEY (doc_code) REFERENCES doctors(doc_id)",
    "ALTER TABLE appointments ADD CONSTRAINT fk_appt_patients FOREIGN KEY (pat_code) REFERENCES patients(pat_id)",
    "ALTER TABLE health_documents ADD CONSTRAINT fk_hd_doctors FOREIGN KEY (doc_code) REFERENCES doctors(doc_id)",
    "ALTER TABLE health_documents ADD CONSTRAINT fk_hd_patients FOREIGN KEY (patient_code) REFERENCES patients(pat_id)",
    "ALTER TABLE health_documents ADD CONSTRAINT fk_hd_appt FOREIGN KEY (appt_code) REFERENCES appointments(appt_id) ON DELETE SET NULL",
    "ALTER TABLE costs ADD CONSTRAINT fk_costs_patients FOREIGN KEY (pat_code) REFERENCES patients(pat_id)",
    "ALTER TABLE costs ADD CONSTRAINT fk_costs_appt FOREIGN KEY (appt_code) REFERENCES appointments(appt_id) ON DELETE SET NULL",
    # log.record_id intentionally has NO foreign key: points at a different
    # table depending on table_name, so no single REFERENCES target is correct.
    "CREATE INDEX IF NOT EXISTS idx_employees_ppl_code ON employees(ppl_code)",
    "CREATE INDEX IF NOT EXISTS idx_doctors_emp_code ON doctors(emp_code)",
    "CREATE INDEX IF NOT EXISTS idx_patients_ppl_code ON patients(ppl_code)",
    "CREATE INDEX IF NOT EXISTS idx_appt_doc_code ON appointments(doc_code)",
    "CREATE INDEX IF NOT EXISTS idx_appt_pat_code ON appointments(pat_code)",
    "CREATE INDEX IF NOT EXISTS idx_hd_doc_code ON health_documents(doc_code)",
    "CREATE INDEX IF NOT EXISTS idx_hd_patient_code ON health_documents(patient_code)",
    "CREATE INDEX IF NOT EXISTS idx_hd_appt_code ON health_documents(appt_code)",
    "CREATE INDEX IF NOT EXISTS idx_costs_pat_code ON costs(pat_code)",
    "CREATE INDEX IF NOT EXISTS idx_costs_appt_code ON costs(appt_code)",
]

if __name__ == "__main__":
    pg_conn = connect_pg()
    pg_cur = pg_conn.cursor()
    for stmt in STATEMENTS:
        print(f"  {stmt[:70]}...")
        pg_cur.execute(stmt)
    pg_conn.commit()
    print("All foreign keys and supporting indexes added.")
    pg_cur.close(); pg_conn.close()
