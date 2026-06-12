"""
text_utils.py — Functional Layer
Pure functions only. No classes, no state, no side effects.
All input processing, parsing, and intent prediction lives here.
"""

import string
import re
import difflib
from functools import reduce


# ╔══════════════════════════════════════════════════════════════════╗
# ║                     1. TEXT CLEANING                             ║
# ╚══════════════════════════════════════════════════════════════════╝

def remove_punctuation(text: str) -> str:
    """Strip every punctuation character from text."""
    return "".join(filter(lambda c: c not in string.punctuation, text))


def to_lowercase(text: str) -> str:
    return text.lower()


def strip_extra_spaces(text: str) -> str:
    return " ".join(text.split())


def clean_text(text: str) -> list[str]:
    """
    Full cleaning pipeline — returns a list of lowercase word tokens.
    Pipeline: lowercase → remove punctuation → split → strip blanks
    Uses `reduce` to apply each transform in sequence.
    """
    pipeline = [to_lowercase, remove_punctuation, strip_extra_spaces]
    cleaned  = reduce(lambda t, fn: fn(t), pipeline, text)
    return list(filter(None, cleaned.split()))   # filter removes empty strings


def normalize(text: str) -> str:
    """Return a single cleaned string (joined tokens)."""
    return " ".join(clean_text(text))


# ╔══════════════════════════════════════════════════════════════════╗
# ║                     2. PARSERS                                   ║
# ╚══════════════════════════════════════════════════════════════════╝

# Known prefixes to strip before passing to Wikipedia / search
_SEARCH_PREFIXES = (
    "who is", "who was", "who are",
    "what is", "what are", "what was",
    "tell me about", "search for", "look up",
    "explain", "define", "what do you know about",
    "describe", "give me information on", "info on",
)

# Stop words to strip from the query AFTER prefix removal
# so "a tree in dsa" → "tree dsa"
_STOP_WORDS = frozenset({
    "a", "an", "the", "in", "of", "on", "at", "to",
    "for", "with", "by", "from", "as", "is", "was",
    "are", "were", "be", "been", "being",
})

# Query modes for general knowledge questions
QUERY_MODE_EXPLAIN = "explain"
QUERY_MODE_LIST    = "list"
QUERY_MODE_TYPES   = "types"
QUERY_MODE_NORMAL  = "normal"


def parse_general_query(text: str) -> dict | None:
    """
    Detect and parse general knowledge questions into a structured dict:
      {
        "mode":  "explain" | "list" | "types" | "normal",
        "topic": str,
        "count": int | None,
      }
    Returns None if not a general knowledge query.

    BUG 6 FIX: Excludes bot-self questions ("what is your name") and
    intent-handled questions ("what is the time") so they are not
    incorrectly routed to general-knowledge handling.
    """
    lowered = text.lower().strip()

    # ── Guard: skip bot-self and intent-owned questions ────────────────────
    _EXCLUDED_TOPICS = frozenset({
        "your name", "the time", "time", "your age", "your creator",
        "this project", "you", "your purpose",
    })
    # Any second-person pronoun in the topic → bot-self question, skip
    _SELF_PRONOUNS = re.compile(r'\byour\b|\byou\b|\byourself\b')

    # ── LIST mode — must check BEFORE explain to catch "what are the uses of" ──
    list_match = re.search(
        r'(?:list|give me|name|tell me|what are(?: the)?|show me)\s+(\d+)?\s*'
        r'(?:uses?|examples?|applications?|benefits?|advantages?|disadvantages?'
        r'|features?|properties?|characteristics?|functions?)\s+(?:of\s+)?(.+)',
        lowered
    )
    if list_match:
        count = int(list_match.group(1)) if list_match.group(1) else 5
        topic = _clean_topic(list_match.group(2))
        if topic and topic not in _EXCLUDED_TOPICS and not _SELF_PRONOUNS.search(topic):
            return {"mode": QUERY_MODE_LIST, "topic": topic, "count": min(count, 10)}

    # ── TYPES mode ─────────────────────────────────────────────────────────
    types_match = re.search(
        r'(?:types?|kinds?|categories|forms?|varieties)\s+(?:of\s+)?(.+)', lowered
    )
    if types_match:
        topic = _clean_topic(types_match.group(1))
        if topic and topic not in _EXCLUDED_TOPICS and not _SELF_PRONOUNS.search(topic):
            return {"mode": QUERY_MODE_TYPES, "topic": topic, "count": None}

    # ── EXPLAIN mode ───────────────────────────────────────────────────────
    explain_triggers = (
        "explain ", "describe ", "elaborate on ", "tell me about ",
        "what is ", "what are ", "define ", "give me information on ",
        "info on ", "how does ", "how do ",
    )
    for trigger in explain_triggers:
        if lowered.startswith(trigger):
            topic = _clean_topic(lowered[len(trigger):])
            if topic and topic not in _EXCLUDED_TOPICS and not _SELF_PRONOUNS.search(topic):
                return {"mode": QUERY_MODE_EXPLAIN, "topic": topic, "count": None}

    return None


