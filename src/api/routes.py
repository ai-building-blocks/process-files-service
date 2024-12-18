from fastapi import APIRouter, HTTPException, Depends
from ..utils.logging import get_logger, log_api_error
import httpx
from sqlalchemy.orm import Session
from ..models.documents import SessionLocal, Document
from ..services.s3_service import S3Service
from typing import List, Dict
import ulid
from pydantic import BaseModel, validator
from datetime import datetime
import os

class FileResponse(BaseModel):
    id: str
    filename: str
    status: str

class ProcessingResponse(BaseModel):
    status: str
    message: str

class TimeFilter(BaseModel):
    since: str  # Can be timestamp or ULID
    
    @validator('since')
    def validate_since(cls, v):
        # Try parsing as ULID first
        try:
            ulid.parse(v)
            return v
        except ValueError:
            # Try parsing as timestamp
            try:
                datetime.fromisoformat(v.replace('Z', '+00:00'))
                return v
            except ValueError:
                raise ValueError("since must be a valid ULID or ISO timestamp")

router = APIRouter()
logger = get_logger(__name__)

# Validate environment variables on startup
required_vars = [
    'DATA_DIR', 'TEMP_DIR', 'PROCESSED_DIR', 'DATABASE_URL',
    'S3_ENDPOINT', 'S3_ACCESS_KEY', 'S3_SECRET_KEY', 'SOURCE_BUCKET'
]
missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

s3_service = S3Service()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/files", response_model=List[FileResponse])
async def list_files(
    source: str = "bucket",
    since: str = None,
    db: Session = Depends(get_db)
):
    """
    List files from either source folder or processed folder
    source: 'bucket' for source folder, 'parsed' for processed folder
    """
    if source not in ["bucket", "parsed"]:
        raise HTTPException(400, "Invalid source parameter")
    
    try:
        if since:
            # Validate since parameter
            TimeFilter(since=since)
            if source == "bucket":
                return await s3_service.list_files(db, since=since)
            else:
                return await s3_service.list_processed_files(db, since=since)
        else:
            if source == "bucket":
                return await s3_service.list_files(db)
            else:
                return await s3_service.list_processed_files(db)
    except Exception as e:
        raise HTTPException(500, f"Error listing files: {str(e)}")

@router.get("/files/{process_id}/status", response_model=ProcessingResponse)
async def get_processing_status(
    process_id: str,
    db: Session = Depends(get_db)
):
    """Get status of a specific processing job"""
    doc = db.query(Document).filter_by(id=process_id).first()
    if not doc:
        raise HTTPException(404, "Processing job not found")
        
    return {
        "status": doc.status,
        "message": doc.error_message if doc.status == "failed" else f"Processing status: {doc.status}"
    }

@router.get("/status", response_model=Dict[str, str])
async def get_files_status(db: Session = Depends(get_db)):
    """Get processing status for all files"""
    try:
        return await s3_service.get_files_status(db)
    except Exception as e:
        log_api_error(logger, e, {
            "operation": "get_files_status"
        })
        raise HTTPException(
            status_code=500,
            detail="Error retrieving file status. Please try again later."
        )

@router.get("/files/{file_id}", response_model=FileResponse)
async def get_file(file_id: str, source: str, db: Session = Depends(get_db)):
    """Get details for a specific file"""
    if source not in ["bucket", "parsed"]:
        raise HTTPException(400, "Invalid source parameter")
    
    if source == "bucket":
        return await s3_service.get_file(file_id)
    else:
        return await s3_service.get_processed_file(file_id, db)

class ProcessFileRequest(BaseModel):
    """Request model for file processing"""
    identifier_type: str = "id"  # Either "id" or "filename"

    @validator('identifier_type')
    def validate_identifier_type(cls, v):
        if v not in ["id", "filename"]:
            raise ValueError('identifier_type must be either "id" or "filename"')
        return v

@router.post("/files/{identifier}/process", response_model=ProcessingResponse)
async def process_file(
    identifier: str,
    request: ProcessFileRequest = None,
    db: Session = Depends(get_db)
):
    """Process a specific file asynchronously"""
    # Generate new ULID for tracking
    process_id = str(ulid.new())
    
    try:
        if request is None:
            request = ProcessFileRequest()
            if '.' in identifier:
                request.identifier_type = "filename"

        # Create document record immediately
        doc = Document(
            id=process_id,
            original_filename=identifier if request.identifier_type == "filename" else None,
            processed_filename="",
            version="1.0",
            status="queued",
            created_at=datetime.utcnow(),
            s3_last_modified=datetime.utcnow()  # Set initial last_modified time
        )
        db.add(doc)
        db.commit()

        # Trigger processing in background
        worker_url = os.getenv("WORKER_URL", "http://worker:8081")
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{worker_url}/files/process",
                    json={
                        "process_id": process_id,
                        "identifier": identifier,
                        "identifier_type": request.identifier_type
                    },
                    timeout=30.0
                )
        except Exception as e:
            logger.error(f"Failed to queue processing: {str(e)}")
            doc.status = "failed"
            doc.error_message = "Failed to queue processing"
            db.commit()
            raise HTTPException(
                status_code=503,
                detail="Processing service unavailable"
            )

        return {
            "status": "accepted",
            "message": f"Processing queued with ID: {process_id}"
        }
    except FileNotFoundError as e:
        log_api_error(logger, e, {
            "identifier": identifier,
            "identifier_type": request.identifier_type,
            "operation": "process_file"
        })
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        log_api_error(logger, e, {
            "identifier": identifier,
            "identifier_type": request.identifier_type,
            "operation": "process_file"
        })
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        log_api_error(logger, e, {
            "identifier": identifier,
            "identifier_type": request.identifier_type,
            "operation": "process_file"
        })
        raise HTTPException(
            status_code=500,
            detail=f"Internal error processing file. Please contact support if the issue persists."
        )

@router.post("/process", response_model=ProcessingResponse)
async def trigger_processing():
    """Trigger the worker to process new files"""
    try:
        # Just trigger the worker asynchronously and return immediately
        worker_url = os.getenv("WORKER_URL", "http://worker:8081")
        try:
            async with httpx.AsyncClient() as client:
                # Add longer timeout and retries
                await client.post(
                    f"{worker_url}/process",
                    timeout=30.0,
                    headers={"Content-Type": "application/json"}
                )
        except Exception as e:
            logger.error(f"Failed to connect to worker service at {worker_url}: {str(e)}")
            raise HTTPException(
                status_code=503,
                detail="Worker service unavailable. Please try again later."
            )
            
        return {
            "status": "accepted",
            "message": "Processing triggered successfully"
        }
    except Exception as e:
        raise HTTPException(500, f"Error triggering processing: {str(e)}")
