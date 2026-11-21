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
    def test_window_selection_filter_middle_pan_and_midpoint_split(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from desktop.qt.app import DesktopApp

        app = QApplication.instance() or QApplication([])
        window = DesktopApp()
        window.show()
        try:
            app.processEvents()
            view = window.view
            view.configure_grid(125, 4)
            self.assertEqual((view.grid_mm, view.grid_major), (125, 4))
            window.selection_filter.setCurrentIndex(window.selection_filter.findData('member'))
            member = next(iter(view._members.values()))
            mid = view.mapFromScene(member.line().center())
            widget = view.viewport()
            QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=mid + QPoint(0, 4))
            self.assertIn(('member', member.member_id), view.selected_ids())

            first, last = mid - QPoint(12, 12), mid + QPoint(12, 12)
            def drag(start, end, button=Qt.MouseButton.LeftButton):
                QTest.mousePress(widget, button, pos=start)
                QTest.mouseMove(widget, end)
                QTest.mouseRelease(widget, button, pos=end)

            drag(first, last)
            self.assertNotIn(('member', member.member_id), view.selected_ids())
            drag(last, first)
            self.assertIn(('member', member.member_id), view.selected_ids())
            before_pan = view.mapToScene(widget.rect().center())
            drag(mid, mid + QPoint(30, 20), Qt.MouseButton.MiddleButton)
            self.assertNotEqual(before_pan, view.mapToScene(widget.rect().center()))
            self.assertIsNone(view._pan_position)
            self.assertEqual(view.tool, 'select')

            expected = member.line().center()
            click = view.mapFromScene(member.line().pointAt(.25))
            window.choose_tool('split')
            original = set(view._nodes)
            QTest.mouseClick(widget, Qt.MouseButton.LeftButton, pos=click)
            created, = set(view._nodes) - original
            self.assertLess((view._nodes[created].pos() - expected).manhattanLength(), 1e-8)
            self.assertTrue(window.session.model.chord_loads)
        finally:
            window._dirty = False
            window.close()

    def test_envelope_keeps_extremes_and_deformed_nodes_are_clickable(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from desktop.qt.app import DesktopApp
        from desktop.qt.result_display import displacement_peaks, envelope_values
        from desktop.qt.viewport import EnvelopeLabel

        app = QApplication.instance() or QApplication([])
        window = DesktopApp()
        window.show()
        try:
            window.cases.setCurrentText('S_GRAV')
            window.calculate()
            window.axial_source.setCurrentIndex(1)
            app.processEvents()
            result = window.session.result
            envelope = result['envelope']
            self.assertTrue(window.view.show_envelope)
            labels = [label for label in window.view._axial_labels if isinstance(label, EnvelopeLabel)]
            self.assertEqual(len(labels), len(window.session.model.members))
            self.assertEqual({label.font().pointSize() for label in labels}, {10})
            self.assertEqual({label.member_id for label in labels if label.isVisible()},
                             {label.member_id for label in labels if label.peak})
            secondary = next(label for label in labels if not label.peak)
            window._set_canvas_selection([('member', secondary.member_id)])
            self.assertTrue(secondary.isVisible())
            visible = next(label for label in labels if label.isVisible())
            position = visible.deviceTransform(window.view.viewportTransform()).map(visible.boundingRect().center())
            with patch.object(EnvelopeLabel, 'popup', autospec=True) as popup:
                QTest.mouseClick(window.view.viewport(), Qt.MouseButton.LeftButton, pos=position.toPoint())
                self.assertEqual(window.view.selected_ids(), [('member', visible.member_id)])
                popup.assert_called_once()
            self.assertTrue(any(top.startswith('+') and bottom.startswith('-')
                                for top, bottom in (label.values for label in labels)))
            table = window.quick_table
            member = table.item(0, 0).text()
            expected = envelope_values(envelope[member], window.units, unit=False)
            self.assertEqual(tuple(table.item(0, i).text() for i in (2, 3)), expected)
            for col, key in [(2, 'tension_case'), (3, 'compression_case')]:
                if envelope[member][key]:
                    self.assertIn(envelope[member][key], table.item(0, col).toolTip())
            window.cases.setCurrentText('W_UP')
            self.assertEqual(table.item(0, 0).text(), member)

            window.result_views.setCurrentIndex(1)
            app.processEvents()
            data = result['analyses']['W_UP']['nodal_displacements']
            peaks = displacement_peaks(data)
            self.assertTrue(peaks)
            self.assertEqual(set(window.view._peak_labels), set(peaks))
            node = next(iter(peaks))
            marker = window.view._deformed_nodes[node]
            self.assertTrue(marker.peak)
            for point in (marker.pos(), window.view.selection_item('node', node).pos()):
                window._set_canvas_selection([])
                QTest.mouseClick(window.view.viewport(), Qt.MouseButton.LeftButton,
                                 pos=window.view.mapFromScene(point))
                self.assertEqual(window.view.selected_ids(), [('node', node)])
                callout = window.view._displacement_callout
                self.assertIsNotNone(callout)
                self.assertTrue(callout.isVisible())
                self.assertIn(window.units.displacement_text(data[node]['uy_mm'], signed=True), callout.text())
        finally:
            window.close()

    def test_els_deformation_uses_a_governing_combination_and_node_restraint_is_independent(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtWidgets import QApplication
        from desktop.bridge import Session, load_project
        from desktop.qt.app import DesktopApp

        app = QApplication.instance() or QApplication([])
        project = load_project()
        project['combinations'].extend([
            {'id': 'ELS_MENOR', 'combination_class': 'sls_rare', 'factors': {'W_UP': .25}},
            {'id': 'ELS_CRITICO', 'combination_class': 'sls_frequent', 'factors': {'W_DOWN': 1}},
        ])
        window = DesktopApp(Session(project))
        window.show()
        try:
            window.calculate()
            self.assertEqual(window.axial_source.findData('els'), -1)
            window.result_views.setCurrentIndex(1)
            self.assertEqual(window.case_id, 'ELS_CRITICO')
            self.assertEqual(window.view._analysis_id, 'ELS_CRITICO')
            self.assertIn('ELS_CRITICO', window.dock_info.text())
            window.deformation_case.setCurrentIndex(window.deformation_case.findData('ELS_MENOR'))
            self.assertEqual(window.case_id, 'ELS_MENOR')
            self.assertIn('ELS_MENOR', window.dock_info.text())
            window.result_views.setCurrentIndex(0)
            window._set_canvas_selection([('node', 'T02')])
            window._update_selection([('node', 'T02')])
            window.node_lateral.setChecked(True)
            window.node_lateral_reference.setText('Detalhe T1')
            window.apply_node_properties()
            model = window.session.model
            self.assertNotIn('model_override', window.session.project)
            self.assertNotIn('T02', model.supports)
            self.assertEqual(window.view._nodes['T02'].restraint['reference'], 'Detalhe T1')
            self.assertIsNone(window.session.result)
        finally:
            window._dirty = False
            window.close()

    def test_result_views_select_diagrams_and_keep_displacements_unscaled(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from math import hypot
        from PySide6.QtCore import QPointF
        from PySide6.QtWidgets import QApplication, QGraphicsLineItem
        from desktop.qt.app import DesktopApp
        from desktop.qt.viewport import BoxedLabel

        app = QApplication.instance() or QApplication([])
        window = DesktopApp()
        window.show()
        try:
            window.cases.setCurrentText('S_GRAV')
            window.calculate()
            app.processEvents()
            self.assertTrue(window.view.show_efforts)
            boxes = []
            for item in window.view.scene().items():
                if isinstance(item, BoxedLabel) and item.isVisible():
                    rect = item.deviceTransform(window.view.viewportTransform()).mapRect(item.boundingRect())
                    self.assertFalse(any(box.intersects(rect) for box in boxes))
                    boxes.append(rect)
            self.assertGreater(len(boxes), 2)

            window.result_views.setCurrentIndex(1)
            self.assertFalse(window.view.show_efforts)
            self.assertTrue(window.view.show_deformed)
            table = window.quick_table
            self.assertEqual(table.horizontalHeaderItem(2).text(), 'Uy (mm)')
            data = window.session.result['analyses']['S_GRAV']['nodal_displacements']
            node, delta = max(data.items(), key=lambda pair: hypot(pair[1]['ux_mm'], pair[1]['uy_mm']))
            self.assertEqual(table.item(0, 0).text(), node)
            self.assertEqual(table.item(0, 2).text(),
                             window.units.displacement_text(delta['uy_mm'], signed=True, unit=False))
            revision = window.session.revision
            window.auto_deformation.setChecked(False)
            window.deformation_scale.setValue(50)
            self.assertEqual(window.view.effective_deformation_factor, 50)
            self.assertEqual(window.session.revision, revision)
            member = window.session.model.members[0]
            expected = window.view._pos[member.i] + QPointF(50 * data[member.i]['ux_mm'],
                                                             -50 * data[member.i]['uy_mm'])
            mesh = [item.line() for item in window.view.scene().items()
                    if isinstance(item, QGraphicsLineItem) and item.zValue() == 13]
            self.assertEqual(len(mesh), len(window.session.model.members))
            self.assertIn(expected, [segment.p1() for segment in mesh])
            window.quick_select_result(0, 0)
            self.assertEqual(window.view.selected_ids(), [('node', node)])
        finally:
            window.close()

    def test_display_units_convert_results_and_keep_the_model_revision(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from tempfile import TemporaryDirectory
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from desktop.qt.app import DesktopApp
        from desktop.qt.display_units import DisplayUnits, LoadField

        app = QApplication.instance() or QApplication([])
        self.assertEqual([DisplayUnits(force=unit).force_text(10_000) for unit in ('tf', 'kgf', 'kN')],
                         ['1,00 tf', '1.000 kgf', '10,00 kN'])
        self.assertEqual([DisplayUnits(length=unit).length_text(1_000) for unit in ('m', 'mm', 'cm')],
                         ['1,000 m', '1.000 mm', '100,0 cm'])
        self.assertEqual(DisplayUnits().stress_text(25), '25,00 MPa')
        units = DisplayUnits('kgf', 'cm', 'derived')
        self.assertEqual(units.stress_text(25), '250,00 kgf/cm²')
        self.assertEqual(DisplayUnits(force_digits=3).force_text(10_000), '10,000 kN')
        self.assertEqual(DisplayUnits(force_digits=3).force_text(10_000, load=True), '10,00 kN')
        field = LoadField(-100, 100)
        field.set_stored_value(2.3456)
        self.assertEqual(field.text(), '2,35')
        self.assertEqual(field.submitted_value(), 2.3456)
        with TemporaryDirectory() as directory:
            settings = QSettings(str(Path(directory) / 'display.ini'), QSettings.Format.IniFormat)
            units.save(settings)
            settings.sync()
            self.assertEqual(DisplayUnits.load(settings), units)

        window = DesktopApp()
        window.show()
        try:
            window.calculate()
            revision, result = window.session.revision, window.session.result
            window.set_units(units)
            self.assertEqual(window.session.revision, revision)
            self.assertIs(window.session.result, result)
            self.assertEqual(window.quick_table.horizontalHeaderItem(2).text(), 'N (kgf)')
            self.assertEqual(window.quick_table.horizontalHeaderItem(3).text(), 'Seção')
            member = window.quick_table.item(0, 0).text()
            axial = result['analyses'][window.case_id]['axial_n'][member]
            self.assertEqual(window.quick_table.item(0, 2).text(), units.force_text(axial, signed=True, unit=False))
            window.member_tag_checks['diagonal'].setChecked(True)
            self.assertTrue(window.view._identifiers)
            self.assertTrue(all(not label.node for label in window.view._identifiers))
            self.assertEqual({label.text() for label in window.view._identifiers},
                             {m.id for m in window.session.model.members if m.group == 'diagonal'})
            window._set_overlay('show_ids', True)
            self.assertTrue(any(label.node for label in window.view._identifiers))
            window.member_tag_checks['diagonal'].setChecked(False)
            self.assertTrue(all(label.node for label in window.view._identifiers))
        finally:
            window.close()

    def test_workspace_context_and_3d_cube(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtCore import QPointF, Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from desktop.qt.app import DesktopApp

        app = QApplication.instance() or QApplication([])
        window = DesktopApp()
        window.show()
        try:
            app.processEvents()
            self.assertEqual(window.mode_3d.toolButtonStyle(), Qt.ToolButtonStyle.ToolButtonIconOnly)
            node = window.session.model.nodes[0]
            window._update_selection([('node', node.id)])
            self.assertEqual(window.property_summary.topLevelItem(0).child(0).text(1), node.id)
            self.assertIn('Cargas nodais', [window.context_tabs.tabText(i)
                                           for i in range(window.context_tabs.count())])
            window.inspector_toggle.click()
            member = window.session.model.members[0]
            window._update_selection([('member', member.id)])
            self.assertTrue(window.task_host.isHidden())
            self.assertNotIn('Cargas nodais', [window.context_tabs.tabText(i)
                                              for i in range(window.context_tabs.count())])
            window.open_general_actions()
            self.assertTrue(window._load_dialogs[window.actions_tab].isVisible())
            self.assertTrue(window.task_host.isHidden())
            window.open_static_cases()
            self.assertTrue(window._load_dialogs[window.static_tab].isVisible())
            self.assertFalse(window._load_dialogs[window.actions_tab].isVisible())
            window.open_combinations()
            combo = window._load_dialogs[window.combo_tab]
            self.assertTrue(combo.isVisible())
            self.assertFalse(combo.isModal())
            combo.close()
            window.mode_3d.click()
            cube = window._view3d.cube
            polygon = cube.faces['Superior XZ'][0]
            point = sum(polygon, QPointF()) / 4
            QTest.mouseClick(cube, Qt.MouseButton.LeftButton, pos=point.toPoint())
            self.assertEqual(window._view3d._angles, (0, 90))
            self.assertEqual(list(cube.faces), ['Superior XZ'])
        finally:
            window.close()

    def test_force_vectors_enter_or_leave_nodes_and_labels_fit_without_overlap(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PySide6.QtCore import QPointF
        from PySide6.QtWidgets import QApplication, QGraphicsSimpleTextItem
        from desktop.qt.app import DesktopApp
        from desktop.qt.viewport import ForceVectorItem, NodeItem

        app = QApplication.instance() or QApplication([])
        for fx, fy in [(0, -10), (0, 10), (10, 0), (-10, 0), (-6, 8), (6, -8)]:
            with self.subTest(fx=fx, fy=fy):
                vector = ForceVectorItem('N1', QPointF(), fx, fy, 10)
                tail, head = (vector.path().elementAt(i) for i in (0, 1))
                outward = (fy or fx) > 0
                anchor = tail if outward else head
                sign = 1 if outward else -1
                self.assertAlmostEqual(anchor.x, sign * .7 * fx)
                self.assertAlmostEqual(anchor.y, -sign * .7 * fy)
                self.assertAlmostEqual(head.x - tail.x, 5 * fx)
                self.assertAlmostEqual(head.y - tail.y, -5 * fy)

        window = DesktopApp()
        window.show()
        try:
            window.open_general_actions()
            window._load_dialogs[window.actions_tab].close()
            window.cases.setCurrentText('W_UP')
            window._set_overlay('show_ids', True)
            window.force_values.click()
            app.processEvents()
            window.fit()
            view = window.view
            view.scale(.45, .45)
            view._place_labels()
            transform = view.viewportTransform()
            annotations = {
                item.text() for item in view.scene().items()
                if isinstance(item, QGraphicsSimpleTextItem) and item.parentItem() is None
            }
            self.assertEqual({item.toolTip() for item in view._support_items},
                             {'Apoio · UX e UY', 'Apoio · UY'})
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
            self.assertIn('ΣFy -4,00', window.force_summary.text())

            window.load_table.selectRow(0)
            window.fy.setValue(-1)
            QTest.mouseClick(window.commit_load, Qt.MouseButton.LeftButton)
            self.assertEqual(window.load_table.rowCount(), 2)
            self.assertIn('ΣFy -3,00', window.force_summary.text())
            window.cases.setCurrentText('COMB_UI')
            self.assertIn('ΣFy -6,00', window.force_summary.text())
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
            window.quick_select_result(0, 0)
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
            self.assertGreaterEqual(window.info_tabs.count(),8)
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