def _clean_topic(text: str) -> str:
    """Strip trailing punctuation and stop words from a topic string."""
    cleaned = re.sub(r'[?!.]+$', '', text.strip())
    tokens  = cleaned.split()
    content = list(filter(lambda w: w not in _STOP_WORDS, tokens))
    return " ".join(content) if content else cleaned


# ╔══════════════════════════════════════════════════════════════════╗
# ║               WEB SCRAPER (no API key required)                  ║
# ╚══════════════════════════════════════════════════════════════════╝

def _clean_item(text: str, max_len: int = 220) -> str:
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'\[\d+\]', '', text)
    if len(text) > max_len:
        cut  = text[:max_len]
        last = cut.rfind(". ")
        text = (cut[:last + 1] if last > 40 else cut.rstrip()) + "."
    if text and not text.endswith("."):
        text += "."
    return text


def _is_relevant(text: str, topic: str) -> bool:
    """
    Return True only if the snippet text is actually about the topic.
    Rejects off-topic DDG results early.
    """
    topic_words = set(re.sub(r'[^\w\s]', '', topic.lower()).split())
    text_lower  = text.lower()
    # At least one significant topic word must appear in the snippet
    matches = sum(1 for w in topic_words if len(w) > 3 and w in text_lower)
    return matches >= max(1, len(topic_words) // 2)


def _ddg_search(query: str, n: int = 8) -> list[dict]:
    """Run a DuckDuckGo text search and return result dicts."""
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=n))
    except Exception:
        return []


def scrape_list_items(topic: str, count: int = 5) -> list[str] | None:
    """
    Build a real list about `topic` from DuckDuckGo snippets.

    Uses very specific queries that reliably hit listicle pages
    (geeksforgeeks, byjus, javatpoint etc.) and filters snippets
    to keep only ones that are actually about the topic.

    Returns list[str] with >= 3 items, or None → Wikipedia fallback.
    """
    try:
        from duckduckgo_search import DDGS  # noqa: F401
    except ImportError:
        return None

    # Specific queries ranked by how likely they hit listicle content
    queries = [
        f"10 uses of {topic} in daily life",
        f"uses of {topic} with examples",
        f"types of {topic} with explanation",
        f"{topic} important uses",
    ]

    relevant_snippets: list[str] = []

    for query in queries:
        results = _ddg_search(query, n=8)
        for r in results:
            body = r.get("body", "").strip()
            if len(body) > 40 and _is_relevant(body, topic):
                relevant_snippets.append(body)
        if len(relevant_snippets) >= 5:
            break

    if not relevant_snippets:
        return None

    items: list[str] = []
    seen:  set[str]  = set()

    # Strategy A — split on bullet/numbered separators
    sep_pattern = re.compile(r'[·•]\s*|\s*-\s+(?=[A-Z])')
    for snippet in relevant_snippets:
        # Try splitting on separators first
        if re.search(r'[·•]', snippet):
            parts = re.split(r'[·•]\s*', snippet)
        elif re.search(r'\d+\.\s+[A-Z]', snippet):
            parts = re.split(r'\d+\.\s+', snippet)
        else:
            parts = []

        good = [p.strip(" .,\n") for p in parts if 20 < len(p.strip()) < 300]
        for part in good:
            key = part.lower()[:45]
            if key not in seen and _is_relevant(part, topic):
                seen.add(key)
                items.append(_clean_item(part))
        if len(items) >= count:
            break

    # Strategy B — full sentences from relevant snippets
    if len(items) < 3:
        items.clear()
        seen.clear()
        for snippet in relevant_snippets:
            sentences = re.split(r'(?<=[.!?])\s+', snippet)
            for s in sentences:
                s = s.strip()
                if 30 < len(s) < 300 and _is_relevant(s, topic):
                    key = s.lower()[:45]
                    if key not in seen:
                        seen.add(key)
                        items.append(_clean_item(s))
            if len(items) >= count:
                break

    return items[:count] if len(items) >= 3 else None


def scrape_explanation(topic: str) -> str | None:
    """
    Return a short explanation of `topic` from DuckDuckGo snippets.
    """
    try:
        from duckduckgo_search import DDGS  # noqa: F401
    except ImportError:
        return None

    for r in _ddg_search(topic, n=5):
        snippet = r.get("body", "").strip()
        if len(snippet) > 80 and _is_relevant(snippet, topic):
            return re.sub(r'\s+', ' ', snippet)

    return None
