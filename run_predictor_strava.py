"""
Entry point. Launches the app (GUI) or can run CLI operations.
"""
import argparse
from ui import RunPredictorApp
from fetcher import StravaFetcher
from analysis import Analyzer

def main():
    parser = argparse.ArgumentParser(description="Strava Run Predictor (GUI)")
    parser.add_argument("--nogui", action="store_true", help="Run CLI-only workflow and exit")
    parser.add_argument("--update", action="store_true", help="Refresh token and fetch latest runs into DB")
    args = parser.parse_args()

    fetcher = StravaFetcher()
    analyzer = Analyzer(fetcher.db_path)

    if args.nogui:
        if args.update:
            fetcher.refresh_and_fetch()
        # Run CLI summary
        stats = analyzer.compute_all_stats()
        for k, v in stats.items():
            print(f"{k}: {v}")
        return

    # Launches GUI
    app = RunPredictorApp(fetcher=fetcher, analyzer=analyzer)
    app.run()

if __name__ == "__main__":
    main()
