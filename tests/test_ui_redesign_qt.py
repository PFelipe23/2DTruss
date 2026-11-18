"""Smoke-test Qt real: executado quando PySide6 estiver instalado no host."""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch

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

    def test_3d_closes_when_project_changes(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        from desktop.bridge import ROOT, Session
        from desktop.qt.app import DesktopApp

        app = QApplication.instance() or QApplication([])
        window = DesktopApp(Session())
        try:
            path = ROOT / 'examples' / 'FTool_A02_trelica_triangular.json'
            for replace_project in (window.new, window.open):
                with self.subTest(action=replace_project.__name__):
                    window.calculate()
                    window.open_3d()
                    self.assertTrue(window._view3d.axial())
                    with patch('PySide6.QtWidgets.QFileDialog.getOpenFileName',
                               return_value=(str(path), '')):
                        replace_project()
                    self.assertIsNone(window._view3d)
                    self.assertIsNone(window.session.result)

            window.open_3d()
            self.assertIs(window._view3d.session, window.session)
            self.assertFalse(window._view3d.axial())
            self.assertEqual(window.filepath, Path(path))
        finally:
            if window._view3d is not None:
                window._view3d.close()
            window.close()

    def test_open_3d_follows_recalculation_and_history(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        from desktop.bridge import Session
        from desktop.qt.app import DesktopApp

        app = QApplication.instance() or QApplication([])
        window = DesktopApp(Session())
        try:
            window.open_3d()
            dialog = window._view3d
            window.calculate()
            member = next(iter(dialog.axial()))
            dialog.inspect_member(member)
            self.assertIn('kN', dialog.selected_label.text())

            self.assertTrue(window._apply(window.session.project))
            for change in (window.undo, window.redo):
                window.calculate()
                self.assertTrue(dialog.axial())
                change()
                self.assertFalse(dialog.axial())
                self.assertNotIn('kN', dialog.selected_label.text())
        finally:
            window._dirty = False
            if window._view3d is not None:
                window._view3d.close()
            window.close()


if __name__=='__main__':unittest.main()