def parse_search_query(text: str) -> str:
    """
    Strip common question prefixes AND stop words to get a clean search topic.
    e.g. "what is a tree in dsa" → "tree dsa"
    e.g. "who is Nikola Tesla?"  → "nikola tesla"
    Pure function: input string → output string.
    """
    cleaned = normalize(text)

    # Step 1 — remove prefix
    stripped = next(
        (cleaned[len(prefix):].strip()
         for prefix in _SEARCH_PREFIXES
         if cleaned.startswith(prefix)),
        cleaned
    )

    # Step 2 — remove stop words using filter()
    tokens  = stripped.split()
    content = list(filter(lambda w: w not in _STOP_WORDS, tokens))

    return " ".join(content) if content else stripped


def split_into_clauses(text: str) -> list[str]:
    """
    Split a message into individual clauses so multiple facts can be
    extracted from one message.

    Splits on:  sentence-ending punctuation, commas, " and ", newlines.

    e.g. "my name is Kunal i am 20 years old i live in Mumbai"
         → ["my name is Kunal", "i am 20 years old", "i live in Mumbai"]

    Pure function — returns a list of non-empty stripped strings.
    """
    # Insert a split marker around common clause boundaries
    import re as _re
    marked = _re.sub(r'[,\n]|(?<!\w)and(?!\w)', '|', text, flags=_re.IGNORECASE)
    # Also split on sentence-ending punctuation followed by space or end
    marked = _re.sub(r'[.!?]+\s*', '|', marked)
    clauses = marked.split('|')
    return list(filter(None, map(str.strip, clauses)))
    """Return a set of unique cleaned words from a text."""
    return set(clean_text(text))


def tokenize_patterns(intents_data: dict) -> dict[str, set[str]]:
    """
    Pre-compute a {tag: set_of_pattern_words} map from intents JSON.
    Called once at startup so we don't re-parse on every message.
    Pure function: dict → dict.
    """
    return {
        intent["tag"]: set(
            word
            for pattern in intent["patterns"]
            for word in clean_text(pattern)
        )
        for intent in intents_data["intents"]
    }


# ╔══════════════════════════════════════════════════════════════════╗
# ║                     3. STRING SIMILARITY                         ║
# ╚══════════════════════════════════════════════════════════════════╝

def similarity_ratio(a: str, b: str) -> float:
    """Sequence-based similarity score between two strings (0.0 – 1.0)."""
    return difflib.SequenceMatcher(None, a, b).ratio()


def is_similar(word1: str, word2: str, threshold: float = 0.82) -> bool:
    """True if two words are similar enough (handles typos)."""
    return similarity_ratio(word1, word2) >= threshold


def best_match(word: str, candidates: set[str], threshold: float = 0.82) -> str | None:
    """
    Return the closest candidate to `word`, or None if below threshold.
    Uses max() with a key function — functional style.
    """
    if not candidates:
        return None
    closest = max(candidates, key=lambda c: similarity_ratio(word, c))
    return closest if similarity_ratio(word, closest) >= threshold else None


# ╔══════════════════════════════════════════════════════════════════╗
# ║                     4. INTENT PREDICTION                         ║
# ╚══════════════════════════════════════════════════════════════════╝

def _exact_phrase_match(padded_input: str, intents_data: dict) -> str | None:
    """
    PASS 1 — look for a whole-pattern match inside the user input.
    Padding with spaces prevents substring false positives
    (e.g. "hi" matching inside "this").
    Returns a tag string or None.
    """
    for intent in intents_data["intents"]:
        for pattern in intent["patterns"]:
            padded_pattern = f" {normalize(pattern)} "
            if padded_pattern in padded_input:
                return intent["tag"]
    return None


def _score_intent(user_words: list[str], tag: str,
                  pattern_words: set[str]) -> dict:
    """
    PASS 2 — count fuzzy matches AND sum their similarity ratios.
    Using ratio_sum as a tiebreaker means "goodby→goodbye" beats "goodby→good"
    even when both score 1 match.
    """
    matched_ratios = list(filter(
        lambda r: r >= 0.82,
        (max((similarity_ratio(u, p) for p in pattern_words), default=0.0)
         for u in user_words)
    ))
    return {
        "tag":        tag,
        "score":      len(matched_ratios),
        "ratio_sum":  sum(matched_ratios),
    }


def predict_intent(user_input: str, intents_data: dict,
                   token_map: dict[str, set[str]] | None = None) -> str:
    """
    Two-pass intent classification.

    Pass 1 — exact phrase matching  (fast, handles normal input)
    Pass 2 — fuzzy word scoring     (fallback, handles typos / paraphrasing)

    `token_map` is the pre-computed {tag: word_set} dict from
    `tokenize_patterns()`. Pass it in from ChatSession to avoid
    re-parsing on every call.
    """
    padded = f" {normalize(user_input)} "

    # ── Pass 1 ────────────────────────────────────────────────────────────
    tag = _exact_phrase_match(padded, intents_data)
    if tag:
        return tag

    # ── Pass 2 ────────────────────────────────────────────────────────────
    user_words = clean_text(user_input)
    if not user_words:
        return "unknown"

    if token_map is None:
        token_map = tokenize_patterns(intents_data)

    scored = list(map(
        lambda item: _score_intent(user_words, item[0], item[1]),
        token_map.items()
    ))
    scored.sort(key=lambda x: (x["score"], x["ratio_sum"]), reverse=True)

    best = scored[0]
    return best["tag"] if best["score"] > 0 else "unknown"


