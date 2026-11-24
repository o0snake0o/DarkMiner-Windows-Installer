
#!/usr/bin/env python3
"""DarkMiner v0.2 — local, user-controlled Monero miner GUI."""

import json
import os
import re
import socket
import sys
from collections import deque
from pathlib import Path
from urllib.request import urlopen

from PySide6.QtCore import Qt, QProcess, QSettings, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFormLayout, QFrame,
    QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
ENGINE = ROOT / "engine" / ("xmrig.exe" if os.name == "nt" else "xmrig")
BASE58 = set(
    "123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    "abcdefghijkmnopqrstuvwxyz"
)

STYLE = """
QWidget {
    background: #0b1019;
    color: #e7edf5;
    font: 11pt "Sans Serif";
}
QFrame#panel {
    background: #172131;
    border: 1px solid #293548;
    border-radius: 12px;
}
QLabel#heading {
    font-size: 23px;
    font-weight: 800;
    color: #72e9b1;
}
QLabel#metric {
    font-size: 26px;
    font-weight: bold;
    color: #72e9b1;
}
QLineEdit, QSpinBox, QPlainTextEdit {
    background: #101826;
    color: #edf3fa;
    border: 1px solid #38465b;
    border-radius: 6px;
    padding: 7px;
}
QPushButton {
    background: #245e4a;
    color: white;
    border-radius: 7px;
    padding: 11px;
    font-weight: bold;
}
QPushButton:hover { background: #30765d; }
QPushButton:disabled {
    background: #303b49;
    color: #8c99a8;
}
QCheckBox { spacing: 8px; }
"""


