import socket

from fastapi import FastAPI

from app.routers import auth

app = FastAPI()
app.include_router(auth.router)


@app.get("/health")
def health():
    return {"status": "ok", "instance": socket.gethostname()}