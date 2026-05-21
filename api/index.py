from mangum import Mangum
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()


@app.get("/")
async def root():
    return HTMLResponse("<h1>It works!</h1>")


@app.get("/health")
async def health():
    return {"status": "ok"}


handler = Mangum(app)
