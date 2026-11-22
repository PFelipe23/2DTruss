"""Regressão CPU das seções extrudadas; independente de PySide6."""
from __future__ import annotations
from pathlib import Path
from math import isclose
import tempfile
import unittest
from desktop.section_mesh import (
    load_shape_catalog, section_polygon, polygon_area, polygon_centroid,
    centered_polygon, make_section_layout, extrude_member, make_model_meshes,
    triangulate_contour, export_obj, display_scaled_vertices
)
from desktop.bridge import Session, CATALOG


class SectionMeshTests(unittest.TestCase):
    def test_gerdau_h_uses_independent_flange_and_web_dimensions(self):
        shape = self.catalog['W 150 x 22,5 (H)']
        self.assertEqual((shape.height, shape.flange, shape.thickness, shape.flange_thickness),
                         (152, 152, 5.8, 6.6))
        ideal_area = 2 * 152 * 6.6 + (152 - 2 * 6.6) * 5.8
        self.assertAlmostEqual(polygon_area(section_polygon(shape)), ideal_area)

    @classmethod
    def setUpClass(cls): cls.catalog=load_shape_catalog(CATALOG)

    def test_all_catalog_shapes_have_simple_ccw_outline(self):
        families = {shape.family.split()[0] for shape in self.catalog.values()}
        self.assertEqual(families, {'U', 'UE', 'L', 'W', 'H', 'HP'})
        for shape in self.catalog.values():
            with self.subTest(profile=shape.name):
                pts=section_polygon(shape)
                self.assertGreater(polygon_area(pts),0)
                self.assertEqual(len(triangulate_contour(pts)),len(pts)-2)

    def test_u_channel_thin_wall_rectangle(self):
        s=self.catalog['U 150x50x3,00']
        pts=section_polygon(s)
        self.assertAlmostEqual(max(u for u,v in pts),50)
        self.assertAlmostEqual(max(v for u,v in pts),150)
        self.assertAlmostEqual(polygon_area(pts),732)
        cx,cy=polygon_centroid(centered_polygon(s))
        self.assertAlmostEqual(cx,0,places=9)
        self.assertAlmostEqual(cy,0,places=9)

    def test_ue_lipped_has_real_lips_and_higher_area(self):
        s=self.catalog['Ue 150x60x20x3,00']
        self.assertEqual(s.lip,20)
        self.assertEqual(len(section_polygon(s)),12)
        self.assertAlmostEqual(polygon_area(section_polygon(s)),912)
        self.assertGreater(polygon_area(section_polygon(s)),732)

    def test_angle_is_L_not_rectangular_bar(self):
        s=self.catalog['L laminada 50x50x3']
        poly=section_polygon(s)
        self.assertEqual(len(poly),6)
        self.assertAlmostEqual(polygon_area(poly),291)
        self.assertLess(polygon_area(poly),2500)

    def test_pair_orientation_changes_shape(self):
        s=self.catalog['Ue 150x60x20x3,00']
        backs,_=make_section_layout(s,2,{'assembly_type':'back_to_back','centroid_dx_mm':150})
        faces,_=make_section_layout(s,2,{'assembly_type':'face_to_face','centroid_dx_mm':150})
        self.assertNotEqual(backs,faces)
        self.assertAlmostEqual(sum(polygon_area(p) for p in backs),1824)
        self.assertAlmostEqual(sum(polygon_area(p) for p in faces),1824)

    def test_missing_pair_spacing_declared_as_graphical(self):
        s=self.catalog['U 150x50x3,00']
        polygons,notes=make_section_layout(s,2)
        self.assertEqual(len(polygons),2)
        self.assertTrue(any('GRÁFICA' in msg for msg in notes))

    def test_member_extrusion_uses_local_section_not_prism(self):
        s=self.catalog['U 150x50x3,00']
        polygons,_=make_section_layout(s,1)
        mesh=extrude_member((0,0),(1000,0),polygons,'B1','superior',s.name)[0]
        self.assertEqual(len(mesh.vertices),2*len(section_polygon(s)))
        self.assertEqual(len(mesh.faces),2+len(section_polygon(s)))
        self.assertTrue(all(isclose(x,0) for x,y,z in mesh.vertices[:len(polygons[0])]))
        self.assertTrue(all(isclose(x,1000) for x,y,z in mesh.vertices[len(polygons[0]):]))

    def test_diagonal_extrusion_respects_member_axis(self):
        s=self.catalog['L dobrada 40x40x2']
        mesh=extrude_member((100,200),(900,800),make_section_layout(s,1)[0],
                            'D1','diagonal',s.name)[0]
        n=len(mesh.vertices)//2
        for a,b in zip(mesh.vertices[:n],mesh.vertices[n:]):
            self.assertAlmostEqual(b[0]-a[0],800)
            self.assertAlmostEqual(b[1]-a[1],600)
            self.assertAlmostEqual(b[2]-a[2],0)

    def test_display_exaggeration_does_not_change_export_geometry(self):
        s=self.catalog['Ue 150x60x20x3,00']
        mesh=extrude_member((0,0),(1000,0),make_section_layout(s,1)[0],
                            'B1','superior',s.name)[0]
        self.assertEqual(display_scaled_vertices(mesh,(0,0),(1000,0),1),mesh.vertices)
        big=display_scaled_vertices(mesh,(0,0),(1000,0),4)
        self.assertAlmostEqual(big[0][2],mesh.vertices[0][2]*4)
        self.assertAlmostEqual(big[0][0],mesh.vertices[0][0]*4)
        self.assertEqual(mesh.vertices,display_scaled_vertices(mesh,(0,0),(1000,0),1))
        with self.assertRaises(ValueError):display_scaled_vertices(mesh,(0,0),(1000,0),20)

    def test_invalid_zero_length_rejected(self):
        s=self.catalog['U 150x50x3,00']
        with self.assertRaisesRegex(ValueError,'inválida'):
            extrude_member((0,0),(0,0),make_section_layout(s,1)[0], 'B1','superior',s.name)

    def test_real_example_mesh_and_session_not_modified(self):
        session=Session()
        before=session.project.copy()
        meshes,warnings,metadata=make_model_meshes(session.model,session.project,self.catalog)
        self.assertEqual(len(metadata),len(session.model.members))
        self.assertGreater(len(meshes),len(session.model.members))
        self.assertTrue(warnings)
        self.assertEqual(session.project,before)
        self.assertIsNone(session.result)

    def test_obj_is_watertight_and_has_correct_volume(self):
        try:import trimesh
        except ImportError:self.skipTest('trimesh não instalado na bancada')
        s=self.catalog['Ue 150x60x20x3,00']
        mesh=extrude_member((0,0),(1000,0),make_section_layout(s,1)[0],
                             'B1','superior',s.name)[0]
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'mesh.obj';export_obj([mesh],path)
            geom=trimesh.load_mesh(path,force='mesh')
            self.assertTrue(geom.is_watertight)
            self.assertAlmostEqual(geom.volume,912000,places=2)
            self.assertIn('UNIDADE: mm',path.read_text())

    def test_export_does_not_change_analysis(self):
        session=Session()
        res=session.calculate();snapshot=res['analyses']
        meshes,_,_=make_model_meshes(session.model,session.project,self.catalog)
        with tempfile.TemporaryDirectory() as d:export_obj(meshes,Path(d)/'trelica.obj')
        self.assertEqual(session.result['analyses'],snapshot)


if __name__=='__main__':unittest.main()
