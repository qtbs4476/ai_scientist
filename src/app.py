
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .mock_engine import (
    add_feedback,
    build_report,
    get_research,
    list_questions,
    list_researches,
    report_to_markdown,
    start_research,
    stop_research,
    stream_research,
)

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "web"

app = FastAPI(title="AI Scientist Mock Backend V2", version="0.2.0")
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

class StartBody(BaseModel):
    question_id: int

class FeedbackBody(BaseModel):
    message: str = Field(min_length=1, max_length=4000)

@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-store"})

@app.get("/report/{research_id}")
def report_page(research_id: str):
    if not get_research(research_id):
        raise HTTPException(status_code=404, detail="Research not found")
    return FileResponse(FRONTEND / "report.html", headers={"Cache-Control": "no-store"})

@app.get("/api/health")
def health():
    return {"ok": True, "mode": "mock", "storage": "sqlite", "version": "0.2.0"}

@app.get("/api/questions")
def questions(q: str = Query(default=""), category: str = Query(default="")):
    rows = list_questions(q=q, category=category)
    return {"items": rows, "total": len(rows)}

@app.get("/api/research")
def research_list():
    return {"items": list_researches()}

@app.post("/api/research/start")
def research_start(body: StartBody):
    try:
        research = start_research(body.question_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Question not found")
    return {
        "research_id": research["id"],
        "status": research["status"],
        "question": research["question"],
        "stream_url": f"/api/research/{research['id']}/stream?reason=start",
    }

@app.get("/api/research/{research_id}")
def research_get(research_id: str):
    research = get_research(research_id)
    if not research:
        raise HTTPException(status_code=404, detail="Research not found")
    return research

@app.get("/api/research/{research_id}/stream")
async def research_stream(
    research_id: str,
    reason: str = Query(default="start", pattern="^(start|feedback)$"),
):
    if not get_research(research_id):
        raise HTTPException(status_code=404, detail="Research not found")
    return StreamingResponse(
        stream_research(research_id, reason=reason),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@app.post("/api/research/{research_id}/feedback")
def research_feedback(research_id: str, body: FeedbackBody):
    if not get_research(research_id):
        raise HTTPException(status_code=404, detail="Research not found")
    return add_feedback(research_id, body.message)

@app.post("/api/research/{research_id}/stop")
def research_stop(research_id: str):
    if not get_research(research_id):
        raise HTTPException(status_code=404, detail="Research not found")
    return stop_research(research_id)

@app.get("/api/research/{research_id}/result")
def research_result(research_id: str):
    research = get_research(research_id)
    if not research:
        raise HTTPException(status_code=404, detail="Research not found")
    return {
        "research_id": research_id,
        "status": research["status"],
        "result": research.get("result"),
    }

@app.get("/api/research/{research_id}/report")
def research_report(research_id: str):
    if not get_research(research_id):
        raise HTTPException(status_code=404, detail="Research not found")
    return JSONResponse(build_report(research_id), headers={"Cache-Control": "no-store"})

@app.get("/api/research/{research_id}/report.md")
def research_report_markdown(research_id: str):
    if not get_research(research_id):
        raise HTTPException(status_code=404, detail="Research not found")
    report = build_report(research_id)
    content = "\ufeff" + report_to_markdown(report)
    filename = f"ai-scientist-report-{research_id}.md"
    return PlainTextResponse(
        content,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
