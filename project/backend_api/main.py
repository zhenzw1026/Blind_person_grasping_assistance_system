from __future__ import annotations

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from backend_api.routes import router

app = FastAPI(title="Grasp Assist API", version="0.1.0")

app.add_middleware(
	CORSMiddleware,
	allow_origins=[
		"http://localhost:3000",
		"http://127.0.0.1:3000",
	],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def root() -> dict[str, str]:
	return {"message": "Grasp Assist API is running", "health": "/api/health", "docs": "/docs"}


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
	return Response(status_code=204)
