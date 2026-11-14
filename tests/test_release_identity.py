"""Contrato de identificação externa e migração 2DTruss v0.1."""
from pathlib import Path
import unittest
from poe_truss import __version__
from poe_truss.version import APP_NAME, TAG

ROOT = Path(__file__).resolve().parents[1]

class ReleaseIdentityTests(unittest.TestCase):
    def test_public_identity_single_decimal(self):
        self.assertEqual(APP_NAME, '2DTruss')
        self.assertEqual(__version__, '0.1')
        self.assertEqual(TAG, 'v0.1')

    def test_desktop_entry_point_exists(self):
        self.assertTrue((ROOT/'2DTruss.pyw').exists())
        self.assertFalse((ROOT/'POE_Trelica.pyw').exists())

    def test_launcher_uses_current_entry_point(self):
        for name in ('INICIAR_DESKTOP.bat', 'INICIAR_DESKTOP.sh', 'BUILD_EXE_WINDOWS.bat'):
            contents = (ROOT/name).read_text(encoding='utf-8')
            self.assertIn('2DTruss.pyw', contents)

if __name__ == '__main__':
    unittest.main()
