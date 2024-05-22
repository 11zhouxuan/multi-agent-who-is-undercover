from fastapi import FastAPI, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from game.main import router as game_router

app = FastAPI(title="Multi agent who is undercover")

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(game_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", status_code=status.HTTP_302_FOUND)
def index():
    return RedirectResponse("static/index.html")
