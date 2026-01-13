"""
GhostReply - Main Entry Point
FastAPI server with background monitor
Runs Playwright in separate process to avoid Windows asyncio issues
"""
import asyncio
import subprocess
import sys
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from database import init_db
from routes import router

# Track monitor process
monitor_process = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    global monitor_process
    
    # Initialize database
    init_db()
    print("✅ Database initialized")
    
    yield
    
    # Cleanup - stop monitor if running
    if monitor_process and monitor_process.poll() is None:
        monitor_process.terminate()


app = FastAPI(
    title="GhostReply",
    description="AI-powered X/Twitter engagement assistant",
    version="1.0.0",
    lifespan=lifespan
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router)


# --- Control Endpoints ---

@app.get("/")
async def root():
    """Health check"""
    running = monitor_process is not None and monitor_process.poll() is None
    return {
        "name": "GhostReply",
        "status": "running",
        "monitor_active": running
    }


@app.post("/control/start")
async def start_monitor(headless: bool = False, auto_post: bool = False):
    """Start the tweet monitor in separate process"""
    global monitor_process
    
    # Check if already running
    if monitor_process and monitor_process.poll() is None:
        return {"status": "already running"}
    
    try:
        # Start monitor.py as separate process
        cmd = [sys.executable, "monitor.py"]
        if auto_post:
            cmd.append("--auto-post")
        
        monitor_process = subprocess.Popen(
            cmd,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
        )
        
        return {"status": "started", "pid": monitor_process.pid, "auto_post": auto_post}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


@app.post("/control/stop")
async def stop_monitor():
    """Stop the tweet monitor"""
    global monitor_process
    
    if monitor_process:
        if monitor_process.poll() is None:
            monitor_process.terminate()
            try:
                monitor_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                monitor_process.kill()
        monitor_process = None
    
    return {"status": "stopped"}


@app.get("/control/status")
async def get_status():
    """Get monitor status"""
    running = monitor_process is not None and monitor_process.poll() is None
    return {
        "running": running,
        "auto_post": False,
        "replies_this_hour": 0
    }


@app.post("/control/post/{reply_id}")
async def post_reply_now(reply_id: int):
    """Manually post an approved reply"""
    from database import SessionLocal, Reply
    
    running = monitor_process is not None and monitor_process.poll() is None
    if not running:
        return {"status": "error", "message": "Monitor not running"}
    
    # Update status in DB
    db = SessionLocal()
    try:
        reply = db.query(Reply).filter(Reply.id == reply_id).first()
        if not reply:
            return {"status": "error", "message": "Reply not found"}
        
        reply.status = "approved"
        db.commit()
        return {"status": "approved", "message": "Reply queued for posting"}
    finally:
        db.close()


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
