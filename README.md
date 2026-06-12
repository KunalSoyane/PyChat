# PyChat 🤖

> A feature-rich Python desktop chatbot demonstrating **Object-Oriented** and **Functional Programming** paradigms — built with a clean 4-layer architecture.

---

## ✨ Features

| Feature | Description |
|---|---|
| 🗣️ **Intent Recognition** | Keyword + fuzzy-token matching across 15 built-in intents |
| 🧠 **Persistent Memory** | Learns and recalls facts about you across sessions (SQLite-backed) |
| 🔍 **Wikipedia Search** | Auto-fetches article summaries for knowledge questions |
| 🌐 **Web Scraping** | DuckDuckGo-powered answers for "list/types of" queries |
| 🧮 **Math Evaluator** | Solves symbol expressions and natural language maths ("add 5 to 3") |
| 😊 **Sentiment Tracking** | Scores every message and tracks your mood across the session |
| 🎭 **Persona Switching** | Three bot personalities — Friendly, Formal, Sarcastic |
| 🎤 **Voice Input** | Speak your message via microphone using SpeechRecognition |
| 🔊 **Text-to-Speech** | Bot reads its responses aloud via pyttsx3 |
| 📊 **Session Stats** | Live message count, sentiment breakdown, and mood summary |
| 💾 **Chat Export** | Save full conversation history to a `.txt` file |
| 🌙 **Dark Mode UI** | Polished CustomTkinter interface with Mac-style title bar |

---

## 🏗️ Architecture

PyChat is split into **four clean layers**, each with a single responsibility:

```
┌────────────────────────────────────────────────────┐
│  app.py            — UI Layer                      │
│  (CustomTkinter GUI, event handlers, display)      │
├────────────────────────────────────────────────────┤
│  chat_session.py   — Orchestration Layer           │
│  (wires User, Bot, DB, text_utils together)        │
├────────────────────────────────────────────────────┤
│  models.py         — OOP Domain Layer              │
│  (User, Bot, Memory — encapsulation & composition) │
├────────────────────────────────────────────────────┤
│  text_utils.py     — Functional Layer              │
│  (pure functions: clean, parse, predict, evaluate) │
├────────────────────────────────────────────────────┤
│  database.py       — Persistence Layer             │
│  (SQLite: messages + per-user memory facts)        │
└────────────────────────────────────────────────────┘
```

---

## 📂 Project Structure

```
PyChat/
├── app.py              # UI — ChatApplication class, startup name dialog
├── chat_session.py     # Orchestrator — ChatSession, intent routing
├── models.py           # OOP models — User, Bot, Memory
├── text_utils.py       # Functional utils — all pure functions
├── database.py         # SQLite persistence — ChatDatabase
├── intents.json        # Knowledge base — patterns and responses
├── chat_history.db     # Auto-created SQLite database (gitignore this)
└── README.md
```

---

## 🧩 Programming Paradigms

### Object-Oriented Programming (OOP)

| Concept | Where used |
|---|---|
| **Classes & Objects** | `User`, `Bot`, `Memory`, `ChatDatabase`, `ChatSession`, `ChatApplication` |
| **Encapsulation** | Private attributes (`_name`, `_facts`, `_conn`) with property accessors |
| **Composition** | `ChatSession` has-a `User`, `Bot`, and `ChatDatabase` |
| **Single Responsibility** | Each class does exactly one job |
| **Abstraction** | `app.py` talks to `ChatSession` through a clean public interface only |

### Functional Programming (FP)

All of `text_utils.py` is written as **pure functions** with no shared state or side effects.

| Concept | Where used |
|---|---|
| **Pure functions** | Every function in `text_utils.py` — same input always gives same output |
| **`reduce`** | `clean_text()` applies a transform pipeline: lowercase → strip punctuation → split |
| **`filter`** | Removes empty tokens, stop words, irrelevant DDG snippets |
| **`map`** | `export_as_lines()` in `database.py` formats rows with `map + lambda` |
| **Lambda functions** | Used throughout for inline transformations |
| **Higher-order functions** | Functions that accept or return other functions (e.g. pipeline pattern) |

---

## 🛠️ Tech Stack