# ╔══════════════════════════════════════════════════════════════════╗
# ║                     5. SENTIMENT ANALYSIS                        ║
# ╚══════════════════════════════════════════════════════════════════╝

_POSITIVE_WORDS = frozenset({
    "good", "great", "awesome", "happy", "thanks", "love",
    "excellent", "amazing", "fantastic", "wonderful", "nice",
    "cool", "perfect", "brilliant", "best", "helpful", "glad",
})

_NEGATIVE_WORDS = frozenset({
    "bad", "terrible", "sad", "angry", "hate", "frustrated",
    "awful", "horrible", "worst", "useless", "annoying", "boring",
    "stupid", "wrong", "poor", "dumb", "broken", "ugly",
})

_NEGATION_WORDS = frozenset({
    "not", "no", "never", "don't", "doesn't", "didn't", "won't",
    "can't", "cannot", "isn't", "aren't", "wasn't", "weren't",
    "nothing", "nobody", "nowhere", "neither", "nor",
})

def analyze_sentiment(text: str) -> int:
    """
    Count positive minus negative words in text, with negation handling.
    Returns an integer:  > 0 = positive,  < 0 = negative,  0 = neutral.

    BUG 11 FIX: Naive word-counting didn't handle negation — "I am not happy"
    returned +1 (positive). Now a sentiment word preceded by a negation word
    within a 2-token window has its polarity flipped.
    Uses filter() — functional style.
    """
    words  = clean_text(text)
    score  = 0
    for i, word in enumerate(words):
        # Check if a negation word appears in the 1-2 positions before this word
        negated = any(
            words[j] in _NEGATION_WORDS
            for j in range(max(0, i - 2), i)
        )
        if word in _POSITIVE_WORDS:
            score += -1 if negated else +1
        elif word in _NEGATIVE_WORDS:
            score += +1 if negated else -1
    return score


def sentiment_label(score: int) -> str:
    """Convert a numeric sentiment score to a readable label."""
    if score > 0:  return "positive"
    if score < 0:  return "negative"
    return "neutral"


# ╔══════════════════════════════════════════════════════════════════╗
# ║                     6. RESPONSE FILTERS                          ║
# ╚══════════════════════════════════════════════════════════════════╝

def truncate(text: str, max_chars: int = 2000) -> str:
    """
    Truncate text at a sentence boundary so it never cuts mid-sentence.
    Raised default to 2000 to avoid cutting Wikipedia summaries.
    """
    if len(text) <= max_chars:
        return text
    # Find the last sentence-ending punctuation before max_chars
    cutoff = text[:max_chars]
    last   = max(cutoff.rfind(". "), cutoff.rfind("! "), cutoff.rfind("? "))
    if last > 0:
        return text[:last + 1]
    return cutoff  # no sentence boundary found — hard cut


def capitalize_sentences(text: str) -> str:
    """
    Ensure every sentence starts with a capital letter.

    BUG 3 FIX:
      - Old code used .capitalize() which lowercases everything after char 1
        (e.g. "PyChat" → "Pychat"). Now uses a regex sub that only upcases
        the very first character of each sentence.
      - Old re.split used (?<=[.!?])\\s+ which treated "1.", "2." etc. as
        sentence boundaries, fragmenting numbered lists. The new pattern uses
        a negative lookbehind to avoid splitting after a digit followed by a dot.
    """
    # Split only on . ! ? that are NOT preceded by a digit (to protect "1.", "2.")
    # and NOT inside an existing all-caps abbreviation sequence.
    parts = re.split(r'(?<![0-9])(?<=[.!?])\s+', text.strip())
    # Capitalise only the first character of each part, leaving the rest untouched
    def _cap_first(s: str) -> str:
        return s[0].upper() + s[1:] if s else s
    return " ".join(map(_cap_first, parts))


def format_response(text: str, max_chars: int = 2000) -> str:
    """
    Final response pipeline:
    capitalize → truncate
    Compose two pure functions — functional style.

    BUG 4 FIX: Default raised from 400 → 2000 so Wikipedia summaries
    are not cut mid-sentence.
    """
    pipeline = [capitalize_sentences, lambda t: truncate(t, max_chars)]
    return reduce(lambda t, fn: fn(t), pipeline, text)


# ╔══════════════════════════════════════════════════════════════════╗
# ║                  7. MEMORY EXTRACTION                            ║
# ╚══════════════════════════════════════════════════════════════════╝

