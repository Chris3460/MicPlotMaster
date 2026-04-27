from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices

from utils.resources import resource_path


class HelpTab(QWidget):
    def __init__(self):
        super().__init__()

        layout = QVBoxLayout()

        title = QLabel("Mic Plot Master")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        title.setStyleSheet("font-size: 16pt; font-weight: bold;")
        layout.addWidget(title)

        layout.addWidget(QLabel(
            "Mic Plot Master is a free tool built to help theatre sound designers, "
            "production teams, and volunteers manage wireless microphone logistics "
            "with less stress and fewer mistakes."
        ))

        layout.addSpacing(12)

        # --- User Guide link ---
        guide_label = QLabel(
            '<a href="#">Open User Guide</a>'
        )
        guide_label.setOpenExternalLinks(False)
        guide_label.linkActivated.connect(self.open_user_guide)
        layout.addWidget(guide_label)

        layout.addSpacing(12)

        support_header = QLabel("Support & Feedback")
        support_header.setStyleSheet("font-weight: bold;")
        layout.addWidget(support_header)

        email_label = QLabel(
            'Email questions, feedback, or bug reports to: '
            '<a href="mailto:Chris3460@gmail.com">Chris3460@gmail.com</a>'
        )
        email_label.setOpenExternalLinks(True)
        layout.addWidget(email_label)

        layout.addSpacing(12)

        donate_header = QLabel("Optional Support")
        donate_header.setStyleSheet("font-weight: bold;")
        layout.addWidget(donate_header)

        donate_label = QLabel(
            'If this tool saves you time or helps your production run more smoothly, '
            'you can optionally support ongoing development via Venmo:<br><br>'
            '<a href="https://venmo.com/code?user_id=2968534653075456460&created=1776955829">'
            'Support Mic Plot Master on Venmo</a>'
        )
        donate_label.setOpenExternalLinks(True)
        layout.addWidget(donate_label)

        layout.addSpacing(12)

        footer = QLabel(
            "Donations are never required. Thank you for using Mic Plot Master "
            "and for supporting theatre."
        )
        footer.setWordWrap(True)
        footer.setStyleSheet("color: #555;")
        layout.addWidget(footer)

        version_label = QLabel("Version 2.0 — Created by Chris")
        version_label.setStyleSheet(
            "color: #777; font-size: 10pt; margin-top: 8px;"
        )
        layout.addWidget(version_label)

        layout.addStretch(1)

        self.setLayout(layout)

    def open_user_guide(self):
        guide_path: Path = resource_path("Help/User_Guide.html")

        if not guide_path.exists():
            QMessageBox.warning(
                self,
                "User Guide Not Found",
                f"Could not find:\n{guide_path}"
            )
            return

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(guide_path)))