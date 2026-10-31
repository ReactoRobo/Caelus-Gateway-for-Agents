import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('caelus', Path(__file__).resolve().parents[1] / 'scripts/caelus.py')
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


class ClientBoundary(unittest.TestCase):
    def test_only_clean_https_or_loopback_endpoints(self):
        for value in ('https://gateway.example.com/mcp', 'http://127.0.0.1:18890/mcp'):
            self.assertEqual(client.endpoint(value), value)
        for value in ('http://gateway.example.com/mcp', 'https://u:p@gateway.example.com/mcp',
                      'https://gateway.example.com/mcp?key=secret', 'https://gateway.example.com/mcp#x',
                      'https://gateway.example.com/other', 'https://gateway.example.com:bad/mcp'):
            with self.assertRaises(ValueError):
                client.endpoint(value)
        self.assertIsNone(client.NoRedirect().redirect_request(None, None, None, None, None, None))

    @unittest.skipUnless(os.name == 'posix', 'POSIX credential storage')
    def test_private_profile_and_unsafe_permissions_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = client.Profile(Path(directory) / 'private')
            data = dict(url='https://gateway.example.com/mcp', token='fixture-not-a-live-secret')
            profile.save(data)
            self.assertEqual(profile.read(), data)
            self.assertEqual(profile.path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(profile.directory.stat().st_mode & 0o777, 0o700)
            profile.path.chmod(0o644)
            with self.assertRaises(ValueError):
                profile.read()
            profile.path.unlink()
            target = Path(directory) / 'other'
            target.write_text(json.dumps(data))
            profile.path.symlink_to(target)
            with self.assertRaises(OSError):
                profile.read()


if __name__ == '__main__':
    unittest.main()
