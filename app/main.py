from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
import secrets
import time
import warnings

# Database Imports
from app.database import engine, get_db
from app.models import Base, Trip, User, Destination, Blog, Notification  
from app.routes import auth
from app.services.explore_logic import get_explore_recommendations
import pandas as pd
from app.services.recommender import get_ai_recommendations
from datetime import datetime, date
from app.services.notify import add_notification # Ensure your helper is imported
import json
from app.services.ai_engine import generate_smart_itinerary, update_itinerary_with_ai
from fastapi import Form
from app.models import Destination
from collections import Counter
from sqlalchemy import func
from app.models import SystemLog, AISettings # Ensure this is in your imports

Base.metadata.create_all(bind=engine)
app = FastAPI()



# Suppress all deprecation and user warnings to keep terminal clean
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# SessionMiddleware required for OAuth
secret_key = secrets.token_urlsafe(32)
app.add_middleware(SessionMiddleware, secret_key=secret_key)

# Now, every templates.TemplateResponse in main.py MUST include:
# "unread_count": request.state.unread_count, "notifications": request.state.notifications
# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")
# Templates
templates = Jinja2Templates(directory="frontend")
# Include authentication routes
app.include_router(auth.router)

# --- Helpers ---
def is_admin(request: Request):
    return request.session.get("role") == "admin"


# PUBLIC ROUTES 
@app.get("/", response_class=HTMLResponse)
def landing_page(request: Request):
    # Old: ("getstarted.html", {"request": request})
    return templates.TemplateResponse(request, "getstarted.html")

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    # Old: ("login.html", {"request": request})
    return templates.TemplateResponse(request, "login.html")

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    # Old: ("register.html", {"request": request})
    return templates.TemplateResponse(request, "register.html")

from app.services.notify import add_notification # Ensure your helper is imported
@app.get("/home", response_class=HTMLResponse)
async def home_page(request: Request, db: Session = Depends(get_db)):
    user_session = request.session.get("user")
    if not user_session:
        return RedirectResponse(url="/login")

    user = db.query(User).filter(User.email == user_session['email']).first()
    if not user:
        return RedirectResponse(url="/login")

    # Fetch all trips for this user
    user_trips = db.query(Trip).filter(Trip.user_id == user.id).all()
    
    # --- SUCCESS PILLAR: Find the user's current active trip ---
    # We look for a trip that has a destination but hasn't happened yet.
    active_trip = db.query(Trip).filter(
        Trip.user_id == user.id, 
        Trip.selected_dest != None
    ).order_by(Trip.created_at.desc()).first()

    today = date.today()
    visited_count = 0
    planned_count = 0
    total_budget = 0
    budget_entries = 0
    
    # AI Discoveries: Count finalized trips
    ai_discovery_count = db.query(Trip).filter(
        Trip.user_id == user.id, 
        Trip.status == "finalized"
    ).count()

    for trip in user_trips:
        try:
            end_date_str = trip.date_range.split(" to ")[1]
            end_date_obj = datetime.strptime(end_date_str, "%Y-%m-%d").date()

            if end_date_obj < today:
                visited_count += 1
                
                notif_exists = db.query(Notification).filter(
                    Notification.user_id == user.id,
                    Notification.message.contains(trip.trip_name)
                ).first()
                
                if not notif_exists:
                    add_notification(
                        db, user.id, 
                        "Trip Complete!", 
                        f"How was '{trip.trip_name}'? Your vlog access is now unlocked!", 
                        "blog"
                    )
            else:
                planned_count += 1
            
            if trip.budget and trip.budget > 0:
                total_budget += trip.budget
                budget_entries += 1
        except:
            planned_count += 1

    avg_val = total_budget / budget_entries if budget_entries > 0 else 0

    notifications = db.query(Notification).filter(
        Notification.user_id == user.id
    ).order_by(Notification.created_at.desc()).limit(5).all()
    
    unread_count = db.query(Notification).filter(
        Notification.user_id == user.id, 
        Notification.is_read == False
    ).count()

    return templates.TemplateResponse(request, "home.html", {
        "user": user,
        "active_trip": active_trip, # <--- PASSING THE TRIP TO HTML
        "visited_count": visited_count,
        "planned_count": planned_count,
        "avg_budget": f"{avg_val:,.0f}",
        "ai_discovery_count": ai_discovery_count,
        "notifications": notifications,
        "unread_count": unread_count
    })

@app.get("/contact", response_class=HTMLResponse)
def contact_page(request: Request):
    return templates.TemplateResponse(request, "contact.html")
@app.post("/submit-contact")
async def submit_contact(request: Request, db: Session = Depends(get_db)):
    # ... yo
    # ur save data logic ...
    
    # After saving, return this:
    return RedirectResponse(url="/contact?msg=sent", status_code=303)
@app.get("/aboutus", response_class=HTMLResponse)
def about_page(request: Request):
    return templates.TemplateResponse(request, "aboutus.html")


# --- Update your existing profile_page route ---
@app.get("/customer-profile", response_class=HTMLResponse)
async def profile_page(request: Request, db: Session = Depends(get_db)):
    user_session = request.session.get("user")
    if not user_session:
        return RedirectResponse(url="/login")

    user = db.query(User).filter(User.email == user_session['email']).first()
    
    # Fetch all trips for this specific user
    user_trips = db.query(Trip).filter(Trip.user_id == user.id).order_by(Trip.id.desc()).all()
    
    # Logic for stats
    planning_count = 0
    today = date.today()
    taken_count = 0
    total_budget = 0
    ongoing_trip = None

    for trip in user_trips:
        try:
            end_str = trip.date_range.split(" to ")[1]
            end_date = datetime.strptime(end_str, "%Y-%m-%d").date()

            if today > end_date:
                taken_count += 1
            else:
                planning_count += 1
                ongoing_trip = trip
            if trip.budget:
                total_budget += trip.budget
        except:
            continue

    avg = total_budget / len(user_trips) if user_trips else 0

    return templates.TemplateResponse(request, "customerprofile.html", {
        "user": user,
        "user_trips": user_trips, # PASS THE TRIPS LIST
        "planning_count": planning_count,
        "taken_count": taken_count,
        "avg_budget": f"Rs. {avg:,.0f}",
        "ongoing_trip": ongoing_trip
    })

