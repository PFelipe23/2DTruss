"""Smoke-test Qt real: executado quando PySide6 estiver instalado no host."""
from __future__ import annotations
import importlib.util
import os
import unittest

HAS_QT=importlib.util.find_spec('PySide6') is not None


@unittest.skipUnless(HAS_QT,'PySide6 ausente neste ambiente; teste gráfico pendente no Windows')
class QtRedesignSmoke(unittest.TestCase):
    def test_window_tasks_and_3d_real_section(self):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        from desktop.bridge import Session
        from desktop.qt.app import DesktopApp
        app=QApplication.instance() or QApplication([])
        window=DesktopApp(Session())
        try:
            self.assertGreater(window.task_tree.topLevelItemCount(),2)
            self.assertGreater(window.info_tabs.count(),8)
            self.assertTrue(window.info_tabs.tabBar().isHidden())
            self.assertIsNotNone(window.quick_table)
            window.open_3d()
            dialog=window._view3d
            dialog._ensure_meshes()
            self.assertGreater(len(dialog._meshes),len(window.session.model.members))
            self.assertTrue(all(len(m.faces)>=8 for m in dialog._meshes))
            dialog.group.setCurrentText('diagonal')
            dialog.update_section_preview()
            self.assertTrue(dialog.section_preview.scene().items())
        finally:
            if window._view3d:window._view3d.close()
            window.close()


if __name__=='__main__':unittest.main()
