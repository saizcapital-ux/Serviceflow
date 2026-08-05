"""Tests for email dispatch mode selection and the /health email indicator."""
from unittest.mock import patch

from app.core.config import Settings
from app.services import notifications


def test_health_reports_console_when_no_smtp(client):
    # Test env has no SMTP configured.
    assert client.get("/health").json()["email"] == "console"


def test_console_backend_does_not_open_smtp(monkeypatch):
    monkeypatch.setattr(notifications.settings, "smtp_host", "")
    with patch("smtplib.SMTP") as m_smtp, patch("smtplib.SMTP_SSL") as m_ssl:
        notifications._dispatch_email("a@b.com", "subject", "body")
    assert not m_smtp.called and not m_ssl.called  # logged, not sent


def test_starttls_path(monkeypatch):
    cfg = Settings(smtp_host="smtp.example.com", smtp_port=587, smtp_ssl=False)
    monkeypatch.setattr(notifications, "settings", cfg)
    with patch("smtplib.SMTP") as m_smtp, patch("smtplib.SMTP_SSL") as m_ssl:
        notifications._dispatch_email("a@b.com", "subject", "body")
    assert m_smtp.called and not m_ssl.called
    assert m_smtp.return_value.starttls.called
    assert m_smtp.return_value.send_message.called


def test_implicit_ssl_path(monkeypatch):
    cfg = Settings(smtp_host="smtp.example.com", smtp_port=465, smtp_ssl=True)
    monkeypatch.setattr(notifications, "settings", cfg)
    with patch("smtplib.SMTP") as m_smtp, patch("smtplib.SMTP_SSL") as m_ssl:
        notifications._dispatch_email("a@b.com", "subject", "body")
    assert m_ssl.called and not m_smtp.called
    # No STARTTLS on an already-encrypted connection.
    assert not m_ssl.return_value.starttls.called
    assert m_ssl.return_value.send_message.called
