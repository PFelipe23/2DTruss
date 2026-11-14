"""Testes da interface Tk sob Xvfb (Linux) ou sessão gráfica Windows."""
from __future__ import annotations
from copy import deepcopy
import os
import unittest

def _can_open_gui():
    try:
        import tkinter as tk
        root=tk.Tk();root.withdraw();root.destroy()
        return True
    except (ImportError,tk.TclError):
        return False

@unittest.skipUnless(_can_open_gui(),'Sessão gráfica não disponível')
class NativeUISmokeTests(unittest.TestCase):
    def setUp(self):
        from desktop.app import App
        self.app=App();self.app.update()
    def tearDown(self):self.app.destroy()

    def test_node_selection_edit_stale_and_reanalysis(self):
        app=self.app;app.calculate()
        old=app.session.model.node_map()['T08'].y
        app._on_select('node','T08')
        app.node_y.set(str(old+120))
        app.apply_node()
        self.assertEqual(app.session.model.node_map()['T08'].y,old+120)
        self.assertIsNone(app.session.result)
        app.calculate()
        self.assertIn('G1',app.session.result['analyses'])

    def test_wind_case_edit_and_diagram_in_sync(self):
        app=self.app;app._show_inspector('Cargas')
        app.load_cases_list.selection_clear(0,'end')
        idx=app._load_case_ids.index('W_UP')
        app.load_cases_list.selection_set(idx)
        app._show_case_loads();app.update()
        self.assertEqual(app.case_var.get(),'W_UP')
        self.assertTrue(app.surface_editor.winfo_ismapped())
        app.surface_vars['value'].set('32.50')
        app.apply_load_case()
        self.assertEqual(next(c for c in app.session.project['load_cases'] if c['id']=='W_UP')['value'],32.5)
        app.calculate()
        self.assertEqual(app.case_var.get(),'W_UP')
        self.assertEqual(app.viewport.case_id.get(),'W_UP')

if __name__=='__main__':unittest.main()
