# God of War Asset Tool

A standalone Windows GUI for browsing, extracting, editing, and repacking assets from **God of War (2018)** and **God of War Ragnarök**.

> [!WARNING]
> Modding game archives can prevent the game from starting when an invalid file is installed. Keep **Backup Original** enabled and test one modified archive at a time.

## Features

### WAD archives

- Browse archive contents without unpacking the entire WAD.
- Search and sort entries by name, type, and size.
- Extract individual files or unpack complete archives.
- Replace files directly from the archive view.
- Repack the active archive view with your changes or repack from a replacement folder.
- Follow texture references from WADs to their source TEXPACK files.
- Supports both:
  - God of War (2018) PS4-style flat WADs.
  - God of War Ragnarök PS5-style LZ4 WADs.

### Variable-size Ragnarök WAD repacking

Ragnarök WADs are rebuilt using the layout rules extracted directly from the game's code through Ghidra:

- All nine logical block cursors are recalculated.
- Every descriptor keeps its original alignment requirements.
- Main and auxiliary offsets are updated.
- Block sizes and the physical payload stream are rebuilt.
- Existing `autopad` entries remain unchanged.
- The final archive is compressed with the required LZ4 frame settings.

Real physical WAD growth has been tested successfully in-game. The editor can therefore save a larger or smaller `MSGS_TXT` without balancing it back to its original size.

### Text editing

- Built-in `MSGS_TXT` editor, allowing you to edit language files.
- Search and navigation across large language files.
- Separate header calculations for God of War (2018) and Ragnarök.
- Preserves the final null terminator when present.

### TEXPACK textures

- Browse PS4 and PS5 TEXPACK contents.
- Export textures as native GNF, DDS, or PNG.
- Repack from the active archive or a replacement folder.
- Accept replacement GNF, DDS, and lossless PNG files.
- Automatically preserve the original texture's:
  - Dimensions.
  - BC/DXGI format.
  - Mip count.
  - PS4 or PS5 swizzle layout.
  - Metadata and alignment.
  - Reserved payload size.

PNG import is unavailable for HDR or floating-point textures because ordinary PNG files cannot preserve their numeric range. Use DDS for those textures.

> [!NOTE]
> BC texture compression is lossy. Repeated PNG/DDS import and BC recompression can gradually reduce image quality, especially for normal maps, masks, and alpha channels. Keep a backup of the original extracted texture to avoid that.

### Audio

- Browse and extract supported SBP/BNK audio entries.
- Convert supported game audio through vgmstream.
- Built-in playback for converted WAV audio.

## Requirements

- Windows 10 or Windows 11, 64-bit.
- Python 3.10 or newer when running from source.
- A legally owned PC installation of the supported game.

Install the Python packages:

```powershell
python -m pip install customtkinter tkinterdnd2 packaging pyinstaller
```

Run from source:

```powershell
python app.py
```

The application asks for the game installation directory before executing commands that need external game files. The configured path can be changed later from the GUI.

## Native Dependencies

If absent, place the required native files beside `app.py` when running from source or before creating a bundled EXE.

| File | Purpose |
| --- | --- |
| `liblz4.dll` | Ragnarök WAD decompression and recompression |
| `oo2core_7_win64.dll` | God of War (2018) Oodle-compressed assets |
| `texconv.exe` | DDS/PNG conversion and texture import |
| `texture_codec.dll` | Accelerated PS5 swizzle and unswizzle |
| `vgmstream-cli.exe` and codec DLLs | Game audio conversion |

`texture_codec.dll` is built from the included `texture_codec.cpp`. The tool has a slower pure-Python texture fallback when this DLL is unavailable.

`oo2core_7_win64.dll` is proprietary and must be obtained from a legally owned game installation.

## Building a Single EXE

### Included build script

```powershell
python built_clean.py
```

The build script installs the required Python packages, generates the PyInstaller configuration, bundles available native dependencies, and applies the existing size exclusions.
For more compression, download [UPX](https://upx.github.io/), place the upx.exe file in the project folder in a folder called "upx", and change the variable upx from False to True in built_clean.py.

### Existing PyInstaller specification

```powershell
pyinstaller --clean GodOfWarRagnarok_PS5_AssetTool.spec
```

The `.spec` file expects native dependencies and UI assets to be present in the project directory. It does **not** compile `texture_codec.cpp`; `texture_codec.dll` must already exist before the build starts.

The same files can be added manually when building through auto-py-to-exe.

## Repository Layout

```text
app.py                                Main CustomTkinter GUI
gow_unified_backend.py                PS4/PS5 archive and texture backend
texture_codec.cpp                     Native PS5 texture acceleration source
texture_codec.dll                     Prebuilt Windows texture codec
liblz4.dll                            Ragnarök WAD decompression and recompression
texconv.exe                           DDS/PNG conversion and texture import
texture_codec.dll                     Accelerated PS5 swizzle and unswizzle
vgmstream-cli.exe and codec DLLs      Game audio conversion
built_clean.py                        Automated PyInstaller build helper
GodOfWarRagnarok_PS5_AssetTool.spec   PyInstaller build configuration
Berserker.ttf                         Application font
icon*.ico                             Window and dialog icons
```

## Known Limitations

- TEXPACK replacement cannot add a new texture entry; it replaces an existing reserved entry.
- A replacement texture must be representable using the original dimensions, format, mip layout, and payload reservation.
- GNF input must already match the target texture properties. DDS and PNG input can be converted automatically when supported.
- Internal file formats may impose semantic restrictions beyond the WAD container itself.
- Executable internals and signatures can change after a game update.

## Legal Notice

This project is an independent community tool and is not affiliated with Sony Interactive Entertainment, Santa Monica Studio, Jetpack Interactive, or PlayStation.

No copyrighted game archives or game assets should be distributed with the repository. Users are responsible for complying with the licenses of bundled third-party tools and libraries.
