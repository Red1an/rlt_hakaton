from fastapi import FastAPI
from dotenv import load_dotenv
from sqlalchemy import select
from typing import List
from contextlib import asynccontextmanager
from database import (
    database,
    SuppliersModel
)


load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init()
    yield
    # Код после yield — логика остановки
    print("Shutting down...")


app = FastAPI(lifespan=lifespan)


@app.post("/enrich")
async def enrich():
    return {
        "status": 200
    }

@app.get("/get_suppliers")
async def get_suppliers(limit: int = 100):
    async with database.session() as session:
        stmt = select(SuppliersModel).limit(limit)
        res = await session.execute(stmt)
        suppliers = list(res.scalars().all())
        return suppliers
    # return {
    #     "status": 200
    # }

@app.get("/parse")
async def parse():
    return {
        "status": 200
    }