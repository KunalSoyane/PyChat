"""
models.py — OOP Layer
Defines the core domain objects: User, Bot, and Memory.
"""

import pyttsx3
import threading
from datetime import datetime


# ╔══════════════════════════════════════════════════════════════════╗
# ║                          Memory                                  ║
# ╚══════════════════════════════════════════════════════════════════╝

class Memory:
    """
    Stores facts the user shares during a conversation.
    e.g. "my name is Kunal"           → memory.store("name", "Kunal")
         "my favourite colour is blue" → memory.store("favourite colour", "blue")
    """

    def __init__(self):
        self._facts: dict[str, dict] = {}

    def store(self, key: str, value: str):
        """Save or overwrite a fact."""
        self._facts[key.lower().strip()] = {
            "value":      value.strip(),
            "learned_at": datetime.now().strftime("%H:%M"),
        }

    def recall(self, key: str) -> str | None:
        """Return the stored value for a key, or None if unknown."""
        entry = self._facts.get(key.lower().strip())
        return entry["value"] if entry else None

    def recall_all(self) -> dict[str, str]:
        return {k: v["value"] for k, v in self._facts.items()}

    def forget(self, key: str):
        self._facts.pop(key.lower().strip(), None)

    def clear(self):
        self._facts.clear()

    def has(self, key: str) -> bool:
        return key.lower().strip() in self._facts

    def size(self) -> int:
        return len(self._facts)

    def __repr__(self) -> str:
        return f"Memory(facts={self.size()}: {list(self._facts.keys())})"


# ╔══════════════════════════════════════════════════════════════════╗
# ║                          User                                    ║
# ╚══════════════════════════════════════════════════════════════════╝

class User:
    """
    Represents the human participant in a chat session.
    Owns a Memory instance for storing shared facts.
    """

    def __init__(self, name: str = "You"):
        self._name            = name.strip() or "You"
        self._messages: list  = []
        self._total_sentiment = 0
        self.memory           = Memory()

    @property
    def name(self) -> str:
        return self._name

    @property
    def messages(self) -> list:
        return list(self._messages)

    @property
    def total_sentiment(self) -> int:
        return self._total_sentiment

    @property
    def mood(self) -> str:
        if self._total_sentiment > 2:
            return "positive"
        elif self._total_sentiment < -2:
            return "negative"
        return "neutral"

    def add_message(self, text: str, sentiment: int = 0) -> dict:
        entry = {
            "sender":    self._name,
            "text":      text,
            "sentiment": sentiment,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._messages.append(entry)
        self._total_sentiment += sentiment
        return entry

    def last_message(self) -> str | None:
        return self._messages[-1]["text"] if self._messages else None

    def clear_history(self):
        self._messages.clear()
        self._total_sentiment = 0
        self.memory.clear()

    def __repr__(self) -> str:
        return (f"User(name={self._name!r}, "
                f"messages={len(self._messages)}, "
                f"mood={self.mood!r}, "
                f"memory={self.memory.size()} facts)")


# ╔══════════════════════════════════════════════════════════════════╗
# ║                           Bot                                    ║
# ╚══════════════════════════════════════════════════════════════════╝

PERSONAS = {
    "friendly":  "Friendly",
    "formal":    "Formal",
    "sarcastic": "Sarcastic",
}

class Bot:
    """
    Represents the chatbot participant.
    Supports persona switching and TTS.
    """

    def __init__(self, name: str = "PyChat", muted: bool = False,
                 persona: str = "friendly"):
        self._name            = name
        self._muted           = muted
        self._persona         = persona if persona in PERSONAS else "friendly"
        self._responses: list = []

        self._engine = pyttsx3.init()
        self._configure_tts()

    def _configure_tts(self):
        voices = self._engine.getProperty("voices")
        preferred = 1 if len(voices) > 1 else 0
        self._engine.setProperty("voice", voices[preferred].id)
        self._engine.setProperty("rate",  165)
        self._engine.setProperty("volume", 0.9)

    @property
    def name(self) -> str:
        return self._name

    @property
    def muted(self) -> bool:
        return self._muted

    @property
    def persona(self) -> str:
        return self._persona

    @property
    def responses(self) -> list:
        return list(self._responses)

    def set_persona(self, persona: str) -> bool:
        """Switch persona. Returns True if valid, False otherwise."""
        if persona.lower() in PERSONAS:
            self._persona = persona.lower()
            return True
        return False

    def available_personas(self) -> list[str]:
        return list(PERSONAS.keys())

    def add_response(self, text: str) -> dict:
        entry = {
            "sender":    self._name,
            "text":      text,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._responses.append(entry)
        return entry

    def speak(self, text: str):
        if self._muted:
            return
        def _run():
            try:
                self._engine.say(text)
                self._engine.runAndWait()
            except RuntimeError:
                pass
        threading.Thread(target=_run, daemon=True).start()

    def toggle_mute(self) -> bool:
        self._muted = not self._muted
        return self._muted

    def last_response(self) -> str | None:
        return self._responses[-1]["text"] if self._responses else None

    def clear_history(self):
        self._responses.clear()

    def __repr__(self) -> str:
        return (f"Bot(name={self._name!r}, "
                f"persona={self._persona!r}, "
                f"responses={len(self._responses)}, "
                f"muted={self._muted})")


# ── Quick self-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    mem = Memory()
    mem.store("name", "Kunal")
    mem.store("favourite colour", "blue")
    print("── Memory ─────────────────────────────────")
    print(f"  name   : {mem.recall('name')}")
    print(f"  colour : {mem.recall('favourite colour')}")
    print(f"  repr   : {mem}")

    user = User("Kunal")
    user.memory.store("name", "Kunal")
    user.add_message("This is great!", sentiment=2)
    print(f"\n── User ───────────────────────────────────")
    print(f"  {user}")

    bot = Bot("PyChat", muted=True, persona="formal")
    print(f"\n── Bot ────────────────────────────────────")
    print(f"  {bot}")
    bot.set_persona("sarcastic")
    print(f"  after switch : {bot.persona}")