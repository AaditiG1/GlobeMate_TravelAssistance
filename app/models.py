from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
# CRITICAL FIX: Import Base from your database configuration, 
# do not create a new Base here.
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    # This column will store the HASHED password (not plain text)
    password = Column(String, nullable=False)  
    is_active = Column(Boolean, default=True)
    role = Column(String, default="customer")

    def __repr__(self):
         return f"<User(id={self.id}, email={self.email}, full_name={self.full_name})>"
    
    trips = relationship("Trip", back_populates="owner")

class Trip(Base):
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id")) 
    trip_name = Column(String)
    date_range = Column(String)
    duration = Column(Integer)
    traveler_type = Column(String)
    vibe = Column(String, nullable=True)           
    secondary_pref = Column(String, nullable=True) 
    budget = Column(Integer, nullable=True)
    travel_style = Column(String, nullable=True)     
    acc_priority = Column(String, nullable=True)
    food_priority = Column(String, nullable=True)   
    status = Column(String, default="planning") 
    created_at = Column(DateTime, default=datetime.utcnow)

    # --- ADDED FOR CHATBOT & ITINERARY ---
    selected_dest = Column(String, nullable=True)
    itinerary_data = Column(String, nullable=True) # Using Text for long JSON strings
    chat_history = Column(String, nullable=True)
    # -------------------------------------

    owner = relationship("User", back_populates="trips")

class Destination(Base):
    __tablename__ = "destinations"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    country = Column(String, nullable=False)
    vibe_tags = Column(String)
    avg_daily_cost = Column(Integer)
    description = Column(String)

class Blog(Base):
    __tablename__ = "blogs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    trip_id = Column(Integer, ForeignKey("trips.id"))
    title = Column(String(255))
    content = Column(String)
    rating = Column(Integer) # 1-5 stars
    image_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    owner = relationship("User")

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    title = Column(String(255))
    message = Column(String)
    # Types can be: 'ai', 'blog', 'weather', 'info'
    notif_type = Column(String(50), default="info")
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Link back to user
    owner = relationship("User")

class AISettings(Base):
    __tablename__ = "ai_settings"
    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String, default="llama-3.3-70b-versatile")
    system_prompt = Column(String)
    temperature = Column(Float, default=0.7) # Float handles decimals like 0.7


class SystemLog(Base):
    __tablename__ = "system_logs"
    id = Column(Integer, primary_key=True, index=True)
    level = Column(String) # info, success, error, warning
    message = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    latency = Column(Float, default=0.0) 
    created_at = Column(DateTime, default=datetime.utcnow)
