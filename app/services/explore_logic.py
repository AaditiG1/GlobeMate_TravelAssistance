import math
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Haversine Formula to calculate distance in km
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371 # Earth radius
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return round(R * c, 2)

def get_explore_recommendations(user_lat, user_lng, available_time, user_vibe, poi_df):
    # 1. Filter by Time (Hard Constraint)
    # Only show places where stay time <= available time
    filtered_df = poi_df[poi_df['time_required_hours'] <= float(available_time)].copy()

    # 2. Filter by Proximity (Within 5km)
    filtered_df['distance'] = filtered_df.apply(
        lambda row: calculate_distance(user_lat, user_lng, row['latitude'], row['longitude']), axis=1
    )
    filtered_df = filtered_df[filtered_df['distance'] <= 5.0]

    # 3. Rank by AI Vibe Matching (Scikit-Learn)
    if not filtered_df.empty:
        tfidf = TfidfVectorizer()
        vibe_matrix = tfidf.fit_transform(filtered_df['vibe'])
        user_vec = tfidf.transform([user_vibe.lower()])
        scores = cosine_similarity(user_vec, vibe_matrix).flatten()
        filtered_df['match_score'] = scores
        
        # Sort by Match Score, then Distance
        results = filtered_df.sort_values(by=['match_score', 'distance'], ascending=[False, True])
        return results.head(5).to_dict('records')
    
    return []