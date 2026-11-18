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
    def test_force_vectors_stay_above_nodes_and_labels_fit_without_overlap(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtCore import QPointF
        from PySide6.QtWidgets import QApplication, QGraphicsSimpleTextItem
        from desktop.qt.app import DesktopApp
        from desktop.qt.viewport import ForceVectorItem, NodeItem

        app = QApplication.instance() or QApplication([])
        for fx, fy in [(0, -10), (0, 10), (10, 0), (-6, 8), (6, -8)]:
            with self.subTest(fx=fx, fy=fy):
                vector = ForceVectorItem('N1', QPointF(), fx, fy, 10)
                tail, head = (vector.path().elementAt(i) for i in (0, 1))
                self.assertLess(vector.boundingRect().bottom(), -7)
                self.assertAlmostEqual(head.x - tail.x, 5 * fx)
                self.assertAlmostEqual(head.y - tail.y, -5 * fy)

        window = DesktopApp()
        window.show()
        try:
            window.open_general_actions()
            window.cases.setCurrentText('W_UP')
            window._set_overlay('show_ids', True)
            window.force_values.click()
            app.processEvents()
            window.fit()
            view = window.view
            view.scale(.45, .45)
            view._place_force_labels()
            transform = view.viewportTransform()
            annotations = {
                item.text() for item in view.scene().items()
                if isinstance(item, QGraphicsSimpleTextItem) and item.parentItem() is None
            }
            self.assertIn('△ XY', annotations)
            self.assertIn(window.session.model.nodes[0].id, annotations)
            other_items = [
                item.deviceTransform(transform).mapRect(item.boundingRect())
                for item in view.items(view.viewport().rect())
                if isinstance(item, (NodeItem, ForceVectorItem))
                or isinstance(item, QGraphicsSimpleTextItem) and item.parentItem() is None
            ]
            labels = []
            for vector in view._force_items:
                if not vector.label.isVisible():
                    continue
                rect = vector.label.deviceTransform(transform).mapRect(vector.label.boundingRect())
                self.assertTrue(view.viewport().rect().contains(rect.toAlignedRect()))
                self.assertFalse(any(rect.intersects(other) for other in other_items + labels))
                labels.append(rect)
            self.assertGreater(len(labels), 0)
            self.assertLess(len(labels), len(view._force_items))
        finally:
            window.close()

    def test_batch_nodal_loads_follow_the_canvas_case_and_edit_one_parcel(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from desktop.bridge import Session, load_project
        from desktop.qt.app import DesktopApp

        app = QApplication.instance() or QApplication([])
        project = load_project()
        project['load_cases'].extend([
            {'id': 'Q_EMPTY', 'kind': 'nodal', 'loads': []},
            {'id': 'Q_NODAL', 'kind': 'nodal', 'loads': []},
        ])
        project['combinations'].append({'id': 'COMB_UI', 'factors': {'Q_EMPTY': 1, 'Q_NODAL': 2}})
        window = DesktopApp(Session(project))
        window.show()
        try:
            window.open_nodal_loads()
            window.load_case.setCurrentText('Q_NODAL')
            app.processEvents()
            window.fit()
            nodes = [node.id for node in window.session.model.nodes[1:3]]
            for index, node in enumerate(nodes):
                position = window.view.mapFromScene(window.view.selection_item('node', node).pos())
                modifier = Qt.KeyboardModifier.ControlModifier if index else Qt.KeyboardModifier.NoModifier
                QTest.mouseClick(window.view.viewport(), Qt.MouseButton.LeftButton, modifier, position)
            window.fx.setValue(1)
            window.fy.setValue(-2)
            self.assertEqual(window.case_id, 'Q_NODAL')
            self.assertTrue(window.batch_load.isEnabled())
            self.assertEqual(set(window._selected_load_nodes()), set(nodes))
            QTest.mouseClick(window.batch_load, Qt.MouseButton.LeftButton)
            self.assertEqual(window.load_table.rowCount(), 2)
            self.assertEqual(len(window.view._force_items), 2)
            self.assertIn('ΣFy -4.00', window.force_summary.text())

            window.load_table.selectRow(0)
            window.fy.setValue(-1)
            QTest.mouseClick(window.commit_load, Qt.MouseButton.LeftButton)
            self.assertEqual(window.load_table.rowCount(), 2)
            self.assertIn('ΣFy -3.00', window.force_summary.text())
            window.cases.setCurrentText('COMB_UI')
            self.assertIn('ΣFy -6.00', window.force_summary.text())
            window.load_case.setCurrentText('Q_EMPTY')
            self.assertEqual(window.case_id, 'Q_EMPTY')
            self.assertFalse(window.view._force_items)
            self.assertIn('Sem cargas', window.force_summary.text())
        finally:
            window._dirty = False
            window.close()

    def test_profiles_and_steel_update_the_active_3d_view(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        from desktop.qt.app import DesktopApp

        app = QApplication.instance() or QApplication([])
        window = DesktopApp()
        window.show()
        try:
            window.open_3d()
            view = window._view3d
            self.assertIs(window.canvas_stack.currentWidget(), view)
            group = view.group.currentText()
            self.assertEqual(view.profile_picker.count.value(), 2)
            profile = 'W 150 x 13,0'
            view.profile_picker.family.setCurrentText('W (laminado)')
            view.profile_picker.profile.setCurrentText(profile)
            view.profile_picker.profile.activated.emit(view.profile_picker.profile.currentIndex())

            section = window.session.project['sections'][group]
            self.assertEqual(section, {'profile': profile, 'count': 1})
            members = [member for member in window.session.model.members if member.group == group]
            self.assertTrue(members)
            for member in members:
                self.assertAlmostEqual(member.area, 1660)
            self.assertTrue(all(view._member_meta[member.id]['profile'] == profile for member in members))

            view.rotation.setValue(90)
            self.assertEqual(window.session.project['section_arrangements'][group]['rotation_deg'], 90)
            self.assertEqual(view._mesh_revision, window.session.revision)

            revision = window.session.revision
            window.geom_fields['span_m'].setValue(window.geom_fields['span_m'].value() + 1)
            self.assertGreater(window.session.revision, revision)
            self.assertEqual(view._mesh_revision, window.session.revision)

            window.calculate()
            self.assertTrue(view.axial())
            window.steel_grade.setCurrentIndex(window.steel_grade.findData('a572gr50'))
            window.steel_grade.activated.emit(window.steel_grade.currentIndex())
            self.assertEqual(window.session.project['material']['fy_MPa'], 345)
            self.assertIsNone(window.session.result)
            self.assertFalse(view.axial())
            window.set_3d_visible(False)
            self.assertIs(window.canvas_stack.currentWidget(), window.view)
            self.assertTrue(all(window.view.selection_item('member', member.id) for member in members))
        finally:
            window._dirty = False
            window.close()

    def test_workspace_selection_results_and_drawing_only(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from desktop.qt.app import DesktopApp

        app = QApplication.instance() or QApplication([])
        window = DesktopApp()
        window.show()
        try:
            member = window.session.model.members[0]
            key = ('member', member.id)
            window._model_items[key].setSelected(True)
            self.assertEqual(window.view.selected_ids(), [key])
            self.assertTrue(window.member_properties.isVisible())
            self.assertFalse(window.node_properties.isVisible())

            window.calculate()
            self.assertTrue(window.results_panel.isVisible())
            self.assertGreater(window.quick_table.rowCount(), 0)
            self.assertEqual(window.view.selected_ids(), [key])
            window.quick_select_member(0, 0)
            first_result = ('member', window.quick_table.item(0, 0).text())
            self.assertEqual(window.view.selected_ids(), [first_result])
            self.assertTrue(window._model_items[first_result].isSelected())

            QTest.mouseClick(window.focus_button, Qt.MouseButton.LeftButton)
            self.assertFalse(window.navigator.isVisible())
            self.assertFalse(window.results_panel.isVisible())
            QTest.mouseClick(window.focus_button, Qt.MouseButton.LeftButton)
            self.assertTrue(window.navigator.isVisible())
            self.assertTrue(window.results_panel.isVisible())

            QTest.mouseClick(window.grid, Qt.MouseButton.LeftButton)
            self.assertFalse(window.view.grid_visible)
            self.assertTrue(window.view.snap_enabled)
            self.assertTrue(window._apply(window.session.project))
            self.assertEqual(window.quick_table.rowCount(), 0)
        finally:
            window._dirty = False
            window.close()

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

    def test_3d_rebinds_when_project_changes(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        from desktop.bridge import ROOT, Session
        from desktop.qt.app import DesktopApp

        app = QApplication.instance() or QApplication([])
        window = DesktopApp(Session())
        window.show()
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
                    self.assertIs(window.canvas_stack.currentWidget(), window._view3d)
                    self.assertIs(window._view3d.session, window.session)
                    self.assertFalse(window._view3d.axial())
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
