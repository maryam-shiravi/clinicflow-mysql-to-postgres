# ClinicFlow: MySQL to PostgreSQL migration tool

A Python tool that migrates a legacy clinic database from MySQL 8.0 to PostgreSQL 18 on AWS (Amazon Web Services) RDS (Relational Database Service), then proves the result row by row.

The source database is **synthetic**: it was generated with Faker and contains no real patient or personal data.

## Highlights

- Migrates 8 tables in dependency order (people, employees, doctors, patients, appointments, health_documents, costs, log).
- Cleans messy legacy dates (`YYYY-MM-DD`, `DD/MM/YYYY`, `MM-DD-YYYY`); anything unrecognised is stored as NULL and recorded in a `migration_quarantine` table with the original value and the reason.
- Handles orphan references explicitly: a row whose required parent does not exist is quarantined; an optional link (`appt_code`) is set to NULL and logged.
- Safety switches: `--dry-run` (run everything, then roll back), `--max-error-rate` (abort and roll back if too many rows are quarantined), `--truncate-first` (clean re-runs), `--tables` (migrate a subset).
- Adds real FOREIGN KEY constraints and supporting indexes after the load (the legacy schema had none).
- Verifies the result twice: row counts, then a value-by-value comparison written to a Markdown report.

## Results

Latest verification run, against the PostgreSQL 18 instance on AWS RDS (`migrator/out/migration_report.md`): **all 8 tables PASS, 17,028,800 rows compared, 0 mismatched, 0 quarantined.** The load itself (17,028,800 rows) took about 885 seconds (roughly 15 minutes) on a `db.t4g.micro` instance.

| Table | Rows compared | Matched |
|---|---|---|
| people | 520,000 | 520,000 |
| employees | 8,000 | 8,000 |
| doctors | 800 | 800 |
| patients | 500,000 | 500,000 |
| appointments | 4,000,000 | 4,000,000 |
| health_documents | 2,500,000 | 2,500,000 |
| costs | 3,000,000 | 3,000,000 |
| log | 6,500,000 | 6,500,000 |

## Project layout

```
migrator/
  run_all.py            run all migrators in dependency order
  migrate_*.py          one migrator per table
  common.py             shared helpers (date parsing, connection, identity reset)
  copy_helper.py        bulk-loading helper
  introspect.py         reads the MySQL structure
  generate_ddl.py       writes the PostgreSQL schema to out/schema_pg.sql
  add_foreign_keys.py   adds foreign keys and indexes after the load
  verify.py             row counts, quarantine summary
  checksum_verify.py    value-by-value verification, writes out/migration_report.md
  out/                  generated schema and verification report
seed_clinic_data.py     generates the synthetic legacy data
```

## Requirements

- Python 3.12
- A MySQL 8.0 source and a PostgreSQL target you can reach
- Python packages: `pip install -r requirements.txt` (Faker, mysql-connector-python, psycopg2-binary)

## Quick start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 1. (optional) generate the synthetic legacy data in MySQL
python seed_clinic_data.py

# 2. create the PostgreSQL schema
python migrator/generate_ddl.py
psql -f migrator/out/schema_pg.sql

# 3. rehearse, then migrate
python migrator/run_all.py --dry-run
python migrator/run_all.py

# 4. add foreign keys and indexes, then verify
python migrator/add_foreign_keys.py
python migrator/verify.py
python migrator/checksum_verify.py
```

Passwords are always typed at a prompt. They are never stored in the code or in the repository.

The PostgreSQL target is chosen with the `PG_SERVICE` environment variable, which names a section in your own `~/.pg_service.conf` (host, port, database, user, TLS settings). That file is deliberately not part of the repository. Example: `PG_SERVICE=local_pg python migrator/run_all.py --dry-run`. Connections are created by `connect_pg()` in `migrator/common.py`.

## Design decisions

- **Quarantine instead of silent loss.** Every row or value that cannot be migrated cleanly is recorded with its original value and a reason.
- **Foreign keys after the load.** Loading first and constraining afterwards keeps the bulk load fast and lets orphan rows be handled explicitly.
- **`log.record_id` has no foreign key on purpose:** it points to a different table depending on `table_name`, so no single target is correct.
- **Timestamps in `log` are labelled, not converted:** they get the source timezone (default `Europe/Lisbon`, changeable with `--source-timezone`).
- **Least privilege on the target:** separate roles for the owner, the loader (`migrator_rw`) and a read-only application user; encrypted connections verified with `sslmode=verify-full`.

## Limitations

- The verification re-applies the same normalisation rules as the migrators, so it proves the load is faithful to those rules, not that the rules themselves are right.
- Built and tested on one source schema; other schemas need new per-table migrators.
- Not intended for real patient data without an additional security and compliance review.

## License

MIT, see [LICENSE](LICENSE).