from passlib.context import CryptContext

# Set Argon2 as the primary scheme
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

@app.post("/update-profile")
async def update_profile(
    request: Request,
    name: str = Form(...),
    password: str = Form(None),
    confirm_password: str = Form(None),
    db: Session = Depends(get_db)
):
    user_session = request.session.get("user")
    if not user_session: return RedirectResponse(url="/login")

    # Fetch user
    user = db.query(User).filter(User.email == user_session['email']).first()
    
    try:
        user.full_name = name
        
        # 1. Handle Password Mismatch
        if password and password.strip() != "":
            if password != confirm_password:
                # Redirect back to the profile with the mismatch message
                return RedirectResponse(url="/customer-profile?msg=mismatch", status_code=303)
            
            user.password = pwd_context.hash(password)

        db.commit()
        request.session["user"]["full_name"] = name
        return RedirectResponse(url="/customer-profile?msg=success", status_code=303)
    except Exception as e:
        db.rollback()
        return RedirectResponse(url="/customer-profile?msg=error", status_code=303)
        
# --- ADD THE DELETE ROUTE ---
@app.post("/delete-trip/{trip_id}")
async def delete_trip(trip_id: int, request: Request, db: Session = Depends(get_db)):
    user_session = request.session.get("user")
    if not user_session:
        return RedirectResponse(url="/login")

    user = db.query(User).filter(User.email == user_session['email']).first()
    # Ensure the trip belongs to the logged-in user (Security)
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.user_id == user.id).first()
    
    if trip:
        db.delete(trip)
        db.commit()
    
    return RedirectResponse(url="/customer-profile", status_code=303)

@app.get("/plan-trip", response_class=HTMLResponse)
def plan_trip_page(request: Request):
    return templates.TemplateResponse(request, "plantrip.html")

# STEP 1: Plan Trip (POST - Save Initial Data)
@app.post("/plan-trip")
async def save_trip_step_one(
    request: Request,
    trip_name: str = Form(...),
    date_range: str = Form(...),
    duration: int = Form(...),
    traveler_type: str = Form(...),
    db: Session = Depends(get_db)
):
    user_data = request.session.get("user")
    if not user_data:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).filter(User.email == user_data['email']).first()

    # 1. Create the new trip
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

    # This adds the record to pgAdmin so the Live API can find it
    send_user_notification(
        db, 
        user.id, 
        "Trip Initialized! 🌍", 
        f"You've started planning '{trip_name}'. Next: Select your vibe tags!", 
        "info"
    )

    # 2. Store the Trip ID in session so Step 2 knows which one to update
    request.session["current_trip_id"] = new_trip.id
    return RedirectResponse(url="/vibe-selection", status_code=303)

@app.get("/vibe-selection", response_class=HTMLResponse)
def vibe_selection_page(request: Request, db: Session = Depends(get_db)):
    trip_id = request.session.get("current_trip_id")
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    
    # FIX: Move 'request' to the first position
    return templates.TemplateResponse(request, "vibeselection.html", {
        "trip_name": trip.trip_name if trip else "New Trip"
    })

# STEP 2: Vibe Selection (POST - Update Trip with Vibes)
@app.post("/vibe-selection")
async def save_trip_step_two(
    request: Request,
    vibe: list[str] = Form(None), # Captures multiple checkboxes
    pref: list[str] = Form(None), # This captures name="pref"
    db: Session = Depends(get_db)
):
    trip_id = request.session.get("current_trip_id")
    if not trip_id:
        return RedirectResponse(url="/plan-trip")

    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if trip:
        # 3. Join the lists into strings to store in the DB (e.g. "beach, adventure")
         # Convert lists to strings for PostgreSQL
        trip.vibe = ", ".join(vibe) if vibe else ""
        trip.secondary_pref = ", ".join(pref) if pref else ""
        db.commit()
        print("✅ Database updated successfully.")
    else:
        print(f"ERROR: Trip with ID {trip_id} not found in database.")
        
        # 4. Save changes to PostgreSQL
        db.commit()
    return RedirectResponse(url="/budget-estimation", status_code=303)

@app.get("/budget-estimation", response_class=HTMLResponse)
async def budget_estimation_page(request: Request, db: Session = Depends(get_db)):
    trip_id = request.session.get("current_trip_id")
    
    # Fetch trip from DB
    trip = None
    if trip_id:
        trip = db.query(Trip).filter(Trip.id == trip_id).first()
    
    # Provide defaults if trip is not found
    return templates.TemplateResponse(request, "budgetestimation.html", {
        "trip_name": trip.trip_name if trip else "Your Trip",
        "duration": trip.duration if (trip and trip.duration) else 1
    })