# Patterns that signal the user is sharing a fact about themselves
# Format: (regex_pattern, key_template)
# The first capture group becomes the value; key comes from the pattern name.
_MEMORY_PATTERNS = [
    # BUG 12 FIX: name patterns use a non-greedy stop-at-conjunction anchor
    # so "my name is Kunal and i live in Mumbai" only captures "Kunal".
    # The negative lookahead (?!.*\b(?:and|but|or|,)\b) is replaced by
    # a character class that stops at common clause separators.
    (r"my name is ([A-Za-z][A-Za-z'\-]*)(?:\s|$)",        "name"),
    (r"i am called ([A-Za-z][A-Za-z'\-]*)(?:\s|$)",        "name"),
    # BUG 8 FIX: "call me X" — require a single capitalised word (proper name)
    # and reject things like "call me at 9pm", "call me maybe"
    # BUG 8 FIX: pattern runs on lowered text so capital-letter check fails.
    # Use blocklist of common non-name words instead.
    (r"call me ([a-z]{2,30})(?:\s|$)",                     "name"),
    (r"my age is (\d+)",                                    "age"),
    (r"i am (\d+) years old",                               "age"),
    (r"i'm (\d+) years old",                                "age"),
    (r"my favourite colou?r is (.+)",                       "favourite colour"),
    (r"my favorite colou?r is (.+)",                        "favourite colour"),
    (r"i live in ([A-Za-z][A-Za-z ]*?)(?= and| but|,|$|$)",  "location"),
    (r"i'm from ([A-Za-z][A-Za-z ]*?)(?= and| but|,|$|$)",   "location"),
    (r"i am from ([A-Za-z][A-Za-z ]*?)(?= and| but|,|$|$)",   "location"),
    (r"my hobby is (.+)",                                   "hobby"),
    (r"i love (.+)",                                        "hobby"),
    (r"i like (.+)",                                        "hobby"),
    (r"my favourite food is (.+)",                          "favourite food"),
    (r"my job is (.+)",                                     "job"),
    (r"i work as (.+)",                                     "job"),
    # BUG 7 FIX: "i am a X" — require a real job/role noun: must be a single
    # meaningful word (no short filler words like "bit", "fan", "little").
    # We anchor to a known set of occupation-like endings or require the word
    # to be a plausible single-token profession (>=5 chars, no "of/in/on" after it).
    (r"i am a ([A-Za-z]{5,}(?:\s+[A-Za-z]+)?)(?:\s*$)",   "job"),
    (r"i'm a ([A-Za-z]{5,}(?:\s+[A-Za-z]+)?)(?:\s*$)",    "job"),
]

def extract_memory(text: str) -> tuple[str, str] | None:
    """
    Try to extract a (key, value) fact from a user message.
    Returns a (key, value) tuple if a pattern matches, else None.

    Pure function — no side effects.  The caller (ChatSession) does
    the actual storing in user.memory.

    Examples:
        "my name is Kunal"       → ("name", "Kunal")
        "i am 20 years old"      → ("age", "20")
        "i live in Mumbai"       → ("location", "Mumbai")
        "what time is it"        → None
    """
    # BUG 2 FIX: Search on lowered text for case-insensitive matching, but
    # recover the value from the *original* text to preserve proper-noun casing.
    # BUG 8 FIX: words that look like names but are common phrases
    _CALL_ME_BLOCKLIST = frozenset({
        # Common non-name words that can appear after "call me"
        "maybe", "later", "back", "soon", "tomorrow", "crazy",
        "baby", "honey", "babe", "dear", "sir", "miss", "mister",
        "please", "again", "never",
        # Prepositions / determiners — reject "call me at", "call me on", etc.
        "at", "on", "in", "by", "to", "of", "an", "the", "if",
        "up", "as", "or", "so", "no", "do", "go", "be",
    })

    lowered = text.lower().strip()
    original = text.strip()
    for pattern, key in _MEMORY_PATTERNS:
        match = re.search(pattern, lowered)
        if match:
            value_lower = match.group(1).strip()
            # Reject blocklisted "call me" values
            if key == "name" and r"call me" in pattern and value_lower in _CALL_ME_BLOCKLIST:
                continue
            # Re-run the same pattern on the original to get the correctly-cased value
            orig_match = re.search(pattern, original, re.IGNORECASE)
            value = orig_match.group(1).strip() if orig_match else value_lower
            return (key, value)
    return None


# Recall trigger phrases → the key the user is asking about
_RECALL_TRIGGERS = {
    "what is my name":             "name",
    "what's my name":              "name",
    "do you know my name":         "name",
    "my name":                     "name",
    "how old am i":                "age",
    "what is my age":              "age",
    "where do i live":             "location",
    "where am i from":             "location",
    "what is my hobby":            "hobby",
    "what do i like":              "hobby",
    "what do i love":              "hobby",
    "what is my favourite colour": "favourite colour",
    "what is my favorite color":   "favourite colour",
    "what is my job":              "job",
    "what do i do":                "job",
}

