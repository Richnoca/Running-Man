import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ttkbootstrap.scrolled import ScrolledFrame
import tkinter as tk
from tkinter import messagebox, filedialog
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from fetcher import StravaFetcher
from analysis import Analyzer
import threading
import csv
import datetime
import sqlite3

class RunPredictorApp:
    def __init__(self, fetcher: StravaFetcher, analyzer: Analyzer):
        self.fetcher = fetcher
        self.analyzer = analyzer
        self.root = tb.Window(themename="litera", title="Run Predictor (ttkbootstrap)")
        self.root.geometry("1000x700")
        self._build_ui()

    def _build_ui(self):
        nb = tb.Notebook(self.root)
        nb.pack(fill=BOTH, expand=YES, padx=10, pady=10)

        # Dashboard Tab
        frame_dash = tb.Frame(nb)
        nb.add(frame_dash, text="Dashboard")

        top_row = tb.Frame(frame_dash)
        top_row.pack(fill=X, padx=5, pady=5)

        self.btn_refresh = tb.Button(top_row, text="Refresh from Strava", bootstyle="primary", command=self._on_refresh)
        self.btn_refresh.pack(side=LEFT, padx=5)
        self.btn_predict = tb.Button(top_row, text="Predict Standard Races", bootstyle="success", command=self._on_predict)
        self.btn_predict.pack(side=LEFT, padx=5)
        self.btn_export = tb.Button(top_row, text="Export CSV", bootstyle="info", command=self._on_export)
        self.btn_export.pack(side=LEFT, padx=5)
        self.btn_plot = tb.Button(top_row, text="Show Trends", bootstyle="secondary", command=self._on_plot)
        self.btn_plot.pack(side=LEFT, padx=5)

        right_side = tb.Frame(frame_dash)
        right_side.pack(fill=BOTH, expand=YES, padx=8, pady=8)

        # Stats panel
        stats_box = tb.Labelframe(right_side, text="Key Stats", padding=10)
        stats_box.pack(side=LEFT, fill=Y, padx=5, pady=5)

        self.txt_stats = tk.Text(stats_box, width=40, height=20)
        self.txt_stats.pack(fill=BOTH, expand=YES)

        # Plot area
        plot_box = tb.Labelframe(right_side, text="Plots", padding=10)
        plot_box.pack(side=LEFT, fill=BOTH, expand=YES, padx=5)

        self.fig, self.ax = plt.subplots(figsize=(6,4))
        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_box)
        self.canvas.get_tk_widget().pack(fill=BOTH, expand=YES)

        # Bottom area for predictions (list)
        pred_box = tb.Labelframe(frame_dash, text="Predictions", padding=10)
        pred_box.pack(fill=X, padx=5, pady=5)
        self.pred_list = tk.Listbox(pred_box, height=5)
        self.pred_list.pack(fill=X, expand=YES)

        # Populate initial stats
        self._refresh_stats_display()

    def run(self):
        self.root.mainloop()

    def _set_buttons_state(self, enabled: bool):
        state = "normal" if enabled else "disabled"
        for w in [self.btn_refresh, self.btn_predict, self.btn_export, self.btn_plot]:
            w.configure(state=state)

    def _on_refresh(self):
        self._set_buttons_state(False)
        t = threading.Thread(target=self._refresh_background)
        t.start()

    def _refresh_background(self):
        try:
            count = self.fetcher.refresh_and_fetch(num_activities=200)
            self._refresh_stats_display()
            messagebox.showinfo("Refresh complete", f"Fetched & stored up to {count} runs.")
        except Exception as e:
            messagebox.showerror("Error", str(e))
        finally:
            self._set_buttons_state(True)

    def _on_predict(self):
        distances = {
            "5K": 5.0,
            "10K": 10.0,
            "Half Marathon": 21.0975,
            "Marathon": 42.195
        }
        preds = self.analyzer.predict_times_for_distances(distances)
        self.pred_list.delete(0, 'end')
        for k, v in preds.items():
            self.pred_list.insert('end', f"{k}: {v}")

    def _on_export(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files","*.csv")])
        if not path:
            return
        with sqlite3.connect(self.fetcher.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, date, distance_km, duration_sec, name, elevation, avg_heartrate FROM runs ORDER BY date")
            rows = cur.fetchall()
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["id","date","distance_km","duration_sec","name","elevation","avg_heartrate"])
            writer.writerows(rows)
        messagebox.showinfo("Export", f"Exported {len(rows)} rows to {path}")

    def _on_plot(self):
        # show monthly totals and pace scatter
        with sqlite3.connect(self.fetcher.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT date, distance_km, duration_sec FROM runs ORDER BY date")
            rows = cur.fetchall()

        if not rows:
            messagebox.showinfo("No data", "No runs in DB yet.")
            return
        # prepare monthly totals
        monthly = {}
        pts_x = []
        pts_y = []
        for date_str, d, t in rows:
            dt = datetime.datetime.fromisoformat(date_str)
            key = dt.strftime("%Y-%m")
            monthly[key] = monthly.get(key, 0.0) + (d or 0.0)
            if d and d > 0 and t:
                pts_x.append(d)
                pts_y.append(t/d)  # sec per km (pace)
        months = sorted(monthly.keys())
        totals = [monthly[m] for m in months]
        

        self.ax.clear()
        self.ax2 = self.ax.twinx()
        bar_pos = range(len(months))
        self.ax.bar(bar_pos, totals, alpha=0.6)
        self.ax.set_xticks(bar_pos)
        self.ax.set_xticklabels(months, rotation=45, ha='right')
        self.ax.set_ylabel("Monthly km")

        # pace scatter on second axis
        self.ax2.scatter(pts_x, pts_y, marker='o')
        self.ax2.set_ylabel("Pace (sec/km)")
        self.fig.tight_layout()
        self.canvas.draw()

    def _refresh_stats_display(self):
        stats = self.analyzer.compute_all_stats()
        self.txt_stats.delete("1.0", "end")
        lines = []
        lines.append(f"Total runs: {stats.get('count')}")
        lines.append(f"Avg distance: {stats.get('avg_distance_km'):.2f} km" if stats.get('avg_distance_km') else "Avg distance: N/A")
        lines.append(f"Total distance: {stats.get('total_distance_km'):.2f} km" if stats.get('total_distance_km') else "Total: N/A")
        lines.append(f"Longest run: {stats.get('longest_km'):.2f} km" if stats.get('longest_km') else "Longest: N/A")
        fp = stats.get('fastest_pace_sec_per_km')
        if fp:
            lines.append(f"Fastest pace: {Analyzer.format_time(fp)} per km")
        lines.append("Most common distances (km):")
        for d, c in stats.get('most_common_distances', []):
            lines.append(f"  {d:.1f} km: {c} runs")
        lines.append("")
        lines.append("Training load:")
        lines.append(f"  Fitness (42-run sum proxy): {stats.get('fitness'):.1f}")
        lines.append(f"  Fatigue (7-run sum proxy): {stats.get('fatigue'):.1f}")
        lines.append(f"  Form: {stats.get('form'):.1f}")
        self.txt_stats.insert("1.0", "\n".join(lines))
