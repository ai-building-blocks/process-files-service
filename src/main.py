from fastapi import FastAPI
from .api.routes import router

app = FastAPI(title="S3 Document Processor")
app.include_router(router)
