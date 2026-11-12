from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from app.auth import router as auth_router
from app.admin_officer import admin_router, officer_router
from app.ai_assistant import router as ai_router
from app.database import PROJECT_ROOT, get_connection, initialize_database
from app.grievances import router as grievances_router
from app.public_services import router as public_services_router


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

app = FastAPI(
    title="CM Kerala Grievance Portal",
    description="Independent demonstration of a citizen grievance-management service. Not an official Government of Kerala service.",
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
app.include_router(auth_router)
app.include_router(ai_router)
app.include_router(grievances_router)
app.include_router(admin_router)
app.include_router(officer_router)
app.include_router(public_services_router)


@app.on_event("startup")
async def startup_event():
    initialize_database()


@app.get("/", include_in_schema=False)
async def home(request: Request):
    with get_connection() as connection:
        stats = connection.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN status = 'Resolved' THEN 1 ELSE 0 END) AS resolved,
                   SUM(CASE WHEN status IN ('In Progress', 'Reopened')
                       THEN 1 ELSE 0 END) AS in_progress
            FROM grievances
            """
        ).fetchone()
        departments = connection.execute(
            """
            SELECT departments.name, departments.description,
                   COUNT(grievances.id) AS grievance_count
            FROM departments
            LEFT JOIN grievances
              ON grievances.assigned_department_id = departments.id
            GROUP BY departments.id
            ORDER BY grievance_count DESC, departments.name
            LIMIT 3
            """
        ).fetchall()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "stats": {
                "total": stats["total"] or 0,
                "resolved": stats["resolved"] or 0,
                "in_progress": stats["in_progress"] or 0,
            },
            "featured_departments": departments,
        },
    )


@app.get("/about", include_in_schema=False)
async def about_page(request: Request):
    return templates.TemplateResponse(request=request, name="about.html", context={})


@app.get("/how-it-works", include_in_schema=False)
async def how_it_works_page(request: Request):
    return templates.TemplateResponse(request=request, name="how_it_works.html", context={})


@app.get("/departments", include_in_schema=False)
async def departments_page(request: Request):
    with get_connection() as connection:
        departments = connection.execute(
            "SELECT name, description FROM departments ORDER BY id"
        ).fetchall()
    return templates.TemplateResponse(
        request=request,
        name="departments.html",
        context={"departments": departments},
    )


@app.get("/contact", include_in_schema=False)
async def contact_page(request: Request):
    return templates.TemplateResponse(request=request, name="contact.html", context={})


@app.get("/faq", include_in_schema=False)
async def faq_page(request: Request):
    return templates.TemplateResponse(request=request, name="faq.html", context={})


@app.get("/login", include_in_schema=False)
async def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={},
    )


@app.get("/register", include_in_schema=False)
async def register_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="register.html",
        context={},
    )


@app.get("/citizen/dashboard", include_in_schema=False)
async def citizen_dashboard_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="citizen_dashboard.html",
        context={},
    )


@app.get("/citizen/grievances/new", include_in_schema=False)
async def new_grievance_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="grievance_form.html",
        context={},
    )


@app.get("/citizen/track", include_in_schema=False)
async def track_grievance_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="track_grievance.html",
        context={},
    )


@app.get("/admin/dashboard", include_in_schema=False)
async def admin_dashboard_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="admin_dashboard.html",
        context={},
    )


@app.get("/officer/dashboard", include_in_schema=False)
async def officer_dashboard_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="officer_dashboard.html",
        context={},
    )


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}


@app.get("/api/departments", tags=["departments"])
async def list_departments():
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, name, description FROM departments ORDER BY id"
        ).fetchall()
    return [dict(row) for row in rows]
