"""
Sprite Animator  v4.0 — Standalone Sprite Sheet Tool
─────────────────────────────────────────────────────
Usage:
    python sprite_animator.py [image_path]
    Drag-drop a PNG onto the window to load.

Keyboard shortcuts:
    Space       Play / Pause
    Left/Right  Step frame
    Up/Down     FPS +/- 5
    R           Reset to range start
    O           Open file
    G           Export GIF
    W           Export WebP
    P           Export PNG sequence
    J           Export Atlas JSON
    N           Toggle onion skin
    B           Cycle background
    F           Zoom to fit
    T           Trim/auto-crop
    D           Find duplicates
    C           Compare (load 2nd sheet)
    H           Flip horizontal
    V           Flip vertical
    1/2/3/4     Pixel scale 1x/2x/3x/4x
    Ctrl+Z      Undo reorder/delete
    Del         Delete frame from sequence
    Esc         Quit
"""

import sys, os, json, math, hashlib, copy, time
import pygame
from pygame.locals import *

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import tkinter as tk
    from tkinter import filedialog, colorchooser
    HAS_TK = True
except ImportError:
    HAS_TK = False

# ── palette ───────────────────────────────────────────────────────────────────
BG        = (28,  28,  38)
PANEL_BG  = (20,  20,  30)
ACCENT    = (90, 170, 255)
ACCENT2   = (130, 100, 255)
TEXT      = (220, 220, 230)
TEXT_DIM  = (110, 110, 130)
HIGHLIGHT = (255, 200,  70)
BTN_BG    = (45,  50,  70)
BTN_HOV   = (60,  68,  98)
CHK_A     = (55,  55,  65)
CHK_B     = (42,  42,  52)
RED       = (220,  65,  65)
GREEN     = ( 70, 200, 100)
ORANGE    = (255, 160,  40)
PURPLE    = (180, 100, 255)
CYAN      = ( 60, 210, 220)
YELLOW    = (240, 220,  60)

PANEL_W   = 310
MIN_W     = 1024
MIN_H     = 680
STRIP_H   = 72

PLAY_MODES = ["Loop", "Once", "Ping-Pong"]
BG_MODES   = ["Checker", "Black", "White", "Custom"]
TABS       = ["Grid", "Play", "Export", "Analyze", "Tools", "Anim"]

# ── helpers ───────────────────────────────────────────────────────────────────
def draw_text(surf, font, text, pos, colour=TEXT, anchor="topleft"):
    s = font.render(str(text), True, colour)
    r = s.get_rect(**{anchor: pos})
    surf.blit(s, r)
    return r

def draw_rect_aa(surf, colour, rect, radius=5, width=0):
    pygame.draw.rect(surf, colour, rect, width, border_radius=radius)

def draw_button(surf, font, rect, label, hovered=False, active=False,
                accent=ACCENT):
    bg = accent if active else (BTN_HOV if hovered else BTN_BG)
    draw_rect_aa(surf, bg, rect)
    draw_rect_aa(surf, accent, rect, width=1)
    draw_text(surf, font, label, rect.center, TEXT, anchor="center")

