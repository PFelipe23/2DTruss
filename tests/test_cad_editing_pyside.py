"""Testes de topologia e CAD, sem depender da instalação do PySide6."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy
import ezdxf
from desktop.bridge import Session
from desktop.editing import (materialize,add_draft,add_member,split_members,
                              move_nodes,delete_elements,update_member_group)
from desktop.cad_io import load_cad,make_import_project


class TestAdvancedEditor(unittest.TestCase):
    def setUp(self):self.session=Session()

    def test_materialize_matches_original_geometry(self):
        m=self.session.model;p=materialize(self.session.project,m)
        self.assertEqual(len(p['model_override']['nodes']),len(m.nodes))
        s=Session(p,self.session.catalog)
        self.assertEqual(m.mass_kg(),s.model.mass_kg())
        self.assertEqual([v.id for v in m.members],[v.id for v in s.model.members])

    def test_add_draft_and_attached_member(self):
        m=self.session.model
        p,n=add_draft(self.session.project,m,8000,4000)
        Session(p,self.session.catalog) # draft does not change original analysis geometry
        self.assertEqual(len(p['cad_drafts']),1)
        p,mid=add_member(p,m,m.nodes[0].id,n,group='diagonal')
        s=Session(p,self.session.catalog)
        self.assertIn(n,s.model.node_map());self.assertTrue(any(x.id==mid for x in s.model.members))
        self.assertFalse(p.get('cad_drafts'))

    def test_disallow_isolated_two_drafts(self):
        m=self.session.model
        p,a=add_draft(self.session.project,m,-500,0)
        p,b=add_draft(p,m,-1000,0)
        with self.assertRaises(ValueError):add_member(p,m,a,b)

    def test_split_preserves_total_lengths_and_areas(self):
        m=self.session.model;mid=m.members[0].id
        old=m.member_length(m.members[0]);oldmass=m.mass_kg()
        p,ids=split_members(self.session.project,m,[mid],.35)
        s=Session(p,self.session.catalog)
        self.assertNotIn(mid,[x.id for x in s.model.members])
        self.assertAlmostEqual(sum(s.model.member_length(x) for x in s.model.members if ids[0] in (x.i,x.j)),old,places=5)
        self.assertAlmostEqual(s.model.mass_kg(),oldmass,places=6)

    def test_move_atomic_and_reject_collision(self):
        m=self.session.model
        a,b=m.nodes[:2]
        p=move_nodes(self.session.project,m,{a.id:(a.x+20,a.y+50)})
        Session(p,self.session.catalog)
        p2=move_nodes(self.session.project,m,{a.id:(b.x,b.y)})
        with self.assertRaises(ValueError):Session(p2,self.session.catalog)

    def test_delete_bar_and_stability_assumptions(self):
        m=self.session.model
        # On removing a diagonal, the remaining truss can still be valid.
        diag=next(x for x in m.members if x.group=='diagonal')
        p=deepcopy(self.session.project)
        p.setdefault('stability',{}).setdefault('members',{})[diag.id]={'k_in_plane':1.1}
        updated=delete_elements(p,m,member_ids=[diag.id])
        self.assertNotIn(diag.id,updated.get('stability',{}).get('members',{}))
        self.assertNotIn(diag.id,[x.id for x in Session(updated,self.session.catalog).model.members])

    def test_group_change_updates_material(self):
        m=self.session.model;mid=m.members[0].id
        p=update_member_group(self.session.project,m,[mid],'diagonal')
        s=Session(p,self.session.catalog)
        self.assertEqual(next(x for x in s.model.members if x.id==mid).group,'diagonal')


class TestCADImport(unittest.TestCase):
    def create_dxf(self,path,units=4):
        doc=ezdxf.new('R2013');doc.header['$INSUNITS']=units
        space=doc.modelspace()
        # Simple triangular truss, 3 bars. Add a duplicate and an arc to verify diagnostics.
        space.add_line((0,0),(4000,0),dxfattribs={'layer':'BANZO_INF'})
        space.add_line((0,0),(2000,1500),dxfattribs={'layer':'DIAGONAL'})
        space.add_line((2000,1500),(4000,0),dxfattribs={'layer':'DIAGONAL'})
        space.add_line((4000,0),(0,0),dxfattribs={'layer':'BANZO_INF'})
        space.add_arc((0,0),200,0,90,dxfattribs={'layer':'ANNOTATIONS'})
        doc.saveas(path)

    def test_dxf_units_and_layer_mapping(self):
        with TemporaryDirectory() as root:
            path=Path(root)/'tri.dxf';self.create_dxf(path)
            d=load_cad(path)
            self.assertEqual(len(d.nodes),3)
            self.assertEqual(len(d.members),3)
            self.assertIn('ARC',d.ignored)
            self.assertEqual(d.ignored['DUPLICADA'],1)
            self.assertAlmostEqual(max(n['x_mm'] for n in d.nodes),4000)
            self.assertEqual(d.layers['BANZO_INF'],1)
            s=Session()
            p=make_import_project(s.project,d,s.catalog)
            s2=Session(p,s.catalog)
            self.assertEqual(len(s2.model.members),3)
            self.assertEqual(s2.model.supports,{})
            self.assertEqual(p['combinations'],[])
            self.assertTrue(all(x['kind']=='self_weight' for x in p['load_cases']))
            with self.assertRaises(Exception):s2.calculate() # sem apoios

    def test_dxf_unitless_manual_cm(self):
        with TemporaryDirectory() as root:
            path=Path(root)/'tri.dxf';self.create_dxf(path,units=0)
            d=load_cad(path,unitless_unit='cm')
            self.assertAlmostEqual(max(n['x_mm'] for n in d.nodes),40000)
            self.assertTrue(any('sem unidade' in s for s in d.warnings))

    def test_dwg_without_converter_fails_closed(self):
        with TemporaryDirectory() as root:
            path=Path(root)/'arquivo.dwg';path.write_bytes(b'AC1027 fake DWG')
            from ezdxf.addons import odafc
            if not odafc.is_installed():
                with self.assertRaisesRegex(RuntimeError,'ODA File Converter'):load_cad(path)

    def test_reject_dxf_invalid_type_and_tolerance(self):
        with TemporaryDirectory() as root:
            path=Path(root)/'a.dxf';self.create_dxf(path)
            with self.assertRaises(ValueError):load_cad(path,merge_tolerance_mm=-1)


if __name__=='__main__':unittest.main()

class TestImportedProjectRoundTrip(unittest.TestCase):
    def test_cad_import_supports_and_loads_roundtrip(self):
        from desktop.bridge import write_project,load_project
        import math
        with TemporaryDirectory() as root:
            path=Path(root)/'tri.dxf'
            doc=ezdxf.new();doc.header['$INSUNITS']=4
            dxf=doc.modelspace()
            for i,j in [((0,0),(4000,0)),((0,0),(2000,1500)),((2000,1500),(4000,0))]:
                dxf.add_line(i,j)
            doc.saveas(path)
            base=Session();preview=load_cad(path)
            project=make_import_project(base.project,preview,base.catalog)
            session=Session(project,base.catalog)
            nm={ (n.x,n.y):n.id for n in session.model.nodes }
            A=nm[(0,0)];B=nm[(4000,0)];C=nm[(2000,1500)]
            session.set_support(A,True,True)
            session.set_support(B,False,True)
            session.add_nodal_case('P')
            session.set_nodal_load('P',C,0,-1000,'kgf')
            result=session.calculate()['analyses']['P']
            self.assertAlmostEqual(result['reactions'][A]['fy_n'],5000,places=3)
            self.assertAlmostEqual(result['reactions'][B]['fy_n'],5000,places=3)
            self.assertAlmostEqual(sum(result['axial_n'].values())!=0,True)
            new_path=Path(root)/'project.json'
            write_project(new_path,session.project)
            restored=Session(load_project(new_path),base.catalog)
            r2=restored.calculate()['analyses']['P']
            for member_id,n in result['axial_n'].items():
                self.assertAlmostEqual(r2['axial_n'][member_id],n,places=5)
