from PyInstaller.utils.hooks import collect_data_files

# Keep runtime resources and leave generated C/Cython sources out of the bundle.
datas = collect_data_files(
    "ezdxf",
    excludes=["**/*.c", "**/*.h", "**/*.pyx", "**/*.pxd"],
)
