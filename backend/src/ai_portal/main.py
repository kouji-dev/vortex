from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_portal.config import get_settings

settings = get_settings()

app = FastAPI(title="AI Portal API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
