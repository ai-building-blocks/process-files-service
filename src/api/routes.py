from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
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
    background_tasks: BackgroundTasks,
    request: ProcessFileRequest = None,
    db: Session = Depends(get_db)
):
    # Auto-detect identifier type if not specified
    if request is None:
        request = ProcessFileRequest()
        # If identifier contains file extension, assume it's a filename
        if '.' in identifier:
            request.identifier_type = "filename"
    """
    Process a specific file by ID or filename
    
    Args:
        identifier: Either a ULID (if identifier_type="id") or the original filename
        request: Optional request body specifying identifier_type ("id" or "filename")
        
    Returns:
        ProcessingResponse with status and message
        
    Raises:
        404: File not found
        403: Permission denied
        500: Internal server error
    """
    try:
        if request.identifier_type == "filename":
            # If identifier is filename, add source prefix
            file_path = f"{s3_service.source_prefix}{identifier}"
        else:
            # Look up original filename from database using ID
            doc = db.query(Document).filter_by(id=identifier).first()
            if not doc:
                raise FileNotFoundError(f"No file found with ID {identifier}")
            file_path = doc.original_filename

        # Start background processing and update initial status
        background_tasks.add_task(s3_service.process_single_file, file_path, db)
        
        return ProcessingResponse(
            status="accepted",
            message=f"Processing started for file (identifier: {identifier})"
        )
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
        async with httpx.AsyncClient(timeout=30.0) as client:
            worker_url = os.getenv("WORKER_URL", "http://worker:8081")
            response = await client.post(f"{worker_url}/process")
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Worker error: {response.text}"
                )
    except httpx.TimeoutException:
        raise HTTPException(504, "Worker processing timed out")
    except httpx.RequestError as e:
        raise HTTPException(502, f"Error connecting to worker: {str(e)}")
    except Exception as e:
        raise HTTPException(500, f"Error triggering processing: {str(e)}")
