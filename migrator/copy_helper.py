"""COPY-based bulk insert helper (replaces execute_values for the big inserts)."""
import io
from datetime import timedelta

NULL_TOKEN = r"\N"


def _timedelta_text(td):
    """MySQL TIME arrives as a timedelta. Render it with the same text PostgreSQL
    produced when execute_values adapted the timedelta (so old and new loads match)."""
    days = td.days                      # Python keeps seconds/microseconds >= 0
    rest = td.seconds
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    text = f"{hours:02d}:{minutes:02d}:{secs:02d}"
    if td.microseconds:
        text += "." + f"{td.microseconds:06d}".rstrip("0")
    if days:
        unit = "day" if days == 1 else "days"
        if td.seconds == 0 and td.microseconds == 0:
            return f"{days} {unit}"
        text = f"{days} {unit} " + ("+" if days < 0 else "") + text
    return text


def _field(value):
    """None -> unquoted \\N (SQL NULL). Everything else is always double-quoted,
    so an empty string stays '' and a real text value '\\N' is NOT mistaken for NULL."""
    if value is None:
        return NULL_TOKEN
    if isinstance(value, bool):
        value = "true" if value else "false"
    elif isinstance(value, timedelta):
        value = _timedelta_text(value)
    return '"' + str(value).replace('"', '""') + '"'


def copy_rows(pg_cur, table, columns, rows):
    """Insert rows into `table` with COPY ... FROM STDIN (CSV format).

    rows: list of tuples, same order as `columns`. Returns the number of rows sent."""
    if not rows:
        return 0
    buf = io.StringIO()
    for row in rows:
        buf.write(",".join(_field(v) for v in row))
        buf.write("\n")
    buf.seek(0)
    pg_cur.copy_expert(
        f"COPY {table} ({', '.join(columns)}) "
        f"FROM STDIN WITH (FORMAT csv, NULL '{NULL_TOKEN}')",
        buf,
    )
    return len(rows)
