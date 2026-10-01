from fastapi import FastAPI
from dotenv import load_dotenv


load_dotenv()


app = FastAPI()

@app.post("/enrich")
async def enrich():
    return {
        "status": 200
    }

@app.get("/get_suppliers")
async def get_suppliers():
    return {
        "status": 200
    }