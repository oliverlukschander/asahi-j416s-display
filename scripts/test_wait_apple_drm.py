import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location('wait_drm', Path(__file__).with_name('wait-apple-drm.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class ReadyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.sysfs, self.dev = root / 'sys', root / 'dev'
        self.sysfs.mkdir()
        self.dev.mkdir()

    def connector(self, card='card7', driver='apple-drm', modes='3456x2160\n'):
        device = self.sysfs / card / 'device'
        device.mkdir(parents=True)
        target = self.sysfs / 'drivers' / driver
        target.mkdir(parents=True, exist_ok=True)
        (device / 'driver').symlink_to(target)
        con = self.sysfs / (card + '-eDP-1')
        con.mkdir()
        (con / 'status').write_text('connected\n')
        (con / 'modes').write_text(modes)
        (self.dev / card).symlink_to('/dev/null')
        return con

    def test_waits_for_absent_device(self):
        self.assertIsNone(module.ready_card(self.sysfs, self.dev))

    def test_accepts_dynamic_card_number(self):
        self.connector()
        self.assertEqual(module.ready_card(self.sysfs, self.dev), 'card7')

    def test_rejects_other_driver(self):
        self.connector(driver='simple-framebuffer')
        self.assertIsNone(module.ready_card(self.sysfs, self.dev))

    def test_waits_for_modes(self):
        con = self.connector(modes='')
        self.assertIsNone(module.ready_card(self.sysfs, self.dev))
        (con / 'modes').write_text('3456x2160\n')
        self.assertEqual(module.ready_card(self.sysfs, self.dev), 'card7')

    def test_rejects_disconnected_panel(self):
        con = self.connector()
        (con / 'status').write_text('disconnected\n')
        self.assertIsNone(module.ready_card(self.sysfs, self.dev))

    def test_timeout_and_delayed_registration(self):
        self.assertEqual(module.wait_for_display(0, lambda: None), 1)
        replies = iter([None, 'card9'])
        self.assertEqual(module.wait_for_display(1, lambda: next(replies)), 0)

if __name__ == '__main__':
    unittest.main()
