import sqlite3
from collections import Counter

DB_PATH = "runs.db"

def get_average_distance(cursor):
    cursor.execute("SELECT AVG(distance_km) FROM runs")
    avg = cursor.fetchone()[0]
    return avg

def get_top_10_common_distances(cursor):
    cursor.execute("SELECT distance_km FROM runs")
    distances = [round(row[0] * 2) / 2 for row in cursor.fetchall()]  # round to nearest 0.5 km
    counter = Counter(distances)
    return counter.most_common(10)

if __name__ == "__main__":
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    avg_distance = get_average_distance(cursor)
    print(f"Average run distance: {avg_distance:.2f} km")

    print("\nTop 10 most common run distances (rounded to nearest 0.5 km):")
    for dist, count in get_top_10_common_distances(cursor):
        print(f"{dist:.1f} km: {count} runs")

    conn.close()