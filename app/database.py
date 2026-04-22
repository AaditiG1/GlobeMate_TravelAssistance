from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Use your PostgreSQL credentials
SQLALCHEMY_DATABASE_URL = "postgresql://postgres:Aaditi123%40@localhost:5432/globemate_db"


# Create engine
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# Session maker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
