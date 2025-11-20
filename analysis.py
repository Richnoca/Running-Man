import sqlite3
import math
import numpy as np
from sklearn.linear_model import LinearRegression
from collections import Counter
from typing import List, Tuple, Dict, Any

class Analyzer:
    def __init__(self, db_path: str = "runs.db"):
        self.db_path = db_path

    def _fetch_all_runs(self) -> List[Tuple[float, float, int]]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT distance_km, duration_sec, id FROM runs ORDER BY date")
            return cur.fetchall()

    def compute_basic_stats(self) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*), AVG(distance_km), SUM(distance_km), MAX(distance_km) FROM runs")
            count, avg_distance, total_distance, longest = cur.fetchone()
            # most common distances rounded to 0.5
            cur.execute("SELECT distance_km FROM runs")
            distances = [round(row[0] * 2) / 2 for row in cur.fetchall()]
            most_common = Counter(distances).most_common(10)
            # fastest pace (sec per km)
            cur.execute("SELECT distance_km, duration_sec FROM runs")
            rows = cur.fetchall()
            paces = [r[1] / r[0] for r in rows if r[0] > 0]
            fastest_pace = min(paces) if paces else None
        return {
            "count": count,
            "avg_distance_km": avg_distance,
            "total_distance_km": total_distance,
            "longest_km": longest,
            "most_common_distances": most_common,
            "fastest_pace_sec_per_km": fastest_pace
        }

    def fit_riegel(self) -> Dict[str, float]:
        # Use Riegel T2 = T1 * (D2/D1)^exponent. Solve for exponent and T1 using log regression.
        runs = self._fetch_all_runs()
        if len(runs) < 3:
            return {}
        distances = np.array([r[0] for r in runs if r[0] > 0])
        durations = np.array([r[1] for r in runs if r[0] > 0])
        # log-log regression: log(T) = a + b * log(D)
        logD = np.log(distances)
        logT = np.log(durations)
        model = LinearRegression()
        model.fit(logD.reshape(-1,1), logT)
        a = model.intercept_
        b = model.coef_[0]  # this is exponent in log space
        # Riegel exponent is b (since T = exp(a) * D^b)
        return {"a": float(a), "b": float(b)}

    def predict_time_riegel(self, dist_km: float) -> float:
        params = self.fit_riegel()
        if not params:
            # fallback: linear model seconds = m*km + c
            runs = self._fetch_all_runs()
            if len(runs) < 2:
                return float("nan")
            X = np.array([r[0] for r in runs]).reshape(-1,1)
            y = np.array([r[1] for r in runs])
            lr = LinearRegression().fit(X, y)
            return float(lr.predict([[dist_km]])[0])
        a = params["a"]
        b = params["b"]
        pred = math.exp(a) * (dist_km ** b)
        return float(pred)

    def predict_times_for_distances(self, distances: dict) -> Dict[str, str]:
        out = {}
        for name, km in distances.items():
            sec = self.predict_time_riegel(km)
            out[name] = self.format_time(sec)
        return out

    @staticmethod
    def format_time(seconds: float) -> str:
        if seconds is None or math.isnan(seconds):
            return "N/A"
        seconds = max(0, int(round(seconds)))
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h}:{m:02d}:{s:02d}"

    def best_effort_from_stream(self, distances_m: List[float], times_s: List[float], target_m: int) -> Tuple[float, int]:
        """
        Sliding window on distance/time arrays (distance array is cumulative meters).
        Returns best time (seconds) and index where it starts.
        """
        if not distances_m or not times_s:
            return float("inf"), -1
        best = float("inf")
        best_idx = -1
        n = len(distances_m)
        i = 0
        j = 0
        while i < n:
            # move j so that distances_m[j] - distances_m[i] >= target_m
            while j < n and (distances_m[j] - distances_m[i]) < target_m:
                j += 1
            if j >= n:
                break
            time_window = times_s[j] - times_s[i]
            if time_window < best:
                best = time_window
                best_idx = i
            i += 1
        return best, best_idx

    def compute_training_loads(self) -> Dict[str, Any]:
        """
        Simple load: for each run, define load = distance_km * (average_pace_sec_per_km / 3600) * 100
        Then compute 7-day and 42-day rolling sums (approximate using dates if needed).
        For simplicity here: compute last 7-run sum and last 42-run sum as a proxy.
        """
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT distance_km, duration_sec FROM runs ORDER BY date")
            rows = cur.fetchall()
        loads = []
        for d, t in rows:
            if d and d > 0:
                pace = t / d  # sec per km
                load = d * (pace / 3600.0) * 100.0
            else:
                load = 0.0
            loads.append(load)
        last7 = sum(loads[-7:]) if loads else 0.0
        last42 = sum(loads[-42:]) if loads else 0.0
        fitness = last42
        fatigue = last7
        form = fitness - fatigue
        return {"fitness": fitness, "fatigue": fatigue, "form": form, "last7": last7, "last42": last42}

    def compute_all_stats(self) -> Dict[str, Any]:
        stats = self.compute_basic_stats()
        stats.update(self.compute_training_loads())
        params = self.fit_riegel()
        stats["riegel_params"] = params
        return stats
