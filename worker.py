import imaplib
import email
import json
import time
from email.header import decode_header

CONFIG_FILE = "config.json"
STATE_FILE = "state.json"

def decode_subject(raw):
    if not raw:
        return ""
    parts = decode_header(raw)
    out = ""
    for p, enc in parts:
        if isinstance(p, bytes):
            out += p.decode(enc or "utf-8", errors="ignore")
        else:
            out += p
    return out

def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def main():
    cfg = load_config()
    imap_cfg = cfg["imap"]

    mail = imaplib.IMAP4_SSL(imap_cfg["server"])
    mail.login(imap_cfg["email_user"], imap_cfg["email_pass"])
    mail.select("inbox")

    state = {"drones": []}

    while True:
        _, messages = mail.search(None, "ALL")
        ids = messages[0].split()[-20:]

        drones = []

        for i in ids:
            _, msg_data = mail.fetch(i, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])

            subject = decode_subject(msg["Subject"])

            if "ALPHA" in subject:
                drones.append({"name": "ALPHA", "status": "Online", "battery": 78})
            if "BRAVO" in subject:
                drones.append({"name": "BRAVO", "status": "Standby", "battery": 55})

        state["drones"] = drones
        save_state(state)

        time.sleep(5)

if __name__ == "__main__":
    main()