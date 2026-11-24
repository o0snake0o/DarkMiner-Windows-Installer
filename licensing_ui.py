
"""DarkMiner v0.4 account and licensing interface."""

import json
import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QTimer, QUrl
from PySide6.QtNetwork import (
    QNetworkAccessManager, QNetworkReply, QNetworkRequest
)
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPushButton, QVBoxLayout
)


def get_api_url():
    root = Path(getattr(
        sys, "_MEIPASS",
        Path(__file__).resolve().parent
    ))
    path = root / "license_config.json"

    with path.open(encoding="utf-8") as f:
        url = json.load(f)["api_url"].rstrip("/")

    if not (
        url.startswith("https://")
        or url.startswith("http://127.0.0.1:")
    ):
        raise ValueError("License API must use HTTPS")

    return url


class AccountDialog(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle("DarkMiner Account")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Sign in or create your DarkMiner account"
        ))

        form = QFormLayout()
        self.email = QLineEdit()
        self.email.setPlaceholderText("you@example.com")

        self.password = QLineEdit()
        self.password.setEchoMode(
            QLineEdit.EchoMode.Password
        )

        form.addRow("Email:", self.email)
        form.addRow("Password:", self.password)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        login = QPushButton("Log in")
        register = QPushButton("Register")

        login.clicked.connect(
            lambda: self.submit("login")
        )
        register.clicked.connect(
            lambda: self.submit("register")
        )

        buttons.addWidget(register)
        buttons.addWidget(login)
        layout.addLayout(buttons)

        self.message = QLabel(
            "New accounts receive a 3-day trial."
        )
        self.message.setWordWrap(True)
        layout.addWidget(self.message)

        self.buttons = (login, register)

    def submit(self, action):
        email = self.email.text().strip()
        password = self.password.text()

        if "@" not in email or len(password) < 10:
            self.message.setText(
                "Enter a valid email and password "
                "of at least 10 characters."
            )
            return

        for button in self.buttons:
            button.setEnabled(False)

        self.message.setText("Contacting license server...")

        def completed(data, error):
            for button in self.buttons:
                button.setEnabled(True)

            if error:
                self.message.setText(error)
                return

            if action == "register":
                self.message.setText(
                    "Registration successful. "
                    "Now click Log in."
                )
                self.password.clear()
                return

            self.owner.token = data["access_token"]
            self.owner.license_label.setText(
                "Account: Checking license..."
            )
            self.accept()
            self.owner.check_license()

        self.owner.api_request(
            "/" + action,
            {"email": email, "password": password},
            completed
        )


class LicensedMinerMixin:
    """Adds licensing to the existing DarkMiner window."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.start_button.clicked.disconnect()
        self.start_button.clicked.connect(self.start_mining)
        self.token = None
        self.license_active = False
        self.api_url = get_api_url()
        self.network = QNetworkAccessManager(self)

        self.account_button = QPushButton(
            "Register / Login"
        )
        self.account_button.clicked.connect(
            self.open_account
        )

        self.logout_button = QPushButton("Log out")
        self.logout_button.clicked.connect(
            self.logout
        )
        self.logout_button.setEnabled(False)

        self.license_label = QLabel(
            "Account: Not signed in"
        )

        row = QHBoxLayout()
        row.addWidget(self.account_button)
        row.addWidget(self.logout_button)
        row.addWidget(self.license_label, 1)

        self.centralWidget().layout().insertLayout(1, row)
        self.start_button.setEnabled(False)

        self.license_timer = QTimer(self)
        self.license_timer.timeout.connect(
            self.background_license_check
        )
        self.license_timer.start(10000)

        QTimer.singleShot(300, self.open_account)

    def open_account(self):
        self.account_dialog = AccountDialog(self)
        self.account_dialog.exec()

    def api_request(self, path, payload, callback):
        request = QNetworkRequest(
            QUrl(self.api_url + path)
        )
        request.setHeader(
            QNetworkRequest.KnownHeaders.ContentTypeHeader,
            "application/json"
        )
        request.setRawHeader(
            b"Accept", b"application/json"
        )

        if self.token:
            request.setRawHeader(
                b"Authorization",
                ("Bearer " + self.token).encode("ascii")
            )

        request.setTransferTimeout(10000)

        if payload is None:
            reply = self.network.get(request)
        else:
            reply = self.network.post(
                request,
                QByteArray(json.dumps(payload).encode())
            )

        def finished():
            raw = bytes(reply.readAll())
            try:
                data = json.loads(raw or b"{}")
            except (ValueError, UnicodeDecodeError):
                data = {}

            error = None
            if reply.error() != QNetworkReply.NetworkError.NoError:
                error = str(
                    data.get("detail", reply.errorString())
                )

            reply.deleteLater()
            callback(data, error)

        reply.finished.connect(finished)

    def check_license(self, on_success=None):
        if not self.token:
            self.license_active = False
            self.start_button.setEnabled(False)
            return

        def completed(data, error):
            if error:
                self.license_active = False
                self.license_label.setText(
                    "License check failed: " + error
                )
                self.start_button.setEnabled(False)

                if self.running_miner():
                    self.stop_mining()

                return

            self.license_active = bool(
                data.get("active", False)
            )
            status = str(data.get("status", "unknown"))
            expiry = str(data.get("expires_at", "—"))

            self.license_label.setText(
                f"{status.upper()} · Expires: {expiry}"
            )

            if not self.license_active:
                self.start_button.setEnabled(False)
                if self.running_miner():
                    self.stop_mining()
                return

            if not self.running_miner():
                self.start_button.setEnabled(True)

            if on_success is not None:
                on_success()

        self.api_request(
            "/license", None, completed
        )


    def logout(self):
        if self.running_miner():
            self.stop_mining()

        self.token = None
        self.license_active = False
        self.start_button.setEnabled(False)
        self.account_button.setEnabled(True)
        self.logout_button.setEnabled(False)
        self.license_label.setText(
            "Account: Logged out"
        )

def stop_mining(self):
    # Peata kaevandamine ja keela käivitamine,
    # kuni litsents on uuesti kinnitatud.
    if self.running_miner():
        self.process.kill()

    self.license_active = False
    self.start_button.setEnabled(False)

    def running_miner(self):
        from PySide6.QtCore import QProcess
        return (
            self.process.state()
            != QProcess.ProcessState.NotRunning
        )

    def background_license_check(self):
        if self.token:
            self.check_license()

    def start_mining(self):
        # Always check the server before starting mining.
        if not self.token:
            QMessageBox.warning(
                self, "Login required",
                "Please log in before mining."
            )
            self.open_account()
            return

        self.start_button.setEnabled(False)

        def approved():
            if not self.running_miner():
                super(LicensedMinerMixin, self).start_mining()

        self.check_license(on_success=approved)

    def logout(self):
        if self.running_miner():
            self.stop_mining()

        self.token = None
        self.license_active = False

        self.start_button.setEnabled(False)
        self.account_button.setEnabled(True)
        self.logout_button.setEnabled(False)
        self.license_label.setText("Account: Logged out")

    def set_controls(self, mining):
        super().set_controls(mining)
        if hasattr(self, "token"):
            self.start_button.setEnabled(
                not mining and self.license_active
            )
            self.logout_button.setEnabled(
                bool(self.token)
            )