def api_port():
    """Choose a local port for this mining session."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def format_uptime(seconds):
    seconds = max(0, int(seconds))
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    return f"{h:02}:{m:02}:{s:02}"


class HashrateChart(QWidget):
    def __init__(self):
        super().__init__()
        self.values = deque(maxlen=60)
        self.setMinimumHeight(135)

    def add(self, value):
        self.values.append(max(0, float(value)))
        self.update()

    def reset(self):
        self.values.clear()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )

        rect = self.rect().adjusted(10, 10, -10, -10)
        painter.setPen(QPen(QColor("#344258"), 1))

        for i in range(5):
            y = rect.top() + i * rect.height() / 4
            painter.drawLine(
                int(rect.left()), int(y),
                int(rect.right()), int(y)
            )

        if len(self.values) < 2:
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(
                rect,
                Qt.AlignmentFlag.AlignCenter,
                "Waiting for mining data"
            )
            return

        values = list(self.values)
        maximum = max(1.0, max(values) * 1.15)

        painter.setPen(QPen(QColor("#72e9b1"), 2.5))

        for i in range(1, len(values)):
            x1 = rect.left() + (
                (i - 1) / 59
            ) * rect.width()
            x2 = rect.left() + (
                i / 59
            ) * rect.width()

            y1 = rect.bottom() - (
                values[i - 1] / maximum
            ) * rect.height()
            y2 = rect.bottom() - (
                values[i] / maximum
            ) * rect.height()

            painter.drawLine(
                int(x1), int(y1),
                int(x2), int(y2)
            )


class DarkMiner(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("DarkMiner v0.2 — Linux")
        self.resize(1000, 770)
        self.setStyleSheet(STYLE)

        self.settings = QSettings(
            "DarkMiner", "DarkMiner"
        )
        self.process = QProcess(self)
        self.process.setProcessChannelMode(
            QProcess.ProcessChannelMode.MergedChannels
        )

        self.process.readyReadStandardOutput.connect(
            self.read_output
        )
        self.process.started.connect(self.on_started)
        self.process.finished.connect(self.on_finished)
        self.process.errorOccurred.connect(
            self.on_process_error
        )

        self.port = None
        self.stopping = False
        self.setup_ui()
        self.restore_settings()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_stats)
        self.timer.start(2000)

    def make_panel(self):
        panel = QFrame()
        panel.setObjectName("panel")
        return panel

    def create_metric_card(self, title):
        panel = self.make_panel()
        layout = QVBoxLayout(panel)

        label = QLabel(title)
        label.setStyleSheet("color: #94a3b8;")
        value = QLabel("0")
        value.setObjectName("metric")

        layout.addWidget(label)
        layout.addWidget(value)
        return panel, value

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setSpacing(12)
        outer.setContentsMargins(20, 20, 20, 20)

        header = QHBoxLayout()
        heading = QLabel("DARKMINER")
        heading.setObjectName("heading")
        self.status = QLabel("● OFFLINE")
        self.status.setStyleSheet("color: #94a3b8;")

        header.addWidget(heading)
        header.addStretch()
        header.addWidget(self.status)
        outer.addLayout(header)

        metrics = QGridLayout()

        panels = [
            self.create_metric_card("HASHRATE (H/s)"),
            self.create_metric_card("ACCEPTED SHARES"),
            self.create_metric_card("REJECTED SHARES"),
            self.create_metric_card("UPTIME"),
        ]

        (
            self.hashrate_label,
            self.accepted_label,
            self.rejected_label,
            self.uptime_label,
        ) = [value for _, value in panels]

        self.uptime_label.setText("00:00:00")

        for i, (panel, _) in enumerate(panels):
            metrics.addWidget(panel, i // 2, i % 2)

        outer.addLayout(metrics)

        chart_panel = self.make_panel()
        chart_layout = QVBoxLayout(chart_panel)
        chart_layout.addWidget(QLabel("HASHRATE HISTORY"))
        self.chart = HashrateChart()
        chart_layout.addWidget(self.chart)
        outer.addWidget(chart_panel)

        config = self.make_panel()
        form = QFormLayout(config)

        self.wallet = QLineEdit()
        self.wallet.setPlaceholderText(
            "Your public Monero receiving address"
        )

        self.pool = QLineEdit()
        self.pool.setPlaceholderText(
            "pool.example.org:3333"
        )

        self.threads = QSpinBox()
        cpu_count = max(1, os.cpu_count() or 1)
        self.threads.setRange(1, cpu_count)
        self.threads.setValue(max(1, cpu_count // 2))

        self.tls = QCheckBox(
            "Use TLS (pool must support it)"
        )

        form.addRow("Wallet:", self.wallet)
        form.addRow("Pool:", self.pool)
        form.addRow("CPU threads:", self.threads)
        form.addRow("Connection:", self.tls)

        outer.addWidget(config)

        buttons = QHBoxLayout()

        self.start_button = QPushButton(
            "▶ START MINING"
        )
        self.stop_button = QPushButton(
            "■ STOP MINING"
        )
        self.stop_button.setEnabled(False)

        self.start_button.clicked.connect(
            self.start_mining
        )
        self.stop_button.clicked.connect(
            self.stop_mining
        )

        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        outer.addLayout(buttons)

        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMaximumBlockCount(500)
        self.logs.setPlaceholderText(
            "Mining logs will appear here."
        )
        outer.addWidget(self.logs, stretch=1)

    def restore_settings(self):
        self.wallet.setText(
            self.settings.value("wallet", "")
        )
        self.pool.setText(
            self.settings.value("pool", "")
        )
        saved_threads = int(
            self.settings.value(
                "threads", self.threads.value()
            )
        )
        self.threads.setValue(saved_threads)

        self.tls.setChecked(
            self.settings.value(
                "tls", False, type=bool
            )
        )

    def save_settings(self):
        self.settings.setValue(
            "wallet", self.wallet.text().strip()
        )
        self.settings.setValue(
            "pool", self.pool.text().strip()
        )
        self.settings.setValue(
            "threads", self.threads.value()
        )
        self.settings.setValue(
            "tls", self.tls.isChecked()
        )
        self.settings.sync()

    def log(self, message):
        self.logs.appendPlainText(str(message))

    def validate(self):
        wallet = self.wallet.text().strip()
        pool = self.pool.text().strip()

        if (
            len(wallet) not in (95, 106)
            or wallet[0] not in "48"
            or not all(c in BASE58 for c in wallet)
        ):
            raise ValueError(
                "Enter a valid-format Monero address "
                "(95 or 106 characters)."
            )

        match = re.fullmatch(
            r"([A-Za-z0-9][A-Za-z0-9.-]*):([0-9]{1,5})",
            pool
        )
        if not match:
            raise ValueError(
                "Pool must be hostname:port."
            )

        port = int(match.group(2))
        if not 1 <= port <= 65535:
            raise ValueError("Invalid pool port.")

    def set_controls(self, mining):
        self.start_button.setEnabled(not mining)
        self.stop_button.setEnabled(mining)

        for control in (
            self.wallet, self.pool,
            self.threads, self.tls
        ):
            control.setEnabled(not mining)

    def start_mining(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return

        if not ENGINE.is_file() or not os.access(
            ENGINE, os.X_OK
        ):
            QMessageBox.warning(
                self, "XMRig missing",
                f"Executable not found:\n{ENGINE}"
            )
            return

        try:
            self.validate()
        except ValueError as error:
            QMessageBox.warning(
                self, "Invalid configuration", str(error)
            )
            return

        self.save_settings()
        self.chart.reset()

        self.hashrate_label.setText("0.0")
        self.accepted_label.setText("0")
        self.rejected_label.setText("0")
        self.uptime_label.setText("00:00:00")

        self.port = api_port()
        self.stopping = False

        arguments = [
            "--coin=monero",
            "--url", self.pool.text().strip(),
            "--user", self.wallet.text().strip(),
            "--pass", "x",
            "--threads", str(self.threads.value()),
            "--http-host=127.0.0.1",
            f"--http-port={self.port}",
            "--print-time=10",
            "--no-color",
            "--no-title",
        ]

        if self.tls.isChecked():
            arguments.append("--tls")

        self.process.setWorkingDirectory(str(Path.home()))

        self.process.start(str(ENGINE), arguments)
        self.set_controls(True)
        self.status.setText("● STARTING")
        self.log("Starting XMRig...")

    def on_started(self):
        self.status.setText("● MINER RUNNING")
        self.log(
            "XMRig process started. "
            "Waiting for pool connection."
        )

    def read_output(self):
        output = bytes(
            self.process.readAllStandardOutput()
        ).decode("utf-8", errors="replace")

        if output:
            self.log(output.rstrip())

    def on_process_error(self, error):
        self.log(
            f"Process error: "
            f"{self.process.errorString()}"
        )

    def stop_mining(self):
        if self.process.state() == QProcess.ProcessState.NotRunning:
            return

        self.stopping = True
        self.status.setText("● STOPPING")
        self.stop_button.setEnabled(False)
        self.log("Stop requested by user.")
        self.process.terminate()

        QTimer.singleShot(3000, self.force_stop)

    def force_stop(self):
        if (
            self.stopping
            and self.process.state()
            != QProcess.ProcessState.NotRunning
        ):
            self.log("Miner did not exit; killing process.")
            self.process.kill()

    def on_finished(self, exit_code, exit_status):
        self.read_output()
        self.status.setText("● OFFLINE")
        self.set_controls(False)
        self.stopping = False
        self.port = None
        self.hashrate_label.setText("0.0")
        self.log(f"Miner exited: code {exit_code}")

    def refresh_stats(self):
        if (
            self.process.state()
            != QProcess.ProcessState.Running
            or self.port is None
        ):
            return

        try:
            url = (
                f"http://127.0.0.1:"
                f"{self.port}/1/summary"
            )
            with urlopen(url, timeout=0.35) as response:
                data = json.load(response)

            rates = data.get("hashrate", {}).get(
                "total", []
            )
            rate = next(
                (
                    float(x)
                    for x in rates
                    if isinstance(x, (float, int))
                ),
                0.0
            )

            results = data.get("results", {})
            accepted = int(
                results.get("shares_good", 0)
            )
            total = int(
                results.get("shares_total", 0)
            )
            rejected = max(0, total - accepted)

            self.hashrate_label.setText(
                f"{rate:,.1f}"
            )
            self.accepted_label.setText(
                str(accepted)
            )
            self.rejected_label.setText(
                str(rejected)
            )
            self.uptime_label.setText(
                format_uptime(data.get("uptime", 0))
            )
            self.chart.add(rate)

            connection = data.get("connection", {})
            if connection.get("pool"):
                self.status.setText("● POOL CONNECTED")

        except (
            OSError, ValueError, TypeError,
            KeyError, json.JSONDecodeError
        ):
            # API might still be initializing.
            pass

    def closeEvent(self, event):
        self.save_settings()

        if (
            self.process.state()
            != QProcess.ProcessState.NotRunning
        ):
            self.process.terminate()
            if not self.process.waitForFinished(2000):
                self.process.kill()
                self.process.waitForFinished(1000)

        event.accept()



from licensing_ui import LicensedMinerMixin

class LicensedDarkMiner(LicensedMinerMixin, DarkMiner):
    pass


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = LicensedDarkMiner()
    window.show()
    sys.exit(app.exec())
