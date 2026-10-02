from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from sqlalchemy import (
    select,
    or_,
    and_,
    func,
    distinct
)
from database import (
    database,
    SuppliersModel,
    OKPDModel,
    AnnouncementModel,
    BidModel,
    LotModel
)
from .requests import (
    GetSuppliersRequest,
    FindOKPDRequest,
    GraphsRequest
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


@app.get("/graphs/activity")
async def graphs_activity(request: GraphsRequest):
    stmt = (
        select(
            AnnouncementModel.publish_date.label("date"),
            func.count().label("engages"),
            func.count().filter(BidModel.is_winner).label("wins"),
        )
        .select_from(BidModel)
        .join(AnnouncementModel, AnnouncementModel.lot_id == BidModel.lot_id)
        .where(BidModel.supplier_inn == request.inn)
        .group_by(AnnouncementModel.publish_date)
        .order_by(AnnouncementModel.publish_date)
    )

    try:
        async with database.session() as session:
            rows = (await session.execute(stmt)).all()
    except Exception as e:
        return {
            "status": 400,
            "message": f"{e}",
        }

    return {
        "status": 200,
        "inn": request.inn,
        "points": [
            {
                "date": row.date.isoformat(),
                "wins": row.wins,
                "engages": row.engages,
            }
            for row in rows
        ],
        "wins": sum(row.wins for row in rows),
        "engages": sum(row.engages for row in rows),
    }


@app.get("/graphs/okpd")
async def graphs_okpd(request: GraphsRequest):
    stmt = (
        select(
            LotModel.okpd_code.label("code"),
            OKPDModel.name.label("name"),
            func.count(distinct(BidModel.lot_id)).label("engages"),
            func.count(distinct(BidModel.lot_id)).filter(BidModel.is_winner).label("wins"),
        )
        .select_from(BidModel)
        .join(LotModel, LotModel.lot_id == BidModel.lot_id)
        .outerjoin(OKPDModel, OKPDModel.code == LotModel.okpd_code)
        .where(BidModel.supplier_inn == request.inn)
        .group_by(LotModel.okpd_code, OKPDModel.name)
        .order_by(func.count(distinct(BidModel.lot_id)).desc())
    )

    try:
        async with database.session() as session:
            rows = (await session.execute(stmt)).all()
    except Exception as e:
        return {
            "status": 400,
            "message": f"{e}",
        }

    total_engages = sum(row.engages for row in rows)
    total_wins = sum(row.wins for row in rows)

    return {
        "status": 200,
        "inn": request.inn,
        "items": [
            {
                "code": row.code,
                "name": row.name,
                "wins": row.wins,
                "engages": row.engages,
                "percent": round(100 * row.engages / total_engages, 2) if total_engages else 0.0,
                "win_percent": round(100 * row.wins / total_wins, 2) if total_wins else 0.0,
            }
            for row in rows
        ],
        "wins": total_wins,
        "engages": total_engages,
    }
