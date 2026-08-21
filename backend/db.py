import os
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "brandora.db")

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()


class ScheduledPost(Base):
    __tablename__ = "scheduled_posts"

    id = Column(Integer, primary_key=True, index=True)
    scheduled_at = Column(DateTime, index=True)
    platforms = Column(String(255))
    content = Column(Text)
    media_url = Column(String(1000), nullable=True)
    media_type = Column(String(20), nullable=True)
    status = Column(String(20), default="pending", index=True)
    result = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100), nullable=True)


def init_db():
    """Create tables if they do not yet exist."""
    Base.metadata.create_all(engine)
    print(f"[DB] SQLite database ready at {DB_PATH}")