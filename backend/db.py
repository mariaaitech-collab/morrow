import os
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, Boolean, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import inspect, text

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
    # Recurring / bulk scheduling support
    recurrence = Column(String(20), default="none")          # none|daily|weekly|monthly
    recurrence_end = Column(DateTime, nullable=True)
    recurring = Column(Boolean, default=False)
    # Why the AI image for this post could not be made (the post is kept and
    # goes out text-only). Empty when there was no image failure.
    media_error = Column(Text, nullable=True)


def init_db():
    """Create tables if they do not yet exist, then ensure new columns exist."""
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    existing = {c["name"] for c in inspector.get_columns("scheduled_posts")}
    with engine.begin() as conn:
        if "recurrence" not in existing:
            conn.execute(text("ALTER TABLE scheduled_posts ADD COLUMN recurrence VARCHAR(20) DEFAULT 'none'"))
        if "recurrence_end" not in existing:
            conn.execute(text("ALTER TABLE scheduled_posts ADD COLUMN recurrence_end DATETIME"))
        if "recurring" not in existing:
            conn.execute(text("ALTER TABLE scheduled_posts ADD COLUMN recurring BOOLEAN DEFAULT 0"))
        if "media_error" not in existing:
            conn.execute(text("ALTER TABLE scheduled_posts ADD COLUMN media_error TEXT"))
    print(f"[DB] SQLite database ready at {DB_PATH}")