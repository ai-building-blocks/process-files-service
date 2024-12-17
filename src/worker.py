from dotenv import load_dotenv
from src.models.documents import SessionLocal
from src.services.s3_service import S3Service

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
    import os
    import uvicorn
    from fastapi import FastAPI

    app = FastAPI()
    
    @app.post("/process")
    async def trigger_processing():
        """Process files endpoint with proper error handling"""
        try:
            result = await process_files()
            return result
        except Exception as e:
            return {"status": "error", "message": str(e)}, 500
            
    @app.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {"status": "healthy"}
    
    uvicorn.run(
        app, 
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("WORKER_PORT", 8081)),
        log_level="info"
    )
