import os
import subprocess
import sys
import shutil

# --- CONFIGURAÇÕES ---
APP_NAME = "GodOfWar_AssetTool"
MAIN_SCRIPT = "app.py"
UPX_DIR = "upx"

# Pacotes essenciais
REQUIRED_PACKAGES = [
    "customtkinter",
    "tkinterdnd2",
    "pyinstaller",
    "packaging"
]

# Conteúdo do .spec com EXCLUSÕES CORRIGIDAS e VGMSTREAM
SPEC_CONTENT = r"""
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
import os

block_cipher = None

# --- COLETA DE DADOS ---
datas = []
binaries = []
hiddenimports = []

# Coleta CustomTkinter
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# Coleta TkinterDnD (Com filtro de arquitetura)
tmp_ret = collect_all('tkinterdnd2')
raw_dnd_datas = tmp_ret[0]
raw_dnd_binaries = tmp_ret[1]
hiddenimports += tmp_ret[2]

# Filtra lixo do TkinterDnD (ARM, Mac, Linux, x86)
filtered_binaries = []
for entry in raw_dnd_binaries:
    source = entry[0]
    lower_src = source.lower()
    if "arm64" in lower_src or "aarch64" in lower_src: continue
    if "win-x86" in lower_src or "win32" in lower_src: continue
    if "linux" in lower_src or "mac" in lower_src or "osx" in lower_src: continue
    filtered_binaries.append(entry)
binaries += filtered_binaries

filtered_datas = []
for entry in raw_dnd_datas:
    source = entry[0]
    lower_src = source.lower()
    if "arm64" in lower_src or "aarch64" in lower_src: continue
    if "win-x86" in lower_src or "win32" in lower_src: continue
    filtered_datas.append(entry)
datas += filtered_datas

# --- ASSETS MANUAIS ---
import glob
project_assets = []

# 1. Fontes e DLL Oodle
if os.path.exists("Berserker.ttf"): project_assets.append(('Berserker.ttf', '.'))
if os.path.exists("oo2core_7_win64.dll"): project_assets.append(('oo2core_7_win64.dll', '.'))

# 2. Todos os icones
for ico in glob.glob("*.ico"):
    project_assets.append((ico, '.'))

# 3. VGMStream e suas DLLs (Adicionado conforme solicitado)
vgm_files = [
    "vgmstream-cli.exe",
    "avcodec-vgmstream-59.dll",
    "avformat-vgmstream-59.dll",
    "avutil-vgmstream-57.dll",
    "libatrac9.dll",
    "libcelt-0061.dll",
    "libcelt-0110.dll",
    "libg719_decode.dll",
    "libmpg123-0.dll",
    "libspeex-1.dll",
    "libvorbis.dll",
    "swresample-vgmstream-4.dll"
]

for f in vgm_files:
    if os.path.exists(f):
        print(f"Incluindo no build: {f}")
        project_assets.append((f, '.'))

datas += project_assets

# --- LISTA DE EXCLUSÃO ---
excludes_list = [
    'matplotlib', 'numpy', 'pandas', 'scipy', 'notebook', 'ipython', 'zmq', 
    'test', 'unittest', 'email', 'http', 'xmlrpc', 'pydoc', 'lib2to3', 
    'pkg_resources', 'distutils', 'setuptools', 'difflib', 'doctest', 
    'pdb', 'tarfile', 'bz2', 'lzma', '_decimal', 
    'multiprocessing', 'concurrent', 'asyncio', 'curses'
]

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes_list,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
    optimize=2,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='GodOfWar_AssetTool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    # Protege arquivos sensíveis do UPX
    upx_exclude=['vcruntime140.dll', 'ucrtbase.dll', 'lxml', 'libtkdnd*'],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico', 
)
"""

def create_venv():
    venv_dir = "temp_build_venv"
    if os.path.exists(venv_dir):
        try: shutil.rmtree(venv_dir)
        except: pass
    subprocess.check_call([sys.executable, "-m", "venv", venv_dir])
    if os.name == 'nt': return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")

def build():
    python_bin = create_venv()
    
    # Instala SEM cache
    subprocess.check_call([python_bin, "-m", "pip", "install", "--no-cache-dir", "--upgrade", "pip"])
    subprocess.check_call([python_bin, "-m", "pip", "install", "--no-cache-dir"] + REQUIRED_PACKAGES)
    
    with open(f"{APP_NAME}.spec", "w", encoding="utf-8") as f:
        f.write(SPEC_CONTENT)
        
    cmd = [python_bin, "-m", "PyInstaller", f"{APP_NAME}.spec", "--clean", "--noconfirm"]
    
    if os.path.exists(UPX_DIR):
        cmd.append(f"--upx-dir={UPX_DIR}")

    subprocess.check_call(cmd)

if __name__ == "__main__":
    try:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        build()
        print("\nSUCESSO! Verifique a pasta 'dist'.")
    except Exception as e:
        print(f"ERRO: {e}")