@app.post("/find-destination")
async def find_destination(
    request: Request,
    budget_amount: int = Form(...),
    style: str = Form("moderate"),
    acc: str = Form("balanced"),
    food: str = Form("balanced"),
    db: Session = Depends(get_db)
):
    trip_id = request.session.get("current_trip_id")
    user_session = request.session.get("user")
    
    if not trip_id or not user_session:
        return RedirectResponse(url="/plan-trip", status_code=303)

    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    
    if trip:
        # 1. JUST SAVE THE DATA (This is very fast)
        trip.budget = budget_amount
        trip.travel_style = style
        trip.acc_priority = acc
        trip.food_priority = food
        db.commit()

        # 2. DO NOT CALL AI HERE. 
        # Just let the next page (/trip-results) handle the AI call.

    # 3. This will now load INSTANTLY
    return templates.TemplateResponse(request, "aiprogress.html")

@app.get("/trip-results", response_class=HTMLResponse)
async def trip_results_page(request: Request, db: Session = Depends(get_db)):
    trip_id = request.session.get("current_trip_id")
    if not trip_id: return RedirectResponse(url="/plan-trip")

    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip: return RedirectResponse("/plan-trip")

     # Check if we already notified the user for this trip to prevent spam
    already_notified = db.query(Notification).filter(
        Notification.user_id == trip.user_id,
        Notification.title == "Discovery Complete! 🔍"
    ).first()

    if not already_notified:
        add_notification(
            db, 
            trip.user_id, 
            "Discovery Complete! 🔍", 
            f"AI has analyzed 25,000+ data points and found the perfect matches for '{trip.trip_name}'!", 
            "ai"
        )
        db.commit()


    search_keywords = f"{trip.vibe or ''} {trip.secondary_pref or ''}"

    # SUCCESS PILLAR: Passing the 4th variable (travel_style)
    ai_results = get_ai_recommendations(
        user_vibe=search_keywords, 
        user_budget=trip.budget or 0, 
        duration=trip.duration or 1,
        user_style=trip.travel_style or "moderate"
    )

    for res in ai_results:
        # Data Sanitization
        try:
            res['estimated_cost'] = float(res['estimated_cost'])
        except:
            res['estimated_cost'] = 0.0

        user_limit = trip.budget or 0
        
        # SUCCESS PILLAR: Logic Guard (Calculates exact positive shortfall)
        res['remaining_budget'] = max(0, user_limit - res['estimated_cost'])
        res['shortfall'] = max(0, res['estimated_cost'] - user_limit)
        res['is_over_budget'] = res['estimated_cost'] > user_limit

    return templates.TemplateResponse(request, "tripresult.html", {
        "results": ai_results,
        "trip_name": trip.trip_name,
        "vibe": trip.vibe,
        "budget": trip.budget,
        "duration": trip.duration,
        "traveler_type": trip.travel_style
    })

@app.get("/notifications/mark-all-read")
async def mark_read(request: Request, db: Session = Depends(get_db)):
    user_session = request.session.get("user")
    user = db.query(User).filter(User.email == user_session['email']).first()
    
    if user:
        db.query(Notification).filter(Notification.user_id == user.id).update({"is_read": True})
        db.commit()
        
    return RedirectResponse(url=request.headers.get("referer", "/home"), status_code=303)

# 1. Route to save selection and generate initial itinerary




@app.post("/select-destination")
async def select_destination(request: Request, dest_name: str = Form(...), db: Session = Depends(get_db)):
    # 1. Get the current trip from session
    trip_id = request.session.get("current_trip_id")
    trip = db.query(Trip).filter(Trip.id == trip_id).first()

    if not trip:
        # Redirect if session is lost or trip doesn't exist
        return RedirectResponse(url="/plan-trip", status_code=303)

    # --- LATENCY TRACKING: START STOPWATCH ---
    start_time = time.time() 

    try:
        # Initial log to show activity in the Admin Terminal
        add_system_log(db, f"User {trip.user_id} requested {trip.duration}-day plan for {dest_name}", "info")

        # 2. CALL THE AI (The heavy execution step)
        generated_plan = generate_smart_itinerary(
            dest_name=dest_name,
            duration=trip.duration,
            vibe=trip.vibe,
            budget=trip.budget
        )

        # --- LATENCY TRACKING: STOP STOPWATCH ---
        end_time = time.time()
        duration_ms = (end_time - start_time) * 1000  # Convert seconds to ms

        # 3. SAVE RESULTS TO POSTGRESQL (pgAdmin)
        trip.selected_dest = dest_name
        # Convert Python list/dict from AI into a JSON String
        trip.itinerary_data = json.dumps(generated_plan) 
        
        # 4. COMMIT TO DATABASE
        db.commit()

        # 5. DIAGNOSTIC FEEDBACK (For Admin Dashboard)
        # We pass the latency here to fix the "0ms" display bug
        print(f"✅ Success: {dest_name} plan saved. Latency: {duration_ms:.2f}ms")
        add_system_log(
            db, 
            f"Itinerary successfully pushed to pgAdmin for {dest_name}", 
            "success", 
            
        )

        # 6. USER NOTIFICATION (For Traveler Dashboard)
        add_notification(
            db, 
            trip.user_id, 
            "Itinerary Generated! ✨", 
            f"GlobeMate has finished your professional {trip.duration}-day plan for {dest_name}. Ready to explore!", 
            "ai"
        )
        db.commit() # Commit the notification

    except Exception as e:
        # Calculate time spent until error occurred
        error_duration = (time.time() - start_time) * 1000
        db.rollback()

        # Log the failure for the Admin to see
        add_system_log(db, f"Inference Error for {dest_name}: {str(e)}", "error", latency=error_duration)
        print(f"❌ AI ERROR: {str(e)}")

        # EMERGENCY FALLBACK: Prevent a NULL crash by saving a basic day 1
        fallback = [{"day": 1, "title": "Welcome to " + dest_name, "status": "active", "activities": []}]
        trip.itinerary_data = json.dumps(fallback)
        db.commit()

        # Notify user that a basic plan is ready instead
        add_notification(
            db, 
            trip.user_id, 
            "Plan Ready (Basic)", 
            f"We created a base plan for {dest_name}. Our AI is currently busy, but your trip is saved!", 
            "info"
        )

    # Redirect to the Chatbot/Itinerary view
    return RedirectResponse(url="/chatbot", status_code=303)


