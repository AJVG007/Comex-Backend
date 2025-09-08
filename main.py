from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
import requests
from requests.auth import HTTPDigestAuth
import datetime
import calendar

app = FastAPI()

# 🚀 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🔌 Mongo
client = MongoClient("mongodb://localhost:27017/")
db = client["passenger_flow"]
users_collection = db["users"]
statistics_collection = db["statistics"]

# 📦 Modelos
class LoginRequest(BaseModel):
    username: str
    password: str

# 👤 Admin por defecto
@app.on_event("startup")
def startup_event():
    admin = users_collection.find_one({"username": "admin"})
    if not admin:
        users_collection.insert_one({
            "username": "admin",
            "email": "jair.velasco@tecnosinergia.com",
            "password": "Admin123.",
            "created_at": datetime.datetime.utcnow()
        })

@app.get("/")
def root():
    return {"message": "Backend funcionando 🚀"}

# 🔐 Login (Mongo)
@app.post("/login")
def login(request: LoginRequest):
    user = users_collection.find_one({"username": request.username})
    if not user or user["password"] != request.password:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    return {"user": user["username"], "message": "Login exitoso"}

# 🧮 Helper para sumar listas (soporta listas anidadas)
def sum_counts(values):
    if values is None:
        return 0
    if not isinstance(values, list):
        try:
            return int(values)
        except Exception:
            return 0
    total = 0
    for v in values:
        if isinstance(v, list):
            total += sum((x or 0) for x in v)
        else:
            total += (v or 0)
    return int(total)

# ---------------------------------------
# 🔧 Helper para ejecutar el flujo en NVR
# ---------------------------------------
def fetch_from_nvr(base_url: str, username: str, password: str,
                   first_day: datetime.datetime, last_day: datetime.datetime):
    """Ejecuta PUT -> Progress -> GET contra un NVR y procesa los datos."""
    statistics = {
        "Num": 16,
        "IDs": [i for i in range(1, 17)],
        "StatisticsType": 2,
        "StatisticsUnit": 2,
        "Begin": int(first_day.timestamp()),
        "End": int(last_day.timestamp()),
    }

    # 1) PUT -> SearchID
    put_resp = requests.put(
        f"{base_url}/CustomTimeStart",
        json=statistics,
        auth=HTTPDigestAuth(username, password),
        timeout=10,
    )
    put_resp.raise_for_status()
    remote_response = put_resp.json()
    search_id = remote_response.get("Response", {}).get("Data", {}).get("SearchID")
    if not search_id:
        raise RuntimeError("No SearchID en respuesta del PUT")

    # 2) GET Progress
    progress_resp = requests.get(
        f"{base_url}/Progress?SearchID={search_id}",
        auth=HTTPDigestAuth(username, password),
        timeout=10,
    )
    progress_resp.raise_for_status()
    progress_data = progress_resp.json()
    percent = progress_data.get("Response", {}).get("Data", {}).get("Percent")

    stats_data = None
    processed_stats = []

    # 3) Si terminó, GET final y procesar
    if percent == 100:
        stats_resp = requests.get(
            f"{base_url}?SearchID={search_id}",
            auth=HTTPDigestAuth(username, password),
            timeout=10,
        )
        stats_resp.raise_for_status()
        stats_data = stats_resp.json()

        # ⚠️ La lista real viene en "PassengerFlowInfos"
        data_section = stats_data.get("Response", {}).get("Data", {}) or {}
        cams = data_section.get("PassengerFlowInfos")
        if cams is None:
            cams = data_section.get("List", [])  # fallback

        for cam in cams:
            enter_list = cam.get("EnterCountList", []) or []
            exit_list = cam.get("ExitCountList", []) or []

            # Totales
            enter_total = sum_counts(enter_list)
            exit_total = sum_counts(exit_list)

            # Procesar por día
            daily_stats = []
            for i in range(min(len(enter_list), len(exit_list))):
                day = (first_day + datetime.timedelta(days=i)).strftime("%Y-%m-%d")
                enter = enter_list[i] if i < len(enter_list) else 0
                exit_ = exit_list[i] if i < len(exit_list) else 0
                present = (enter or 0) - (exit_ or 0)
                daily_stats.append({
                    "day": day,
                    "enter": enter,
                    "exit": exit_,
                    "present": present
                })

            processed_stats.append({
                "ID": cam.get("ID"),
                "EnterTotal": enter_total,
                "ExitTotal": exit_total,
                "Daily": daily_stats
            })

        return {
            "search_id": search_id,
            "percent": percent,
            "final_statistics": stats_data,
            "processed_statistics": processed_stats,
            "begin": statistics["Begin"],
            "end": statistics["End"],
        }
    else:
        # Si no terminó, igual regresamos progreso
        return {
            "search_id": search_id,
            "percent": percent,
            "final_statistics": None,
            "processed_statistics": [],
            "begin": statistics["Begin"],
            "end": statistics["End"],
        }

