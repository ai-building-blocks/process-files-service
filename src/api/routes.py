from fastapi import APIRouter, HTTPException, Depends
import httpx
from sqlalchemy.orm import Session
from ..models.documents import SessionLocal
from ..services.s3_service import S3Service
from typing import List, Dict
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
    return await s3_service.get_files_status(db)

@router.get("/files/{file_id}", response_model=FileResponse)
async def get_file(file_id: str, source: str, db: Session = Depends(get_db)):
    """Get details for a specific file"""
    if source not in ["bucket", "parsed"]:
        raise HTTPException(400, "Invalid source parameter")
    
    if source == "bucket":
        return await s3_service.get_file(file_id)
    else:
        return await s3_service.get_processed_file(file_id, db)

@router.post("/files/{file_id}/process", response_model=ProcessingResponse)
async def process_file(file_id: str, db: Session = Depends(get_db)):
    """Process a specific file by ID"""
    try:
        result = await s3_service.process_single_file(file_id, db)
        return {"status": "success", "message": f"File {file_id} processed successfully"}
    except Exception as e:
        raise HTTPException(500, f"Error processing file: {str(e)}")

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
