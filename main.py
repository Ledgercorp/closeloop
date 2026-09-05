from fastapi import FastAPI

app = FastAPI(title="CloseLoop", version="0.1.0")


@app.get("/")
def root():
    return {
        "name": "CloseLoop",
        "status": "ok",
        "message": "CloseLoop verification service is live.",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}