@app.get("/my-trips", response_class=HTMLResponse)
async def view_my_trips(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(url="/login")

    # Fetch only trips that have a selected destination (Saved Trips)
    trips = db.query(Trip).filter(
        Trip.user_id == user_id, 
        Trip.selected_dest != None
    ).order_by(Trip.created_at.desc()).all()

    return templates.TemplateResponse("my_trips.html", {
        "request": request,
        "trips": trips
    })

@app.post("/trips/delete/{trip_id}")
async def delete_trip(trip_id: int, request: Request, db: Session = Depends(get_db)):
    # 1. Get the user dictionary from the session
    user_session = request.session.get("user")
    
    if not user_session:
        print("DEBUG: Delete failed - No user session found.")
        return RedirectResponse(url="/login")

    # 2. Find the user in the DB using the email from the session
    user = db.query(User).filter(User.email == user_session['email']).first()
    
    if not user:
        return RedirectResponse(url="/login")

    # 3. Find the trip AND verify it belongs to THIS user (Security)
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.user_id == user.id).first()
    
    if trip:
        try:
            db.delete(trip)
            db.commit()
            print(f"DEBUG: Trip {trip_id} successfully deleted.")
        except Exception as e:
            db.rollback()
            print(f"DEBUG: Error during delete: {e}")
            return RedirectResponse(url="/customer-profile?msg=error")

    # 4. Redirect back to the profile page
    return RedirectResponse(url="/customer-profile", status_code=303)

@app.get("/share/{trip_id}", response_class=HTMLResponse)
async def share_itinerary(trip_id: int, db: Session = Depends(get_db)):
    # This route does NOT check for session/login so friends can see it
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    if not trip:
        return "Trip not found", 404
    
    # Use a read-only version of your itinerary template
    return templates.TemplateResponse("shared_itinerary.html", {
        "request": {}, # Empty request since no session needed
        "trip": trip,
        "itinerary": json.loads(trip.itinerary_data)
    })

@app.get("/public/trip/{trip_id}")
async def public_trip_view(trip_id: int, db: Session = Depends(get_db)):
    # NOTICE: No login check here, so friends can see it!
    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    
    if not trip or not trip.itinerary_data:
        return "Itinerary not found or not yet generated.", 404

    itinerary = json.loads(trip.itinerary_data)
    
    # You can reuse your trip results template or a new 'shared.html'
    return templates.TemplateResponse("shared_itinerary.html", {
        "request": {}, 
        "trip": trip,
        "itinerary": itinerary
    })

@app.get("/trips/resume/{trip_id}")
async def resume_trip(trip_id: int, request: Request, db: Session = Depends(get_db)):
    # 1. Match the session check from your profile_page route
    user_session = request.session.get("user")
    
    # If this is missing, that's why you are being redirected to login
    if not user_session:
        print("DEBUG: Redirecting to login because session['user'] is empty")
        return RedirectResponse(url="/login")

    # 2. Get the user from DB using email (just like your profile_page does)
    user = db.query(User).filter(User.email == user_session['email']).first()
    
    if not user:
        print("DEBUG: Redirecting to login because user email not found in DB")
        return RedirectResponse(url="/login")

    # 3. Verify the trip belongs to this user
    trip = db.query(Trip).filter(Trip.id == trip_id, Trip.user_id == user.id).first()
    
    if trip:
        # 4. Set the current trip ID so the Chatbot knows which one to load
        request.session["current_trip_id"] = trip.id
        print(f"DEBUG: Successfully set trip {trip.id} as current. Redirecting to Chatbot.")
        return RedirectResponse(url="/chatbot", status_code=303)
    
    # If trip doesn't belong to them, send them back to profile
    print(f"DEBUG: Trip {trip_id} not found for user {user.id}")
    return RedirectResponse(url="/customer-profile?msg=not_found")

