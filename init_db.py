"""Create the database tables. Usage: python init_db.py"""

from app.config import Settings
from app.database import init_db, make_engine

if __name__ == "__main__":
    settings = Settings.from_env()
    init_db(make_engine(settings.database_url))
    print(f"Database ready: {settings.database_url}")
