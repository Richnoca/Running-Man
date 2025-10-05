import requests
import sqlite3
import time
import numpy as np
from sklearn.linear_model import LinearRegression

# --- CONFIGURATION ---
CLIENT_ID = "179724"  # Replace with your Strava client ID
CLIENT_SECRET = "3f77e89798fed5b04de5c58d355e50cd28ea443d"  # Replace with your Strava client secret
REFRESH_TOKEN = "f24322e4d7748df3f61f7518ab404111594f3226"  # Replace with your Strava refresh token
DB_PATH = "runs.db"
NUM_ACTIVITIES = 30  # Number of recent activities to fetch

# --- REFRESH ACCESS TOKEN ---
def refresh_access_token(client_id, client_secret, refresh_token):
    url = "https://www.strava.com/oauth/token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    response = requests.post(url, data=payload)
    if response.status_code == 200:
        tokens = response.json()
        return tokens["access_token"], tokens["refresh_token"]
    else:
        print("Failed to refresh access token:", response.status_code, response.text)
        exit()

# ...existing code...
def refresh_access_token(client_id, client_secret, refresh_token):
    url = "https://www.strava.com/oauth/token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }
    response = requests.post(url, data=payload)
    print("DEBUG: Token response:", response.status_code, response.text)  # Add this line
    if response.status_code == 200:
        tokens = response.json()
        return tokens["access_token"], tokens["refresh_token"]
    else:
        print("Failed to refresh access token:", response.status_code, response.text)
        exit()
# ...existing code...

# --- FETCH ACTIVITIES FROM STRAVA ---
def fetch_strava_runs(access_token, num_activities=30):
    url = "https://www.strava.com/api/v3/athlete/activities"
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"per_page": 30, "page": 1}
    runs = []

    while len(runs) < num_activities:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            print("Error fetching activities:", response.status_code, response.text)
            break
        activities = response.json()
        if not activities:
            break
        for act in activities:
            if act.get("type") == "Run":
                runs.append({
                    "date": act["start_date_local"],
                    "distance_km": act["distance"] / 1000.0,
                    "duration_sec": act["moving_time"]
                })
                if len(runs) >= num_activities:
                    break
        params["page"] += 1
        time.sleep(1)  # Be polite to the API
    return runs

# --- INSERT RUNS INTO SQLITE ---
def insert_runs_into_db(runs, db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        distance_km REAL,
        duration_sec REAL
    )
    ''')
    for run in runs:
        cursor.execute(
            "INSERT INTO runs (date, distance_km, duration_sec) VALUES (?, ?, ?)",
            (run["date"], run["distance_km"], run["duration_sec"])
        )
    conn.commit()
    conn.close()

# --- FORMAT TIME ---
def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"

# --- MAIN WORKFLOW ---
if __name__ == "__main__":
    # 1. Refresh access token
    access_token, new_refresh_token = refresh_access_token(CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN)
    print("Access token refreshed.")

    # Optionally, save new_refresh_token somewhere safe for next time

    # 2. Fetch runs from Strava
    runs = fetch_strava_runs(access_token, NUM_ACTIVITIES)
    print(f"Fetched {len(runs)} runs from Strava.")

    # 3. Insert into SQLite
    insert_runs_into_db(runs, DB_PATH)
    print("Inserted runs into database.")

    # 4. Load data from SQLite and train ML predictor
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT distance_km, duration_sec FROM runs")
    data = cursor.fetchall()
    conn.close()

    if not data:
        print("No run data found. Please add your runs to the database.")
        exit()

    X = np.array([d[0] for d in data]).reshape(-1, 1)  # distances
    y = np.array([d[1] for d in data])                # durations

    model = LinearRegression()
    model.fit(X, y)

    distances = {
        "5K": 5.0,
        "10K": 10.0,
        "Half Marathon": 21.0975,
        "Marathon": 42.195
    }

    print("\nPredicted Race Times (using your run history):")
    for race, km in distances.items():
        pred_sec = model.predict(np.array([[km]]))[0]
        print(f"{race}: {format_time(pred_sec)}")