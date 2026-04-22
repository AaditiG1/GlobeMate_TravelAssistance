from fastapi import APIRouter, Form, Depends, Request
from sqlalchemy.orm import Session
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from passlib.hash import argon2
from dotenv import load_dotenv
from app.database import SessionLocal
from app.models import Trip, User
from authlib.integrations.starlette_client import OAuth
import os
from passlib.context import CryptContext
import secrets

load_dotenv()

router = APIRouter(prefix="/auth", tags=["Authentication"])
# Use your frontend folder
templates = Jinja2Templates(directory="frontend")

# Temporary in-memory storage for reset tokens
password_reset_tokens = {}

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
# ----------------------
# Database session dependency
# ----------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ----------------------
# Register endpoint
# ----------------------
@router.post("/register")
def register(
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # Check if email already exists
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        return JSONResponse({"message": "Email already exists"}, status_code=400)
    # Hash the password before saving
    hashed_password = pwd_context.hash(password)
    # Create new user
    new_user = User(full_name=full_name, email=email, password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return JSONResponse({"message": "User registered successfully"}, status_code=200)

# ----------------------
# Login endpoint
# ----------------------=
@router.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()

    if not user or not pwd_context.verify(password, user.password):
        return JSONResponse({"message": "Invalid email or password"}, status_code=401)
    
    # Save User and Role to Session
    request.session['user'] = {"email": user.email, "full_name": user.full_name}
    request.session['role'] = user.role 

    # Determine redirect based on role
    redirect_url = "/admin/dashboard" if user.role == "admin" else "/home"

    return JSONResponse({
        "message": f"Welcome, {user.full_name}!",
        "redirect_url": redirect_url,
        "role": user.role  
    }, status_code=200)

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType
from pydantic import EmailStr
import os

# --- 1. MAIL SERVER CONFIGURATION ---
# Ensure these are in your .env file
conf = ConnectionConfig(
    MAIL_USERNAME = os.getenv("MAIL_USERNAME"),
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD"), # Your 16-character App Password
    MAIL_FROM = os.getenv("MAIL_FROM"),
    MAIL_PORT = 587,
    MAIL_SERVER = "smtp.gmail.com",
    MAIL_STARTTLS = True,
    MAIL_SSL_TLS = False,
    USE_CREDENTIALS = True,
    VALIDATE_CERTS = True
)

# --- 2. FORGOT PASSWORD (GET) ---
@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page(request: Request):
    return templates.TemplateResponse("forgot-password.html", {
        "request": request,
        "hide_nav": True # SUCCESS MOVE: Hides header/footer in base.html
    })

# --- 3. PROCESS FORGOT PASSWORD (POST) ---
@router.post("/forgot-password")
async def forgot_password(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()

    # Security Pillar: Don't reveal if user exists. 
    # Return success regardless to prevent "Email Enumeration" attacks.
    if not user:
        return JSONResponse({"message": "Check your inbox! If the account exists, a link has been sent."})

    # Create Token
    token = secrets.token_urlsafe(32)
    password_reset_tokens[token] = user.id
    reset_link = f"http://localhost:8000/auth/reset-password/{token}"

    # SUCCESS PILLAR: SEND REAL EMAIL
    html_content = f"""
    <div style="font-family: sans-serif; padding: 20px; border: 1px solid #A3B1AA; border-radius: 15px; max-width: 500px;">
        <h2 style="color: #2D1B10;">GlobeMate Security</h2>
        <p>Hello {user.full_name},</p>
        <p>You requested to reset your password. Click the professional button below to proceed:</p>
        <a href="{reset_link}" style="display:inline-block; padding: 12px 25px; background-color: #A3B1AA; color: #2D1B10; text-decoration: none; border-radius: 8px; font-weight: bold;">Reset My Password</a>
        <p style="margin-top: 20px; font-size: 0.8rem; color: #888;">If you did not request this, you can safely ignore this email.</p>
    </div>
    """

    message = MessageSchema(
        subject="GlobeMate: Password Reset Link",
        recipients=[email],
        body=html_content,
        subtype=MessageType.html
    )

    fm = FastMail(conf)
    try:
        await fm.send_message(message)
        return JSONResponse({"message": "Check your email! The reset link has been sent."})
    except Exception as e:
        print(f"❌ Mail Error: {e}")
        return JSONResponse({"message": "Server error. Could not send email."}, status_code=500)

# --- 4. RESET PASSWORD PAGE (GET) ---
@router.get("/reset-password/{token}", response_class=HTMLResponse)
def reset_password_page(request: Request, token: str):
    if token not in password_reset_tokens:
        return HTMLResponse("Invalid or expired token. Please try again.")
    
    return templates.TemplateResponse("reset-password.html", {
        "request": request, 
        "token": token,
        "hide_nav": True # SUCCESS MOVE: Hides header/footer
    })

# --- 5. PROCESS RESET PASSWORD (POST) ---
@router.post("/reset-password")
async def reset_password(
    token: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db)
):
    if token not in password_reset_tokens:
        return JSONResponse({"message": "Invalid or expired token"}, status_code=400)

    user_id = password_reset_tokens[token]
    user = db.query(User).filter(User.id == user_id).first()

    # Hash new password
    user.password = pwd_context.hash(new_password)
    db.commit()

    # Clean up token
    del password_reset_tokens[token]

    return RedirectResponse("/login?msg=password_updated", status_code=303)

# --- Updated OAuth Registration ---
oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    # This one URL automatically gets all the other endpoints for you
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

# --- Google Login ---
@router.get("/google/login")
async def google_login(request: Request):
    # This must match your Google Console Redirect URI exactly
    redirect_uri = request.url_for('google_callback')
    return await oauth.google.authorize_redirect(request, redirect_uri)

# --- Google Callback ---
@router.get("/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    try:
        # 1. Fetch token and user info
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo') # Simple way to get data

        email = user_info.get("email")
        full_name = user_info.get("name")

        # 2. Check if user already exists in pgAdmin
        user = db.query(User).filter(User.email == email).first()
        
        if not user:
            # 3. SUCCESS PILLAR: Auto-Register for new Google Users
            random_password = os.urandom(16).hex()
            hashed_password = pwd_context.hash(random_password)
            user = User(
                full_name=full_name, 
                email=email, 
                password=hashed_password,
                role="customer" # Default role
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"🆕 New Google User Registered: {email}")

        # 4. SUCCESS PILLAR: Sync Session with Identity & Role
        request.session['user'] = {"email": email, "full_name": full_name}
        request.session['role'] = user.role #
        # 5. Redirect based on role
        redirect_url = "/admin/dashboard" if user.role == "admin" else "/home"
        return RedirectResponse(url="/home")

    except Exception as e:
        print(f"❌ Google Login Error: {e}")
        return RedirectResponse(url="/login?error=google_auth_failed")

# app/routes/auth.py

@router.get("/logout")
async def logout(request: Request):
    # Clear all data from the session
    request.session.clear()
    # Redirect to the login page
    return RedirectResponse(url="/login", status_code=303)

@router.post("/plan-trip")
async def post_plan_trip(
    request: Request,
    trip_name: str = Form(...),
    date_range: str = Form(...),
    duration: int = Form(...),
    traveler_type: str = Form(...),
    db: Session = Depends(get_db)
):
    # 1. Get logged in user from session
    user_data = request.session.get("user")
    if not user_data:
        return RedirectResponse(url="/login", status_code=303)

    # 2. Find user in DB
    user = db.query(User).filter(User.email == user_data['email']).first()

    # 3. Create a new Trip record
    new_trip = Trip(
        user_id=user.id,
        trip_name=trip_name,
        date_range=date_range,
        duration=duration,
        traveler_type=traveler_type,
        status="planning"
    )
    
    db.add(new_trip)
    db.commit()
    db.refresh(new_trip)

    # 4. Store the trip_id in the session so the AI knows which trip we are updating next
    request.session["current_trip_id"] = new_trip.id

    # 5. Redirect to Step 2
    return RedirectResponse(url="/vibe-selection", status_code=303)