| Library | Purpose |
|---|---|
| `customtkinter` | Modern dark-mode desktop GUI |
| `sqlite3` | Built-in persistent storage (messages + memory) |
| `pyttsx3` | Offline text-to-speech |
| `SpeechRecognition` | Microphone voice input |
| `wikipedia` | Article summaries for knowledge queries |
| `duckduckgo_search` | Web scraping for list/types queries |
| `difflib` | Fuzzy intent matching (typo tolerance) |
| `re` | Regex-based parsing throughout `text_utils.py` |

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10 or higher
- A working microphone (optional, for voice input)

### 1. Clone the repository

```bash
git clone https://github.com/your-username/pychat.git
cd pychat
```

### 2. Install dependencies

```bash
pip install customtkinter pyttsx3 SpeechRecognition wikipedia duckduckgo-search
```

> On some systems you may also need:
> ```bash
> pip install pyaudio        # for microphone support (Windows/Linux)
> brew install portaudio     # macOS prerequisite for pyaudio
> ```

### 3. Run the app

```bash
python app.py
```

A startup dialog will ask for your name, then the main chat window opens. Your name and any facts you share are remembered the next time you run the app.

---

## 💬 Usage Examples

Once the app is running, try typing any of the following:

```
Hello / Hey / Good morning          → greeting response
What time is it?                    → current time
Who is Alan Turing?                 → Wikipedia summary
What is machine learning?           → DuckDuckGo / Wikipedia explanation
Types of sorting algorithms         → numbered list from the web
5 + 3 / add 10 to 5 / two plus two → math evaluator
My name is Kunal                    → stores the fact in memory
How old am I?                       → recalls stored age
What do you know about me?          → dumps all remembered facts
How am I feeling?                   → sentiment mood report
Show stats                          → full session statistics
Switch to formal / be sarcastic     → changes bot persona
Tell me a joke                      → random programming joke
Bye / Exit                          → goodbye response
```

---

## 🎭 Bot Personas

| Persona | Style |
|---|---|
| **Friendly** (default) | Warm, encouraging, uses emoji occasionally |
| **Formal** | Professional language, no contractions |
| **Sarcastic** | Dry humour, witty remarks |

Switch at any time by saying `"switch to formal"`, `"be sarcastic"`, etc.

---

## 🗄️ Database Schema

The SQLite database (`chat_history.db`) contains two tables:

```sql
-- Full conversation log
CREATE TABLE messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT,
    sender          TEXT,
    message         TEXT,
    sentiment_score INTEGER
);

-- Per-user persistent memory facts
CREATE TABLE memory (
    user        TEXT,
    key         TEXT,
    value       TEXT,
    learned_at  TEXT,
    PRIMARY KEY (user, key)
);
```

---

## 📄 Module Reference

### `app.py` — UI Layer
- `ask_user_name(root)` — Modal startup dialog
- `ChatApplication` — Full UI; delegates all logic to `ChatSession`

### `chat_session.py` — Orchestration Layer
- `ChatSession` — Wires User + Bot + DB + text_utils
- `handle_input(text)` — Main entry point for every message
- `listen()` — Captures voice via microphone
- `export_history()` — Returns chat lines for file export

### `models.py` — OOP Layer
- `Memory` — Key-value fact store with timestamps
- `User` — Human participant; owns a `Memory`, tracks sentiment
- `Bot` — Chatbot participant; manages persona, TTS, response log

### `text_utils.py` — Functional Layer
- `clean_text()` — Tokenization pipeline using `reduce`
- `predict_intent()` — Token overlap + fuzzy matching
- `analyze_sentiment()` — Weighted positive/negative word scoring
- `extract_memory()` — Regex extraction of "my X is Y" facts
- `evaluate_math()` — Natural language and symbol math evaluation
- `apply_persona()` — Formats responses based on active persona and user mood
- `scrape_list_items()` — DuckDuckGo-powered list generation

### `database.py` — Persistence Layer
- `ChatDatabase` — SQLite wrapper with context manager support
- `insert_message()`, `fetch_all()`, `fetch_recent()`
- `save_memory()`, `load_memory()`, `clear_memory()`
- `sentiment_stats()` — Aggregate mood analytics

---

## 🤝 Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

---

## 📝 License

This project was built as a college assignment to demonstrate OOP and Functional Programming in Python.
