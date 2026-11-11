import socket

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import auth, tasks

app = FastAPI()
app.include_router(auth.router)
app.include_router(tasks.router)


@app.get("/health")
def health():
    return {"status": "ok", "instance": socket.gethostname()}


app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
