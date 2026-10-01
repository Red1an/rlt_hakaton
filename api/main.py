from fastapi import FastAPI
from dotenv import load_dotenv
from sqlalchemy import select
from typing import List
from contextlib import asynccontextmanager
from database import (
    database,
    SuppliersModel
)
from requests import (
    GetSuppliersRequest,
    FindOKPDRequest
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
async def get_suppliers(request: GetSuppliersRequest):
    limit: int = 10
    offset: int = (request.page - 1) * limit
    try:
        async with database.session() as session:
            stmt = select(
                SuppliersModel
            ).limit(
                limit
            ).offset(
                offset
            ).where(
                SuppliersModel.okpds.contains([request.okpd])
            )

            res = await get_all_scalars(stmt)
            suppliers = list(res)

            return {
                "status": 200,
                "message": f"Get {len(suppliers)} suppliers",
                "suppliers": suppliers[offset : offset + limit],
            }

    except Exception as e:
        return {
            "status": 400,
            "message": f"{e}",
        }
    

@app.get("/parse")
async def parse():
    return {
        "status": 200
    }

@app.get("/find_okpd")
async def find_okpd(request: FindOKPDRequest):
    _str: str = request._str

    stmt = select(
        OKPDModel
    ).where(
        or_(
            OKPDModel.code.ilike(f"%{_str}%"),
            OKPDModel.name.ilike(f"%{_str}%"),
        )
    )

    try:
        async with database.session() as session:
            result = await get_all_scalars(stmt)

    except Exception as e:
        return {
            "status": 400,
            "message": f"{e}",
        }

    return {
        "status": 200,
        "name": result,
    }