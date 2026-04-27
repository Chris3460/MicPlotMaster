🎤 Mic Plot Master 2.0
Mic Plot Master is a free desktop application designed to help theater sound designers, production teams, and volunteers plan and manage wireless microphone sharing for live productions.
It provides tools for:

Defining scenes and page ranges
Assigning characters to actors
Automatically or manually assigning microphone packs
Identifying risky mic swaps
Making per‑scene microphone overrides
Exporting CSV and Excel files for booth and backstage use

Mic Plot Master is designed to reduce confusion, missed handoffs, and last‑minute scrambling during a show.

✅ Quick Start (Most Users)
🪟 Windows (Recommended)
If you are on Windows, the easiest way to use Mic Plot Master is the prebuilt executable.

Download MicPlotMaster.exe from the latest GitHub release.
Double‑click the file to launch.
No Python installation is required.

That’s it — the app runs fully offline once downloaded.

💻 Running from Source (All Operating Systems)
If you are on macOS, Linux, or prefer running from source on Windows, you can launch Mic Plot Master using Python.

✅ Requirements

Python 3.10 or newer

The following Python packages:

PyQt6
openpyxl



📦 Install Dependencies
From the project root:
pip install -r requirements.txtShow more lines
▶ Run the Application
python app.pyShow more lines
The Mic Plot Master window should open normally.

📁 Project Files & Resources
When running from source or using the Windows executable, the following folders are included:
Help/

Contains the User Guide (User_Guide.html)
Accessible from the Help tab inside the application

Demo CSVs/

Example CSV files for:

Character → Scene lists
Character → Actor lists


Useful for learning the import format


📘 User Guide
A full step‑by‑step user guide is included with the application:

Open the Help tab inside Mic Plot Master
Click Open User Guide
The guide opens in your web browser (works offline)

The guide covers:

Scene setup
Casting
Grouping
Manual vs automatic mic assignment
Timeline risk indicators
Export formats and examples


📤 Exported Outputs
Mic Plot Master can generate:
CSV Files

Mic assignments
Actor summaries
Scene participation lists

Excel Workbook
An Excel file with multiple tabs:

Mic Plot – scene‑by‑scene mic usage
Sharing – who shares each mic
Mic List – actors, packs, and wires
Scenes – scene‑centric mic requirements

These are intended to be printed, shared, or posted backstage and in the sound booth.

🛠 For Developers (Optional)

app.py is the main entry point
The UI is built with PyQt6
Core logic lives in the core/ package
Import/export logic is in imports/ and exports/
Resource paths are managed using utils/resources.py

Supports normal Python runs
Supports PyInstaller onedir and onefile builds



Prebuilt executables are created using PyInstaller.

💬 Support & Feedback
Questions, bug reports, or suggestions are welcome:
📧 Email: Chris3460@gmail.com

❤️ Optional Donations
Mic Plot Master is provided free of charge.
If the tool saves you time or helps your production run more smoothly, optional donations help support continued development:
💸 Venmo:
https://venmo.com/code?user_id=2968534653075456460&created=1776955829
Donations are never required — thank you for supporting theater.

📄 License
This project is provided for community and educational use.