# 2. Updated Chatbot Logic (POST) - Now saves conversation
@app.post("/api/chat")
async def chat_logic(request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    user_msg = data.get("message")
    trip_id = request.session.get("current_trip_id")
    trip = db.query(Trip).filter(Trip.id == trip_id).first()

    if not trip:
        return {"reply": "Session expired. Please restart.", "update": False}
    # --- SUCCESS MOVE: PERSISTENCE (LOAD OLD CHAT) ---
    # We turn the string from pgAdmin back into a Python List
    history = json.loads(trip.chat_history) if trip.chat_history else []
    
    # SAFETY FIX: Ensure we have an itinerary
    if not trip.itinerary_data or trip.itinerary_data == "null":
        current_itinerary = []
    else:
        current_itinerary = json.loads(trip.itinerary_data)
    dest_context = trip.selected_dest or "your chosen destination"

    try:
        ai_result = update_itinerary_with_ai(current_itinerary, user_msg, dest_context)
        # --- SUCCESS MOVE: SAVE TO HISTORY ---
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": ai_result["reply"]})
        # Save history as a JSON string back to pgAdmin
        trip.chat_history = json.dumps(history)

        if ai_result.get("did_update"):
            trip.itinerary_data = json.dumps(ai_result["updated_itinerary"])
            from app.services.notify import add_notification
            add_notification(db, trip.user_id, "Schedule Revised 🔄", f"I've updated your {trip.selected_dest} plan.", "ai")
            
        db.commit() # Saves both the chat and the new itinerary

        return {
            "reply": ai_result["reply"], 
            "update": ai_result["did_update"], 
            "new_itinerary": ai_result.get("updated_itinerary")
        }
    except Exception as e:
        print(f" Chat Error: {e}")
        return {"reply": "I'm having a brief connection issue.", "update": False}

# 3. Updated Chatbot GET route - Now loads old chat
@app.get("/chatbot")
def chatbot_page(request: Request, db: Session = Depends(get_db)):
    trip_id = request.session.get("current_trip_id")
    
    # SUCCESS MOVE: If no session, look for the most recent trip to 'Resume'
    if not trip_id:
        user_session = request.session.get("user")
        if user_session:
            user = db.query(User).filter(User.email == user_session['email']).first()
            latest_trip = db.query(Trip).filter(Trip.user_id == user.id).order_by(Trip.id.desc()).first()
            if latest_trip:
                trip_id = latest_trip.id
                request.session["current_trip_id"] = trip_id

    trip = db.query(Trip).filter(Trip.id == trip_id).first()
    
    if not trip:
        return RedirectResponse(url="/plan-trip")

    # SELF-REPAIR LOGIC (Keep your existing repair code here...)
    if not trip.itinerary_data or trip.itinerary_data == "null" or trip.itinerary_data == "[]":
        db.commit()

    # --- SUCCESS MOVE: PASS HISTORY TO HTML ---
    real_itinerary = json.loads(trip.itinerary_data) if trip.itinerary_data else []
    chat_history = json.loads(trip.chat_history) if trip.chat_history else []
    
    return templates.TemplateResponse("chatbot.html", {
        "request": request, 
        "user": request.session.get("user"),
        "trip": trip,
        "itinerary": real_itinerary,
        "chat_history": chat_history # Now the UI can see old messages!
    })


# --- Updated Live Notification API ---
@app.get("/api/notifications/live")
async def get_live_notifications(request: Request, db: Session = Depends(get_db)):
    user_session = request.session.get("user")
    if not user_session:
        return {"unread_count": 0, "notifications": []}

    user = db.query(User).filter(User.email == user_session['email']).first()
    if not user:
        return {"unread_count": 0, "notifications": []}

    # 1. Fetch latest 5 notifications for THIS user
    notifs = db.query(Notification).filter(
        Notification.user_id == user.id
    ).order_by(Notification.created_at.desc()).limit(5).all()
    
    # 2. Count unread for the red badge
    unread_count = db.query(Notification).filter(
        Notification.user_id == user.id, 
        Notification.is_read == False
    ).count()

    # 3. SUCCESS MOVE: Add 'Z' (UTC marker) for perfect Nepali Time tracking
    notif_list = []
    for n in notifs:
        # isoformat() + "Z" tells the browser this is UTC time.
        # JavaScript will automatically convert this to Nepal Time (+5:45)
        timestamp = n.created_at.isoformat() + "Z"
        
        notif_list.append({
            "title": n.title,
            "message": n.message,
            "is_read": n.is_read,
            "time": timestamp 
        })

    return {"unread_count": unread_count, "notifications": notif_list}

# Helper function to create a new notification in pgAdmin
def send_user_notification(db, user_id, title, message, n_type="ai"):
    from app.models import Notification # Ensure it's imported
    new_notif = Notification(
        user_id=user_id,
        title=title,
        message=message,
        notif_type=n_type,
        is_read=False
    )
    db.add(new_notif)
    db.commit()



# --- ADMIN ROUTES ---



@app.get("/admin/dashboard")
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    # 1. SECURITY: Strict Admin Check
    if request.session.get("role") != "admin":
        return RedirectResponse(url="/login")
    
    # 2. KEY METRICS: Top Stat Cards
    user_count = db.query(func.count(User.id)).scalar() or 0
    trip_count = db.query(func.count(Trip.id)).scalar() or 0
    ai_count = db.query(func.count(Trip.id)).filter(Trip.itinerary_data != None).scalar() or 0
    dest_count = db.query(func.count(Destination.id)).scalar() or 0

    # 3. SUCCESS PILLAR: Advanced Vibe Analytics
    # We fetch all vibe strings and split them (e.g., "Adventure, Nature" -> ["Adventure", "Nature"])
    all_vibes = db.query(Trip.vibe).filter(Trip.vibe != None).all()
    vibe_list = []
    for v_tuple in all_vibes:
        # Split by comma, strip spaces, and add to the master list
        vibe_list.extend([v.strip() for v in v_tuple[0].split(',')])
    
    # Count frequencies
    vibe_counts_map = Counter(vibe_list)
    vibe_labels = list(vibe_counts_map.keys())
    vibe_counts = list(vibe_counts_map.values())

    # 4. SUCCESS PILLAR: Top 5 Destinations (Making it interesting)
    dest_stats = db.query(Trip.selected_dest, func.count(Trip.id))\
                   .filter(Trip.selected_dest != None)\
                   .group_by(Trip.selected_dest)\
                   .order_by(func.count(Trip.id).desc())\
                   .limit(5).all()
    
    dest_labels = [d[0] for d in dest_stats]
    dest_counts = [d[1] for d in dest_stats]

    # 5. USER MANAGEMENT: Fetch all users
    users_list = db.query(User).order_by(User.id.desc()).all()

    # 6. RECENT ACTIVITY: Latest 5 trips
    recent_activity = db.query(Trip).order_by(Trip.created_at.desc()).limit(5).all()

    return templates.TemplateResponse(request, "dashboard.html", {
        "total_users": user_count,
        "trips_planned": trip_count,
        "ai_predictions": ai_count,
        "destinations": dest_count,
        "vibe_labels": vibe_labels,   # Corrected dynamic list
        "vibe_counts": vibe_counts,   # Corrected dynamic list
        "dest_labels": dest_labels,   # NEW: for the bar chart
        "dest_counts": dest_counts,   # NEW: for the bar chart
        "users_list": users_list,
        "recent_trips": recent_activity 
    })

# ADD THIS NEW ROUTE: Handles the actual deletion from the table
@app.post("/admin/delete-user/{user_id}")
async def delete_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    if request.session.get("role") != "admin":
        return RedirectResponse(url="/login", status_code=303)

    user_to_delete = db.query(User).filter(User.id == user_id).first()
    
    # Safety: Don't let admin delete themselves
    current_admin_email = request.session.get("user")["email"]
    if user_to_delete and user_to_delete.email != current_admin_email:
        db.delete(user_to_delete)
        db.commit()
    
    return RedirectResponse(url="/admin/dashboard", status_code=303)

# 1. VIEW DESTINATIONS
@app.get("/admin/destination", response_class=HTMLResponse)
async def admin_destination_page(request: Request, db: Session = Depends(get_db)):
    if request.session.get("role") != "admin":
        return RedirectResponse(url="/login")

    # Fetch all places from pgAdmin
    destinations = db.query(Destination).order_by(Destination.id.desc()).all()

    return templates.TemplateResponse(request,"destination.html", {
        "destinations": destinations,
        "role": "admin"
    })

# 2. ADD DESTINATION (The Functionality you need now)
@app.post("/admin/destination/add")
async def add_destination(
    request: Request,
    name: str = Form(...),
    country: str = Form(...),
    vibe_tags: str = Form(...),
    avg_daily_cost: int = Form(...),
    description: str = Form(...),
    db: Session = Depends(get_db)
):
    if request.session.get("role") != "admin":
        return RedirectResponse(url="/login", status_code=303)

    try:
        new_place = Destination(
            name=name,
            country=country,
            vibe_tags=vibe_tags,
            avg_daily_cost=avg_daily_cost,
            description=description
        )
        db.add(new_place)
        db.commit()
        return RedirectResponse(url="/admin/destination?msg=added", status_code=303)
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        return RedirectResponse(url="/admin/destination?msg=error", status_code=303)

# 3. DELETE DESTINATION
@app.post("/admin/destination/delete/{dest_id}")
async def delete_destination(
    dest_id: int, 
    request: Request, 
    db: Session = Depends(get_db)
):
    # 1. SECURITY: Check admin role
    if request.session.get("role") != "admin":
        return RedirectResponse(url="/login", status_code=303)
    try:
        # 2. Find the destination
        dest = db.query(Destination).filter(Destination.id == dest_id).first()
        if dest:
            print(f"DEBUG: Deleting {dest.name} (ID: {dest_id})")
            db.delete(dest)
            db.commit()
            # SUCCESS LOG
            add_system_log(db, f"Admin deleted destination: {dest.id}", "warning")
            return RedirectResponse(url="/admin/destination?msg=deleted", status_code=303)
        return RedirectResponse(url="/admin/destination?msg=error", status_code=303)
    except Exception as e:
        db.rollback()
        print(f"DATABASE ERROR: {e}")
        return RedirectResponse(url="/admin/destination?msg=error", status_code=303)
    
@app.get("/explore", response_class=HTMLResponse)
def explore_page(request: Request):
    return templates.TemplateResponse(request, "explore.html")

@app.post("/api/explore")
async def api_explore(request: Request):
    data = await request.json()
    
    results = get_explore_recommendations(
        user_lat=data['lat'],
        user_lng=data['lng'],
        available_time=data['time'],
        user_vibe=data['vibe'],
        
    )
    
    # Return data to the frontend
    return results

@app.get("/admin-profile")
def admin_profile(request: Request, db: Session = Depends(get_db)):
    # 1. Get the user and role from the session
    user_session = request.session.get("user")
    role_session = request.session.get("role")

    # 2. SECURITY CHECK: If not logged in OR not an admin, kick them out
    if not user_session or role_session != "admin":
        print("🚨 Unauthorized access attempt to Admin Profile")
        return RedirectResponse(url="/login")

    # 3. DATABASE SYNC: Fetch the actual User object from PostgreSQL
    # This ensures that if you change your name/photo, it updates instantly
    user = db.query(User).filter(User.email == user_session['email']).first()

    # 4. SUCCESS MOVE: Explicitly pass 'role' to the template
    return templates.TemplateResponse(request, "adminprofile.html", {
        "user": user,
        "role": "admin" # <--- THIS LOCKS THE ADMIN HEADER ON REFRESH
    })


from datetime import date, datetime

# 1. The Public Blog Feed - NOW WITH LOGIC GATE CALCULATION
@app.get("/blogs", response_class=HTMLResponse)
async def blog_feed(request: Request, db: Session = Depends(get_db)):
    all_blogs = db.query(Blog).order_by(Blog.created_at.desc()).all()
    user_session = request.session.get("user")
    
    # SUCCESS PILLAR: Determine if Natasha can write a blog
    blog_status = "none" # Default: No trips at all
    
    if user_session:
        user = db.query(User).filter(User.email == user_session['email']).first()
        my_trips = db.query(Trip).filter(Trip.user_id == user.id).all()
        
        today = date.today()
        
        if my_trips:
            # Check if at least one trip is finished
            has_finished = False
            for trip in my_trips:
                try:
                    # Parse "2024-03-25 to 2024-03-30" -> 2024-03-30
                    end_str = trip.date_range.split(" to ")[1]
                    end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
                    
                    if today > end_date:
                        # Success: Check if they ALREADY wrote a blog for this finished trip
                        blog_exists = db.query(Blog).filter(Blog.trip_id == trip.id).first()
                        if not blog_exists:
                            has_finished = True
                            break
                except:
                    continue
            
            if has_finished:
                blog_status = "unlocked"
            else:
                blog_status = "locked" # They have a trip, but it's not over yet

    return templates.TemplateResponse(request, "blog.html", { 
        "blogs": all_blogs,
        "blog_status": blog_status,
        "user": user_session
    })

# 2. The Form Page Gate: Double checks eligibility before showing the 'Add Blog' form
@app.get("/add-blog-check", response_class=HTMLResponse)
async def add_blog_check(request: Request, db: Session = Depends(get_db)):
    user_session = request.session.get("user")
    if not user_session:
        return RedirectResponse(url="/login?error=Please login", status_code=303)
    
    user = db.query(User).filter(User.email == user_session['email']).first()
    my_trips = db.query(Trip).filter(Trip.user_id == user.id).all()
    
    today = date.today()
    ongoing_trip = None
    eligible_trip = None

    for trip in my_trips:
        try:
            _, end_str = trip.date_range.split(" to ")
            end_date = datetime.strptime(end_str, "%Y-%m-%d").date()

            if today <= end_date:
                ongoing_trip = trip
            else:
                blog_exists = db.query(Blog).filter(Blog.trip_id == trip.id).first()
                if not blog_exists:
                    eligible_trip = trip
        except:
            continue

    # Priority: If they have a finished trip ready, show form. 
    # If they only have ongoing, show locked.
    status = "unlocked" if eligible_trip else ("locked" if ongoing_trip else "no_trip")

    return templates.TemplateResponse(request, "add_blog.html", {
        "status": status,
        "ongoing_trip": ongoing_trip,
        "eligible_trip": eligible_trip
    })

# 3. Create the Blog Post
@app.post("/create-blog")
async def create_blog(
    request: Request,
    trip_id: int = Form(...),
    title: str = Form(...),
    content: str = Form(...),
    rating: int = Form(...),
    db: Session = Depends(get_db)
):
    user_session = request.session.get("user")
    if not user_session:
        return RedirectResponse(url="/login", status_code=303)

    user = db.query(User).filter(User.email == user_session['email']).first()
    
    try:
        new_blog = Blog(
            user_id=user.id, 
            trip_id=trip_id, 
            title=title, 
            content=content, 
            rating=rating
        )
        db.add(new_blog)
        
        # SUCCESS PILLAR: Trigger a notification for the community
        from app.services.notify import add_notification
        add_notification(
            db, user.id, 
            "Story Published! 🖋️", 
            f"Your vlog for your recent trip is now live in the GlobeMate community.", 
            "blog"
        )
        
        db.commit()
        return RedirectResponse(url="/blogs?msg=success", status_code=303)
    except Exception as e:
        db.rollback()
        return RedirectResponse(url="/blogs?msg=error", status_code=303)
    
from sqlalchemy import func

@app.get("/admin/reports", response_class=HTMLResponse)
async def admin_reports(request: Request, db: Session = Depends(get_db)):
    if request.session.get("role") != "admin":
        return RedirectResponse(url="/login")

    # 1. Aggregate Vibe Data for Pie Chart
    vibe_query = db.query(Trip.vibe, func.count(Trip.id)).group_by(Trip.vibe).all()
    vibe_labels = [v[0] for v in vibe_query if v[0]]
    vibe_counts = [v[1] for v in vibe_query if v[0]]

    # 2. Aggregate Destination Data for Bar Chart
    dest_query = db.query(Trip.selected_dest, func.count(Trip.id)).filter(Trip.selected_dest != None).group_by(Trip.selected_dest).limit(5).all()
    dest_labels = [d[0] for d in dest_query]
    dest_counts = [d[1] for d in dest_query]

    # 3. Calculate Average Budget
    avg_budget = db.query(func.avg(Trip.budget)).scalar() or 0

    # 4. NEW: Fetch Detailed Itinerary History (Functional Oversight)
    # This joins Trip with User to show who generated what
    detailed_reports = db.query(Trip, User).join(User, Trip.user_id == User.id)\
                        .filter(Trip.itinerary_data != None)\
                        .order_by(Trip.created_at.desc()).limit(20).all()

    return templates.TemplateResponse(request, "report.html", {
        "vibe_labels": vibe_labels,
        "vibe_counts": vibe_counts,
        "dest_labels": dest_labels,
        "dest_counts": dest_counts,
        "avg_budget": f"{avg_budget:,.0f}",
        "reports": detailed_reports, # The new detailed list
        "role": "admin"
    })

@app.get("/admin/notification")
async def admin_notif_page(request: Request, db: Session = Depends(get_db)):
    # 1. Security Check
    user_session = request.session.get("user")
    if not user_session or request.session.get("role") != "admin":
        return RedirectResponse(url="/login")

    # 2. Get the Admin's own User record
    admin = db.query(User).filter(User.email == user_session['email']).first()

    # 3. SUCCESS MOVE: Only show notifications belonging to the Admin
    # Since your 'broadcast' loop sends one to EVERYONE (including the admin),
    # this will show exactly ONE row for every launch you perform.
    history = db.query(Notification).filter(
        Notification.user_id == admin.id
    ).order_by(Notification.created_at.desc()).all()

    return templates.TemplateResponse(request, "admin_notification.html", {
        "history": history
    })

# --- BROADCAST ENGINE ---
@app.post("/admin/notifications/broadcast")
async def broadcast_notification(
    request: Request, 
    title: str = Form(...), 
    message: str = Form(...), 
    notif_type: str = Form(...), 
    db: Session = Depends(get_db)
):
    # 1. Security Check
    if request.session.get("role") != "admin":
        return RedirectResponse(url="/login", status_code=303)

    try:
        # 2. Get all users and blast the notification
        users = db.query(User).all()
        for user in users:
            new_notif = Notification(
                user_id=user.id,
                title=title,
                message=message,
                notif_type=notif_type,
                is_read=False
            )
            db.add(new_notif)
        
        db.commit()
        # Redirect with Success Message
        return RedirectResponse(url="/admin/notification?msg=sent", status_code=303)

    except Exception as e:
        db.rollback() # Undo database changes if it fails
        print(f"❌ Error: {e}")
        return RedirectResponse(url="/admin/notification?msg=error", status_code=303)


# --- DELETE ENGINE ---
@app.post("/admin/notifications/delete/{notif_id}")
async def delete_notification(notif_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        # 1. Find the "Master" notification the admin clicked on
        target = db.query(Notification).filter(Notification.id == notif_id).first()
        
        if target:
            # 2. SUCCESS MOVE: Delete the WHOLE BATCH 
            # This deletes the message from every single user's account at once
            db.query(Notification).filter(
                Notification.title == target.title,
                Notification.message == target.message
            ).delete(synchronize_session=False)
            
            db.commit()
            return RedirectResponse(url="/admin/notification?msg=deleted", status_code=303)
            
        return RedirectResponse(url="/admin/notification?msg=error", status_code=303)

    except Exception as e:
        db.rollback()
        return RedirectResponse(url="/admin/notification?msg=error", status_code=303)
    
# --- 1. SYSTEM LOGGING HELPER ---
# Call this function anywhere in main.py to send text to the Admin Terminal
def add_system_log(db: Session, message: str, level: str = "info"):
    new_log = SystemLog(message=message, level=level)
    db.add(new_log)
    db.commit()

# --- 2. API FOR DYNAMIC TERMINAL ---
# This is called by the JavaScript in your ai.html every 3 seconds
@app.get("/api/system-logs")
async def get_system_logs(db: Session = Depends(get_db)):
    # 1. Fetch last 15 events
    logs = db.query(SystemLog).order_by(SystemLog.id.desc()).limit(15).all()
    
    # 2. Calculate average latency
    avg_latency = db.query(func.avg(SystemLog.latency)).scalar() or 0

    # 3. Calculate success rate
    total = db.query(SystemLog).count()
    successes = db.query(SystemLog).filter(SystemLog.level == 'success').count()
    rate = (successes / total * 100) if total > 0 else 100

    # RETURN A DICTIONARY (This allows JS to read both logs and metrics)
    return {
        "logs": [{
            "level": l.level,
            "message": l.message,
            "time": l.created_at.strftime("%H:%M:%S")
        } for l in reversed(logs)],
        "metrics": {
            "avg_latency": round(avg_latency, 2),
            "success_rate": round(rate, 1)
        }
    }
# --- 3. VIEW AI MANAGEMENT (GET) ---

@app.get("/admin/ai", response_class=HTMLResponse)
async def ai_management_page(request: Request, db: Session = Depends(get_db)):
    avg_val = 120.5 # or pull from DB
    rate_val = 98.2

    # Security: Strict Admin Check
    user_session = request.session.get("user")
    if not user_session or request.session.get("role") != "admin":
        return RedirectResponse(url="/login")

    # SUCCESS PILLAR: Self-Healing Settings
    settings = db.query(AISettings).first()
    if not settings:
        settings = AISettings(
            model_name="llama-3.3-70b-versatile",
            system_prompt="You are GlobeMate, a professional travel assistant...",
            temperature=0.7
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)

    # Note: Ensure your file is named ai.html inside the frontend folder
    return templates.TemplateResponse("ai.html", {
        "request": request,
        "settings": settings,
        "avg_latency": avg_val,
        "success_rate": rate_val,
        "role": "admin", # Locks the Admin Header
        "msg": request.query_params.get("msg")
    })

# --- 4. UPDATE AI SETTINGS (POST) ---
@app.post("/admin/ai/update")
async def update_ai_settings(
    request: Request, 
    model: str = Form(...), 
    prompt: str = Form(...), 
    temp: float = Form(...), 
    db: Session = Depends(get_db)
):
    # 1. Security Check
    if request.session.get("role") != "admin":
        return RedirectResponse(url="/login")
    try:
        # 2. Fetch current settings
        settings = db.query(AISettings).first()
        
        # SUCCESS PILLAR: The "Self-Repair" Logic
        # If pgAdmin is empty, create the first record instead of crashing
        if not settings:
            settings = AISettings(
                model_name=model,
                system_prompt=prompt,
                temperature=temp
            )
            db.add(settings)
            print(" Created initial AI settings record.")
        else:
            # Update existing record
            settings.model_name = model
            settings.system_prompt = prompt
            settings.temperature = temp
            print(f" Updated AI settings to model: {model}")
        # 3. Save to Database
        db.commit()
        # 4. Log the success to your dynamic terminal
        add_system_log(db, f"Admin updated AI parameters. Model: {model}", "success")
        
        # 5. REDIRECT: Ensure this matches your sidebar URL exactly!
        return RedirectResponse(url="/admin/ai?msg=updated", status_code=303)
            
    except Exception as e:
        db.rollback()
        print(f" CRITICAL ERROR: {e}")
        # Even if it fails, always return a response to prevent a "500 Error" screen
        return RedirectResponse(url="/admin/ai?msg=error", status_code=303)