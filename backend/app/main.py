import socket

from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
def health():
    return {"status": "ok", "instance": socket.gethostname()}