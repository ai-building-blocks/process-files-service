from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from ..utils.logging import get_logger, log_api_error
import httpx
import asyncio
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
    background_tasks: BackgroundTasks,
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

        # Create or update document record
        if request.identifier_type == "filename":
            # Check for existing document by filename
            doc = db.query(Document).filter_by(original_filename=identifier).first()
            if not doc:
                doc = Document(
                    id=process_id,
                    original_filename=identifier,
                    processed_filename="",
                    version="1.0",
                    status="queued",  # Always start with queued
                    created_at=datetime.utcnow()
                )
                db.add(doc)
        else:
            # Look up by ID
            doc = db.query(Document).filter_by(id=identifier).first()
            if not doc:
                raise HTTPException(status_code=404, detail=f"No document found with ID {identifier}")
            # Reset status to queued for reprocessing
            doc.status = "queued"
            doc.error_message = None  # Clear any previous errors
            
        doc.s3_last_modified = datetime.utcnow()
        db.commit()

        # Add processing to background tasks
        s3_service = S3Service()
        if request.identifier_type == "filename":
            file_path = f"{s3_service.source_prefix}{identifier}"
        else:
            # Look up original filename from database using ID
            orig_doc = db.query(Document).filter_by(id=identifier).first()
            if not orig_doc:
                raise FileNotFoundError(f"No file found with ID {identifier}")
            file_path = orig_doc.original_filename

        # Get file metadata from S3
        try:
            response = s3_service.s3_client.get_object(
                Bucket=s3_service.source_bucket,
                Key=file_path
            )
            obj = {
                "Key": file_path,
                "LastModified": response['LastModified'],
                "Content": response['Body'].read()
            }
        except Exception as e:
            doc.status = "failed"
            doc.error_message = f"Failed to get file from S3: {str(e)}"
            db.commit()
            raise HTTPException(status_code=404, detail=str(e))

        # Update document status to queued before processing
        doc.status = "queued"
        doc.error_message = None
        db.commit()
            
        # Add to background tasks
        background_tasks.add_task(s3_service.process_single_file_background, obj, db)

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
        worker_url = os.getenv("WORKER_URL", "http://worker:8071")
        logger.info(f"Connecting to worker service at: {worker_url}")
        
        try:
            async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
                # Configure client with retries
                for attempt in range(3):
                    try:
                        logger.debug(f"Attempt {attempt + 1}: Sending request to worker: POST {worker_url}/process")
                        response = await client.post(
                            f"{worker_url}/process",
                            headers={"Content-Type": "application/json"}
                        )
                        logger.debug(f"Worker response status: {response.status_code}")
                        break
                    except httpx.ConnectError as e:
                        if attempt == 2:  # Last attempt
                            raise
                        logger.warning(f"Connection attempt {attempt + 1} failed, retrying... Error: {str(e)}")
                        await asyncio.sleep(1)  # Wait before retry
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
