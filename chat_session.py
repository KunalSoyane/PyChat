"""
chat_session.py — Orchestration Layer
Wires together User, Bot, ChatDatabase, and text_utils.
"""

import json
import random
import datetime
import speech_recognition as sr
import wikipedia

from models   import User, Bot
from database import ChatDatabase
import text_utils


class ChatSession:
    """
    Manages one conversation between a User and a Bot.

    OOP concepts:
      Encapsulation  — all state lives inside the instance
      Composition    — HAS-A User, Bot, ChatDatabase
      Single Responsibility — each collaborator does one job

    Public interface used by app.py:
      handle_input(text)    -> str
      score_sentiment(text) -> int
      listen()              -> str
      export_history()      -> list[str]
      user.name, bot.name, bot.persona
    """

    def __init__(self, intents_file="intents.json", user_name="You",
                 bot_name="PyChat", db_path=None, muted=False):

        # ── Core OOP objects ──────────────────────────────────────────────
        self.user = User(user_name)
        self.bot  = Bot(bot_name, muted=muted)
        self.db   = ChatDatabase(db_path) if db_path else ChatDatabase()

        # ── Restore persisted memory from DB (scoped to this user) ───────
        saved_facts = self.db.load_memory(user_name)
        for key, value in saved_facts.items():
            self.user.memory.store(key, value)

        # Always keep the startup name in sync with memory
        self.user.memory.store("name", user_name)
        self.db.save_memory(self.user.memory.recall_all(), user_name)

        # ── Knowledge base ────────────────────────────────────────────────
        self._intents   = self._load_intents(intents_file)
        self._token_map = text_utils.tokenize_patterns(self._intents)

        # ── Speech recognition ────────────────────────────────────────────
        self._recognizer = sr.Recognizer()

        # ── Session metadata ──────────────────────────────────────────────
        self._started_at = datetime.datetime.now()

    # ── Intents loader ────────────────────────────────────────────────────
    @staticmethod
    def _load_intents(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"intents.json not found at '{path}'. "
                "Make sure it lives in the same folder as this script."
            )

    # ╔══════════════════════════════════════════════════════════════╗
    # ║               Public Interface (used by app.py)              ║
    # ╚══════════════════════════════════════════════════════════════╝

    def handle_input(self, text: str) -> str:
        """
        Main entry point.
        If the input contains newlines (pasted multi-line text), split
        into individual lines and process each one, then join responses.
        Otherwise process as a single message.
        """
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if len(lines) > 1:
            responses = []
            for line in lines:
                responses.append(self._process_single(line))
            # Persist the full original text as one DB entry
            sentiment = text_utils.analyze_sentiment(text)
            self.user.add_message(text, sentiment)
            self.db.insert_message(self.user.name, text, sentiment)
            combined = "\n".join(responses)
            self.bot.add_response(combined)
            self.db.insert_message(self.bot.name, combined, 0)
            self.bot.speak(responses[-1])   # speak only the last response
            return combined

        # Single line — process, persist, speak
        response  = self._process_single(text)
        sentiment = text_utils.analyze_sentiment(text)
        self.user.add_message(text, sentiment)
        self.bot.add_response(response)
        self.db.insert_message(self.user.name, text,     sentiment)
        self.db.insert_message(self.bot.name,  response, 0)
        self.bot.speak(response)
        return response

    def _process_single(self, text: str) -> str:
        """
        Process one line/message and return the bot response string.
        Handles: persona switch → memory store/recall → intent routing.
        Applies persona + mood formatting. Does NOT persist to DB
        (handle_input does that so multi-line doesn't double-insert).
        """
        # ── 1. Persona switch ──────────────────────────────────────────────
        persona_request = text_utils.parse_persona_request(text)
        if persona_request:
            response = self._handle_persona_switch(persona_request)

        else:
            # ── 2a. Memory — extract ALL facts from multi-clause input ─────
            clauses      = text_utils.split_into_clauses(text)
            stored_facts = []
            for clause in clauses:
                fact = text_utils.extract_memory(clause)
                if fact:
                    key, value = fact
                    self.user.memory.store(key, value)
                    stored_facts.append((key, value))

            if stored_facts:
                self.db.save_memory(self.user.memory.recall_all(), self.user.name)
                if len(stored_facts) == 1:
                    response = self._handle_memory_store(*stored_facts[0])
                else:
                    summary  = ", ".join(f"{k}: {v}" for k, v in stored_facts)
                    name     = self.user.memory.recall("name")
                    address  = f", {name}" if name else ""
                    response = f"Got it{address}! I've noted all of that — {summary}."

            # ── 2b. Memory — full dump ─────────────────────────────────────
            elif any(phrase in text.lower() for phrase in [
                "what do you know about me",
                "what have you remembered",
                "what do you remember",
                "what have you stored",
                "tell me what you know",
                "what did i tell you",
            ]):
                response = self._handle_full_memory_dump()

            # ── 2c. Memory — recall a single fact ─────────────────────────
            elif (recall_key := text_utils.detect_recall_request(text)):
                response = self._handle_memory_recall(recall_key)

            # ── 3. General knowledge (list/types/explain) ─────────────────
            elif (gq := text_utils.parse_general_query(text)):
                response = self._handle_general_knowledge(gq)

            # ── 4. Math expression ────────────────────────────────────────
            elif text_utils.is_math_expression(text):
                response = self._handle_math(text)

            # ── 4. Normal intent routing ───────────────────────────────────
            else:
                intent   = text_utils.predict_intent(text, self._intents,
                                                     self._token_map)
                response = self._route(intent, text)

        # ── 4. Apply persona + mood formatting ────────────────────────────
        return text_utils.apply_persona(
            text_utils.format_response(response),
            self.bot.persona,
            self.user.mood,
        )

    def score_sentiment(self, text: str) -> int:
        return text_utils.analyze_sentiment(text)

    def listen(self) -> str:
        try:
            with sr.Microphone() as source:
                self._recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self._recognizer.listen(source, timeout=5,
                                                phrase_time_limit=8)
            return self._recognizer.recognize_google(audio)
        except (sr.WaitTimeoutError, sr.UnknownValueError,
                sr.RequestError, OSError):
            return ""

    def export_history(self) -> list[str]:
        facts = self.user.memory.recall_all()
        fact_lines = (
            [f"  {k:<22}: {v}" for k, v in facts.items()]
            if facts else ["  (none)"]
        )
        header = [
            "=" * 56,
            "  PyChat — Session Export",
            f"  User     : {self.user.name}",
            f"  Persona  : {self.bot.persona}",
            f"  Mood     : {self.user.mood} ({self.user.total_sentiment:+d})",
            f"  Started  : {self._started_at.strftime('%Y-%m-%d %H:%M')}",
            f"  Exported : {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"  Duration : {self.duration()}",
            "── Facts remembered " + "─" * 36,
        ] + fact_lines + ["=" * 56, ""]
        return header + self.db.export_as_lines()

    def shutdown(self):
        """Called on window close — saves memory and closes DB cleanly."""
        self.db.save_memory(self.user.memory.recall_all(), self.user.name)
        self.db.close()

    # ╔══════════════════════════════════════════════════════════════╗
    # ║                   Response Routing                           ║
    # ╚══════════════════════════════════════════════════════════════╝

    def _route(self, intent: str, user_text: str) -> str:
        dynamic_handlers = {
            "time":      self._handle_time,
            "wikipedia": self._handle_wikipedia,
            "mood":      self._handle_mood,
            "stats":     self._handle_stats,
        }
        if intent in dynamic_handlers:
            return dynamic_handlers[intent](user_text)
        return self._static_response(intent, user_text)

    # ── Dynamic handlers ──────────────────────────────────────────────────

    def _handle_time(self, _):
        now = datetime.datetime.now()
        return f"The current time is {now.strftime('%I:%M %p')}."

    def _handle_wikipedia(self, user_text):
        query = text_utils.parse_search_query(user_text)
        if not query:
            return "What would you like me to look up?"
        try:
            results = wikipedia.search(query)
            if not results:
                return "I couldn't find anything on that topic."
            for candidate in results[:3]:
                try:
                    # Increased from 2 → 5 sentences so answers aren't cut off mid-explanation
                    summary = wikipedia.summary(candidate, sentences=5,
                                                auto_suggest=False)
                    return f"Here's what I found about {candidate}:\n\n{summary}"
                except (wikipedia.exceptions.PageError,
                        wikipedia.exceptions.DisambiguationError):
                    continue
            return "I found results but couldn't load any pages. Try being more specific."
        except wikipedia.exceptions.DisambiguationError as e:
            opts = ", ".join(e.options[:3])
            return f"That topic is broad. Did you mean: {opts}?"
        except Exception:
            return "I'm having trouble reaching Wikipedia right now."

    def _handle_mood(self, _):
        mood  = self.user.mood
        total = self.user.total_sentiment
        return {
            "positive": f"You seem to be in a good mood! Session score: {total:+d}.",
            "negative": f"You seem a bit down. Session score: {total:+d}. Hope things improve!",
            "neutral":  f"You seem pretty neutral so far. Session score: {total:+d}.",
        }[mood]

    def _handle_stats(self, _):
        stats = self.db.sentiment_stats()
        return (
            f"Session stats — "
            f"messages: {self.db.message_count()}, "
            f"mood: {stats['overall_mood']}, "
            f"positive: {stats['positive_count']}, "
            f"negative: {stats['negative_count']}, "
            f"facts remembered: {self.user.memory.size()}, "
            f"persona: {self.bot.persona}."
        )

    def _handle_math(self, user_text: str) -> str:
        """Evaluate a math expression and return a natural language response."""
        result = text_utils.evaluate_math(user_text)
        if result is None:
            return ("I couldn't parse that as a math expression. "
                    "Try something like '5 + 3', 'add 10 to 5', or '2 power 8'.")
        expr, answer = result
        return f"{expr} = {answer}"

    def _handle_general_knowledge(self, gq: dict) -> str:
        """
        BUG 1 FIX: Handle general knowledge queries (list / types / explain).
        Uses DuckDuckGo scraping first; falls back to Wikipedia summary.

        gq = {"mode": "list"|"types"|"explain"|"normal", "topic": str, "count": int|None}
        """
        mode  = gq.get("mode", "explain")
        topic = gq.get("topic", "")
        count = gq.get("count") or 5

        if not topic:
            return "What topic would you like me to explain?"

        # ── LIST / TYPES mode ──────────────────────────────────────────────
        if mode in (text_utils.QUERY_MODE_LIST, text_utils.QUERY_MODE_TYPES):
            items = text_utils.scrape_list_items(topic, count)
            if items:
                header = (f"Here are {len(items)} types of {topic}:"
                          if mode == text_utils.QUERY_MODE_TYPES
                          else f"Here are {len(items)} uses of {topic}:")
                numbered = "\n".join(f"  {i+1}. {item}" for i, item in enumerate(items))
                return f"{header}\n{numbered}"
            # Fallback to Wikipedia
            return self._handle_wikipedia(f"types of {topic}" if mode == text_utils.QUERY_MODE_TYPES
                                          else f"uses of {topic}")

        # ── EXPLAIN mode ───────────────────────────────────────────────────
        explanation = text_utils.scrape_explanation(topic)
        if explanation:
            return f"Here's what I know about {topic}:\n\n{explanation}"
        # Fallback: Wikipedia with full topic for best match
        return self._handle_wikipedia(topic)

    # ── Memory handlers ───────────────────────────────────────────────────

    def _handle_memory_store(self, key, value):
        name    = self.user.memory.recall("name")
        address = f", {name}" if name and key != "name" else ""
        return random.choice([
            f"Got it{address}! I'll remember that your {key} is {value}.",
            f"Noted{address} — your {key} is {value}.",
            f"I'll keep that in mind{address}. {key.capitalize()}: {value}.",
        ])

    def _handle_memory_recall(self, key):
        value   = self.user.memory.recall(key)
        name    = self.user.memory.recall("name")
        address = f", {name}" if name else ""
        if value:
            return f"You told me your {key} is {value}{address}."
        return (f"I don't know your {key} yet{address}. "
                f"You can tell me by saying 'my {key} is ...'")

    def _handle_full_memory_dump(self):
        """Return everything stored in memory as a formatted response."""
        facts = self.user.memory.recall_all()

        if not facts:
            return ("I don't know anything about you yet! "
                    "Tell me things like 'my name is ...' or 'i live in ...'")

        # Use the login name (self.user.name) not the stored "name" fact
        address = f", {self.user.name}"
        lines   = "\n".join(f"  • {k:<20}: {v}" for k, v in facts.items())
        return f"Here's everything I know about you{address}:\n{lines}"

    # ── Persona handler ───────────────────────────────────────────────────

    def _handle_persona_switch(self, persona):
        success = self.bot.set_persona(persona)
        if success:
            return {
                "friendly":  "Switching to friendly mode! I'll be warm and encouraging.",
                "formal":    "Understood. I shall communicate in a formal and professional manner henceforth.",
                "sarcastic": "Oh great, sarcastic mode. Because that's definitely what everyone wanted.",
            }.get(persona, f"Switched to {persona} mode.")
        return f"I don't have a '{persona}' persona. Try: friendly, formal, or sarcastic."

    # ── Static fallback ───────────────────────────────────────────────────

    def _static_response(self, intent, user_text=""):
        for item in self._intents["intents"]:
            if item["tag"] == intent and item.get("responses"):
                return random.choice(item["responses"])
        words = text_utils.clean_text(user_text)
        if len(words) >= 2:
            return self._handle_wikipedia(user_text)
        return "I'm not sure how to respond to that. Try asking something else!"

    # ── Utilities ─────────────────────────────────────────────────────────

    def duration(self):
        delta   = datetime.datetime.now() - self._started_at
        minutes = int(delta.total_seconds() // 60)
        seconds = int(delta.total_seconds() % 60)
        return f"{minutes}m {seconds}s"

    def __repr__(self):
        return (f"ChatSession(user={self.user.name!r}, bot={self.bot.name!r}, "
                f"messages={self.db.message_count()}, duration={self.duration()})")


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import customtkinter as ctk
    from app import ChatApplication, ask_user_name

    root      = ctk.CTk()
    user_name = ask_user_name(root)
    session   = ChatSession(
        intents_file = "intents.json",
        user_name    = user_name,
        bot_name     = "PyChat",
        muted        = False,
    )
    app = ChatApplication(root, session)
    root.mainloop()