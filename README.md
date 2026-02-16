# Tarot42 Sigil Scanner (Local Web MVP)

This repo is a **local-first** MVP:
- 42-card deck with **black-on-light centered sigils**
- Web app uses your **computer camera** to scan
- Scanned cards appear on a **spread board** (1-card / 3-card / Celtic Cross)
- Generates a reading + lets you chat about it (deterministic MVP; swap in AI later)

## 0) Prereqs
- Ubuntu
- Python 3.10+

## 1) Setup
```bash
cd tarot-sigil-app

python3 -m venv .venv
source .venv/bin/activate

pip install -r tools/requirements.txt
pip install -r backend/requirements.txt
```

## 2) Generate sigils + card faces + print sheet
```bash
python tools/generate_sigils.py
python tools/render_card_faces.py
python tools/build_print_sheet.py

xdg-open deck/print/print_sheet.pdf
```

## 3) Run backend (serves frontend too)
```bash
cp backend/.env.example backend/.env
set -a; source backend/.env; set +a
chmod +x backend/run.sh
bash backend/run.sh
```

Open:
- http://127.0.0.1:8789

## 4) How scanning works
Frontend takes a JPEG snapshot and POSTs to:
- `POST /scan` (multipart image)

Backend uses OpenCV ORB feature matching against `deck/sigils/*.png`.

## 5) Replace meanings
Edit:
- `deck/deck.json`

Fill in `name`, `upright`, `reversed`, `lore`, `keywords`.

## 6) Tests
```bash
pytest -q
```
