from fastapi import APIRouter, HTTPException, Depends
import httpx
from sqlalchemy.orm import Session
from ..models.documents import SessionLocal
from ..services.s3_service import S3Service
from typing import List, Dict
from pydantic import BaseModel
import os

class FileResponse(BaseModel):
    id: str
    filename: str
    status: str

class ProcessingResponse(BaseModel):
    status: str
    message: str

router = APIRouter()
s3_service = S3Service()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/files", response_model=List[FileResponse])
async def list_files(source: str = "bucket", db: Session = Depends(get_db)):
    """
    List files from either source folder or processed folder
    source: 'bucket' for source folder, 'parsed' for processed folder
    """
    if source not in ["bucket", "parsed"]:
        raise HTTPException(400, "Invalid source parameter")
    
    try:
        if source == "bucket":
            return await s3_service.list_files()
        else:
            return await s3_service.list_processed_files(db)
    except Exception as e:
        raise HTTPException(500, f"Error listing files: {str(e)}")

@router.get("/files/{file_id}", response_model=FileResponse)
async def get_file(file_id: str, source: str, db: Session = Depends(get_db)):
    if source not in ["bucket", "parsed"]:
        raise HTTPException(400, "Invalid source parameter")
    
    if source == "bucket":
        return await s3_service.get_file(file_id)
    else:
        return await s3_service.get_processed_file(file_id, db)

@router.get("/files/status", response_model=Dict[str, str])
async def get_files_status(db: Session = Depends(get_db)):
    return await s3_service.get_files_status(db)

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
