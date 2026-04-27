# Mic Plot Master 2.0 (PyQt6)

This is a desktop-first implementation of Mic Plot Master 2.0 with a clean separation between UI and core logic.

## Run

```bash
pip install -r requirements.txt
python app.py
```

## Inputs
- Character_Scene_List.csv (scenes across columns; row 1 = scene names; row 2 = page ranges)
- Character_Actor_List.csv (Character, Role)

## Notes
- One actor is assigned to at most one microphone (actor belongs to exactly one mic group).
- Auto-assignment uses a greedy strategy that minimizes the number of mics under the no-overlap constraint.
