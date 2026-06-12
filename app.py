"""
app.py — UI Layer
Handles only the visual interface. All logic lives in ChatSession.
"""

import customtkinter as ctk
from tkinter import filedialog
from datetime import datetime
import threading

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# ── Color Palette ─────────────────────────────────────────────────────────────
COLORS = {
    "bg_primary":   "#0f1117",
    "bg_secondary": "#1a1d27",
    "bg_input":     "#22263a",
    "accent":       "#4f8ef7",
    "accent_hover": "#3a6fd4",
    "text_primary": "#e8eaf2",
    "text_muted":   "#6b7280",
    "text_user":    "#93c5fd",
    "text_bot":     "#a5b4fc",
    "positive":     "#34d399",
    "negative":     "#f87171",
    "border":       "#2e3350",
    "persona_friendly":  "#34d399",
    "persona_formal":    "#a5b4fc",
    "persona_sarcastic": "#fb923c",
}

FONT_TITLE  = ("Consolas", 15, "bold")
FONT_CHAT   = ("Consolas", 13)
FONT_SMALL  = ("Consolas", 11)
FONT_INPUT  = ("Consolas", 13)
FONT_BUTTON = ("Consolas", 12, "bold")

PERSONA_COLORS = {
    "friendly":  "#34d399",
    "formal":    "#a5b4fc",
    "sarcastic": "#fb923c",
}


# ╔══════════════════════════════════════════════════════════════════╗
# ║                    Name Dialog (startup)                         ║
# ╚══════════════════════════════════════════════════════════════════╝

def ask_user_name(root: ctk.CTk) -> str:
    """
    Show a small modal dialog before the main window appears.
    Blocks until the user submits a name.
    Returns the entered name, or "You" if left blank.
    """
    result = {"name": "You"}

    dialog = ctk.CTkToplevel(root)
    dialog.title("Welcome to PyChat")
    dialog.geometry("380x200")
    dialog.resizable(False, False)
    dialog.configure(fg_color=COLORS["bg_secondary"])
    dialog.grab_set()           # modal — blocks the root window
    dialog.focus_force()

    # Centre dialog on screen
    dialog.update_idletasks()
    x = (dialog.winfo_screenwidth()  - 380) // 2
    y = (dialog.winfo_screenheight() - 200) // 2
    dialog.geometry(f"380x200+{x}+{y}")

    ctk.CTkLabel(dialog, text="Welcome to PyChat",
                 font=FONT_TITLE,
                 text_color=COLORS["text_primary"]).pack(pady=(24, 4))

    ctk.CTkLabel(dialog, text="What should I call you?",
                 font=FONT_SMALL,
                 text_color=COLORS["text_muted"]).pack(pady=(0, 12))

    entry = ctk.CTkEntry(dialog,
                         placeholder_text="Enter your name…",
                         font=FONT_INPUT, height=38,
                         fg_color=COLORS["bg_input"],
                         text_color=COLORS["text_primary"],
                         border_color=COLORS["border"],
                         width=280)
    entry.pack(pady=(0, 14))
    entry.focus()

    def submit(*_):
        name = entry.get().strip()
        result["name"] = name if name else "You"
        dialog.destroy()

    entry.bind("<Return>", submit)
    ctk.CTkButton(dialog, text="Start Chatting →",
                  font=FONT_BUTTON, height=36, width=180,
                  fg_color=COLORS["accent"],
                  hover_color=COLORS["accent_hover"],
                  command=submit).pack()

    root.wait_window(dialog)    # block here until dialog closes
    return result["name"]


# ╔══════════════════════════════════════════════════════════════════╗
# ║                     ChatApplication (UI)                         ║
# ╚══════════════════════════════════════════════════════════════════╝

