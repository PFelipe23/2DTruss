"""Gera amostras das MALHAS REAIS; não é captura da janela Qt.

Ferramenta de verificação opcional: requer matplotlib. O desktop não depende dela.
"""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from desktop.section_mesh import (load_shape_catalog,make_section_layout,
    extrude_member,triangulate_contour,polygon_area,export_obj,make_model_meshes)
from desktop.bridge import Session, CATALOG

COLORS=['#087AAC','#D08A4C','#5F8B7D','#8C61A2']
profiles=[
 ('U 150x50x3,00','U DOBRADO',1,{}),
 ('Ue 150x60x20x3,00','UE ENRIJECIDO',1,{}),
 ('L laminada 60x60x4','L LAMINADA',1,{}),
 ('Ue 150x60x20x3,00','2 UE FACE A FACE',2,{'centroid_dx_mm':135,'assembly_type':'face_to_face'}),
]
shapes=load_shape_catalog(CATALOG)
fig=plt.figure(figsize=(15,5),facecolor='#F4F8FB')
fig.suptitle('POE TRELIÇA  /  GEOMETRIA DOS PERFIS EM 3D',fontsize=18,fontweight='bold',color='#163B57',y=.975)
all_meshes=[]
for idx,(key,title,count,config) in enumerate(profiles):
    ax=fig.add_subplot(1,4,idx+1,projection='3d')
    ax.set_facecolor('#F4F8FB')
    s=shapes[key]
    outlines,notes=make_section_layout(s,count,config)
    meshes=extrude_member((0,0),(290,0),outlines,f'DEMO{idx+1}','superior',key)
    all_meshes.extend(meshes)
    polys=[];colors=[]
    for mesh in meshes:
        n=len(mesh.vertices)//2
        outline=[(v[2],v[1]) for v in mesh.vertices[:n]]
        # Mesma orientação dos contornos originais centrados.
        for a,b,c in triangulate_contour(outline):
            polys.append([mesh.vertices[i] for i in (a,b,c)])
            colors.append('#4E7996')
            polys.append([mesh.vertices[n+i] for i in (a,b,c)])
            colors.append('#A5C6D9')
        for face in mesh.faces[2:]:
            polys.append([mesh.vertices[i] for i in face])
            colors.append(COLORS[idx])
    coll=Poly3DCollection(polys,facecolors=colors,edgecolor='#294E65',linewidths=.28,alpha=1)
    ax.add_collection3d(coll)
    ax.set_xlim(0,310);ax.set_ylim(-110,110);ax.set_zlim(-120,120)
    ax.set_box_aspect((310,220,240),zoom=.86)
    ax.view_init(elev=27,azim=-52)
    ax.set_axis_off()
    ax.text2D(.5,.91,title,transform=ax.transAxes,ha='center',fontsize=11,fontweight='bold',color='#193D55')
    dims=f'{s.height:g} × {s.flange:g} × {s.thickness:g} mm'
    if s.lip:dims=f'{s.height:g} × {s.flange:g} × {s.lip:g} × {s.thickness:g} mm'
    ax.text2D(.5,.08,dims,transform=ax.transAxes,ha='center',fontsize=9,color='#44667D')
    if notes:ax.text2D(.5,.015,'ARRANJO GEOMÉTRICO DECLARADO',transform=ax.transAxes,ha='center',fontsize=7,color='#B47538')
fig.text(.5,.03,'Extrusão reta de 290 mm por amostra · Sem raios de dobra, variações de espessura de mesa ou ligações · Uso visual, não ELU',
         ha='center',fontsize=9,color='#6D7F8E')
fig.subplots_adjust(left=.012,right=.988,top=.90,bottom=.06,wspace=.02)
output=ROOT/'captures'/'POE_Trelica_v09_Perfis_3D_Contornos.png'
output.parent.mkdir(exist_ok=True,parents=True)
fig.savefig(output,dpi=185,facecolor=fig.get_facecolor())
print(output)
meshdir=ROOT/'verification'/'meshes';meshdir.mkdir(exist_ok=True)
export_obj(all_meshes,meshdir/'amostras_U_UE_L_e_2UE.obj')
session=Session()
meshes,warnings,_=make_model_meshes(session.model,session.project,shapes,session.catalog)
export_obj(meshes,meshdir/'trelica_16m_perfils_idealizados.obj')
print('OBJ',len(meshes),'members',len(session.model.members),'warn',len(warnings))
