"""Execute submitted SQLite reports against original and held-out input states."""

import csv
from functools import lru_cache
import io
import json
import math
from pathlib import Path
import re
import sqlite3
import tempfile

DATA = Path(__file__).parent / "data"
LIMIT = 1000
IDENT = re.compile(r"[a-z][a-z0-9_]*\Z")
COLUMN = re.compile(r"([a-z][a-z0-9_]*) (TEXT|INTEGER|REAL)\Z")


def validate_tables(tables):
    if not tables or len(tables) > 12:
        raise ValueError("Expected at least one table")
    for name, spec in tables.items():
        cols = spec["columns"]
        if (
            not IDENT.fullmatch(name)
            or not cols
            or not all(COLUMN.fullmatch(c) for c in cols)
        ):
            raise ValueError("Invalid SQLite schema")
        if any(len(r) != len(cols) for r in spec["rows"]):
            raise ValueError("Incorrect row width")


def execute(sql, tables):
    if not isinstance(sql, str) or len(sql) > 32000:
        raise ValueError("Expected one SQL statement")
    validate_tables(tables)
    db = sqlite3.connect(":memory:")
    try:
        for name, spec in tables.items():
            quoted = [f'"{col.split()[0]}" {col.split()[1]}' for col in spec["columns"]]
            db.execute(f'CREATE TABLE "{name}" ({", ".join(quoted)})')
            marks = ", ".join("?" for _ in quoted)
            db.executemany(f'INSERT INTO "{name}" VALUES ({marks})', spec["rows"])
        db.execute("PRAGMA query_only=ON")
        if hasattr(db, "setlimit"):
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 2_000_000)
        allowed = {
            sqlite3.SQLITE_SELECT,
            sqlite3.SQLITE_READ,
            sqlite3.SQLITE_FUNCTION,
            getattr(sqlite3, "SQLITE_RECURSIVE", 33),
        }
        blocked_functions = {
            "load_extension",
            "readfile",
            "writefile",
            "fts3_tokenizer",
            "random",
            "randomblob",
            "zeroblob",
            "printf",
            "format",
        }

        def authorize(action, first, second, _db, _trigger):
            if action not in allowed or (
                action == sqlite3.SQLITE_READ and first not in tables
            ):
                return sqlite3.SQLITE_DENY
            if (
                action == sqlite3.SQLITE_FUNCTION
                and (second or "").lower() in blocked_functions
            ):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        db.set_authorizer(authorize)
        budget = iter(range(1500))
        db.set_progress_handler(lambda: int(next(budget, None) is None), 1000)
        result = db.execute(sql)
        if result.description is None:
            raise ValueError("Expected result columns")
        columns = [c[0] for c in result.description]
        values = result.fetchmany(LIMIT + 1)
        if len(values) > LIMIT:
            raise ValueError("Result row limit exceeded")
        return columns, [list(row) for row in values]
    finally:
        db.close()


def csv_bytes(columns, rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def artifact(task, columns, rows):
    settings = task.get("artifact", {})
    payload = settings.get("payload_column")
    if payload is not None:
        if len(rows) != 1 or not isinstance(rows[0][columns.index(payload)], str):
            raise ValueError("Expected one complete report body")
        return rows[0][columns.index(payload)].encode("utf-8")
    token = settings.get("null_token", "")
    return csv_bytes(
        columns, [[token if cell is None else cell for cell in row] for row in rows]
    )


def equal(actual, expected):
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(
            equal(a, e) for a, e in zip(actual, expected)
        )
    if type(actual) in (int, float) and type(expected) in (int, float):
        return math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9)
    return type(actual) is type(expected) and actual == expected


@lru_cache(maxsize=2)
def index(private=False):
    path = DATA / ("relational_keys.json" if private else "relational_tasks.json")
    return {row["task_id"]: row for row in json.loads(path.read_text())}


def records():
    return [{k: v for k, v in row.items() if k != "tables"} for row in index().values()]


def run_reference(task_id):
    return index(True)[task_id]["reference"]


def run_negative(task_id):
    return index(True)[task_id]["negative"]


def materialize(task_id, directory):
    task = index()[task_id]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "task.json").write_text(
        json.dumps(task, ensure_ascii=False, indent=2) + "\n"
    )
    for name, table in task["tables"].items():
        (directory / (name + ".csv")).write_bytes(
            csv_bytes([c.split()[0] for c in table["columns"]], table["rows"])
        )


def grade(task_id, candidate):
    task, key = index()[task_id], index(True)[task_id]
    for variant, expected in (
        (None, key["expected"]),
        (key["alternate"], key["expected_alternate"]),
    ):
        tables = (
            task["tables"]
            if variant is None
            else {n: {**t, "rows": variant[n]} for n, t in task["tables"].items()}
        )
        try:
            columns, rows = execute(candidate, tables)
        except (ValueError, OverflowError, sqlite3.Error):
            return False
        if columns != task["columns"] or not equal(rows, expected):
            return False
        if task["domain"] == "file_workflow":
            with tempfile.TemporaryDirectory(prefix="independent-export-") as work:
                output = Path(work) / "report.csv"
                output.write_bytes(artifact(task, columns, rows))
                if output.read_bytes() != artifact(task, task["columns"], expected):
                    return False
    return True


def candidate_from_file(path):
    return path.read_text()


def save_candidate(task_id, candidate, path):
    path.write_text(candidate)
