import os
import time
import shutil
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="HTTP/1.1 File Transfer Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FILES_DIR = Path("./files")
UPLOADS_DIR = Path("./uploads")

os.makedirs(FILES_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

@app.get("/files/{filename}")
async def get_file(filename: str):
    """
    Endpoint to download a file from the server via GET request
    """
    file_path = FILES_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File {filename} not found")
    file_size = os.path.getsize(file_path)
    print(f"Serving file {filename} ({file_size} bytes)")
    return FileResponse(path=file_path, filename=filename)

@app.post("/upload/{filename}")
async def upload_file(filename: str, file: UploadFile = File(...)):
    """
    Endpoint to upload a file to the server via POST request
    """
    start_time = time.time()
    file_path = UPLOADS_DIR / filename
    
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        file.file.close()
    
    end_time = time.time()
    transfer_time = end_time - start_time
    file_size = os.path.getsize(file_path)
    throughput = file_size / transfer_time if transfer_time > 0 else 0
    
    print(f"Received file {filename} ({file_size} bytes) in {transfer_time:.4f}s")
    print(f"Upload throughput: {throughput/1024:.2f} KB/s")
    
    return {
        "filename": filename,
        "size": file_size,
        "transfer_time": transfer_time,
        "throughput": throughput
    }

@app.get("/list")
async def list_files():
    """
    Endpoint to list available files
    """
    if not FILES_DIR.exists():
        return {"files": []}
    
    files = [f.name for f in FILES_DIR.iterdir() if f.is_file()]
    return {"files": files}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000)