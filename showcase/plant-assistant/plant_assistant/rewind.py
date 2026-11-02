"""The show's rewind of the stetiq server's tracking database, keeping its API tokens.

stetiq has no call to delete a Knowledge Graph, so the rewind is an operator's, on the
database itself: every table but the tokens' is emptied, and the server's clients stay
signed in.

The module needs only SQLAlchemy, which the stetiq image has, so it also runs inside the
stetiq container, next to the SQLite file the server holds open (what `show.py` does on
stage, piping this file to `docker compose exec -T stetiq python -`):

    python rewind.py              # rewinds $STETIQ_DATABASE_URL
"""

from __future__ import annotations

import os

import sqlalchemy

# The table of the server's API tokens: the one a rewind keeps.
API_TOKENS_TABLE = "api_tokens"


def rewind_tracking(database_url: str) -> None:
    """Empty the stetiq server's tracking database at `database_url`, keeping its API
    tokens."""
    engine = sqlalchemy.create_engine(database_url)
    try:
        tables = sqlalchemy.MetaData()
        tables.reflect(engine)
        with engine.begin() as connection:
            for table in reversed(tables.sorted_tables):
                if table.name != API_TOKENS_TABLE:
                    connection.execute(table.delete())
    finally:
        engine.dispose()


if __name__ == "__main__":
    rewind_tracking(os.environ["STETIQ_DATABASE_URL"])
