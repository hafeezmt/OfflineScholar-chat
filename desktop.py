"""Small desktop window that runs OfflineScholar only while it is open."""
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import font as tkfont
from tkinter import ttk

import manage


class DesktopApp:
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.closing = False
        self.url = None

        root.title("OfflineScholar")
        root.geometry("560x320")
        root.minsize(520, 300)
        root.protocol("WM_DELETE_WINDOW", self.shutdown)

        frame = ttk.Frame(root, padding=24)
        frame.pack(fill="both", expand=True)

        heading_font = tkfont.nametofont("TkHeadingFont").copy()
        heading_font.configure(size=20, weight="bold")
        ttk.Label(frame, text="OfflineScholar", font=heading_font).pack(anchor="w")

        ttk.Label(frame, text="Your private study assistant, running on this computer.").pack(
            anchor="w", pady=(4, 18))

        self.status = tk.StringVar(value="Starting OfflineScholar...")
        ttk.Label(frame, textvariable=self.status, wraplength=500).pack(anchor="w")

        self.url_label = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.url_label, foreground="#2457a7").pack(
            anchor="w", pady=(8, 18))

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", side="bottom")
        self.open_button = ttk.Button(buttons, text="Open in browser", command=self.open_browser,
                                      state="disabled")
        self.open_button.pack(side="left")
        ttk.Button(buttons, text="Stop and close", command=self.shutdown).pack(side="right")

        ttk.Label(
            frame,
            text="Closing this window stops the server and unloads the local models.",
            foreground="#666666",
        ).pack(anchor="w", side="bottom", pady=(16, 0))

        root.after(100, self.start)
        root.after(100, self.poll)

    def start(self):
        threading.Thread(target=self.start_worker, daemon=True).start()

    def start_worker(self):
        try:
            url, _, _ = manage.start(open_browser=False)
            result = ("ready", url)
        except Exception as error:
            result = ("error", str(error))
        if self.closing:
            try:
                manage.stop()
            except Exception:
                pass
        else:
            self.events.put(result)

    def poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "ready":
                    self.ready(event[1])
                elif event[0] == "error":
                    self.failed(event[1])
        except queue.Empty:
            pass
        if not self.closing:
            self.root.after(100, self.poll)

    def ready(self, url):
        self.url = url
        self.status.set("OfflineScholar is running.")
        self.url_label.set(url)
        self.open_button.configure(state="normal")
        webbrowser.open(url)

    def failed(self, message):
        self.status.set(f"Could not start OfflineScholar.\n\n{message}\n\nSee server.log in the app folder.")
        self.url_label.set("")

    def open_browser(self):
        if self.url:
            webbrowser.open(self.url)

    def shutdown(self):
        if self.closing:
            return
        self.closing = True
        self.status.set("Stopping OfflineScholar and unloading models...")
        self.root.update_idletasks()
        try:
            manage.stop()
        except Exception as error:
            print(f"Could not stop OfflineScholar: {error}", file=sys.stderr)
        self.root.destroy()


def main():
    root = tk.Tk()
    DesktopApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
