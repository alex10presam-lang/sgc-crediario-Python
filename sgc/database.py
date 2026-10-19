import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from sgc.models import Base


def data_directory():
    return Path(
        os.environ.get("SGC_DATA_DIR", Path(__file__).resolve().parents[1] / "data")
    ).resolve()


class Database:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory else data_directory()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "sgc_demo.db"
        self.engine = create_engine(
            "sqlite:///" + self.path.as_posix(),
            connect_args={"check_same_thread": False, "timeout": 15},
        )

        @event.listens_for(self.engine, "connect")
        def configure(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        self.session = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    @contextmanager
    def transaction(self):
        # Serialize writes before reading balances or stock to avoid stale updates.
        with self.session() as session:
            session.connection().exec_driver_sql("BEGIN IMMEDIATE")
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
