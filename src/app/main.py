from fastapi import FastAPI
from .db import check_db

app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/db-ping")
def db_ping():
    return {"db": check_db()}