def checker(surf, rect, size=12):
    for gy in range(rect.h // size + 2):
        for gx in range(rect.w // size + 2):
            c = CHK_A if (gx + gy) % 2 == 0 else CHK_B
            r = pygame.Rect(rect.x + gx*size, rect.y + gy*size, size, size)
            r = r.clip(rect)
            if r.width > 0 and r.height > 0:
                pygame.draw.rect(surf, c, r)

def sep(surf, x, y, w, colour=BTN_BG):
    pygame.draw.line(surf, colour, (x, y), (x+w, y))

def open_file(title="Open sprite sheet"):
    if not HAS_TK: return None
    root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
    p = filedialog.askopenfilename(
        title=title,
        filetypes=[("Images", "*.png *.jpg *.bmp"), ("All", "*.*")])
    root.destroy()
    return p or None

def open_folder(title="Select folder"):
    if not HAS_TK: return None
    root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
    p = filedialog.askdirectory(title=title)
    root.destroy()
    return p or None

def pick_color(initial=(80, 80, 80)):
    if not HAS_TK: return initial
    root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
    r = colorchooser.askcolor(color=initial, title="Pick colour")
    root.destroy()
    if r and r[0]: return tuple(int(x) for x in r[0])
    return initial

def ask_string(title, prompt, initial=""):
    if not HAS_TK: return initial
    root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
    from tkinter.simpledialog import askstring
    val = askstring(title, prompt, initialvalue=initial, parent=root)
    root.destroy()
    return val

def surf_to_pil(surf):
    raw = pygame.image.tobytes(surf, "RGBA")
    return Image.frombytes("RGBA", surf.get_size(), raw)

def frame_hash(surf):
    return hashlib.md5(pygame.image.tobytes(surf, "RGBA")).hexdigest()

def find_trim_rect(surf):
    w, h = surf.get_size()
    min_x, min_y, max_x, max_y = w, h, 0, 0
    arr = pygame.surfarray.pixels_alpha(surf)
    for x in range(w):
        for y in range(h):
            if arr[x][y] > 10:
                min_x = min(min_x, x); min_y = min(min_y, y)
                max_x = max(max_x, x); max_y = max(max_y, y)
    del arr
    if max_x < min_x: return pygame.Rect(0, 0, w, h)
    return pygame.Rect(min_x, min_y, max_x - min_x + 1, max_y - min_y + 1)


# ── integer spin-box ──────────────────────────────────────────────────────────
class IntInput:
    def __init__(self, label, value, lo, hi, step=1):
        self.label = label
        self.value = value
        self.lo, self.hi, self.step = lo, hi, step
        self.active = False
        self._buf   = str(value)
        self._rect = self._plus = self._minus = pygame.Rect(0,0,0,0)

    def handle(self, ev):
        if not self.active or ev.type != KEYDOWN: return
        if ev.key in (K_RETURN, K_ESCAPE): self._commit()
        elif ev.key == K_BACKSPACE:        self._buf = self._buf[:-1]
        elif ev.unicode.lstrip("-").isdigit(): self._buf += ev.unicode

    def _commit(self):
        try: self.value = max(self.lo, min(self.hi, int(self._buf)))
        except ValueError: pass
        self._buf = str(self.value); self.active = False

    def click(self, mx, my):
        if self._rect.collidepoint(mx, my):
            self.active = True; self._buf = str(self.value); return True
        if self._plus.collidepoint(mx, my):
            self.value = min(self.hi, self.value + self.step)
            self._buf = str(self.value); return True
        if self._minus.collidepoint(mx, my):
            self.value = max(self.lo, self.value - self.step)
            self._buf = str(self.value); return True
        if self.active: self._commit()
        return False

    def draw(self, surf, font, x, y, w=PANEL_W - 28):
        draw_text(surf, font, self.label + ":", (x, y), TEXT_DIM)
        y += 20
        bw = 26
        fw = w - bw * 2 - 8
        self._minus = pygame.Rect(x,              y, bw, 26)
        self._rect  = pygame.Rect(x + bw + 4,     y, fw, 26)
        self._plus  = pygame.Rect(x + bw + fw + 8,y, bw, 26)
        for r, lbl in [(self._minus,"-"),(self._plus,"+")]:
            draw_rect_aa(surf, BTN_BG, r)
            draw_text(surf, font, lbl, r.center, TEXT, "center")
        border = ACCENT if self.active else TEXT_DIM
        draw_rect_aa(surf, BTN_BG, self._rect)
        draw_rect_aa(surf, border, self._rect, width=1)
        buf = self._buf if self.active else str(self.value)
        draw_text(surf, font, buf, self._rect.center,
                  HIGHLIGHT if self.active else TEXT, "center")
        return y + 34


# ── animation state ──────────────────────────────────────────────────────────
class AnimState:
    """A named animation clip with frame range and per-frame timing."""
    def __init__(self, name, start, end, fps=12):
        self.name  = name
        self.start = start
        self.end   = end
        self.fps   = fps
        self.frame_durations = {}  # frame_idx -> ms override (empty = uniform)

    def to_dict(self):
        d = {"name": self.name, "start": self.start, "end": self.end, "fps": self.fps}
        if self.frame_durations:
            d["frame_durations"] = {str(k): v for k, v in self.frame_durations.items()}
        return d


# ── main app ──────────────────────────────────────────────────────────────────
class SpriteAnimator:
    def __init__(self, path=None):
        pygame.init()
        pygame.display.set_caption("Sprite Animator  v4.0")
        self.screen = pygame.display.set_mode((MIN_W, MIN_H), RESIZABLE)
        self.clock  = pygame.time.Clock()

        self.font_sm = pygame.font.SysFont("segoeui", 13)
        self.font    = pygame.font.SysFont("segoeui", 15)
        self.font_b  = pygame.font.SysFont("segoeui", 15, bold=True)
        self.font_lg = pygame.font.SysFont("segoeui", 19, bold=True)

        # sheet state
        self.sheet      = None
        self.sheet_path = None

        # grid inputs
        self.cols_inp   = IntInput("Columns",      4,  1, 64)
        self.rows_inp   = IntInput("Rows",         8,  1, 64)
        self.frames_inp = IntInput("Total frames", 29, 1, 999)
        self.fps_inp    = IntInput("FPS",          12, 1, 120)
        self.start_inp  = IntInput("Range start",  0,  0, 998)
        self.end_inp    = IntInput("Range end",    28, 0, 998)
        self._grid_inputs     = [self.cols_inp, self.rows_inp, self.frames_inp]
        self._playback_inputs = [self.fps_inp, self.start_inp, self.end_inp]

        # playback
        self.frame       = 0
        self.playing     = True
        self.acc         = 0.0
        self.direction   = 1
        self.play_mode   = 0
        self.done_once   = False

        # view
        self.zoom        = 1.0
        self.pixel_scale = 0          # 0=free zoom, 1=1x, 2=2x, 3=3x, 4=4x
        self.onion       = False
        self.bg_mode     = 0
        self.bg_custom   = (80, 60, 100)
        self.show_grid   = False      # pixel grid overlay

        # flip
        self.flip_h      = False
        self.flip_v      = False

        # atlas prefix
        self.sprite_prefix = "sprite_"

        # analysis
        self._palette       = []
        self._palette_frame = -1
        self._duplicates    = set()
        self._dupes_hash    = ""

        # trim
        self._trim_rects    = []
        self._trim_computed = False
        self._trim_union    = None

        # frame reorder
        self._frame_order   = []
        self._undo_stack    = []

        # hitbox / origin
        self._origins       = {}
        self._hitboxes      = {}
        self._editing_hitbox = False
        self._hb_start      = None

        # palette swap
        self._remap_from    = None
        self._remap_to      = None
        self._sheet_backup  = None   # for undo palette swap

        # compare
        self.compare_sheet  = None
        self.compare_path   = None
        self.compare_frame  = 0
        self.show_compare   = False

        # animation states
        self.anim_states    = []       # list of AnimState
        self.active_anim    = -1       # index into anim_states, -1 = manual
        self._anim_scroll   = 0

        # background sprite preview
        self.bg_sprite      = None
        self.bg_sprite_path = None

        # project file
        self.project_path   = None

        # recent files
        self._recent_file   = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".recent")
        self.recent_files   = self._load_recent()

        # UI
        self.active_tab  = 0
        self._msg        = ""
        self._msg_timer  = 0.0
        self._msg_err    = False
        self._all_btns   = {}

        if path:
            self.load(path)

    # ── recent files ─────────────────────────────────────────────────────────
    def _load_recent(self):
        try:
            if os.path.exists(self._recent_file):
                with open(self._recent_file, "r") as f:
                    return [l.strip() for l in f if l.strip() and os.path.exists(l.strip())][:8]
        except Exception:
            pass
        return []

    def _save_recent(self, path):
        path = os.path.abspath(path)
        self.recent_files = [p for p in self.recent_files if p != path]
        self.recent_files.insert(0, path)
        self.recent_files = self.recent_files[:8]
        try:
            with open(self._recent_file, "w") as f:
                f.write("\n".join(self.recent_files))
        except Exception:
            pass

    # ── loading ───────────────────────────────────────────────────────────────
    def load(self, path):
        try:
            self.sheet      = pygame.image.load(path).convert_alpha()
            self.sheet_path = path
            self.frame = 0; self.acc = 0; self.direction = 1; self.done_once = False
            self._palette = []; self._palette_frame = -1
            self._duplicates = set(); self._trim_rects = []
            self._trim_computed = False; self._trim_union = None
            self._frame_order = []; self._undo_stack = []
            self._origins = {}; self._hitboxes = {}
            self.anim_states = []; self.active_anim = -1
            self.flip_h = False; self.flip_v = False
            self._sheet_backup = None
            self._save_recent(path)
            w, h = self.sheet.get_size()
            self.end_inp.value = self.total_frames - 1
            self.end_inp._buf  = str(self.end_inp.value)
            self.zoom_to_fit()
            fw, fh = self.frame_size
            self.show_msg(f"Loaded {w}x{h}  |  frame {fw}x{fh}")
        except Exception as ex:
            self.show_msg(f"{ex}", error=True)

    def show_msg(self, text, error=False):
        self._msg = text; self._msg_timer = 4.0; self._msg_err = error

    # ── geometry ──────────────────────────────────────────────────────────────
    @property
    def frame_size(self):
        if not self.sheet: return (64, 64)
        w, h = self.sheet.get_size()
        return w // max(1, self.cols_inp.value), h // max(1, self.rows_inp.value)

    def frame_rect(self, idx):
        fw, fh = self.frame_size
        c = idx % max(1, self.cols_inp.value)
        r = idx // max(1, self.cols_inp.value)
        return pygame.Rect(c * fw, r * fh, fw, fh)

    @property
    def total_frames(self):
        return min(self.frames_inp.value,
                   self.cols_inp.value * self.rows_inp.value)

    @property
    def range_start(self):
        return max(0, min(self.start_inp.value, self.total_frames - 1))

    @property
    def range_end(self):
        return max(self.range_start,
                   min(self.end_inp.value, self.total_frames - 1))

    def get_actual(self, logical):
        if self._frame_order and 0 <= logical < len(self._frame_order):
            return self._frame_order[logical]
        return logical

    @property
    def display_total(self):
        return len(self._frame_order) if self._frame_order else self.total_frames

    def zoom_to_fit(self):
        if not self.sheet: return
        sw, sh = self.screen.get_size()
        vw, vh = sw - PANEL_W, sh - STRIP_H - 20
        fw, fh = self.frame_size
        if fw == 0 or fh == 0: return
        self.zoom = max(0.1, min(vw / fw, vh / fh) * 0.85)
        self.pixel_scale = 0

    def get_frame_surface(self, logical_idx):
        """Get frame surface with flip applied."""
        actual = self.get_actual(logical_idx)
        sub = self.sheet.subsurface(self.frame_rect(actual)).copy()
        if self.flip_h or self.flip_v:
            sub = pygame.transform.flip(sub, self.flip_h, self.flip_v)
        return sub

    # ── update ────────────────────────────────────────────────────────────────
    def update(self, dt):
        if self._msg_timer > 0: self._msg_timer -= dt
        if not (self.playing and self.sheet): return

        # Per-frame duration from active anim state
        anim = self.anim_states[self.active_anim] if 0 <= self.active_anim < len(self.anim_states) else None
        if anim and self.frame in anim.frame_durations:
            interval = anim.frame_durations[self.frame] / 1000.0
        else:
            interval = 1.0 / max(1, self.fps_inp.value)

        self.acc += dt
        max_f = self.display_total - 1

        while self.acc >= interval:
            self.acc -= interval
            rs, re = self.range_start, min(self.range_end, max_f)

            if self.play_mode == 1:
                if not self.done_once:
                    self.frame += 1
                    if self.frame > re:
                        self.frame = re; self.done_once = True; self.playing = False
            elif self.play_mode == 2:
                self.frame += self.direction
                if self.frame >= re:   self.frame = re;  self.direction = -1
                elif self.frame <= rs: self.frame = rs;  self.direction =  1
            else:
                self.frame += 1
                if self.frame > re: self.frame = rs

    # ── exports ───────────────────────────────────────────────────────────────
    def _collect_pil_frames(self, trim=False):
        frames = []
        for i in range(self.range_start, self.range_end + 1):
            sub = self.get_frame_surface(i)
            if trim and self._trim_computed:
                actual = self.get_actual(i)
                if actual < len(self._trim_rects):
                    sub = sub.subsurface(self._trim_rects[actual])
            frames.append(surf_to_pil(sub))
        return frames

    def export_gif(self):
        if not HAS_PIL:
            self.show_msg("pip install Pillow", error=True); return
        if not self.sheet_path:
            self.show_msg("No sheet loaded", error=True); return
        frames = self._collect_pil_frames(trim=self._trim_computed)
        dur = max(20, int(1000 / max(1, self.fps_inp.value)))
        out = os.path.splitext(self.sheet_path)[0] + ".gif"
        frames[0].save(out, save_all=True, append_images=frames[1:],
                       loop=0, duration=dur, disposal=2, optimize=False)
        self.show_msg(f"GIF -> {os.path.basename(out)}  ({len(frames)}f, {dur}ms)")

    def export_webp(self):
        if not HAS_PIL:
            self.show_msg("pip install Pillow", error=True); return
        if not self.sheet_path:
            self.show_msg("No sheet loaded", error=True); return
        frames = self._collect_pil_frames(trim=self._trim_computed)
        dur = max(1, int(1000 / max(1, self.fps_inp.value)))
        out = os.path.splitext(self.sheet_path)[0] + ".webp"
        frames[0].save(out, save_all=True, append_images=frames[1:],
                       loop=0, duration=dur, lossless=True)
        self.show_msg(f"WebP -> {os.path.basename(out)}")

    def export_png_seq(self):
        if not self.sheet_path:
            self.show_msg("No sheet loaded", error=True); return
        folder = os.path.splitext(self.sheet_path)[0] + "_frames"
        os.makedirs(folder, exist_ok=True)
        count = 0
        for i in range(self.range_start, self.range_end + 1):
            sub = self.get_frame_surface(i)
            if self._trim_computed:
                actual = self.get_actual(i)
                if actual < len(self._trim_rects):
                    sub = sub.subsurface(self._trim_rects[actual])
            pygame.image.save(sub, os.path.join(folder, f"frame_{i:03d}.png"))
            count += 1
        self.show_msg(f"PNG seq -> {os.path.basename(folder)}/  ({count} files)")

    def export_atlas(self):
        if not self.sheet_path:
            self.show_msg("No sheet loaded", error=True); return
        fw, fh = self.frame_size
        sprites = []
        prefix = self.sprite_prefix
        for i in range(self.display_total):
            actual = self.get_actual(i)
            r = self.frame_rect(actual)
            entry = {"name": f"{prefix}{i}", "x": r.x, "y": r.y, "w": fw, "h": fh}
            if self._trim_computed and actual < len(self._trim_rects):
                tr = self._trim_rects[actual]
                entry["trim"] = {"x": tr.x, "y": tr.y, "w": tr.w, "h": tr.h}
            if i in self._origins:
                entry["origin"] = {"x": self._origins[i][0], "y": self._origins[i][1]}
            if i in self._hitboxes:
                hx, hy, hw, hh = self._hitboxes[i]
                entry["hitbox"] = {"x": hx, "y": hy, "w": hw, "h": hh}
            sprites.append(entry)
        data = {"image": os.path.basename(self.sheet_path), "sprites": sprites}
        if self.anim_states:
            data["animations"] = [a.to_dict() for a in self.anim_states]
        if self.flip_h: data["flip_h"] = True
        if self.flip_v: data["flip_v"] = True
        out = os.path.splitext(self.sheet_path)[0] + "_atlas.json"
        with open(out, "w") as f:
            json.dump(data, f, indent=2)
        self.show_msg(f"Atlas -> {os.path.basename(out)}  ({len(sprites)} sprites)")

    def export_packed(self):
        if not self.sheet_path:
            self.show_msg("No sheet loaded", error=True); return
        fw, fh = self.frame_size
        n = self.display_total
        cols = max(1, math.ceil(math.sqrt(n)))
        rows = max(1, math.ceil(n / cols))
        use_trim = self._trim_computed
        tw, th = (self._trim_union.w, self._trim_union.h) if use_trim and self._trim_union else (fw, fh)
        atlas = pygame.Surface((cols * tw, rows * th), pygame.SRCALPHA)
        atlas.fill((0, 0, 0, 0))
        sprites = []
        for i in range(n):
            sub = self.get_frame_surface(i)
            if use_trim:
                actual = self.get_actual(i)
                if actual < len(self._trim_rects):
                    sub = sub.subsurface(self._trim_rects[actual])
            dx, dy = (i % cols) * tw, (i // cols) * th
            atlas.blit(sub, (dx, dy))
            sprites.append({"name": f"{self.sprite_prefix}{i}", "x": dx, "y": dy,
                             "w": sub.get_width(), "h": sub.get_height()})
        base = os.path.splitext(self.sheet_path)[0]
        pygame.image.save(atlas, base + "_packed.png")
        with open(base + "_packed.json", "w") as f:
            json.dump({"image": os.path.basename(base + "_packed.png"),
                       "sprites": sprites}, f, indent=2)
        self.show_msg(f"Packed -> {cols*tw}x{rows*th}")

    def export_anim_json(self):
        """Export animation states as standalone JSON for game integration."""
        if not self.anim_states:
            self.show_msg("No animation states defined", error=True); return
        if not self.sheet_path:
            self.show_msg("No sheet loaded", error=True); return
        out = os.path.splitext(self.sheet_path)[0] + "_anims.json"
        data = {
            "image": os.path.basename(self.sheet_path),
            "frame_size": {"w": self.frame_size[0], "h": self.frame_size[1]},
            "animations": [a.to_dict() for a in self.anim_states]
        }
        with open(out, "w") as f:
            json.dump(data, f, indent=2)
        self.show_msg(f"Anims -> {os.path.basename(out)}  ({len(self.anim_states)} states)")

    def batch_export(self):
        """Batch export all PNGs in a folder as GIF."""
        if not HAS_PIL:
            self.show_msg("pip install Pillow", error=True); return
        folder = open_folder("Select folder with sprite sheets")
        if not folder: return
        count = 0
        for fname in os.listdir(folder):
            if not fname.lower().endswith(".png"): continue
            fpath = os.path.join(folder, fname)
            try:
                sheet = pygame.image.load(fpath).convert_alpha()
                w, h = sheet.get_size()
                cols, rows = self.cols_inp.value, self.rows_inp.value
                fw, fh = w // max(1, cols), h // max(1, rows)
                total = min(cols * rows, self.frames_inp.value)
                frames = []
                for i in range(total):
                    c, r = i % cols, i // cols
                    rect = pygame.Rect(c*fw, r*fh, fw, fh)
                    if rect.right <= w and rect.bottom <= h:
                        frames.append(surf_to_pil(sheet.subsurface(rect)))
                if frames:
                    dur = max(20, int(1000 / max(1, self.fps_inp.value)))
                    out = os.path.splitext(fpath)[0] + ".gif"
                    frames[0].save(out, save_all=True, append_images=frames[1:],
                                   loop=0, duration=dur, disposal=2)
                    count += 1
            except Exception:
                pass
        self.show_msg(f"Batch: {count} GIFs exported from {os.path.basename(folder)}")

    # ── project save/load ───────────────────────────────────────────────────
    def save_project(self):
        if not self.sheet_path:
            self.show_msg("No sheet loaded", error=True); return
        out = self.project_path
        if not out:
            out = os.path.splitext(self.sheet_path)[0] + ".sproj"
        data = {
            "version": "4.0",
            "sheet_path": os.path.abspath(self.sheet_path),
            "grid": {
                "cols": self.cols_inp.value,
                "rows": self.rows_inp.value,
                "frames": self.frames_inp.value,
            },
            "playback": {
                "fps": self.fps_inp.value,
                "range_start": self.start_inp.value,
                "range_end": self.end_inp.value,
                "play_mode": self.play_mode,
            },
            "flip_h": self.flip_h,
            "flip_v": self.flip_v,
            "sprite_prefix": self.sprite_prefix,
            "origins": {str(k): list(v) for k, v in self._origins.items()},
            "hitboxes": {str(k): list(v) for k, v in self._hitboxes.items()},
            "animations": [a.to_dict() for a in self.anim_states],
            "frame_order": self._frame_order if self._frame_order else [],
            "trim_computed": self._trim_computed,
        }
        with open(out, "w") as f:
            json.dump(data, f, indent=2)
        self.project_path = out
        self.show_msg(f"Project saved: {os.path.basename(out)}")

    def load_project(self, path=None):
        if not path:
            if not HAS_TK: return
            root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
            path = filedialog.askopenfilename(
                title="Open project",
                filetypes=[("Sprite Project", "*.sproj"), ("All", "*.*")])
            root.destroy()
        if not path: return
        try:
            with open(path, "r") as f:
                data = json.load(f)
            sheet_path = data.get("sheet_path", "")
            if not os.path.exists(sheet_path):
                # Try relative to project file
                sheet_path = os.path.join(os.path.dirname(path), os.path.basename(sheet_path))
            if not os.path.exists(sheet_path):
                self.show_msg(f"Sheet not found: {sheet_path}", error=True); return

            # Load grid settings first
            grid = data.get("grid", {})
            self.cols_inp.value = grid.get("cols", 4); self.cols_inp._buf = str(self.cols_inp.value)
            self.rows_inp.value = grid.get("rows", 4); self.rows_inp._buf = str(self.rows_inp.value)
            self.frames_inp.value = grid.get("frames", 16); self.frames_inp._buf = str(self.frames_inp.value)

            # Load sheet
            self.sheet = pygame.image.load(sheet_path).convert_alpha()
            self.sheet_path = sheet_path
            self.project_path = path
            self._save_recent(path)

            # Playback
            pb = data.get("playback", {})
            self.fps_inp.value = pb.get("fps", 12); self.fps_inp._buf = str(self.fps_inp.value)
            self.start_inp.value = pb.get("range_start", 0); self.start_inp._buf = str(self.start_inp.value)
            self.end_inp.value = pb.get("range_end", self.total_frames-1); self.end_inp._buf = str(self.end_inp.value)
            self.play_mode = pb.get("play_mode", 0)

            # State
            self.flip_h = data.get("flip_h", False)
            self.flip_v = data.get("flip_v", False)
            self.sprite_prefix = data.get("sprite_prefix", "sprite_")

            # Origins & hitboxes
            self._origins = {int(k): tuple(v) for k, v in data.get("origins", {}).items()}
            self._hitboxes = {int(k): tuple(v) for k, v in data.get("hitboxes", {}).items()}

            # Animation states
            self.anim_states = []
            for ad in data.get("animations", []):
                a = AnimState(ad["name"], ad["start"], ad["end"], ad.get("fps", 12))
                fd = ad.get("frame_durations", {})
                a.frame_durations = {int(k): v for k, v in fd.items()}
                self.anim_states.append(a)
            self.active_anim = -1

            # Frame order
            fo = data.get("frame_order", [])
            self._frame_order = fo if fo else []
            self._undo_stack = []

            # Re-trim if it was computed
            self._trim_computed = False; self._trim_rects = []; self._trim_union = None
            if data.get("trim_computed", False):
                self.compute_trim()

            self._palette = []; self._palette_frame = -1
            self._duplicates = set(); self._dupes_hash = ""
            self._sheet_backup = None
            self.frame = 0; self.acc = 0; self.direction = 1; self.done_once = False
            self.zoom_to_fit()
            n_anims = len(self.anim_states)
            n_origins = len(self._origins)
            n_hb = len(self._hitboxes)
            self.show_msg(f"Project loaded: {n_anims} anims, {n_origins} origins, {n_hb} hitboxes")
        except Exception as ex:
            self.show_msg(f"Load failed: {ex}", error=True)

    # ── copy origin/hitbox to all ─────────────────────────────────────────────
    def copy_origin_to_all(self):
        if self.frame not in self._origins:
            self.show_msg("Set origin on current frame first", error=True); return
        origin = self._origins[self.frame]
        n = self.display_total
        for i in range(n):
            self._origins[i] = origin
        self.show_msg(f"Origin {origin} copied to all {n} frames")

    def copy_hitbox_to_all(self):
        if self.frame not in self._hitboxes:
            self.show_msg("Set hitbox on current frame first", error=True); return
        hb = self._hitboxes[self.frame]
        n = self.display_total
        for i in range(n):
            self._hitboxes[i] = hb
        self.show_msg(f"Hitbox copied to all {n} frames")

    # ── analysis ──────────────────────────────────────────────────────────────
    def compute_palette(self):
        if not self.sheet or not HAS_PIL: return
        if self._palette_frame == self.frame: return
        sub = self.get_frame_surface(self.frame)
        img = surf_to_pil(sub)
        colors = img.getcolors(maxcolors=262144) or []
        colors = [(c, col) for c, col in colors if col[3] > 20]
        colors.sort(reverse=True)
        self._palette = colors[:20]
        self._palette_frame = self.frame

    def compute_duplicates(self):
        if not self.sheet: return
        key = f"{self.total_frames}_{self.cols_inp.value}_{self.rows_inp.value}"
        if self._dupes_hash == key: return
        hashes = {}; dupes = set()
        for i in range(self.total_frames):
            h = frame_hash(self.sheet.subsurface(self.frame_rect(i)))
            if h in hashes: dupes.add(i); dupes.add(hashes[h])
            else: hashes[h] = i
        self._duplicates = dupes; self._dupes_hash = key
        self.show_msg(f"Duplicates: {len(dupes)} frames")

    def compute_trim(self):
        if not self.sheet: return
        self._trim_rects = []; union = None
        for i in range(self.total_frames):
            tr = find_trim_rect(self.sheet.subsurface(self.frame_rect(i)))
            self._trim_rects.append(tr)
            union = tr.copy() if union is None else union.union(tr)
        self._trim_computed = True; self._trim_union = union
        fw, fh = self.frame_size
        if union:
            saved = (1.0 - (union.w * union.h) / max(1, fw * fh)) * 100
            self.show_msg(f"Trim: {union.w}x{union.h} ({saved:.0f}% smaller)")

    def auto_detect(self):
        if not self.sheet: return
        w, h = self.sheet.get_size()
        def good(total, n): return n > 0 and total % n == 0 and 16 <= total//n <= 512
        cols = next((n for n in range(1, 33) if good(w, n)), self.cols_inp.value)
        rows = next((n for n in range(1, 33) if good(h, n)), self.rows_inp.value)
        self.cols_inp.value = cols; self.cols_inp._buf = str(cols)
        self.rows_inp.value = rows; self.rows_inp._buf = str(rows)
        total = cols * rows
        self.frames_inp.value = total; self.frames_inp._buf = str(total)
        self.end_inp.value = total - 1; self.end_inp._buf = str(total-1)
        self.show_msg(f"Auto: {cols}x{rows} -> {w//cols}x{h//rows} px")

    # ── frame reorder ─────────────────────────────────────────────────────────
    def _ensure_order(self):
        if not self._frame_order:
            self._frame_order = list(range(self.total_frames))

    def delete_frame(self):
        if not self.sheet: return
        self._ensure_order()
        if len(self._frame_order) <= 1:
            self.show_msg("Can't delete last frame", error=True); return
        self._undo_stack.append(list(self._frame_order))
        self._frame_order.pop(self.frame)
        if self.frame >= len(self._frame_order):
            self.frame = len(self._frame_order) - 1
        self.show_msg(f"Deleted ({len(self._frame_order)} left)")

    def move_frame(self, delta):
        if not self.sheet: return
        self._ensure_order()
        new_pos = self.frame + delta
        if new_pos < 0 or new_pos >= len(self._frame_order): return
        self._undo_stack.append(list(self._frame_order))
        self._frame_order[self.frame], self._frame_order[new_pos] = \
            self._frame_order[new_pos], self._frame_order[self.frame]
        self.frame = new_pos

    def undo_reorder(self):
        if self._undo_stack:
            self._frame_order = self._undo_stack.pop()
            self.frame = min(self.frame, max(0, len(self._frame_order) - 1))
            self.show_msg("Undo")

    # ── palette swap ─────────────────────────────────────────────────────────
    def apply_palette_swap(self):
        if not self.sheet or not self._remap_from or not self._remap_to:
            self.show_msg("Set From/To colors first", error=True); return
        self._sheet_backup = self.sheet.copy()
        fr, fg, fb = self._remap_from
        tr, tg, tb = self._remap_to
        px = pygame.surfarray.pixels3d(self.sheet)
        alpha = pygame.surfarray.pixels_alpha(self.sheet)
        tol = 15
        mask = ((abs(px[:,:,0].astype(int) - fr) < tol) &
                (abs(px[:,:,1].astype(int) - fg) < tol) &
                (abs(px[:,:,2].astype(int) - fb) < tol) &
                (alpha > 20))
        px[mask] = [tr, tg, tb]
        del px, alpha
        self.show_msg(f"Swapped ({fr},{fg},{fb}) -> ({tr},{tg},{tb})  [Ctrl+Z to undo]")

    def undo_palette_swap(self):
        if self._sheet_backup:
            self.sheet = self._sheet_backup
            self._sheet_backup = None
            self.show_msg("Palette swap undone")
        else:
            self.show_msg("No swap to undo", error=True)

    # ── animation states ─────────────────────────────────────────────────────
    def add_anim_state(self):
        name = ask_string("Animation State", "Name (e.g. idle, walk, attack):", "idle")
        if not name: return
        state = AnimState(name, self.range_start, self.range_end, self.fps_inp.value)
        self.anim_states.append(state)
        self.show_msg(f"Added anim: {name} [{state.start}-{state.end}]")

    def play_anim_state(self, idx):
        if idx < 0 or idx >= len(self.anim_states): return
        anim = self.anim_states[idx]
        self.active_anim = idx
        self.start_inp.value = anim.start; self.start_inp._buf = str(anim.start)
        self.end_inp.value = anim.end; self.end_inp._buf = str(anim.end)
        self.fps_inp.value = anim.fps; self.fps_inp._buf = str(anim.fps)
        self.frame = anim.start
        self.playing = True; self.done_once = False; self.direction = 1
        self.show_msg(f"Playing: {anim.name}")

    def delete_anim_state(self, idx):
        if 0 <= idx < len(self.anim_states):
            name = self.anim_states[idx].name
            self.anim_states.pop(idx)
            if self.active_anim >= len(self.anim_states):
                self.active_anim = -1
            self.show_msg(f"Deleted anim: {name}")

    def set_frame_duration(self):
        """Set custom duration for current frame in active anim."""
        if self.active_anim < 0:
            self.show_msg("Select an animation first", error=True); return
        val = ask_string("Frame Duration", f"Duration for frame {self.frame} (ms):", "100")
        if val is None: return
        try:
            ms = int(val)
            self.anim_states[self.active_anim].frame_durations[self.frame] = ms
            self.show_msg(f"Frame {self.frame} = {ms}ms")
        except ValueError:
            self.show_msg("Invalid number", error=True)

    # ── compare ──────────────────────────────────────────────────────────────
    def load_compare(self):
        p = open_file("Open comparison sheet")
        if not p: return
        try:
            self.compare_sheet = pygame.image.load(p).convert_alpha()
            self.compare_path = p; self.compare_frame = 0; self.show_compare = True
            self.show_msg(f"Compare: {os.path.basename(p)}")
        except Exception as ex:
            self.show_msg(str(ex), error=True)

    def load_bg_sprite(self):
        p = open_file("Open background image")
        if not p: return
        try:
            self.bg_sprite = pygame.image.load(p).convert_alpha()
            self.bg_sprite_path = p
            self.show_msg(f"BG: {os.path.basename(p)}")
        except Exception as ex:
            self.show_msg(str(ex), error=True)

    # ── merge sheets ─────────────────────────────────────────────────────────
    def merge_sheets(self):
        """Load multiple PNGs and merge into one atlas."""
        if not HAS_TK:
            self.show_msg("Needs tkinter", error=True); return
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        files = filedialog.askopenfilenames(
            title="Select PNGs to merge",
            filetypes=[("PNG", "*.png")])
        root.destroy()
        if not files: return
        surfs = []
        for f in files:
            surfs.append(pygame.image.load(f).convert_alpha())
        if not surfs: return
        # Stack horizontally
        max_h = max(s.get_height() for s in surfs)
        total_w = sum(s.get_width() for s in surfs)
        atlas = pygame.Surface((total_w, max_h), pygame.SRCALPHA)
        atlas.fill((0, 0, 0, 0))
        x = 0
        for s in surfs:
            atlas.blit(s, (x, 0)); x += s.get_width()
        out = os.path.join(os.path.dirname(files[0]), "merged_atlas.png")
        pygame.image.save(atlas, out)
        self.load(out)
        self.show_msg(f"Merged {len(surfs)} sheets -> {total_w}x{max_h}")

    # ── UI helpers ────────────────────────────────────────────────────────────
    def _btn(self, name, rect):
        self._all_btns[name] = rect; return rect

    def _viewport_to_frame(self, mx, my):
        sw, sh = self.screen.get_size()
        px = sw - PANEL_W
        fw, fh = self.frame_size
        z = self.pixel_scale if self.pixel_scale > 0 else self.zoom
        dw, dh = max(1, int(fw * z)), max(1, int(fh * z))
        strip_top = sh - STRIP_H - 6
        cx = px // 2 - dw // 2; cy = strip_top // 2 - dh // 2
        dest = pygame.Rect(cx, cy, dw, dh)
        if not dest.collidepoint(mx, my): return None
        fx = int((mx - dest.x) / z); fy = int((my - dest.y) / z)
        return (max(0, min(fx, fw-1)), max(0, min(fy, fh-1)))

    # ── draw panel ────────────────────────────────────────────────────────────
    def draw_panel(self, px, sh):
        mx, my = pygame.mouse.get_pos()
        self._all_btns = {}
        pygame.draw.rect(self.screen, PANEL_BG, pygame.Rect(px, 0, PANEL_W, sh))
        pygame.draw.line(self.screen, ACCENT, (px, 0), (px, sh))

        y = 10
        draw_text(self.screen, self.font_lg, "Sprite Animator v4.0", (px+12, y), ACCENT)
        y += 28

        if self.sheet_path:
            name = os.path.basename(self.sheet_path)
            if len(name) > 30: name = name[:27] + "..."
            draw_text(self.screen, self.font_sm, name, (px+12, y), TEXT_DIM)
        else:
            draw_text(self.screen, self.font_sm, "No file loaded", (px+12, y), TEXT_DIM)
        y += 18

        # File buttons row
        bw_file = (PANEL_W - 30) // 3
        ob = pygame.Rect(px+12, y, bw_file, 28)
        draw_button(self.screen, self.font_sm, ob, "Open (O)",
                    hovered=ob.collidepoint(mx,my))
        self._btn("open", ob)
        sv = pygame.Rect(px+15+bw_file, y, bw_file, 28)
        draw_button(self.screen, self.font_sm, sv, "Save",
                    hovered=sv.collidepoint(mx,my), accent=GREEN)
        self._btn("save_proj", sv)
        ld = pygame.Rect(px+18+bw_file*2, y, bw_file, 28)
        draw_button(self.screen, self.font_sm, ld, "Load",
                    hovered=ld.collidepoint(mx,my), accent=ORANGE)
        self._btn("load_proj", ld)
        y += 34

        # Recent files
        if self.recent_files:
            draw_text(self.screen, self.font_sm, "Recent:", (px+12, y), TEXT_DIM)
            y += 16
            for ri, rp in enumerate(self.recent_files[:4]):
                rname = os.path.basename(rp)
                if len(rname) > 32: rname = rname[:29] + "..."
                rr = pygame.Rect(px+12, y, PANEL_W-24, 18)
                col = ACCENT if rr.collidepoint(mx, my) else TEXT_DIM
                draw_text(self.screen, self.font_sm, rname, (px+14, y), col)
                self._btn(f"recent_{ri}", rr)
                y += 18
            y += 4

        sep(self.screen, px+8, y, PANEL_W-16); y += 10

        # tabs
        tw = (PANEL_W - 24) // len(TABS)
        for i, name in enumerate(TABS):
            tr = pygame.Rect(px+12 + i*tw, y, tw, 26)
            draw_button(self.screen, self.font_sm, tr, name,
                        hovered=tr.collidepoint(mx,my), active=(i == self.active_tab))
            self._btn(f"tab_{i}", tr)
        y += 34
        sep(self.screen, px+8, y, PANEL_W-16); y += 10

        tab_funcs = [self._tab_grid, self._tab_play, self._tab_export,
                     self._tab_analyze, self._tab_tools, self._tab_anim]
        if self.active_tab < len(tab_funcs):
            y = tab_funcs[self.active_tab](px, y, sh)

        if self._msg_timer > 0:
            a = min(1.0, self._msg_timer)
            col = RED if self._msg_err else GREEN
            draw_text(self.screen, self.font_sm, self._msg,
                      (px+12, sh-22), (*col, int(a*220)))

    def _tab_grid(self, px, y, sh):
        mx, my = pygame.mouse.get_pos()
        for inp in self._grid_inputs:
            y = inp.draw(self.screen, self.font, px+12, y) + 2
        ab = pygame.Rect(px+12, y, PANEL_W-24, 28)
        draw_button(self.screen, self.font, ab, "Auto-detect grid",
                    hovered=ab.collidepoint(mx,my), accent=ACCENT2)
        self._btn("auto", ab); y += 36
        sep(self.screen, px+8, y, PANEL_W-16); y += 10
        if self.sheet:
            fw, fh = self.frame_size; sw2, sh2 = self.sheet.get_size()
            for lbl, val in [
                ("Sheet", f"{sw2} x {sh2} px"), ("Frame", f"{fw} x {fh} px"),
                ("Cells", f"{self.cols_inp.value * self.rows_inp.value}"),
                ("Active", f"{self.display_total}"),
            ]:
                draw_text(self.screen, self.font_sm, lbl+":", (px+12, y), TEXT_DIM)
                draw_text(self.screen, self.font_sm, val, (px+100, y), TEXT); y += 18
            if self.flip_h or self.flip_v:
                flips = []
                if self.flip_h: flips.append("H")
                if self.flip_v: flips.append("V")
                draw_text(self.screen, self.font_sm, f"Flip: {'+'.join(flips)}",
                          (px+12, y), CYAN); y += 18
        return y

    def _tab_play(self, px, y, sh):
        mx, my = pygame.mouse.get_pos()
        for inp in self._playback_inputs:
            y = inp.draw(self.screen, self.font, px+12, y) + 2
        sep(self.screen, px+8, y, PANEL_W-16); y += 10

        draw_text(self.screen, self.font, "Mode:", (px+12, y), TEXT_DIM); y += 20
        mw = (PANEL_W - 24) // 3
        for i, lbl in enumerate(PLAY_MODES):
            mr = pygame.Rect(px+12 + i*mw, y, mw, 26)
            draw_button(self.screen, self.font_sm, mr, lbl,
                        hovered=mr.collidepoint(mx,my), active=(i == self.play_mode))
            self._btn(f"mode_{i}", mr)
        y += 34; sep(self.screen, px+8, y, PANEL_W-16); y += 10

        # Feature toggles row
        hw = (PANEL_W - 30) // 2
        on_r = pygame.Rect(px+12, y, hw, 28)
        draw_button(self.screen, self.font_sm, on_r,
                    "Onion ON" if self.onion else "Onion OFF",
                    hovered=on_r.collidepoint(mx,my), active=self.onion)
        self._btn("onion", on_r)
        gr_r = pygame.Rect(px+18+hw, y, hw, 28)
        draw_button(self.screen, self.font_sm, gr_r,
                    "Grid ON" if self.show_grid else "Grid OFF",
                    hovered=gr_r.collidepoint(mx,my), active=self.show_grid)
        self._btn("pgrid", gr_r)
        y += 34

        # Flip buttons
        fh_r = pygame.Rect(px+12, y, hw, 28)
        fv_r = pygame.Rect(px+18+hw, y, hw, 28)
        draw_button(self.screen, self.font_sm, fh_r,
                    "Flip H  ON" if self.flip_h else "Flip H (H)",
                    hovered=fh_r.collidepoint(mx,my), active=self.flip_h)
        draw_button(self.screen, self.font_sm, fv_r,
                    "Flip V  ON" if self.flip_v else "Flip V (V)",
                    hovered=fv_r.collidepoint(mx,my), active=self.flip_v)
        self._btn("flip_h", fh_r); self._btn("flip_v", fv_r)
        y += 34

        # Background
        draw_text(self.screen, self.font, "Background:", (px+12, y), TEXT_DIM); y += 20
        bw2 = (PANEL_W - 24) // len(BG_MODES)
        for i, lbl in enumerate(BG_MODES):
            br = pygame.Rect(px+12 + i*bw2, y, bw2, 26)
            draw_button(self.screen, self.font_sm, br, lbl,
                        hovered=br.collidepoint(mx,my), active=(i == self.bg_mode))
            self._btn(f"bg_{i}", br)
        y += 34
        if self.bg_mode == 3:
            cr = pygame.Rect(px+12, y, PANEL_W-24, 24)
            pygame.draw.rect(self.screen, self.bg_custom, cr, border_radius=4)
            pygame.draw.rect(self.screen, TEXT_DIM, cr, 1, border_radius=4)
            draw_text(self.screen, self.font_sm, "Click to pick", cr.center, TEXT, "center")
            self._btn("bg_pick", cr); y += 32
        sep(self.screen, px+8, y, PANEL_W-16); y += 10

        # Pixel scale
        draw_text(self.screen, self.font, "Scale:", (px+12, y), TEXT_DIM); y += 20
        scales = ["Free", "1x", "2x", "3x", "4x"]
        sw2 = (PANEL_W - 24) // 5
        for i, lbl in enumerate(scales):
            sr = pygame.Rect(px+12 + i*sw2, y, sw2, 26)
            draw_button(self.screen, self.font_sm, sr, lbl,
                        hovered=sr.collidepoint(mx,my), active=(i == self.pixel_scale))
            self._btn(f"scale_{i}", sr)
        y += 34

        # Zoom / play controls
        zf_r = pygame.Rect(px+12, y, PANEL_W-24, 28)
        z = self.pixel_scale if self.pixel_scale > 0 else self.zoom
        draw_button(self.screen, self.font, zf_r, f"Zoom to Fit  (F)  {z:.1f}x",
                    hovered=zf_r.collidepoint(mx,my))
        self._btn("zoom_fit", zf_r); y += 36

        bw3 = (PANEL_W - 36) // 3
        prev_r = pygame.Rect(px+12, y, bw3, 32)
        play_r = pygame.Rect(px+12+bw3+6, y, bw3, 32)
        next_r = pygame.Rect(px+12+bw3*2+12, y, bw3, 32)
        draw_button(self.screen, self.font, prev_r, "<", hovered=prev_r.collidepoint(mx,my))
        draw_button(self.screen, self.font, play_r,
                    "||" if self.playing else ">",
                    hovered=play_r.collidepoint(mx,my), active=self.playing)
        draw_button(self.screen, self.font, next_r, ">", hovered=next_r.collidepoint(mx,my))
        self._btn("prev", prev_r); self._btn("play", play_r); self._btn("next", next_r)
        y += 40

        if self.sheet:
            draw_text(self.screen, self.font_b,
                      f"Frame {self.frame}  [{self.range_start}-{self.range_end}]",
                      (px+12, y), HIGHLIGHT); y += 22
            draw_text(self.screen, self.font_sm,
                      f"{self.fps_inp.value} fps  |  {1000//max(1,self.fps_inp.value)} ms/f",
                      (px+12, y), TEXT_DIM); y += 20
        return y

    def _tab_export(self, px, y, sh):
        mx, my = pygame.mouse.get_pos()
        draw_text(self.screen, self.font_sm,
                  f"Range {self.range_start}-{self.range_end}  "
                  f"({self.range_end-self.range_start+1}f)"
                  + ("  [trimmed]" if self._trim_computed else ""),
                  (px+12, y), TEXT_DIM); y += 20
        sep(self.screen, px+8, y, PANEL_W-16); y += 10

        exports = [
            ("gif",    "Export GIF  (G)",          ACCENT,  HAS_PIL),
            ("webp",   "Export WebP  (W)",         ACCENT2, HAS_PIL),
            ("png",    "Export PNG Seq  (P)",       GREEN,   True),
            ("json",   "Export Atlas JSON  (J)",    ORANGE,  True),
            ("packed", "Export Packed Atlas",       CYAN,    True),
            ("anims",  "Export Anim JSON",         PURPLE,  bool(self.anim_states)),
            ("batch",  "Batch Export Folder",      YELLOW,  HAS_PIL),
            ("merge",  "Merge Multiple Sheets",    (180,180,80), True),
        ]
        for key, label, color, available in exports:
            r = pygame.Rect(px+12, y, PANEL_W-24, 28)
            if available:
                draw_button(self.screen, self.font, r, label,
                            hovered=r.collidepoint(mx,my), accent=color)
                self._btn(f"exp_{key}", r)
            else:
                draw_rect_aa(self.screen, BTN_BG, r)
                draw_text(self.screen, self.font_sm, label + "  (n/a)",
                          r.center, TEXT_DIM, "center")
            y += 34

        sep(self.screen, px+8, y, PANEL_W-16); y += 10
        draw_text(self.screen, self.font, "Prefix:", (px+12, y), TEXT_DIM)
        pr = pygame.Rect(px+80, y-2, PANEL_W-92, 22)
        draw_rect_aa(self.screen, BTN_BG, pr)
        draw_text(self.screen, self.font_sm, self.sprite_prefix, pr.center, HIGHLIGHT, "center")
        self._btn("prefix_edit", pr); y += 26
        return y

    def _tab_analyze(self, px, y, sh):
        mx, my = pygame.mouse.get_pos()

        dup_r = pygame.Rect(px+12, y, PANEL_W-24, 28)
        draw_button(self.screen, self.font, dup_r, "Find Duplicates  (D)",
                    hovered=dup_r.collidepoint(mx,my), accent=ORANGE)
        self._btn("dupes", dup_r); y += 34
        if self._duplicates:
            draw_text(self.screen, self.font_sm, f"{len(self._duplicates)} dupes (red in strip)",
                      (px+12, y), ORANGE); y += 18
        sep(self.screen, px+8, y, PANEL_W-16); y += 10

        pal_r = pygame.Rect(px+12, y, PANEL_W-24, 28)
        draw_button(self.screen, self.font, pal_r, "Analyze Palette",
                    hovered=pal_r.collidepoint(mx,my), accent=PURPLE)
        self._btn("palette", pal_r); y += 34
        if self._palette:
            sw2 = 20; cx = px+12; row_x = cx
            for i, (cnt, col) in enumerate(self._palette[:16]):
                sr = pygame.Rect(row_x, y, sw2, sw2)
                pygame.draw.rect(self.screen, col[:3], sr, border_radius=3)
                pygame.draw.rect(self.screen, TEXT_DIM, sr, 1, border_radius=3)
                if (i+1) % 12 == 0: y += sw2+3; row_x = cx
                else: row_x += sw2+3
            y += sw2+6
        sep(self.screen, px+8, y, PANEL_W-16); y += 10

        if self.sheet:
            fw, fh = self.frame_size
            for lbl, val in [
                ("Pixels/frame", f"{fw*fh:,}"),
                ("Duration", f"{(self.range_end-self.range_start+1)/max(1,self.fps_inp.value):.2f}s"),
                ("File", f"{os.path.getsize(self.sheet_path)//1024} KB" if self.sheet_path else ""),
            ]:
                draw_text(self.screen, self.font_sm, f"{lbl}: {val}", (px+12, y), TEXT_DIM); y += 18
        return y

    def _tab_tools(self, px, y, sh):
        mx, my = pygame.mouse.get_pos()

        # Trim
        tr_r = pygame.Rect(px+12, y, PANEL_W-24, 28)
        draw_button(self.screen, self.font, tr_r,
                    "Trim Done" if self._trim_computed else "Auto-Trim  (T)",
                    hovered=tr_r.collidepoint(mx,my), accent=GREEN, active=self._trim_computed)
        self._btn("trim", tr_r); y += 34
        if self._trim_computed and self._trim_union:
            u = self._trim_union
            draw_text(self.screen, self.font_sm, f"Bbox: {u.x},{u.y} {u.w}x{u.h}",
                      (px+12, y), TEXT_DIM); y += 18
        sep(self.screen, px+8, y, PANEL_W-16); y += 10

        # Frame reorder
        draw_text(self.screen, self.font, "Frame Order:", (px+12, y), TEXT_DIM); y += 22
        bw3 = (PANEL_W - 36) // 3
        ml = pygame.Rect(px+12, y, bw3, 28)
        mr = pygame.Rect(px+12+bw3+6, y, bw3, 28)
        dl = pygame.Rect(px+12+bw3*2+12, y, bw3, 28)
        draw_button(self.screen, self.font, ml, "<< Move", hovered=ml.collidepoint(mx,my))
        draw_button(self.screen, self.font, mr, "Move >>", hovered=mr.collidepoint(mx,my))
        draw_button(self.screen, self.font, dl, "Delete", hovered=dl.collidepoint(mx,my), accent=RED)
        self._btn("move_l", ml); self._btn("move_r", mr); self._btn("del_f", dl)
        y += 34
        ur = pygame.Rect(px+12, y, PANEL_W-24, 28)
        draw_button(self.screen, self.font, ur, "Undo  (Ctrl+Z)",
                    hovered=ur.collidepoint(mx,my), accent=ACCENT2)
        self._btn("undo", ur); y += 36
        sep(self.screen, px+8, y, PANEL_W-16); y += 10

        # Hitbox / Origin
        draw_text(self.screen, self.font, "Hitbox / Origin:", (px+12, y), TEXT_DIM); y += 22
        hb_r = pygame.Rect(px+12, y, PANEL_W-24, 28)
        draw_button(self.screen, self.font, hb_r,
                    "Drawing Hitbox..." if self._editing_hitbox else "Draw Hitbox (click 2 corners)",
                    hovered=hb_r.collidepoint(mx,my), active=self._editing_hitbox)
        self._btn("draw_hb", hb_r); y += 34
        draw_text(self.screen, self.font_sm, "Right-click viewport = set origin",
                  (px+12, y), TEXT_DIM); y += 18
        if self.frame in self._origins:
            draw_text(self.screen, self.font_sm, f"Origin: {self._origins[self.frame]}",
                      (px+12, y), CYAN); y += 18
        if self.frame in self._hitboxes:
            hx, hy, hw, hh = self._hitboxes[self.frame]
            draw_text(self.screen, self.font_sm, f"Hitbox: ({hx},{hy}) {hw}x{hh}",
                      (px+12, y), CYAN); y += 18

        # Copy to all buttons
        hw3 = (PANEL_W - 36) // 2
        co_r = pygame.Rect(px+12, y, hw3, 26)
        ch_r = pygame.Rect(px+18+hw3, y, hw3, 26)
        draw_button(self.screen, self.font_sm, co_r, "Origin -> All",
                    hovered=co_r.collidepoint(mx,my), accent=CYAN)
        draw_button(self.screen, self.font_sm, ch_r, "Hitbox -> All",
                    hovered=ch_r.collidepoint(mx,my), accent=CYAN)
        self._btn("copy_origin", co_r); self._btn("copy_hb", ch_r)
        y += 32
        sep(self.screen, px+8, y, PANEL_W-16); y += 10

        # Palette swap
        draw_text(self.screen, self.font, "Palette Swap:", (px+12, y), TEXT_DIM); y += 22
        hw2 = (PANEL_W - 36) // 2
        from_r = pygame.Rect(px+12, y, hw2, 28)
        to_r = pygame.Rect(px+12+hw2+12, y, hw2, 28)
        if self._remap_from:
            pygame.draw.rect(self.screen, self._remap_from, from_r, border_radius=5)
            draw_text(self.screen, self.font_sm, "From", from_r.center, TEXT, "center")
        else:
            draw_button(self.screen, self.font_sm, from_r, "Pick From",
                        hovered=from_r.collidepoint(mx,my))
        if self._remap_to:
            pygame.draw.rect(self.screen, self._remap_to, to_r, border_radius=5)
            draw_text(self.screen, self.font_sm, "To", to_r.center, TEXT, "center")
        else:
            draw_button(self.screen, self.font_sm, to_r, "Pick To",
                        hovered=to_r.collidepoint(mx,my))
        self._btn("remap_from", from_r); self._btn("remap_to", to_r)
        y += 34
        hw4 = (PANEL_W - 36) // 2
        sw_r = pygame.Rect(px+12, y, hw4, 28)
        draw_button(self.screen, self.font_sm, sw_r, "Apply Swap",
                    hovered=sw_r.collidepoint(mx,my), accent=PURPLE)
        self._btn("apply_swap", sw_r)
        us_r = pygame.Rect(px+18+hw4, y, hw4, 28)
        draw_button(self.screen, self.font_sm, us_r, "Undo Swap",
                    hovered=us_r.collidepoint(mx,my), accent=ACCENT2,
                    active=bool(self._sheet_backup))
        self._btn("undo_swap", us_r)
        y += 36
        sep(self.screen, px+8, y, PANEL_W-16); y += 10

        # Compare + BG sprite
        cmp_r = pygame.Rect(px+12, y, PANEL_W-24, 28)
        draw_button(self.screen, self.font, cmp_r,
                    "Compare  (C)" + ("  ON" if self.show_compare else ""),
                    hovered=cmp_r.collidepoint(mx,my), active=self.show_compare, accent=CYAN)
        self._btn("compare", cmp_r); y += 34

        bg_r = pygame.Rect(px+12, y, PANEL_W-24, 28)
        draw_button(self.screen, self.font, bg_r,
                    "BG Sprite" + ("  ON" if self.bg_sprite else ""),
                    hovered=bg_r.collidepoint(mx,my), active=bool(self.bg_sprite))
        self._btn("bg_sprite", bg_r); y += 34
        return y

    def _tab_anim(self, px, y, sh):
        mx, my = pygame.mouse.get_pos()
        draw_text(self.screen, self.font, "Animation States:", (px+12, y), TEXT_DIM); y += 22

        add_r = pygame.Rect(px+12, y, PANEL_W-24, 28)
        draw_button(self.screen, self.font, add_r, "+ Add State (from current range)",
                    hovered=add_r.collidepoint(mx,my), accent=GREEN)
        self._btn("anim_add", add_r); y += 36

        sep(self.screen, px+8, y, PANEL_W-16); y += 10

        # List states
        if not self.anim_states:
            draw_text(self.screen, self.font_sm, "No states defined yet", (px+12, y), TEXT_DIM)
            y += 18
        else:
            for i, anim in enumerate(self.anim_states):
                is_active = (i == self.active_anim)
                # State row
                row_r = pygame.Rect(px+12, y, PANEL_W-80, 26)
                color = ACCENT if is_active else BTN_BG
                draw_rect_aa(self.screen, color, row_r)
                draw_rect_aa(self.screen, ACCENT if is_active else TEXT_DIM, row_r, width=1)
                label = f"{anim.name}  [{anim.start}-{anim.end}]  {anim.fps}fps"
                draw_text(self.screen, self.font_sm, label,
                          (row_r.x+6, row_r.centery), TEXT, "midleft")
                self._btn(f"anim_play_{i}", row_r)

                # Delete button
                del_r = pygame.Rect(px+PANEL_W-62, y, 50, 26)
                draw_button(self.screen, self.font_sm, del_r, "X",
                            hovered=del_r.collidepoint(mx,my), accent=RED)
                self._btn(f"anim_del_{i}", del_r)
                y += 30

        sep(self.screen, px+8, y, PANEL_W-16); y += 10

        # Per-frame timing
        dur_r = pygame.Rect(px+12, y, PANEL_W-24, 28)
        draw_button(self.screen, self.font, dur_r, f"Set Frame {self.frame} Duration (ms)",
                    hovered=dur_r.collidepoint(mx,my), accent=ORANGE)
        self._btn("frame_dur", dur_r); y += 36

        sep(self.screen, px+8, y, PANEL_W-16); y += 10

        # Timeline visualization
        if self.anim_states and self.sheet:
            draw_text(self.screen, self.font, "Timeline:", (px+12, y), TEXT_DIM); y += 22
            bar_w = PANEL_W - 24
            bar_h = 20
            total = self.total_frames
            bar_r = pygame.Rect(px+12, y, bar_w, bar_h)
            pygame.draw.rect(self.screen, BTN_BG, bar_r, border_radius=3)

            colors_list = [ACCENT, GREEN, ORANGE, PURPLE, CYAN, RED, YELLOW, ACCENT2]
            for i, anim in enumerate(self.anim_states):
                if total == 0: continue
                x1 = px+12 + int(anim.start / total * bar_w)
                x2 = px+12 + int((anim.end + 1) / total * bar_w)
                col = colors_list[i % len(colors_list)]
                seg = pygame.Rect(x1, y, max(2, x2 - x1), bar_h)
                pygame.draw.rect(self.screen, col, seg, border_radius=2)
                draw_text(self.screen, self.font_sm, anim.name[:6],
                          (seg.x + 2, seg.y + 2), TEXT)
            y += bar_h + 8

            # Current frame marker
            if total > 0:
                marker_x = px+12 + int(self.frame / total * bar_w)
                pygame.draw.line(self.screen, HIGHLIGHT,
                                 (marker_x, y - bar_h - 10), (marker_x, y - 4), 2)
        return y

    # ── draw viewport ─────────────────────────────────────────────────────────
    def draw_viewport(self, vw, sh):
        view = pygame.Rect(0, 0, vw, sh)
        if   self.bg_mode == 0: checker(self.screen, view)
        elif self.bg_mode == 1: pygame.draw.rect(self.screen, (0,0,0), view)
        elif self.bg_mode == 2: pygame.draw.rect(self.screen, (255,255,255), view)
        else:                   pygame.draw.rect(self.screen, self.bg_custom, view)

        if not self.sheet:
            draw_text(self.screen, self.font_lg, "Drop PNG or press O",
                      view.center, TEXT_DIM, "center")
            return

        fw, fh = self.frame_size
        z = float(self.pixel_scale) if self.pixel_scale > 0 else self.zoom
        dw, dh = max(1, int(fw * z)), max(1, int(fh * z))
        strip_top = sh - STRIP_H - 6

        if self.show_compare and self.compare_sheet:
            self._draw_compare(vw, strip_top, dw, dh, fw, fh, z)
        else:
            cx = vw // 2 - dw // 2
            cy = strip_top // 2 - dh // 2
            dest = pygame.Rect(cx, cy, dw, dh)

            # Background sprite
            if self.bg_sprite:
                bw, bh = self.bg_sprite.get_size()
                bg_scaled = pygame.transform.scale(self.bg_sprite,
                    (int(bw * z), int(bh * z)))
                self.screen.blit(bg_scaled,
                    (vw//2 - bg_scaled.get_width()//2,
                     strip_top//2 - bg_scaled.get_height()//2))

            # Onion skin
            if self.onion and self.display_total > 1:
                prev = max(self.range_start, self.frame - 1)
                prev_surf = pygame.Surface((dw, dh), pygame.SRCALPHA)
                raw = self.get_frame_surface(prev)
                if self.pixel_scale > 0:
                    prev_scaled = pygame.transform.scale(raw, (dw, dh))
                else:
                    prev_scaled = pygame.transform.scale(raw, (dw, dh))
                prev_surf.blit(prev_scaled, (0,0))
                tint = pygame.Surface((dw, dh), pygame.SRCALPHA)
                tint.fill((50, 80, 200, 120))
                prev_surf.blit(tint, (0,0), special_flags=pygame.BLEND_RGBA_MULT)
                self.screen.blit(prev_surf, dest)

            # Current frame
            frame_surf = self.get_frame_surface(self.frame)
            if self.pixel_scale > 0:
                scaled = pygame.transform.scale(frame_surf, (dw, dh))
            else:
                scaled = pygame.transform.scale(frame_surf, (dw, dh))
            self.screen.blit(scaled, dest)
            pygame.draw.rect(self.screen, ACCENT, dest, 1, border_radius=2)

            # Pixel grid overlay
            if self.show_grid and z >= 4:
                for gx in range(fw + 1):
                    x = dest.x + int(gx * z)
                    pygame.draw.line(self.screen, (80, 80, 100, 60),
                                     (x, dest.y), (x, dest.bottom))
                for gy in range(fh + 1):
                    y_line = dest.y + int(gy * z)
                    pygame.draw.line(self.screen, (80, 80, 100, 60),
                                     (dest.x, y_line), (dest.right, y_line))

            # Trim rect
            if self._trim_computed:
                actual = self.get_actual(self.frame)
                if actual < len(self._trim_rects):
                    tr = self._trim_rects[actual]
                    trim_r = pygame.Rect(dest.x+int(tr.x*z), dest.y+int(tr.y*z),
                                         int(tr.w*z), int(tr.h*z))
                    pygame.draw.rect(self.screen, GREEN, trim_r, 1)

            # Origin
            if self.frame in self._origins:
                ox, oy = self._origins[self.frame]
                mx_o, my_o = dest.x + int(ox * z), dest.y + int(oy * z)
                pygame.draw.circle(self.screen, CYAN, (mx_o, my_o), 5, 2)
                pygame.draw.line(self.screen, CYAN, (mx_o-8, my_o), (mx_o+8, my_o))
                pygame.draw.line(self.screen, CYAN, (mx_o, my_o-8), (mx_o, my_o+8))

            # Hitbox
            if self.frame in self._hitboxes:
                hx, hy, hw, hh = self._hitboxes[self.frame]
                hb_r = pygame.Rect(dest.x+int(hx*z), dest.y+int(hy*z),
                                   int(hw*z), int(hh*z))
                pygame.draw.rect(self.screen, RED, hb_r, 2)

            # Label
            draw_text(self.screen, self.font_sm,
                      f"#{self.frame}  [{fw}x{fh}]  {z:.0f}x",
                      (dest.x+4, dest.y+4), HIGHLIGHT)

        # ── Film strip ────────────────────────────────────────────────────────
        strip_bg = pygame.Rect(0, strip_top, vw, STRIP_H + 6)
        pygame.draw.rect(self.screen, (15, 15, 25), strip_bg)
        pygame.draw.line(self.screen, ACCENT, (0, strip_top), (vw, strip_top))

        thumb_w = max(8, int(STRIP_H * fw / max(1, fh)))
        visible = max(1, vw // (thumb_w + 4))
        dt = self.display_total
        half = visible // 2
        start = max(0, self.frame - half)
        start = min(start, max(0, dt - visible))
        draw_x = (vw - visible * (thumb_w + 4)) // 2

        # Anim state color segments on strip
        anim_colors = {}
        colors_list = [ACCENT, GREEN, ORANGE, PURPLE, CYAN, RED, YELLOW, ACCENT2]
        for ai, anim in enumerate(self.anim_states):
            for fi in range(anim.start, anim.end + 1):
                anim_colors[fi] = colors_list[ai % len(colors_list)]

        for i in range(visible):
            fi = start + i
            if fi >= dt: break
            actual = self.get_actual(fi)
            thumb = pygame.transform.scale(
                self.sheet.subsurface(self.frame_rect(actual)), (thumb_w, STRIP_H))
            if self.flip_h or self.flip_v:
                thumb = pygame.transform.flip(thumb, self.flip_h, self.flip_v)
            tr = pygame.Rect(draw_x + i*(thumb_w+4), strip_top+4, thumb_w, STRIP_H-2)
            self.screen.blit(thumb, tr)

            if fi == self.frame:             border = HIGHLIGHT
            elif actual in self._duplicates: border = RED
            elif fi in anim_colors:          border = anim_colors[fi]
            elif fi == self.range_start or fi == self.range_end: border = ORANGE
            else:                            border = (50, 50, 70)
            pygame.draw.rect(self.screen, border, tr, 1 if fi != self.frame else 2)
            draw_text(self.screen, self.font_sm, str(fi),
                      (tr.centerx, tr.bottom+1), TEXT_DIM, "midtop")

    def _draw_compare(self, vw, strip_top, dw, dh, fw, fh, z):
        half_w = vw // 2
        cx1 = half_w // 2 - dw // 2
        cy = strip_top // 2 - dh // 2
        frame_surf = self.get_frame_surface(self.frame)
        scaled = pygame.transform.scale(frame_surf, (dw, dh))
        dest1 = pygame.Rect(cx1, cy, dw, dh)
        self.screen.blit(scaled, dest1)
        pygame.draw.rect(self.screen, ACCENT, dest1, 1)
        draw_text(self.screen, self.font_sm, f"Main #{self.frame}",
                  (dest1.x+4, dest1.y+4), HIGHLIGHT)

        cw, ch = self.compare_sheet.get_size()
        cfw = cw // max(1, 4); cfh = ch // max(1, 4)
        cdw, cdh = max(1, int(cfw * z)), max(1, int(cfh * z))
        cx2 = half_w + half_w // 2 - cdw // 2
        cc = self.compare_frame % 4; cr = self.compare_frame // 4
        crect = pygame.Rect(cc*cfw, cr*cfh, cfw, cfh)
        if crect.right <= cw and crect.bottom <= ch:
            cscaled = pygame.transform.scale(self.compare_sheet.subsurface(crect), (cdw, cdh))
            dest2 = pygame.Rect(cx2, cy, cdw, cdh)
            self.screen.blit(cscaled, dest2)
            pygame.draw.rect(self.screen, CYAN, dest2, 1)
            draw_text(self.screen, self.font_sm, f"Compare #{self.compare_frame}",
                      (dest2.x+4, dest2.y+4), CYAN)
        pygame.draw.line(self.screen, ACCENT, (half_w, 0), (half_w, strip_top), 2)

    # ── master draw ───────────────────────────────────────────────────────────
    def draw(self):
        sw, sh = self.screen.get_size()
        px = sw - PANEL_W
        self.screen.fill(BG)
        self.draw_viewport(px, sh)
        self.draw_panel(px, sh)
        pygame.display.flip()

    # ── events ────────────────────────────────────────────────────────────────
    def on_click(self, mx, my):
        B = self._all_btns
        def hit(n): return n in B and B[n].collidepoint(mx,my)

        if hit("open"):      p = open_file(); p and self.load(p)
        elif hit("save_proj"): self.save_project()
        elif hit("load_proj"): self.load_project()
        elif hit("auto"):   self.auto_detect()
        elif hit("onion"):  self.onion = not self.onion
        elif hit("pgrid"):  self.show_grid = not self.show_grid
        elif hit("flip_h"): self.flip_h = not self.flip_h
        elif hit("flip_v"): self.flip_v = not self.flip_v
        elif hit("zoom_fit"): self.zoom_to_fit()
        elif hit("play"):
            self.playing = not self.playing
            if self.playing: self.done_once = False
        elif hit("prev"):
            self.playing = False
            self.frame = max(self.range_start, self.frame-1) if self.frame > self.range_start else self.range_end
        elif hit("next"):
            self.playing = False
            m = self.display_total - 1
            self.frame = self.frame+1 if self.frame < min(self.range_end, m) else self.range_start

        elif hit("exp_gif"):    self.export_gif()
        elif hit("exp_webp"):   self.export_webp()
        elif hit("exp_png"):    self.export_png_seq()
        elif hit("exp_json"):   self.export_atlas()
        elif hit("exp_packed"): self.export_packed()
        elif hit("exp_anims"):  self.export_anim_json()
        elif hit("exp_batch"):  self.batch_export()
        elif hit("exp_merge"):  self.merge_sheets()

        elif hit("dupes"):   self.compute_duplicates()
        elif hit("palette"): self.compute_palette()
        elif hit("trim"):    self.compute_trim()
        elif hit("move_l"):  self.move_frame(-1)
        elif hit("move_r"):  self.move_frame(1)
        elif hit("del_f"):   self.delete_frame()
        elif hit("undo"):    self.undo_reorder()
        elif hit("draw_hb"):
            self._editing_hitbox = not self._editing_hitbox; self._hb_start = None
        elif hit("remap_from"): self._remap_from = pick_color(self._remap_from or (255,0,0))
        elif hit("remap_to"):   self._remap_to = pick_color(self._remap_to or (0,0,255))
        elif hit("apply_swap"): self.apply_palette_swap()
        elif hit("undo_swap"):  self.undo_palette_swap()
        elif hit("copy_origin"): self.copy_origin_to_all()
        elif hit("copy_hb"):    self.copy_hitbox_to_all()
        elif hit("compare"):
            if self.compare_sheet: self.show_compare = not self.show_compare
            else: self.load_compare()
        elif hit("bg_sprite"): self.load_bg_sprite()
        elif hit("bg_pick"): self.bg_custom = pick_color(self.bg_custom)
        elif hit("prefix_edit"):
            v = ask_string("Prefix", "Atlas sprite prefix:", self.sprite_prefix)
            if v is not None: self.sprite_prefix = v
        elif hit("anim_add"): self.add_anim_state()
        elif hit("frame_dur"): self.set_frame_duration()

        # Scale buttons
        for i in range(5):
            if hit(f"scale_{i}"): self.pixel_scale = i

        # Tabs
        for i in range(len(TABS)):
            if hit(f"tab_{i}"): self.active_tab = i
        for i in range(len(PLAY_MODES)):
            if hit(f"mode_{i}"):
                self.play_mode = i; self.done_once = False; self.direction = 1
        for i in range(len(BG_MODES)):
            if hit(f"bg_{i}"): self.bg_mode = i

        # Anim state buttons
        for i in range(len(self.anim_states)):
            if hit(f"anim_play_{i}"): self.play_anim_state(i)
            if hit(f"anim_del_{i}"): self.delete_anim_state(i)

        # Recent files
        for i in range(min(4, len(self.recent_files))):
            if hit(f"recent_{i}"):
                rp = self.recent_files[i]
                if rp.endswith(".sproj"):
                    self.load_project(rp)
                else:
                    self.load(rp)

        # Viewport clicks (hitbox editing)
        sw, sh_s = self.screen.get_size()
        px_p = sw - PANEL_W
        strip_top = sh_s - STRIP_H - 6
        if mx < px_p and my < strip_top:
            fc = self._viewport_to_frame(mx, my)
            if fc and self._editing_hitbox:
                if self._hb_start is None:
                    self._hb_start = fc
                    self.show_msg(f"Start: {fc} (click end)")
                else:
                    x1, y1 = self._hb_start; x2, y2 = fc
                    hx, hy = min(x1,x2), min(y1,y2)
                    hw, hh = abs(x2-x1)+1, abs(y2-y1)+1
                    self._hitboxes[self.frame] = (hx, hy, hw, hh)
                    self._editing_hitbox = False; self._hb_start = None
                    self.show_msg(f"Hitbox: ({hx},{hy}) {hw}x{hh}")

        # Film strip click
        if 0 <= mx < px_p and strip_top <= my < sh_s:
            fw, fh = self.frame_size
            thumb_w = max(8, int(STRIP_H * fw / max(1, fh)))
            vis = max(1, px_p // (thumb_w + 4))
            half = vis // 2; dt = self.display_total
            st = max(0, min(self.frame - half, max(0, dt - vis)))
            dx = (px_p - vis*(thumb_w+4)) // 2
            idx = (mx - dx) // (thumb_w + 4)
            fi = st + idx
            if 0 <= fi < dt: self.frame = fi; self.playing = False

    def on_right_click(self, mx, my):
        fc = self._viewport_to_frame(mx, my)
        if fc:
            self._origins[self.frame] = fc
            self.show_msg(f"Origin: {fc}")

    def on_key(self, key, mods):
        for inp in self._grid_inputs + self._playback_inputs:
            if inp.active: return
        ctrl = mods & KMOD_CTRL

        if   key == K_ESCAPE: return "quit"
        elif key == K_o:     p = open_file(); p and self.load(p)
        elif key == K_g:     self.export_gif()
        elif key == K_w:     self.export_webp()
        elif key == K_p:     self.export_png_seq()
        elif key == K_j:     self.export_atlas()
        elif key == K_n:     self.onion = not self.onion
        elif key == K_b:     self.bg_mode = (self.bg_mode + 1) % len(BG_MODES)
        elif key == K_f:     self.zoom_to_fit()
        elif key == K_t:     self.compute_trim()
        elif key == K_d:     self.compute_duplicates()
        elif key == K_h:     self.flip_h = not self.flip_h
        elif key == K_v and not ctrl: self.flip_v = not self.flip_v
        elif key == K_c:
            if self.compare_sheet: self.show_compare = not self.show_compare
            else: self.load_compare()
        elif key == K_s and ctrl: self.save_project()
        elif key == K_z and ctrl:
            if self._sheet_backup: self.undo_palette_swap()
            else: self.undo_reorder()
        elif key == K_DELETE: self.delete_frame()
        elif key == K_SPACE:
            self.playing = not self.playing
            if self.playing: self.done_once = False
        elif key == K_r:
            self.frame = self.range_start; self.acc = 0; self.direction = 1; self.done_once = False
        elif key == K_LEFT:  self.playing = False; self.frame = max(self.range_start, self.frame-1)
        elif key == K_RIGHT: self.playing = False; self.frame = min(self.range_end, self.frame+1)
        elif key == K_UP:    self.fps_inp.value = min(120, self.fps_inp.value + 5)
        elif key == K_DOWN:  self.fps_inp.value = max(1, self.fps_inp.value - 5)
        elif key == K_1:     self.pixel_scale = 1
        elif key == K_2:     self.pixel_scale = 2
        elif key == K_3:     self.pixel_scale = 3
        elif key == K_4:     self.pixel_scale = 4
        elif key == K_0:     self.pixel_scale = 0

    # ── main loop ─────────────────────────────────────────────────────────────
    def run(self):
        all_inputs = self._grid_inputs + self._playback_inputs
        while True:
            dt = self.clock.tick(60) / 1000.0
            for event in pygame.event.get():
                if event.type == QUIT: pygame.quit(); return
                if event.type == DROPFILE: self.load(event.file)
                if event.type == MOUSEWHEEL:
                    self.zoom = max(0.05, min(16.0, self.zoom + event.y * 0.12))
                    self.pixel_scale = 0
                if event.type == MOUSEBUTTONDOWN and event.button == 1:
                    for inp in all_inputs: inp.click(*event.pos)
                    self.on_click(*event.pos)
                if event.type == MOUSEBUTTONDOWN and event.button == 3:
                    self.on_right_click(*event.pos)
                if event.type == KEYDOWN:
                    for inp in all_inputs:
                        if inp.active: inp.handle(event); break
                    else:
                        if self.on_key(event.key, pygame.key.get_mods()) == "quit":
                            pygame.quit(); return
            self.update(dt)
            self.draw()


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    SpriteAnimator(path).run()
