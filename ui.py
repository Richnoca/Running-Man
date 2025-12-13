import ttkbootstrap as tb
from ttkbootstrap.constants import *
import tkinter as tk
from tkinter import messagebox, filedialog
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
from fetcher import StravaFetcher
from analysis import Analyzer
import threading
import csv
import sqlite3


class RunPredictorApp:
    def __init__(self, fetcher: StravaFetcher, analyzer: Analyzer):
        self.fetcher = fetcher
        self.analyzer = analyzer
        self.root = tb.Window(
            themename="litera", title="Run Predictor (ttkbootstrap)"
        )
        self.root.geometry("1000x700")
        self._build_ui()

    # --------------------------------------------------
    # UI
    # --------------------------------------------------
    def _build_ui(self):
        nb = tb.Notebook(self.root)
        nb.pack(fill=BOTH, expand=YES, padx=10, pady=10)

        frame = tb.Frame(nb)
        nb.add(frame, text="Dashboard")

        top = tb.Frame(frame)
        top.pack(fill=X, pady=5)

        tb.Button(top, text="Refresh", bootstyle="primary",
                  command=self._on_refresh).pack(side=LEFT, padx=5)
        tb.Button(top, text="Predict", bootstyle="success",
                  command=self._on_predict).pack(side=LEFT, padx=5)
        tb.Button(top, text="Export CSV", bootstyle="info",
                  command=self._on_export).pack(side=LEFT, padx=5)
        tb.Button(top, text="Weekly Mileage", bootstyle="secondary",
                  command=self._on_plot).pack(side=LEFT, padx=5)

        body = tb.Frame(frame)
        body.pack(fill=BOTH, expand=YES)

        stats_box = tb.Labelframe(body, text="Stats", padding=10)
        stats_box.pack(side=LEFT, fill=Y)

        self.txt_stats = tk.Text(stats_box, width=42, height=28)
        self.txt_stats.pack()
        self.txt_stats.configure(state="disabled")

        plot_box = tb.Labelframe(body, text="Plot", padding=10)
        plot_box.pack(side=LEFT, fill=BOTH, expand=YES)

        self.fig, self.ax = plt.subplots(figsize=(6, 4))
        self.canvas = FigureCanvasTkAgg(self.fig, plot_box)
        self.canvas.get_tk_widget().pack(fill=BOTH, expand=YES)

        pred_box = tb.Labelframe(frame, text="Predictions", padding=10)
        pred_box.pack(fill=X)

        self.pred_list = tk.Listbox(pred_box, height=5)
        self.pred_list.pack(fill=X)

        self._refresh_stats_display()

    def run(self):
        self.root.mainloop()

    # --------------------------------------------------
    # Actions
    # --------------------------------------------------
    def _on_refresh(self):
        threading.Thread(target=self._refresh_bg, daemon=True).start()

    def _refresh_bg(self):
        try:
            self.fetcher.refresh_and_fetch(200)
            self.root.after(0, self._refresh_stats_display)
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))

    def _on_predict(self):
        distances = {
            "5K": 5.0,
            "10K": 10.0,
            "Half Marathon": 21.0975,
            "Marathon": 42.195,
        }
        preds = self.analyzer.predict_times_for_distances(distances)
        self.pred_list.delete(0, END)
        for k, v in preds.items():
            self.pred_list.insert(END, f"{k}: {v}")

    def _on_export(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv", filetypes=[("CSV files", "*.csv")]
        )
        if not path:
            return

        with sqlite3.connect(self.fetcher.db_path) as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM runs ORDER BY date")
            rows = cur.fetchall()

        with open(path, "w", newline="") as f:
            csv.writer(f).writerows(rows)

        messagebox.showinfo("Export", f"Exported {len(rows)} rows")

    def _on_plot(self):
        weeks, mileage = self.analyzer.weekly_mileage()
        self.ax.clear()
        self.ax.plot(weeks, mileage)
        self.ax.set_ylabel("Weekly km")
        self.ax.set_title("Rolling Weekly Mileage")
        self.ax.tick_params(axis="x", rotation=45)
        self.fig.tight_layout()
        self.canvas.draw()

    # --------------------------------------------------
    # Stats
    # --------------------------------------------------
    def _refresh_stats_display(self):
        stats = self.analyzer.compute_all_stats()

        lines = []
        lines.append(f"Total runs: {stats['count']}")
        lines.append(f"Avg distance: {stats['avg_distance_km']:.2f} km")
        lines.append(f"Total distance: {stats['total_distance_km']:.1f} km")
        lines.append(f"Longest run: {stats['longest_km']:.2f} km")

        if stats.get("fastest_pace_sec_per_km"):
            lines.append(
                f"Fastest pace: {Analyzer.format_time(stats['fastest_pace_sec_per_km'])}/km"
            )

        prs = self.analyzer.compute_personal_records()
        lines.append("")
        lines.append("Personal Records:")
        for k, v in prs.items():
            lines.append(f"  {k}: {v}")

        trend = stats["trend"]
        lines.append("")
        lines.append(f"Recent trend: {trend['label']} ({trend['delta']:+.1f})")

        self.txt_stats.configure(state="normal")
        self.txt_stats.delete("1.0", END)
        self.txt_stats.insert("1.0", "\n".join(lines))
        self.txt_stats.configure(state="disabled")
