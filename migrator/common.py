"""Shared helpers used by every per-table migration script."""
import os
import re
from datetime import datetime
from getpass import getpass

import psycopg2

DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m-%d-%Y"]

# Dependency order: each table only references tables earlier in this list.
TABLE_ORDER = ["people", "employees", "doctors", "patients",
               "appointments", "health_documents", "costs", "log"]


def parse_messy_date(raw):
    """Return (date_or_None, reason_or_None)."""
    if raw is None or raw.strip() == "":
        return None, None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw.strip(), fmt).date(), None
        except ValueError:
            continue
    return None, f"unrecognized date format: {raw!r}"


def shape_of(raw):
    """13/45/2026 -> 99/99/9999 -- for grouping quarantine reasons."""
    return re.sub(r"\d", "9", raw or "")


def reset_identity(pg_cur, table, pk_column):
    """After loading explicit IDs, tell Postgres what the NEXT auto id should be."""
    pg_cur.execute(
        f"SELECT setval(pg_get_serial_sequence('{table}','{pk_column}'), "
        f"COALESCE((SELECT MAX({pk_column}) FROM {table}), 1))"
    )


QUARANTINE_COLUMNS = ["source_table", "source_row_id", "source_column", "original_value", "reason"]


def connect_pg(default_service="local_pg"):
    """Connect to PostgreSQL using a named profile from ~/.pg_service.conf.
    Choose the target with the environment variable PG_SERVICE
    (for example PG_SERVICE=prod_rw). Host, database, user, SSL and keepalive
    settings all come from the profile; only the password is asked for."""
    service = os.environ.get("PG_SERVICE", default_service)
    return psycopg2.connect(service=service,
                            password=getpass(f"Postgres ({service}) password: "))
