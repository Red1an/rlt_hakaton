from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from sqlalchemy import (
    select,
    or_,
    and_
)
from database import (
    database,
    SuppliersModel,
    OKPDModel
)
from .requests import (
    GetSuppliersRequest,
    FindOKPDRequest
)
from .routes import router as match_router


load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.init()
    yield
    print("Shutting down...")


app = FastAPI(lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(match_router)


@app.post("/enrich")
async def enrich():
    # worker run: search for new suppliers + search suppliers data + upd db

    # ml run: upd suppliers

    # /get_suppliers call for new suppliers

    return {
        "status": 200
    }

# @app.get("/get_suppliers")
# async def get_suppliers(request: GetSuppliersRequest):
#     limit: int = 10
#     offset: int = (request.page - 1) * limit
#     try:
#         async with database.session() as session:
#             stmt = select(
#                 SuppliersModel
#             ).limit(
#                 limit
#             ).offset(
#                 offset
#             ).where(
#                 and_(
#                     SuppliersModel.okpds.contains([request.okpd]),
#                     SuppliersModel.is_smp == request.is_smp,
#                     # SuppliersModel.source == request.source,
#                 )
#             )

#             res = await get_all_scalars(stmt)
#             suppliers = list(res)

#             return {
#                 "status": 200,
#                 "message": f"Get {len(suppliers)} suppliers",
#                 "suppliers": suppliers[offset : offset + limit],
#             }

#     except Exception as e:
#         return {
#             "status": 400,
#             "message": f"{e}",
#         }
    

# @app.get("/find_okpd")
# async def find_okpd(request: FindOKPDRequest):
#     _str: str = request._str

#     stmt = select(
#         OKPDModel
#     ).where(
#         or_(
#             OKPDModel.code.ilike(f"%{_str}%"),
#             OKPDModel.name.ilike(f"%{_str}%"),
#         )
#     )

#     try:
#         async with database.session() as session:
#             result = await get_all_scalars(stmt)

#     except Exception as e:
#         return {
#             "status": 400,
#             "message": f"{e}",
#         }

#     return {
#         "status": 200,
#         "name": result,
#     }