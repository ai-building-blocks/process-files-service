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

engine = create_engine(os.getenv("DATABASE_URL"))
SessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(engine)
