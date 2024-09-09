import unittest
from unittest.mock import patch, Mock
from main import send_callback

class TestSendCallback(unittest.TestCase):
    def test_send_callback_with_empty_messages(self):
        callback_url = "https://example.com/callback"
        sale_token = "example-sale-token"
        client_id = "example-client-id"
        messages = []

        mock_response = Mock()
        mock_response.raise_for_status.return_value = None

        with patch("requests.post") as mock_post:
            mock_post.return_value = mock_response

            send_callback(callback_url, sale_token, client_id, messages)

            mock_post.assert_called_once_with(
                callback_url,
                json={"client_id": client_id, "messages": messages},
                headers={"Authorization": f"Bearer {sale_token}", "Content-Type": "application/json"},
            )

if __name__ == "__main__":
    unittest.main()