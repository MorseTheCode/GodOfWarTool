# God of War PS4 / PS5 Asset Tool - Variable WAD experiment

This is the standalone unified version of the original 2018 Python tool. It detects the game format from each file and keeps the corresponding behavior isolated.

## Supported formats

- God of War 2018 PS4 flat WAD browsing, extraction, editing, variable-size repacking, SBP/BNK audio, and TEXPACK extraction.
- God of War Ragnarok PS5 LZ4 WAD browsing, raw extraction, editing/repacking, and Ragnarok MSGS_TXT header calculation.
- PS4 and PS5 TEXPACK browsing and native GNF, DDS, or PNG extraction.
- PS4 and PS5 TEXPACK repacking through either the active tab or a folder containing replacement GNF, DDS, or PNG files.

No `GOWTool.exe` or C++ project installation is required.

## One-file build

When using auto-py-to-exe, add these native files as binaries at the application root:

- `liblz4.dll` for Ragnarok WAD compression.
- `oo2core_7_win64.dll` for the original 2018 workflows.
- `texconv.exe` for DDS/PNG export and automatic texture import.
- `texture_codec.dll` for fast PS5 swizzle and unswizzle operations.
- The included vgmstream executable and DLL files for audio conversion.

The backend resolves bundled files through PyInstaller's temporary `_MEIPASS` directory automatically. The included `.spec` and `built_clean.py` already include `liblz4.dll` and `texconv.exe`, and no longer bundle `GOWTool.exe`.

The bundled `texture_codec.dll` accelerates PS5 swizzle/unswizzle operations without the size overhead of NumPy. Source runs without the DLL still work through the slower pure-Python fallback.

## Ragnarok MSGS_TXT editing

Ragnarok WADs support real variable-size replacements. The repacker preserves autopad entries, recalculates all nine logical block cursors, applies each descriptor's original alignment, updates main and auxiliary offsets, updates block sizes, rebuilds the physical stream, and recompresses it using the required LZ4 frame settings.

**Balance Size** remains available as an optional compatibility tool, but is no longer required. Internal formats can still impose their own semantic restrictions, so keep **Backup Original** enabled and test modified WADs individually.

TEXPACK replacements are deliberately strict. PNG and DDS inputs are resized and recompressed to the original dimensions, BC/DXGI format, mip count, PS4/PS5 swizzle, metadata, alignment, and exact payload size. GNF inputs must already match those properties. Repacking copies the original TEXPACK and changes only the existing texture payload bytes, preserving every descriptor, offset, metadata block, and alignment value.

BC compression is lossy even when the source is a lossless PNG. It can introduce small artifacts, especially in normal maps, masks, and alpha channels. Imported PNG files also regenerate every mip level. HDR and floating-point textures reject PNG input because an ordinary PNG cannot preserve their range; use DDS for those textures.
