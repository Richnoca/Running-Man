import sqlite3
import math
import numpy as np
from sklearn.linear_model import LinearRegression
from collections import Counter
from typing import List, Tuple, Dict, Any
import datetime


class Analyzer:
    def __init__(self, db_path: str = "runs.db"):
        self.db_path = db_path
        self._riegel_cache = None

    # --------------------------------------------------
    # Data access
    # --------------------------------------------------
    def _fetch_all_runs(self) -> List[Tuple[float, float, int]]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT distance_km, duration_sec, id FROM runs ORDER BY date"
            )
            return cur.fetchall()

    # --------------------------------------------------
    # Basic stats
    # --------------------------------------------------
    def compute_basic_stats(self) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT COUNT(*), AVG(distance_km), SUM(distance_km), MAX(distance_km) FROM runs"
            )
            count, avg_distance, total_distance, longest = cur.fetchone()

            cur.execute("SELECT distance_km FROM runs")
            distances = [round(row[0] * 2) / 2 for row in cur.fetchall() if row[0]]
            most_common = Counter(distances).most_common(10)

            cur.execute("SELECT distance_km, duration_sec FROM runs")
            rows = cur.fetchall()
            paces = [t / d for d, t in rows if d and d > 0]
            fastest_pace = min(paces) if paces else None

        return {
            "count": count,
            "avg_distance_km": avg_distance,
            "total_distance_km": total_distance,
            "longest_km": longest,
            "most_common_distances": most_common,
            "fastest_pace_sec_per_km": fastest_pace,
        }

    # --------------------------------------------------
    # Training load + trend
    # --------------------------------------------------
    def compute_training_loads(self) -> Dict[str, float]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT distance_km, duration_sec FROM runs ORDER BY date"
            )
            rows = cur.fetchall()

        loads = []
        for d, t in rows:
            if d and d > 0:
                pace = t / d
                load = d * (pace / 3600.0) * 100.0
            else:
                load = 0.0
            loads.append(load)

        last7 = sum(loads[-7:]) if len(loads) >= 7 else sum(loads)
        last42 = sum(loads[-42:]) if len(loads) >= 42 else sum(loads)

        return {
            "fitness": last42,
            "fatigue": last7,
            "form": last42 - last7,
        }

    def compute_recent_trend(self) -> Dict[str, Any]:
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT distance_km, duration_sec
                FROM runs
                ORDER BY date DESC
                LIMIT 14
                """
            )
            rows = cur.fetchall()

        if len(rows) < 14:
            return {"label": "N/A", "delta": 0.0}

        def load(d, t):
            return d * ((t / d) / 3600.0) * 100.0 if d and d > 0 else 0.0

        recent = sum(load(d, t) for d, t in rows[:7])
        prev = sum(load(d, t) for d, t in rows[7:])

        delta = recent - prev
        arrow = "↑" if delta > 0 else "↓"
        label = "Improving" if delta > 0 else "Declining"

        return {"label": f"{arrow} {label}", "delta": delta}

    # --------------------------------------------------
    # Riegel model + confidence
    # --------------------------------------------------
    def fit_riegel(self) -> Dict[str, float]:
        if self._riegel_cache is not None:
            return self._riegel_cache

        runs = [
            (d, t)
            for d, t, _ in self._fetch_all_runs()
            if d >= 2 and 180 < (t / d) < 600
        ]

        if len(runs) < 5:
            return {}

        distances = np.array([d for d, _ in runs])
        durations = np.array([t for _, t in runs])

        logD = np.log(distances)
        logT = np.log(durations)

        model = LinearRegression().fit(logD.reshape(-1, 1), logT)

        params = {
            "a": float(model.intercept_),
            "b": float(model.coef_[0]),
            "sigma": float(np.std(logT - model.predict(logD.reshape(-1, 1)))),
        }

        self._riegel_cache = params
        return params

    def predict_with_confidence(self, dist_km: float) -> Tuple[float, float | None]:
        params = self.fit_riegel()
        if not params:
            return float("nan"), None

        a, b, sigma = params["a"], params["b"], params["sigma"]
        pred = math.exp(a) * (dist_km ** b)
        margin = pred * (math.exp(sigma) - 1)

        return pred, margin

    def predict_times_for_distances(self, distances: Dict[str, float]) -> Dict[str, str]:
        out = {}
        for name, km in distances.items():
            sec, margin = self.predict_with_confidence(km)
            if margin:
                out[name] = f"{self.format_time(sec)} ± {self.format_time(margin)}"
            else:
                out[name] = self.format_time(sec)
        return out

    # --------------------------------------------------
    # Personal records
    # --------------------------------------------------
    def compute_personal_records(self) -> Dict[str, str]:
        targets = {
            "1K": 1.0,
            "5K": 5.0,
            "10K": 10.0,
            "Half": 21.0975,
        }

        prs = {}
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT distance_km, duration_sec FROM runs")
            rows = cur.fetchall()

        for name, target_km in targets.items():
            best = float("inf")
            for d, t in rows:
                if d and d >= target_km:
                    pace = t / d
                    est = pace * target_km
                    best = min(best, est)
            prs[name] = self.format_time(best) if best < float("inf") else "N/A"

        return prs

    # --------------------------------------------------
    # Weekly mileage
    # --------------------------------------------------
    def weekly_mileage(self):
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT date, distance_km FROM runs")
            rows = cur.fetchall()

        weekly = {}
        for date_str, d in rows:
            week = datetime.datetime.fromisoformat(date_str).strftime("%Y-%W")
            weekly[week] = weekly.get(week, 0.0) + (d or 0.0)

        weeks = sorted(weekly.keys())
        mileage = [weekly[w] for w in weeks]
        return weeks, mileage

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------
    @staticmethod
    def format_time(seconds: float) -> str:
        if seconds is None or math.isnan(seconds):
            return "N/A"
        seconds = int(round(seconds))
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h}:{m:02d}:{s:02d}"

    def compute_all_stats(self) -> Dict[str, Any]:
        stats = self.compute_basic_stats()
        stats.update(self.compute_training_loads())
        stats["trend"] = self.compute_recent_trend()
        return stats
