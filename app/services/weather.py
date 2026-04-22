import requests
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("WEATHER_API_KEY")

def get_forecast(city_name):
    url = f"http://api.openweathermap.org/data/2.5/forecast?q={city_name}&appid={API_KEY}&units=metric"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        # We grab the forecast for the first few days
        forecast_list = []
        for entry in data['list'][::8]: # Get data every 24 hours (8 * 3hr blocks)
            forecast_list.append({
                "date": entry['dt_txt'].split(" ")[0],
                "temp": entry['main']['temp'],
                "condition": entry['weather'][0]['main'] # e.g., 'Rain', 'Clear', 'Clouds'
            })
        return forecast_list
    return None