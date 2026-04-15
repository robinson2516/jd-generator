"""Job Description Generator — FastAPI app."""
from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn
import io
import re

from database import get_pool
from auth import hash_password, verify_password, create_token, get_current_user
from generator import generate_job_description
from pdf_maker import make_pdf
from scraper import scrape_company, fetch_logo

app = FastAPI(title="JD Generator")
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── Request models ─────────────────────────────────────────────
class RegisterRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class GenerateRequest(BaseModel):
    company_name: str
    job_title: str
    skills: str
    experience_level: str
    company_website: str = ""


# ── Routes ─────────────────────────────────────────────────────
@app.get("/api/debug")
async def debug():
    import os, traceback
    url = os.environ.get("DATABASE_URL", "NOT SET")
    masked = url[:30] + "..." if len(url) > 30 else url
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_ok = True
        db_error = None
    except Exception as e:
        db_ok = False
        db_error = traceback.format_exc()
    return {"db_ok": db_ok, "db_error": db_error, "url_prefix": masked}


@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html") as f:
        return f.read()


@app.post("/api/auth/register")
async def register(body: RegisterRequest):
    pool = await get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM users WHERE email = $1", body.email.lower()
        )
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered.")
        user = await conn.fetchrow(
            "INSERT INTO users (email, password_hash) VALUES ($1, $2) RETURNING id",
            body.email.lower(), hash_password(body.password),
        )
    token = create_token(user["id"])
    return {"token": token, "email": body.email.lower()}


@app.post("/api/auth/login")
async def login(body: LoginRequest):
    pool = await get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id, password_hash FROM users WHERE email = $1", body.email.lower()
        )
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = create_token(user["id"])
    return {"token": token, "email": body.email.lower()}


@app.post("/api/generate")
async def generate(body: GenerateRequest, user_id: int = Depends(get_current_user)):
    company_context = await scrape_company(body.company_website) if body.company_website else ""
    text = generate_job_description(
        body.company_name, body.job_title, body.skills, body.experience_level, company_context
    )
    pool = await get_pool()
    async with pool.acquire() as conn:
        record = await conn.fetchrow(
            """INSERT INTO job_descriptions
               (user_id, company_name, company_website, job_title, skills, experience_level, generated_text)
               VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id""",
            user_id, body.company_name, body.company_website or None,
            body.job_title, body.skills, body.experience_level, text,
        )
    return {"id": record["id"], "text": text}


@app.get("/api/history")
async def history(user_id: int = Depends(get_current_user)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, company_name, job_title, created_at
               FROM job_descriptions WHERE user_id = $1
               ORDER BY created_at DESC""",
            user_id,
        )
    return [
        {
            "id": r["id"],
            "company_name": r["company_name"],
            "job_title": r["job_title"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


@app.get("/api/history/{jd_id}/pdf")
async def download_pdf(jd_id: int, user_id: int = Depends(get_current_user)):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM job_descriptions WHERE id = $1 AND user_id = $2",
            jd_id, user_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Not found.")
    logo_bytes = await fetch_logo(row["company_website"]) if row["company_website"] else None
    pdf = make_pdf(row["job_title"], row["company_name"], row["generated_text"], logo_bytes)
    filename = re.sub(r"[^\w\s\-.]", "", f"{row['company_name']} - {row['job_title']}.pdf")
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
