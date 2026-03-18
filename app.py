import json
import os
import re
import time
import threading
import imaplib
import email
import email.message
from email.header import decode_header
from datetime import datetime
from email.utils import parsedate_to_datetime

import tkinter as tk
from tkinter import ttk, messagebox

# Beep Windows
try:
    import winsound
    HAS_WINSOUND = True
except Exception:
    HAS_WINSOUND = False

# Logo (Pillow opzionale)
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except Exception:
    HAS_PIL = False


# -------------------------
# Regex eventi
# -------------------------
TAKEOFF_RE = re.compile(r"\b(take\s*off|takeoff|taken\s*off)\b", re.IGNORECASE)
LANDED_RE  = re.compile(r"\b(landed|landing)\b", re.IGNORECASE)

NOGO_RE    = re.compile(r"\bno\s*go\s*volo\b", re.IGNORECASE)
GOVOLO_RE  = re.compile(r"\bgo\s*volo\b", re.IGNORECASE)

CONFIG_FILE = "config.json"


def now_hms():
    return datetime.now().strftime("%H:%M:%S")


def decode_subject(raw_subj: str) -> str:
    if not raw_subj:
        return ""
    parts = decode_header(raw_subj)
    out = ""
    for part, enc in parts:
        if isinstance(part, bytes):
            out += part.decode(enc or "utf-8", errors="ignore")
        else:
            out += part
    return out.strip()


def is_notam_subject(subject: str) -> bool:
    s = (subject or "").strip()
    return s.upper().startswith("NOTAM")


def get_text_body(msg: email.message.Message) -> str:
    """Extract best-effort plain text body from an email.message."""
    if msg.is_multipart():
        # Prefer text/plain
        for part in msg.walk():
            ctype = (part.get_content_type() or "").lower()
            disp = str(part.get("Content-Disposition") or "").lower()
            if ctype == "text/plain" and "attachment" not in disp:
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace").strip()
        # Fallback: first text/*
        for part in msg.walk():
            ctype = (part.get_content_type() or "").lower()
            if ctype.startswith("text/"):
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace").strip()
        return ""
    payload = msg.get_payload(decode=True) or b""
    charset = msg.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace").strip()


def clean_body(text: str) -> str:
    # Remove super long reply chains (best effort)
    t = (text or "").replace("\r\n", "\n")
    # Common separators (English/Italian)
    for sep in ["\nOn ", "\nIl ", "\nDa: ", "\nFrom: "]:
        if sep in t:
            t = t.split(sep, 1)[0]
    return t.strip()


def safe_load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ensure_config_has_keys(cfg: dict):
    if "imap" not in cfg:
        raise ValueError("config.json: manca la sezione 'imap'")

    # server/port sono obbligatori; credenziali possono arrivare da env var
    for k in ("server", "port"):
        if k not in cfg["imap"]:
            raise ValueError(f"config.json: imap.{k} mancante")

    # Se non ci sono nel config, le prendiamo da variabili d'ambiente:
    # READI_IMAP_USER / READI_IMAP_PASS
    cfg["imap"]["email_user"] = cfg["imap"].get("email_user") or os.environ.get("READI_IMAP_USER", "")
    cfg["imap"]["email_pass"] = cfg["imap"].get("email_pass") or os.environ.get("READI_IMAP_PASS", "")

    if not cfg["imap"]["email_user"] or not cfg["imap"]["email_pass"]:
        raise ValueError(
            "Credenziali IMAP mancanti. Metti imap.email_user e imap.email_pass in config.json "
            "oppure esporta READI_IMAP_USER e READI_IMAP_PASS."
        )