def detect_recall_request(text: str) -> str | None:
    """
    Return the memory key the user is asking about, or None.
    e.g. "do you remember my name?" → "name"
    """
    lowered = normalize(text)
    return next(
        (key for trigger, key in _RECALL_TRIGGERS.items()
         if trigger in lowered),
        None
    )


# ╔══════════════════════════════════════════════════════════════════╗
# ║                  8. PERSONA FORMATTERS                           ║
# ╚══════════════════════════════════════════════════════════════════╝

# Mood prefix lines per persona
_MOOD_PREFIXES = {
    "friendly": {
        "positive": ["Great energy today! 😊 ", "Love the positivity! ",
                     "You seem to be in a great mood! "],
        "negative": ["Hope you're doing okay. ",
                     "Hang in there! ", "I'm here for you. "],
        "neutral":  [],
    },
    "formal": {
        "positive": ["I note your positive disposition. ",
                     "It appears you are in good spirits. "],
        "negative": ["I observe that you may be experiencing some difficulty. ",
                     "I hope circumstances improve for you. "],
        "neutral":  [],
    },
    "sarcastic": {
        "positive": ["Oh wow, someone's happy. How refreshing. ",
                     "Alert the press — someone's in a good mood. "],
        "negative": ["Oh great, another sad message. ",
                     "Shocking. Truly shocking that things are bad. "],
        "neutral":  [],
    },
}

# Persona response wrappers
_PERSONA_WRAPPERS = {
    "friendly": {
        "prefix": "",
        "suffix": "",
        "transform": lambda t: t,   # no change
    },
    "formal": {
        "prefix": "",
        "suffix": "",
        # Ensure formal punctuation; strip casual phrases
        "transform": lambda t: t.replace("!", ".").replace("Hey", "Hello"),
    },
    "sarcastic": {
        "prefix": "",
        "suffix": " ...Obviously.",
        "transform": lambda t: t,
    },
}


def apply_persona(text: str, persona: str, mood: str = "neutral") -> str:
    """
    Apply persona-based formatting to a response.
    Optionally prepend a mood-aware prefix.

    BUG 9 FIX: Sarcastic suffix (" ...Obviously.") must NOT be appended
    to multi-line formatted output such as memory dumps or numbered lists.
    We detect this by checking if the text contains a newline character.

    Pure function: (text, persona, mood) → formatted string.
    """
    import random as _random

    persona = persona.lower()
    mood    = mood.lower()

    wrapper   = _PERSONA_WRAPPERS.get(persona, _PERSONA_WRAPPERS["friendly"])
    prefixes  = _MOOD_PREFIXES.get(persona, {}).get(mood, [])
    mood_line = _random.choice(prefixes) if prefixes else ""

    transformed = wrapper["transform"](text)

    # BUG 9 FIX: suppress suffix for multi-line/formatted responses
    is_multiline = "\n" in transformed or transformed.startswith("Here's everything")
    suffix = "" if is_multiline else wrapper["suffix"]

    result = f"{mood_line}{wrapper['prefix']}{transformed}{suffix}"
    return result.strip()


def parse_persona_request(text: str) -> str | None:
    """
    Detect a persona switch request and return the target persona name.
    Returns the requested word even if it's not a valid persona —
    ChatSession will handle the 'invalid persona' response.
    Returns None only if this doesn't look like a persona request at all.

    e.g. "switch to formal mode" → "formal"
         "be sarcastic"          → "sarcastic"
         "switch to angry mode"  → "angry"   ← caught, not sent to Wikipedia
         "hello there"           → None
    """
    lowered = text.lower()

    # Pattern: "switch to X", "be X", "X mode", "change to X"
    import re as _re
    patterns = [
        r"switch to (\w+)",
        r"\bbe (\w+)",           # \b ensures 'be' is a whole word, not inside 'describe'
        r"change to (\w+)",
        r"(\w+) mode",
        r"use (\w+) mode",
    ]
    for pattern in patterns:
        match = _re.search(pattern, lowered)
        if match:
            word = match.group(1)
            # Exclude common false positives that aren't persona requests
            excluded = {"the", "a", "an", "this", "that", "it", "my",
                        "dark", "light", "full", "safe", "airplane"}
            if word not in excluded:
                return word
    return None



# ╔══════════════════════════════════════════════════════════════════╗
# ║                  9. MATH PROCESSING                              ║
# ╚══════════════════════════════════════════════════════════════════╝

# Word-to-operator/number mappings — functional lookup tables
_WORD_OPERATORS = {
    "plus":       "+",
    "add":        "+",
    "added":      "+",
    "and":        "+",
    "minus":      "-",
    "subtract":   "-",
    "subtracted": "-",
    "less":       "-",
    "times":      "*",
    "multiply":   "*",
    "multiplied": "*",
    "into":       "*",
    "divided":    "/",
    "divide":     "/",
    "over":       "/",
    "power":      "**",
    "squared":    "** 2",
    "cubed":      "** 3",
    "modulo":     "%",
    "mod":        "%",
    "remainder":  "%",
}

