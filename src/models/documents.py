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
    status = Column(String, nullable=False, default='queued')  # queued, downloading, processing, completed, failed
    created_at = Column(DateTime, default=datetime.utcnow)
    downloaded_at = Column(DateTime, nullable=True)
    processing_started_at = Column(DateTime, nullable=True)
    processing_completed_at = Column(DateTime, nullable=True)
    s3_last_modified = Column(DateTime, nullable=False)
    error_message = Column(String, nullable=True)

# Get data directory from environment with validation
data_dir = os.path.abspath(os.getenv('DATA_DIR'))
if not data_dir:
    raise ValueError("DATA_DIR environment variable is required")

# Ensure data directories exist
os.makedirs(data_dir, exist_ok=True)
os.makedirs(os.path.join(data_dir, 'temp'), exist_ok=True)
os.makedirs(os.path.join(data_dir, 'processed'), exist_ok=True)

# Use configured database URL or construct from data dir
database_url = os.getenv("DATABASE_URL")
if not database_url:
    db_path = os.path.join(data_dir, 'documents.db')
    database_url = f"sqlite:///{db_path}"

print(f"Using data directory: {data_dir}")  # Debug print

# Construct database path if not provided via URL
db_path = os.path.join(data_dir, 'documents.db') if not database_url else None
if db_path:
    print(f"Database path: {db_path}")  # Debug print

print(f"Initializing database at: {database_url}")  # Temporary debug print

engine = create_engine(database_url)
SessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(engine)
