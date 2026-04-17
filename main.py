"""Job Description Generator — FastAPI app."""
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from pydantic import BaseModel
import asyncio
import uvicorn
import io
import re

from database import get_pool
from auth import hash_password, verify_password, create_token, get_current_user
from generator import generate_job_description
from pdf_maker import make_pdf
from scraper import scrape_company, fetch_logo, extract_brand_colors
from billing import FREE_MONTHLY_LIMIT, create_checkout_session, create_portal_session, handle_webhook

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


# ── Helpers ────────────────────────────────────────────────────
async def _get_user_row(user_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)

async def _monthly_count(user_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """SELECT COUNT(*) FROM job_descriptions
               WHERE user_id = $1
               AND created_at >= date_trunc('month', NOW())""",
            user_id,
        )


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


@app.get("/api/debug/scrape")
async def debug_scrape(url: str):
    logo, colors = await asyncio.gather(fetch_logo(url), extract_brand_colors(url))
    return {
        "logo": f"{len(logo)} bytes" if logo else None,
        "colors": colors,
    }


@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html") as f:
        return f.read()

@app.get("/billing/success", response_class=HTMLResponse)
async def billing_success(session_id: str):
    """Handle successful Stripe checkout — upgrade user plan."""
    import stripe, os
    stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == "paid":
            user_id = int(session.metadata["user_id"])
            plan = session.metadata["plan"]
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET plan=$1, stripe_customer_id=$2, stripe_subscription_id=$3 WHERE id=$4",
                    plan, session.customer, session.subscription, user_id,
                )
    except Exception:
        pass
    with open("static/index.html") as f:
        return f.read()


# ── Auth ───────────────────────────────────────────────────────
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


# ── Billing ────────────────────────────────────────────────────
@app.get("/api/billing/status")
async def billing_status(user_id: int = Depends(get_current_user)):
    user = await _get_user_row(user_id)
    count = await _monthly_count(user_id)
    plan = user["plan"] or "free"
    return {
        "plan": plan,
        "monthly_count": count,
        "monthly_limit": FREE_MONTHLY_LIMIT if plan == "free" else None,
    }


@app.post("/api/billing/checkout")
async def billing_checkout(plan: str, request: Request, user_id: int = Depends(get_current_user)):
    if plan not in ("pro", "team"):
        raise HTTPException(status_code=400, detail="Invalid plan.")
    user = await _get_user_row(user_id)
    base_url = str(request.base_url).rstrip("/")
    url = create_checkout_session(plan, user_id, user["email"], base_url)
    return {"url": url}


@app.get("/api/billing/portal")
async def billing_portal(request: Request, user_id: int = Depends(get_current_user)):
    user = await _get_user_row(user_id)
    if not user["stripe_customer_id"]:
        raise HTTPException(status_code=400, detail="No active subscription.")
    base_url = str(request.base_url).rstrip("/")
    url = create_portal_session(user["stripe_customer_id"], base_url)
    return {"url": url}


@app.post("/api/billing/webhook")
async def billing_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    result = handle_webhook(payload, sig)
    if result:
        pool = await get_pool()
        async with pool.acquire() as conn:
            if "user_id" in result:
                await conn.execute(
                    "UPDATE users SET plan=$1, stripe_customer_id=$2, stripe_subscription_id=$3 WHERE id=$4",
                    result["plan"], result["customer_id"], result["subscription_id"], result["user_id"],
                )
            else:
                # Subscription cancelled — find user by customer ID
                await conn.execute(
                    "UPDATE users SET plan='free', stripe_subscription_id=NULL WHERE stripe_customer_id=$1",
                    result["customer_id"],
                )
    return {"ok": True}


# ── Generate ───────────────────────────────────────────────────
@app.post("/api/generate")
async def generate(body: GenerateRequest, user_id: int = Depends(get_current_user)):
    user = await _get_user_row(user_id)
    plan = user["plan"] or "free"

    if plan == "free":
        count = await _monthly_count(user_id)
        if count >= FREE_MONTHLY_LIMIT:
            raise HTTPException(
                status_code=402,
                detail=f"Free plan limit of {FREE_MONTHLY_LIMIT} job descriptions per month reached. Upgrade to continue.",
            )

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


# ── History ────────────────────────────────────────────────────
@app.get("/api/history")
async def history(user_id: int = Depends(get_current_user)):
    user = await _get_user_row(user_id)
    if (user["plan"] or "free") == "free":
        raise HTTPException(status_code=403, detail="upgrade_required")

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, company_name, company_website, job_title, created_at
               FROM job_descriptions WHERE user_id = $1
               ORDER BY created_at DESC""",
            user_id,
        )
    return [
        {
            "id": r["id"],
            "company_name": r["company_name"],
            "company_website": r["company_website"],
            "job_title": r["job_title"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


# ── PDF Download ───────────────────────────────────────────────
@app.get("/api/history/{jd_id}/pdf")
async def download_pdf(jd_id: int, user_id: int = Depends(get_current_user)):
    user = await _get_user_row(user_id)
    if (user["plan"] or "free") == "free":
        raise HTTPException(status_code=403, detail="upgrade_required")

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM job_descriptions WHERE id = $1 AND user_id = $2",
            jd_id, user_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Not found.")
    website = (row["company_website"] or "").strip()
    logo_bytes, brand_colors = None, None
    if website:
        try:
            logo_bytes, brand_colors = await asyncio.gather(
                fetch_logo(website),
                extract_brand_colors(website),
            )
        except Exception:
            pass
    pdf = make_pdf(row["job_title"], row["company_name"], row["generated_text"], logo_bytes, brand_colors)
    filename = re.sub(r"[^\w\s\-.]", "", f"{row['company_name']} - {row['job_title']}.pdf")
    return StreamingResponse(
        io.BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
