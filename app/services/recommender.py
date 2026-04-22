import joblib
import pandas as pd
import os
import random
import warnings
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.exceptions import InconsistentVersionWarning

from app.models import SystemLog

# Silence version mismatch warnings for the demo
warnings.filterwarnings("ignore", category=InconsistentVersionWarning)

# Get the path to the current folder
BASE_PATH = os.path.dirname(__file__)

# Load the 4 Brain Components using absolute paths
tfidf = joblib.load(os.path.join(BASE_PATH, "vibe_vectorizer.pkl"))
vibe_matrix = joblib.load(os.path.join(BASE_PATH, "vibe_matrix.pkl"))
budget_model = joblib.load(os.path.join(BASE_PATH, "budget_model.pkl"))
df = joblib.load(os.path.join(BASE_PATH, "destination_data.pkl"))

def get_ai_recommendations(user_vibe, user_budget, duration, user_style):
    # 1. NLP SCORING
    user_vec = tfidf.transform([user_vibe.lower()])
    similarity_scores = cosine_similarity(user_vec, vibe_matrix).flatten()
    df['match_score'] = (similarity_scores * 100).astype(int)

    # 2. CONFIGURATION
    style_map = {"budget": 0.7, "moderate": 1.0, "luxury": 2.8}
    style_mult = style_map.get(user_style.lower(), 1.0)
    
    final_recommendations = []
    seen_hubs = set() 
    
    # SUCCESS MOVE: Increase search depth to 1000 to find diverse cities
    # in your large 100k dataset.
    sorted_df = df.sort_values(by='match_score', ascending=False).head(1000)

    # 3. FIRST PASS: TRY TO FIND 5 WITHIN BUDGET (+25% buffer)
    for _, row in sorted_df.iterrows():
        base_city_hub = row['city'].split(' ')[0] 
        if base_city_hub in seen_hubs: continue

        input_features = pd.DataFrame(
            [[duration, row['avg_cost_per_day_npr'], style_mult]], 
            columns=['duration', 'city_rate', 'style_mult'] 
        )
        predicted_total = budget_model.predict(input_features)[0]

        # Check if it fits the "Soft Budget" (125% of user limit)
        if predicted_total <= (user_budget * 1.25):
            final_recommendations.append(format_res(row, predicted_total, user_budget))
            seen_hubs.add(base_city_hub)
        
        if len(final_recommendations) >= 5: break

    # 4. SECOND PASS: IF LESS THAN 5, FILL WITH BEST VIBE MATCHES (Regardless of Budget)
    if len(final_recommendations) < 5:
        for _, row in sorted_df.iterrows():
            base_city_hub = row['city'].split(' ')[0]
            if base_city_hub not in seen_hubs:
                # Calculate cost anyway to show the user the price
                input_features = pd.DataFrame([[duration, row['avg_cost_per_day_npr'], style_mult]], columns=['duration', 'city_rate', 'style_mult'])
                predicted_total = budget_model.predict(input_features)[0]
                
                final_recommendations.append(format_res(row, predicted_total, user_budget))
                seen_hubs.add(base_city_hub)
            
            if len(final_recommendations) >= 5: break

    return final_recommendations

# --- HELPER FUNCTION TO KEEP CODE CLEAN ---
def format_res(row, predicted_total, user_budget):
    # Calculate Budget Fit Score
    if predicted_total <= user_budget:
        b_score = 100
    else:
        diff = (predicted_total - user_budget) / user_budget
        b_score = max(5, int(100 - (diff * 300)))

    return {
        "name": row['city'],
        "country": row['country'],
        "vibe_score": int(row['match_score']),
        "budget_score": b_score,
        "season_score": random.randint(85, 100),
        "estimated_cost": round(predicted_total, 2),
        "description": row['description'],
        "image": row['image_url'] 
    }

def add_system_log(db, message, level="info", latency=0.0):
    new_log = SystemLog(message=message, level=level, latency=latency)
    db.add(new_log)
    db.commit()