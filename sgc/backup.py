"""Machine operator tool; database snapshots include all local companies."""

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from sgc.database import data_directory


def create_backup(directory=None):
    directory = Path(directory) if directory else data_directory()
    source = directory / "sgc_demo.db"
    if not source.exists():
        raise FileNotFoundError("Crie a demonstração antes de gerar o backup.")
    target_dir = directory / "backups"
    target_dir.mkdir(exist_ok=True)
    target = target_dir / f"sgc_{datetime.now():%Y%m%d_%H%M%S}_{uuid4().hex[:8]}.db"
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as origin:
        with closing(sqlite3.connect(target)) as destination:
            origin.backup(destination)
    return target


if __name__ == "__main__":
    print("Backup local criado: " + str(create_backup()))
