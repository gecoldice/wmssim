#!/usr/bin/env python3
"""PostgreSQL 切换：DATABASE_URL 指向一次性 Docker Postgres，再打开存储仍能读回。

SQLite 显式路径在同一进程里仍然可用。不打印连接串。

Usage:
  PYTHONPATH=shared/python:services/api python3 scripts/run_pg_checks.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 55432
CONTAINER = "simapp-pg-ops"
DB_NAME = "simapp"
DB_USER = "simapp"
DB_PASSWORD = "simapp"

os.environ.pop("SIMAPP_DB", None)
os.environ["DATABASE_URL"] = (
    f"postgresql://{DB_USER}:{DB_PASSWORD}@127.0.0.1:{PORT}/{DB_NAME}"
)
sys.path.insert(0, str(ROOT / "shared" / "python"))
sys.path.insert(0, str(ROOT / "services" / "api"))


def _docker(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        check=False,
        text=True,
        capture_output=True,
    )


def _start_postgres() -> None:
    _docker("rm", "-f", CONTAINER)
    started = _docker(
        "run",
        "-d",
        "--name",
        CONTAINER,
        "-e",
        f"POSTGRES_USER={DB_USER}",
        "-e",
        f"POSTGRES_PASSWORD={DB_PASSWORD}",
        "-e",
        f"POSTGRES_DB={DB_NAME}",
        "-p",
        f"127.0.0.1:{PORT}:5432",
        "postgres:16-alpine",
    )
    if started.returncode != 0:
        raise SystemExit(started.stderr.strip() or started.stdout.strip() or "docker run failed")


def _wait_until_ready() -> None:
    import psycopg

    last = "not connected"
    for _ in range(40):
        try:
            with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=2) as conn:
                conn.execute("SELECT 1")
            return
        except Exception as exc:  # noqa: BLE001
            last = str(exc).split("\n", 1)[0]
            time.sleep(1)
    raise SystemExit(f"postgres did not become ready: {last}")


def main() -> None:
    _start_postgres()
    try:
        _wait_until_ready()
        from app.store import MemoryStore  # noqa: E402

        first = MemoryStore()
        info = first.persistence_info()
        assert info["engine"] == "postgresql", info
        assert info["durable"] is True
        assert info["database"] == DB_NAME
        assert info["path"] is None
        project = first.create_project("pg-switch", "metric")
        pid = project["id"]
        first.put_layout_revision(
            pid,
            {
                "id": "layout-pg",
                "revision": "ld-pg-1",
                "elements": [{"instanceId": "rack-001"}],
            },
        )
        assert first._conn is not None
        first._conn.close()

        revived = MemoryStore()
        loaded = revived.get_project(pid)
        assert loaded is not None and loaded["name"] == "pg-switch"
        layout = revived.get_layout(pid, "layout-pg", "ld-pg-1")
        assert layout is not None and layout["revision"] == "ld-pg-1"
        revived._conn.close()

        sqlite_path = Path(tempfile.mkdtemp(prefix="simapp-sqlite-")) / "side.sqlite"
        side = MemoryStore(db_path=sqlite_path)
        assert side.persistence_info()["engine"] == "sqlite"
        assert side.get_project(pid) is None
        local = side.create_project("sqlite-side", "metric")
        side._conn.close()
        again = MemoryStore(db_path=sqlite_path)
        assert again.get_project(local["id"])["name"] == "sqlite-side"
        assert again.get_project(pid) is None
        again._conn.close()
        print(f"PASS postgres switch database={DB_NAME} port={PORT} sqlite side stays separate")
    finally:
        _docker("rm", "-f", CONTAINER)


if __name__ == "__main__":
    main()
