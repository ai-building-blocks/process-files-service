from sqlalchemy import Column, String, DateTime, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os

Base = declarative_base()

class Document(Base):
    __tablename__ = "documents"
    
    id = Column(String, primary_key=True)
    original_filename = Column(String, nullable=False)
    processed_filename = Column(String, nullable=False)
    version = Column(String, nullable=False)
    status = Column(String, nullable=False, default='pending')  # pending, downloading, processing, completed, failed
    created_at = Column(DateTime, default=datetime.utcnow)
    downloaded_at = Column(DateTime, nullable=True)
    processing_started_at = Column(DateTime, nullable=True)
    processing_completed_at = Column(DateTime, nullable=True)
    s3_last_modified = Column(DateTime, nullable=False)
    error_message = Column(String, nullable=True)

# Ensure data directory exists
data_dir = os.path.abspath('./data')
os.makedirs(data_dir, exist_ok=True)

# Use absolute path for database
db_path = os.path.join(data_dir, 'documents.db')
database_url = os.getenv("DATABASE_URL", f"sqlite:///{db_path}")

print(f"Initializing database at: {database_url}")  # Temporary debug print

engine = create_engine(database_url)
SessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(engine)
