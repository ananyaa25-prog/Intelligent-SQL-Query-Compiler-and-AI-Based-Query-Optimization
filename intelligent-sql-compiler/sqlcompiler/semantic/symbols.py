"""Symbol table and metadata extraction from SQLite database."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ColumnSymbol:
    name: str
    declared_type: str
    canonical_type: str  # "INTEGER", "REAL", "TEXT", or "UNKNOWN"
    nullable: bool
    is_pk: bool


@dataclass
class TableSymbol:
    name: str
    columns: dict[str, ColumnSymbol] = field(default_factory=dict)
    primary_key: list[str] = field(default_factory=list)


def canonicalize_type(declared: str) -> str:
    declared = (declared or "").upper()
    if any(k in declared for k in ("INT", "INTEGER", "BIGINT", "TINYINT")):
        return "INTEGER"
    if any(k in declared for k in ("REAL", "FLOAT", "DOUBLE", "NUMERIC")):
        return "REAL"
    if any(k in declared for k in ("TEXT", "CHAR", "CLOB", "VARCHAR", "STRING")):
        return "TEXT"
    return "UNKNOWN"


@dataclass
class Catalog:
    tables: dict[str, TableSymbol] = field(default_factory=dict)

    @classmethod
    def from_sqlite(cls, conn: sqlite3.Connection) -> Catalog:
        catalog = cls()
        cursor = conn.cursor()
        table_rows = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()

        for (table_name,) in table_rows:
            table_sym = TableSymbol(name=table_name)
            col_rows = cursor.execute(f'PRAGMA table_info("{table_name}")').fetchall()
            for col in col_rows:
                # cid, name, type, notnull, dflt_value, pk
                cid, cname, ctype, notnull, _, pk = col
                canon = canonicalize_type(ctype)
                sym = ColumnSymbol(
                    name=cname,
                    declared_type=ctype or "UNKNOWN",
                    canonical_type=canon,
                    nullable=not bool(notnull),
                    is_pk=bool(pk),
                )
                table_sym.columns[cname.casefold()] = sym
                if pk:
                    table_sym.primary_key.append(cname)
            catalog.tables[table_name.casefold()] = table_sym
        return catalog

    @classmethod
    def default_university(cls, db_path: Optional[Path] = None) -> Catalog:
        if db_path and db_path.exists():
            uri = f"{db_path.resolve().as_uri()}?mode=ro"
            with sqlite3.connect(uri, uri=True) as conn:
                return cls.from_sqlite(conn)


        # Fallback static university catalog
        catalog = cls()

        # students
        students = TableSymbol(name="students", primary_key=["student_id"])
        for name, ctype, null in [
            ("student_id", "INTEGER", False),
            ("name", "TEXT", False),
            ("email", "TEXT", False),
            ("department", "TEXT", False),
            ("age", "INTEGER", False),
            ("gpa", "REAL", False),
        ]:
            students.columns[name.casefold()] = ColumnSymbol(
                name=name,
                declared_type=ctype,
                canonical_type=canonicalize_type(ctype),
                nullable=null,
                is_pk=(name == "student_id"),
            )
        catalog.tables["students"] = students

        # courses
        courses = TableSymbol(name="courses", primary_key=["course_id"])
        for name, ctype, null in [
            ("course_id", "INTEGER", False),
            ("title", "TEXT", False),
            ("department", "TEXT", False),
            ("credits", "INTEGER", False),
        ]:
            courses.columns[name.casefold()] = ColumnSymbol(
                name=name,
                declared_type=ctype,
                canonical_type=canonicalize_type(ctype),
                nullable=null,
                is_pk=(name == "course_id"),
            )
        catalog.tables["courses"] = courses

        # enrollments
        enrollments = TableSymbol(name="enrollments", primary_key=["enrollment_id"])
        for name, ctype, null in [
            ("enrollment_id", "INTEGER", False),
            ("student_id", "INTEGER", False),
            ("course_id", "INTEGER", False),
            ("grade", "TEXT", True),
        ]:
            enrollments.columns[name.casefold()] = ColumnSymbol(
                name=name,
                declared_type=ctype,
                canonical_type=canonicalize_type(ctype),
                nullable=null,
                is_pk=(name == "enrollment_id"),
            )
        catalog.tables["enrollments"] = enrollments

        return catalog


class Scope:
    """Per-query scope tracking table references, aliases, and column aliases."""

    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        self.table_aliases: dict[str, str] = {}  # alias.lower() -> table_name.lower()
        self.available_tables: list[str] = []    # list of table_name.lower()
        self.column_aliases: dict[str, str] = {} # alias.lower() -> inferred_type

    def add_table(self, table_name: str, alias: Optional[str] = None) -> Optional[str]:
        t_key = table_name.casefold()
        if t_key not in self.catalog.tables:
            return None
        self.available_tables.append(t_key)
        if alias:
            self.table_aliases[alias.casefold()] = t_key
        return t_key

    def resolve_table_name(self, qualifier: str) -> Optional[str]:
        q = qualifier.casefold()
        if q in self.table_aliases:
            return self.table_aliases[q]
        if q in self.catalog.tables:
            return q
        return None

    def resolve_column(
        self,
        column_name: str,
        qualifier: Optional[str] = None
    ) -> tuple[Optional[ColumnSymbol], Optional[str], Optional[str]]:
        """
        Resolve a column in this scope.
        Returns: (column_symbol, resolved_table_name, error_reason)
        """
        c_key = column_name.casefold()

        if qualifier:
            tbl_key = self.resolve_table_name(qualifier)
            if not tbl_key:
                return None, None, f"Unknown table or alias '{qualifier}'."
            table_sym = self.catalog.tables.get(tbl_key)
            if not table_sym:
                return None, None, f"Table '{qualifier}' not found in catalog."
            col_sym = table_sym.columns.get(c_key)
            if not col_sym:
                return None, tbl_key, f"Column '{column_name}' does not exist in table '{table_sym.name}'."
            return col_sym, table_sym.name, None

        # Unqualified column: search all available tables
        matches = []
        for tbl_key in self.available_tables:
            table_sym = self.catalog.tables.get(tbl_key)
            if table_sym and c_key in table_sym.columns:
                matches.append((table_sym.columns[c_key], table_sym.name))

        if not matches:
            return None, None, f"Column '{column_name}' not found in referenced tables."
        if len(matches) > 1:
            matched_tables = ", ".join(t for _, t in matches)
            return None, None, f"Ambiguous column '{column_name}'; appears in tables: {matched_tables}."
        col_sym, tbl_name = matches[0]
        return col_sym, tbl_name, None