def parse_subject(subject: str, aliases: dict):
    """
    Return: (drone, event, reason)
    event: TAKEOFF | LANDED | NO_GO | GO
    """
    s = (subject or "").strip()
    s_low = s.lower()

    event = None
    reason = ""

    if NOGO_RE.search(s_low):
        event = "NO_GO"
        idx = s_low.find("no go volo")
        tail = s[idx:] if idx >= 0 else s
        if ":" in tail:
            reason = tail.split(":", 1)[1].strip()
        else:
            reason = tail.replace("NO GO VOLO", "").replace("no go volo", "").strip(" -:").strip()

    elif GOVOLO_RE.search(s_low):
        event = "GO"

    elif TAKEOFF_RE.search(s_low):
        event = "TAKEOFF"

    elif LANDED_RE.search(s_low):
        event = "LANDED"

    else:
        return None

    # match drone name via aliases
    for drone_name, alias_list in (aliases or {}).items():
        for alias in (alias_list or []):
            if not alias:
                continue
            if str(alias).lower() in s_low:
                return drone_name, event, reason

    return None


# -------------------------
# Card UI
# -------------------------
class DroneCard(ttk.Frame):
    def __init__(self, parent, drone_name: str, theme: dict):
        super().__init__(parent)
        self.drone_name = drone_name
        self.theme = theme

        self.state = "A_TERRA"  # A_TERRA | IN_VOLO | NO_GO
        self.timer_start_ts = None

        self.configure(style="Card.TFrame")

        self.title_lbl = ttk.Label(self, text=drone_name, style="CardTitle.TLabel")
        self.title_lbl.grid(row=0, column=0, sticky="w", padx=14, pady=(12, 6))

        self.status_box = tk.Frame(self, bg=theme["green"], height=56)
        self.status_box.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
        self.status_box.grid_propagate(False)

        self.status_lbl = tk.Label(
            self.status_box, text="A TERRA", bg=theme["green"],
            fg=theme["status_text"], font=("Segoe UI", 14, "bold")
        )
        self.status_lbl.place(relx=0.5, rely=0.5, anchor="center")

        self.timer_lbl = ttk.Label(self, text="Timer: —", style="CardMeta.TLabel")
        self.timer_lbl.grid(row=2, column=0, sticky="w", padx=14, pady=(0, 2))

        self.last_lbl = ttk.Label(self, text="Ultimo evento: —", style="CardMetaItalic.TLabel")
        self.last_lbl.grid(row=3, column=0, sticky="w", padx=14, pady=(0, 12))

        self.columnconfigure(0, weight=1)

    def set_state(self, state: str):
        self.state = state
        if state == "IN_VOLO":
            bg = self.theme["red"]
            txt = "IN VOLO"
            if self.timer_start_ts is None:
                self.timer_start_ts = time.time()
        elif state == "NO_GO":
            bg = self.theme["yellow"]
            txt = "NO GO"
            self.timer_start_ts = None
        else:
            bg = self.theme["green"]
            txt = "A TERRA"
            self.timer_start_ts = None

        self.status_box.configure(bg=bg)
        self.status_lbl.configure(bg=bg, text=txt)

        self._refresh_timer()

    def set_last_event(self, text: str):
        self.last_lbl.configure(text=f"Ultimo evento: {text if text else '—'}")

    def set_timer_start(self, ts):
        self.timer_start_ts = ts
        self._refresh_timer()

    def _refresh_timer(self):
        if self.timer_start_ts is None:
            self.timer_lbl.configure(text="Timer: —")
            return
        sec = int(max(0, time.time() - self.timer_start_ts))
        mm = sec // 60
        ss = sec % 60
        self.timer_lbl.configure(text=f"Timer: {mm:02d}:{ss:02d}")


