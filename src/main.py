from fastapi import FastAPI
from .api.routes import router

app = FastAPI(title="Document Processor Service")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}

app.include_router(router, prefix="/api")
