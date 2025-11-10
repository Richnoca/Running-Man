import requests
import sqlite3
import time
import numpy as np
from sklearn.linear_model import LinearRegression
import matplotlib.pyplot as plt
import json
import os
from collections import Counter

# --- CONFIG ---
CONFIG_FILE = "config.json"
DB_PATH = "runs.db"
NUM_ACTIVITIES = 30  # Number of recent runs to fetch

# --- LOAD CONFIG ---
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE, "r") as f:
        config = json.load(f)
else:
    print("Please create config.json with client_id, client_secret, refresh_token")
    exit()

CLIENT_ID = config["client_id"]
CLIENT_SECRET = config["client_secret"]
REFRESH_TOKEN = config["refresh_token"]

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
        config["refresh_token"] = tokens["refresh_token"]
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
        return tokens["access_token"]
    else:
        print("Failed to refresh access token:", response.status_code, response.text)
        exit()

# --- FETCH RUNS ---
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
        time.sleep(1)
    return runs

# --- INSERT INTO DB ---
def insert_runs_into_db(runs, db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT UNIQUE,
        distance_km REAL,
        duration_sec REAL
    )
    ''')
    for run in runs:
        try:
            cursor.execute(
                "INSERT INTO runs (date, distance_km, duration_sec) VALUES (?, ?, ?)",
                (run["date"], run["distance_km"], run["duration_sec"])
            )
        except sqlite3.IntegrityError:
            continue
    conn.commit()
    conn.close()

# --- STATISTICS ---
def get_average_distance(cursor):
    cursor.execute("SELECT AVG(distance_km) FROM runs")
    return cursor.fetchone()[0]

def get_top_common_distances(cursor, top_n=10):
    cursor.execute("SELECT distance_km FROM runs")
    distances = [round(row[0] * 2)/2 for row in cursor.fetchall()]  # round to nearest 0.5 km
    counter = Counter(distances)
    return counter.most_common(top_n)

def get_fastest_pace(cursor):
    cursor.execute("SELECT distance_km, duration_sec FROM runs")
    data = cursor.fetchall()
    if not data:
        return None
    paces = [d[1]/d[0] for d in data if d[0] > 0]
    return min(paces)

# --- FORMAT TIME ---
def format_time(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"

# --- VISUALIZATION ---
def plot_runs(data):
    distances = [d[0] for d in data]
    durations = [d[1] for d in data]
    plt.scatter(distances, durations)
    plt.xlabel("Distance (km)")
    plt.ylabel("Duration (sec)")
    plt.title("Run Distance vs Duration")
    plt.show()

def plot_histogram(cursor):
    cursor.execute("SELECT distance_km FROM runs")
    distances = [row[0] for row in cursor.fetchall()]
    plt.hist(distances, bins=10, edgecolor='black')
    plt.xlabel("Distance (km)")
    plt.ylabel("Number of Runs")
    plt.title("Histogram of Run Distances")
    plt.show()

# --- MAIN WORKFLOW ---
if __name__ == "__main__":
    # Refresh token & fetch runs
    access_token = refresh_access_token(CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN)
    print("Access token refreshed.")

    runs = fetch_strava_runs(access_token, NUM_ACTIVITIES)
    print(f"Fetched {len(runs)} runs from Strava.")

    insert_runs_into_db(runs, DB_PATH)
    print("Inserted runs into database (duplicates skipped).")

    # Load data
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT distance_km, duration_sec FROM runs")
    data = cursor.fetchall()

    if not data:
        print("No run data found in database.")
        conn.close()
        exit()

    # Statistics
    avg_distance = get_average_distance(cursor)
    top_distances = get_top_common_distances(cursor)
    fastest_pace = get_fastest_pace(cursor)

    print(f"\nAverage run distance: {avg_distance:.2f} km")
    print("Top 10 most common run distances (rounded to nearest 0.5 km):")
    for dist, count in top_distances:
        print(f"{dist:.1f} km: {count} runs")
    if fastest_pace:
        print(f"Fastest pace: {fastest_pace:.2f} sec/km ({format_time(fastest_pace)} per km)")

    # Predict race times
    X = np.array([d[0] for d in data]).reshape(-1,1)
    y = np.array([d[1] for d in data])
    model = LinearRegression()
    model.fit(X, y)

    distances = {
        "5K": 5.0,
        "10K": 10.0,
        "Half Marathon": 21.0975,
        "Marathon": 42.195
    }

    custom_input = input("Enter custom race distances in km separated by commas, or press Enter to skip: ")
    if custom_input:
        try:
            custom_distances = [float(x.strip()) for x in custom_input.split(",")]
            distances.update({f"Custom {i+1}": d for i,d in enumerate(custom_distances)})
        except ValueError:
            print("Invalid input. Using default distances.")

    print("\nPredicted Race Times:")
    for race, km in distances.items():
        pred_sec = model.predict(np.array([[km]]))[0]
        print(f"{race}: {format_time(pred_sec)}")

    # Visualizations
    plot_choice = input("Do you want to see a scatter plot of your runs? (y/n): ")
    if plot_choice.lower() == "y":
        plot_runs(data)

    hist_choice = input("Do you want to see a histogram of run distances? (y/n): ")
    if hist_choice.lower() == "y":
        plot_histogram(cursor)

    conn.close()
