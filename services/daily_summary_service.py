"""Daily summary service for efficient call history storage and sync."""
import json
import logging
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Optional, Set

from services.log_manager import get_log_dir

logger = logging.getLogger(__name__)

DAILY_SUMMARIES_DIR = "daily_summaries"
SUMMARY_INDEX_FILE = "daily_summary_index.json"

class DailySummaryService:
    """Service for managing daily call summaries with Firebase sync."""

    def __init__(self):
        self.log_dir = get_log_dir()
        self.summaries_dir = self.log_dir / DAILY_SUMMARIES_DIR
        self.summaries_dir.mkdir(exist_ok=True)
        self.index_file = self.log_dir / SUMMARY_INDEX_FILE
        self._summary_index: Dict[str, Dict[str, Any]] = {}
        self._load_index()

    def _load_index(self):
        """Load daily summary index from disk."""
        if self.index_file.exists():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    self._summary_index = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load summary index: {e}")
                self._summary_index = {}

    def _save_index(self):
        """Save daily summary index to disk."""
        try:
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(self._summary_index, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save summary index: {e}")

    def _get_date_key(self, dt: datetime) -> str:
        """Get date key in YYYY-MM-DD format."""
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        return dt.date().isoformat()

    def _get_summary_file_path(self, date_key: str) -> Path:
        """Get path to daily summary file."""
        return self.summaries_dir / f"summary_{date_key}.json"

    def add_call_to_daily_summary(self, call_data: Dict[str, Any]) -> bool:
        """Add a call to the daily summary for its date."""
        try:
            start_time = call_data.get("start_time")
            if not start_time:
                return False

            date_key = self._get_date_key(start_time)
            summary_file = self._get_summary_file_path(date_key)

            if summary_file.exists():
                with open(summary_file, "r", encoding="utf-8") as f:
                    summary = json.load(f)
            else:
                summary = {
                    "date": date_key,
                    "calls": [],
                    "stats": {
                        "total_calls": 0,
                        "total_duration_seconds": 0.0,
                        "total_rating": 0.0,
                        "rating_count": 0
                    },
                    "last_updated": datetime.now().isoformat()
                }

            call_id = call_data.get("call_id")
            if call_id:

                summary["calls"] = [c for c in summary["calls"] if c.get("call_id") != call_id]

            summary["calls"].append(call_data)

            self._update_summary_stats(summary)
            summary["last_updated"] = datetime.now().isoformat()

            with open(summary_file, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)

            self._summary_index[date_key] = {
                "date": date_key,
                "filepath": str(summary_file),
                "call_count": len(summary["calls"]),
                "last_updated": summary["last_updated"],
                "synced_to_firebase": False
            }
            self._save_index()

            logger.debug(f"Added call {call_id} to daily summary {date_key}")
            return True

        except Exception as e:
            logger.error(f"Error adding call to daily summary: {e}", exc_info=True)
            return False

    def _update_summary_stats(self, summary: Dict[str, Any]):
        """Update aggregated stats in daily summary."""
        calls = summary.get("calls", [])

        total_calls = 0
        total_duration = 0.0
        total_rating = 0.0
        rating_count = 0

        for call in calls:

            status = call.get("status", "")
            duration = call.get("duration_seconds", 0) or 0
            transcriptions = call.get("transcriptions", [])

            if (status != "in_progress" and
                duration > 0 and
                len(transcriptions) > 0):
                total_calls += 1
                total_duration += duration

                rating = call.get("rating")
                if rating:
                    if isinstance(rating, dict) and "numeric" in rating:
                        rating_value = rating["numeric"]
                    elif isinstance(rating, (int, float)):
                        rating_value = rating
                    else:
                        rating_value = None

                    if rating_value and rating_value > 0:
                        total_rating += rating_value
                        rating_count += 1

        summary["stats"] = {
            "total_calls": total_calls,
            "total_duration_seconds": total_duration,
            "total_rating": total_rating,
            "rating_count": rating_count
        }

    def get_local_summary_dates(self) -> Set[str]:
        """Get set of dates that have local summaries."""
        dates = set()
        for date_key in self._summary_index.keys():
            summary_file = self._get_summary_file_path(date_key)
            if summary_file.exists():
                dates.add(date_key)
        return dates

    def get_firebase_summary_dates(self) -> Set[str]:
        """Get set of dates that have summaries in Firebase."""
        try:
            from services.firebase_service import get_firestore_db

            db = get_firestore_db()
            if not db:
                return set()

            summaries_ref = db.collection("daily_summaries")
            docs = summaries_ref.stream()

            dates = set()
            for doc in docs:
                dates.add(doc.id)

            return dates
        except Exception as e:
            logger.error(f"Error getting Firebase summary dates: {e}", exc_info=True)
            return set()

    def get_missing_summary_dates(self) -> List[str]:
        """Get list of dates that exist in Firebase but not locally."""
        firebase_dates = self.get_firebase_summary_dates()
        local_dates = self.get_local_summary_dates()
        missing = sorted(firebase_dates - local_dates, reverse=True)
        return missing

    def sync_missing_summaries_from_firebase(self, limit: int = 30) -> int:
        """Sync missing daily summaries from Firebase."""
        missing_dates = self.get_missing_summary_dates()[:limit]

        if not missing_dates:
            logger.debug("No missing daily summaries to sync")
            return 0

        synced_count = 0
        for date_key in missing_dates:
            if self._download_summary_from_firebase(date_key):
                synced_count += 1
                logger.info(f"Synced daily summary for {date_key}")

        if synced_count > 0:
            logger.info(f"Synced {synced_count} daily summaries from Firebase")

        return synced_count

    def _download_summary_from_firebase(self, date_key: str) -> bool:
        """Download a single daily summary from Firebase."""
        try:
            from services.firebase_service import get_firestore_db

            db = get_firestore_db()
            if not db:
                return False

            doc_ref = db.collection("daily_summaries").document(date_key)
            doc = doc_ref.get()

            if not doc.exists:
                return False

            summary_data = doc.to_dict()
            if not summary_data:
                return False

            summary_file = self._get_summary_file_path(date_key)
            with open(summary_file, "w", encoding="utf-8") as f:
                json.dump(summary_data, f, indent=2, ensure_ascii=False)

            self._summary_index[date_key] = {
                "date": date_key,
                "filepath": str(summary_file),
                "call_count": len(summary_data.get("calls", [])),
                "last_updated": summary_data.get("last_updated", datetime.now().isoformat()),
                "synced_to_firebase": True
            }
            self._save_index()

            return True
        except Exception as e:
            logger.error(f"Error downloading summary for {date_key}: {e}", exc_info=True)
            return False

    def save_summary_to_firebase(self, date_key: str) -> bool:
        """Save a daily summary to Firebase."""
        try:
            from services.firebase_service import get_firestore_db

            db = get_firestore_db()
            if not db:
                logger.debug("Firestore not available")
                return False

            summary_file = self._get_summary_file_path(date_key)
            if not summary_file.exists():
                return False

            with open(summary_file, "r", encoding="utf-8") as f:
                summary_data = json.load(f)

            doc_ref = db.collection("daily_summaries").document(date_key)
            doc_ref.set(summary_data, merge=True)

            if date_key in self._summary_index:
                self._summary_index[date_key]["synced_to_firebase"] = True
                self._save_index()

            logger.info(f"Saved daily summary {date_key} to Firebase")
            return True
        except Exception as e:
            logger.error(f"Error saving summary to Firebase: {e}", exc_info=True)
            return False

    def get_all_calls(self, limit: int = 1000, restore_missing: bool = True) -> List[Dict[str, Any]]:
        """Get all calls from daily summaries, syncing missing days if needed."""
        if restore_missing:
            self.sync_missing_summaries_from_firebase(limit=30)

        all_calls = []

        summary_files = sorted(
            self.summaries_dir.glob("summary_*.json"),
            key=lambda p: p.name,
            reverse=True
        )

        for summary_file in summary_files:
            try:
                with open(summary_file, "r", encoding="utf-8") as f:
                    summary = json.load(f)

                calls = summary.get("calls", [])
                all_calls.extend(calls)

                if len(all_calls) >= limit:
                    break
            except Exception as e:
                logger.warning(f"Error reading summary file {summary_file}: {e}")
                continue

        all_calls.sort(
            key=lambda c: c.get("start_time", ""),
            reverse=True
        )

        return all_calls[:limit]

    def calculate_stats(self) -> Dict[str, Any]:
        """Calculate aggregated statistics from all daily summaries."""

        summary_files = list(self.summaries_dir.glob("summary_*.json"))

        total_calls = 0
        total_duration = 0.0
        total_rating = 0.0
        rating_count = 0

        for summary_file in summary_files:
            try:
                with open(summary_file, "r", encoding="utf-8") as f:
                    summary = json.load(f)

                stats = summary.get("stats", {})
                total_calls += stats.get("total_calls", 0)
                total_duration += stats.get("total_duration_seconds", 0.0)
                total_rating += stats.get("total_rating", 0.0)
                rating_count += stats.get("rating_count", 0)
            except Exception as e:
                logger.warning(f"Error reading summary file {summary_file}: {e}")
                continue

        average_rating = (total_rating / rating_count) if rating_count > 0 else None

        return {
            "total_calls": total_calls,
            "total_duration_seconds": total_duration,
            "average_rating": round(average_rating, 2) if average_rating else None,
            "rating_count": rating_count
        }

    def get_summary_for_date(self, date_key: str) -> Optional[Dict[str, Any]]:
        """Get daily summary for a specific date."""
        summary_file = self._get_summary_file_path(date_key)
        if summary_file.exists():
            try:
                with open(summary_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Error reading summary for {date_key}: {e}")
        return None

_daily_summary_service = None

def get_daily_summary_service() -> DailySummaryService:
    """Get singleton DailySummaryService instance."""
    global _daily_summary_service
    if _daily_summary_service is None:
        _daily_summary_service = DailySummaryService()
    return _daily_summary_service
