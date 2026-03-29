"""Call logging service for capturing and storing call transcripts."""
import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any

from services.log_manager import get_log_dir

logger = logging.getLogger(__name__)

class CallLogger:
    """Manages call log lifecycle and transcription storage."""

    def __init__(self, log_dir: Optional[Path] = None):
        """
        Initialize the CallLogger.

        Args:
            log_dir: Directory to store call logs. Defaults to centralized log directory.
        """
        if log_dir is None:

            log_dir = get_log_dir()

        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)

        self.call_id: Optional[str] = None
        self.call_data: Optional[Dict[str, Any]] = None
        self.transcriptions: List[Dict[str, Any]] = []

    def start_call(
        self,
        client_name: str,
        phone_number: str,
        client_code: str
    ) -> str:
        """
        Start logging a new call.

        Args:
            client_name: Name of the client
            phone_number: Phone number of the caller
            client_code: Client code

        Returns:
            call_id: Unique identifier for this call
        """
        self.call_id = str(uuid.uuid4())
        start_time = datetime.now()

        self.call_data = {
            "call_id": self.call_id,
            "start_time": start_time.isoformat(),
            "end_time": None,
            "duration_seconds": None,
            "client": {
                "name": client_name,
                "phone_number": phone_number,
                "client_code": client_code
            },
            "transcriptions": [],
            "summary": None,
            "mood": None,
            "rating": None,
            "status": "in_progress"
        }

        self.transcriptions = []

        try:
            self._cleanup_orphaned_blank_files()
        except Exception as e:
            logger.warning(f"Failed to cleanup orphaned blank files: {e}")

        self._save_transcriptions_incremental()

        logger.info(f"Started call logging: call_id={self.call_id}, client={client_name}")
        return self.call_id

    def log_transcription(
        self,
        text: str,
        speaker: str,
        timestamp: Optional[datetime] = None
    ) -> None:
        """
        Log a transcription entry.

        Args:
            text: The transcribed text
            speaker: "user" or "agent"
            timestamp: Timestamp of the transcription. Defaults to now.
        """
        if not self.call_data:
            logger.warning("Attempted to log transcription before call started")
            return

        if timestamp is None:
            timestamp = datetime.now()

        transcription_entry = {
            "timestamp": timestamp.isoformat(),
            "speaker": speaker,
            "text": text
        }

        self.transcriptions.append(transcription_entry)
        self.call_data["transcriptions"].append(transcription_entry)

        self._save_transcriptions_incremental()

        logger.debug(f"Logged transcription: speaker={speaker}, text={text[:50]}...")

    def _save_transcriptions_incremental(self) -> None:
        """Save current transcriptions to file incrementally for live access."""
        if not self.call_id or not self.call_data:
            return

        try:
            filename = f"call_{self.call_id}.json"
            filepath = self.log_dir / filename

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.call_data, f, indent=2, ensure_ascii=False)

            logger.debug(f"Incrementally saved transcriptions to {filepath} ({len(self.transcriptions)} entries)")
        except Exception as e:
            logger.warning(f"Failed to save transcriptions incrementally: {e}", exc_info=True)

    async def generate_call_metadata(
        self,
        llm,
        conversation_history: str
    ) -> Dict[str, Any]:
        """
        Generate call summary, mood, and rating using LLM.

        Args:
            llm: The LLM instance to use for generation
            conversation_history: Full conversation transcript

        Returns:
            Dictionary with summary, mood, and rating
        """
        prompt = f"""Based on the following conversation transcript, provide:
1. A brief 1-2 sentence summary of the conversation
2. The caller's emotional mood (one word or short phrase: e.g., "happy", "frustrated", "neutral", "satisfied", "confused", "angry")
3. A rating of the conversation quality (numeric 1-5 and text description like "Excellent", "Good", "Fair", "Poor")

Conversation transcript:
{conversation_history}

Respond in JSON format:
{{
    "summary": "1-2 sentence summary here",
    "mood": "mood description",
    "rating": {{
        "numeric": 4,
        "text": "Good"
    }}
}}"""

        try:

            from livekit.agents import llm as llm_module
            import inspect

            response = None
            sig = inspect.signature(llm.chat) if hasattr(llm, 'chat') else None

            try:
                async with llm:
                    messages = [
                        llm_module.ChatMessage(role="user", content=[prompt])
                    ]

                    if hasattr(llm, 'chat'):

                        if sig and len(sig.parameters) == 1:

                            response = await llm.chat()
                        else:
                            response = await llm.chat(messages)
            except Exception as e1:

                try:
                    from livekit.plugins import openai

                    temp_llm = openai.LLM(model="gpt-4o-mini")
                    async with temp_llm:
                        messages = [
                            llm_module.ChatMessage(role="user", content=[prompt])
                        ]
                        response = await temp_llm.chat(messages=messages)
                except Exception as e2:

                    logger.warning(f"Could not generate metadata with LLM (tried multiple formats): {e1}, {e2}")
                    raise e2

            if hasattr(response, 'choices') and len(response.choices) > 0:
                response_text = response.choices[0].message.content.strip()
            elif hasattr(response, 'content'):
                response_text = response.content.strip()
            elif hasattr(response, 'text'):
                response_text = response.text.strip()
            else:
                response_text = str(response).strip()

            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()

            metadata = json.loads(response_text)

            if "summary" not in metadata:
                metadata["summary"] = "No summary available"
            if "mood" not in metadata:
                metadata["mood"] = "neutral"
            if "rating" not in metadata:
                metadata["rating"] = {"numeric": 3, "text": "Neutral"}
            elif not isinstance(metadata["rating"], dict):

                rating_num = int(metadata["rating"]) if isinstance(metadata["rating"], (int, float)) else 3
                rating_text = self._get_rating_text(rating_num)
                metadata["rating"] = {"numeric": rating_num, "text": rating_text}

            logger.info(f"Generated call metadata: summary={metadata['summary'][:50]}..., mood={metadata['mood']}, rating={metadata['rating']}")
            return metadata

        except Exception as e:
            logger.error(f"Failed to generate call metadata: {e}", exc_info=True)

            return {
                "summary": "Unable to generate summary",
                "mood": "unknown",
                "rating": {"numeric": 3, "text": "Neutral"}
            }

    def _get_rating_text(self, numeric: int) -> str:
        """Convert numeric rating to text."""
        rating_map = {
            1: "Poor",
            2: "Fair",
            3: "Neutral",
            4: "Good",
            5: "Excellent"
        }
        return rating_map.get(numeric, "Neutral")

    def end_call(
        self,
        summary: Optional[str] = None,
        mood: Optional[str] = None,
        rating: Optional[Dict[str, Any]] = None,
        status: str = "completed",
        save_to_firebase: bool = True
    ) -> Optional[str]:
        """
        End call logging and save to file.

        Args:
            summary: Call summary (1-2 sentences)
            mood: Caller mood description
            rating: Rating dictionary with numeric and text
            status: Call status (completed, ended, error)
            save_to_firebase: Whether to save to Firebase Firestore (default: True)

        Returns:
            Path to saved log file, or None if call wasn't started
        """
        if not self.call_data:
            logger.warning("Attempted to end call that was never started")
            return None

        end_time = datetime.now()
        start_time = datetime.fromisoformat(self.call_data["start_time"])
        duration = (end_time - start_time).total_seconds()

        self.call_data["end_time"] = end_time.isoformat()
        self.call_data["duration_seconds"] = duration
        self.call_data["status"] = status

        if summary:
            self.call_data["summary"] = summary
        if mood:
            self.call_data["mood"] = mood
        if rating:
            self.call_data["rating"] = rating

        timestamp_str = start_time.strftime("%Y%m%d_%H%M%S")
        filename = f"call_{timestamp_str}_{self.call_id[:8]}.json"
        filepath = self.log_dir / filename

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.call_data, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved call log: {filepath}, duration={duration:.2f}s, transcriptions={len(self.transcriptions)}")

            if len(self.transcriptions) > 0 and duration > 0:
                try:
                    from services.daily_summary_service import get_daily_summary_service
                    summary_service = get_daily_summary_service()
                    summary_service.add_call_to_daily_summary(self.call_data)

                    date_key = summary_service._get_date_key(self.call_data["start_time"])
                    summary_service.save_summary_to_firebase(date_key)
                except Exception as e:
                    logger.warning(f"Failed to add call to daily summary: {e}")

            initial_file = self.log_dir / f"call_{self.call_id}.json"
            if initial_file.exists():
                try:
                    initial_file.unlink()
                    logger.info(f"Cleaned up initial blank call file: {initial_file}")
                except Exception as e:
                    logger.warning(f"Failed to clean up initial call file {initial_file}: {e}")

            try:
                self._cleanup_orphaned_blank_files()
            except Exception as e:
                logger.warning(f"Failed to cleanup orphaned blank files: {e}")

            if save_to_firebase and len(self.transcriptions) > 0 and duration > 0:
                try:
                    from services.firebase_service import save_call_log_to_firestore

                    call_data_copy = self.call_data.copy()
                    firebase_success = save_call_log_to_firestore(call_data_copy)
                    if firebase_success:
                        logger.info(f"Call log saved to Firebase: call_id={self.call_id}")
                    else:
                        logger.warning(f"Failed to save call log to Firebase: call_id={self.call_id}")
                except Exception as e:

                    logger.error(f"Error saving call log to Firebase: {e}", exc_info=True)
            elif save_to_firebase:
                logger.info(f"Skipped Firebase save for blank call: call_id={self.call_id}, duration={duration}, transcriptions={len(self.transcriptions)}")

            call_id = self.call_id
            self.call_id = None
            self.call_data = None
            self.transcriptions = []

            return str(filepath)

        except Exception as e:
            logger.error(f"Failed to save call log: {e}", exc_info=True)
            return None

    def _cleanup_orphaned_blank_files(self) -> None:
        """
        Clean up old orphaned blank call files (status "in_progress" older than 1 hour).
        These are from previous runs that didn't complete properly.
        """
        try:

            import re
            uuid_pattern = re.compile(r'^call_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.json$')

            orphaned_count = 0
            for call_file in self.log_dir.glob("call_*.json"):

                if not uuid_pattern.match(call_file.name):
                    continue

                try:

                    with open(call_file, "r", encoding="utf-8") as f:
                        call_data = json.load(f)

                    status = call_data.get("status", "unknown")
                    start_time_str = call_data.get("start_time")

                    if status != "in_progress":
                        continue

                    if start_time_str:
                        start_time = datetime.fromisoformat(start_time_str)
                        age_seconds = (datetime.now() - start_time).total_seconds()

                        if age_seconds > 3600:

                            call_id = call_data.get("call_id")
                            if call_id:

                                completed_pattern = f"call_*_{call_id[:8]}.json"
                                completed_files = list(self.log_dir.glob(completed_pattern))

                                if not completed_files:
                                    call_file.unlink()
                                    orphaned_count += 1
                                    logger.info(f"Cleaned up orphaned blank file: {call_file.name} (age: {age_seconds/3600:.1f} hours)")
                except Exception as e:
                    logger.warning(f"Error checking orphaned file {call_file}: {e}")
                    continue

            if orphaned_count > 0:
                logger.info(f"Cleaned up {orphaned_count} orphaned blank call file(s)")
        except Exception as e:
            logger.error(f"Error during orphaned file cleanup: {e}", exc_info=True)

    def get_conversation_history(self) -> str:
        """
        Get formatted conversation history from transcriptions.

        Returns:
            Formatted conversation string
        """
        if not self.transcriptions:
            return ""

        lines = []
        for trans in self.transcriptions:
            speaker_label = "User" if trans["speaker"] == "user" else "Agent"
            timestamp = datetime.fromisoformat(trans["timestamp"]).strftime("%H:%M:%S")
            lines.append(f"[{timestamp}] {speaker_label}: {trans['text']}")

        return "\n".join(lines)
