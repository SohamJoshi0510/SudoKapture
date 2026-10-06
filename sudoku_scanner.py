"""Sudoku Scanner (customtkinter)

Photo of a Sudoku -> Gemini reads the grid -> digital board you can fix, play,
or solve with backtracking.

Setup:
    pip install customtkinter pillow requests
    pip install opencv-python        # recommended: scanner-style straightening + webcam

Put your Google AI Studio key in a .env file next to this script:
    GEMINI_API_KEY=your_key_here
    GEMINI_MODEL=gemini-flash-latest      # optional
"""
import base64
import io
import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import requests
from PIL import Image, ImageOps, ImageTk

try:
    import cv2
    import numpy as np
except ImportError:  # straightening and webcam are optional
    cv2 = None
    np = None

# --------------------------------------------------------------------------- config
ENV_PATH = Path(__file__).with_name(".env")
DEFAULT_MODEL = "gemini-flash-latest"
MODELS = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
PROMPT = (
    "This image shows a Sudoku puzzle, possibly photographed from a newspaper or screen at an angle, "
    "with other text around it. Find the 9x9 grid and read it row by row, top to bottom, left to right. "
    'Return JSON with "found" (true if a Sudoku grid is visible) and "grid" (9 rows of 9 integers). '
    "Use the printed digit 1-9 for a filled cell and 0 for an empty cell. Ignore handwriting, pencil marks "
    "and anything outside the grid. Do not solve the puzzle and do not guess digits you cannot see. "
    "If no grid is visible, return found false and nine rows of nine zeros."
)
SPEEDS = [(1, 150), (1, 40), (3, 16), (30, 16), (5000, 1)]  # (steps per tick, delay ms)
COL = dict(
    bg="#12132a", panel="#1a1c3a", panel2="#222551", line="#3b3f78", strong="#8b7cff",
    text="#ece9ff", muted="#9c9fcc", accent="#8b7cff", ink="#12132a",
    given="#f4f1ff", user="#9db4ff", auto="#6ee7b7", trial="#ffb86b", bad="#ff6b81",
    sel="#3a3688", peer="#232652", same="#33307a",
)
CELL, PAD = 58, 6
SIZE = CELL * 9 + PAD * 2


# --------------------------------------------------------------------------- .env helpers
def load_env():
    vals = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


def get_key():
    env = load_env()
    return (os.environ.get("GEMINI_API_KEY") or env.get("GEMINI_API_KEY")
            or env.get("GOOGLE_API_KEY") or "")


