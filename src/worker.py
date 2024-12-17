from dotenv import load_dotenv
from models.documents import SessionLocal
from services.s3_service import S3Service

async def process_files():
    """Process new files once when requested"""
    load_dotenv()
    session = SessionLocal()
    s3_service = S3Service()
    
    try:
        await s3_service.process_new_files(session)
        return {"status": "success", "message": "Files processed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    # Worker now waits for API requests instead of running continuously
    import uvicorn
    from fastapi import FastAPI

    app = FastAPI()
    
    @app.post("/process")
    async def trigger_processing():
        return await process_files()
    
    uvicorn.run(app, host="0.0.0.0", port=8081)