# -------------------------
# Main App
# -------------------------
class ControlCenterApp:
    def __init__(self, root: tk.Tk, cfg: dict):
        self.root = root
        self.cfg = cfg
        self.imap_cfg = cfg["imap"]

        self.poll_seconds = int(cfg.get("poll_seconds", 3))
        self.tail_uids = int(cfg.get("tail_uids", 300))
        self.aliases = cfg.get("aliases", {})

        self.ui_cfg = cfg.get("ui", {})
        self.title = self.ui_cfg.get("title", "ReADI Control Center AiviewGroup")
        self.lock_1366x768 = bool(self.ui_cfg.get("lock_1366x768", False))
        self.logo_path = self.ui_cfg.get("logo_path", "")
        self.fixed_columns = int(self.ui_cfg.get("columns", 0))  # 0 = auto
        self.card_min_width = int(self.ui_cfg.get("card_min_width", 260))
        self.beep_enabled = bool(self.ui_cfg.get("beep", True))

        self.theme = {
            "bg": "#0b0f14",
            "card_bg": "#111822",
            "card_border": "#1f2a38",
            "text": "#e7eef7",
            "muted": "#a9b7c6",
            "green": "#39d98a",
            "red": "#ff3b3b",
            "yellow": "#f7c948",
            "status_text": "#0b0f14",
        }

        self.imap = None
        self.running = True
        self.connected = False
        self.last_uid_int = 0

        # Stato “vero”
        self.model = {}

        self.cards = {}
        self.card_wrappers = {}
        self.columns = 4
        self.global_last_event = "—"

        # =========================
        # NOTAM panel (bottom)
        # =========================
        self.notam_height = int(self.ui_cfg.get("notam_height", 220))
        self.notam_max = int(cfg.get("notam_max", 250))
        self._notam_new_ttl_ms = int(cfg.get("notam_new_ttl_ms", 10000))
        self.notams = []  # newest first
        self.notam_seen_uids = set()
        self.notam_iid_to_item = {}

        # Bottom area padding so the scrollable grid doesn't hide behind the NOTAM panel
        self.hud_bottom_pad = self.notam_height + 64


        self._setup_styles()
        self._build_ui()

        # init model
        for d in (self.aliases.keys() or ["ALPHA","BRAVO","CHARLIE","DELTA","ECHO","FOXTROT","GOLF","HOTEL","INDIA"]):
            self.model.setdefault(d, {"state": "A_TERRA", "timer_start_ts": None, "last_event_text": "—"})

        # Restore from mail
        self._startup_restore_from_mail()

        # IMAP thread
        threading.Thread(target=self._imap_loop, daemon=True).start()

        # timer refresh
        self._tick_timers()

    # ---------------- UI ----------------
    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Root.TFrame", background=self.theme["bg"])
        style.configure("Card.TFrame", background=self.theme["card_bg"])
        style.configure("CardTitle.TLabel", background=self.theme["card_bg"], foreground=self.theme["text"],
                        font=("Segoe UI", 14, "bold"))
        style.configure("CardMeta.TLabel", background=self.theme["card_bg"], foreground=self.theme["muted"],
                        font=("Segoe UI", 10))
        style.configure("CardMetaItalic.TLabel", background=self.theme["card_bg"], foreground=self.theme["muted"],
                        font=("Segoe UI", 10, "italic"))
        style.configure("HeaderTitle.TLabel", background=self.theme["bg"], foreground=self.theme["text"],
                        font=("Segoe UI", 24, "bold"))
        style.configure("HeaderSub.TLabel", background=self.theme["bg"], foreground=self.theme["muted"],
                        font=("Segoe UI", 10))

        # NOTAM panel (Treeview) - dark theme
        style.configure(
            "Notam.Treeview",
            background=self.theme["bg"],
            foreground=self.theme["text"],
            fieldbackground=self.theme["bg"],
            rowheight=26,
            borderwidth=0
        )
        style.configure(
            "Notam.Treeview.Heading",
            background=self.theme["card_bg"],
            foreground=self.theme.get("accent", self.theme.get("green", "#00e676")),
            relief="flat"
        )
        style.map(
            "Notam.Treeview",
            background=[("selected", "#003c2f")],
            foreground=[("selected", "#eafff5")]
        )


    def _build_ui(self):
        self.root.title(self.title)
        self.root.configure(bg=self.theme["bg"])

        if self.lock_1366x768:
            self.root.geometry("1366x768")
            self.root.minsize(1366, 768)
            self.root.maxsize(1366, 768)
        else:
            self.root.state("zoomed")

        self.root_frame = ttk.Frame(self.root, style="Root.TFrame")
        self.root_frame.pack(fill="both", expand=True)

        # Header row
        header = ttk.Frame(self.root_frame, style="Root.TFrame")
        header.pack(fill="x", padx=18, pady=(14, 8))

        left = ttk.Frame(header, style="Root.TFrame")
        left.pack(side="left", fill="x", expand=True)

        ttk.Label(left, text=self.title, style="HeaderTitle.TLabel").pack(anchor="w")
        self.sub_lbl = ttk.Label(left, text="Connessione…", style="HeaderSub.TLabel")
        self.sub_lbl.pack(anchor="w", pady=(6, 0))

        center = ttk.Frame(header, style="Root.TFrame")
        center.pack(side="left", padx=12)

        self.logo_lbl = None
        self._load_logo(center)

        right = ttk.Frame(header, style="Root.TFrame")
        right.pack(side="right")

        self.conn_dot = tk.Canvas(right, width=14, height=14, bg=self.theme["bg"], highlightthickness=0)
        self.conn_dot.pack(side="left", padx=(0, 6))
        self.conn_text = ttk.Label(right, text="DISCONNESSO", style="HeaderSub.TLabel")
        self.conn_text.pack(side="left")
        self._set_connected(False)

        # Scroll grid
        self.canvas = tk.Canvas(self.root_frame, bg=self.theme["bg"], highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.root_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side="right", fill="y", padx=(0, 10), pady=(0, 10))
        # ⬇️ lascio spazio sotto per HUD fisso (così non si sovrappone)
        self.canvas.pack(side="left", fill="both", expand=True, padx=(18, 8), pady=(0, self.hud_bottom_pad))

        self.grid_container = ttk.Frame(self.canvas, style="Root.TFrame")
        self.canvas_window = self.canvas.create_window((0, 0), window=self.grid_container, anchor="nw")

        self.grid_container.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # =========================
        # BOTTOM CONTAINER (NOTAM + footer)
        # =========================
        self.bottom_container = tk.Frame(self.root, bg=self.theme["bg"])
        self.bottom_container.place(relx=0, rely=1.0, relwidth=1.0, anchor="sw")
        self.bottom_container.pack_propagate(False)
        self.bottom_container.configure(height=self.hud_bottom_pad)

        # ---- NOTAM PANEL ----
        self.notam_panel = tk.Frame(self.bottom_container, bg=self.theme["card_bg"], highlightthickness=1)
        self.notam_panel.configure(highlightbackground=self.theme["card_border"], highlightcolor=self.theme["card_border"])
        self.notam_panel.pack(side="top", fill="x", padx=18, pady=(0, 8))
        self.notam_panel.pack_propagate(False)
        self.notam_panel.configure(height=self.notam_height)

        self._build_notam_panel(self.notam_panel)

        # ---- FOOTER ----
        self.hud_bottom = ttk.Frame(self.bottom_container, style="Root.TFrame")
        self.hud_bottom.pack(side="top", fill="x")

        self.hud_bottom.columnconfigure(0, weight=1)
        self.hud_bottom.columnconfigure(1, weight=1)
        self.hud_bottom.columnconfigure(2, weight=1)

        self.global_lbl = ttk.Label(
        self.hud_bottom,
        text="Ultimo evento globale: —",
        style="CardMetaItalic.TLabel",
        anchor="center"
        )
        self.global_lbl.grid(row=0, column=1, pady=(6, 10))

        ttk.Label(
        self.hud_bottom,
        text="DEVELOPED BY Roberto Innocenti - Powered by AiviewGroup - V.003",
        style="HeaderSub.TLabel"
        ).grid(row=0, column=2, sticky="e", padx=18, pady=(6, 10))

        self._rebuild_cards()

    def _load_logo(self, parent):
        if not self.logo_path or not HAS_PIL:
            return
        try:
            path = self.logo_path
            if not os.path.isabs(path):
                path = os.path.join(os.getcwd(), path)
            if not os.path.exists(path):
                return

            img = Image.open(path).convert("RGBA")
            target_h = 64
            w, h = img.size
            scale = target_h / max(1, h)
            img = img.resize((int(w * scale), int(h * scale)))

            self._logo_imgtk = ImageTk.PhotoImage(img)
            self.logo_lbl = tk.Label(parent, image=self._logo_imgtk, bg=self.theme["bg"])
            self.logo_lbl.pack()
        except Exception:
            return

    def _set_connected(self, ok: bool):
        self.connected = ok
        self.conn_dot.delete("all")
        color = self.theme["green"] if ok else self.theme["red"]
        self.conn_dot.create_oval(2, 2, 12, 12, fill=color, outline=color)
        self.conn_text.configure(text="CONNESSO" if ok else "DISCONNESSO")

    def _on_frame_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _compute_columns(self):
        if self.fixed_columns and self.fixed_columns > 0:
            return self.fixed_columns
        # se lock 1366, meglio fisso 4 (stabile)
        if self.lock_1366x768:
            return 4
        width = max(1, self.canvas.winfo_width())
        cols = max(2, min(6, width // self.card_min_width))
        return cols

    def _on_canvas_configure(self, event=None):
        if event:
            self.canvas.itemconfig(self.canvas_window, width=event.width)
        cols = self._compute_columns()
        if cols != self.columns:
            self.columns = cols
            self._rebuild_cards()

    def _rebuild_cards(self):
        for w in self.grid_container.winfo_children():
            w.destroy()
        self.cards.clear()
        self.card_wrappers.clear()

        drone_names = list(self.aliases.keys()) or list(self.model.keys())
        if not drone_names:
            drone_names = ["ALPHA","BRAVO","CHARLIE","DELTA","ECHO","FOXTROT","GOLF","HOTEL","INDIA"]

        for i, name in enumerate(drone_names):
            self.model.setdefault(name, {"state": "A_TERRA", "timer_start_ts": None, "last_event_text": "—"})

            wrapper = tk.Frame(self.grid_container, bg=self.theme["card_border"], padx=2, pady=2)
            card = DroneCard(wrapper, name, self.theme)
            card.pack(fill="both", expand=True)

            r = i // self.columns
            c = i % self.columns
            wrapper.grid(row=r, column=c, sticky="nsew", padx=10, pady=10)
            self.grid_container.columnconfigure(c, weight=1)

            self.cards[name] = card
            self.card_wrappers[name] = wrapper

        for drone, st in self.model.items():
            if drone in self.cards:
                self._apply_model_to_ui(drone)

    def _apply_model_to_ui(self, drone: str):
        st = self.model[drone]
        card = self.cards.get(drone)
        if not card:
            return

        card.set_state(st["state"])
        card.set_timer_start(st["timer_start_ts"])
        card.set_last_event(st["last_event_text"])

        if st["state"] == "IN_VOLO":
            self.card_wrappers[drone].configure(bg=self.theme["red"])
        elif st["state"] == "NO_GO":
            self.card_wrappers[drone].configure(bg=self.theme["yellow"])
        else:
            self.card_wrappers[drone].configure(bg=self.theme["green"])

    def _tick_timers(self):
        for card in self.cards.values():
            card._refresh_timer()
        self.root.after(500, self._tick_timers)

    # ---------------- IMAP ----------------
    def _imap_connect(self):
        im = self.imap_cfg
        m = imaplib.IMAP4_SSL(im["server"], int(im.get("port", 993)))
        m.login(im["email_user"], im["email_pass"])
        m.select("INBOX")
        return m

    def _uid_search_all(self):
        status, data = self.imap.uid("search", None, "ALL")
        if status != "OK" or not data or not data[0]:
            return []
        uids = data[0].split()
        return uids[-self.tail_uids:] if self.tail_uids > 0 else uids
    def _uid_fetch_email(self, uid_bytes):
        status, msg_data = self.imap.uid("fetch", uid_bytes, "(RFC822)")
        if status != "OK" or not msg_data or not msg_data[0]:
            return None
        raw_email = msg_data[0][1]
        return email.message_from_bytes(raw_email)

    def _startup_restore_from_mail(self):
        try:
            self.sub_lbl.configure(text="Ripristino stato da mail…")
            m = self._imap_connect()
            self._set_connected(True)

            uids = self._uid_search_all()
            for uid in uids:
                try:
                    uid_i = int(uid)
                except Exception:
                    continue

                msg = self._uid_fetch_email(uid)
                if not msg:
                    continue

                subj = decode_subject(msg.get("Subject", ""))
                if not subj:
                    continue

                # NOTAM feed (subject starts with NOTAM)
                if is_notam_subject(subj):
                    self._ingest_notam_from_msg(uid_i, msg, subj)
                    continue

                parsed = parse_subject(subj, self.aliases)
                if not parsed:
                    continue

                drone, event, reason = parsed
                self._apply_event(drone, event, reason, stamp_time=None, do_beep=False)

                self.last_uid_int = max(self.last_uid_int, uid_i)

            self.sub_lbl.configure(text=f"Connesso — ascolto da UID {self.last_uid_int + 1}")

            try:
                m.logout()
            except Exception:
                pass

        except Exception:
            self._set_connected(False)
            self.sub_lbl.configure(text="Connessione… (restore fallito)")

    def _imap_loop(self):
        while self.running:
            try:
                if self.imap is None:
                    self.imap = self._imap_connect()
                    self.root.after(0, lambda: self._set_connected(True))
                    self.root.after(0, lambda: self.sub_lbl.configure(
                        text=f"Connesso — ascolto da UID {self.last_uid_int + 1}"
                    ))

                self.imap.noop()
                self.imap.select("INBOX")

                uids = self._uid_search_all()
                for uid in uids:
                    try:
                        uid_i = int(uid)
                    except Exception:
                        continue
                    if uid_i <= self.last_uid_int:
                        continue

                    self.last_uid_int = uid_i
                    msg = self._uid_fetch_email(uid)
                    if not msg:
                        continue

                    subj = decode_subject(msg.get("Subject", ""))
                    if not subj:
                        continue

                    # NOTAM feed
                    if is_notam_subject(subj):
                        self._ingest_notam_from_msg(uid_i, msg, subj)
                        continue

                    parsed = parse_subject(subj, self.aliases)
                    if not parsed:
                        continue

                    drone, event, reason = parsed
                    self.root.after(0, lambda d=drone, e=event, r=reason: self._apply_event(d, e, r))

                time.sleep(self.poll_seconds)

            except Exception as e:
                self.imap = None
                self.root.after(0, lambda: self._set_connected(False))
                self.root.after(0, lambda: self.sub_lbl.configure(text=f"Disconnesso — retry… ({e})"))
                time.sleep(max(2, self.poll_seconds))

    # ---------------- Events -> Model -> UI ----------------
    def _beep_takeoff(self):
        if not self.beep_enabled:
            return
        try:
            if HAS_WINSOUND:
                winsound.Beep(1100, 180)
                winsound.Beep(1300, 180)
            else:
                self.root.bell()
        except Exception:
            pass

    def _set_global_event(self, text: str):
        self.global_last_event = text
        self.global_lbl.configure(text=f"Ultimo evento globale: {text}")

    def _apply_event(self, drone: str, event: str, reason: str = "", stamp_time: str | None = None, do_beep=True):
        if drone not in self.model:
            self.model[drone] = {"state": "A_TERRA", "timer_start_ts": None, "last_event_text": "—"}

        t = stamp_time or now_hms()

        if event == "TAKEOFF":
            self.model[drone]["state"] = "IN_VOLO"
            if self.model[drone]["timer_start_ts"] is None:
                self.model[drone]["timer_start_ts"] = time.time()
            self.model[drone]["last_event_text"] = f"{t} — TAKEOFF"
            self._set_global_event(f"{drone} — TAKEOFF ({t})")
            if do_beep:
                self._beep_takeoff()

        elif event == "LANDED":
            self.model[drone]["state"] = "A_TERRA"
            self.model[drone]["timer_start_ts"] = None
            self.model[drone]["last_event_text"] = f"{t} — LANDED"
            self._set_global_event(f"{drone} — LANDED ({t})")

        elif event == "NO_GO":
            self.model[drone]["state"] = "NO_GO"
            self.model[drone]["timer_start_ts"] = None

            # NO GO: sulla card c’è già "NO GO", quindi qui mostriamo solo motivo (se c’è)
            if reason:
                self.model[drone]["last_event_text"] = f"{t} — {reason}"
                self._set_global_event(f"{drone} — NO GO ({t}) — {reason}")
            else:
                self.model[drone]["last_event_text"] = f"{t} — NO GO"
                self._set_global_event(f"{drone} — NO GO ({t})")



        elif event == "GO":
            self.model[drone]["state"] = "A_TERRA"
            self.model[drone]["timer_start_ts"] = None
            self.model[drone]["last_event_text"] = f"{t} — GO VOLO"
            self._set_global_event(f"{drone} — GO VOLO ({t})")

        if drone in self.cards:
            self._apply_model_to_ui(drone)



    # ---------------- NOTAM UI ----------------
    def _build_notam_panel(self, parent):
        header = ttk.Frame(parent, style="Root.TFrame")
        header.pack(side="top", fill="x", padx=12, pady=(10, 6))

        ttk.Label(header, text="NOTAM / Comunicazioni PIC", style="CardTitle.TLabel").pack(side="left")

        self.notam_count_lbl = ttk.Label(header, text="0 msg", style="CardMeta.TLabel")
        self.notam_count_lbl.pack(side="left", padx=(10, 0))

        table_wrap = ttk.Frame(parent, style="Root.TFrame")
        table_wrap.pack(side="top", fill="both", expand=True, padx=12, pady=(0, 10))

        cols = ("flag", "dt", "pic", "msg")
        self.notam_tree = ttk.Treeview(table_wrap, columns=cols, show="headings", style="Notam.Treeview")
        self.notam_tree.heading("flag", text="")
        self.notam_tree.heading("dt", text="Data/Ora")
        self.notam_tree.heading("pic", text="PIC")
        self.notam_tree.heading("msg", text="Messaggio")

        self.notam_tree.column("flag", width=42, anchor="center", stretch=False)
        self.notam_tree.column("dt", width=150, anchor="w")
        self.notam_tree.column("pic", width=220, anchor="w")
        self.notam_tree.column("msg", width=1000, anchor="w")

        ysb = ttk.Scrollbar(table_wrap, orient="vertical", command=self.notam_tree.yview)
        self.notam_tree.configure(yscrollcommand=ysb.set)

        # Row styles
        self.notam_tree.tag_configure("even", background="#0b1117", foreground="#d6e3f0")
        self.notam_tree.tag_configure("odd", background="#0f1720", foreground="#d6e3f0")
        self.notam_tree.tag_configure("new", background="#003c2f", foreground="#eafff5")
        self.notam_tree.tag_configure("warn", foreground="#ffcc80")

        self.notam_tree.pack(side="left", fill="both", expand=True)
        ysb.pack(side="right", fill="y")

        self.notam_tree.bind("<Double-1>", self._open_selected_notam)

    def _open_selected_notam(self, _evt=None):
        sel = self.notam_tree.selection()
        if not sel:
            return
        iid = sel[0]
        item = self.notam_iid_to_item.get(iid)
        if not item:
            return

        dt_show = item.get("dt_iso") or ""
        try:
            if dt_show:
                dt_show = datetime.fromisoformat(dt_show).strftime("%d/%m/%Y %H:%M:%S")
        except Exception:
            pass

        pic = item.get("pic_from") or "—"
        subj = item.get("subject") or "NOTAM"
        body = item.get("body") or ""

        messagebox.showinfo(subj, f"Data/Ora: {dt_show}\nPIC: {pic}\n\n{body}")

    def _update_notam_count(self):
        try:
            self.notam_count_lbl.configure(text=f"{len(self.notams)} msg")
        except Exception:
            pass

    def _ingest_notam_from_msg(self, uid_i: int, msg, subject: str):
        if uid_i in self.notam_seen_uids:
            return
        self.notam_seen_uids.add(uid_i)

        dt_iso = ""
        try:
            dt = parsedate_to_datetime(msg.get("Date"))
            dt_iso = dt.astimezone().isoformat(timespec="seconds")
        except Exception:
            dt_iso = ""

        pic_from = decode_subject(msg.get("From", ""))
        body = clean_body(get_text_body(msg))

        item = {"dt_iso": dt_iso, "pic_from": pic_from, "subject": subject, "body": body}

        self.notams.insert(0, item)
        if len(self.notams) > self.notam_max:
            self.notams = self.notams[:self.notam_max]

        self.root.after(0, lambda it=item: self._add_notam_row(it))

    def _add_notam_row(self, item: dict):
        dt_show = item.get("dt_iso") or ""
        try:
            if dt_show:
                dt_show = datetime.fromisoformat(dt_show).strftime("%d/%m %H:%M:%S")
        except Exception:
            pass

        body = (item.get("body") or "").strip()
        body_one_line = " ".join(body.split())
        if len(body_one_line) > 180:
            body_one_line = body_one_line[:177] + "…"

        pic = item.get("pic_from") or "—"

        # Quick warning flag based on keywords (subject + body)
        kw = f"{item.get('subject') or ''} {item.get('body') or ''}".lower()
        warn_words = [
            "vento", "wind", "strong", "raffiche", "gust", "temporale", "thunder",
            "pioggia", "rain", "neve", "snow", "ghiaccio", "ice",
            "allerta", "alert", "fulmini", "lightning", "dirott", "divert"
        ]
        is_warn = any(w in kw for w in warn_words)
        flag = "⚠" if is_warn else ""

        tags = ["new"]
        if is_warn:
            tags.append("warn")

        iid = self.notam_tree.insert("", 0, values=(flag, dt_show, pic, body_one_line), tags=tuple(tags))
        self.notam_iid_to_item[iid] = item
        self._update_notam_count()

        # Zebra striping (cheap: list is short)
        self._restyle_notam_rows()

        # Fade the "new" highlight after a bit
        self.root.after(self._notam_new_ttl_ms, lambda _iid=iid: self._expire_notam_new_tag(_iid))

        if self.beep_enabled:
            try:
                if HAS_WINSOUND:
                    winsound.Beep(900, 120)
                else:
                    self.root.bell()
            except Exception:
                pass

    def _restyle_notam_rows(self):
        # Zebra striping + keep extra tags (new/warn)
        children = self.notam_tree.get_children("")
        for idx, iid in enumerate(children):
            cur_tags = set(self.notam_tree.item(iid, "tags") or [])
            cur_tags.discard("odd")
            cur_tags.discard("even")
            cur_tags.add("even" if idx % 2 == 0 else "odd")
            self.notam_tree.item(iid, tags=tuple(cur_tags))

    def _expire_notam_new_tag(self, iid: str):
        if not iid or not self.notam_tree.exists(iid):
            return
        cur_tags = set(self.notam_tree.item(iid, "tags") or [])
        if "new" in cur_tags:
            cur_tags.discard("new")
            self.notam_tree.item(iid, tags=tuple(cur_tags))


    def stop(self):
        self.running = False
        try:
            if self.imap:
                self.imap.logout()
        except Exception:
            pass

def main():
    try:
        cfg = safe_load_json(CONFIG_FILE)
        ensure_config_has_keys(cfg)
    except Exception as e:
        messagebox.showerror("Errore config", f"config.json non valido:\n{e}")
        return

    root = tk.Tk()
    app = ControlCenterApp(root, cfg)

    def on_close():
        app.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