class ChatApplication:
    """
    Pure UI class. Receives a session object and delegates all logic to it.

    Session contract:
        session.handle_input(text)    -> str
        session.score_sentiment(text) -> int
        session.listen()              -> str
        session.export_history()      -> list[str]
        session.shutdown()
        session.user.name             -> str
        session.bot.name              -> str
        session.bot.persona           -> str
    """

    def __init__(self, root: ctk.CTk, session):
        self.root    = root
        self.session = session

        self._build_window()
        self._build_topbar()
        self._build_chat_area()
        self._build_input_bar()
        self._build_statusbar()
        self._register_shutdown()
        self._show_welcome()

    # ── Window ────────────────────────────────────────────────────────────
    def _build_window(self):
        self.root.title("PyChat")
        self.root.geometry("640x740")
        self.root.minsize(480, 520)
        self.root.configure(fg_color=COLORS["bg_primary"])
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

    # ── Top Bar ───────────────────────────────────────────────────────────
    def _build_topbar(self):
        bar = ctk.CTkFrame(self.root, fg_color=COLORS["bg_secondary"],
                           corner_radius=0, height=54,
                           border_width=1, border_color=COLORS["border"])
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(1, weight=1)

        # Mac-style dots
        dot_frame = ctk.CTkFrame(bar, fg_color="transparent")
        dot_frame.grid(row=0, column=0, padx=14)
        for color in ("#ff5f57", "#febc2e", "#28c840"):
            ctk.CTkLabel(dot_frame, text="●", text_color=color,
                         font=("Consolas", 10)).pack(side="left", padx=2)

        # Title + persona badge (two-line layout)
        title_frame = ctk.CTkFrame(bar, fg_color="transparent")
        title_frame.grid(row=0, column=1, sticky="w", padx=6)

        ctk.CTkLabel(title_frame, text="PyChat  //  OOP + Functional",
                     font=FONT_TITLE,
                     text_color=COLORS["text_primary"]).pack(side="left")

        # Persona badge — updates live when persona changes
        self._persona_label = ctk.CTkLabel(
            title_frame,
            text=f"  [ {self.session.bot.persona} ]",
            font=("Consolas", 11),
            text_color=PERSONA_COLORS.get(self.session.bot.persona,
                                          COLORS["text_muted"])
        )
        self._persona_label.pack(side="left", padx=(8, 0))

        # Right-side buttons
        btn_frame = ctk.CTkFrame(bar, fg_color="transparent")
        btn_frame.grid(row=0, column=2, padx=14)

        # Mute toggle button
        self._mute_btn = ctk.CTkButton(
            btn_frame, text="🔊", font=("Consolas", 14),
            width=36, height=30,
            fg_color="transparent",
            border_width=1, border_color=COLORS["border"],
            text_color=COLORS["text_muted"],
            hover_color=COLORS["bg_input"],
            command=self._toggle_mute
        )
        self._mute_btn.pack(side="left", padx=(0, 6))

        # Export button
        ctk.CTkButton(
            btn_frame, text="⬆ Export", font=FONT_BUTTON,
            width=90, height=30,
            fg_color="transparent",
            border_width=1, border_color=COLORS["accent"],
            text_color=COLORS["accent"],
            hover_color=COLORS["bg_input"],
            command=self._export_chat
        ).pack(side="left")

    # ── Chat Area ─────────────────────────────────────────────────────────
    def _build_chat_area(self):
        outer = ctk.CTkFrame(self.root, fg_color=COLORS["bg_primary"],
                             corner_radius=0)
        outer.grid(row=1, column=0, sticky="nsew")
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        self.chat_box = ctk.CTkTextbox(
            outer,
            font=FONT_CHAT,
            fg_color=COLORS["bg_primary"],
            text_color=COLORS["text_primary"],
            border_width=0, corner_radius=0,
            wrap="word", state="disabled",
            padx=18, pady=12,
            scrollbar_button_color=COLORS["bg_input"],
            scrollbar_button_hover_color=COLORS["accent"],
        )
        self.chat_box.grid(row=0, column=0, sticky="nsew", padx=(4, 0))

        self.chat_box.tag_config("user_name",     foreground=COLORS["text_user"])
        self.chat_box.tag_config("bot_name",      foreground=COLORS["text_bot"])
        self.chat_box.tag_config("timestamp",     foreground=COLORS["text_muted"])
        self.chat_box.tag_config("typing",        foreground=COLORS["text_muted"])
        self.chat_box.tag_config("sentiment_pos", foreground=COLORS["positive"])
        self.chat_box.tag_config("sentiment_neg", foreground=COLORS["negative"])
        self.chat_box.tag_config("sentiment_neu", foreground=COLORS["text_muted"])
        self.chat_box.tag_config("system",        foreground=COLORS["text_muted"])
        self.chat_box.tag_config("memory_dump",   foreground="#fbbf24")   # gold for memory

    # ── Input Bar ─────────────────────────────────────────────────────────
    def _build_input_bar(self):
        bar = ctk.CTkFrame(self.root, fg_color=COLORS["bg_secondary"],
                           corner_radius=0, height=68,
                           border_width=1, border_color=COLORS["border"])
        bar.grid(row=2, column=0, sticky="ew")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(0, weight=1)

        inner = ctk.CTkFrame(bar, fg_color="transparent")
        inner.grid(row=0, column=0, padx=14, pady=10, sticky="ew")
        inner.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkEntry(
            inner,
            placeholder_text="Type a message and press Enter…",
            font=FONT_INPUT, height=40,
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text_primary"],
            placeholder_text_color=COLORS["text_muted"],
            border_width=1, border_color=COLORS["border"],
            corner_radius=8,
        )
        self.entry.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        self.entry.bind("<Return>", self._on_send)

        self.voice_btn = ctk.CTkButton(
            inner, text="🎤", font=("Consolas", 16),
            width=42, height=40,
            fg_color=COLORS["bg_input"],
            hover_color=COLORS["bg_primary"],
            border_width=1, border_color=COLORS["border"],
            corner_radius=8,
            command=self._on_voice
        )
        self.voice_btn.grid(row=0, column=1, padx=(0, 8))

        self.send_btn = ctk.CTkButton(
            inner, text="Send →", font=FONT_BUTTON,
            width=88, height=40,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            corner_radius=8, command=self._on_send
        )
        self.send_btn.grid(row=0, column=2)

    # ── Status Bar ────────────────────────────────────────────────────────
    def _build_statusbar(self):
        bar = ctk.CTkFrame(self.root, fg_color=COLORS["bg_primary"],
                           corner_radius=0, height=22)
        bar.grid(row=3, column=0, sticky="ew")
        bar.grid_propagate(False)
        bar.grid_columnconfigure(1, weight=1)

        self.status_label = ctk.CTkLabel(
            bar, text="●  ready",
            font=FONT_SMALL, text_color=COLORS["positive"], anchor="w"
        )
        self.status_label.grid(row=0, column=0, padx=14)

        self.sentiment_label = ctk.CTkLabel(
            bar, text="", font=FONT_SMALL,
            text_color=COLORS["text_muted"], anchor="e"
        )
        self.sentiment_label.grid(row=0, column=2, padx=14)

    # ── Graceful Shutdown ─────────────────────────────────────────────────
    def _register_shutdown(self):
        """Hook window close so we save memory and close DB cleanly."""
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        try:
            self.session.bot._engine.stop()
        except Exception:
            pass
        self.session.shutdown()
        self.root.destroy()

    # ── Welcome Message ───────────────────────────────────────────────────
    def _show_welcome(self):
        user_name = self.session.user.name
        facts     = self.session.user.memory.size()

        self._write("system", f"Session started — welcome back, {user_name}.\n"
                    if facts > 0 else
                    f"Session started — welcome, {user_name}.\n")
        if facts > 0:
            self._write("system",
                        f"Restored {facts} fact(s) from your last session.\n")
        self._write("system", "─" * 52 + "\n\n")

        greeting = (f"Hello again, {user_name}! I remember {facts} things about you."
                    if facts > 0 else
                    f"Hello, {user_name}! I'm PyChat. Ask me anything.")
        self._append_bot_msg(greeting)

    # ── Write Helpers ─────────────────────────────────────────────────────
    def _write(self, tag, text):
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", text, tag)
        self.chat_box.configure(state="disabled")
        self.chat_box.yview("end")

    def _append_user_msg(self, text, sentiment):
        ts = datetime.now().strftime("%H:%M")
        self._write("timestamp", f"[{ts}] ")
        self._write("user_name", f"{self.session.user.name}:  ")
        self._write("", f"{text}\n")
        self._write_sentiment(sentiment)

    def _append_bot_msg(self, text):
        ts = datetime.now().strftime("%H:%M")
        self._write("timestamp", f"[{ts}] ")
        self._write("bot_name", f"{self.session.bot.name}:  ")
        # Memory dump lines get special gold colour
        tag = "memory_dump" if text.startswith("Here's everything") else ""
        self._write(tag, f"{text}\n\n")

    def _write_sentiment(self, score):
        if score > 0:
            label, tag = f"  ↑ positive ({score:+d})\n\n", "sentiment_pos"
        elif score < 0:
            label, tag = f"  ↓ negative ({score:+d})\n\n", "sentiment_neg"
        else:
            label, tag = "  · neutral\n\n", "sentiment_neu"
        self._write(tag, label)
        self.sentiment_label.configure(
            text=f"last sentiment: {score:+d}",
            text_color=COLORS["positive"] if score > 0
                       else COLORS["negative"] if score < 0
                       else COLORS["text_muted"]
        )

    def _show_typing(self):
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"{self.session.bot.name} is typing…\n", "typing")
        self.chat_box.configure(state="disabled")
        self.chat_box.yview("end")

    def _remove_typing(self):
        self.chat_box.configure(state="normal")
        self.chat_box.delete("end-2l", "end-1l")
        self.chat_box.configure(state="disabled")

    # ── Persona Badge Update ──────────────────────────────────────────────
    def _refresh_persona_badge(self):
        """Update the topbar persona label after a persona switch."""
        persona = self.session.bot.persona
        self._persona_label.configure(
            text=f"  [ {persona} ]",
            text_color=PERSONA_COLORS.get(persona, COLORS["text_muted"])
        )

    # ── Event Handlers ────────────────────────────────────────────────────
    def _on_send(self, event=None):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, "end")
        self._set_status("thinking…", COLORS["accent"])
        self._process_message(text)

    def _process_message(self, text):
        sentiment = self.session.score_sentiment(text)
        self._append_user_msg(text, sentiment)
        self._show_typing()

        def worker():
            response = self.session.handle_input(text)
            self.root.after(0, lambda: self._display_response(response))

        threading.Thread(target=worker, daemon=True).start()

    def _display_response(self, response):
        self._remove_typing()
        self._append_bot_msg(response)
        self._refresh_persona_badge()     # update badge in case persona changed
        self._set_status("ready", COLORS["positive"])

    def _on_voice(self):
        self._set_status("listening…", COLORS["accent"])
        self.entry.delete(0, "end")
        self.entry.insert(0, "🎤 listening…")

        def worker():
            text = self.session.listen()
            self.root.after(0, lambda: self._after_voice(text))

        threading.Thread(target=worker, daemon=True).start()

    def _after_voice(self, text):
        self.entry.delete(0, "end")
        if text:
            self.entry.insert(0, text)
            self._on_send()
        else:
            self.entry.insert(0, "Could not hear audio.")
            self._set_status("ready", COLORS["positive"])

    def _toggle_mute(self):
        muted = self.session.bot.toggle_mute()
        self._mute_btn.configure(text="🔇" if muted else "🔊")
        self._set_status("muted" if muted else "unmuted", COLORS["text_muted"])

    def _export_chat(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title="Export Chat History"
        )
        if path:
            lines = self.session.export_history()
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            self._set_status(f"exported → {path.split('/')[-1]}",
                             COLORS["positive"])

    def _set_status(self, msg, color):
        self.status_label.configure(text=f"●  {msg}", text_color=color)


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import customtkinter as ctk
    from chat_session import ChatSession

    root      = ctk.CTk()
    root.withdraw()                  # hide root while name dialog is open
    user_name = ask_user_name(root)
    root.deiconify()                 # show root after name is entered

    session = ChatSession(
        intents_file = "intents.json",
        user_name    = user_name,
        bot_name     = "PyChat",
        muted        = False,
    )
    app = ChatApplication(root, session)
    root.mainloop()