# 📊 Fetch de estadísticas (mes actual) -> Ejecuta 9191 y 9192
@app.post("/statistics/fetch")
def fetch_statistics(request: LoginRequest):
    user = users_collection.find_one({"username": request.username})
    if not user or user["password"] != request.password:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")

    # Rango dinámico del mes actual (UTC local naive)
    now = datetime.datetime.now()
    first_day = datetime.datetime(now.year, now.month, 1, 0, 0, 0)
    last_day = datetime.datetime(
        now.year, now.month, calendar.monthrange(now.year, now.month)[1], 23, 59, 59
    )

    # NVRs a consultar (mismo endpoint, distinto puerto)
    primary_url = "http://201.139.102.51:9191/LAPI/V1.0/Channels/Smart/PassengerFlowStatistics"
    secondary_url = "http://201.139.102.51:9192/LAPI/V1.0/Channels/Smart/PassengerFlowStatistics"

    # --- 1) Ejecutar PRIMARIO (9191) y responder al front con este
    try:
        res_primary = fetch_from_nvr(
            base_url=primary_url,
            username=user["username"],
            password=user["password"],
            first_day=first_day,
            last_day=last_day,
        )

        # Guardar en Mongo (primario) con source {nvr_id, base_url}
        statistics_collection.insert_one({
            "username": user["username"],
            "search_id": res_primary["search_id"],
            "percent": res_primary["percent"],
            "final_statistics": res_primary["final_statistics"],
            "processed_statistics": res_primary["processed_statistics"],
            "created_at": datetime.datetime.utcnow(),
            "begin": res_primary["begin"],
            "end": res_primary["end"],
            "source": {
                "nvr_id": 1,
                "base_url": primary_url
            },
        })
    except Exception as e:
        # Si el primario falla, devolvemos 500 como antes
        raise HTTPException(status_code=500, detail=f"[PRIMARY {primary_url}] {str(e)}")

    # --- 2) Ejecutar SECUNDARIO (9192), guardar pero NO afectar respuesta
    try:
        res_secondary = fetch_from_nvr(
            base_url=secondary_url,
            username=user["username"],
            password=user["password"],
            first_day=first_day,
            last_day=last_day,
        )
        statistics_collection.insert_one({
            "username": user["username"],
            "search_id": res_secondary["search_id"],
            "percent": res_secondary["percent"],
            "final_statistics": res_secondary["final_statistics"],
            "processed_statistics": res_secondary["processed_statistics"],
            "created_at": datetime.datetime.utcnow(),
            "begin": res_secondary["begin"],
            "end": res_secondary["end"],
            "source": {
                "nvr_id": 2,
                "base_url": secondary_url
            },
        })
    except Exception as e:
        # Solo log lógico: NO rompemos la respuesta
        print(f"[SECONDARY {secondary_url}] Error: {e}")

    # --- Responder SOLO con el primario (para no romper el front)
    return {
        "search_id": res_primary["search_id"],
        "progress": {"Response": {"Data": {"Percent": res_primary["percent"]}}},
        "final_statistics": res_primary["final_statistics"],
        "processed_statistics": res_primary["processed_statistics"],
        "begin": res_primary["begin"],
        "end": res_primary["end"],
    }

# 🗂 Última estadística
@app.get("/statistics/latest")
def get_latest_statistics():
    doc = statistics_collection.find_one(sort=[("created_at", -1)])
    if not doc:
        raise HTTPException(status_code=404, detail="No hay estadísticas aún")
    doc["_id"] = str(doc["_id"])
    return doc