def save_key(key):
    lines = []
    if ENV_PATH.exists():
        lines = [l for l in ENV_PATH.read_text(encoding="utf-8").splitlines()
                 if not l.strip().startswith("GEMINI_API_KEY")]
    lines.append(f"GEMINI_API_KEY={key}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- solver
PEERS = [
    [j for j in range(81)
     if j != i and (i // 9 == j // 9 or i % 9 == j % 9 or (i // 27 == j // 27 and (i % 9) // 3 == (j % 9) // 3))]
    for i in range(81)
]
PEERSETS = [set(p) for p in PEERS]


def make_masks(g):
    rows, cols, boxes = [0] * 9, [0] * 9, [0] * 9
    for i, v in enumerate(g):
        if not v:
            continue
        r, c = divmod(i, 9)
        b = (r // 3) * 3 + c // 3
        bit = 1 << (v - 1)
        if (rows[r] | cols[c] | boxes[b]) & bit:
            return None
        rows[r] |= bit
        cols[c] |= bit
        boxes[b] |= bit
    return rows, cols, boxes


def pick_cell(g, m):
    """Most constrained empty cell (fewest candidates)."""
    rows, cols, boxes = m
    best, bm, bc = -1, 0, 10
    for i in range(81):
        if g[i]:
            continue
        r, c = divmod(i, 9)
        mm = ~(rows[r] | cols[c] | boxes[(r // 3) * 3 + c // 3]) & 511
        k = bin(mm).count("1")
        if k < bc:
            best, bm, bc = i, mm, k
            if k == 0:
                break
    return best, bm


def search(g, m):
    """Step-by-step backtracking. Yields (cell, digit); digit 0 means 'undo'. Returns True if solved."""
    best, bm = pick_cell(g, m)
    if best < 0:
        return True
    rows, cols, boxes = m
    r, c = divmod(best, 9)
    b = (r // 3) * 3 + c // 3
    for d in range(1, 10):
        bit = 1 << (d - 1)
        if not bm & bit:
            continue
        g[best] = d
        rows[r] |= bit
        cols[c] |= bit
        boxes[b] |= bit
        yield best, d
        if (yield from search(g, m)):
            return True
        g[best] = 0
        rows[r] &= ~bit
        cols[c] &= ~bit
        boxes[b] &= ~bit
        yield best, 0
    return False


def count_solutions(grid, limit=2, max_nodes=1_500_000):
    """Fast solve that also counts solutions (stops at `limit`)."""
    g = list(grid)
    m = make_masks(g)
    if m is None:
        return dict(count=0, solution=None, conflict=True, aborted=False)
    rows, cols, boxes = m
    st = dict(count=0, solution=None, nodes=0, aborted=False)

    def rec():
        if st["aborted"]:
            return
        st["nodes"] += 1
        if st["nodes"] > max_nodes:
            st["aborted"] = True
            return
        best, bm = pick_cell(g, m)
        if best < 0:
            st["count"] += 1
            if st["solution"] is None:
                st["solution"] = g[:]
            return
        r, c = divmod(best, 9)
        b = (r // 3) * 3 + c // 3
        for d in range(1, 10):
            if st["count"] >= limit or st["aborted"]:
                break
            bit = 1 << (d - 1)
            if not bm & bit:
                continue
            g[best] = d
            rows[r] |= bit
            cols[c] |= bit
            boxes[b] |= bit
            rec()
            g[best] = 0
            rows[r] &= ~bit
            cols[c] &= ~bit
            boxes[b] &= ~bit

    rec()
    return dict(count=st["count"], solution=st["solution"], conflict=False, aborted=st["aborted"])


# --------------------------------------------------------------------------- Gemini
class GeminiError(Exception):
    pass


def encode_jpeg(pil):
    im = pil.copy()
    im.thumbnail((1600, 1600))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode()


def ask_gemini(key, model, b64):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {
        "contents": [{"parts": [{"text": PROMPT}, {"inline_data": {"mime_type": "image/jpeg", "data": b64}}]}],
        "generationConfig": {
            "temperature": 0,
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "found": {"type": "BOOLEAN"},
                    "grid": {"type": "ARRAY", "items": {"type": "ARRAY", "items": {"type": "INTEGER"}}},
                },
                "required": ["found", "grid"],
            },
        },
    }
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    try:
        for _ in range(2):
            res = requests.post(url, headers=headers, json=body, timeout=90)
            if res.status_code != 503:
                break
            time.sleep(2)
    except requests.RequestException:
        raise GeminiError("Network error. Check your connection and try again.")
    try:
        data = res.json()
    except ValueError:
        data = {}
    if not res.ok:
        msg = (data.get("error") or {}).get("message") or res.reason
        if res.status_code == 429:
            raise GeminiError("Free-tier rate limit reached. Wait a minute and try again, or pick another model.")
        if res.status_code == 400 and "api key" in msg.lower():
            raise GeminiError("Google rejected the API key. Check GEMINI_API_KEY in your .env file.")
        if res.status_code == 404:
            raise GeminiError(f"Model “{model}” was not found. Pick another one from the Model list.")
        raise GeminiError(f"Gemini error {res.status_code}: {msg}")
    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError, TypeError):
        text = ""
    if not text:
        raise GeminiError("Gemini returned no answer. Try a clearer photo.")
    import json
    try:
        obj = json.loads(text.replace("```json", "").replace("```", "").strip())
    except ValueError:
        raise GeminiError("The model reply could not be understood. Try again.")
    if not obj.get("found"):
        raise GeminiError("No Sudoku grid was found. Try a closer, well-lit photo of just the puzzle.")
    g = obj.get("grid")
    ok = (isinstance(g, list) and len(g) == 9 and all(
        isinstance(r, list) and len(r) == 9 and all(isinstance(v, int) and 0 <= v <= 9 for v in r) for r in g))
    if not ok:
        raise GeminiError("The reading was not a clean 9×9 grid. Try again with a straighter photo.")
    return [v for row in g for v in row]


# --------------------------------------------------------------------------- webcam window
class CameraWindow(ctk.CTkToplevel):
    def __init__(self, master, cap, on_capture):
        super().__init__(master)
        self.title("Take photo")
        self.configure(fg_color=COL["bg"])
        self.cap, self.on_capture, self.frame, self.job = cap, on_capture, None, None
        self.label = ctk.CTkLabel(self, text="")
        self.label.pack(padx=12, pady=12)
        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(pady=(0, 12))
        ctk.CTkButton(row, text="Capture", command=self.capture, fg_color=COL["accent"],
                      text_color=COL["ink"], hover_color="#a094ff").pack(side="left", padx=6)
        ctk.CTkButton(row, text="Cancel", command=self.close, fg_color=COL["panel2"],
                      border_width=1, border_color=COL["line"]).pack(side="left", padx=6)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.update_frame()

    def update_frame(self):
        ok, frame = self.cap.read()
        if ok:
            self.frame = frame
            img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            img.thumbnail((720, 540))
            self.photo = ctk.CTkImage(img, size=img.size)
            self.label.configure(image=self.photo)
        self.job = self.after(30, self.update_frame)

    def capture(self):
        if self.frame is None:
            return
        pil = Image.fromarray(cv2.cvtColor(self.frame, cv2.COLOR_BGR2RGB))
        self.close()
        self.on_capture(pil)

    def close(self):
        if self.job:
            self.after_cancel(self.job)
        self.cap.release()
        self.destroy()


# --------------------------------------------------------------------------- scanner (straighten + clean)
def order_points(pts):
    """Return corners as top-left, top-right, bottom-right, bottom-left."""
    pts = np.array(pts, dtype=np.float32).reshape(4, 2)
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], dtype=np.float32)


def whole_photo_quad(pil, margin=0.04):
    w, h = pil.size
    mx, my = w * margin, h * margin
    return [[mx, my], [w - 1 - mx, my], [w - 1 - mx, h - 1 - my], [mx, h - 1 - my]]


def grid_score(binary, quad):
    """How much the area inside `quad` looks like a 9x9 grid: how many of the 10 evenly spaced horizontal
    and vertical lines are really there (long unbroken runs), so text and page borders score low."""
    size = 450
    dst = np.array([[0, 0], [size - 1, 0], [size - 1, size - 1], [0, size - 1]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(order_points(quad), dst)
    t = cv2.warpPerspective(binary, m, (size, size))
    hor = cv2.morphologyEx(t, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (size // 3, 1))) > 0
    ver = cv2.morphologyEx(t, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, size // 3))) > 0
    idx = [int(round(k * (size - 1) / 9)) for k in range(10)]

    def strength(v):
        return [v[max(0, i - 3):i + 4].max() for i in idx]

    rows, cols = strength(hor.sum(axis=1) / size), strength(ver.sum(axis=0) / size)
    hits = lambda v: sum(1 for x in v if x > 0.6)
    return min(hits(rows), hits(cols)) + 0.01 * min(np.mean(rows), np.mean(cols))


def detect_quad(pil):
    """Find the Sudoku grid among square-ish 4-corner outlines by picking the one that looks most like a grid.
    Falls back to the whole photo."""
    rgb = np.array(pil)
    h, w = rgb.shape[:2]
    scale = min(1.0, 1000 / max(h, w))
    small = cv2.resize(rgb, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA) if scale < 1 else rgb
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    th = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 7)
    th = cv2.dilate(th, np.ones((3, 3), np.uint8))
    cnts = cv2.findContours(th, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[-2]
    min_area = 0.04 * small.shape[0] * small.shape[1]
    candidates = []
    for c in sorted(cnts, key=cv2.contourArea, reverse=True)[:60]:
        hull = cv2.convexHull(c)  # a digit touching the border can't break the outline
        if cv2.contourArea(hull) < min_area:
            continue
        approx = None
        for eps in (0.02, 0.03, 0.045):
            a = cv2.approxPolyDP(hull, eps * cv2.arcLength(hull, True), True)
            if len(a) == 4:
                approx = a
                break
        if approx is None:
            continue
        quad = order_points(approx)
        tl, tr, br, bl = quad
        wd = (np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)) / 2
        ht = (np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)) / 2
        if min(wd, ht) / max(wd, ht) < 0.65:  # a Sudoku grid is close to square
            continue
        candidates.append(quad)
        if len(candidates) == 14:
            break
    if not candidates:
        return whole_photo_quad(pil)
    best = max(candidates, key=lambda q: grid_score(th, q))
    quad = best / scale
    return [[float(min(max(x, 0), w - 1)), float(min(max(y, 0), h - 1))] for x, y in quad]


def warp_to_square(pil, quad):
    """Perspective-correct the quad into a flat square image."""
    src = order_points(quad)
    tl, tr, br, bl = src
    side = max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl), np.linalg.norm(bl - tl), np.linalg.norm(br - tr))
    size = int(min(1400, max(800, side)))
    dst = np.array([[0, 0], [size - 1, 0], [size - 1, size - 1], [0, size - 1]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(src, dst)
    out = cv2.warpPerspective(np.array(pil), m, (size, size), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return Image.fromarray(out)


def clean_scan(pil):
    """Even out shadows and uneven lighting so it looks like a flatbed scan (keeps grey, so digits stay crisp)."""
    gray = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2GRAY)
    background = cv2.GaussianBlur(gray, (0, 0), sigmaX=max(gray.shape) / 25)
    flat = cv2.divide(gray, background, scale=255)
    flat = cv2.normalize(flat, None, 0, 255, cv2.NORM_MINMAX)
    return Image.fromarray(flat).convert("RGB")


class CropWindow(ctk.CTkToplevel):
    """Drag the four corners onto the grid, like the Google Drive scanner."""
    OFF = 16

    def __init__(self, master, pil, on_done):
        super().__init__(master)
        self.title("Straighten the puzzle")
        self.configure(fg_color=COL["bg"])
        self.img, self.on_done, self.drag = pil, on_done, None
        self.clean = ctk.BooleanVar(value=True)
        ctk.CTkLabel(self, text="Drag the four corners onto the outer corners of the Sudoku grid. "
                                "The dashed lines should follow the thick 3×3 box lines.",
                     text_color=COL["muted"], wraplength=780, justify="left").pack(padx=14, pady=(12, 6), anchor="w")
        self.canvas = tk.Canvas(self, bg=COL["panel"], highlightthickness=0, cursor="crosshair")
        self.canvas.pack(padx=14, pady=4)
        self.canvas.bind("<Button-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_move)
        self.canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, "drag", None))

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(padx=14, pady=(8, 4), anchor="w")
        for text, cmd in [("Auto-detect", self.auto), ("Whole photo", self.whole), ("Rotate", self.rotate)]:
            ctk.CTkButton(bar, text=text, command=cmd, width=100, fg_color=COL["panel2"], hover_color=COL["sel"],
                          border_width=1, border_color=COL["line"]).pack(side="left", padx=(0, 8))
        ctk.CTkCheckBox(bar, text="Clean up lighting", variable=self.clean, fg_color=COL["accent"]).pack(side="left", padx=8)

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.pack(padx=14, pady=(4, 14), anchor="w")
        ctk.CTkButton(row, text="Apply", command=self.apply, width=100, fg_color=COL["accent"],
                      text_color=COL["ink"], hover_color="#a094ff").pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Use original photo", command=self.use_original, fg_color=COL["panel2"],
                      hover_color=COL["sel"], border_width=1, border_color=COL["line"]).pack(side="left", padx=(0, 8))
        ctk.CTkButton(row, text="Cancel", command=self.destroy, width=80, fg_color=COL["panel2"],
                      hover_color=COL["sel"], border_width=1, border_color=COL["line"]).pack(side="left")
        self.load_image(auto=True)
        self.after(150, self.lift)

    def load_image(self, auto):
        w, h = self.img.size
        self.s = min(860 / w, 580 / h, 1.0)
        dw, dh = max(1, int(w * self.s)), max(1, int(h * self.s))
        self.tkimg = ImageTk.PhotoImage(self.img.resize((dw, dh)))
        self.canvas.configure(width=dw + 2 * self.OFF, height=dh + 2 * self.OFF)
        self.corners = detect_quad(self.img) if auto else whole_photo_quad(self.img, 0.0)
        self.redraw()

    def auto(self):
        self.corners = detect_quad(self.img)
        self.redraw()

    def whole(self):
        self.corners = whole_photo_quad(self.img, 0.0)
        self.redraw()

    def rotate(self):
        self.img = self.img.rotate(-90, expand=True)
        self.load_image(auto=True)

    def to_canvas(self, p):
        return self.OFF + p[0] * self.s, self.OFF + p[1] * self.s

    def redraw(self):
        cv = self.canvas
        cv.delete("all")
        cv.create_image(self.OFF, self.OFF, anchor="nw", image=self.tkimg)
        pts = [self.to_canvas(p) for p in self.corners]
        cv.create_polygon(*[v for p in pts for v in p], outline=COL["accent"], fill="", width=2)
        tl, tr, br, bl = pts
        lerp = lambda a, b, t: (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
        for t in (1 / 3, 2 / 3):
            cv.create_line(*lerp(tl, bl, t), *lerp(tr, br, t), fill=COL["trial"], dash=(6, 4), width=2)
            cv.create_line(*lerp(tl, tr, t), *lerp(bl, br, t), fill=COL["trial"], dash=(6, 4), width=2)
        for x, y in pts:
            cv.create_oval(x - 9, y - 9, x + 9, y + 9, fill=COL["accent"], outline="white", width=2)

    def on_press(self, e):
        d = [(e.x - x) ** 2 + (e.y - y) ** 2 for x, y in (self.to_canvas(p) for p in self.corners)]
        i = min(range(4), key=d.__getitem__)
        self.drag = i if d[i] < 45 ** 2 else None

    def on_move(self, e):
        if self.drag is None:
            return
        w, h = self.img.size
        x = min(max((e.x - self.OFF) / self.s, 0), w - 1)
        y = min(max((e.y - self.OFF) / self.s, 0), h - 1)
        self.corners[self.drag] = [x, y]
        self.redraw()

    def apply(self):
        result = warp_to_square(self.img, self.corners)
        if self.clean.get():
            result = clean_scan(result)
        self.destroy()
        self.on_done(result)

    def use_original(self):
        img = self.img
        self.destroy()
        self.on_done(img)


# --------------------------------------------------------------------------- app
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")
        self.title("Sudoku Scanner")
        self.geometry("1140x840")
        self.minsize(1000, 720)
        self.configure(fg_color=COL["bg"])

        self.given = [0] * 81
        self.cur = [0] * 81
        self.notes = [0] * 81
        self.auto = [False] * 81
        self.mode = "setup"
        self.sel = -1
        self.notes_on = False
        self.wrong = set()
        self.undo_stack = []
        self.anim = None
        self.solution_cache = None
        self.solving = False
        self.reveal = 99
        self.original = None
        self.photo_pil = None
        self.preview_img = None
        self.q = queue.Queue()

        self.build_ui()
        self.bind("<Key>", self.on_key)
        self.after(100, self.poll)
        self.set_mode("setup")
        self.set_status("Choose a photo to begin, or type the clues in by hand.")

    # ---------------------------------------------------------------- UI building
    def btn(self, parent, text, cmd, primary=False, **kw):
        opts = dict(
            text=text, command=cmd, corner_radius=8, height=38,
            fg_color=COL["accent"] if primary else COL["panel2"],
            hover_color="#a094ff" if primary else COL["sel"],
            text_color=COL["ink"] if primary else COL["text"],
            border_width=0 if primary else 1, border_color=COL["line"],
        )
        opts.update(kw)
        return ctk.CTkButton(parent, **opts)

    def panel(self, title):
        f = ctk.CTkFrame(self.side, fg_color=COL["panel"], border_width=1, border_color=COL["line"], corner_radius=12)
        f.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(f, text=title, font=ctk.CTkFont(size=15, weight="bold"), anchor="w").pack(fill="x", padx=16, pady=(14, 6))
        return f

    def build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="w", padx=22, pady=(18, 10))
        ctk.CTkLabel(head, text="Sudoku Scanner", font=ctk.CTkFont(size=26, weight="bold")).pack(anchor="w")
        ctk.CTkLabel(head, text="Photograph a puzzle, check the digits that were read, then solve it yourself or let the backtracking solver do it.",
                     text_color=COL["muted"]).pack(anchor="w")

        # left: board
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=1, column=0, sticky="n", padx=(22, 12), pady=(0, 18))
        self.canvas = tk.Canvas(left, width=SIZE, height=SIZE, bg=COL["panel"], highlightthickness=0, cursor="hand2")
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self.on_click)

        pad = ctk.CTkFrame(left, fg_color="transparent")
        pad.pack(pady=(10, 0))
        for n in range(1, 10):
            b = self.btn(pad, str(n), lambda n=n: self.enter(n), width=100, height=42, font=ctk.CTkFont(size=17))
            b.grid(row=(n - 1) // 5, column=(n - 1) % 5, padx=3, pady=3)
        self.btn(pad, "Erase", lambda: self.enter(0), width=100, height=42).grid(row=1, column=4, padx=3, pady=3)

        self.status = ctk.CTkLabel(left, text="", wraplength=SIZE, justify="left", anchor="w", text_color=COL["muted"])
        self.status.pack(fill="x", pady=(10, 0))
        legend = ctk.CTkFrame(left, fg_color="transparent")
        legend.pack(anchor="w", pady=(6, 0))
        for text, color in [("clues", COL["given"]), ("your digits", COL["user"]),
                            ("solver / hints", COL["auto"]), ("solver trying", COL["trial"])]:
            ctk.CTkLabel(legend, text="● " + text, text_color=color, font=ctk.CTkFont(size=12)).pack(side="left", padx=(0, 12))

        # right: panels
        self.side = ctk.CTkScrollableFrame(self, fg_color="transparent", width=420)
        self.side.grid(row=1, column=1, sticky="nsew", padx=(0, 20), pady=(0, 18))

        scan = self.panel("Scan a puzzle")
        self.key_label = ctk.CTkLabel(scan, text="", text_color=COL["muted"], anchor="w", wraplength=380, justify="left")
        self.key_label.pack(fill="x", padx=16)
        self.refresh_key_label()
        ctk.CTkLabel(scan, text="Model", anchor="w").pack(fill="x", padx=16, pady=(10, 2))
        self.model_var = ctk.StringVar(value=load_env().get("GEMINI_MODEL") or DEFAULT_MODEL)
        ctk.CTkComboBox(scan, values=MODELS, variable=self.model_var, fg_color=COL["bg"],
                        border_color=COL["line"], button_color=COL["panel2"]).pack(fill="x", padx=16)
        self.scan_var = ctk.BooleanVar(value=cv2 is not None)
        ctk.CTkCheckBox(scan, text="Straighten photos first (scanner mode)", variable=self.scan_var,
                        fg_color=COL["accent"], state="normal" if cv2 is not None else "disabled").pack(anchor="w", padx=16, pady=(12, 0))
        row = ctk.CTkFrame(scan, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(10, 0))
        self.btn(row, "Take photo", self.open_camera, width=96).pack(side="left", padx=(0, 8))
        self.btn(row, "Choose photo", self.choose_photo, width=104).pack(side="left", padx=(0, 8))
        self.straighten_btn = self.btn(row, "Straighten", self.open_cropper, width=90, state="disabled")
        self.straighten_btn.pack(side="left")
        self.preview = ctk.CTkLabel(scan, text="")
        self.preview.pack(padx=16, pady=(10, 0))
        self.read_btn = self.btn(scan, "Read puzzle", self.read_puzzle, primary=True, state="disabled")
        self.read_btn.pack(anchor="w", padx=16, pady=(10, 16))

        mode = self.panel("Play")
        self.mode_title = mode.winfo_children()[0]
        self.mode_help = ctk.CTkLabel(mode, text="", text_color=COL["muted"], anchor="w", wraplength=380, justify="left")
        self.mode_help.pack(fill="x", padx=16)
        self.setup_row = ctk.CTkFrame(mode, fg_color="transparent")
        self.btn(self.setup_row, "Start playing", self.start_playing, primary=True).pack(side="left", padx=(0, 8))
        self.btn(self.setup_row, "Clear board", self.clear_board).pack(side="left")
        self.play_row = ctk.CTkFrame(mode, fg_color="transparent")
        self.notes_btn = self.btn(self.play_row, "Notes", self.toggle_notes, width=80)
        self.undo_btn = self.btn(self.play_row, "Undo", self.undo, width=80)
        for i, b in enumerate([
            self.notes_btn,
            self.btn(self.play_row, "Hint", self.hint, width=80),
            self.btn(self.play_row, "Check", self.check, width=80),
            self.undo_btn,
            self.btn(self.play_row, "Reset", self.reset_entries, width=80),
            self.btn(self.play_row, "Edit puzzle", self.edit_puzzle, width=100),
        ]):
            b.grid(row=i // 3, column=i % 3, padx=(0, 8), pady=(0, 8), sticky="w")

        solver = self.panel("Solver")
        ctk.CTkLabel(solver, text="Backtracking tries a digit in the most constrained empty cell, moves on, and steps back "
                                  "whenever a cell has no legal digit left.",
                     text_color=COL["muted"], anchor="w", wraplength=380, justify="left").pack(fill="x", padx=16)
        row = ctk.CTkFrame(solver, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(10, 0))
        self.solve_btn = self.btn(row, "Solve now", self.solve_now, primary=True)
        self.solve_btn.pack(side="left", padx=(0, 8))
        self.anim_btn = self.btn(row, "Show backtracking", self.solve_animated)
        self.anim_btn.pack(side="left", padx=(0, 8))
        self.stop_btn = self.btn(row, "Stop", lambda: self.stop_anim(False), width=70, state="disabled")
        self.stop_btn.pack(side="left")
        row = ctk.CTkFrame(solver, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(10, 16))
        ctk.CTkLabel(row, text="Speed").pack(side="left", padx=(0, 10))
        self.speed = ctk.CTkSlider(row, from_=0, to=4, number_of_steps=4, button_color=COL["accent"],
                                   progress_color=COL["accent"])
        self.speed.set(2)
        self.speed.pack(side="left", fill="x", expand=True)

    # ---------------------------------------------------------------- helpers
    def post(self, fn):
        self.q.put(fn)

    def poll(self):
        try:
            while True:
                self.q.get_nowait()()
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def set_status(self, msg, kind=""):
        color = {"ok": COL["auto"], "err": COL["bad"]}.get(kind, COL["muted"])
        self.status.configure(text=msg, text_color=color)

    def refresh_key_label(self):
        if get_key():
            self.key_label.configure(text="API key: found (.env). Photos are sent to Google's Gemini API.")
        else:
            self.key_label.configure(text="API key: not set. Add GEMINI_API_KEY to a .env file next to this script, "
                                          "or you'll be asked for it when you press Read puzzle.")

    def shown(self, i):
        if self.anim:
            return self.given[i] or self.anim["grid"][i]
        return self.given[i] or self.cur[i]

    def conflicts(self):
        bad = set()
        for i in range(81):
            v = self.shown(i)
            if v and any(self.shown(j) == v for j in PEERS[i]):
                bad.add(i)
        return bad

    def update_controls(self):
        busy = self.anim is not None
        self.stop_btn.configure(state="normal" if busy else "disabled")
        self.solve_btn.configure(state="disabled" if busy else "normal")
        self.anim_btn.configure(state="disabled" if busy else "normal")
        self.undo_btn.configure(state="normal" if self.undo_stack and not busy else "disabled")

    # ---------------------------------------------------------------- drawing
    def draw(self):
        cv = self.canvas
        cv.delete("all")
        bad = self.conflicts()
        sv = self.shown(self.sel) if self.sel >= 0 else 0
        digit_font = ("Segoe UI", 24, "bold")
        user_font = ("Segoe UI", 24)
        note_font = ("Segoe UI", 9)
        for i in range(81):
            r, c = divmod(i, 9)
            x0, y0 = PAD + c * CELL, PAD + r * CELL
            val = self.shown(i)
            fill = COL["panel"]
            if self.sel >= 0:
                if i == self.sel:
                    fill = COL["sel"]
                elif val and val == sv:
                    fill = COL["same"]
                elif i in PEERSETS[self.sel]:
                    fill = COL["peer"]
            cv.create_rectangle(x0, y0, x0 + CELL, y0 + CELL, fill=fill, outline="")
            flagged = i in bad or i in self.wrong
            if flagged:
                cv.create_rectangle(x0 + 3, y0 + 3, x0 + CELL - 3, y0 + CELL - 3, outline=COL["bad"], width=2)
            if val and not (self.given[i] and r + c > self.reveal):
                if flagged:
                    color = COL["bad"]
                elif self.given[i]:
                    color = COL["given"]
                elif self.anim:
                    color = COL["trial"]
                elif self.auto[i]:
                    color = COL["auto"]
                else:
                    color = COL["user"]
                cv.create_text(x0 + CELL / 2, y0 + CELL / 2, text=str(val), fill=color,
                               font=digit_font if self.given[i] else user_font)
            elif not val and not self.anim and self.notes[i]:
                for k in range(9):
                    if self.notes[i] >> k & 1:
                        cv.create_text(x0 + (k % 3 + 0.5) * CELL / 3, y0 + (k // 3 + 0.5) * CELL / 3,
                                       text=str(k + 1), fill=COL["muted"], font=note_font)
        for k in range(10):
            thick = k % 3 == 0
            color = COL["strong"] if thick else COL["line"]
            w = 3 if thick else 1
            p = PAD + k * CELL
            cv.create_line(PAD, p, PAD + 9 * CELL, p, fill=color, width=w)
            cv.create_line(p, PAD, p, PAD + 9 * CELL, fill=color, width=w)
        self.update_controls()

    # ---------------------------------------------------------------- modes and input
    def set_mode(self, m):
        self.mode = m
        if m == "setup":
            self.play_row.pack_forget()
            self.setup_row.pack(fill="x", padx=16, pady=(10, 16))
            self.mode_title.configure(text="Check the puzzle")
            self.mode_help.configure(text="Click a cell and type to fix any digit that was misread. "
                                          "You can also type a puzzle in by hand.")
        else:
            self.setup_row.pack_forget()
            self.play_row.pack(fill="x", padx=16, pady=(10, 6))
            self.mode_title.configure(text="Play")
            self.mode_help.configure(text="Click a cell, then use the number pad or keyboard. Turn on Notes for pencil marks.")
        self.draw()

    def on_click(self, e):
        c, r = (e.x - PAD) // CELL, (e.y - PAD) // CELL
        if 0 <= r < 9 and 0 <= c < 9:
            self.sel = r * 9 + c
            self.canvas.focus_set()
            self.draw()

    def on_key(self, e):
        try:
            if isinstance(self.focus_get(), tk.Entry):
                return
        except KeyError:
            pass
        if e.char and e.char in "123456789":
            self.enter(int(e.char))
        elif e.char == "0" or e.keysym in ("BackSpace", "Delete"):
            self.enter(0)
        elif e.keysym in ("Up", "Down", "Left", "Right"):
            if self.sel < 0:
                self.sel = 0
            else:
                r, c = divmod(self.sel, 9)
                if e.keysym == "Up":
                    r = (r + 8) % 9
                elif e.keysym == "Down":
                    r = (r + 1) % 9
                elif e.keysym == "Left":
                    c = (c + 8) % 9
                else:
                    c = (c + 1) % 9
                self.sel = r * 9 + c
            self.draw()
        elif e.char in ("n", "N") and self.mode == "play":
            self.toggle_notes()

    def push_undo(self):
        self.undo_stack.append((self.cur[:], self.notes[:], self.auto[:]))
        if len(self.undo_stack) > 300:
            self.undo_stack.pop(0)

    def enter(self, d):
        if self.anim or self.sel < 0:
            return
        s = self.sel
        if self.mode == "setup":
            self.given[s] = d
            self.solution_cache = None
            self.wrong.clear()
            self.draw()
            return
        if self.given[s]:
            return
        if d and self.notes_on:
            if self.cur[s]:
                return
            self.push_undo()
            self.notes[s] ^= 1 << (d - 1)
            self.draw()
            return
        self.push_undo()
        self.wrong.clear()
        if d == 0:
            self.cur[s], self.notes[s], self.auto[s] = 0, 0, False
        else:
            self.cur[s], self.auto[s], self.notes[s] = d, False, 0
            for j in PEERS[s]:
                self.notes[j] &= ~(1 << (d - 1))
        self.draw()
        self.check_complete()

    def check_complete(self):
        if all(self.shown(i) for i in range(81)) and not self.conflicts():
            self.set_status("Solved! Every row, column and box is complete.", "ok")

    def undo(self):
        if not self.undo_stack or self.anim:
            return
        self.cur, self.notes, self.auto = (list(x) for x in self.undo_stack.pop())
        self.wrong.clear()
        self.draw()

    def toggle_notes(self):
        self.notes_on = not self.notes_on
        self.notes_btn.configure(fg_color=COL["sel"] if self.notes_on else COL["panel2"],
                                 border_color=COL["accent"] if self.notes_on else COL["line"])

    # ---------------------------------------------------------------- solving
    def need_clues(self):
        if not any(self.given):
            self.set_status("Scan or type a puzzle first.", "err")
            return True
        return False

    def no_solution_message(self, r):
        if r.get("conflict"):
            return "Some clues clash with each other (shown in red). A digit was probably misread — fix it and try again."
        if r.get("aborted"):
            return "The solver gave up after a very long search. Check the clues for a misread digit."
        return "These clues have no solution. A digit was probably misread — compare the board with your photo and fix it."

    def with_solution(self, cb):
        """Run the fast solver in a worker thread (cached), then call cb(result) on the UI thread."""
        if self.solution_cache is not None:
            cb(self.solution_cache)
            return
        if self.solving:
            return
        self.solving = True
        self.set_status("Checking the puzzle…")
        snapshot = list(self.given)

        def work():
            r = count_solutions(snapshot, 2)

            def done():
                self.solving = False
                if snapshot != self.given:
                    return
                self.solution_cache = r
                cb(r)
            self.post(done)

        threading.Thread(target=work, daemon=True).start()

    def fill_from_solution(self, sol):
        self.push_undo()
        self.wrong.clear()
        for i in range(81):
            if not self.given[i]:
                if self.cur[i] != sol[i]:
                    self.cur[i] = sol[i]
                    self.auto[i] = True
                self.notes[i] = 0

    def solve_now(self):
        if self.anim or self.need_clues():
            return
        if self.mode == "setup":
            self.set_mode("play")

        def cb(r):
            if not r["solution"]:
                self.set_status(self.no_solution_message(r), "err")
                self.draw()
                return
            self.fill_from_solution(r["solution"])
            self.draw()
            if r["count"] > 1:
                self.set_status("Solved, but this grid has more than one solution — a clue may have been missed in the scan.")
            else:
                self.set_status("Solved. This puzzle has exactly one solution.", "ok")
        self.with_solution(cb)

    def solve_animated(self):
        if self.anim or self.need_clues():
            return
        if self.mode == "setup":
            self.set_mode("play")
        g = list(self.given)
        m = make_masks(g)
        if m is None:
            self.set_status(self.no_solution_message({"conflict": True}), "err")
            self.draw()
            return
        self.anim = {"grid": list(self.given), "it": search(g, m), "steps": 0, "job": None}
        self.tick()

    def tick(self):
        a = self.anim
        if not a:
            return
        per, delay = SPEEDS[int(round(self.speed.get()))]
        for _ in range(per):
            try:
                i, v = next(a["it"])
            except StopIteration as stop:
                ok, steps, grid = stop.value, a["steps"], a["grid"]
                self.anim = None
                if ok:
                    self.fill_from_solution(grid)
                    self.set_status(f"Solved by backtracking in {steps:,} steps.", "ok")
                else:
                    self.set_status(self.no_solution_message({}), "err")
                self.draw()
                return
            a["grid"][i] = v
            a["steps"] += 1
        self.draw()
        self.set_status(f"Backtracking… {a['steps']:,} steps")
        a["job"] = self.after(delay, self.tick)

    def stop_anim(self, silent):
        if not self.anim:
            return
        if self.anim["job"]:
            self.after_cancel(self.anim["job"])
        self.anim = None
        self.draw()
        if not silent:
            self.set_status("Stopped. The board is back to your own entries.")

    # ---------------------------------------------------------------- play actions
    def start_playing(self):
        if self.need_clues():
            return
        if self.conflicts():
            self.set_status("Fix the clues shown in red first.", "err")
            return

        def cb(r):
            if not r["solution"]:
                self.set_status(self.no_solution_message(r), "err")
                return
            self.set_mode("play")
            if r["count"] > 1:
                self.set_status("Ready. Note: this grid has more than one solution, so a clue may be missing.")
            else:
                self.set_status("Ready. Pick a cell and enter a digit.", "ok")
        self.with_solution(cb)

    def edit_puzzle(self):
        if any(self.cur) and not messagebox.askyesno("Edit puzzle", "Go back to editing the clues? Your entries will be cleared."):
            return
        self.stop_anim(True)
        self.reset_progress()
        self.set_mode("setup")
        self.set_status("Editing clues.")

    def reset_progress(self):
        self.cur = [0] * 81
        self.notes = [0] * 81
        self.auto = [False] * 81
        self.wrong.clear()
        self.undo_stack = []

    def reset_entries(self):
        self.push_undo()
        self.cur = [0] * 81
        self.notes = [0] * 81
        self.auto = [False] * 81
        self.wrong.clear()
        self.draw()
        self.set_status("Entries cleared. Undo brings them back.")

    def clear_board(self):
        if any(self.given) and not messagebox.askyesno("Clear board", "Clear the whole board?"):
            return
        self.given = [0] * 81
        self.reset_progress()
        self.solution_cache = None
        self.sel = -1
        self.draw()
        self.set_status("Board cleared.")

    def hint(self):
        if self.anim:
            return

        def cb(r):
            if not r["solution"]:
                self.set_status(self.no_solution_message(r), "err")
                return
            sol = r["solution"]
            if self.sel >= 0 and not self.given[self.sel] and self.cur[self.sel] != sol[self.sel]:
                t = self.sel
            else:
                open_cells = [i for i in range(81) if not self.given[i] and self.cur[i] != sol[i]]
                if not open_cells:
                    self.set_status("Nothing left to reveal — the board matches the solution.")
                    return
                import random
                t = random.choice(open_cells)
            self.push_undo()
            self.wrong.clear()
            self.cur[t], self.auto[t], self.notes[t] = sol[t], True, 0
            for j in PEERS[t]:
                self.notes[j] &= ~(1 << (sol[t] - 1))
            self.sel = t
            self.draw()
            self.set_status(f"Revealed row {t // 9 + 1}, column {t % 9 + 1}.")
            self.check_complete()
        self.with_solution(cb)

    def check(self):
        if self.anim:
            return

        def cb(r):
            if not r["solution"]:
                self.set_status(self.no_solution_message(r), "err")
                return
            self.wrong = {i for i in range(81) if not self.given[i] and self.cur[i] and self.cur[i] != r["solution"][i]}
            self.draw()
            if self.wrong:
                n = len(self.wrong)
                self.set_status(f"{n} of your digits {'does not' if n == 1 else 'do not'} match the solution (outlined in red).", "err")
            else:
                self.set_status("Everything you have entered so far is correct.", "ok")
        self.with_solution(cb)

    # ---------------------------------------------------------------- photo -> grid
    def choose_photo(self):
        path = filedialog.askopenfilename(
            title="Choose a Sudoku photo",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff"), ("All files", "*.*")])
        if not path:
            return
        try:
            self.load_source(Image.open(path))
        except Exception:
            self.set_status("That file could not be opened as an image.", "err")

    def open_camera(self):
        if cv2 is None:
            messagebox.showinfo("Webcam needs OpenCV", "Install it with:\n\npip install opencv-python\n\n"
                                "Or use “Choose photo” with a picture from your phone.")
            return
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(0)
        if not cap.isOpened():
            messagebox.showerror("Webcam", "Could not open the webcam. Is another app using it?")
            return
        win = CameraWindow(self, cap, self.load_source)
        win.transient(self)

    def load_source(self, pil):
        """A new photo arrived: remember the original, then straighten it (or use as is)."""
        self.original = ImageOps.exif_transpose(pil).convert("RGB")
        self.straighten_btn.configure(state="normal" if cv2 is not None else "disabled")
        if cv2 is not None and self.scan_var.get():
            self.open_cropper()
        else:
            self.use_photo(self.original)
            if cv2 is None:
                self.set_status("Photo ready. Install opencv-python to enable scanner-style straightening.")

    def open_cropper(self):
        if self.original is None or cv2 is None:
            return
        CropWindow(self, self.original, self.use_photo).transient(self)

    def use_photo(self, pil):
        self.photo_pil = pil
        thumb = self.photo_pil.copy()
        thumb.thumbnail((360, 220))
        self.preview_img = ctk.CTkImage(thumb, size=thumb.size)
        self.preview.configure(image=self.preview_img)
        self.read_btn.configure(state="normal")
        self.set_status("Photo ready. Press “Read puzzle”.")

    def ensure_key(self):
        key = get_key()
        if key:
            return key
        key = (ctk.CTkInputDialog(text="Paste your Google AI Studio API key:", title="API key").get_input() or "").strip()
        if not key:
            return ""
        if messagebox.askyesno("Save key", "Save it to a .env file next to this script so you don't have to paste it again?"):
            save_key(key)
        os.environ["GEMINI_API_KEY"] = key
        self.refresh_key_label()
        return key

    def read_puzzle(self):
        if self.photo_pil is None:
            return
        key = self.ensure_key()
        if not key:
            self.set_status("An API key is needed to read the photo.", "err")
            return
        model = self.model_var.get().strip() or DEFAULT_MODEL
        self.read_btn.configure(state="disabled", text="Reading…")
        self.set_status("Reading the grid…")
        pil = self.photo_pil

        def work():
            try:
                grid = ask_gemini(key, model, encode_jpeg(pil))
                self.post(lambda: self.read_done(grid, None))
            except GeminiError as e:
                msg = str(e)
                self.post(lambda: self.read_done(None, msg))
            except Exception as e:  # unexpected
                msg = f"Unexpected error: {e}"
                self.post(lambda: self.read_done(None, msg))

        threading.Thread(target=work, daemon=True).start()

    def read_done(self, grid, err):
        self.read_btn.configure(state="normal", text="Read puzzle")
        if err:
            self.set_status(err, "err")
            return
        self.stop_anim(True)
        self.reset_progress()
        self.given = grid
        self.solution_cache = None
        self.sel = -1
        self.set_mode("setup")
        self.set_status("Puzzle read. Compare it with your photo, fix any wrong digit, then press “Start playing”.", "ok")
        self.reveal = -1
        self.reveal_step()

    def reveal_step(self):
        """Digits settle in along a diagonal wave."""
        self.reveal += 1
        self.draw()
        if self.reveal < 17:
            self.after(35, self.reveal_step)
        else:
            self.reveal = 99


if __name__ == "__main__":
    App().mainloop()