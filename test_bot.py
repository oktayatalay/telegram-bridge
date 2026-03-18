"""
Telegram Claude Bridge — birim testleri
bot_poller.py fonksiyonlarını import etmeden, fonksiyonları izole ederek test eder.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import subprocess


# ─── Fonksiyonlar (bot_poller.py'den izole kopyalar) ─────────────────────────
# bot_poller.py modülü yüklenirken config.env okuduğu için doğrudan import
# mümkün değil. Fonksiyonları burada parametrik hale getirerek test ediyoruz.

def get_active_session(active_session_file):
    """Aktif session adını döner, dosya yoksa None döner."""
    if os.path.exists(active_session_file):
        with open(active_session_file) as f:
            return f.read().strip()
    return None


def set_active_session(name, active_session_file):
    """Session adını dosyaya yazar."""
    with open(active_session_file, "w") as f:
        f.write(name)


def tmux_list_sessions():
    """Mevcut tmux session listesini döner. tmux yoksa None döner."""
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return []
        sessions = [s.strip() for s in result.stdout.strip().splitlines() if s.strip()]
        return sessions
    except FileNotFoundError:
        return None
    except Exception:
        return []


def tmux_send(session, text):
    """Aktif session'a metin gönderir, başarısızsa False döner."""
    try:
        result = subprocess.run(
            ["tmux", "send-keys", "-t", session, text, "Enter"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False
    except Exception:
        return False


# ─── Test sınıfları ───────────────────────────────────────────────────────────

class TestGetActiveSession(unittest.TestCase):

    def test_returns_none_when_file_missing(self):
        """active_session.txt yoksa None dönmeli."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_file = os.path.join(tmpdir, "active_session.txt")
            result = get_active_session(fake_file)
            self.assertIsNone(result)

    def test_returns_content_when_file_exists(self):
        """Dosya varsa içeriği (strip'lenmiş) döndürmeli."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("myproject\n")
            tmp_path = f.name
        try:
            result = get_active_session(tmp_path)
            self.assertEqual(result, "myproject")
        finally:
            os.unlink(tmp_path)

    def test_returns_stripped_content(self):
        """Dosyadaki whitespace strip'lenmeli."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("  session-x  \n")
            tmp_path = f.name
        try:
            result = get_active_session(tmp_path)
            self.assertEqual(result, "session-x")
        finally:
            os.unlink(tmp_path)


class TestSetActiveSession(unittest.TestCase):

    def test_writes_name_to_file(self):
        """set_active_session dosyaya doğru içeriği yazmalı."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_file = os.path.join(tmpdir, "active_session.txt")
            set_active_session("test-session", fake_file)
            with open(fake_file) as f:
                content = f.read()
            self.assertEqual(content, "test-session")

    def test_overwrites_existing_file(self):
        """Mevcut dosyayı üzerine yazmalı."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("old-session")
            tmp_path = f.name
        try:
            set_active_session("new-session", tmp_path)
            with open(tmp_path) as f:
                content = f.read()
            self.assertEqual(content, "new-session")
        finally:
            os.unlink(tmp_path)

    def test_roundtrip_with_get(self):
        """set sonrası get aynı değeri döndürmeli."""
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_file = os.path.join(tmpdir, "active_session.txt")
            set_active_session("roundtrip-session", fake_file)
            result = get_active_session(fake_file)
            self.assertEqual(result, "roundtrip-session")


class TestListSessions(unittest.TestCase):

    @patch("subprocess.run")
    def test_returns_empty_list_when_tmux_no_sessions(self, mock_run):
        """tmux çalışıyor ama session yoksa boş liste döner."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_run.return_value = mock_result
        result = tmux_list_sessions()
        self.assertEqual(result, [])

    @patch("subprocess.run")
    def test_returns_session_list_when_tmux_has_sessions(self, mock_run):
        """tmux çalışıyor ve session varsa liste döner."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "session1\nsession2\nmyproject\n"
        mock_run.return_value = mock_result
        result = tmux_list_sessions()
        self.assertEqual(result, ["session1", "session2", "myproject"])

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_returns_none_when_tmux_not_installed(self, mock_run):
        """tmux kurulu değilse None döner."""
        result = tmux_list_sessions()
        self.assertIsNone(result)

    @patch("subprocess.run")
    def test_filters_empty_lines(self, mock_run):
        """Boş satırlar filtrelenmeli."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "s1\n\ns2\n\n"
        mock_run.return_value = mock_result
        result = tmux_list_sessions()
        self.assertEqual(result, ["s1", "s2"])


class TestTmuxSend(unittest.TestCase):

    @patch("subprocess.run")
    def test_returns_true_on_success(self, mock_run):
        """send-keys başarılıysa True dönmeli."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        result = tmux_send("mysession", "hello")
        self.assertTrue(result)

    @patch("subprocess.run")
    def test_returns_false_on_failure(self, mock_run):
        """send-keys başarısızsa False dönmeli."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result
        result = tmux_send("nosession", "hello")
        self.assertFalse(result)

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_returns_false_when_tmux_not_found(self, mock_run):
        """tmux kurulu değilse False dönmeli."""
        result = tmux_send("session", "text")
        self.assertFalse(result)

    @patch("subprocess.run")
    def test_sends_correct_args(self, mock_run):
        """subprocess.run'a doğru argümanlar iletilmeli."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        tmux_send("work", "ls -la")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        self.assertIn("work", args)
        self.assertIn("ls -la", args)
        self.assertIn("Enter", args)


if __name__ == "__main__":
    unittest.main()