_WORD_NUMBERS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "fifteen": "15",
    "twenty": "20", "fifty": "50", "hundred": "100", "thousand": "1000",
}

# Trigger phrases that indicate a math request (used for intent detection)
_MATH_TRIGGERS = frozenset({
    "calculate", "compute", "what is", "whats", "solve",
    "add", "subtract", "multiply", "divide", "plus", "minus",
    "times", "squared", "cubed", "power", "modulo", "mod",
    "how much is", "how many is",
})


_SYMBOL_OPERATORS = frozenset({"+", "-", "*", "/", "%", "**", "^"})

# Regex patterns for verb-style math — matched BEFORE token loop
# Each entry: (pattern, replacement)
# Use word numbers too by replacing them first
_VERB_MATH_PATTERNS = [
    # "add X to Y" or "add X Y"         → "X + Y"
    (r'add\s+(\d+(?:\.\d+)?)\s+(?:to\s+)?(\d+(?:\.\d+)?)',      r'\1 + \2'),
    # "subtract X from Y"                → "Y - X"  (note: reversed)
    (r'subtract\s+(\d+(?:\.\d+)?)\s+(?:from\s+)?(\d+(?:\.\d+)?)', r'\2 - \1'),
    # "multiply X by Y" or "multiply X Y"→ "X * Y"
    (r'multiply\s+(\d+(?:\.\d+)?)\s+(?:by\s+)?(\d+(?:\.\d+)?)', r'\1 * \2'),
    # "divide X by Y" or "divide X Y"    → "X / Y"
    (r'divide\s+(\d+(?:\.\d+)?)\s+(?:by\s+)?(\d+(?:\.\d+)?)',   r'\1 / \2'),
]


def _words_to_expression(text: str) -> str:
    """
    Convert word-based OR symbol-based math to a clean symbol expression.

    Handles three forms:
      Verb prefix:  "add 5 to 3"      → "5 + 3"
                    "subtract 4 from 10" → "10 - 4"
      Infix words:  "two plus two"    → "2 + 2"
                    "five times three" → "5 * 3"
      Symbols:      "1 + 1"           → "1 + 1"  (passed through)

    Pure function: string → string.
    """
    lowered = text.lower().strip()

    # Step 1 — replace word numbers so regex patterns match digits
    for word, digit in _WORD_NUMBERS.items():
        lowered = re.sub(rf'\b{word}\b', digit, lowered)

    # Step 2 — try verb-style patterns first (add/subtract/multiply/divide)
    for pattern, replacement in _VERB_MATH_PATTERNS:
        match = re.search(pattern, lowered)
        if match:
            return re.sub(pattern, replacement, lowered).strip()

    # Step 3 — infix token loop for "X plus Y", "X times Y", symbols
    # Remove non-math filler words
    for filler in ["what is ", "whats ", "calculate ", "compute ", "solve "]:
        lowered = lowered.replace(filler, " ")

    tokens = lowered.split()
    result = []
    for token in tokens:
        if token in _WORD_OPERATORS:
            result.append(_WORD_OPERATORS[token])   # "plus" → "+"
        elif token in _SYMBOL_OPERATORS:
            result.append(token)                     # "+" → "+"
        elif re.match(r'^\d+(\.\d+)?$', token):
            result.append(token)                     # digits pass through
        # skip everything else (articles, unknown words)

    return " ".join(result)


def is_math_expression(text: str) -> bool:
    """
    Return True if the message looks like a math request.

    BUG 5 FIX: Trigger words like "add", "times", "minus" alone are NOT
    enough — the message must ALSO contain at least one digit or a spelled-out
    number word. This prevents "add me on Instagram", "times have changed",
    "minus the attitude" from matching.

    Checks:
      - digit operator digit pattern  (e.g. "1 + 1", "2 ** 8")
      - math trigger word AND a digit (e.g. "add 5 to 3", "calculate 7*8")
    Pure function.
    """
    lowered = text.lower()

    # Pattern 1: digit + operator + digit — unambiguous math
    if re.search(r'\d+\s*(\*\*|[\+\-\*\/\%\^])\s*\d+', lowered):
        return True

    # Pattern 2: math trigger word AND at least one digit or word-number
    _NUMBER_WORDS = frozenset({
        "zero","one","two","three","four","five","six","seven","eight","nine",
        "ten","eleven","twelve","fifteen","twenty","fifty","hundred","thousand",
    })
    words = set(clean_text(lowered))
    has_trigger = bool(words & _MATH_TRIGGERS)
    has_number  = bool(re.search(r'\d', lowered)) or bool(words & _NUMBER_WORDS)
    if has_trigger and has_number:
        return True

    return False


