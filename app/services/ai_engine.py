import os
import json
from pathlib import Path
from groq import Groq
from dotenv import load_dotenv

# --- SUCCESS PILLAR: LOAD API KEY ---
# 1. Load from .env
load_dotenv()

# 2. Get the key from environment variables
api_key = os.getenv("GROQ_API_KEY")

# 3. SECURITY GUARDRAIL: If key is missing, stop the app professionally
if not api_key:
    raise ValueError("❌ CRITICAL ERROR: GROQ_API_KEY not found in .env file. System execution halted for security.")
else:
    print(f"✅ Success: AI Engine linked to Groq LPU via .env")

# 4. Initialize the Client
client = Groq(api_key=api_key)
# --- FUNCTION 1: INITIAL GENERATION ---
def generate_smart_itinerary(dest_name, duration, vibe, budget):
    """
    Called when a destination is selected. Creates a professional plan.
    """
    system_prompt = f"""
    You are GlobeMate AI. Create a {duration}-day travel itinerary for {dest_name}.
    Vibe: {vibe} | Total Budget: Rs. {budget}
    
    RULES:
    1. Budget: Calculate realistic costs. NEVER provide a negative remaining budget.
    2. Format: Return ONLY a JSON object.
    3. Keys: Each day must have 'day', 'title', 'status' (set to 'active'), and 'activities'.
    4. Activity Keys: Each activity MUST have 'time' and 'desc'.

    JSON STRUCTURE:
    {{
      "itinerary": [
        {{
          "day": 1,
          "title": "Welcome to {dest_name}",
          "status": "active",
          "activities": [
            {{"time": "09:00 AM", "desc": "Activity description here"}},
            {{"time": "01:00 PM", "desc": "Lunch at a local spot"}}
          ]
        }}
      ]
    }}
    """

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system_prompt}],
            response_format={"type": "json_object"},
            temperature=0.7
        )
        
        content = json.loads(response.choices[0].message.content)
        # Success check: ensure we return just the list of days
        return content.get("itinerary", content)

    except Exception as e:
        print(f"❌ AI Generation Error: {e}")
        # Return a professional fallback so the UI doesn't say "Generating..." forever
        return [{"day": 1, "title": "Trip to " + dest_name, "status": "active", "activities": [{"time": "Check-in", "desc": "Welcome to your destination!"}]}]

# --- FUNCTION 2: CHATBOT UPDATES ---
def update_itinerary_with_ai(current_itinerary, user_message, dest_name):
    """
    Processes chat messages to update the itinerary in real-time.
    """
    system_prompt = f"""
    You are GlobeMate AI. You are managing a trip to {dest_name}.
    CURRENT ITINERARY: {json.dumps(current_itinerary)}

    USER REQUEST: "{user_message}"

    TASK:
    - If user wants to skip/change/reschedule: Update 'status' (active/missed/rescheduled) and return the full list.
    - If it's just a question: Answer politely.
    - Return JSON ONLY with: "reply", "updated_itinerary", and "did_update" (boolean).
    """

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system_prompt}],
            response_format={"type": "json_object"},
            temperature=0.5
        )
        return json.loads(response.choices[0].message.content)
    
    except Exception as e:
        print(f"❌ AI Chat Error: {e}")
        return {
            "reply": "I'm having trouble connecting to my brain right now. Please try again!",
            "updated_itinerary": current_itinerary,
            "did_update": False
        }