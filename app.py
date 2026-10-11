#!/usr/bin/env python3
"""
Shogi Openings Explorer — Optimized Single-file PySide6 application.
Key improvements:
- SQLite-backed DataProvider for fast opening loads
- Paginated openings list (virtual scrolling)
- Batch rendering with checkbox selection + range select
- Title card & end screen preview widgets
- Tabbed settings dialog
- Authentic 9x9 Shogi board rendering with Kanji pieces and drop animations
"""
import sys, os, re, ast, base64, json, csv, math, time, wave, logging, zlib
import shutil, subprocess, tempfile, threading, sqlite3
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
import numpy as np
import shogi
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QListWidget, QListWidgetItem,
    QSlider, QComboBox, QCheckBox, QGroupBox, QSplitter,
    QStatusBar, QLineEdit, QProgressBar, QSpinBox, QFileDialog,
    QTabWidget, QScrollArea, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QDialog, QDialogButtonBox,
    QToolTip, QFrame, QGridLayout, QSizePolicy, QToolButton, QDoubleSpinBox
)
from PySide6.QtCore import (
    Qt, QTimer, Signal, QThread, QUrl, QRect, QRectF, QPointF,
    QSortFilterProxyModel, QAbstractTableModel, QModelIndex,
)
from PySide6.QtGui import (
    QPainter, QPixmap, QPalette, QColor, QFont, QPen, QBrush,
    QRadialGradient, QLinearGradient, QImage, QPolygonF, QPainterPath,
    QTransform, QAction, QIcon, QFontMetrics,
)

# ═══════════════════════════════════════════════════════════════════════════════
#  OPTIONAL DEPENDENCIES
# ═══════════════════════════════════════════════════════════════════════════════
HAS_NUMPY = True
HAS_IMAGEIO = False
try:
    import imageio.v3 as iio; HAS_IMAGEIO = True
except Exception: pass
HAS_PANDAS = False; HAS_PYARROW = False; HAS_DUCKDB = False
try:
    import pandas as pd; HAS_PANDAS = True
except ImportError: pass
if not HAS_PANDAS:
    try:
        import pyarrow.parquet as pq; HAS_PYARROW = True
    except ImportError: pass
try:
    import duckdb; HAS_DUCKDB = True
except ImportError: pass
HAS_NUMBA = False
try:
    import numba; HAS_NUMBA = True
except ImportError: pass
HAS_CUPY = False
try:
    import cupy as cp; HAS_CUPY = True
except Exception: pass
HAS_FFMPEG = shutil.which('ffmpeg') is not None
HAS_MOVIEPY = False
try:
    import moviepy; HAS_MOVIEPY = True
except ImportError: pass

# ═══════════════════════════════════════════════════════════════════════════════
#  LOGGING
# ═══════════════════════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s.%(msecs)03d] [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

def log(msg, level="INFO"):
    level_map = {
        "INFO": logging.INFO, "WARN": logging.WARNING, "WARNING": logging.WARNING,
        "ERROR": logging.ERROR, "DATA": logging.INFO, "DEBUG": logging.DEBUG
    }
    logger.log(level_map.get(level.upper(), logging.INFO), msg)

# ═══════════════════════════════════════════════════════════════════════════════
#  FILE PATHS
# ═══════════════════════════════════════════════════════════════════════════════
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "data")
EXPORT_DIR = os.path.join(APP_DIR, "exports")
DB_OPENINGS_PATH = os.path.join(DATA_DIR, "cache_openings.parquet")
LICHESS_DB_PATH = os.path.join(DATA_DIR, "lichess_db_openings.parquet")
EXPORT_MANIFEST_PATH = os.path.join(APP_DIR, "export_manifest.json")
SQLITE_DB_PATH = os.path.join(DATA_DIR, "openings.db")

# ═══════════════════════════════════════════════════════════════════════════════
#  BOARD / RENDERING CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════
SQ_SIZE   = 64
BOARD_PX  = SQ_SIZE * 9
FILES_STR = '987654321'
RANKS_STR = '987654321'
ANIM_SPEED_SLOW    = 500
ANIM_SPEED_DEFAULT = 250
ANIM_SPEED_FAST    = 100
ANIM_FPS           = 60

SHOGI_PIECE_KANJI = {
    'P': '歩', 'p': '歩', '+P': 'と',
    'L': '香', 'l': '香', '+L': '成香',
    'N': '桂', 'n': '桂', '+N': '成桂',
    'S': '銀', 's': '銀', '+S': '成銀',
    'G': '金', 'g': '金',
    'B': '角', 'b': '角', '+B': '馬',
    'R': '飛', 'r': '飛', '+R': '龍',
    'K': '王', 'k': '玉',
}

# ═══════════════════════════════════════════════════════════════════════════════
#  ARROW STYLES
# ═══════════════════════════════════════════════════════════════════════════════
ARROW_STYLE_SIMPLE  = "simple"
ARROW_STYLE_THICK   = "thick"
ARROW_STYLE_FANCY   = "fancy"
ARROW_STYLE_MINIMAL = "minimal"
ARROW_STYLE_NONE    = "none"
ARROW_STYLES = {
    "Thick":          ARROW_STYLE_THICK,
    "Fancy":          ARROW_STYLE_FANCY,
    "Simple":         ARROW_STYLE_SIMPLE,
    "Minimal":        ARROW_STYLE_MINIMAL,
    "None":           ARROW_STYLE_NONE,
}
ARROW_STYLES_LIST = list(ARROW_STYLES.keys())

# ═══════════════════════════════════════════════════════════════════════════════
#  BOARD THEMES
# ═══════════════════════════════════════════════════════════════════════════════
class BoardTheme:
    def __init__(self, name="Classic",
                 light=(235, 215, 180), dark=(220, 200, 165),
                 border=(48, 26, 7), highlight=(255, 255, 0, 100),
                 last_move=(155, 199, 0, 100), arrow=(220, 50, 47, 200), arrow_style=ARROW_STYLE_THICK):
        self.name = name; self.light_sq = QColor(*light)
        self.dark_sq = QColor(*dark); self.border = QColor(*border)
        self.highlight = QColor(*highlight); self.last_move = QColor(*last_move)
        self.arrow_clr = QColor(*arrow)
        self.arrow_style = arrow_style
        self.bg = QColor(32, 32, 36); self.coord = QColor(180, 160, 130)

THEMES = {
    "Classic": BoardTheme(),
    "Green":   BoardTheme("Green", (238, 238, 210), (218, 218, 190), (50, 60, 40)),
    "Wood":    BoardTheme("Wood", (222, 197, 165), (210, 185, 155), (60, 35, 15)),
    "Dark":    BoardTheme("Dark", (80, 80, 90), (60, 60, 70), (30, 30, 30)),
}