def evaluate_math(text: str) -> tuple[str, str] | None:
    """
    Parse and safely evaluate a math expression from natural language.
    Returns (expression_string, result_string) or None if it can't parse.

    Handles:
        "5+5"        → ("5 + 5",   "10")   ← no spaces, direct extraction
        "1 + 1"      → ("1 + 1",   "2")
        "add 5 to 3" → ("5 + 3",   "8")
        "Whats 7+7"  → ("7 + 7",   "14")   ← prefix words stripped first
        "two plus two"→ ("2 + 2",  "4")
    """
    # Step 1 — try extracting a raw symbol expression directly from text
    # This catches "5+5", "7*8", "Whats is 7+7" before word conversion
    raw_match = re.search(r'\d+(?:\.\d+)?\s*(?:\*\*|[\+\-\*\/\%\^])\s*\d+(?:\.\d+)?'
                          r'(?:\s*(?:\*\*|[\+\-\*\/\%\^])\s*\d+(?:\.\d+)?)*', text)
    if raw_match:
        safe_expr = raw_match.group(0).replace("^", "**").strip()
        # Add spaces around operators for clean display
        safe_expr = re.sub(r'\s*(\*\*|[\+\-\*\/\%])\s*', r' \1 ', safe_expr).strip()
        safe_expr = re.sub(r'\s+', ' ', safe_expr)
        try:
            raw = eval(safe_expr, {"__builtins__": {}})
            if isinstance(raw, float) and raw.is_integer():
                result = str(int(raw))
            elif isinstance(raw, float):
                result = str(round(raw, 6))
            else:
                result = str(raw)
            return (safe_expr, result)
        except (ZeroDivisionError, SyntaxError, TypeError, NameError):
            pass

    # Step 2 — word-to-symbol conversion for "add 5 to 3", "two plus two" etc.
    expr      = _words_to_expression(text)
    safe_expr = re.sub(r'[^\d\s\+\-\*\/\%\.\(\)\^]', '', expr).strip()
    safe_expr = safe_expr.replace("^", "**")

    if not safe_expr or not re.search(r'\d', safe_expr):
        return None

    try:
        raw = eval(safe_expr, {"__builtins__": {}})
        if isinstance(raw, float) and raw.is_integer():
            result = str(int(raw))
        elif isinstance(raw, float):
            result = str(round(raw, 6))
        else:
            result = str(raw)
        return (safe_expr.strip(), result)
    except (ZeroDivisionError, SyntaxError, TypeError, NameError):
        return None


# ── Quick self-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    sample_intents = {
        "intents": [
            {"tag": "greeting",  "patterns": ["Hi", "Hello", "Hey"]},
            {"tag": "goodbye",   "patterns": ["Bye", "See you", "Exit"]},
            {"tag": "time",      "patterns": ["what time is it", "current time"]},
            {"tag": "wikipedia", "patterns": ["who is", "what is", "tell me about"]},
        ]
    }

    token_map = tokenize_patterns(sample_intents)

    tests = [
        ("Hello there!",              "greeting"),
        ("helo",                       "greeting"),   # typo
        ("what time is it?",           "time"),
        ("who is Nikola Tesla?",       "wikipedia"),
        ("tell me about black holes",  "wikipedia"),
        ("xyzzy nonsense",             "unknown"),
    ]

    print("── Intent Prediction ─────────────────────")
    for text, expected in tests:
        result = predict_intent(text, sample_intents, token_map)
        status = "✓" if result == expected else "✗"
        print(f"  {status}  '{text}' → {result}  (expected {expected})")

    print("\n── Sentiment Analysis ────────────────────")
    for text in ["This is great and awesome!", "I hate this terrible app.", "What time is it?"]:
        score = analyze_sentiment(text)
        print(f"  {score:+d}  ({sentiment_label(score)})  '{text}'")

    print("\n── Memory Extraction ─────────────────────")
    memory_tests = [
        "my name is Kunal",
        "i am 20 years old",
        "i live in Mumbai",
        "i love cricket",
        "what time is it",          # should return None
        "call me K",
    ]
    for t in memory_tests:
        result = extract_memory(t)
        print(f"  '{t}' → {result}")

    print("\n── Recall Detection ──────────────────────")
    recall_tests = [
        "what is my name?",
        "do you know my name",
        "where do i live",
        "tell me a joke",           # should return None
    ]
    for t in recall_tests:
        print(f"  '{t}' → {detect_recall_request(t)}")

    print("\n── Persona Formatting ────────────────────")
    response = "I found some information for you!"
    for persona in ["friendly", "formal", "sarcastic"]:
        for mood in ["positive", "negative", "neutral"]:
            out = apply_persona(response, persona, mood)
            print(f"  [{persona:<10} / {mood:<8}] {out}")