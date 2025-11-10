from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.chat import router as chat_router
from app.api.commit import router as commit_router
from app.api.export import router as export_router
from app.api.files import router as files_router
from app.api.graph import router as graph_router
from app.api.notes import router as notes_router
from app.api.upload import router as upload_router

app = FastAPI(title="OVC Simple App", version="0.1.0")
app.include_router(chat_router, prefix="/api")
app.include_router(commit_router, prefix="/api")
app.include_router(notes_router, prefix="/api")
app.include_router(export_router, prefix="/api")
app.include_router(graph_router, prefix="/api")
app.include_router(upload_router, prefix="/api")
app.include_router(files_router)

app.mount("/static", StaticFiles(directory="simple_app/static"), name="static")
templates = Jinja2Templates(directory="simple_app/templates")


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse("editor.html", {"request": request, "note_id": None})


@app.get("/notes")
def notes_page(request: Request):
    return templates.TemplateResponse("notes.html", {"request": request})


@app.get("/notes/{note_id}")
def note_page(request: Request, note_id: str):
    return templates.TemplateResponse("editor.html", {"request": request, "note_id": note_id})


@app.get("/graph")
def graph_page(request: Request):
    return templates.TemplateResponse("graph.html", {"request": request})
