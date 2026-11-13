"""SQLAlchemy schema. PostgreSQL in production; SQLite is a local/test fallback."""
import os
import time
import uuid
from sqlalchemy import create_engine, String, Text, Float, LargeBinary, ForeignKey, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__="users"
    id:Mapped[str]=mapped_column(String(32),primary_key=True,default=lambda:uuid.uuid4().hex)
    email:Mapped[str]=mapped_column(String(254),unique=True)
    password:Mapped[str]=mapped_column(Text)

class Session(Base):
    __tablename__="sessions"
    token:Mapped[str]=mapped_column(String(64),primary_key=True)
    user_id:Mapped[str]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    expires:Mapped[float]=mapped_column(Float)

class Reset(Base):
    __tablename__="password_resets"
    token:Mapped[str]=mapped_column(String(64),primary_key=True)
    user_id:Mapped[str]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"))
    expires:Mapped[float]=mapped_column(Float)

class Resource(Base):
    __tablename__="resources"
    id:Mapped[str]=mapped_column(String(32),primary_key=True,default=lambda:uuid.uuid4().hex)
    user_id:Mapped[str]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    kind:Mapped[str]=mapped_column(String(32))
    name:Mapped[str]=mapped_column(String(100))
    payload:Mapped[str]=mapped_column(Text)
    created:Mapped[float]=mapped_column(Float,default=time.time)

class Artifact(Base):
    __tablename__="artifacts"
    id:Mapped[str]=mapped_column(String(32),primary_key=True)
    user_id:Mapped[str]=mapped_column(ForeignKey("users.id",ondelete="CASCADE"),index=True)
    data:Mapped[bytes]=mapped_column(LargeBinary)

url=os.getenv("DATABASE_URL","sqlite:////tmp/fraudshield-local.db")
engine=create_engine(url,connect_args={"check_same_thread":False} if url.startswith("sqlite") else {},pool_pre_ping=True)
if url.startswith("sqlite"):
    @event.listens_for(engine,"connect")
    def foreign_keys(dbapi,record):
        dbapi.execute("PRAGMA foreign_keys=ON")
DB=sessionmaker(engine,expire_on_commit=False)

def initialize():
    if url.startswith("sqlite"):
        Base.metadata.create_all(engine)
    else:
        from sqlalchemy import inspect
        if "users" not in inspect(engine).get_table_names():
            raise RuntimeError("Run alembic upgrade head before starting PostgreSQL.")
