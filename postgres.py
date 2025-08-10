from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence

import psycopg
from psycopg.rows import dict_row


@dataclass
class QueryResult:
    rows: list[Mapping[str, Any]]
    rowcount: int


class PorygonPostgres:
    """Thin Postgres helper around psycopg connection pool.

    Primary API: run_query(sql, params=None, many=False) -> QueryResult | int | None

    - If the SQL is a SELECT, returns QueryResult with list of dict rows.
    - For INSERT/UPDATE/DELETE, returns the affected rowcount.
    - If many=True, `params` must be a sequence of param sequences for executemany.
    """

    def __init__(self, connection_string: str, min_size: int = 1, max_size: int = 10) -> None:
        if not connection_string:
            raise ValueError("connection_string is required")
        self._pool = psycopg.ConnectionPool(
            conninfo=connection_string,
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": dict_row},
        )

    @contextlib.contextmanager
    def _get_conn(self):
        with self._pool.connection() as conn:  # type: ignore[attr-defined]
            yield conn

    def close(self) -> None:
        self._pool.close()

    def run_query(
        self,
        sql: str,
        params: Optional[Sequence[Any] | Mapping[str, Any]] = None,
        *,
        many: bool = False,
    ) -> QueryResult | int:
        """Run a SQL query safely using the connection pool.

        - For SELECT: returns QueryResult
        - For DML (INSERT/UPDATE/DELETE): returns rowcount
        """
        if not isinstance(sql, str) or not sql.strip():
            raise ValueError("sql must be a non-empty string")

        sql_stripped = sql.lstrip().lower()
        is_select = sql_stripped.startswith("select")

        with self._get_conn() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if many:
                    if params is None or not isinstance(params, Iterable):
                        raise ValueError("params must be an iterable of param sequences when many=True")
                    cur.executemany(sql, params)  # type: ignore[arg-type]
                else:
                    if params is None:
                        cur.execute(sql)
                    else:
                        cur.execute(sql, params)

                if is_select:
                    rows = cur.fetchall()
                    return QueryResult(rows=list(rows), rowcount=cur.rowcount)
                else:
                    return cur.rowcount


__all__ = ["PorygonPostgres", "QueryResult"]


