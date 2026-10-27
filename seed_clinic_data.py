import random
import string
from getpass import getpass
import mysql.connector
from faker import Faker

fake = Faker()

def safe(s, maxlen):
    return s[:maxlen] if s else s

# --- scale knobs ---
TOTAL_PEOPLE      = 520_000
NUM_EMPLOYEES     = 8_000
NUM_DOCTORS       = 800
NUM_PATIENTS      = 500_000
NUM_APPOINTMENTS  = 4_000_000
NUM_HEALTHDOCS    = 2_500_000
NUM_COSTS         = 3_000_000
BATCH_SIZE        = 20_000
# --------------------

conn = mysql.connector.connect(
    host="localhost", user="maryam",
    password=getpass("MySQL password: "),
    database="clinicflow_legacy",
)
conn.autocommit = False
cur = conn.cursor()

def rand_date_messy():
    d = fake.date_between(start_date="-5y", end_date="today")
    fmt = random.choice(["%Y-%m-%d", "%d/%m/%Y", "%m-%d-%Y"])
    return d.strftime(fmt)

def rand_time():
    h = random.randint(8, 18)
    m = random.choice([0, 15, 30, 45])
    return f"{h:02d}:{m:02d}"

TEST_TYPES = ["Blood Test", "X-Ray", "MRI", "Urine Test", "ECG", "Allergy Panel", "CT Scan", "Ultrasound"]
RESULT_PHRASES = [
    "Within normal range.", "Slightly elevated, monitor.", "No abnormalities detected.",
    "Requires follow-up.", "Consistent with prior results.", "Mild irregularity noted.",
]
def rand_result_text():
    tail = "".join(random.choices(string.ascii_lowercase, k=random.randint(5, 15)))
    return f"{random.choice(RESULT_PHRASES)} ref:{tail}"

COST_CATEGORIES = ["consultation", "lab_test", "medication", "procedure", "other"]
COST_DESCS = ["Routine visit", "Follow-up", "Emergency", "Lab fee", "Medication charge", "Procedure fee"]
STATUSES = ["scheduled", "completed", "cancelled", "no_show"]
USERNAMES = ["front_desk1", "front_desk2", "admin", "nurse_j"]

def bulk_insert(sql, total, row_fn, label):
    batch = []
    inserted = 0
    for i in range(total):
        batch.append(row_fn(i))
        if len(batch) >= BATCH_SIZE:
            cur.executemany(sql, batch)
            conn.commit()
            inserted += len(batch)
            batch = []
            print(f"  {label}: {inserted}/{total}")
    if batch:
        cur.executemany(sql, batch)
        conn.commit()
        inserted += len(batch)
        print(f"  {label}: {inserted}/{total}")

# 1. People
bulk_insert(
    "INSERT INTO People (firstName, last_name, birth_date, address, phone) VALUES (%s,%s,%s,%s,%s)",
    TOTAL_PEOPLE,
    lambda i: (fake.first_name(), fake.last_name(), rand_date_messy(),
           fake.address().replace("\n", ", "), safe(fake.phone_number(), 30)),
    "People"
)

# Split People IDs into disjoint employee/patient pools (IDs are sequential 1..TOTAL_PEOPLE)
all_people_ids = list(range(1, TOTAL_PEOPLE + 1))
random.shuffle(all_people_ids)
employee_people_ids = all_people_ids[:NUM_EMPLOYEES]
patient_people_ids = all_people_ids[NUM_EMPLOYEES:NUM_EMPLOYEES + NUM_PATIENTS]

# 2. Employees
responsibilities = ["Receptionist", "Nurse", "Doctor", "Admin", "Lab Technician", "Manager"]
bulk_insert(
    "INSERT INTO Employees (ppl_code, responsibility, hire_date, is_active) VALUES (%s,%s,%s,%s)",
    NUM_EMPLOYEES,
    lambda i: (employee_people_ids[i], random.choice(responsibilities), rand_date_messy(),
               random.choice([1, 1, 1, 0])),
    "Employees"
)
employee_ids = list(range(1, NUM_EMPLOYEES + 1))

# 3. Doctors (subset of employee IDs)
doctor_employee_ids = random.sample(employee_ids, NUM_DOCTORS)
specialties = ["Cardiology", "Dermatology", "Pediatrics", "Orthopedics", "General Practice", "Neurology"]
bulk_insert(
    "INSERT INTO Doctors (emp_code, specialty, license_no) VALUES (%s,%s,%s)",
    NUM_DOCTORS,
    lambda i: (doctor_employee_ids[i], random.choice(specialties), f"MD-{random.randint(10000,99999)}"),
    "Doctors"
)
doctor_ids = list(range(1, NUM_DOCTORS + 1))

# 4. Patients
diseases = ["Hypertension", "Diabetes", "Asthma", "Migraine", "Flu", "Arthritis", "Allergy"]
bulk_insert(
    "INSERT INTO Patients (ppl_code, diseaseType, diagnosisDate) VALUES (%s,%s,%s)",
    NUM_PATIENTS,
    lambda i: (patient_people_ids[i], random.choice(diseases), rand_date_messy()),
    "Patients"
)
patient_ids = range(1, NUM_PATIENTS + 1)

# 5. Appointments
bulk_insert(
    "INSERT INTO Appointments (doc_code, pat_code, apptDate, apptTime, registered_by, status) VALUES (%s,%s,%s,%s,%s,%s)",
    NUM_APPOINTMENTS,
    lambda i: (random.choice(doctor_ids), random.choice(patient_ids), rand_date_messy(),
               rand_time(), random.choice(USERNAMES), random.choice(STATUSES)),
    "Appointments"
)
appt_ids = range(1, NUM_APPOINTMENTS + 1)

# 6. HealthDocuments (~25% not linked to any appointment)
bulk_insert(
    "INSERT INTO HealthDocuments (doc_code, PatientCode, appt_code, testType, result, result_date) VALUES (%s,%s,%s,%s,%s,%s)",
    NUM_HEALTHDOCS,
    lambda i: (random.choice(doctor_ids), random.choice(patient_ids),
           (random.randint(1, NUM_APPOINTMENTS) if random.random() > 0.25 else None),
           random.choice(TEST_TYPES), rand_result_text(), rand_date_messy()),
    "HealthDocuments"
)

# 7. Costs
bulk_insert(
    "INSERT INTO Costs (pat_code, appt_code, category, amount, is_paid, cost_date, description) VALUES (%s,%s,%s,%s,%s,%s,%s)",
    NUM_COSTS,
    lambda i: (random.choice(patient_ids),
               random.choice(appt_ids) if random.random() > 0.35 else None,
               random.choice(COST_CATEGORIES), round(random.uniform(10, 500), 2),
               random.choice([0, 1]), rand_date_messy(), random.choice(COST_DESCS)),    "Costs"
)

# 8. Log — one row per Appointments insert, one per HealthDocuments insert
bulk_insert(
    "INSERT INTO Log (table_name, record_id, action_type, changed_by) VALUES (%s,%s,%s,%s)",
    NUM_APPOINTMENTS,
    lambda i: ("Appointments", i + 1, "INSERT", random.choice(USERNAMES)),
    "Log (Appointments)"
)
bulk_insert(
    "INSERT INTO Log (table_name, record_id, action_type, changed_by) VALUES (%s,%s,%s,%s)",
    NUM_HEALTHDOCS,
    lambda i: ("HealthDocuments", i + 1, "INSERT", random.choice(USERNAMES)),
    "Log (HealthDocuments)"
)

cur.close()
conn.close()
print("Done seeding clinicflow_legacy at scale.")
