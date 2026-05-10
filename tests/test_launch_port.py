import unittest
from unittest.mock import MagicMock, patch

import app


class LaunchPortTests(unittest.TestCase):
    def test_uses_preferred_port_when_available(self):
        with patch("app.socket.socket") as socket_factory:
            preferred_socket = socket_factory.return_value.__enter__.return_value

            port = app.find_available_port("127.0.0.1", 5000)

        self.assertEqual(port, 5000)
        preferred_socket.bind.assert_called_once_with(("127.0.0.1", 5000))

    def test_falls_back_to_free_port_when_preferred_port_is_unavailable(self):
        preferred_socket = MagicMock()
        preferred_socket.bind.side_effect = OSError("forbidden")

        fallback_socket = MagicMock()
        fallback_socket.getsockname.return_value = ("127.0.0.1", 51234)

        with patch("app.socket.socket") as socket_factory:
            socket_factory.return_value.__enter__.side_effect = [
                preferred_socket,
                fallback_socket,
            ]

            port = app.find_available_port("127.0.0.1", 5000)

        self.assertEqual(port, 51234)
        preferred_socket.bind.assert_called_once_with(("127.0.0.1", 5000))
        fallback_socket.bind.assert_called_once_with(("127.0.0.1", 0))

    def test_source_launch_disables_reloader_so_selected_port_is_stable(self):
        with (
            patch("app.find_available_port", return_value=61234),
            patch("builtins.print"),
            patch.object(app.app, "run") as run_server,
            patch("app.Timer") as timer,
        ):
            app.run_desktop_app(is_frozen=False)

        timer.assert_not_called()
        run_server.assert_called_once_with(
            host=app.HOST,
            port=61234,
            debug=True,
            use_reloader=False,
        )

    def test_frozen_launch_opens_browser_on_selected_port(self):
        with (
            patch("app.find_available_port", return_value=61234),
            patch("builtins.print"),
            patch.object(app.app, "run") as run_server,
            patch("app.Timer") as timer,
        ):
            app.run_desktop_app(is_frozen=True)

        timer.assert_called_once_with(
            1.5,
            app.open_browser,
            args=(app.HOST, 61234),
        )
        timer.return_value.start.assert_called_once_with()
        run_server.assert_called_once_with(
            host=app.HOST,
            port=61234,
            debug=False,
            use_reloader=False,
        )


if __name__ == "__main__":
    unittest.main()