# ═══════════════════════════════════════════════════════════════════════════════
#  EXPORT PRESETS
# ═══════════════════════════════════════════════════════════════════════════════
class ExportPreset:
    def __init__(self, name, width, height, fps=30, board_frac=0.82,
                 bg=(26, 26, 46), description=""):
        self.name = name; self.width = width; self.height = height
        self.fps = fps; self.board_frac = board_frac
        self.bg = bg; self.description = description

    @property
    def is_vertical(self): return self.height > self.width
    @property
    def is_square(self): return self.width == self.height
    @property
    def is_board_only(self): return self.board_frac >= 1.0

    def calc_sq_size(self):
        if self.is_vertical:
            board_px = int(self.width * self.board_frac)
        else:
            board_px = int(self.height * 0.78 * self.board_frac / 0.82)
        board_px = (board_px // 9) * 9
        return max(9, board_px // 9)

EXPORT_PRESETS = {
    "YouTube 1080p":    ExportPreset("YouTube 1080p",    1920, 1080, 30, 0.60, (26, 26, 46), "16:9 Full HD"),
    "YouTube 720p":     ExportPreset("YouTube 720p",     1280,  720, 30, 0.60, (26, 26, 46), "16:9 HD"),
    "YouTube 4K":       ExportPreset("YouTube 4K",       3840, 2160, 30, 0.60, (26, 26, 46), "16:9 4K"),
    "YouTube Shorts":   ExportPreset("YouTube Shorts",   1080, 1920, 30, 0.70, (26, 26, 46), "9:16 vertical"),
    "TikTok":           ExportPreset("TikTok",           1080, 1920, 30, 0.70, (26, 26, 46), "9:16 vertical"),
    "Instagram Reels":  ExportPreset("Instagram Reels",  1080, 1920, 30, 0.70, (26, 26, 46), "9:16 vertical"),
    "Instagram Square": ExportPreset("Instagram Square", 1080, 1080, 30, 0.65, (26, 26, 46), "1:1 square"),
    "Board Only":       ExportPreset("Board Only",        576,  576, 30, 1.00, (26, 26, 46), "Square board-only"),
}

# ═══════════════════════════════════════════════════════════════════════════════
#  EXPORT CONFIG
# ═══════════════════════════════════════════════════════════════════════════════
SETTINGS_JSON_PATH = os.path.join(APP_DIR, "settings.json")
class ExportConfig:
    def __init__(self):
        self.fps = 30
        self.title_enabled = True; self.title_duration = 3.0
        self.end_title_enabled = True; self.end_title_duration = 3.0
        self.move_anim_duration = 0.5; self.pause_after_move = 0.8
        self.preset_name = "YouTube 1080p"
        self.theme_name = "Classic"
        self.arrow_style = ARROW_STYLE_THICK
        self.ffmpeg_crf = 20; self.ffmpeg_preset = "medium"
        self.title_text_override = ""
        self.end_screen_text = ""
        self.flip_board = False
        self._bg_color = None
        self.output_dir = EXPORT_DIR
        self.load()

    def apply_preset(self, name):
        if name in EXPORT_PRESETS:
            p = EXPORT_PRESETS[name]; self.preset_name = name
            self.fps = p.fps

    @property
    def preset(self):
        return EXPORT_PRESETS.get(self.preset_name, EXPORT_PRESETS["YouTube 1080p"])

    @property
    def target_width(self): return self.preset.width
    @property
    def target_height(self): return self.preset.height

    @property
    def bg_color(self):
        return self._bg_color if self._bg_color is not None else self.preset.bg

    @bg_color.setter
    def bg_color(self, value):
        self._bg_color = value

    @property
    def is_vertical(self): return self.preset.is_vertical
    @property
    def sq_size(self): return self.preset.calc_sq_size()

    def save(self):
        try:
            os.makedirs(os.path.dirname(SETTINGS_JSON_PATH), exist_ok=True)
            data = {}
            for k, v in self.__dict__.items():
                if k == '_bg_color':
                    data['bg_color_override'] = list(v) if v is not None else None
                elif not k.startswith('_'):
                    if isinstance(v, Path): v = str(v)
                    data[k] = v
            with open(SETTINGS_JSON_PATH, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            log(f"Failed to save settings: {e}", "ERROR")

    def load(self):
        if not os.path.exists(SETTINGS_JSON_PATH): return
        try:
            with open(SETTINGS_JSON_PATH, 'r') as f:
                data = json.load(f)
            for k, v in data.items():
                if k == 'bg_color_override':
                    self._bg_color = tuple(v) if v is not None else None
                elif hasattr(self, k):
                    setattr(self, k, v)
        except Exception as e:
            log(f"Failed to load settings: {e}", "WARN")

# ═══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════════
_SAFE_FS = re.compile(r'[\\/*?:"<>|]')

def _qimage_to_bgr_bytes(img):
    if img.format() != QImage.Format_RGB888:
        img = img.convertToFormat(QImage.Format_RGB888)
    w = img.width(); h = img.height(); bpl = img.bytesPerLine()
    ptr = img.constBits()
    raw = np.frombuffer(ptr, dtype=np.uint8, count=img.sizeInBytes()).reshape((h, bpl)).copy()
    if bpl > w * 3:
        raw = raw[:, :w * 3]
    arr = raw.reshape((h, w, 3))
    return arr[:, :, ::-1].tobytes()

def sanitize_filename(name, max_len=120):
    s = _SAFE_FS.sub('_', name).strip('. ')
    return s[:max_len] if s else "untitled"

def _ease_out_cubic(t):
    return 1.0 - (1.0 - t) ** 3

def _to_i16(samples):
    return np.clip(samples * 32767.0, -32768, 32767).astype(np.int16)

@contextmanager
def paint_context(image):
    p = QPainter(image)
    try:
        yield p
    finally:
        if p.isActive():
            p.end()

def _font_family_sans():
    return "Segoe UI, sans-serif"

def _font_family_mono():
    return "Consolas, Courier New, monospace"

def _make_font(family, size_px, bold=False):
    font = QFont(family, -1, QFont.Bold if bold else QFont.Normal)
    font.setPixelSize(int(size_px))
    return font

# ═══════════════════════════════════════════════════════════════════════════════
#  ENGINE
# ═══════════════════════════════════════════════════════════════════════════════
class ShogiEngine:
    def __init__(self):
        self.board = shogi.Board()
        self.game_over = False; self.result = ""; self.last_move = None

    def reset(self):
        self.board.reset(); self.game_over = False
        self.result = ""; self.last_move = None

    @staticmethod
    def sq_to_rc(sq):
        return 8 - shogi.square_rank(sq), shogi.square_file(sq)

    @staticmethod
    def rc_to_sq(r, c):
        rank = 8 - r
        file = c
        return rank * 9 + file

    @property
    def turn(self): return 'b' if self.board.turn == shogi.BLACK else 'w'

    def check_squares(self):
        if self.board.is_check():
            king_sq = self.board.king(self.board.turn)
            if king_sq is not None:
                return [self.sq_to_rc(king_sq)]
        return []

    def legal_moves(self, r, c):
        sq = self.rc_to_sq(r, c)
        return [self.sq_to_rc(m.to_square) for m in self.board.legal_moves if m.from_square == sq]

    def make_move(self, fr, fc, tr, tc, promo=None):
        from_sq = self.rc_to_sq(fr, fc); to_sq = self.rc_to_sq(tr, tc)
        piece = self.board.piece_at(from_sq)
        if not piece: return None
        
        promotion = bool(promo)
        move = shogi.Move(from_sq, to_sq, promotion)
        if move not in self.board.legal_moves: return None
        
        captured = self.board.piece_at(to_sq)
        captured_sym = captured.symbol() if captured else '.'
        notation = self.board.san(move)
        piece_obj = shogi.Piece(piece.piece_type, piece.color)
        
        self.board.push(move); self.last_move = ((fr, fc), (tr, tc))
        self.game_over = self.board.is_game_over()
        self.result = self.board.result() if self.game_over else ""
        
        return {'from': (fr, fc), 'to': (tr, tc), 'piece': piece.symbol(),
                'piece_obj': piece_obj, 'captured': captured_sym,
                'castle': False, 'ep': False, 'promo': promotion,
                'check': self.board.is_check(), 'mate': self.board.is_checkmate(),
                'notation': notation}

    def make_move_usi(self, usi_str):
        try:
            move = shogi.Move.from_usi(usi_str)
        except Exception:
            return None
            
        if move in self.board.legal_moves:
            if move.from_square is None:
                # Drop move
                tr, tc = self.sq_to_rc(move.to_square)
                piece_obj = shogi.Piece(move.piece_type, self.board.turn)
                notation = self.board.san(move)
                
                self.board.push(move)
                self.last_move = (None, (tr, tc))
                self.game_over = self.board.is_game_over()
                self.result = self.board.result() if self.game_over else ""
                
                return {
                    'from': (-1, tc), 'to': (tr, tc), 'piece': piece_obj.symbol(),
                    'piece_obj': piece_obj, 'captured': '.',
                    'castle': False, 'ep': False, 'promo': move.promotion,
                    'check': self.board.is_check(), 'mate': self.board.is_checkmate(),
                    'notation': notation
                }
            else:
                fr, fc = self.sq_to_rc(move.from_square)
                tr, tc = self.sq_to_rc(move.to_square)
                return self.make_move(fr, fc, tr, tc, move.promotion)
        return None

    def undo(self):
        if len(self.board.move_stack) > 0:
            self.board.pop()
            self.game_over = self.board.is_game_over()
            self.result = self.board.result() if self.game_over else ""
            if self.board.move_stack:
                last = self.board.move_stack[-1]
                if last.from_square is not None:
                    self.last_move = (self.sq_to_rc(last.from_square), self.sq_to_rc(last.to_square))
                else:
                    self.last_move = (None, self.sq_to_rc(last.to_square))
            else:
                self.last_move = None
            return True
        return False

# ═══════════════════════════════════════════════════════════════════════════════
#  RENDERING
# ═══════════════════════════════════════════════════════════════════════════════
_tl = threading.local()
def get_render_assets(sz):
    isz = int(sz * 100)
    if getattr(_tl, 'cache_sz', -1) == isz: return _tl.assets
    fp = QFont("Yu Gothic, Meiryo, sans-serif", sz * 0.9); fp.setStyleStrategy(QFont.PreferAntialias)
    fc = QFont("Yu Gothic, Meiryo, sans-serif", max(7, int(sz * 0.13)), QFont.Bold)
    fb1 = QFont("Yu Gothic, Meiryo, sans-serif", max(6, int(sz * 0.19 * 0.95)), QFont.Bold)
    fb2 = QFont("Yu Gothic, Meiryo, sans-serif", max(7, int(sz * 0.19 * 1.15)), QFont.Bold)
    pb = QPen(QColor(255, 255, 255, 120), max(0.8, sz * 0.008))
    _tl.assets = (fp, fc, fb1, fb2, pb); _tl.cache_sz = isz
    return _tl.assets

_piece_cache = {}
def get_cached_piece(piece_obj, sz, font):
    key = (piece_obj.piece_type, piece_obj.color, piece_obj.promoted, sz)
    if key not in _piece_cache:
        pixmap = QPixmap(sz, sz)
        pixmap.fill(Qt.transparent)
        with paint_context(pixmap) as p:
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.TextAntialiasing)
            _draw_piece_at_core(p, piece_obj, 0.0, 0.0, sz, sz, sz, font)
        _piece_cache[key] = pixmap
    return _piece_cache[key]

def _draw_piece_at_core(p, piece_obj, row_f, col_f, sz, w, h, font):
    FIT_FRAC = 0.85
    is_black = piece_obj.color == shogi.BLACK
    glyph = SHOGI_PIECE_KANJI.get(piece_obj.symbol(), "?")
    px = col_f * sz
    py = row_f * sz
    rect = QRectF(px + (sz - w) / 2, py + (sz - h) / 2, w, h)
    center = rect.center()
    p.setFont(font)
    path = QPainterPath()
    path.addText(QPointF(0, 0), font, glyph)
    br = path.boundingRect()
    path.translate(-br.center().x(), -br.center().y())
    if br.width() > 0 and br.height() > 0:
        s = min((w * FIT_FRAC) / br.width(), (h * FIT_FRAC) / br.height())
        path = QTransform.fromScale(s, s).map(path)
        path.translate(center.x(), center.y())
    
    # Rotate 180 degrees for Gote (White) pieces so they point toward Sente
    if not is_black:
        transform = QTransform()
        transform.translate(center.x(), center.y())
        transform.rotate(180)
        transform.translate(-center.x(), -center.y())
        path = transform.map(path)
    
    # Background
    p.setPen(Qt.NoPen)
    bg_color = QColor(255, 255, 255) if is_black else QColor(220, 220, 220)
    p.setBrush(bg_color)
    path_bg = QPainterPath()
    path_bg.addRoundedRect(QRectF(px + (sz-w)/2, py + (sz-h)/2, w, h), sz*0.1, sz*0.1)
    p.drawPath(path_bg)
    
    # Shadow
    shadow = QPainterPath(path)
    shadow.translate(1.5, 2.0)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawPath(shadow)
    
    # Text
    p.setPen(QPen(QColor(0, 0, 0), max(1.0, sz * 0.02), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(QColor(0, 0, 0))
    p.drawPath(path)

def _draw_piece(p, piece_obj, row, col, sz, font):
    pixmap = get_cached_piece(piece_obj, sz, font)
    p.drawPixmap(int(col * sz), int(row * sz), pixmap)

def _draw_piece_at(p, piece_obj, row_f, col_f, sz, w, h, font):
    _draw_piece_at_core(p, piece_obj, row_f, col_f, sz, w, h, font)

def _draw_arrow(painter, fx, fy, tx, ty, color, sz, style=ARROW_STYLE_THICK):
    if style == ARROW_STYLE_NONE: return
    elif style == ARROW_STYLE_SIMPLE: _draw_arrow_simple(painter, fx, fy, tx, ty, color, sz)
    elif style == ARROW_STYLE_THICK: _draw_arrow_thick(painter, fx, fy, tx, ty, color, sz)
    elif style == ARROW_STYLE_FANCY: _draw_arrow_fancy(painter, fx, fy, tx, ty, color, sz)
    elif style == ARROW_STYLE_MINIMAL: _draw_arrow_minimal(painter, fx, fy, tx, ty, color, sz)
    else: _draw_arrow_thick(painter, fx, fy, tx, ty, color, sz)

def _draw_arrow_simple(painter, fx, fy, tx, ty, color, sz):
    dx = tx - fx; dy = ty - fy; dist = max(1, math.hypot(dx, dy))
    margin = sz * 0.22
    fx2 = fx + dx * margin / dist; fy2 = fy + dy * margin / dist
    tx2 = tx - dx * margin / dist; ty2 = ty - dy * margin / dist
    painter.setPen(QPen(color, max(2, sz // 20), Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(int(fx2), int(fy2), int(tx2), int(ty2))
    angle = math.atan2(dy, dx); a_sz = sz * 0.22
    p1x = tx2 - a_sz * math.cos(angle - 0.45); p1y = ty2 - a_sz * math.sin(angle - 0.45)
    p2x = tx2 - a_sz * math.cos(angle + 0.45); p2y = ty2 - a_sz * math.sin(angle + 0.45)
    tri = QPolygonF([QPointF(tx2, ty2), QPointF(p1x, p1y), QPointF(p2x, p2y)])
    painter.setBrush(color); painter.setPen(Qt.NoPen); painter.drawPolygon(tri)

def _draw_arrow_thick(painter, fx, fy, tx, ty, color, sz):
    dx = tx - fx; dy = ty - fy; dist = max(1, math.hypot(dx, dy))
    if dist < 1: return
    ux, uy = dx / dist, dy / dist; nx, ny = -uy, ux
    shaft_half = sz * 0.09; head_half = sz * 0.22; head_len = sz * 0.28
    tail_r = sz * 0.06; margin_s = sz * 0.15; margin_e = sz * 0.06
    sx = fx + ux * margin_s; sy = fy + uy * margin_s
    ex = tx - ux * margin_e; ey = ty - uy * margin_e
    neck_x = ex - ux * head_len; neck_y = ey - uy * head_len
    path = QPainterPath()
    tail_center_x = sx; tail_center_y = sy
    arc_rect = QRectF(tail_center_x - tail_r, tail_center_y - tail_r, tail_r * 2, tail_r * 2)
    start_angle_deg = -math.degrees(math.atan2(-ny, -nx))
    path.arcMoveTo(arc_rect, start_angle_deg)
    path.arcTo(arc_rect, start_angle_deg, 180)
    path.lineTo(neck_x + nx * shaft_half, neck_y + ny * shaft_half)
    path.lineTo(neck_x + nx * head_half, neck_y + ny * head_half)
    path.lineTo(ex, ey)
    path.lineTo(neck_x - nx * head_half, neck_y - ny * head_half)
    path.lineTo(neck_x - nx * shaft_half, neck_y - ny * shaft_half)
    path.closeSubpath()
    painter.save()
    shadow_path = QPainterPath(path); shadow_path.translate(2.5, 3.0)
    painter.setPen(Qt.NoPen); painter.setBrush(QColor(0, 0, 0, 50)); painter.drawPath(shadow_path)
    arrow_clr = QColor(color); arrow_clr.setAlpha(min(arrow_clr.alpha(), 210))
    painter.setPen(QPen(arrow_clr.darker(140), max(1, sz * 0.008), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(arrow_clr); painter.drawPath(path)
    gloss = QPainterPath(); gloss.moveTo(sx + nx * shaft_half * 0.35, sy + ny * shaft_half * 0.35)
    gloss.lineTo(neck_x + nx * shaft_half * 0.35, neck_y + ny * shaft_half * 0.35)
    painter.setPen(QPen(QColor(255, 255, 255, 50), max(1, sz * 0.028), Qt.SolidLine, Qt.RoundCap))
    painter.setBrush(Qt.NoBrush); painter.drawPath(gloss)
    painter.restore()

def _draw_arrow_fancy(painter, fx, fy, tx, ty, color, sz):
    dx = tx - fx; dy = ty - fy; dist = max(1, math.hypot(dx, dy))
    if dist < 1: return
    ux, uy = dx / dist, dy / dist; nx, ny = -uy, ux
    shaft_half = sz * 0.10; head_half = sz * 0.25; head_len = sz * 0.30
    margin_s = sz * 0.15; margin_e = sz * 0.06
    sx = fx + ux * margin_s; sy = fy + uy * margin_s
    ex = tx - ux * margin_e; ey = ty - uy * margin_e
    neck_x = ex - ux * head_len; neck_y = ey - uy * head_len
    path = QPainterPath()
    path.moveTo(sx + nx * shaft_half, sy + ny * shaft_half)
    path.lineTo(neck_x + nx * shaft_half, neck_y + ny * shaft_half)
    path.lineTo(neck_x + nx * head_half, neck_y + ny * head_half)
    path.lineTo(ex, ey)
    path.lineTo(neck_x - nx * head_half, neck_y - ny * head_half)
    path.lineTo(neck_x - nx * shaft_half, neck_y - ny * shaft_half)
    path.lineTo(sx - nx * shaft_half, sy - ny * shaft_half)
    path.closeSubpath()
    painter.save()
    glow_clr = QColor(color); glow_clr.setAlpha(18)
    for i in range(4, 0, -1):
        painter.setPen(QPen(glow_clr, i * sz * 0.04, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush); painter.drawPath(path)
    shadow_path = QPainterPath(path); shadow_path.translate(2, 3)
    painter.setPen(Qt.NoPen); painter.setBrush(QColor(0, 0, 0, 60)); painter.drawPath(shadow_path)
    grad = QLinearGradient(fx, fy, tx, ty)
    lighter = QColor(color).lighter(150); lighter.setAlpha(210)
    darker = QColor(color).darker(130); darker.setAlpha(210)
    grad.setColorAt(0.0, lighter); grad.setColorAt(1.0, darker)
    painter.setPen(QPen(QColor(color).darker(160), max(1, sz * 0.008), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(QBrush(grad)); painter.drawPath(path)
    highlight = QPainterPath(); highlight.moveTo(sx + nx * shaft_half * 0.2, sy + ny * shaft_half * 0.2)
    highlight.lineTo(neck_x + nx * shaft_half * 0.2, neck_y + ny * shaft_half * 0.2)
    painter.setPen(QPen(QColor(255, 255, 255, 70), max(1, sz * 0.022), Qt.SolidLine, Qt.RoundCap))
    painter.setBrush(Qt.NoBrush); painter.drawPath(highlight)
    painter.setPen(Qt.NoPen); painter.setBrush(QColor(255, 255, 255, 55))
    painter.drawEllipse(QPointF(ex, ey), sz * 0.03, sz * 0.03)
    painter.restore()

def _draw_arrow_minimal(painter, fx, fy, tx, ty, color, sz):
    dx = tx - fx; dy = ty - fy; dist = max(1, math.hypot(dx, dy))
    if dist < 1: return
    margin = sz * 0.22
    fx2 = fx + dx * margin / dist; fy2 = fy + dy * margin / dist
    tx2 = tx - dx * margin / dist; ty2 = ty - dy * margin / dist
    subtle = QColor(color); subtle.setAlpha(130)
    painter.setPen(QPen(subtle, max(1.5, sz * 0.022), Qt.SolidLine, Qt.RoundCap))
    painter.drawLine(QPointF(fx2, fy2), QPointF(tx2, ty2))
    angle = math.atan2(dy, dx); a_sz = sz * 0.14
    p1x = tx2 - a_sz * math.cos(angle - 0.4); p1y = ty2 - a_sz * math.sin(angle - 0.4)
    p2x = tx2 - a_sz * math.cos(angle + 0.4); p2y = ty2 - a_sz * math.sin(angle + 0.4)
    tri = QPolygonF([QPointF(tx2, ty2), QPointF(p1x, p1y), QPointF(p2x, p2y)])
    painter.setBrush(subtle); painter.setPen(Qt.NoPen); painter.drawPolygon(tri)

def render_board_image(board, last_move=None, selected=None, legal_targets=None,
                       check_squares=None, anim_state=None, sq_size=SQ_SIZE,
                       show_arrow=True, theme=None, flipped=False, arrow_style=None,
                       static_only=False):
    if theme is None: theme = THEMES["Classic"]
    sz = sq_size
    img = QImage(sz * 9, sz * 9, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    with paint_context(img) as p:
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        (font_piece, font_coord, *_) = get_render_assets(sz)
        check_set = set(check_squares or []); skip_sq = set()
        if anim_state: 
            if anim_state['from'] is not None: skip_sq.add(anim_state['from'])
            skip_sq.add(anim_state['to'])
        b2s = (lambda br, bc: (8 - br, 8 - bc)) if flipped else (lambda br, bc: (br, bc))
        effective_move = None
        if anim_state: effective_move = (anim_state['from'], anim_state['to'])
        elif last_move: effective_move = last_move
        
        # 1. Draw board squares and highlights
        for sq in range(81):
            br = 8 - shogi.square_rank(sq)
            bc = shogi.square_file(sq)
            sr, sc = b2s(br, bc); x, y = sc * sz, sr * sz
            is_light = (br + bc) % 2 == 0
            p.fillRect(x, y, sz, sz, theme.light_sq if is_light else theme.dark_sq)
            if effective_move and effective_move[0] is not None and (br, bc) in effective_move: 
                p.fillRect(x, y, sz, sz, theme.last_move)
            if selected and (br, bc) == selected: 
                p.fillRect(x, y, sz, sz, theme.highlight)
            if (br, bc) in check_set:
                grad = QRadialGradient(x + sz / 2, y + sz / 2, sz * 0.7)
                grad.setColorAt(0, QColor(255, 30, 30, 180)); grad.setColorAt(1, QColor(255, 0, 0, 0))
                p.setBrush(QBrush(grad)); p.setPen(Qt.NoPen); p.drawRect(x, y, sz, sz)
            if legal_targets and (br, bc) in legal_targets:
                cx, cy = x + sz // 2, y + sz // 2
                if board.piece_at(sq) is not None:
                    p.setPen(QPen(QColor(0, 0, 0, 90), max(3, sz // 14))); p.setBrush(Qt.NoBrush)
                    p.drawEllipse(cx - sz * 5 // 12, cy - sz * 5 // 12, sz * 10 // 12, sz * 10 // 12)
                else:
                    p.setPen(Qt.NoPen); p.setBrush(QColor(0, 0, 0, 90))
                    p.drawEllipse(cx - sz // 6, cy - sz // 6, sz // 3, sz // 3)
                    
        # 2. Draw static pieces
        for sq in range(81):
            br = 8 - shogi.square_rank(sq); bc = shogi.square_file(sq)
            if (br, bc) in skip_sq: continue
            piece = board.piece_at(sq)
            if piece: 
                sr, sc = b2s(br, bc); _draw_piece(p, piece, sr, sc, sz, font_piece)
                
        if not static_only:
            # 3. Draw captured piece fade (if animating)
            if anim_state and anim_state.get('captured', '.') != '.':
                bfr, bfc_ = anim_state['from']
                btr, btc_ = anim_state['to']
                cap_piece = shogi.Piece.from_symbol(anim_state['captured']) if anim_state['captured'] != '.' else None
                if cap_piece is not None:
                    fade = max(0, int(200 * (1.0 - anim_state['progress'])))
                    p.setOpacity(fade / 255.0)
                    sr, sc = b2s(btr, btc_); _draw_piece(p, cap_piece, sr, sc, sz, font_piece)
                    p.setOpacity(1.0)
                    
            # 4. Draw arrow
            if show_arrow and effective_move and effective_move[0] is not None:
                (bfr, bfc), (btr, btc) = effective_move
                sfr, sfc = b2s(bfr, bfc); str_, stc = b2s(btr, btc)
                _draw_arrow(p, sfc * sz + sz // 2, sfr * sz + sz // 2,
                            stc * sz + sz // 2, str_ * sz + sz // 2, theme.arrow_clr, sz, arrow_style)
                            
            # 5. Draw animated piece
            if anim_state:
                bfr, bfc_ = anim_state['from']; btr, btc_ = anim_state['to']
                t = anim_state['progress']; anim_obj = anim_state.get('piece_obj')
                if anim_obj:
                    lift = 4.0 * t * (1.0 - t) * 0.20
                    scale = 1.0 + 4.0 * t * (1.0 - t) * 0.15
                    start_r = bfr if bfr is not None else -1
                    ir = start_r + (btr - start_r) * t; ic = bfc_ + (btc_ - bfc_) * t
                    sir, sic = b2s(ir, ic)
                    shadow_w = sz * 0.65 * scale; shadow_h = sz * 0.12 * scale
                    sa = 30 + int(70 * (lift / 0.20))
                    p.setPen(Qt.NoPen); p.setBrush(QColor(0, 0, 0, sa))
                    piece_center_x = sic * sz + sz / 2
                    shadow_x = piece_center_x - shadow_w / 2 + (sz * 0.05 * scale)
                    shadow_y = sir * sz + sz * 0.85
                    p.drawEllipse(QRectF(shadow_x, shadow_y, shadow_w, shadow_h))
                    _draw_piece_at(p, anim_obj, (sir * sz - sz * lift) / sz, sic, sz, sz * scale, sz * scale, font_piece)
                    
        # 6. Draw coordinates
        p.setFont(font_coord); cm = max(3, int(sz * 0.04)); cs = max(12, sz // 5)
        for c in range(9):
            is_light = (8 + c) % 2 == 0
            p.setPen(theme.dark_sq if is_light else theme.light_sq)
            p.drawText(QRect(c * sz + sz - cs - cm, 8 * sz + cm, cs, cs),
                       Qt.AlignCenter, FILES_STR[8 - c if flipped else c])
        for r in range(9):
            is_light = r % 2 == 0
            p.setPen(theme.dark_sq if is_light else theme.light_sq)
            p.drawText(QRect(cm, r * sz + cm, cs, cs),
                       Qt.AlignCenter, RANKS_STR[8 - r if flipped else r])
    return img

class CompositeLayout:
    def __init__(self, width, height, sq_size=None, is_vertical=False, is_square=False, is_board_only=False, show_title=False):
        self.w = width; self.h = height; self.vert = is_vertical; self.show_title = show_title
        self.is_board_only = is_board_only
        self.sf = min(width, height) / 1080.0
        if is_board_only: self._board_only_layout(sq_size)
        elif is_vertical: self._vert_layout(sq_size)
        else: self._horiz_layout(sq_size)

    def _make_sq(self, raw_pixels):
        return max(9, (int(raw_pixels) // 9) * 9)

    def _board_only_layout(self, sq_size):
        self.pad = max(4, int(min(self.w, self.h) * 0.01)); self.title_h = 0
        if sq_size is None:
            board_px = min(self.w, self.h) - (self.pad * 2)
            self.sq_size = self._make_sq(board_px / 9)
        else:
            self.sq_size = sq_size
        self.bpx = self.sq_size * 9
        self.bx = (self.w - self.bpx) // 2; self.by = (self.h - self.bpx) // 2
        self.mx = self.my = self.mw = self.mh = 0

    def _horiz_layout(self, sq_size):
        self.pad = max(8, int(12 * self.sf))
        self.title_h = max(44, int(80 * self.sf)) if self.show_title else 0
        gap = self.pad
        min_mw = max(180, int(220 * self.sf)); max_mw = max(280, int(self.w * 0.35))
        target_mw = min(max_mw, max(min_mw, int(280 * self.sf)))
        max_board_w = self.w - target_mw - gap - self.pad * 2
        max_board_h = self.h - self.title_h - self.pad * 3
        if sq_size is None: self.sq_size = self._make_sq(min(max_board_w, max_board_h) / 9)
        else: self.sq_size = max(9, sq_size)
        self.bpx = self.sq_size * 9
        remaining_w = self.w - self.bpx - gap - self.pad * 2
        actual_mw = max(80, remaining_w) if remaining_w < min_mw else max(min_mw, min(max_mw, remaining_w))
        total_content_w = self.bpx + gap + actual_mw
        group_x = (self.w - total_content_w) // 2
        vert_space = self.h - self.title_h - self.pad * 2
        board_y = self.title_h + self.pad + max(0, (vert_space - self.bpx) // 2)
        self.bx = group_x; self.by = board_y
        self.mx = group_x + self.bpx + gap; self.my = board_y
        self.mw = actual_mw; self.mh = self.bpx

    def _vert_layout(self, sq_size):
        self.pad = max(8, int(14 * self.sf))
        self.title_h = max(36, int(50 * self.sf)) if self.show_title else 0
        gap = self.pad
        min_mh = max(120, int(150 * self.sf)); max_mh = max(180, int(self.h * 0.35))
        target_mh = min(max_mh, max(min_mh, int(200 * self.sf)))
        max_board_w = self.w - self.pad * 2
        max_board_h = self.h - self.title_h - target_mh - gap - self.pad * 3
        if sq_size is None: self.sq_size = self._make_sq(min(max_board_w, max_board_h) / 9)
        else: self.sq_size = max(9, sq_size)
        self.bpx = self.sq_size * 9
        remaining_h = self.h - self.title_h - self.bpx - gap - self.pad * 3
        actual_mh = max(60, remaining_h) if remaining_h < min_mh else max(min_mh, min(max_mh, remaining_h))
        board_x = (self.w - self.bpx) // 2
        total_content_h = self.bpx + gap + actual_mh
        vert_space = self.h - self.title_h - self.pad * 2
        group_y = self.title_h + self.pad + max(0, (vert_space - total_content_h) // 2)
        self.bx = board_x; self.by = group_y
        self.mx = board_x; self.my = group_y + self.bpx + gap
        self.mw = self.bpx; self.mh = actual_mh

def render_composite_frame(board, notations, current_move_idx, last_move=None, check_squares=None,
                           anim_state=None, anim_move_idx=-1, width=1920, height=1080, sq_size=None, 
                           theme=None, flipped=False, bg_color=(26, 26, 46), arrow_style=None, 
                           is_board_only=False, static_board_img=None):
    is_vert = height > width; is_sq = (width == height)
    layout = CompositeLayout(width, height, sq_size=sq_size, is_vertical=is_vert, is_square=is_sq, is_board_only=is_board_only, show_title=not is_board_only)
    sq = layout.sq_size; sf = layout.sf
    img = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
    bg = QColor(*bg_color); img.fill(bg)
    with paint_context(img) as p:
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        if static_board_img is not None and anim_state is not None:
            p.drawImage(layout.bx, layout.by, static_board_img)
            p.save(); p.translate(layout.bx, layout.by)
            bfr, bfc = anim_state['from']; btr, btc = anim_state['to']
            if arrow_style != ARROW_STYLE_NONE and bfr is not None:
                b2s = (lambda br, bc: (8 - br, 8 - bc)) if flipped else (lambda br, bc: (br, bc))
                sfr, sfc = b2s(bfr, bfc); str_, stc = b2s(btr, btc)
                _draw_arrow(p, sfc * sq + sq // 2, sfr * sq + sq // 2, stc * sq + sq // 2, str_ * sq + sq // 2, theme.arrow_clr, sq, arrow_style)
            t = anim_state['progress']; anim_obj = anim_state.get('piece_obj')
            if anim_obj:
                lift = 4.0 * t * (1.0 - t) * 0.15; scale = 1.0 + 4.0 * t * (1.0 - t) * 0.08
                start_r = bfr if bfr is not None else -1
                ir = start_r + (btr - start_r) * t; ic = bfc + (btc - bfc) * t
                b2s = (lambda br, bc: (8 - br, 8 - bc)) if flipped else (lambda br, bc: (br, bc))
                sir, sic = b2s(ir, ic)
                sa = 30 + int(70 * (lift / 0.15))
                p.setPen(Qt.NoPen); p.setBrush(QColor(0, 0, 0, sa))
                p.drawEllipse(QRectF(sic * sq + (sq * scale - sq * 0.65) / 2, sir * sq + sq * 0.82, sq * 0.65, sq * 0.12))
                (font_piece, _, *_) = get_render_assets(sq)
                _draw_piece_at(p, anim_obj, sir - lift, sic, sq, sq * scale, sq * scale, font_piece)
            p.restore()
        else:
            board_img = render_board_image(board, last_move=last_move, check_squares=check_squares,
                                           anim_state=anim_state, sq_size=sq, theme=theme, flipped=flipped, arrow_style=arrow_style)
            p.drawImage(layout.bx, layout.by, board_img)
        if layout.mw > 20 and layout.mh > 20:
            display_idx = anim_move_idx if anim_move_idx >= 0 else current_move_idx
            _draw_move_list(p, notations, display_idx, layout, bg_color, sf)
    return img

def _draw_move_list(p, notations, current_idx, layout, bg_color, sf):
    mx, my, mw, mh = layout.mx, layout.my, layout.mw, layout.mh
    panel_bg = QColor(*bg_color).lighter(115)
    p.setPen(Qt.NoPen); p.setBrush(panel_bg)
    radius = max(6, int(10 * sf))
    p.drawRoundedRect(QRectF(mx, my, mw, mh), radius, radius)
    hdr_h = max(32, int(48 * sf)); hdr_fs = max(14, int(24 * sf))
    p.setFont(QFont("Sans", hdr_fs, QFont.Bold))
    p.setPen(QColor(140, 140, 160))
    p.drawText(QRectF(mx + int(16 * sf), my + int(6 * sf), mw - int(32 * sf), hdr_h), Qt.AlignVCenter | Qt.AlignLeft, "MOVES")
    sep_y = my + hdr_h + int(6 * sf)
    p.setPen(QPen(QColor(80, 80, 100), max(1.5, 1.5 * sf)))
    p.drawLine(int(mx + int(16 * sf)), int(sep_y), int(mx + mw - int(16 * sf)), int(sep_y))
    row_h = max(32, int(44 * sf)); fs = max(16, int(22 * sf))
    move_font = QFont("Monospace", fs); move_font_active = QFont("Monospace", fs, QFont.Bold)
    num_font = QFont("Sans", max(14, int(fs * 0.85)))
    content_y = sep_y + int(8 * sf); available_h = my + mh - content_y - int(12 * sf)
    max_rows = max(1, available_h // row_h)
    pairs = []
    for i in range(0, len(notations), 2):
        w_move = notations[i] if i < len(notations) else ""
        b_move = notations[i + 1] if i + 1 < len(notations) else ""
        pairs.append((i + 1, w_move, b_move, i, i + 1 if i + 1 < len(notations) else -1))
    scroll = 0
    if len(pairs) > max_rows:
        cur_pair = current_idx // 2 if current_idx >= 0 else 0
        scroll = max(0, min(cur_pair - max_rows // 2, len(pairs) - max_rows))
    col_num_w = max(32, int(mw * 0.15))
    col_w = (mw - col_num_w - int(24 * sf)) / 2.0
    highlight_clr = QColor(42, 130, 218, 70)
    active_text_clr = QColor(100, 200, 255)
    normal_w_clr = QColor(230, 230, 230); normal_b_clr = QColor(190, 190, 200); num_clr = QColor(120, 120, 140)
    for row_i in range(max_rows):
        pi = scroll + row_i
        if pi >= len(pairs): break
        move_num, w_txt, b_txt, w_idx, b_idx = pairs[pi]
        ry = content_y + row_i * row_h
        w_active = (current_idx == w_idx and w_txt)
        b_active = (current_idx == b_idx and b_txt)
        if w_active:
            p.setPen(Qt.NoPen); p.setBrush(highlight_clr)
            p.drawRoundedRect(QRectF(mx + col_num_w + int(12 * sf), ry, col_w, row_h - 2), max(3, int(4 * sf)), max(3, int(4 * sf)))
        if b_active:
            p.setPen(Qt.NoPen); p.setBrush(highlight_clr)
            p.drawRoundedRect(QRectF(mx + col_num_w + int(12 * sf) + col_w + int(4 * sf), ry, col_w, row_h - 2), max(3, int(4 * sf)), max(3, int(4 * sf)))
        p.setFont(num_font); p.setPen(num_clr)
        p.drawText(QRectF(mx + int(12 * sf), ry, col_num_w, row_h - 2), Qt.AlignVCenter | Qt.AlignRight, f"{move_num}.")
        if w_active: p.setFont(move_font_active); p.setPen(active_text_clr)
        else: p.setFont(move_font); p.setPen(normal_w_clr)
        if w_txt: p.drawText(QRectF(mx + col_num_w + int(16 * sf), ry, col_w, row_h - 2), Qt.AlignVCenter | Qt.AlignLeft, w_txt)
        if b_active: p.setFont(move_font_active); p.setPen(active_text_clr)
        else: p.setFont(move_font); p.setPen(normal_b_clr)
        if b_txt: p.drawText(QRectF(mx + col_num_w + int(16 * sf) + col_w + int(8 * sf), ry, col_w, row_h - 2), Qt.AlignVCenter | Qt.AlignLeft, b_txt)

def _draw_fitted_text(painter, rect, text, base_font, max_size_px=None, min_size_px=10, flags=Qt.AlignCenter | Qt.TextWordWrap, color=None):
    original_pen = painter.pen()
    if color is not None: painter.setPen(QPen(color))
    family = base_font.family(); bold = base_font.bold()
    min_size_px = int(min_size_px); max_size_px = int(max_size_px or base_font.pixelSize())
    q_rect = QRect(int(rect.x()), int(rect.y()), int(rect.width()), int(rect.height()))
    trial_font = _make_font(family, max_size_px, bold)
    painter.setFont(trial_font)
    fm = painter.fontMetrics()
    br = fm.boundingRect(q_rect, int(flags), text)
    if br.width() <= rect.width() and br.height() <= rect.height():
        painter.drawText(rect, int(flags), text)
        painter.setPen(original_pen)
        return
    scale_w = rect.width() / br.width() if br.width() > 0 else 1.0
    scale_h = rect.height() / br.height() if br.height() > 0 else 1.0
    scale = min(scale_w, scale_h) * 0.92
    estimated_size = int(max_size_px * scale)
    estimated_size = max(min_size_px, min(max_size_px, estimated_size))
    for size in range(estimated_size, min_size_px - 1, -1):
        trial_font = _make_font(family, size, bold)
        painter.setFont(trial_font)
        fm = painter.fontMetrics()
        br = fm.boundingRect(q_rect, int(flags), text)
        if br.width() <= rect.width() and br.height() <= rect.height():
            painter.drawText(rect, int(flags), text)
            painter.setPen(original_pen)
            return
    fallback_font = _make_font(family, min_size_px, bold)
    painter.setFont(fallback_font)
    painter.drawText(rect, int(flags), text)
    painter.setPen(original_pen)

def render_export_title_card(opening_name, eco, num_moves, width=1920, height=1080, bg_color=(26, 26, 46)):
    img = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
    bg = QColor(*bg_color); img.fill(bg)
    with paint_context(img) as p:
        p.setRenderHint(QPainter.Antialiasing); p.setRenderHint(QPainter.TextAntialiasing)
        sf = min(width, height) / 1080.0; margin = max(12, int(60 * sf))
        grad = QLinearGradient(0, 0, 0, height)
        grad.setColorAt(0, bg.lighter(130)); grad.setColorAt(0.5, bg); grad.setColorAt(1, bg.lighter(110))
        p.fillRect(0, 0, width, height, grad)
        p.setPen(Qt.NoPen); p.setBrush(QColor(255, 255, 255, 12))
        wm_px = max(16, int(480 * sf)); wm_font = QFont("Yu Gothic, Meiryo, sans-serif"); wm_font.setPixelSize(wm_px)
        p.setFont(wm_font); p.drawText(QRectF(0, 0, width, height), Qt.AlignCenter, "☗")
        lw = width * 0.4; pen_w = max(1.0, 2.0 * sf); line_y = int(height * 0.45)
        p.setPen(QPen(QColor(100, 100, 140, 120), pen_w))
        p.drawLine(int((width - lw) / 2), line_y, int((width + lw) / 2), line_y)
        title_rect = QRectF(margin, height * 0.15, width - 2 * margin, height * 0.25)
        base_title_font = _make_font(_font_family_sans(), 64 * sf, bold=True)
        _draw_fitted_text(p, title_rect, opening_name, base_title_font, max_size_px=64*sf, min_size_px=24*sf, flags=Qt.AlignCenter | Qt.TextWordWrap, color=QColor(240, 240, 245))
        info = f"Opening: {eco}   ·   {num_moves} half-moves"
        info_rect = QRectF(margin, line_y + int(20 * sf), width - 2 * margin, height * 0.15)
        base_info_font = _make_font(_font_family_sans(), 28 * sf)
        _draw_fitted_text(p, info_rect, info, base_info_font, max_size_px=28*sf, min_size_px=16*sf, flags=Qt.AlignCenter | Qt.TextWordWrap, color=QColor(160, 160, 190))
    return img

def render_export_end_screen(opening_name, eco, num_moves, width=1920, height=1080, bg_color=(26, 26, 46)):
    img = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
    bg = QColor(*bg_color); img.fill(bg)
    with paint_context(img) as p:
        p.setRenderHint(QPainter.Antialiasing); p.setRenderHint(QPainter.TextAntialiasing)
        sf = min(width, height) / 1080.0; margin = max(12, int(60 * sf))
        grad = QLinearGradient(0, 0, 0, height)
        grad.setColorAt(0, bg); grad.setColorAt(0.5, bg.lighter(120)); grad.setColorAt(1, bg)
        p.fillRect(0, 0, width, height, grad)
        p.setPen(Qt.NoPen); p.setBrush(QColor(255, 255, 255, 8))
        wm_px = max(16, int(380 * sf)); wm_font = QFont("Yu Gothic, Meiryo, sans-serif"); wm_font.setPixelSize(wm_px)
        p.setFont(wm_font); p.drawText(QRectF(0, 0, width, height), Qt.AlignCenter, "☖")
        thanks_rect = QRectF(margin, height * 0.18, width - 2 * margin, height * 0.12)
        base_thanks_font = _make_font(_font_family_sans(), 64 * sf, bold=True)
        _draw_fitted_text(p, thanks_rect, "Thanks for Watching!", base_thanks_font, max_size_px=64*sf, min_size_px=32*sf, flags=Qt.AlignCenter | Qt.TextWordWrap, color=QColor(240, 240, 245))
        name_text = f"{opening_name}  ·  {eco}"
        name_rect = QRectF(margin, height * 0.30, width - 2 * margin, height * 0.12)
        base_name_font = _make_font(_font_family_sans(), 36 * sf)
        _draw_fitted_text(p, name_rect, name_text, base_name_font, max_size_px=36*sf, min_size_px=20*sf, flags=Qt.AlignCenter | Qt.TextWordWrap, color=QColor(160, 160, 190))
        lw = width * 0.35; pen_w = max(1.0, 2.0 * sf); line_y = int(height * 0.48)
        p.setPen(QPen(QColor(100, 100, 140, 100), pen_w))
        p.drawLine(int((width - lw) / 2), line_y, int((width + lw) / 2), line_y)
        btn_w = max(240, int(360 * sf)); btn_h = max(48, int(72 * sf))
        btn_x = int((width - btn_w) / 2); btn_y = int(height * 0.56)
        btn_rect = QRectF(btn_x, btn_y, btn_w, btn_h)
        p.setPen(Qt.NoPen); p.setBrush(QColor(0, 0, 0, 60))
        p.drawRoundedRect(QRectF(btn_x + 2, btn_y + 3, btn_w, btn_h), btn_h / 2.0, btn_h / 2.0)
        p.setBrush(QColor(255, 0, 0)); p.drawRoundedRect(btn_rect, btn_h / 2.0, btn_h / 2.0)
        p.setPen(QColor(255, 255, 255))
        btn_font = QFont("Sans", max(16, int(32 * sf)), QFont.Bold)
        p.setFont(btn_font); p.drawText(btn_rect, Qt.AlignCenter, "SUBSCRIBE")
        like_rect = QRectF(margin, btn_y + btn_h + int(24 * sf), width - 2 * margin, height * 0.08)
        base_like_font = _make_font(_font_family_sans(), 26 * sf)
        _draw_fitted_text(p, like_rect, "Like if this opening helped you!", base_like_font, max_size_px=26*sf, min_size_px=16*sf, flags=Qt.AlignCenter | Qt.TextWordWrap, color=QColor(140, 160, 200))
    return img

# ═══════════════════════════════════════════════════════════════════════════════
#  SQLITE-BACKED DATA PROVIDER
# ═══════════════════════════════════════════════════════════════════════════════
class DataProvider:
    SCHEMA = '''
    CREATE TABLE IF NOT EXISTS openings (
        id          INTEGER PRIMARY KEY,
        name        TEXT NOT NULL DEFAULT '',
        eco         TEXT NOT NULL DEFAULT '',
        pgn         TEXT NOT NULL DEFAULT '',
        usi_moves   TEXT NOT NULL DEFAULT '[]',
        epd         TEXT NOT NULL DEFAULT '',
        display_title TEXT NOT NULL DEFAULT '',
        img_raw     TEXT NOT NULL DEFAULT '',
        num_moves   INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_name ON openings(name);
    CREATE INDEX IF NOT EXISTS idx_eco  ON openings(eco);
    CREATE INDEX IF NOT EXISTS idx_display ON openings(display_title);
    '''
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.use_duckdb = HAS_DUCKDB
        self.parquet_path = None
        possible_names = ["lichess_db_openings.parquet", "shogi_openings.parquet", "openings.parquet", "cache_openings.parquet"]
        for name in possible_names:
            path = os.path.join(DATA_DIR, name)
            if os.path.exists(path):
                self.parquet_path = path
                break
        if self.use_duckdb and self.parquet_path:
            import duckdb
            self._conn = duckdb.connect(database=':memory:')
            self._total_count = self._conn.execute(f"SELECT COUNT(*) FROM read_parquet('{self.parquet_path}')").fetchone()[0]
            log(f"DataProvider ready (DuckDB): {self._total_count} openings", "DATA")
        else:
            self._conn = sqlite3.connect(SQLITE_DB_PATH, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA cache_size=-64000")
            self._conn.execute("PRAGMA temp_store=MEMORY")
            self._conn.row_factory = sqlite3.Row
            self._ensure_schema()
            self._migrate_from_parquet()
            self._total_count = self._get_count()
            log(f"DataProvider ready (SQLite): {self._total_count} openings", "DATA")

    def _ensure_schema(self):
        self._conn.executescript(self.SCHEMA)
        self._conn.commit()

    def _migrate_from_parquet(self):
        if self._get_count() > 0: return
        if not self.parquet_path:
            log("Parquet file not found. Skipping migration.", "WARN")
            return
        log("Migrating openings from parquet to SQLite...", "DATA")
        try:
            import json, base64
            if HAS_PANDAS:
                import pandas as pd
                for chunk in pd.read_parquet(self.parquet_path, chunksize=50000):
                    self._import_opening_df(chunk)
            elif HAS_PYARROW:
                import pyarrow.parquet as pq
                pf = pq.ParquetFile(self.parquet_path)
                for batch in pf.iter_batches(batch_size=50000):
                    self._import_opening_df(batch.to_pandas())
            else:
                log("Cannot migrate: requires pandas or pyarrow", "ERROR")
                return
            log(f"Migration complete: {self._get_count()} openings", "DATA")
        except Exception as e:
            log(f"Migration error: {e}", "ERROR")

    def _import_opening_df(self, df):
        import json, base64
        records = []
        for row in df.itertuples(index=False):
            name = str(getattr(row, 'name', '')) or ''
            eco = str(getattr(row, 'eco', '')) or ''
            pgn = str(getattr(row, 'pgn', '')) or ''
            usi_str = str(getattr(row, 'usi', getattr(row, 'uci', getattr(row, 'moves', '')))) or ''
            epd = str(getattr(row, 'epd', '')) or ''
            img_bytes = b''
            img_field = getattr(row, 'img', None)
            if isinstance(img_field, dict) and 'bytes' in img_field: img_bytes = img_field['bytes']
            elif hasattr(img_field, 'bytes'): img_bytes = img_field.bytes
            img_raw = base64.b64encode(img_bytes).decode('utf-8') if img_bytes else ''
            usi_list = usi_str.split() if usi_str.strip() else []
            usi_moves_json = json.dumps(usi_list)
            num_moves = len(usi_list)
            id_key = f"{eco}:{name}"
            oid = abs(hash(id_key)) % (2**31)
            records.append({'id': oid, 'name': name, 'eco': eco, 'pgn': pgn, 'usi_moves': usi_moves_json,
                            'epd': epd, 'display_title': name, 'img_raw': img_raw, 'num_moves': num_moves})
            if len(records) >= 10000:
                self._insert_openings_batch(records)
                records = []
        if records: self._insert_openings_batch(records)

    def _insert_openings_batch(self, records):
        self._conn.executemany(
            '''INSERT OR REPLACE INTO openings
            (id, name, eco, pgn, usi_moves, epd, display_title, img_raw, num_moves)
            VALUES (:id, :name, :eco, :pgn, :usi_moves, :epd, :display_title, :img_raw, :num_moves)''', records)
        self._conn.commit()

    def _get_count(self):
        row = self._conn.execute("SELECT COUNT(*) FROM openings").fetchone()
        return row[0]

    @property
    def total_openings(self): return self._total_count

    def get_page(self, page=0, per_page=100, sort_col="name", sort_asc=True, theme_filter=""):
        offset = page * per_page; direction = "ASC" if sort_asc else "DESC"
        safe_cols = {"name", "eco", "id", "num_moves", "display_title"}
        if sort_col not in safe_cols: sort_col = "name"
        if self.use_duckdb:
            query = f"""
            SELECT (abs(hash(name || eco)) % 2147483648) as id, name, eco, name as display_title,
            CASE WHEN usi IS NULL OR usi = '' THEN 0 ELSE array_length(string_split(usi, ' ')) END as num_moves
            FROM read_parquet('{self.parquet_path}')
            """
            params = []
            if theme_filter:
                query += " WHERE LOWER(name) LIKE LOWER(?) OR LOWER(eco) LIKE LOWER(?)"
                params.extend([f"%{theme_filter}%", f"%{theme_filter}%"])
            query += f" ORDER BY {sort_col} {direction} LIMIT ? OFFSET ?"
            params.extend([per_page, offset])
            rows = self._conn.execute(query, params).fetchall()
            count_query = f"SELECT COUNT(*) FROM read_parquet('{self.parquet_path}')"
            count_params = []
            if theme_filter:
                count_query += " WHERE LOWER(name) LIKE LOWER(?) OR LOWER(eco) LIKE LOWER(?)"
                count_params.extend([f"%{theme_filter}%", f"%{theme_filter}%"])
            total = self._conn.execute(count_query, count_params).fetchone()[0]
            return [{'id': r[0], 'name': r[1], 'eco': r[2], 'display_title': r[3], 'num_moves': r[4]} for r in rows], total
        else:
            query = "SELECT id, name, eco, display_title, num_moves FROM openings WHERE 1=1"
            params = []
            if theme_filter:
                query += " AND (LOWER(name) LIKE ? OR LOWER(eco) LIKE ?)"
                params.extend([f"%{theme_filter}%", f"%{theme_filter}%"])
            query += f" ORDER BY {sort_col} {direction} LIMIT ? OFFSET ?"
            params.extend([per_page, offset])
            rows = self._conn.execute(query, params).fetchall()
            count_query = "SELECT COUNT(*) FROM openings WHERE 1=1"
            count_params = []
            if theme_filter:
                count_query += " AND (LOWER(name) LIKE ? OR LOWER(eco) LIKE ?)"
                count_params.extend([f"%{theme_filter}%", f"%{theme_filter}%"])
            total = self._conn.execute(count_query, count_params).fetchone()[0]
            return [dict(r) for r in rows], total

    def search(self, query, page=0, per_page=100):
        return self.get_page(page, per_page, theme_filter=query)

    def get_opening(self, opening_id):
        if self.use_duckdb:
            row = self._conn.execute(f"""
            SELECT (abs(hash(name || eco)) % 2147483648) as id, name, eco, pgn, usi, epd, name as display_title,
            CASE WHEN usi IS NULL OR usi = '' THEN 0 ELSE array_length(string_split(usi, ' ')) END as num_moves
            FROM read_parquet('{self.parquet_path}') WHERE (abs(hash(name || eco)) % 2147483648) = ?
            """, (opening_id,)).fetchone()
            if row:
                return {'id': row[0], 'name': row[1], 'eco': row[2], 'pgn': row[3],
                        'usi_moves': row[4].split() if row[4] else [], 'epd': row[5], 'display_title': row[6], 'num_moves': row[7]}
            return None
        else:
            row = self._conn.execute("SELECT * FROM openings WHERE id = ?", (opening_id,)).fetchone()
            if row:
                d = dict(row)
                import json
                if isinstance(d.get('usi_moves'), str):
                    try: d['usi_moves'] = json.loads(d['usi_moves'])
                    except Exception: d['usi_moves'] = []
                return d
            return None

    def get_openings_by_ids(self, ids):
        if not ids: return []
        placeholders = ",".join("?" * len(ids))
        if self.use_duckdb:
            rows = self._conn.execute(f"""
            SELECT (abs(hash(name || eco)) % 2147483648) as id, name, eco, pgn, usi, epd, name as display_title,
            CASE WHEN usi IS NULL OR usi = '' THEN 0 ELSE array_length(string_split(usi, ' ')) END as num_moves
            FROM read_parquet('{self.parquet_path}') WHERE (abs(hash(name || eco)) % 2147483648) IN ({placeholders})
            """, ids).fetchall()
            return [{'id': r[0], 'name': r[1], 'eco': r[2], 'pgn': r[3], 'usi_moves': r[4].split() if r[4] else [],
                     'epd': r[5], 'display_title': r[6], 'num_moves': r[7]} for r in rows]
        else:
            rows = self._conn.execute(f"SELECT * FROM openings WHERE id IN ({placeholders})", ids).fetchall()
            results = []
            import json
            for row in rows:
                d = dict(row)
                if isinstance(d.get('usi_moves'), str):
                    try: d['usi_moves'] = json.loads(d['usi_moves'])
                    except Exception: d['usi_moves'] = []
                results.append(d)
            return results

    def get_all_slim(self):
        if self.use_duckdb:
            rows = self._conn.execute(f"""
            SELECT (abs(hash(name || eco)) % 2147483648) as id, name, eco, name as display_title,
            CASE WHEN usi IS NULL OR usi = '' THEN 0 ELSE array_length(string_split(usi, ' ')) END as num_moves
            FROM read_parquet('{self.parquet_path}') ORDER BY name ASC
            """).fetchall()
            return [{'id': r[0], 'name': r[1], 'eco': r[2], 'display_title': r[3], 'num_moves': r[4]} for r in rows]
        else:
            rows = self._conn.execute("SELECT id, name, eco, display_title, num_moves FROM openings ORDER BY name ASC").fetchall()
            return [dict(r) for r in rows]

    def clear_all(self):
        if not self.use_duckdb:
            self._conn.execute("DELETE FROM openings")
            self._conn.commit()
            self._total_count = 0

    def close(self):
        self._conn.close()

# ═══════════════════════════════════════════════════════════════════════════════
#  PAGINATED OPENINGS LIST WIDGET
# ═══════════════════════════════════════════════════════════════════════════════
class PaginatedOpeningsWidget(QWidget):
    opening_selected = Signal(int)
    selection_changed = Signal(list)
    PAGE_SIZE = 100

    def __init__(self, data_provider: DataProvider, parent=None):
        super().__init__(parent)
        self.dp = data_provider
        self._current_page = 0; self._total_pages = 1; self._search_query = ""
        self._search_total = 0; self._is_searching = False; self._selected_ids = set()
        self._sort_col = "name"; self._sort_asc = True
        self._build_ui(); self._refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0); layout.setSpacing(4)
        search_row = QHBoxLayout(); search_row.setSpacing(4)
        self.search_input = QLineEdit(); self.search_input.setPlaceholderText("Search openings by name or opening code...")
        self.search_input.setClearButtonEnabled(True); self.search_input.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self.search_input); layout.addLayout(search_row)
        
        batch_row = QHBoxLayout(); batch_row.setSpacing(4)
        self.btn_select_all = QPushButton("Select All"); self.btn_select_all.setFixedHeight(26)
        self.btn_select_all.setStyleSheet("QPushButton{background:#2a82da;color:#fff;border:none;border-radius:3px;padding:2px 8px;font-size:11px}QPushButton:hover{background:#3a92ea}")
        self.btn_select_all.clicked.connect(self._select_all); batch_row.addWidget(self.btn_select_all)
        self.btn_select_page = QPushButton("Select Page"); self.btn_select_page.setFixedHeight(26)
        self.btn_select_page.setStyleSheet("QPushButton{background:#3a3a4a;color:#ddd;border:none;border-radius:3px;padding:2px 8px;font-size:11px}QPushButton:hover{background:#4a4a5a}")
        self.btn_select_page.clicked.connect(self._select_page); batch_row.addWidget(self.btn_select_page)
        self.btn_select_none = QPushButton("Clear Sel."); self.btn_select_none.setFixedHeight(26)
        self.btn_select_none.setStyleSheet("QPushButton{background:#3a3a4a;color:#ddd;border:none;border-radius:3px;padding:2px 8px;font-size:11px}QPushButton:hover{background:#4a4a5a}")
        self.btn_select_none.clicked.connect(self._select_none); batch_row.addWidget(self.btn_select_none)
        self.lbl_selected = QLabel("0 selected"); self.lbl_selected.setStyleSheet("color:#8a8aaa;font-size:11px;")
        batch_row.addWidget(self.lbl_selected); batch_row.addStretch(); layout.addLayout(batch_row)
        
        sort_row = QHBoxLayout(); sort_row.setSpacing(4)
        sort_row.addWidget(QLabel("Sort:"))
        self.sort_combo = QComboBox(); self.sort_combo.addItems(["Name", "Code", "Moves", "ID"])
        self.sort_combo.setFixedWidth(80); self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        sort_row.addWidget(self.sort_combo)
        self.btn_sort_dir = QPushButton("↑"); self.btn_sort_dir.setFixedSize(26, 26)
        self.btn_sort_dir.clicked.connect(self._toggle_sort_dir); sort_row.addWidget(self.btn_sort_dir)
        sort_row.addStretch(); layout.addLayout(sort_row)
        
        self.table = QTableWidget(); self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["☑", "Name", "Code", "Moves"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 28); self.table.setColumnWidth(2, 55); self.table.setColumnWidth(3, 50)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False); self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
        QTableWidget { background-color: #1e1e2a; alternate-background-color: #22223a; color: #ddd; font-size: 12px; border: 1px solid #333; gridline-color: #2a2a3a; }
        QTableWidget::item { padding: 3px 4px; } QTableWidget::item:selected { background: #2a82da; }
        QHeaderView::section { background: #16162a; color: #9a9abc; font-weight: bold; font-size: 11px; padding: 4px; border: none; border-bottom: 1px solid #333; }
        QCheckBox { spacing: 0; }""")
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        layout.addWidget(self.table, 1)
        
        page_row = QHBoxLayout(); page_row.setSpacing(4)
        self.btn_first = QPushButton("⏮"); self.btn_prev = QPushButton("◀"); self.lbl_page = QLabel("Page 1/1")
        self.btn_next = QPushButton("▶"); self.btn_last = QPushButton("⏭")
        for btn in (self.btn_first, self.btn_prev, self.btn_next, self.btn_last):
            btn.setFixedSize(30, 26)
            btn.setStyleSheet("QPushButton{background:#2a2a3a;color:#ccc;border:1px solid #444;border-radius:3px}QPushButton:hover{background:#3a3a5a}")
            page_row.addWidget(btn)
        self.lbl_page.setStyleSheet("color:#9a9abc;font-size:11px;padding:0 6px;"); page_row.addWidget(self.lbl_page); page_row.addStretch()
        self.lbl_total = QLabel("0 openings"); self.lbl_total.setStyleSheet("color:#6a6a8a;font-size:11px;"); page_row.addWidget(self.lbl_total)
        layout.addLayout(page_row)
        self.btn_first.clicked.connect(lambda: self._goto_page(0))
        self.btn_prev.clicked.connect(lambda: self._goto_page(self._current_page - 1))
        self.btn_next.clicked.connect(lambda: self._goto_page(self._current_page + 1))
        self.btn_last.clicked.connect(lambda: self._goto_page(self._total_pages - 1))

    def _refresh(self):
        if self._is_searching:
            rows, total = self.dp.search(self._search_query, self._current_page, self.PAGE_SIZE)
            self._search_total = total; count = total
        else:
            rows, total = self.dp.get_page(self._current_page, self.PAGE_SIZE, self._sort_col, self._sort_asc)
            count = total
        self._total_pages = max(1, (count + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
        self._populate_table(rows); self._update_pagination(count); self._update_selection_label()

    def _populate_table(self, rows):
        self.table.setRowCount(len(rows))
        for i, rec in enumerate(rows):
            oid = rec['id']
            chk_item = QTableWidgetItem(); chk_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk_item.setCheckState(Qt.Checked if oid in self._selected_ids else Qt.Unchecked)
            chk_item.setData(Qt.UserRole, oid); self.table.setItem(i, 0, chk_item)
            name_item = QTableWidgetItem(rec.get('display_title', rec.get('name', '')))
            name_item.setData(Qt.UserRole, oid); name_item.setToolTip(rec.get('name', '')); self.table.setItem(i, 1, name_item)
            eco_item = QTableWidgetItem(rec.get('eco', '')); eco_item.setData(Qt.UserRole, oid); self.table.setItem(i, 2, eco_item)
            moves_item = QTableWidgetItem(str(rec.get('num_moves', 0)))
            moves_item.setTextAlignment(Qt.AlignCenter); moves_item.setData(Qt.UserRole, oid); self.table.setItem(i, 3, moves_item)
        self.table.resizeRowsToContents()

    def _update_pagination(self, count):
        self.lbl_page.setText(f"Page {self._current_page + 1}/{self._total_pages}")
        self.lbl_total.setText(f"{count} openings")
        self.btn_first.setEnabled(self._current_page > 0); self.btn_prev.setEnabled(self._current_page > 0)
        self.btn_next.setEnabled(self._current_page < self._total_pages - 1); self.btn_last.setEnabled(self._current_page < self._total_pages - 1)

    def _on_cell_clicked(self, row, col):
        item = self.table.item(row, 0)
        if item is None: return
        oid = item.data(Qt.UserRole)
        if col == 0:
            if oid in self._selected_ids:
                self._selected_ids.discard(oid); item.setCheckState(Qt.Unchecked)
            else:
                self._selected_ids.add(oid); item.setCheckState(Qt.Checked)
            self._update_selection_label(); self.selection_changed.emit(list(self._selected_ids))
        else:
            self.opening_selected.emit(oid)

    def _on_cell_double_clicked(self, row, col):
        item = self.table.item(row, 0)
        if item: self.opening_selected.emit(item.data(Qt.UserRole))

    def _on_search_changed(self, text):
        self._search_query = text.strip(); self._is_searching = len(self._search_query) > 0
        self._current_page = 0; self._refresh()

    def _on_sort_changed(self, idx):
        col_map = {0: "name", 1: "eco", 2: "num_moves", 3: "id"}
        self._sort_col = col_map.get(idx, "name"); self._current_page = 0; self._refresh()

    def _toggle_sort_dir(self):
        self._sort_asc = not self._sort_asc
        self.btn_sort_dir.setText("↓" if not self._sort_asc else "↑")
        self._current_page = 0; self._refresh()

    def _goto_page(self, page):
        page = max(0, min(page, self._total_pages - 1))
        if page != self._current_page: self._current_page = page; self._refresh()

    def _select_all(self):
        all_slim = self.dp.get_all_slim()
        self._selected_ids = {r['id'] for r in all_slim}
        self._sync_checkboxes(); self._update_selection_label(); self.selection_changed.emit(list(self._selected_ids))

    def _select_page(self):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                oid = item.data(Qt.UserRole); self._selected_ids.add(oid); item.setCheckState(Qt.Checked)
        self._update_selection_label(); self.selection_changed.emit(list(self._selected_ids))

    def _select_none(self):
        self._selected_ids.clear(); self._sync_checkboxes()
        self._update_selection_label(); self.selection_changed.emit([])

    def _sync_checkboxes(self):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                oid = item.data(Qt.UserRole)
                item.setCheckState(Qt.Checked if oid in self._selected_ids else Qt.Unchecked)

    def _update_selection_label(self):
        self.lbl_selected.setText(f"{len(self._selected_ids)} selected")

    def get_selected_ids(self):
        return list(self._selected_ids)

# ═══════════════════════════════════════════════════════════════════════════════
#  PREVIEW WIDGET
# ═══════════════════════════════════════════════════════════════════════════════
class PreviewWidget(QWidget):
    def __init__(self, export_config: ExportConfig, parent=None):
        super().__init__(parent)
        self.config = export_config
        self._opening_name = ""; self._eco = ""; self._num_moves = 0
        self._title_img = None; self._end_img = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self); layout.setContentsMargins(4, 4, 4, 4); layout.setSpacing(4)
        title_lbl = QLabel("TITLE CARD PREVIEW"); title_lbl.setStyleSheet("color:#7a7a9a;font-size:10px;font-weight:bold;")
        layout.addWidget(title_lbl)
        self.title_canvas = QLabel(); self.title_canvas.setFixedSize(240, 135)
        self.title_canvas.setAlignment(Qt.AlignCenter)
        self.title_canvas.setStyleSheet("QLabel{background:#1a1a2e;border:1px solid #333;border-radius:4px;}")
        layout.addWidget(self.title_canvas, 0, Qt.AlignCenter)
        end_lbl = QLabel("END SCREEN PREVIEW"); end_lbl.setStyleSheet("color:#7a7a9a;font-size:10px;font-weight:bold;")
        layout.addWidget(end_lbl)
        self.end_canvas = QLabel(); self.end_canvas.setFixedSize(240, 135)
        self.end_canvas.setAlignment(Qt.AlignCenter)
        self.end_canvas.setStyleSheet("QLabel{background:#1a1a2e;border:1px solid #333;border-radius:4px;}")
        layout.addWidget(self.end_canvas, 0, Qt.AlignCenter)
        layout.addStretch()
        self.btn_regen = QPushButton("Refresh Preview")
        self.btn_regen.setStyleSheet("QPushButton{background:#2a2a3a;color:#ccc;border:1px solid #444;border-radius:3px;padding:4px 8px}QPushButton:hover{background:#3a3a5a}")
        self.btn_regen.clicked.connect(self._regenerate); layout.addWidget(self.btn_regen)

    def set_opening(self, name, eco, num_moves):
        self._opening_name = name; self._eco = eco; self._num_moves = num_moves
        self._regenerate()

    def _regenerate(self):
        pw, ph = 480, 270
        self._title_img = render_export_title_card(self._opening_name, self._eco, self._num_moves, width=pw, height=ph, bg_color=self.config.bg_color)
        self._end_img = render_export_end_screen(self._opening_name, self._eco, self._num_moves, width=pw, height=ph, bg_color=self.config.bg_color)
        self._display_previews()

    def _display_previews(self):
        if self._title_img:
            pm = QPixmap.fromImage(self._title_img.scaled(self.title_canvas.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.title_canvas.setPixmap(pm)
        if self._end_img:
            pm = QPixmap.fromImage(self._end_img.scaled(self.end_canvas.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            self.end_canvas.setPixmap(pm)

    def update_config(self, config):
        self.config = config; self._regenerate()

# ═══════════════════════════════════════════════════════════════════════════════
#  SETTINGS DIALOG
# ═══════════════════════════════════════════════════════════════════════════════
class SettingsDialog(QDialog):
    def __init__(self, export_config: ExportConfig, parent=None):
        super().__init__(parent)
        self.config = export_config
        self.setWindowTitle("Settings")
        self.setMinimumSize(520, 480)
        self.setStyleSheet("""
        QDialog { background: #1a1a2e; color: #ddd; }
        QTabWidget::pane { border: 1px solid #333; background: #1e1e2e; }
        QTabBar::tab { background: #16162a; color: #9a9abc; padding: 8px 16px; border: 1px solid #333; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 2px; }
        QTabBar::tab:selected { background: #1e1e2e; color: #fff; }
        QGroupBox { color: #aab; font-weight: bold; font-size: 12px; border: 1px solid #333; border-radius: 4px; margin-top: 10px; padding-top: 14px; }
        QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
        QLabel { color: #ccc; font-size: 12px; }
        QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit { background: #2a2a3a; color: #ddd; border: 1px solid #444; border-radius: 3px; padding: 3px 6px; font-size: 12px; }
        QCheckBox { color: #ccc; font-size: 12px; } QCheckBox::indicator { width: 16px; height: 16px; }
        QPushButton { background: #2a82da; color: #fff; border: none; border-radius: 4px; padding: 6px 16px; font-size: 12px; }
        QPushButton:hover { background: #3a92ea; }
        QPushButton#secondary { background: #3a3a4a; color: #ccc; }
        QPushButton#secondary:hover { background: #4a4a5a; }
        QSlider::groove:horizontal { height: 6px; background: #333; border-radius: 3px; }
        QSlider::handle:horizontal { width: 14px; height: 14px; background: #2a82da; border-radius: 7px; margin: -4px 0; }
        """)
        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(self._build_video_tab(), "Video")
        tabs.addTab(self._build_title_tab(), "Title Card")
        tabs.addTab(self._build_end_tab(), "End Screen")
        tabs.addTab(self._build_appearance_tab(), "Appearance")
        tabs.addTab(self._build_advanced_tab(), "Advanced")
        main_layout.addWidget(tabs)
        btn_box = QHBoxLayout(); btn_box.addStretch()
        apply_btn = QPushButton("Apply"); apply_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel"); cancel_btn.setObjectName("secondary"); cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(cancel_btn); btn_box.addWidget(apply_btn); main_layout.addLayout(btn_box)

    def _build_video_tab(self):
        w = QWidget(); lay = QVBoxLayout(w)
        grp_preset = QGroupBox("Export Preset"); gl = QVBoxLayout(grp_preset)
        self.combo_preset = QComboBox(); self.combo_preset.addItems(EXPORT_PRESETS.keys())
        self.combo_preset.setCurrentText(self.config.preset_name); self.combo_preset.currentTextChanged.connect(self._on_preset_changed)
        gl.addWidget(QLabel("Format:")); gl.addWidget(self.combo_preset)
        self.lbl_preset_info = QLabel(); self.lbl_preset_info.setStyleSheet("color:#8a8aaa;font-size:11px;")
        gl.addWidget(self.lbl_preset_info); self._update_preset_info(); lay.addWidget(grp_preset)
        grp_timing = QGroupBox("Animation Timing"); tl = QGridLayout(grp_timing)
        tl.addWidget(QLabel("Move animation (s):"), 0, 0)
        self.spin_move_anim = QDoubleSpinBox(); self.spin_move_anim.setRange(0.1, 5.0); self.spin_move_anim.setSingleStep(0.1)
        self.spin_move_anim.setValue(self.config.move_anim_duration); tl.addWidget(self.spin_move_anim, 0, 1)
        tl.addWidget(QLabel("Pause after move (s):"), 1, 0)
        self.spin_pause = QDoubleSpinBox(); self.spin_pause.setRange(0.1, 5.0); self.spin_pause.setSingleStep(0.1)
        self.spin_pause.setValue(self.config.pause_after_move); tl.addWidget(self.spin_pause, 1, 1)
        tl.addWidget(QLabel("FPS:"), 2, 0)
        self.spin_fps = QSpinBox(); self.spin_fps.setRange(10, 120); self.spin_fps.setValue(self.config.fps)
        tl.addWidget(self.spin_fps, 2, 1); lay.addWidget(grp_timing); lay.addStretch()
        return w

    def _build_title_tab(self):
        w = QWidget(); lay = QVBoxLayout(w)
        grp = QGroupBox("Title Card"); gl = QGridLayout(grp)
        self.chk_title_enabled = QCheckBox("Enable title card"); self.chk_title_enabled.setChecked(self.config.title_enabled)
        gl.addWidget(self.chk_title_enabled, 0, 0, 1, 2)
        gl.addWidget(QLabel("Duration (s):"), 1, 0)
        self.spin_title_dur = QDoubleSpinBox(); self.spin_title_dur.setRange(1.0, 15.0); self.spin_title_dur.setSingleStep(0.5)
        self.spin_title_dur.setValue(self.config.title_duration); gl.addWidget(self.spin_title_dur, 1, 1)
        gl.addWidget(QLabel("Title override:"), 2, 0)
        self.edit_title_text = QLineEdit(); self.edit_title_text.setPlaceholderText("(use opening name if empty)")
        self.edit_title_text.setText(self.config.title_text_override); gl.addWidget(self.edit_title_text, 2, 1)
        lay.addWidget(grp)
        preview_lbl = QLabel("Preview:"); preview_lbl.setStyleSheet("color:#7a7a9a;font-size:10px;font-weight:bold;")
        lay.addWidget(preview_lbl)
        self.title_preview = QLabel(); self.title_preview.setFixedSize(320, 180)
        self.title_preview.setAlignment(Qt.AlignCenter)
        self.title_preview.setStyleSheet("QLabel{background:#0e0e1e;border:1px solid #333;border-radius:4px;}")
        lay.addWidget(self.title_preview, 0, Qt.AlignCenter); self._render_title_preview(); lay.addStretch()
        return w

    def _build_end_tab(self):
        w = QWidget(); lay = QVBoxLayout(w)
        grp = QGroupBox("End Screen"); gl = QGridLayout(grp)
        self.chk_end_enabled = QCheckBox("Enable end screen"); self.chk_end_enabled.setChecked(self.config.end_title_enabled)
        gl.addWidget(self.chk_end_enabled, 0, 0, 1, 2)
        gl.addWidget(QLabel("Duration (s):"), 1, 0)
        self.spin_end_dur = QDoubleSpinBox(); self.spin_end_dur.setRange(1.0, 15.0); self.spin_end_dur.setSingleStep(0.5)
        self.spin_end_dur.setValue(self.config.end_title_duration); gl.addWidget(self.spin_end_dur, 1, 1)
        gl.addWidget(QLabel("Custom text:"), 2, 0)
        self.edit_end_text = QLineEdit(); self.edit_end_text.setPlaceholderText("(default: Thanks for watching!)")
        self.edit_end_text.setText(self.config.end_screen_text); gl.addWidget(self.edit_end_text, 2, 1)
        lay.addWidget(grp)
        preview_lbl = QLabel("Preview:"); preview_lbl.setStyleSheet("color:#7a7a9a;font-size:10px;font-weight:bold;")
        lay.addWidget(preview_lbl)
        self.end_preview = QLabel(); self.end_preview.setFixedSize(320, 180)
        self.end_preview.setAlignment(Qt.AlignCenter)
        self.end_preview.setStyleSheet("QLabel{background:#0e0e1e;border:1px solid #333;border-radius:4px;}")
        lay.addWidget(self.end_preview, 0, Qt.AlignCenter); self._render_end_preview(); lay.addStretch()
        return w

    def _build_appearance_tab(self):
        w = QWidget(); lay = QVBoxLayout(w)
        grp_board = QGroupBox("Board Theme"); bl = QVBoxLayout(grp_board)
        self.combo_theme = QComboBox(); self.combo_theme.addItems(THEMES.keys())
        self.combo_theme.setCurrentText(self.config.theme_name); bl.addWidget(QLabel("Theme:")); bl.addWidget(self.combo_theme)
        self.chk_flip = QCheckBox("Flip board (Gote at bottom)"); self.chk_flip.setChecked(self.config.flip_board)
        bl.addWidget(self.chk_flip); lay.addWidget(grp_board)
        arrow_label = QLabel("Arrow Style:"); self.arrow_style_combo = QComboBox()
        for name in ARROW_STYLES_LIST: self.arrow_style_combo.addItem(name)
        current_arrow_name = next((k for k, v in ARROW_STYLES.items() if v == self.config.arrow_style), ARROW_STYLES_LIST[0])
        self.arrow_style_combo.setCurrentText(current_arrow_name)
        self.arrow_style_combo.currentTextChanged.connect(self._on_arrow_style_changed)
        arrow_row = QHBoxLayout(); arrow_row.addWidget(arrow_label); arrow_row.addWidget(self.arrow_style_combo, 1)
        lay.addLayout(arrow_row)
        grp_bg = QGroupBox("Background Color"); bgl = QHBoxLayout(grp_bg)
        self.slider_bg_r = QSlider(Qt.Horizontal); self.slider_bg_r.setRange(0, 255)
        self.slider_bg_g = QSlider(Qt.Horizontal); self.slider_bg_g.setRange(0, 255)
        self.slider_bg_b = QSlider(Qt.Horizontal); self.slider_bg_b.setRange(0, 255)
        r, g, b_ = self.config.bg_color
        self.slider_bg_r.setValue(r); self.slider_bg_g.setValue(g); self.slider_bg_b.setValue(b_)
        for s, lbl in [(self.slider_bg_r, "R"), (self.slider_bg_g, "G"), (self.slider_bg_b, "B")]:
            row = QHBoxLayout(); row.addWidget(QLabel(lbl)); row.addWidget(s); bgl.addLayout(row)
        self.bg_preview = QLabel(); self.bg_preview.setFixedSize(40, 40); bgl.addWidget(self.bg_preview)
        self._update_bg_preview()
        for s in (self.slider_bg_r, self.slider_bg_g, self.slider_bg_b):
            s.valueChanged.connect(self._update_bg_preview)
        lay.addWidget(grp_bg); lay.addStretch()
        return w

    def _build_advanced_tab(self):
        w = QWidget(); lay = QVBoxLayout(w)
        dir_label = QLabel("Export Directory:"); self.output_dir_edit = QLineEdit(self.config.output_dir)
        self.output_dir_edit.setReadOnly(True)
        browse_btn = QPushButton("Browse..."); browse_btn.clicked.connect(self._on_browse_output_dir)
        dir_layout = QHBoxLayout(); dir_layout.addWidget(dir_label); dir_layout.addWidget(self.output_dir_edit, 1); dir_layout.addWidget(browse_btn)
        lay.addLayout(dir_layout)
        grp_ff = QGroupBox("FFmpeg Encoding"); fl = QGridLayout(grp_ff)
        fl.addWidget(QLabel("CRF (quality):"), 0, 0)
        self.spin_crf = QSpinBox(); self.spin_crf.setRange(0, 51); self.spin_crf.setValue(self.config.ffmpeg_crf)
        fl.addWidget(self.spin_crf, 0, 1); fl.addWidget(QLabel("(lower = better quality, larger file)"), 0, 2)
        fl.addWidget(QLabel("Preset:"), 1, 0)
        self.combo_ff_preset = QComboBox()
        self.combo_ff_preset.addItems(["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"])
        self.combo_ff_preset.setCurrentText(self.config.ffmpeg_preset); fl.addWidget(self.combo_ff_preset, 1, 1)
        lay.addWidget(grp_ff)
        info_grp = QGroupBox("System Info"); il = QVBoxLayout(info_grp)
        feats = []
        if HAS_FFMPEG: feats.append("FFmpeg")
        if HAS_IMAGEIO: feats.append("imageio")
        if HAS_NUMBA: feats.append("Numba")
        if HAS_CUPY: feats.append("CuPy (GPU)")
        if HAS_PANDAS: feats.append("Pandas")
        il.addWidget(QLabel(f"Available: {', '.join(feats) if feats else 'None (basic mode)'}"))
        il.addWidget(QLabel(f"Target: {self.config.preset.width}x{self.config.preset.height}"))
        lay.addWidget(info_grp); lay.addStretch()
        return w

    def _on_browse_output_dir(self):
        current_dir = self.output_dir_edit.text() or EXPORT_DIR
        new_dir = QFileDialog.getExistingDirectory(self, "Select Export Directory", current_dir)
        if new_dir:
            self.output_dir_edit.setText(new_dir); self.config.output_dir = new_dir

    def accept(self):
        self.config.output_dir = self.output_dir_edit.text()
        self.config.save()
        super().accept()

    def _on_arrow_style_changed(self, text):
        style = ARROW_STYLES.get(text, ARROW_STYLE_THICK)
        self.config.arrow_style = style

    def _on_preset_changed(self, name):
        self.config.apply_preset(name); self._update_preset_info()

    def _update_preset_info(self):
        p = self.config.preset
        self.lbl_preset_info.setText(f"{p.width}x{p.height}  ·  {p.description}  ·  {p.fps} FPS")

    def _update_bg_preview(self):
        r, g, b = self.slider_bg_r.value(), self.slider_bg_g.value(), self.slider_bg_b.value()
        self.bg_preview.setStyleSheet(f"QLabel{{background:rgb({r},{g},{b});border:1px solid #444;border-radius:4px;}}")

    def _render_title_preview(self):
        name = self.edit_title_text.text() or "Sample Opening"
        img = render_export_title_card(name, "Opening", 12, width=640, height=360, bg_color=self.config.bg_color)
        pm = QPixmap.fromImage(img.scaled(self.title_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.title_preview.setPixmap(pm)

    def _render_end_preview(self):
        name = self.edit_end_text.text() or "Sample Opening"
        img = render_export_end_screen(name, "Opening", 12, width=640, height=360, bg_color=self.config.bg_color)
        pm = QPixmap.fromImage(img.scaled(self.end_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.end_preview.setPixmap(pm)

    def get_config(self):
        self.config.apply_preset(self.combo_preset.currentText())
        self.config.title_enabled = self.chk_title_enabled.isChecked()
        self.config.title_duration = self.spin_title_dur.value()
        self.config.title_text_override = self.edit_title_text.text()
        self.config.end_screen_text = self.edit_end_text.text()
        self.config.move_anim_duration = self.spin_move_anim.value()
        self.config.pause_after_move = self.spin_pause.value()
        self.config.fps = self.spin_fps.value()
        self.config.theme_name = self.combo_theme.currentText()
        self.config.flip_board = self.chk_flip.isChecked()
        self.config.bg_color = (self.slider_bg_r.value(), self.slider_bg_g.value(), self.slider_bg_b.value())
        self.config.ffmpeg_crf = self.spin_crf.value()
        self.config.ffmpeg_preset = self.combo_ff_preset.currentText()
        return self.config

# ═══════════════════════════════════════════════════════════════════════════════
#  BOARD WIDGET
# ═══════════════════════════════════════════════════════════════════════════════
class BoardWidget(QWidget):
    move_made = Signal(dict)
    move_animated = Signal(dict)
    move_attempted = Signal(int, int, int, int, object)

    def __init__(self, engine: ShogiEngine, theme_name="Classic", parent=None):
        super().__init__(parent)
        self.engine = engine; self.theme_name = theme_name; self.flipped = False
        self.selected = None; self.legal_targets = []
        self.anim_timer = None; self.anim_state = None
        self._arrow_style = ARROW_STYLE_THICK; self.opening_mode = False
        self.setMinimumSize(BOARD_PX, BOARD_PX)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

    @property
    def theme(self): return THEMES.get(self.theme_name, THEMES["Classic"])
    def _sq_size(self): return min(self.width(), self.height()) // 9

    def _rc_from_pos(self, pos):
        sz = self._sq_size(); col = pos.x() // sz; row = pos.y() // sz
        if self.flipped: col = 8 - col; row = 8 - row
        if 0 <= row < 9 and 0 <= col < 9: return row, col
        return None, None

    @property
    def arrow_style(self): return self._arrow_style
    @arrow_style.setter
    def arrow_style(self, value): self._arrow_style = value; self.update()

    def paintEvent(self, event):
        with paint_context(self) as p:
            sz = self._sq_size()
            check_sqs = self.engine.check_squares()
            img = render_board_image(
                self.engine.board, last_move=self.engine.last_move,
                selected=self.selected, legal_targets=self.legal_targets,
                check_squares=check_sqs, anim_state=self.anim_state,
                sq_size=sz, theme=self.theme, flipped=self.flipped, arrow_style=self.arrow_style)
            p.drawImage(0, 0, img.scaled(self.width(), self.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton: return
        r, c = self._rc_from_pos(event.pos())
        if r is None: return
        if self.selected:
            sr, sc = self.selected
            if (r, c) in self.legal_targets:
                self._execute_move(sr, sc, r, c)
                return
        piece = self.engine.board.piece_at(ShogiEngine.rc_to_sq(r, c))
        if piece:
            self.selected = (r, c); self.legal_targets = self.engine.legal_moves(r, c)
        else:
            self.selected = None; self.legal_targets = []
        self.update()

    def _execute_move(self, fr, fc, tr, tc, promo=None):
        if self.opening_mode:
            self.move_attempted.emit(fr, fc, tr, tc, promo)
            self.selected = None; self.legal_targets = []
            self.update()
            return
        result = self.engine.make_move(fr, fc, tr, tc, promo)
        if result:
            self.selected = None; self.legal_targets = []
            self._start_animation(result)
            self.move_made.emit(result)

    def play_external_move(self, usi_str):
        result = self.engine.make_move_usi(usi_str)
        if result:
            self._start_animation(result)
            self.move_made.emit(result)

    def _start_animation(self, result):
        if self.anim_timer: self.anim_timer.stop()
        self.anim_state = {
            'from': result['from'], 'to': result['to'],
            'piece_obj': result['piece_obj'], 'captured': result['captured'], 'progress': 0.0}
        duration = ANIM_SPEED_DEFAULT
        steps = max(1, int(duration / 1000 * ANIM_FPS))
        self._anim_step = 0; self._anim_total = steps
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._tick_animation)
        interval = max(1, int(duration / steps))
        self.anim_timer.start(interval)

    def _tick_animation(self):
        if not self.anim_state:
            self.anim_timer.stop(); return
        self._anim_step += 1
        t = min(1.0, self._anim_step / self._anim_total)
        self.anim_state['progress'] = _ease_out_cubic(t)
        self.update()
        if t >= 1.0:
            self.anim_timer.stop()
            result_copy = dict(self.anim_state)
            self.anim_state = None
            self.update()
            self.move_animated.emit(result_copy)

    def reset_view(self):
        self.selected = None; self.legal_targets = []
        self.update()

# ═══════════════════════════════════════════════════════════════════════════════
#  BATCH EXPORT DIALOG
# ═══════════════════════════════════════════════════════════════════════════════
class BatchExportDialog(QDialog):
    def __init__(self, openings_list, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Export")
        self.setMinimumSize(520, 420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setModal(True)
        self.openings_list = openings_list; self.config = config
        self.worker = None; self._completed = 0; self._failed = 0
        self._results = []; self._total = len(openings_list)
        self._build_ui(); self._start_export()

    def _build_ui(self):
        layout = QVBoxLayout(self); layout.setSpacing(10)
        self.lbl_overall = QLabel(f"Exporting {self._total} opening(s)…")
        layout.addWidget(self.lbl_overall)
        self.progress_overall = QProgressBar(); self.progress_overall.setRange(0, self._total)
        self.progress_overall.setValue(0); self.progress_overall.setFormat("%v / %m videos")
        layout.addWidget(self.progress_overall)
        self.lbl_current = QLabel("Preparing…"); layout.addWidget(self.lbl_current)
        self.progress_current = QProgressBar(); self.progress_current.setRange(0, 100)
        self.progress_current.setValue(0); self.progress_current.setFormat("%p%")
        layout.addWidget(self.progress_current)
        self.table = QTableWidget(0, 3); self.table.setHorizontalHeaderLabels(["Opening", "Status", "File"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table)
        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel"); self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_open_folder = QPushButton("Open Folder"); self.btn_open_folder.clicked.connect(self._open_output_folder)
        self.btn_open_folder.setEnabled(False)
        self.btn_close = QPushButton("Close"); self.btn_close.clicked.connect(self.accept); self.btn_close.setEnabled(False)
        btn_layout.addStretch(); btn_layout.addWidget(self.btn_open_folder)
        btn_layout.addWidget(self.btn_cancel); btn_layout.addWidget(self.btn_close)
        layout.addLayout(btn_layout)

    def _start_export(self):
        self.worker = VideoExportWorker(self.openings_list, self.config, parent=self)
        self.worker.video_done.connect(self._on_video_done, Qt.QueuedConnection)
        self.worker.progress.connect(self._on_frame_progress, Qt.QueuedConnection)
        self.worker.finished.connect(self._on_batch_finished, Qt.QueuedConnection)
        self.worker.error.connect(self._on_error, Qt.QueuedConnection)
        self.worker.start()

    def _on_frame_progress(self, current_frame, total_frames):
        if total_frames > 0:
            self.progress_current.setValue(min(100, int(100 * current_frame / total_frames)))

    def _on_video_done(self, video_index, output_path):
        self._completed += 1
        name = self.openings_list[video_index].get("name", f"Video {video_index}")
        self._results.append((name, "✓ Done", output_path))
        self._add_table_row(name, "✓ Done", output_path)
        self.progress_overall.setValue(self._completed + self._failed)
        self.lbl_overall.setText(f"Exported {self._completed} of {self._total}" + (f"  ({self._failed} failed)" if self._failed else ""))
        self.lbl_current.setText(f"✓ {name}"); self.progress_current.setValue(100)

    def _on_error(self, error_msg):
        self._failed += 1
        next_idx = self._completed + self._failed - 1
        name = (self.openings_list[next_idx].get("name", f"Video {next_idx}") if next_idx < len(self.openings_list) else "Unknown")
        self._results.append((name, "✗ Failed", error_msg))
        self._add_table_row(name, "✗ Failed", error_msg[:120])
        self.progress_overall.setValue(self._completed + self._failed)
        self.lbl_overall.setText(f"Exported {self._completed} of {self._total}  ({self._failed} failed)")
        self.lbl_current.setText(f"✗ Failed: {name}")
        log(f"[EXPORT ERROR] {name}: {error_msg}", "ERROR")
        if self._completed + self._failed >= self._total:
            self._on_batch_finished("batch_complete")

    def _on_batch_finished(self, result):
        self.lbl_overall.setText(f"Batch complete: {self._completed} succeeded, {self._failed} failed")
        self.lbl_current.setText("All exports finished."); self.progress_current.setValue(100)
        self.progress_overall.setValue(self._total)
        self.btn_cancel.setEnabled(False); self.btn_close.setEnabled(True); self.btn_open_folder.setEnabled(True)
        if self._failed == 0:
            self.lbl_current.setStyleSheet("color: #4CAF50; font-weight: bold;")
            self.lbl_current.setText(f"✓ All {self._completed} videos exported successfully!")
        else:
            self.lbl_current.setStyleSheet("color: #FF9800; font-weight: bold;")
            self.lbl_current.setText(f"⚠ {self._completed} succeeded, {self._failed} failed. Check the table.")
        log(f"[EXPORT] Batch complete: {self._completed} ok, {self._failed} failed", "EXPORT")

    def _on_cancel(self):
        if self.worker and self.worker.isRunning():
            self.btn_cancel.setEnabled(False); self.btn_cancel.setText("Cancelling…")
            self.lbl_current.setText("Cancelling…"); self.worker.cancel()
            QTimer.singleShot(5000, self._force_cleanup)
        else:
            self.reject()

    def _force_cleanup(self):
        if self.worker and self.worker.isRunning():
            log("[EXPORT] Force-terminating worker", "WARN")
            self.worker.terminate(); self.worker.wait(2000)
            self._on_batch_finished("cancelled")

    def _add_table_row(self, name, status, detail):
        row = self.table.rowCount(); self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(name))
        si = QTableWidgetItem(status); si.setForeground(QColor("#4CAF50") if "✓" in status else QColor("#F44336"))
        self.table.setItem(row, 1, si)
        di = QTableWidgetItem(detail); di.setToolTip(detail); self.table.setItem(row, 2, di)
        self.table.scrollToBottom()

    def _open_output_folder(self):
        path = self.config.output_dir
        if not os.path.isdir(path): os.makedirs(path, exist_ok=True)
        if sys.platform == "win32": os.startfile(path)
        elif sys.platform == "darwin": subprocess.Popen(["open", path])
        else: subprocess.Popen(["xdg-open", path])

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self._on_cancel(); event.ignore()
        else:
            event.accept()

    def cleanup(self):
        if self.worker:
            self.worker.cancel(); self.worker.wait(3000)

# ═══════════════════════════════════════════════════════════════════════════════
#  OPENINGS LOADER
# ═══════════════════════════════════════════════════════════════════════════════
class OpeningsLoader:
    @staticmethod
    def load_usi_file(file_path, data_provider: DataProvider, progress_cb=None):
        """Load openings from a file containing USI moves (e.g., CSV/TSV/JSON)."""
        items = []; count = 0
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                if file_path.endswith('.csv') or file_path.endswith('.tsv'):
                    delimiter = '\t' if file_path.endswith('.tsv') else ','
                    reader = csv.DictReader(f, delimiter=delimiter)
                    for row in reader:
                        name = row.get('name', row.get('Opening', 'Unknown'))
                        eco = row.get('eco', row.get('Code', ''))
                        usi_str = row.get('usi', row.get('uci', row.get('moves', '')))
                        usi_moves = usi_str.split() if usi_str else []
                        items.append({'name': name, 'eco': eco, 'pgn': '', 'usi_moves': usi_moves,
                                      'epd': '', 'display_title': name, 'img_raw': ''})
                        count += 1
                        if len(items) >= 500:
                            data_provider._import_opening_df(type('DF', (), {'itertuples': lambda self, index=False: items})())
                            items = []
                            if progress_cb: progress_cb(count)
                if items:
                    data_provider._import_opening_df(type('DF', (), {'itertuples': lambda self, index=False: items})())
                    if progress_cb: progress_cb(count)
        except Exception as e:
            log(f"Error loading file: {e}", "ERROR")
        return count

# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN WINDOW
# ═══════════════════════════════════════════════════════════════════════════════
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Shogi Openings Explorer")
        self.setMinimumSize(1280, 800); self.resize(1440, 900)
        self.engine = ShogiEngine(); self.config = ExportConfig(); self.dp = DataProvider()
        self._current_opening = None; self._notations = []; self._move_idx = -1
        self._apply_global_style(); self._build_ui(); self._connect_signals()

    def _apply_global_style(self):
        self.setStyleSheet("""
        QMainWindow { background: #12121e; }
        QWidget { background: #12121e; color: #ddd; font-family: 'Segoe UI', sans-serif; }
        QSplitter::handle { background: #2a2a3a; width: 3px; }
        QSplitter::handle:hover { background: #2a82da; }
        QStatusBar { background: #0e0e1a; color: #6a6a8a; font-size: 11px; border-top: 1px solid #222; }
        QMenuBar { background: #16162a; color: #ccc; border-bottom: 1px solid #222; }
        QMenuBar::item:selected { background: #2a82da; }
        QMenu { background: #1e1e2e; color: #ddd; border: 1px solid #333; }
        QMenu::item:selected { background: #2a82da; }
        QToolBar { background: #16162a; border-bottom: 1px solid #222; spacing: 4px; padding: 2px; }
        QToolButton { background: transparent; color: #ccc; border: 1px solid transparent; border-radius: 4px; padding: 4px 8px; font-size: 12px; }
        QToolButton:hover { background: #2a2a3a; border-color: #444; }
        QToolButton:pressed { background: #2a82da; }
        """)

    def _build_ui(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        import_usi_action = QAction("Import USI File (CSV/TSV)...", self)
        import_usi_action.triggered.connect(self._import_usi)
        file_menu.addAction(import_usi_action)
        file_menu.addSeparator()
        clear_action = QAction("Clear Database", self)
        clear_action.triggered.connect(self._clear_db)
        file_menu.addAction(clear_action)
        file_menu.addSeparator()
        exit_action = QAction("Exit", self); exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        toolbar = self.addToolBar("Main"); toolbar.setMovable(False)
        self.btn_settings = QToolButton(); self.btn_settings.setText("⚙ Settings")
        self.btn_settings.clicked.connect(self._show_settings); toolbar.addWidget(self.btn_settings)
        toolbar.addSeparator()
        self.btn_undo = QToolButton(); self.btn_undo.setText("↩ Undo")
        self.btn_undo.clicked.connect(self._undo_move); toolbar.addWidget(self.btn_undo)
        self.btn_reset = QToolButton(); self.btn_reset.setText("⟳ Reset")
        self.btn_reset.clicked.connect(self._reset_board); toolbar.addWidget(self.btn_reset)
        toolbar.addSeparator()
        self.btn_flip = QToolButton(); self.btn_flip.setText("⇅ Flip")
        self.btn_flip.clicked.connect(self._flip_board); toolbar.addWidget(self.btn_flip)
        toolbar.addSeparator()
        self.btn_batch_export = QToolButton(); self.btn_batch_export.setText("▶ Batch Export")
        self.btn_batch_export.setStyleSheet("QToolButton{background:#2a82da;color:#fff;border-radius:4px;padding:4px 12px}QToolButton:hover{background:#3a92ea}")
        self.btn_batch_export.clicked.connect(self._batch_export); toolbar.addWidget(self.btn_batch_export)
        toolbar.addSeparator()
        self.btn_step_back = QToolButton(); self.btn_step_back.setText("◀")
        self.btn_step_back.clicked.connect(self._step_back); toolbar.addWidget(self.btn_step_back)
        self.btn_step_fwd = QToolButton(); self.btn_step_fwd.setText("▶")
        self.btn_step_fwd.clicked.connect(self._step_forward); toolbar.addWidget(self.btn_step_fwd)

        central = QWidget(); self.setCentralWidget(central)
        main_layout = QHBoxLayout(central); main_layout.setContentsMargins(6, 6, 6, 6)
        splitter = QSplitter(Qt.Horizontal)

        left_panel = QWidget(); left_layout = QVBoxLayout(left_panel); left_layout.setContentsMargins(0, 0, 0, 0)
        self.openings_list = PaginatedOpeningsWidget(self.dp)
        left_layout.addWidget(self.openings_list)
        left_panel.setMinimumWidth(320); left_panel.setMaximumWidth(500)
        splitter.addWidget(left_panel)

        center_panel = QWidget(); center_layout = QVBoxLayout(center_panel); center_layout.setContentsMargins(0, 0, 0, 0)
        self.board_widget = BoardWidget(self.engine, self.config.theme_name)
        center_layout.addWidget(self.board_widget, 1)
        self.notation_display = QTextEdit(); self.notation_display.setReadOnly(True)
        self.notation_display.setMaximumHeight(80)
        self.notation_display.setStyleSheet("QTextEdit{background:#1e1e2a;color:#ccc;border:1px solid #333;border-radius:4px;font-family:monospace;font-size:12px;padding:4px;}")
        center_layout.addWidget(self.notation_display)
        splitter.addWidget(center_panel)

        right_panel = QWidget(); right_layout = QVBoxLayout(right_panel); right_layout.setContentsMargins(4, 4, 4, 4)
        info_grp = QGroupBox("Current Opening")
        info_grp.setStyleSheet("QGroupBox{color:#aab;font-weight:bold;border:1px solid #333;border-radius:4px;margin-top:10px;padding-top:14px;}QGroupBox::title{subcontrol-origin:margin;left:10px;padding:0 4px;}")
        info_lay = QVBoxLayout(info_grp)
        self.lbl_opening_name = QLabel("No opening selected"); self.lbl_opening_name.setWordWrap(True)
        self.lbl_opening_name.setStyleSheet("font-size:14px;font-weight:bold;color:#eee;")
        info_lay.addWidget(self.lbl_opening_name)
        self.lbl_eco = QLabel("Code: —"); self.lbl_eco.setStyleSheet("color:#8a8aaa;font-size:12px;")
        info_lay.addWidget(self.lbl_eco)
        self.lbl_moves_count = QLabel("Moves: 0"); self.lbl_moves_count.setStyleSheet("color:#8a8aaa;font-size:12px;")
        info_lay.addWidget(self.lbl_moves_count)
        right_layout.addWidget(info_grp)
        self.preview_widget = PreviewWidget(self.config); right_layout.addWidget(self.preview_widget)
        right_layout.addStretch()
        right_panel.setMinimumWidth(260); right_panel.setMaximumWidth(320)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0); splitter.setStretchFactor(1, 1); splitter.setStretchFactor(2, 0)
        main_layout.addWidget(splitter)
        self.statusBar().showMessage(f"Ready — {self.dp.total_openings} openings loaded")

    def _connect_signals(self):
        self.openings_list.opening_selected.connect(self._on_opening_selected)
        self.board_widget.move_made.connect(self._on_move_made)
        self.board_widget.move_animated.connect(self._on_move_anim_done)

    def _on_opening_selected(self, opening_id):
        rec = self.dp.get_opening(opening_id)
        if rec is None: return
        self._current_opening = rec
        name = rec.get('display_title', rec.get('name', ''))
        eco = rec.get('eco', '')
        usi_moves = rec.get('usi_moves', [])
        self.lbl_opening_name.setText(name)
        self.lbl_eco.setText(f"Code: {eco}")
        self.lbl_moves_count.setText(f"Moves: {len(usi_moves)}")
        self.engine.reset(); self._notations = []
        for usi in usi_moves:
            result = self.engine.make_move_usi(usi)
            if result: self._notations.append(result['notation'])
            else: log(f"Invalid USI move: {usi}", "WARN"); break
        self._move_idx = len(self._notations) - 1
        self._update_notation_display()
        self.board_widget.reset_view(); self.board_widget.update()
        self.preview_widget.set_opening(name, eco, len(usi_moves))
        self.statusBar().showMessage(f"{name} — {eco} — {len(usi_moves)} half-moves")

    def _update_notation_display(self):
        if not self._notations:
            self.notation_display.setPlainText(""); return
        parts = []
        for i, n in enumerate(self._notations):
            if i % 2 == 0: parts.append(f"{i // 2 + 1}. {n}")
            else: parts.append(n)
        self.notation_display.setPlainText(" ".join(parts))

    def _step_forward(self):
        if not self._current_opening: return
        usi_moves = self._current_opening.get('usi_moves', [])
        if self._move_idx + 1 < len(usi_moves):
            self._move_idx += 1
            usi = usi_moves[self._move_idx]
            result = self.engine.make_move_usi(usi)
            if result:
                self.board_widget.update()
                self._update_notation_display()

    def _step_back(self):
        if self._move_idx >= 0:
            self.engine.undo()
            self._move_idx -= 1
            self.board_widget.update()
            self._update_notation_display()

    def _on_move_made(self, result):
        self._notations.append(result['notation'])
        self._move_idx = len(self._notations) - 1
        self._update_notation_display()

    def _on_move_anim_done(self, anim_result): pass

    def _undo_move(self):
        if self.engine.undo():
            if self._notations: self._notations.pop()
            self._move_idx = len(self._notations) - 1
            self._update_notation_display()
            self.board_widget.update()

    def _reset_board(self):
        self.engine.reset(); self._notations = []; self._move_idx = -1
        self._update_notation_display()
        self.board_widget.reset_view()

    def _flip_board(self):
        self.board_widget.flipped = not self.board_widget.flipped
        self.board_widget.update()

    def _show_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec() == QDialog.Accepted:
            self.config = dlg.get_config()
            self.board_widget.theme_name = self.config.theme_name
            self.board_widget.flipped = self.config.flip_board
            self.board_widget.update()
            self.preview_widget.update_config(self.config)
            self.statusBar().showMessage("Settings updated")

    def _batch_export(self):
        ids = self.openings_list.get_selected_ids()
        if not ids:
            self.statusBar().showMessage("No openings selected for export — use checkboxes"); return
        raw_records = self.dp.get_openings_by_ids(ids)
        if not raw_records:
            self.statusBar().showMessage("Could not load selected openings"); return
        openings_data = []
        for rec in raw_records:
            usi_moves = rec.get('usi_moves', [])
            if isinstance(usi_moves, str):
                try: usi_moves = json.loads(usi_moves)
                except Exception: usi_moves = []
            rec['moves'] = usi_moves
            notations = []; temp_board = shogi.Board()
            for usi in usi_moves:
                try:
                    m = shogi.Move.from_usi(usi)
                    notations.append(temp_board.san(m))
                    temp_board.push(m)
                except Exception: break
            rec['notations'] = notations
            openings_data.append(rec)
        dlg = BatchExportDialog(openings_data, self.config, self)
        dlg.exec()

    def _import_usi(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import USI File", DATA_DIR, "CSV/TSV Files (*.csv *.tsv);;All Files (*)")
        if not path: return
        self.statusBar().showMessage("Importing file..."); QApplication.processEvents()
        def worker():
            count = OpeningsLoader.load_usi_file(path, self.dp, lambda c: self.statusBar().showMessage(f"Imported {c} openings..."))
            QTimer.singleShot(0, lambda: self._on_import_done(count))
        threading.Thread(target=worker, daemon=True).start()

    def _on_import_done(self, count):
        self.openings_list._current_page = 0; self.openings_list._refresh()
        self.statusBar().showMessage(f"Import complete — {count} openings added ({self.dp.total_openings} total)")

    def _clear_db(self):
        self.dp.clear_all(); self.openings_list._current_page = 0; self.openings_list._refresh()
        self.statusBar().showMessage("Database cleared")

    def closeEvent(self, event):
        self.dp.close(); event.accept()

# ═══════════════════════════════════════════════════════════════════════════════
#  MP4 EXPORT WORKER
# ═══════════════════════════════════════════════════════════════════════════════
class VideoExportWorker(QThread):
    progress = Signal(int, int)
    finished = Signal(str)
    error = Signal(str)
    video_done = Signal(int, str)
    _FLUSH_THRESHOLD = 32 * 1024 * 1024

    def __init__(self, openings_list, config, parent=None):
        super().__init__(parent)
        self.openings_list = openings_list; self.config = config; self._cancel = False
        self.tmpdir = os.path.join(os.getcwd(), "shogi_sfx_tmp")
        os.makedirs(self.tmpdir, exist_ok=True)

    def cancel(self): self._cancel = True

    def run(self):
        total = len(self.openings_list)
        for vid_idx, opening_data in enumerate(self.openings_list):
            if self._cancel:
                self.error.emit("Export cancelled"); return
            try:
                path = self._export_single(opening_data, vid_idx)
                if path: self.video_done.emit(vid_idx, path)
                elif self._cancel: return
            except Exception as exc:
                self.error.emit(f"Error on '{opening_data.get('name', '?')}': {exc}")
        self.finished.emit("batch_complete")

    def _export_single(self, opening_data, vid_idx):
        cfg = self.config; preset = cfg.preset
        w, h = preset.width, preset.height; fps = cfg.fps
        sq_size = preset.calc_sq_size()
        theme = THEMES.get(cfg.theme_name, THEMES["Classic"])
        bg_color = cfg.bg_color; arrow_sty = cfg.arrow_style
        flipped = cfg.flip_board; is_board_only = preset.is_board_only
        os.makedirs(cfg.output_dir, exist_ok=True)
        safe = sanitize_filename(opening_data["name"])
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = os.path.join(cfg.output_dir, f"{safe}_{ts}.mp4")
        usi_moves = opening_data.get("moves", [])
        notations = opening_data.get("notations", [])
        if not notations: notations = self._generate_notations(usi_moves)
        board_states = self._precompute_boards(usi_moves)
        move_metas = self._precompute_move_meta(board_states, usi_moves)
        n_anim = max(1, int(cfg.move_anim_duration * fps))
        ease_vals = [_ease_out_cubic(i / max(1, n_anim - 1)) for i in range(n_anim)]
        n_hold = max(1, int(cfg.pause_after_move * fps))
        plan = self._build_frame_plan(cfg, fps, usi_moves, move_metas, n_anim, n_hold)
        total_frames = sum(p[1] for p in plan)
        if total_frames == 0:
            self.error.emit(f"No frames for '{opening_data['name']}'"); return None

        sr = 44100; total_duration = total_frames / fps
        total_samples = int(total_duration * sr) + sr
        audio_buffer = np.zeros(total_samples, dtype=np.float64)
        t = 0.0
        if cfg.title_enabled: t += cfg.title_duration
        audio_events = [(t, 'start')]; t += cfg.pause_after_move
        for mi in range(len(usi_moves)):
            meta = move_metas[mi]; snd = 'move'
            if meta.get('checkmate'): snd = 'checkmate'
            elif meta.get('check'): snd = 'check'
            elif meta.get('captured') != '.': snd = 'capture'
            audio_events.append((t, snd))
            t += cfg.move_anim_duration; t += cfg.pause_after_move
        if cfg.end_title_enabled: audio_events.append((t, 'end'))
        for t_sec, snd_name in audio_events:
            samples = self._get_sound_samples(snd_name, sr)
            start_idx = int(t_sec * sr); end_idx = start_idx + len(samples)
            if end_idx > len(audio_buffer):
                new_buf = np.zeros(end_idx + sr, dtype=np.float64)
                new_buf[:len(audio_buffer)] = audio_buffer; audio_buffer = new_buf
            audio_buffer[start_idx:end_idx] += samples
        audio_i16 = _to_i16(audio_buffer)
        temp_audio_path = os.path.join(self.tmpdir, f"shogi_export_audio_{vid_idx}_{int(time.time())}.wav")
        with wave.open(temp_audio_path, 'w') as wave_file:
            wave_file.setnchannels(1); wave_file.setsampwidth(2); wave_file.setframerate(sr)
            wave_file.writeframes(audio_i16.tobytes())
        if not HAS_FFMPEG:
            self.error.emit("ffmpeg not found on PATH"); return None
        cmd = self._ffmpeg_cmd(w, h, fps, cfg, opening_data, out, temp_audio_path)
        log(f"[EXPORT] {opening_data['name']}: {total_frames} frames @ {fps} fps", "EXPORT")
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        stderr_chunks: list[bytes] = []; stderr_exc: list[Exception] = []
        def _drain_stderr():
            try:
                while True:
                    chunk = proc.stderr.read(8192)
                    if not chunk: break
                    stderr_chunks.append(chunk)
            except Exception as e: stderr_exc.append(e)
        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True); stderr_thread.start()

        name = opening_data["name"]; eco = opening_data.get("eco", ""); n_mv = len(usi_moves)
        title_bgr = None
        if cfg.title_enabled:
            img = render_export_title_card(name, eco, n_mv, width=w, height=h, bg_color=bg_color)
            title_bgr = _qimage_to_bgr_bytes(img)
        end_bgr = None
        if cfg.end_title_enabled:
            img = render_export_end_screen(name, eco, n_mv, width=w, height=h, bg_color=bg_color)
            end_bgr = _qimage_to_bgr_bytes(img)
        start_img = render_composite_frame(board_states[0], notations, 0, width=w, height=h, sq_size=sq_size,
                                           theme=theme, flipped=flipped, bg_color=bg_color, arrow_style=arrow_sty, is_board_only=is_board_only)
        start_bgr = _qimage_to_bgr_bytes(start_img)
        hold_cache: dict[int, bytes] = {}
        buf = bytearray(); rendered = 0; last_pct = -1
        def _flush():
            nonlocal buf
            if buf:
                try: proc.stdin.write(buf)
                except BrokenPipeError: raise RuntimeError("ffmpeg pipe broken")
                buf = bytearray()
        def _queue(bgr: bytes):
            nonlocal rendered, last_pct
            buf.extend(bgr); rendered += 1
            if len(buf) >= self._FLUSH_THRESHOLD: _flush()
            pct = rendered * 50 // total_frames
            if pct != last_pct:
                self.progress.emit(rendered, total_frames); last_pct = pct

        try:
            for item in plan:
                if self._cancel:
                    _flush(); self._safe_close(proc); stderr_thread.join(timeout=2); return None
                kind, count = item[0], item[1]
                if kind == 'title':
                    for _ in range(count): _queue(title_bgr)
                elif kind == 'end':
                    for _ in range(count): _queue(end_bgr)
                elif kind == 'anim':
                    _, _, mi, anim_base = item; b = board_states[mi]
                    for af in range(count):
                        state = dict(anim_base); state['progress'] = ease_vals[af]
                        img = render_composite_frame(b, notations, mi, anim_state=state, width=w, height=h, sq_size=sq_size,
                                                     theme=theme, flipped=flipped, bg_color=bg_color, arrow_style=arrow_sty, is_board_only=is_board_only)
                        _queue(_qimage_to_bgr_bytes(img))
                elif kind == 'hold':
                    _, _, bidx, last_mv = item
                    if bidx not in hold_cache:
                        b = board_states[bidx]; chk = self._check_sqs(b)
                        img = render_composite_frame(b, notations, bidx - 1, last_move=last_mv, check_squares=chk,
                                                     width=w, height=h, sq_size=sq_size, theme=theme, flipped=flipped,
                                                     bg_color=bg_color, arrow_style=arrow_sty, is_board_only=is_board_only)
                        hold_cache[bidx] = _qimage_to_bgr_bytes(img)
                    for _ in range(count): _queue(hold_cache[bidx])
            _flush()
        except RuntimeError as e:
            self.error.emit(str(e)); return None

        log(f"[EXPORT] {rendered} frames piped — waiting for ffmpeg…", "EXPORT")
        try: proc.stdin.close()
        except BrokenPipeError as e: self.error.emit(str(e)); return None
        rc = proc.wait(); stderr_thread.join(timeout=5)
        stderr_text = b"".join(stderr_chunks).decode("utf-8", errors="replace")
        if rc != 0:
            self.error.emit(f"ffmpeg exited code {rc}:\n{stderr_text[-800:]}"); return None
        if not os.path.exists(out):
            self.error.emit(f"Output file not found: {out}"); return None
        file_size = os.path.getsize(out)
        if file_size < 1000:
            self.error.emit(f"Output file is suspiciously small ({file_size} bytes): {out}"); return None
        log(f"[EXPORT] ✓ {out} ({file_size:,} bytes)", "EXPORT")
        try:
            if os.path.exists(temp_audio_path): os.remove(temp_audio_path)
        except Exception as e: self.error.emit(str(e))
        return out

    @staticmethod
    def _generate_notations(usi_moves):
        board = shogi.Board(); notations = []
        for usi in usi_moves:
            try:
                m = shogi.Move.from_usi(usi); notations.append(board.san(m)); board.push(m)
            except Exception: break
        return notations

    @staticmethod
    def _precompute_boards(usi_moves, fen=None):
        states = [shogi.Board(fen)] if fen else [shogi.Board()]
        for usi in usi_moves:
            b = states[-1].copy()
            try: b.push(shogi.Move.from_usi(usi))
            except Exception: break
            states.append(b)
        return states

    @staticmethod
    def _precompute_move_meta(board_states, usi_moves):
        metas = []
        for mi, usi in enumerate(usi_moves):
            m = shogi.Move.from_usi(usi); b_before = board_states[mi]
            b_after = board_states[mi + 1] if mi + 1 < len(board_states) else None
            if m.from_square is not None:
                bfr = 8 - shogi.square_rank(m.from_square); bfc = shogi.square_file(m.from_square)
            else:
                bfr = -1; bfc = shogi.square_file(m.to_square)
            btr = 8 - shogi.square_rank(m.to_square); btc = shogi.square_file(m.to_square)
            piece_obj = b_before.piece_at(m.from_square) if m.from_square is not None else shogi.Piece(m.piece_type, b_before.turn)
            cap = b_before.piece_at(m.to_square) if m.from_square is not None else None
            cap_sym = cap.symbol() if cap else '.'
            is_check = b_after.is_check() if b_after else False
            is_mate = b_after.is_checkmate() if b_after else False
            metas.append({
                'from': (bfr, bfc), 'to': (btr, btc), 'piece_obj': piece_obj, 'captured': cap_sym,
                'last_move': ((bfr, bfc) if bfr != -1 else None, (btr, btc)), 'promo': m.promotion,
                'check': is_check, 'checkmate': is_mate,
            })
        return metas

    @staticmethod
    def _get_sound_samples(sound_name, sr=44100):
        def make_wood_hit(freq, duration, volume, noise_vol=0.3, decay_factor=25.0):
            n = int(sr * duration)
            if n <= 0: return np.zeros(1, dtype=np.float64)
            t = np.arange(n, dtype=np.float64) / sr
            rng = np.random.RandomState(42); noise = rng.randn(n)
            pitch = np.sin(2.0 * np.pi * freq * t) + 0.5 * np.sin(2.0 * np.pi * freq * 2.01 * t)
            out = pitch + (noise_vol * noise)
            env = np.exp(-decay_factor * t)
            attack_n = int(sr * 0.003)
            if attack_n > 1: env[:attack_n] *= np.linspace(0.0, 1.0, attack_n)
            return volume * out * env
        def make_tone(freq, duration, volume, harmonics=2, decay_factor=8.0, vibrato=0.0):
            n = int(sr * duration)
            if n <= 0: return np.zeros(1, dtype=np.float64)
            t = np.arange(n, dtype=np.float64) / sr
            mod = 1.0 + vibrato * np.sin(2.0 * np.pi * 5.0 * t)
            phase = 2.0 * np.pi * freq * t * mod
            out = np.sin(phase)
            for h in range(2, harmonics + 1): out += (1.0 / (h**1.5)) * np.sin(phase * h)
            env = np.exp(-decay_factor * t)
            attack_n = int(sr * 0.005)
            if attack_n > 1: env[:attack_n] *= np.linspace(0.0, 1.0, attack_n)
            return volume * out * env
        if sound_name == 'move': return make_wood_hit(800, 0.06, 0.45, noise_vol=0.4, decay_factor=35.0)
        elif sound_name == 'capture': return make_wood_hit(350, 0.10, 0.6, noise_vol=0.6, decay_factor=20.0)
        elif sound_name == 'check': return make_tone(880, 0.25, 0.4, harmonics=3, decay_factor=5.0, vibrato=0.02)
        elif sound_name == 'checkmate':
            n = int(sr * 0.8); t = np.arange(n, dtype=np.float64) / sr
            out = np.sin(2.0 * np.pi * 523.25 * t) + np.sin(2.0 * np.pi * 659.25 * t) + np.sin(2.0 * np.pi * 783.99 * t)
            env = np.exp(-2.0 * t); attack_n = int(sr * 0.01)
            if attack_n > 1: env[:attack_n] *= np.linspace(0.0, 1.0, attack_n)
            return 0.5 * out * env
        elif sound_name == 'start':
            return np.concatenate([make_tone(261.63, 0.12, 0.5, harmonics=2, decay_factor=6.0),
                                   np.zeros(max(1, int(sr * 0.04)), dtype=np.float64),
                                   make_tone(392.00, 0.20, 0.5, harmonics=2, decay_factor=4.0)])
        elif sound_name == 'end':
            return np.concatenate([make_tone(392.00, 0.15, 0.5, harmonics=2, decay_factor=5.0),
                                   np.zeros(max(1, int(sr * 0.05)), dtype=np.float64),
                                   make_tone(261.63, 0.30, 0.5, harmonics=2, decay_factor=3.0)])
        return np.zeros(int(sr * 0.1), dtype=np.float64)

    @staticmethod
    def _check_sqs(board):
        if board.is_check():
            k = board.king(board.turn)
            if k is not None: return [(8 - shogi.square_rank(k), shogi.square_file(k))]
        return []

    @staticmethod
    def _build_frame_plan(cfg, fps, usi_moves, move_metas, n_anim, n_hold):
        plan = []
        if cfg.title_enabled:
            plan.append(('title', int(cfg.title_duration * fps)))
            plan.append(('hold', n_hold))
        for mi in range(len(usi_moves)):
            meta = move_metas[mi]
            plan.append(('anim', n_anim, mi, {'from': meta['from'], 'to': meta['to'], 'piece_obj': meta['piece_obj'], 'captured': meta['captured']}))
            plan.append(('hold', n_hold, mi + 1, meta['last_move']))
        if cfg.end_title_enabled: plan.append(('end', int(cfg.end_title_duration * fps)))
        return plan

    @staticmethod
    def _ffmpeg_cmd(w, h, fps, cfg, opening_data, output_path, audio_path=None):
        cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-vcodec", "rawvideo", "-s", f"{w}x{h}", "-pix_fmt", "bgr24", "-r", str(fps), "-i", "-"]
        if audio_path: cmd.extend(["-i", audio_path])
        cmd.extend(["-c:v", "libx264", "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p", "-crf", str(cfg.ffmpeg_crf),
                    "-preset", cfg.ffmpeg_preset, "-bf", "2", "-g", str(fps * 2), "-keyint_min", str(fps), "-sc_threshold", "0",
                    "-movflags", "+faststart", "-metadata", f"title={opening_data.get('name', 'Shogi Opening')}"])
        if audio_path: cmd.extend(["-c:a", "aac", "-b:a", "192k", "-shortest"])
        else: cmd.append("-an")
        cmd.append(output_path); return cmd

    @staticmethod
    def _safe_close(proc):
        try: proc.stdin.close()
        except Exception: pass
        proc.terminate()

# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(18, 18, 30))
    palette.setColor(QPalette.WindowText, QColor(220, 220, 230))
    palette.setColor(QPalette.Base, QColor(30, 30, 42))
    palette.setColor(QPalette.AlternateBase, QColor(34, 34, 58))
    palette.setColor(QPalette.ToolTipBase, QColor(30, 30, 46))
    palette.setColor(QPalette.ToolTipText, QColor(220, 220, 230))
    palette.setColor(QPalette.Text, QColor(220, 220, 230))
    palette.setColor(QPalette.Button, QColor(42, 42, 58))
    palette.setColor(QPalette.ButtonText, QColor(220, 220, 230))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()