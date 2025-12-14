# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for EVE Means of Profit.

This spec file creates a single executable for the PyQt6-based EVE Online 
profit analysis application.

Build command:
    pyinstaller eve-means-of-profit.spec --clean

Output:
    dist/EVE Means of Profit.exe (single executable file)
    
Runtime:
    Place the 'data' folder beside the .exe file. The application will
    automatically look for it at runtime via user_data_dir logic.
"""

from pathlib import Path
import sys

block_cipher = None

# Project root directory
project_root = Path.cwd()

# === Data Files Configuration ===
# No data files bundled - data folder should be placed beside the executable

datas = []

# Bundle only pyproject.toml for metadata extraction (used in config.py)
pyproject_file = project_root / 'pyproject.toml'
if pyproject_file.exists():
    datas.append((str(pyproject_file), '.'))

# Note: The 'data' folder should be placed beside the executable at runtime.
# The application will automatically look for and create this folder via
# user_data_dir logic in config.py when frozen (next to the .exe file).


# === Hidden Imports Configuration ===
# Specify imports that PyInstaller's static analysis might miss

hiddenimports = [
    # Core async dependencies
    'qasync',
    'asyncio',
    
    # HTTP and API clients
    'httpx',
    'httpx._transports',
    'httpx._transports.default',
    'aiopenapi3',
    
    # Data handling
    'diskcache',
    'pydantic',
    'pydantic_settings',
    
    # Optional clipboard support
    'pyperclip',
    
    # PyQt6 core modules
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtWidgets',
    'PyQt6.QtNetwork',
    'PyQt6.QtPrintSupport',
    
    # PyQtGraph for charting
    'pyqtgraph',
    'pyqtgraph.graphicsItems',
    'pyqtgraph.graphicsItems.ViewBox',
    
    # Dynamically imported service modules
    'services',
    'services.asset_service',
    'services.character_service',
    'services.contract_service',
    'services.industry_service',
    'services.location_service',
    'services.market_service',
    'services.networth_service',
    'services.wallet_service',
    
    # Data provider modules
    'data',
    'data.sde_jsonl',
    'data.fuzzwork_csv',
    
    # UI modules
    'ui',
    'ui.main_window',
    'ui.asset_panel',
    'ui.character_panel',
    'ui.contract_panel',
    'ui.industry_panel',
    'ui.market_panel',
    'ui.networth_panel',
    'ui.wallet_panel',
    
    # Utility modules
    'utils',
    'utils.config',
    'utils.di_container',
    'utils.logging_setup',
    'utils.concurrency_manager',
    'utils.esi_client_singleton',
    'utils.exceptions',
    'utils.jsonl_parser',
    
    # ESI client modules
    'esi',
    'esi.client',
    'esi.auth',
    'esi.cache',
    'esi.callback_server',
    'esi.rate_limit',
    
    # External data clients
    'external',
    'external.sde_client',
    'external.fuzzwork_client',
]


# === Analysis Configuration ===
a = Analysis(
    ['src/__main__.py'],  # Entry point
    pathex=[str(project_root / 'src')],  # Additional import paths
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude test and development modules
        'pytest',
        'pytest_asyncio',
        'pytest_cov',
        'ruff',
        'ty',
        'pip_audit',
        'pre_commit',
        
        # Exclude unused GUI backends
        'tkinter',
        'matplotlib',
        
        # Exclude unused standard library modules
        'pdb',
        'unittest',
        'doctest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)


# === Executable Configuration ===
# Single executable file (one-file mode)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='EVE Means of Profit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI application (no console window)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here if you have one (e.g., 'resources/icon.ico')
)

# Note: One-file mode selected
# The executable will be: dist/EVE Means of Profit.exe
# Place the 'data' folder beside this .exe file at runtime
