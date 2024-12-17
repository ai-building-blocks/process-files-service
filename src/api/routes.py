from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from ..models.documents import SessionLocal
from ..services.s3_service import S3Service
from typing import List, Optional

router = APIRouter()
s3_service = S3Service()

@router.get("/files")
async def list_files(source: str, session: Session = SessionLocal()):
    if source not in ["bucket", "parsed"]:
        raise HTTPException(400, "Invalid source parameter")
    
    if source == "bucket":
        return await s3_service.list_files()
    else:
        return await s3_service.list_processed_files(session)

@router.get("/files/{file_id}")
async def get_file(file_id: str, source: str, session: Session = SessionLocal()):
    if source not in ["bucket", "parsed"]:
        raise HTTPException(400, "Invalid source parameter")
    
    if source == "bucket":
        return await s3_service.get_file(file_id)
    else:
        return await s3_service.get_processed_file(file_id, session)

@router.get("/files/status")
async def get_files_status(session: Session = SessionLocal()):
    return await s3_service.get_files_status(session)
