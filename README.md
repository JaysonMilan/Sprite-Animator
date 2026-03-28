# Sprite Animator v4.0

A standalone sprite sheet viewer, animator, and export tool built with Python + Pygame.

## Features

### Core
- Load sprite sheets (PNG/JPG/BMP) via file dialog or drag-and-drop
- Adjustable grid (cols/rows/frames), auto-detect grid
- Play/Pause/Step with Loop, Once, Ping-Pong modes
- Adjustable FPS, frame range, mouse wheel zoom

### Export
- **GIF** — animated GIF with configurable FPS
- **WebP** — lossless animated WebP
- **PNG Sequence** — individual frame PNGs to folder
- **Atlas JSON** — sprite atlas with positions, trim rects, origins, hitboxes
- **Packed Atlas** — optimized texture atlas PNG + JSON
- **Animation JSON** — named animation states for game integration
- **Batch Export** — bulk convert folder of sheets to GIF
- **Merge Sheets** — combine multiple PNGs into one atlas

### Tools
- **Auto-Trim** — detect transparent padding, export trimmed frames
- **Frame Reorder/Delete** — rearrange or remove frames with undo
- **Hitbox Editor** — click two corners to define collision boxes per frame
- **Origin Editor** — right-click to set pivot point per frame
- **Palette Swap** — recolor sprites by swapping colors
- **Flip H/V** — mirror frames horizontally or vertically
- **Compare Mode** — load two sheets side-by-side
- **Background Sprite** — overlay animation on a background image

### Animation States
- Define named clips (idle, walk, attack) with frame ranges
- Per-frame custom duration (ms) for varied timing
- Visual timeline showing all states as colored segments
- Export animation definitions as standalone JSON

### Analysis
- Duplicate frame detection (MD5 hash)
- Palette analyzer (top 20 dominant colors)
- Frame stats (pixel count, animation duration, file size)

### View
- Pixel-perfect scale: 1x/2x/3x/4x nearest-neighbor
- Onion skinning (ghost previous frame)
- Pixel grid overlay at high zoom
- Background modes: Checker, Black, White, Custom color

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python sprite_animator.py [optional_image_path]
```

Or double-click `run.bat` on Windows.

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Space | Play/Pause |
| Left/Right | Step frame |
| Up/Down | FPS +/- 5 |
| 1-4 | Pixel scale 1x-4x |
| 0 | Free zoom |
| O | Open file |
| G | Export GIF |
| W | Export WebP |
| P | PNG sequence |
| J | Atlas JSON |
| T | Auto-trim |
| D | Find duplicates |
| H | Flip horizontal |
| V | Flip vertical |
| N | Onion skin |
| B | Cycle background |
| F | Zoom to fit |
| C | Compare mode |
| R | Reset playback |
| Del | Delete frame |
| Ctrl+Z | Undo |
| Esc | Quit |
