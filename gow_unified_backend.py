import os
import struct
import ctypes
import shutil
import re
import subprocess
import tempfile

_np = None
import sys
from ctypes import c_int, c_void_p, c_size_t, POINTER, c_ubyte

OODLE_DLL_NAME = "oo2core_7_win64.dll"

class CompressionManager:
    _oodle_handle = None
    _decompress_func = None

    @staticmethod
    def get_dll_path():
        return _resource_path(OODLE_DLL_NAME)

    @classmethod
    def load_oodle(cls):
        if cls._oodle_handle: return True
        dll_path = cls.get_dll_path()
        try:
            if not os.path.exists(dll_path):
                if os.path.exists(OODLE_DLL_NAME):
                    dll_path = os.path.abspath(OODLE_DLL_NAME)
                else:
                    return False
            
            cls._oodle_handle = ctypes.CDLL(dll_path)
            
            try:
                cls._decompress_func = cls._oodle_handle.OodleLZ_Decompress
            except AttributeError:
                try:
                    cls._decompress_func = cls._oodle_handle.OodLZ_Decompress
                except AttributeError:
                    return False

            cls._decompress_func.argtypes = [
                POINTER(c_ubyte), c_size_t, POINTER(c_ubyte), c_size_t, 
                c_int, c_int, c_int, 
                c_void_p, c_size_t, c_void_p, c_void_p, c_void_p, c_size_t, c_int
            ]
            cls._decompress_func.restype = c_int
            return True
        except Exception as e:
            print(f"Error loading Oodle: {e}")
            return False

    @classmethod
    def decompress_oodle(cls, data, decompressed_size):
        if not cls.load_oodle(): 
            return None
        
        try:
            src_len = len(data)
            src = (c_ubyte * src_len).from_buffer_copy(data)
            dst = (c_ubyte * decompressed_size)()
            
            ret = cls._decompress_func(
                src, src_len, dst, decompressed_size, 
                0, 0, 0, None, 0, None, None, None, 0, 0
            )
            
            if ret == 0: 
                return None
            
            return bytearray(dst)
        except Exception as e:
            print(f"Error in Oodle decompression: {e}")
            return None

class FileEntry:
    def __init__(self, name, offset, size, compressed_size=0, is_compressed=False, type_id=0, group=0, unk1=b'', unk2=b''):
        self.name = name
        self.offset = offset
        self.size = size
        self.uncompressed_size = compressed_size if is_compressed else size
        self.is_compressed = is_compressed
        self.type_id = type_id
        self.group = group
        self.unk1 = unk1 
        self.unk2 = unk2 
        self.unique_name_hint = None

    def get_extension(self):
        if self.type_id == 0x80A1: return ".dds" 
        if self.type_id == 0x4: return ".texpack"
        return ".bin"

class TexpackEntry(FileEntry):
    def __init__(self, name, blocks):
        total_size = 0x100
        for b in blocks:
            total_size += b['raw_size']
        super().__init__(name, 0, total_size, total_size, False, 0x80A1)
        self.blocks = blocks

class SbpEntry(FileEntry):
    def __init__(self, entry_id, offset, size, audio_offset):
        # Name is ID, offset is adjusted to absolute position
        super().__init__(str(entry_id), offset + audio_offset, size, size, False, 0)
        self.entry_id = entry_id
        self.relative_offset = offset 
        self.audio_base_offset = audio_offset

    def get_extension(self):
        return ".wem"

def clean_name(name_bytes):
    try:
        if b'\x00' in name_bytes:
            name_bytes = name_bytes.split(b'\x00', 1)[0]
        return name_bytes.decode('utf-8', errors='ignore').strip()
    except:
        return "unknown"

class Gow2018_Wad:
    def __init__(self, path):
        self.path = path
        self.entries = []
        self.platform = "PS4"

    def read(self):
        if not os.path.exists(self.path): return False
        self.entries = []
        try:
            with open(self.path, 'rb') as f:
                f.seek(0, 2)
                file_size = f.tell()
                f.seek(0)
                
                while f.tell() < file_size:
                    start_pos = f.tell()
                    
                    chunk = f.read(8)
                    if len(chunk) < 8: break
                    
                    group, type_id, size = struct.unpack('<HHI', chunk)
                    
                    if size > (file_size - start_pos):
                        print(f"Warning: Invalid size detected at {start_pos}. Ending read.")
                        break
                    
                    unk1 = f.read(16)
                    name_bytes = f.read(56)
                    unk2 = f.read(16)
                    
                    if size > 0:
                        name = clean_name(name_bytes)
                        if not name: name = f"File_{start_pos}"
                        
                        data_offset = f.tell()
                        self.entries.append(FileEntry(name, data_offset, size, size, False, type_id, group, unk1, unk2))
                        
                        f.seek(size, 1)
                        
                        curr = f.tell()
                        remainder = curr % 16
                        if remainder != 0:
                            f.seek(16 - remainder, 1)
                    else:
                        pass

            return True
        except Exception as e:
            print(f"Error reading WAD: {e}")
            return False

class Gow2018_Sbp:
    def __init__(self, path):
        self.path = path
        self.entries = []
        self.data_chunk_offset = 0
        self.platform = "PS4"

    def read(self):
        if not os.path.exists(self.path): return False
        self.entries = []
        try:
            with open(self.path, 'rb') as f:
                data = f.read()
            
            # Use find to locate magic signatures, similar to C++ std::search
            bkhd_idx = data.find(b'BKHD')
            if bkhd_idx == -1: return False
            
            didx_idx = data.find(b'DIDX', bkhd_idx)
            data_idx = data.find(b'DATA', bkhd_idx)
            
            if didx_idx == -1 or data_idx == -1: return False
            
            self.data_chunk_offset = data_idx + 8
            
            # Read DIDX size
            didx_len = struct.unpack_from('<I', data, didx_idx + 4)[0]
            count = didx_len // 12
            
            curr = didx_idx + 8
            for _ in range(count):
                if curr + 12 > len(data): break
                eid, off, length = struct.unpack_from('<III', data, curr)
                self.entries.append(SbpEntry(eid, off, length, self.data_chunk_offset))
                curr += 12
                
            return True
        except Exception as e:
            print(f"Error reading SBP: {e}")
            return False

class Gow2018_Texpack:
    def __init__(self, path):
        self.path = path
        self.entries = []
        self.platform = "PS4"

    def read(self):
        if not os.path.exists(self.path): return False
        self.entries = []
        try:
            with open(self.path, 'rb') as f:
                f.seek(0, 2)
                if f.tell() < 0x20: return False
                
                f.seek(0x20)
                header_data = f.read(16)
                tex_section_off, blocks_count, blocks_info_off, tex_count = struct.unpack('<IIII', header_data)

                tex_infos = []
                f.seek(0x38)
                for _ in range(tex_count):
                    data = f.read(24)
                    file_hash, user_hash, block_info_off = struct.unpack('<QQQ', data)
                    tex_infos.append({
                        'file_hash': file_hash,
                        'user_hash': user_hash,
                        'block_info_off': block_info_off
                    })

                blocks_map = {}
                f.seek(blocks_info_off)
                for _ in range(blocks_count):
                    curr_off = f.tell()
                    data = f.read(32)
                    vals = struct.unpack('<IIQBBHHHQ', data)
                    blocks_map[curr_off] = {
                        'block_off': vals[0],
                        'raw_size': vals[1],
                        'block_size': vals[2],
                        'next_sibling_off': vals[8]
                    }

                for info in tex_infos:
                    chain = []
                    
                    current_block_off = info['block_info_off']
                    if current_block_off in blocks_map:
                        chain.insert(0, blocks_map[current_block_off])
                    
                    while chain and chain[0]['next_sibling_off'] != 0xFFFFFFFFFFFFFFFF:
                        sibling_off = chain[0]['next_sibling_off']
                        if sibling_off in blocks_map:
                            chain.insert(0, blocks_map[sibling_off])
                        else:
                            break
                    
                    name = f"{info['file_hash']:x}_{info['user_hash']:x}"
                    self.entries.append(TexpackEntry(name, chain))

            return True
        except Exception as e:
            print(f"Error reading Texpack: {e}")
            return False

class _Ps4Controller:
    @staticmethod
    def get_container(path, file_type):
        if file_type == "WAD":
            return Gow2018_Wad(path)
        elif file_type in ["SBP", "BNK"]:
            return Gow2018_Sbp(path)
        else:
            return Gow2018_Texpack(path)

    @staticmethod
    def read_file_data(container_path, entry):
        if isinstance(entry, TexpackEntry):
            return None

        try:
            with open(container_path, 'rb') as f:
                f.seek(entry.offset)
                raw_data = f.read(entry.size)
            
            final_data = raw_data
            
            if entry.is_compressed:
                decompressed = CompressionManager.decompress_oodle(raw_data, entry.uncompressed_size)
                if decompressed:
                    final_data = decompressed
                else:
                    print(f"Warning: Failed to decompress {entry.name}.")
                    return None
            return final_data
        except Exception as e:
            print(f"Error reading data for {entry.name}: {e}")
            return None

    @staticmethod
    def extract_file(container_path, entry, out_dir):
        if isinstance(entry, TexpackEntry):
            return _Ps4Controller.extract_texpack(container_path, entry, out_dir)
            
        try:
            final_data = _Ps4Controller.read_file_data(container_path, entry)
            if final_data is None: return False
            
            ext = entry.get_extension()
            
            # Magic checks if standard extraction fails to give ext
            if ext == ".bin" and len(final_data) > 4:
                magic = final_data[0:4]
                if magic == b' GNF': ext = ".dds"
                elif magic == b'OggS': ext = ".ogg"
                elif magic == b'BKHD': ext = ".wem" # Common in sub-containers
                elif magic == b'RIFF': ext = ".wem" # Wwise
                elif magic == b'DDS ': ext = ".dds"
            
            if hasattr(entry, 'unique_name_hint') and entry.unique_name_hint:
                safe_name = entry.unique_name_hint
            else:
                safe_name = "".join([c for c in entry.name if c.isalnum() or c in "._- "]).strip()
                if not safe_name: safe_name = f"file_{entry.offset}"
            
            if ext != ".bin" and "." not in safe_name:
                safe_name += ext
            elif "." not in safe_name:
                safe_name += ".bin"
            
            final_path = os.path.join(out_dir, safe_name)
            
            with open(final_path, 'wb') as f_out:
                f_out.write(final_data)
            return True
        except Exception as e:
            print(f"Error extracting {entry.name}: {e}")
            return False

    @staticmethod
    def extract_texpack(container_path, entry, out_dir):
        try:
            final_data = bytearray()
            
            with open(container_path, 'rb') as f:
                for block in entry.blocks:
                    phys_off = (block['block_off'] << 4) + 4
                    f.seek(phys_off)
                    
                    off_val, len_val = struct.unpack('<II', f.read(8))
                    f.seek(4, 1)
                    
                    if off_val != 0x20:
                        gnf_header = f.read(0x100)
                        final_data.extend(gnf_header)
                        f.seek(4, 1)
                    
                    f.seek(8, 1)
                    
                    dec_size = struct.unpack('<I', f.read(4))[0]
                    f.seek(4, 1)
                    
                    chunk_data = f.read(dec_size)
                    final_data.extend(chunk_data)

            safe_name = entry.name + ".gnf"
            final_path = os.path.join(out_dir, safe_name)
            
            with open(final_path, 'wb') as f_out:
                f_out.write(final_data)
                
            return True
        except Exception as e:
            print(f"Error extracting Texpack {entry.name}: {e}")
            return False

    @staticmethod
    def prepare_unique_names(container):
        name_counts = {}

        for entry in container.entries:
            safe_name = "".join([c for c in entry.name if c.isalnum() or c in "._- "]).strip()
            if not safe_name: safe_name = f"file_{entry.offset}"
            
            if safe_name in name_counts:
                name_counts[safe_name] += 1
                unique_name = f"{safe_name}_{name_counts[safe_name]}"
            else:
                name_counts[safe_name] = 0
                unique_name = safe_name
            
            entry.unique_name_hint = unique_name
            
        return True

    @staticmethod
    def repack_sbp(original_sbp_path, modifications, output_path, status_callback=None):
        if not os.path.exists(original_sbp_path): return False
        
        try:
            # 1. Copy original file to destination
            shutil.copy2(original_sbp_path, output_path)
            
            # 2. Get container info to map names to offsets
            # We re-parse just to get the memory map
            temp_container = Gow2018_Sbp(original_sbp_path)
            if not temp_container.read():
                return False
            
            name_to_entry = {e.name: e for e in temp_container.entries}
            
            # 3. Open destination in read+write binary mode
            with open(output_path, 'r+b') as f:
                for idx, (name, new_data) in enumerate(modifications.items()):
                    if name not in name_to_entry:
                        print(f"Skipping {name}: Not found in SBP.")
                        continue
                    
                    entry = name_to_entry[name]
                    
                    # Logic matches C++ tool:
                    # If new data > original size, truncate.
                    # If new data < original size, pad with 0.
                    # This ensures offsets remain identical.
                    
                    write_len = min(len(new_data), entry.size)
                    
                    f.seek(entry.offset)
                    f.write(new_data[:write_len])
                    
                    if len(new_data) < entry.size:
                        padding_needed = entry.size - len(new_data)
                        f.write(b'\x00' * padding_needed)
                        
                    if status_callback:
                        status_callback(idx, len(modifications), f"Injected {name}")
                        
            return True
        except Exception as e:
            print(f"Repack SBP error: {e}")
            if os.path.exists(output_path):
                try: os.remove(output_path)
                except: pass
            return False

    @staticmethod
    def repack_wad(original_wad_path, mod_folder, output_wad_path, status_callback=None):
        if not os.path.exists(original_wad_path): return False
        
        # --- MAP MOD FILES ---
        mod_map = {}
        if os.path.exists(mod_folder):
            for fname in os.listdir(mod_folder):
                full_path = os.path.join(mod_folder, fname)
                if os.path.isfile(full_path):
                    # Key: lowercase stem (e.g., 'myfile_1') - Handles extension differences
                    stem = os.path.splitext(fname)[0].lower()
                    mod_map[stem] = full_path
                    
                    # Also map full name for strict matches
                    mod_map[fname.lower()] = full_path
        # ---------------------

        is_overwrite = os.path.abspath(original_wad_path) == os.path.abspath(output_wad_path)
        write_target = output_wad_path + ".tmp" if is_overwrite else output_wad_path

        name_counts = {} # Replicates prepare_unique_names logic to find the file

        try:
            with open(original_wad_path, 'rb') as f_in, open(write_target, 'wb') as f_out:
                f_in.seek(0, 2)
                wad_size = f_in.tell()
                f_in.seek(0)
                
                offset = 0
                idx = 0
                
                while offset < wad_size:
                    f_in.seek(offset)
                    
                    header_data = f_in.read(96)
                    if len(header_data) < 96: break
                    
                    current_size = struct.unpack('<I', header_data[4:8])[0]
                    raw_name_block = header_data[24:96]
                    
                    # 1. Decode Name
                    try:
                        name_str = raw_name_block.split(b'\x00', 1)[0].decode('utf-8', errors='ignore')
                    except:
                        name_str = f"file_{offset}"

                    # 2. Generate Safe/Unique Name (EXACT same logic as Extract)
                    safe_name = "".join([c for c in name_str if c.isalnum() or c in "._- "]).strip()
                    if not safe_name: safe_name = f"file_{offset}"
                    
                    if safe_name in name_counts:
                        name_counts[safe_name] += 1
                        unique_name = f"{safe_name}_{name_counts[safe_name]}"
                    else:
                        name_counts[safe_name] = 0
                        unique_name = safe_name

                    # 3. Find Replacement in map
                    search_key = unique_name.lower()
                    
                    # Strict format check (name.idx.bin) as fallback
                    editor_format = f"{name_str.replace('/', '.').replace('\\', '.')}.{idx}.bin".lower()

                    final_data = None
                    
                    # Priority 1: Match exactly what Extract Batch generated (stem based)
                    if search_key in mod_map:
                        mod_path = mod_map[search_key]
                        try:
                            with open(mod_path, 'rb') as f_mod:
                                final_data = f_mod.read()
                        except Exception as e:
                            print(f"Error reading mod file {mod_path}: {e}")
                    
                    # Priority 2: Fallback to Editor format
                    elif editor_format in mod_map:
                         try:
                            with open(mod_map[editor_format], 'rb') as f_mod:
                                final_data = f_mod.read()
                         except: pass

                    if status_callback and idx % 20 == 0:
                        status = f"Processing: {unique_name}"
                        if final_data: status += " [REPLACED]"
                        status_callback(idx, 0, status)

                    # 4. Write Data
                    if final_data is None:
                        f_in.seek(offset + 96)
                        final_data = f_in.read(current_size)
                    
                    new_size = len(final_data)
                    header_ba = bytearray(header_data)
                    struct.pack_into('<I', header_ba, 4, new_size)
                    
                    f_out.write(header_ba)
                    f_out.write(final_data)
                    
                    # Padding
                    curr_pos = f_out.tell()
                    remainder = curr_pos % 16
                    if remainder != 0:
                        f_out.write(b'\x00' * (16 - remainder))
                        
                    next_offset = offset + 96 + current_size
                    next_offset += 0x0F
                    next_offset &= 0xFFFFFFF0
                    
                    offset = next_offset
                    idx += 1
                        
        except Exception as e:
            print(f"Repack error: {e}")
            import traceback
            traceback.print_exc()
            if is_overwrite and os.path.exists(write_target):
                os.remove(write_target)
            return False
        
        if is_overwrite:
            try:
                if os.path.exists(output_wad_path):
                    os.remove(output_wad_path)
                shutil.move(write_target, output_wad_path)
            except Exception as e:
                print(f"Error finalizing file overwrite: {e}")
                return False
            
        return True


LZ4_FRAME_MAGIC = b"\x04\x22\x4d\x18"


def _resource_path(name):
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, name)


class _Lz4FrameInfo(ctypes.Structure):
    _fields_ = [
        ("blockSizeID", ctypes.c_int),
        ("blockMode", ctypes.c_int),
        ("contentChecksumFlag", ctypes.c_int),
        ("frameType", ctypes.c_int),
        ("contentSize", ctypes.c_ulonglong),
        ("dictID", ctypes.c_uint),
        ("blockChecksumFlag", ctypes.c_int),
    ]


class _Lz4Preferences(ctypes.Structure):
    _fields_ = [
        ("frameInfo", _Lz4FrameInfo),
        ("compressionLevel", ctypes.c_int),
        ("autoFlush", ctypes.c_uint),
        ("favorDecSpeed", ctypes.c_uint),
        ("reserved", ctypes.c_uint * 3),
    ]


class Lz4Frame:
    _dll = None

    @classmethod
    def _load(cls):
        if cls._dll is not None:
            return cls._dll
        cls._dll = ctypes.CDLL(_resource_path("liblz4.dll"))
        cls._dll.LZ4F_isError.argtypes = [ctypes.c_size_t]
        cls._dll.LZ4F_isError.restype = ctypes.c_uint
        cls._dll.LZ4F_getErrorName.argtypes = [ctypes.c_size_t]
        cls._dll.LZ4F_getErrorName.restype = ctypes.c_char_p
        cls._dll.LZ4F_createDecompressionContext.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint]
        cls._dll.LZ4F_createDecompressionContext.restype = ctypes.c_size_t
        cls._dll.LZ4F_freeDecompressionContext.argtypes = [ctypes.c_void_p]
        cls._dll.LZ4F_decompress.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.c_void_p,
        ]
        cls._dll.LZ4F_decompress.restype = ctypes.c_size_t
        cls._dll.LZ4F_compressFrameBound.argtypes = [ctypes.c_size_t, ctypes.POINTER(_Lz4Preferences)]
        cls._dll.LZ4F_compressFrameBound.restype = ctypes.c_size_t
        cls._dll.LZ4F_compressFrame.argtypes = [
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.c_void_p,
            ctypes.c_size_t,
            ctypes.POINTER(_Lz4Preferences),
        ]
        cls._dll.LZ4F_compressFrame.restype = ctypes.c_size_t
        return cls._dll

    @classmethod
    def _check(cls, result):
        dll = cls._load()
        if dll.LZ4F_isError(result):
            raise RuntimeError(dll.LZ4F_getErrorName(result).decode("ascii", errors="replace"))
        return result

    @classmethod
    def decompress(cls, compressed):
        if len(compressed) < 15 or compressed[:4] != LZ4_FRAME_MAGIC:
            raise ValueError("Not an LZ4 frame with a stored content size")
        content_size = struct.unpack_from("<Q", compressed, 6)[0]
        source = ctypes.create_string_buffer(compressed)
        destination = ctypes.create_string_buffer(content_size)
        source_size = ctypes.c_size_t(len(compressed))
        destination_size = ctypes.c_size_t(content_size)
        context = ctypes.c_void_p()
        dll = cls._load()
        cls._check(dll.LZ4F_createDecompressionContext(ctypes.byref(context), 100))
        try:
            cls._check(
                dll.LZ4F_decompress(
                    context,
                    destination,
                    ctypes.byref(destination_size),
                    source,
                    ctypes.byref(source_size),
                    None,
                )
            )
        finally:
            dll.LZ4F_freeDecompressionContext(context)
        if destination_size.value != content_size:
            raise RuntimeError("The complete LZ4 frame was not decompressed")
        return destination.raw[:destination_size.value]

    @classmethod
    def compress(cls, decompressed):
        preferences = _Lz4Preferences()
        preferences.frameInfo.blockSizeID = 4
        preferences.frameInfo.blockMode = 1
        preferences.frameInfo.contentChecksumFlag = 1
        preferences.frameInfo.contentSize = len(decompressed)
        preferences.compressionLevel = 0
        dll = cls._load()
        bound = cls._check(dll.LZ4F_compressFrameBound(len(decompressed), ctypes.byref(preferences)))
        destination = ctypes.create_string_buffer(bound)
        source = ctypes.create_string_buffer(decompressed)
        written = cls._check(
            dll.LZ4F_compressFrame(
                destination,
                bound,
                source,
                len(decompressed),
                ctypes.byref(preferences),
            )
        )
        return destination.raw[:written]


class RagnarokFileEntry(FileEntry):
    def __init__(self, name, index, size, data_offset, type_id=0, group=0):
        super().__init__(name, index, size, size, False, type_id, group)
        self.archive_index = index
        self.data_offset = data_offset

    def get_extension(self):
        if self.type_id in (0x80A1, 0x80A2):
            return ".gnf"
        return ".bin"


class RagnarokTexpackEntry(FileEntry):
    def __init__(self, file_hash, user_hash, raw_size, source_texpack, blocks):
        name = f"{file_hash:016X}_{user_hash:016X}"
        super().__init__(name, 0, raw_size, raw_size, False, 0x80A1, 0)
        self.file_hash = file_hash
        self.user_hash = user_hash
        self.source_texpack = source_texpack
        self.blocks = blocks

    def get_extension(self):
        return ".gnf"


class GowRagnarok_Wad:
    def __init__(self, path):
        self.path = path
        self.entries = []
        self.platform = "PS5"
        self.decompressed_data = None
        self.descriptors = []

    def read(self):
        if not _is_file(self.path, ".wad") or not _is_lz4_file(self.path):
            return False

        try:
            with open(self.path, "rb") as stream:
                self.decompressed_data = Lz4Frame.decompress(stream.read())
            self.descriptors, absolute_offsets = _parse_ragnarok_wad(self.decompressed_data)
            self.entries = [
                RagnarokFileEntry(
                    descriptor["name"],
                    index,
                    descriptor["size"],
                    absolute_offsets[index],
                    descriptor["type_id"],
                    descriptor["group"],
                )
                for index, descriptor in enumerate(self.descriptors)
            ]
            return True
        except Exception as exc:
            print(f"Error reading Ragnarok WAD: {exc}")
            return False


class GowRagnarok_Texpack:
    def __init__(self, path):
        self.path = path
        self.entries = []
        self.platform = "PS5"

    def read(self):
        if not _is_file(self.path, ".texpack"):
            return False

        try:
            with open(self.path, "rb") as stream:
                stream.seek(0, os.SEEK_END)
                if stream.tell() < 0x38:
                    return False

                stream.seek(0x20)
                _, block_count, block_info_offset, texture_count = struct.unpack("<IIII", stream.read(16))
                if texture_count > 1000000 or block_count > 1000000:
                    return False

                texture_infos = []
                stream.seek(0x38)
                for _ in range(texture_count):
                    data = stream.read(24)
                    if len(data) != 24:
                        return False
                    texture_infos.append(struct.unpack("<QQQ", data))

                blocks = {}
                stream.seek(block_info_offset)
                for _ in range(block_count):
                    position = stream.tell()
                    data = stream.read(32)
                    if len(data) != 32:
                        return False
                    values = struct.unpack("<IIQBBHHHQ", data)
                    blocks[position] = {
                        "table_offset": position,
                        "block_offset": values[0],
                        "raw_size": values[1],
                        "block_size": values[2],
                        "mip_start": values[3],
                        "mip_end": values[4],
                        "toc_index": values[5],
                        "width": values[6],
                        "height": values[7],
                        "next_sibling": values[8],
                    }

                self.entries = []
                for file_hash, user_hash, block_info in texture_infos:
                    texture_blocks = _texture_blocks(block_info, blocks)
                    payload_size = sum(block["raw_size"] for block in texture_blocks)
                    raw_size = _ragnarok_gnf_size(stream, texture_blocks, payload_size)
                    self.entries.append(
                        RagnarokTexpackEntry(
                            file_hash, user_hash, raw_size, self.path, texture_blocks
                        )
                    )
            return True
        except Exception as exc:
            print(f"Error reading Ragnarok TEXPACK: {exc}")
            return False


class UnifiedController:
    @staticmethod
    def get_container(path, file_type):
        if file_type == "WAD":
            return GowRagnarok_Wad(path) if _is_lz4_file(path) else Gow2018_Wad(path)
        if file_type in ["SBP", "BNK"]:
            return Gow2018_Sbp(path)
        if file_type == "TEXPACK":
            return GowRagnarok_Texpack(path) if _is_ps5_texpack(path) else Gow2018_Texpack(path)
        return Gow2018_Texpack(path)

    @staticmethod
    def read_file_data(container_path, entry):
        if isinstance(entry, RagnarokTexpackEntry):
            return None
        if isinstance(entry, RagnarokFileEntry):
            try:
                with open(container_path, "rb") as stream:
                    decompressed = Lz4Frame.decompress(stream.read())
                return decompressed[entry.data_offset:entry.data_offset + entry.size]
            except (OSError, ValueError, RuntimeError):
                return None
        return _Ps4Controller.read_file_data(container_path, entry)

    @staticmethod
    def resolve_wad_texture_origins(wad_path, entries):
        references = {}
        for entry in entries:
            if entry.type_id not in (0x80A1, 0x80A2):
                continue
            try:
                texture_hash = int(entry.name.rsplit("_", 1)[1], 16)
            except (IndexError, ValueError):
                continue
            entry.is_texture_reference = True
            entry.texture_resolved = False
            entry.texture_hash = texture_hash
            entry.texture_origin = "Not found"
            references.setdefault(texture_hash, []).append(entry)

        origins = _find_texture_origins(os.path.dirname(wad_path), set(references))
        for texture_hash, origin in origins.items():
            for entry in references.get(texture_hash, ()):
                entry.texture_origin = origin
                entry.texture_resolved = True
        return sum(len(group) for group in references.values())

    @staticmethod
    def extract_file(container_path, entry, out_dir, dds=False, png=False):
        if isinstance(entry, TexpackEntry) and (dds or png):
            entry.source_texpack = container_path
            gnf = _build_ps4_gnf(entry)
            converted = _convert_ps4_gnf_to_dds(gnf)
            extension = ".dds"
            if png:
                converted = _convert_dds_to_png(converted, entry.name)
                extension = ".png"
            os.makedirs(out_dir, exist_ok=True)
            destination = _unique_path(os.path.join(out_dir, entry.name + extension))
            with open(destination, "wb") as stream:
                stream.write(converted)
            return os.path.basename(destination)

        if isinstance(entry, RagnarokTexpackEntry):
            source = _get_ragnarok_texture(entry, dds=dds, png=png)
            if not source:
                return None
            os.makedirs(out_dir, exist_ok=True)
            extension = ".png" if png else ".dds" if dds else ".gnf"
            destination = _unique_path(os.path.join(out_dir, entry.name + extension))
            shutil.copy2(source, destination)
            return os.path.basename(destination)

        if isinstance(entry, RagnarokFileEntry):
            os.makedirs(out_dir, exist_ok=True)
            destination = _unique_path(os.path.join(out_dir, _safe_filename(entry.name, entry.get_extension())))
            data = UnifiedController.read_file_data(container_path, entry)
            if data is None:
                return None
            with open(destination, "wb") as stream:
                stream.write(data)
            return os.path.basename(destination)

        return _Ps4Controller.extract_file(container_path, entry, out_dir)

    @staticmethod
    def extract_texpack(container_path, entry, out_dir):
        return UnifiedController.extract_file(container_path, entry, out_dir)

    @staticmethod
    def extract_wad_textures(
        wad_path, out_dir, dds=False, png=False, status_callback=None
    ):
        wad = GowRagnarok_Wad(wad_path)
        if not wad.read():
            return False
        os.makedirs(out_dir, exist_ok=True)
        texture_hashes = []
        for entry in wad.entries:
            if entry.type_id != 0x80A2:
                continue
            try:
                texture_hashes.append((entry.name, int(entry.name.rsplit("_", 1)[1], 16)))
            except (IndexError, ValueError):
                continue
        found = _find_ragnarok_textures(
            os.path.dirname(wad_path), {texture_hash for _, texture_hash in texture_hashes}
        )
        work_items = [
            (name, texture_hash, found[texture_hash])
            for name, texture_hash in texture_hashes
            if texture_hash in found
        ]
        total = len(work_items)
        if png:
            exported = False
            pending = []
            work_dir = tempfile.mkdtemp(prefix="gow_wad_png_batch_")
            try:
                for index, (name, texture_hash, texture) in enumerate(work_items, 1):
                    destination = _unique_path(
                        os.path.join(out_dir, _safe_filename(name, ".png"))
                    )
                    dds_path = os.path.join(
                        work_dir, os.path.splitext(os.path.basename(destination))[0] + ".dds"
                    )
                    with open(dds_path, "wb") as stream:
                        stream.write(_ragnarok_texture_bytes(texture, dds=True))
                    pending.append(dds_path)
                    if len(pending) >= 32:
                        _convert_dds_batch_to_png(pending, out_dir)
                        pending.clear()
                        for filename in os.listdir(work_dir):
                            os.remove(os.path.join(work_dir, filename))
                        if status_callback:
                            status_callback(index, total, name)
                    exported = True
                if pending:
                    _convert_dds_batch_to_png(pending, out_dir)
                    if status_callback:
                        status_callback(total, total, pending[-1])
                return exported
            finally:
                shutil.rmtree(work_dir, ignore_errors=True)

        exported = False
        for index, (name, texture_hash, texture) in enumerate(work_items, 1):
            data = _ragnarok_texture_bytes(texture, dds=dds, png=png)
            extension = ".png" if png else ".dds" if dds else ".gnf"
            destination = _unique_path(os.path.join(out_dir, _safe_filename(name, extension)))
            with open(destination, "wb") as stream:
                stream.write(data)
            exported = True
            if status_callback:
                status_callback(index, total, name)
        return exported

    @staticmethod
    def prepare_unique_names(container):
        return _Ps4Controller.prepare_unique_names(container)

    @staticmethod
    def repack_sbp(original_sbp_path, modifications, output_path, status_callback=None):
        return _Ps4Controller.repack_sbp(
            original_sbp_path, modifications, output_path, status_callback
        )

    @staticmethod
    def repack_texpack(original_texpack_path, mod_folder, output_texpack_path, status_callback=None):
        try:
            container = UnifiedController.get_container(original_texpack_path, "TEXPACK")
            if not container or not container.read():
                return False
            replacements = _map_texture_replacements(mod_folder)
            matched = []
            for entry in container.entries:
                replacement = replacements.get(entry.name.lower())
                if replacement is None and isinstance(entry, RagnarokTexpackEntry):
                    replacement = replacements.get(f"{entry.file_hash:016x}")
                if replacement:
                    matched.append((entry, replacement))
            if not matched:
                print("No replacement GNF names matched textures in this TEXPACK")
                return False

            overwrite = os.path.abspath(original_texpack_path) == os.path.abspath(output_texpack_path)
            write_path = output_texpack_path + ".tmp" if overwrite else output_texpack_path
            shutil.copy2(original_texpack_path, write_path)
            with open(write_path, "r+b") as output:
                for index, (entry, replacement_path) in enumerate(matched, 1):
                    replacement = _prepare_texture_replacement(
                        original_texpack_path,
                        entry,
                        replacement_path,
                        getattr(container, "platform", "PS4"),
                    )
                    _patch_texture_payload(
                        output,
                        original_texpack_path,
                        entry,
                        replacement,
                        getattr(container, "platform", "PS4"),
                    )
                    if status_callback:
                        status_callback(index, len(matched), f"Injected {entry.name}")
            if overwrite:
                os.replace(write_path, output_texpack_path)
            return True
        except Exception as exc:
            print(f"TEXPACK repack failed: {exc}")
            return False

    @staticmethod
    def prepare_texture_replacement(texpack_path, entry, source_path):
        platform = "PS5" if isinstance(entry, RagnarokTexpackEntry) else "PS4"
        return _prepare_texture_replacement(texpack_path, entry, source_path, platform)

    @staticmethod
    def repack_wad(original_wad_path, mod_folder, output_wad_path, status_callback=None):
        if not _is_lz4_file(original_wad_path):
            return _Ps4Controller.repack_wad(
                original_wad_path, mod_folder, output_wad_path, status_callback
            )

        try:
            with open(original_wad_path, "rb") as stream:
                original_compressed = stream.read()
            decompressed = bytearray(Lz4Frame.decompress(original_compressed))
            descriptors, absolute_offsets = _parse_ragnarok_wad(decompressed)
            replacements = _map_replacement_files(mod_folder)
            replacement_data = {}

            for index, descriptor in enumerate(descriptors):
                replacement_path = replacements.get(str(index)) or replacements.get(descriptor["name"].lower())
                if not replacement_path:
                    continue
                with open(replacement_path, "rb") as replacement_stream:
                    replacement_data[index] = replacement_stream.read()
                if status_callback:
                    status_callback(
                        len(replacement_data), len(replacements),
                        f"Prepared {descriptor['name']}",
                    )

            if not replacement_data:
                return False

            resized = [
                index for index, replacement in replacement_data.items()
                if len(replacement) != descriptors[index]["size"]
            ]
            if resized:
                decompressed = _rebuild_variable_ragnarok_wad(
                    bytes(decompressed), descriptors, absolute_offsets,
                    replacement_data,
                )
            else:
                for index, replacement in replacement_data.items():
                    start = absolute_offsets[index]
                    decompressed[start:start + descriptors[index]["size"]] = replacement

            rebuilt = Lz4Frame.compress(bytes(decompressed))
            with open(output_wad_path, "wb") as stream:
                stream.write(rebuilt)
            return True
        except Exception as exc:
            print(f"Ragnarok WAD repack failed: {exc}")
            return False


def _rebuild_variable_ragnarok_wad(
    original, descriptors, original_offsets, replacements
):
    descriptor_count = len(descriptors)
    descriptor_end = 64 + descriptor_count * 144
    header = bytearray(original[:descriptor_end])
    entry_sizes = [descriptor["size"] for descriptor in descriptors]
    for index, replacement in replacements.items():
        if descriptors[index]["name"] == "autopad" or descriptors[index]["type_id"] == 0x19:
            if len(replacement) != descriptors[index]["size"]:
                raise ValueError("Resizing an autopad entry is not supported")
        entry_sizes[index] = len(replacement)
        struct.pack_into("<I", header, 64 + index * 144 + 4, len(replacement))

    # This is the layout loop used by GoWR.exe WAD_LoadAndLayoutEntries.
    # There are nine independent logical block cursors. Main payload offsets are
    # aligned with FileDesc +0x68; auxiliary payloads at +0x60/+0x64 append to
    # blocks 5 and 8. Autopad contributes only an alignment gap here because its
    # bytes are inserted into the physical stream after a queue flush.
    block_cursors = [0] * 9
    for index, descriptor in enumerate(descriptors):
        block = descriptor["block"]
        if not 0 <= block < 9:
            raise ValueError(f"Unsupported WAD block: {block}")
        alignment = descriptor["alignment"] or 1
        if alignment & (alignment - 1):
            raise ValueError(
                f"{descriptor['name']} has invalid alignment {alignment}"
            )
        entry_offset = (block_cursors[block] + alignment - 1) & -alignment
        is_autopad = descriptor["name"] == "autopad" or descriptor["type_id"] == 0x19
        if is_autopad:
            block_cursors[block] = entry_offset
        else:
            struct.pack_into("<Q", header, 64 + index * 144 + 120, entry_offset)
            block_cursors[block] = entry_offset + entry_sizes[index]

        aux5_size = descriptor["aux5_size"]
        if aux5_size:
            struct.pack_into("<Q", header, 64 + index * 144 + 128, block_cursors[5])
            block_cursors[5] += aux5_size
        aux8_size = descriptor["aux8_size"]
        if aux8_size:
            struct.pack_into("<Q", header, 64 + index * 144 + 136, block_cursors[8])
            block_cursors[8] += aux8_size

    for block, size in enumerate(block_cursors):
        struct.pack_into("<I", header, 20 + block * 4, size)

    expected_size = descriptor_end + sum(block_cursors)
    expected_size += sum(
        descriptor["size"] for descriptor in descriptors
        if descriptor["name"] == "autopad" or descriptor["type_id"] == 0x19
    )
    probe_size = max(expected_size, descriptor_end) + 0x10000
    probe = header + bytearray(probe_size - len(header))
    rebuilt_descriptors, rebuilt_offsets = _parse_ragnarok_wad(probe)

    rebuilt = bytearray(expected_size)
    rebuilt[:descriptor_end] = header
    for index, descriptor in enumerate(descriptors):
        destination = rebuilt_offsets[index]
        if index in replacements:
            payload = replacements[index]
        else:
            source = original_offsets[index]
            payload = original[source:source + descriptor["size"]]
        expected_entry_size = rebuilt_descriptors[index]["size"]
        if len(payload) != expected_entry_size:
            raise ValueError(
                f"{descriptor['name']}: rebuilt payload is {len(payload)} bytes; "
                f"expected {expected_entry_size}"
            )
        if destination + len(payload) > len(rebuilt):
            raise ValueError(f"{descriptor['name']} points outside the rebuilt WAD")
        rebuilt[destination:destination + len(payload)] = payload

    verified_descriptors, _ = _parse_ragnarok_wad(rebuilt)
    for block, logical_extent in enumerate(block_cursors):
        declared_size = struct.unpack_from("<I", rebuilt, 20 + block * 4)[0]
        if declared_size != logical_extent:
            raise ValueError(
                f"Block {block} header size is {declared_size}; "
                f"descriptor extent is {logical_extent}"
            )
    declared_total = descriptor_end
    declared_total += sum(struct.unpack_from("<9I", rebuilt, 20))
    declared_total += sum(
        descriptor["size"] for descriptor in verified_descriptors
        if descriptor["name"] == "autopad" or descriptor["type_id"] == 0x19
    )
    if declared_total != len(rebuilt):
        raise ValueError(
            f"Rebuilt WAD is {len(rebuilt)} bytes; block layout declares {declared_total}"
        )
    return rebuilt


def _parse_ragnarok_wad(data):
    if len(data) < 64:
        raise ValueError("Ragnarok WAD header is truncated")
    magic, version, file_count = struct.unpack_from("<III", data, 0)
    if magic != 0x434F5457 or version != 2:
        raise ValueError("Unsupported Ragnarok WAD header")

    descriptor_size = 144
    descriptor_end = 64 + file_count * descriptor_size
    if descriptor_end > len(data):
        raise ValueError("Ragnarok WAD descriptor table is truncated")

    descriptors = []
    for index in range(file_count):
        position = 64 + index * descriptor_size
        group, type_id, size = struct.unpack_from("<HHI", data, position)
        raw_name = data[position + 24:position + 80]
        name = raw_name.split(b"\0", 1)[0].decode("utf-8", errors="replace")
        descriptors.append(
            {
                "group": group,
                "type_id": type_id,
                "size": size,
                "name": name,
                "unk2_20": data[position + 100],
                "aux5_size": struct.unpack_from("<I", data, position + 96)[0],
                "aux8_size": struct.unpack_from("<I", data, position + 100)[0],
                "alignment": struct.unpack_from("<I", data, position + 104)[0],
                "block": data[position + 111],
                # GoWR.exe tests bit 0 at FileDesc +0x72; the remaining bits
                # are independent flags and must not suppress a queue flush.
                "flush": (data[position + 114] & 1) != 0,
                "offset": struct.unpack_from("<Q", data, position + 120)[0],
                "aux5_offset": struct.unpack_from("<Q", data, position + 128)[0],
                "offset2": struct.unpack_from("<Q", data, position + 136)[0],
            }
        )

    absolute_offsets = [None] * file_count
    read_offset = descriptor_end
    bitset_offsets = {}
    queues = {}

    def queue(index, block):
        queues.setdefault(block, []).append(index)

    def flush_queues():
        nonlocal read_offset
        for block in sorted(queues):
            pending = queues[block]
            if not pending:
                continue
            read_offset -= bitset_offsets.get(block, 0)
            temporary = bitset_offsets.get(block, 0)
            while pending:
                entry_index = pending.pop(0)
                descriptor = descriptors[entry_index]
                if block == 8 and descriptor["block"] != 8:
                    temporary = descriptor["offset2"] + 16
                    bitset_offsets[block] = temporary
                else:
                    absolute_offsets[entry_index] = read_offset + descriptor["offset"]
                    temporary = descriptor["offset"] + descriptor["size"]
                    bitset_offsets[block] = temporary
            read_offset += temporary

    for index, descriptor in enumerate(descriptors):
        if descriptor["flush"]:
            if descriptor["name"] != "autopad":
                queue(index, descriptor["block"])
            if descriptor["unk2_20"] != 0:
                queue(index, 8)
            flush_queues()
            if descriptor["name"] == "autopad":
                absolute_offsets[index] = read_offset
                read_offset += descriptor["size"]
        else:
            queue(index, descriptor["block"])
            if descriptor["unk2_20"] != 0:
                queue(index, 8)
    flush_queues()

    for index, absolute_offset in enumerate(absolute_offsets):
        if absolute_offset is None:
            if descriptors[index]["size"] == 0:
                absolute_offsets[index] = read_offset
                continue
            raise ValueError(f"Could not resolve WAD entry {index}")
        if absolute_offset + descriptors[index]["size"] > len(data):
            raise ValueError(f"WAD entry {index} points outside the archive")
    return descriptors, absolute_offsets


def _map_replacement_files(folder):
    replacements = {}
    if not os.path.isdir(folder):
        return replacements
    for filename in os.listdir(folder):
        path = os.path.join(folder, filename)
        if not os.path.isfile(path):
            continue
        stem = os.path.splitext(filename)[0]
        if "---" in stem:
            key = stem.rsplit("---", 1)[1]
        elif "." in stem and stem.rsplit(".", 1)[1].isdigit():
            key = stem.rsplit(".", 1)[1]
        else:
            key = stem.lower()
        replacements[key.lower()] = path
    return replacements


def _map_texture_replacements(folder):
    replacements = {}
    if not os.path.isdir(folder):
        return replacements
    for filename in os.listdir(folder):
        path = os.path.join(folder, filename)
        extension = os.path.splitext(filename)[1].lower()
        if not os.path.isfile(path) or extension not in (".gnf", ".dds", ".png"):
            continue
        key = os.path.splitext(filename)[0].lower()
        if key in replacements:
            raise ValueError(
                f"Multiple replacements found for {key}; keep only one GNF, DDS, or PNG"
            )
        replacements[key] = path
    return replacements


def _prepare_texture_replacement(texpack_path, entry, source_path, platform):
    extension = os.path.splitext(source_path)[1].lower()
    if extension not in (".gnf", ".dds", ".png"):
        raise ValueError(f"{entry.name}: replacement must be GNF, DDS, or PNG")

    if platform == "PS5":
        original = _build_ragnarok_gnf(entry)
        format_word = struct.unpack_from("<I", original, 0x14)[0]
        dimension_word = struct.unpack_from("<I", original, 0x18)[0]
        mip_word = struct.unpack_from("<I", original, 0x1C)[0]
        texture_format = (format_word >> 20) & 0x1FF
        if texture_format not in _PS5_FORMATS:
            raise ValueError(f"{entry.name}: unsupported PS5 texture format {texture_format}")
        dxgi_format = _PS5_FORMATS[texture_format][0]
        width = (((dimension_word & 0xFFF) << 2) | ((format_word >> 30) & 3)) + 1
        height = ((dimension_word >> 14) & 0x3FFF) + 1
        mip_count = ((mip_word >> 16) & 0xF) + 1
    else:
        entry.source_texpack = texpack_path
        original = _build_ps4_gnf(entry)
        info = _ps4_gnf_info(original)
        width, height = info["width"], info["height"]
        mip_count, dxgi_format = info["mips"], info["dxgi"]

    if extension == ".gnf":
        with open(source_path, "rb") as stream:
            replacement = stream.read()
    else:
        if extension == ".png" and dxgi_format in (10, 54, 95, 96):
            raise ValueError(
                f"{entry.name}: PNG cannot safely preserve this HDR/float format; use DDS"
            )
        dds = _run_texconv_exact(source_path, width, height, mip_count, dxgi_format)
        replacement = _dds_to_original_gnf(dds, original, platform)

    # Run the same structural and exact-size checks used by the archive writer.
    if len(replacement) < 0x100 or replacement[:4] != b"GNF ":
        raise ValueError(f"{entry.name}: replacement is not a valid GNF")
    if platform == "PS5":
        original_size = struct.unpack_from("<I", original, 0x2C)[0]
        replacement_size = struct.unpack_from("<I", replacement, 0x2C)[0]
        structural_offsets = (8, 9, 10, 0x14, 0x18, 0x1C, 0x20, 0x2C)
        for offset in structural_offsets:
            size = 1 if offset < 0x10 else 4
            if original[offset:offset + size] != replacement[offset:offset + size]:
                raise ValueError(
                    f"{entry.name}: dimensions, format, mips, swizzle, or metadata changed"
                )
        if replacement_size != original_size:
            raise ValueError(f"{entry.name}: payload size changed")
    elif original[:0x100] != replacement[:0x100]:
        raise ValueError(f"{entry.name}: PS4 GNF configuration changed")
    return replacement


def _build_ps4_gnf(entry):
    header = None
    payload = []
    with open(entry.source_texpack if hasattr(entry, "source_texpack") else "", "rb") as stream:
        for block in entry.blocks:
            base = block["block_off"] << 4
            stream.seek(base + 4)
            payload_offset, payload_end = struct.unpack("<II", stream.read(8))
            if payload_offset != 0x20:
                stream.seek(base + 16)
                header = stream.read(0x100)
            stream.seek(base + payload_offset - 8)
            payload_size = struct.unpack("<I", stream.read(4))[0]
            stream.seek(base + payload_offset)
            payload.append(stream.read(payload_size))
    if header is None:
        raise ValueError("PS4 GNF header block was not found")
    return header + b"".join(payload)


def _texture_payload_regions(texpack_path, entry, platform):
    blocks = entry.blocks
    if platform == "PS5":
        blocks = sorted(
            blocks,
            key=lambda block: (
                block["mip_start"],
                block["mip_end"],
                block["width"] * block["height"],
                block["block_offset"],
            ),
        )
    regions = []
    with open(texpack_path, "rb") as stream:
        for block in blocks:
            block_offset = block["block_offset"] if platform == "PS5" else block["block_off"]
            base = block_offset << 4
            stream.seek(base + 4)
            payload_offset, payload_end = struct.unpack("<II", stream.read(8))
            if platform == "PS5":
                payload_size = block["raw_size"]
                if payload_end > payload_offset:
                    payload_size = min(payload_size, payload_end - payload_offset)
            else:
                stream.seek(base + payload_offset - 8)
                payload_size = struct.unpack("<I", stream.read(4))[0]
            regions.append((base + payload_offset, payload_size))
    return regions


def _patch_texture_payload(output, original_texpack_path, entry, replacement, platform):
    if len(replacement) < 0x100 or replacement[:4] != b"GNF ":
        raise ValueError(f"{entry.name}: replacement is not a GNF")
    if platform == "PS5":
        original = _build_ragnarok_gnf(entry)
        if replacement[8] != 4:
            raise ValueError(f"{entry.name}: expected a PS5 GNF v4 replacement")
        original_data_size = struct.unpack_from("<I", original, 0x2C)[0]
        replacement_file_size = struct.unpack_from("<I", replacement, 0x0C)[0]
        replacement_data_size = struct.unpack_from("<I", replacement, 0x2C)[0]
        replacement_payload_offset = replacement_file_size - replacement_data_size
        structural_offsets = (8, 9, 10, 0x14, 0x18, 0x1C, 0x20, 0x2C)
        for offset in structural_offsets:
            size = 1 if offset < 0x10 else 4
            if original[offset:offset + size] != replacement[offset:offset + size]:
                raise ValueError(f"{entry.name}: dimensions, format, mips, swizzle, or data size changed")
        if replacement_data_size != original_data_size:
            raise ValueError(f"{entry.name}: PS5 payload size changed")
        payload = replacement[
            replacement_payload_offset:replacement_payload_offset + replacement_data_size
        ]
    else:
        entry.source_texpack = original_texpack_path
        original = _build_ps4_gnf(entry)
        if replacement[8] == 4:
            raise ValueError(f"{entry.name}: expected a PS4 GNF replacement")
        if original[:0x100] != replacement[:0x100]:
            raise ValueError(f"{entry.name}: PS4 GNF configuration changed")
        payload = replacement[0x100:]

    regions = _texture_payload_regions(original_texpack_path, entry, platform)
    expected_size = sum(size for _, size in regions)
    if len(payload) != expected_size:
        raise ValueError(
            f"{entry.name}: payload must remain {expected_size} bytes, got {len(payload)}"
        )
    cursor = 0
    for offset, size in regions:
        output.seek(offset)
        output.write(payload[cursor:cursor + size])
        cursor += size


def _is_file(path, extension):
    return os.path.isfile(path) and os.path.splitext(path)[1].lower() == extension


def _is_lz4_file(path):
    try:
        with open(path, "rb") as stream:
            return stream.read(4) == LZ4_FRAME_MAGIC
    except OSError:
        return False


def _is_ps5_texpack(path):
    try:
        with open(path, "rb") as stream:
            stream.seek(0, os.SEEK_END)
            file_size = stream.tell()
            if file_size < 0x38:
                return False
            stream.seek(0x24)
            block_count, block_info_offset = struct.unpack("<II", stream.read(8))
            if block_count > 1000000 or block_info_offset >= file_size:
                return False
            stream.seek(block_info_offset)
            for _ in range(block_count):
                data = stream.read(32)
                if len(data) != 32:
                    return False
                block_offset = struct.unpack_from("<I", data)[0] << 4
                return_position = stream.tell()
                if block_offset + 0x19 <= file_size:
                    stream.seek(block_offset + 4)
                    payload_offset = struct.unpack("<I", stream.read(4))[0]
                    if payload_offset != 0x20:
                        stream.seek(block_offset + 0x18)
                        return stream.read(1) == b"\x04"
                stream.seek(return_position)
    except (OSError, struct.error):
        return False
    return False


def _stem(path):
    return os.path.splitext(os.path.basename(path))[0]


def _texture_raw_size(block_info_offset, blocks):
    return sum(block["raw_size"] for block in _texture_blocks(block_info_offset, blocks))


def _texture_blocks(block_info_offset, blocks):
    result = []
    seen = set()
    current = block_info_offset
    while current in blocks and current not in seen:
        seen.add(current)
        block = blocks[current]
        result.insert(0, block)
        current = block["next_sibling"]
        if current == 0xFFFFFFFFFFFFFFFF:
            break
    return result


def _ragnarok_gnf_size(stream, blocks, payload_size):
    old_position = stream.tell()
    try:
        for block in blocks:
            base = block["block_offset"] << 4
            stream.seek(base + 4)
            payload_offset = struct.unpack("<I", stream.read(4))[0]
            if payload_offset == 0x20:
                continue
            stream.seek(base + 0x1C)
            header_file_size = struct.unpack("<I", stream.read(4))[0]
            stream.seek(base + 0x3C)
            data_size = struct.unpack("<I", stream.read(4))[0]
            gnf_payload_offset = header_file_size - data_size if header_file_size > data_size else 0x100
            return max(header_file_size, gnf_payload_offset + payload_size)
    finally:
        stream.seek(old_position)
    return 0x100 + payload_size


def _parse_unpacked_name(relative_path):
    base_name = os.path.basename(relative_path.replace("\\", "/"))
    match = re.match(r"^(.*)---(\d+)\.bin$", base_name, re.IGNORECASE)
    if match:
        return match.group(1), int(match.group(2))
    return relative_path, 0


def _safe_filename(name, extension):
    safe_name = "".join(character for character in name if character.isalnum() or character in "._- ").strip()
    safe_name = safe_name or "file"
    if "." not in safe_name and extension:
        safe_name += extension
    return safe_name


def _get_ragnarok_texture(entry, dds=False, png=False):
    data = _ragnarok_texture_bytes(entry, dds=dds, png=png)
    if png:
        extension = ".png"
    elif dds:
        extension = ".dds"
    else:
        extension = ".gnf"

    cache_dir = os.path.join(tempfile.gettempdir(), "gowr_native_texture_cache")
    os.makedirs(cache_dir, exist_ok=True)
    output = os.path.join(cache_dir, f"{entry.file_hash:016X}{extension}")
    with open(output, "wb") as stream:
        stream.write(data)
    return output


def _ragnarok_texture_bytes(entry, dds=False, png=False):
    gnf = _build_ragnarok_gnf(entry)
    if png:
        return _convert_dds_to_png(_convert_ps5_gnf_to_dds(gnf), entry.name)
    if dds:
        return _convert_ps5_gnf_to_dds(gnf)
    return gnf


def _find_ragnarok_textures(texpack_dir, wanted_hashes):
    wanted = set(wanted_hashes)
    found = {}
    if not wanted or not os.path.isdir(texpack_dir):
        return found

    for file_entry in os.scandir(texpack_dir):
        if not wanted or not file_entry.is_file() or not file_entry.name.lower().endswith(".texpack"):
            continue
        try:
            with open(file_entry.path, "rb") as stream:
                stream.seek(0x20)
                header = stream.read(16)
                if len(header) != 16:
                    continue
                _, block_count, block_info_offset, texture_count = struct.unpack("<IIII", header)
                if texture_count > 1000000 or block_count > 1000000:
                    continue
                stream.seek(0x38)
                table = stream.read(texture_count * 24)
                if len(table) != texture_count * 24:
                    continue
                matches = [
                    values
                    for values in struct.iter_unpack("<QQQ", table)
                    if values[0] in wanted
                ]
                for file_hash, user_hash, first_block in matches:
                    blocks = _read_ragnarok_texture_blocks(stream, first_block, block_info_offset, block_count)
                    if not blocks:
                        continue
                    payload_size = sum(block["raw_size"] for block in blocks)
                    raw_size = _ragnarok_gnf_size(stream, blocks, payload_size)
                    found[file_hash] = RagnarokTexpackEntry(
                        file_hash, user_hash, raw_size, file_entry.path, blocks
                    )
                    wanted.discard(file_hash)
        except (OSError, struct.error, ValueError):
            continue
    return found


def _find_texture_origins(texpack_dir, wanted_hashes):
    wanted = set(wanted_hashes)
    origins = {}
    if not wanted or not os.path.isdir(texpack_dir):
        return origins

    for file_entry in os.scandir(texpack_dir):
        if not wanted or not file_entry.is_file() or not file_entry.name.lower().endswith(".texpack"):
            continue
        try:
            with open(file_entry.path, "rb") as stream:
                stream.seek(0x20)
                header = stream.read(16)
                if len(header) != 16:
                    continue
                _, block_count, _, texture_count = struct.unpack("<IIII", header)
                if texture_count > 1000000 or block_count > 1000000:
                    continue
                stream.seek(0x38)
                table = stream.read(texture_count * 24)
                if len(table) != texture_count * 24:
                    continue
                for file_hash, _, _ in struct.iter_unpack("<QQQ", table):
                    if file_hash in wanted:
                        origins[file_hash] = file_entry.name
                        wanted.remove(file_hash)
                        if not wanted:
                            break
        except (OSError, struct.error):
            continue
    return origins


def _read_ragnarok_texture_blocks(stream, first_block, table_start, block_count):
    table_end = table_start + block_count * 32
    blocks = []
    seen = set()
    current = first_block
    while current != 0xFFFFFFFFFFFFFFFF and current not in seen:
        if current < table_start or current + 32 > table_end:
            return []
        seen.add(current)
        stream.seek(current)
        data = stream.read(32)
        if len(data) != 32:
            return []
        values = struct.unpack("<IIQBBHHHQ", data)
        blocks.insert(0, {
            "table_offset": current,
            "block_offset": values[0],
            "raw_size": values[1],
            "block_size": values[2],
            "mip_start": values[3],
            "mip_end": values[4],
            "toc_index": values[5],
            "width": values[6],
            "height": values[7],
            "next_sibling": values[8],
        })
        current = values[8]
    return blocks


def _build_ragnarok_gnf(entry):
    blocks = sorted(
        entry.blocks,
        key=lambda block: (
            block["mip_start"],
            block["mip_end"],
            block["width"] * block["height"],
            block["block_offset"],
        ),
    )
    if not blocks:
        raise ValueError("Texture has no data blocks")

    with open(entry.source_texpack, "rb") as stream:
        header_block = None
        for block in blocks:
            base = block["block_offset"] << 4
            stream.seek(base + 4)
            if struct.unpack("<I", stream.read(4))[0] != 0x20:
                header_block = block
                break
        if header_block is None:
            raise ValueError("Texture GNF header block was not found")

        header_base = header_block["block_offset"] << 4
        stream.seek(header_base + 4)
        header_payload_offset = struct.unpack("<I", stream.read(4))[0]
        stream.seek(header_base + 16)
        header = bytearray(stream.read(0x100))
        if len(header) != 0x100 or header[:4] != b"GNF ":
            raise ValueError("Invalid PS5 GNF header")

        metadata = b""
        if header_payload_offset > 0x110:
            stream.seek(header_base + 0x110)
            metadata = stream.read(header_payload_offset - 0x110)

        payload_parts = []
        for block in blocks:
            base = block["block_offset"] << 4
            stream.seek(base + 4)
            payload_offset, payload_end = struct.unpack("<II", stream.read(8))
            payload_size = block["raw_size"]
            if payload_end > payload_offset:
                payload_size = min(payload_size, payload_end - payload_offset)
            stream.seek(base + payload_offset)
            payload_parts.append(stream.read(payload_size))

    payload = b"".join(payload_parts)
    original_file_size = struct.unpack_from("<I", header, 0x0C)[0]
    original_data_size = struct.unpack_from("<I", header, 0x2C)[0]
    payload_offset = (
        original_file_size - original_data_size
        if original_file_size > original_data_size
        else 0x100
    )
    largest = max(blocks, key=lambda block: block["width"] * block["height"])
    if largest["width"] and largest["height"]:
        stored_width = largest["width"] - 1
        format_word = struct.unpack_from("<I", header, 0x14)[0]
        dimension_word = struct.unpack_from("<I", header, 0x18)[0]
        format_word = (format_word & ~0x000FFFFF) | 0xC
        format_word = (format_word & ~(0x3 << 30)) | ((stored_width & 0x3) << 30)
        dimension_word = (dimension_word & ~0xFFF) | ((stored_width >> 2) & 0xFFF)
        dimension_word = (dimension_word & ~(0x3FFF << 14)) | (((largest["height"] - 1) & 0x3FFF) << 14)
        struct.pack_into("<I", header, 0x14, format_word)
        struct.pack_into("<I", header, 0x18, dimension_word)

    expanded_size = max(original_file_size, payload_offset + len(payload))
    struct.pack_into("<I", header, 0x0C, expanded_size)
    output = bytearray(expanded_size)
    output[:0x100] = header
    output[0x100:0x100 + len(metadata)] = metadata
    output[payload_offset:payload_offset + len(payload)] = payload
    return bytes(output)


_PS5_FORMATS = {
    7: (56, 2, 1, 1),
    8: (58, 2, 1, 1),
    13: (54, 2, 1, 1),
    65: (11, 8, 1, 1),
    66: (13, 8, 1, 1),
    71: (10, 8, 1, 1),
    169: (71, 8, 4, 4),
    170: (72, 8, 4, 4),
    171: (74, 16, 4, 4),
    172: (75, 16, 4, 4),
    173: (77, 16, 4, 4),
    174: (78, 16, 4, 4),
    175: (80, 8, 4, 4),
    176: (81, 8, 4, 4),
    177: (83, 16, 4, 4),
    178: (84, 16, 4, 4),
    179: (95, 16, 4, 4),
    180: (96, 16, 4, 4),
    181: (98, 16, 4, 4),
    182: (99, 16, 4, 4),
}


def _align_up(value, alignment):
    return (value + alignment - 1) & ~(alignment - 1)


def _ps5_tiled_offset(block_x, block_y, block_columns, bytes_per_block):
    if bytes_per_block == 8:
        page_width, page_height = 32, 16
        x = block_x & 31
        y = block_y & 15
        element = (
            ((x >> 0) & 1) << 0
            | ((y >> 0) & 1) << 1
            | ((y >> 1) & 1) << 2
            | ((x >> 1) & 1) << 3
            | ((x >> 2) & 1) << 4
            | ((y >> 2) & 1) << 5
            | ((x >> 3) & 1) << 6
            | ((y >> 3) & 1) << 7
            | ((x >> 4) & 1) << 8
        )
    else:
        page_width, page_height = 16, 16
        x = block_x & 15
        y = block_y & 15
        element = (
            ((y >> 0) & 1) << 0
            | ((y >> 1) & 1) << 1
            | ((x >> 0) & 1) << 2
            | ((x >> 1) & 1) << 3
            | ((y >> 2) & 1) << 4
            | ((x >> 2) & 1) << 5
            | ((y >> 3) & 1) << 6
            | ((x >> 3) & 1) << 7
        )
    page_columns = (block_columns + page_width - 1) // page_width
    page_index = (block_y // page_height) * page_columns + block_x // page_width
    return page_index * 4096 + element * bytes_per_block


class _NativeTextureCodec:
    _dll = None
    _load_attempted = False

    @classmethod
    def load(cls):
        if cls._load_attempted:
            return cls._dll
        cls._load_attempted = True
        try:
            dll = ctypes.CDLL(_resource_path("texture_codec.dll"))
            byte_pointer = POINTER(c_ubyte)
            arguments = [
                byte_pointer, c_size_t, byte_pointer, c_size_t, c_size_t,
                ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32,
            ]
            dll.ps5_unswizzle.argtypes = arguments
            dll.ps5_unswizzle.restype = c_int
            dll.ps5_swizzle.argtypes = arguments
            dll.ps5_swizzle.restype = c_int
            cls._dll = dll
        except (OSError, AttributeError):
            cls._dll = None
        return cls._dll


def _ps5_unswizzle_native(tiled_data, source_base, columns, rows, bytes_per_block):
    dll = _NativeTextureCodec.load()
    if dll is None:
        return None
    output = bytearray(columns * rows * bytes_per_block)
    source_buffer = (c_ubyte * len(tiled_data)).from_buffer_copy(tiled_data)
    output_buffer = (c_ubyte * len(output)).from_buffer(output)
    success = dll.ps5_unswizzle(
        source_buffer, len(tiled_data), output_buffer, len(output), source_base,
        columns, rows, bytes_per_block,
    )
    return bytes(output) if success else None


def _ps5_swizzle_native(
    linear, payload, destination_base, columns, rows, bytes_per_block
):
    dll = _NativeTextureCodec.load()
    if dll is None:
        return False
    source_buffer = (c_ubyte * len(linear)).from_buffer_copy(linear)
    payload_buffer = (c_ubyte * len(payload)).from_buffer(payload)
    return bool(dll.ps5_swizzle(
        source_buffer, len(linear), payload_buffer, len(payload), destination_base,
        columns, rows, bytes_per_block,
    ))


def _ps5_numpy_offsets(columns, row_start, row_end, bytes_per_block):
    x = _np.arange(columns, dtype=_np.uint64)[None, :]
    y = _np.arange(row_start, row_end, dtype=_np.uint64)[:, None]
    if bytes_per_block == 8:
        page_width, page_height = 32, 16
        local_x, local_y = x & 31, y & 15
        element = (
            ((local_x >> 0) & 1) << 0
            | ((local_y >> 0) & 1) << 1
            | ((local_y >> 1) & 1) << 2
            | ((local_x >> 1) & 1) << 3
            | ((local_x >> 2) & 1) << 4
            | ((local_y >> 2) & 1) << 5
            | ((local_x >> 3) & 1) << 6
            | ((local_y >> 3) & 1) << 7
            | ((local_x >> 4) & 1) << 8
        )
    else:
        page_width, page_height = 16, 16
        local_x, local_y = x & 15, y & 15
        element = (
            ((local_y >> 0) & 1) << 0
            | ((local_y >> 1) & 1) << 1
            | ((local_x >> 0) & 1) << 2
            | ((local_x >> 1) & 1) << 3
            | ((local_y >> 2) & 1) << 4
            | ((local_x >> 2) & 1) << 5
            | ((local_y >> 3) & 1) << 6
            | ((local_x >> 3) & 1) << 7
        )
    page_columns = (columns + page_width - 1) // page_width
    page_index = (y // page_height) * page_columns + x // page_width
    return page_index * 4096 + element * bytes_per_block


def _ps5_unswizzle_numpy(tiled_data, source_base, columns, rows, bytes_per_block):
    source = _np.frombuffer(tiled_data, dtype=_np.uint8)
    output = _np.zeros((rows, columns, bytes_per_block), dtype=_np.uint8)
    byte_indices = _np.arange(bytes_per_block, dtype=_np.uint64)
    for row_start in range(0, rows, 64):
        row_end = min(row_start + 64, rows)
        offsets = _ps5_numpy_offsets(columns, row_start, row_end, bytes_per_block)
        offsets = source_base + offsets[..., None] + byte_indices
        valid = offsets < source.size
        chunk = _np.zeros(offsets.shape, dtype=_np.uint8)
        chunk[valid] = source[offsets[valid]]
        output[row_start:row_end] = chunk
    return output.tobytes()


def _ps5_swizzle_numpy(linear, payload, destination_base, columns, rows, bytes_per_block):
    source = _np.frombuffer(linear, dtype=_np.uint8).reshape(rows, columns, bytes_per_block)
    destination = _np.frombuffer(payload, dtype=_np.uint8)
    byte_indices = _np.arange(bytes_per_block, dtype=_np.uint64)
    for row_start in range(0, rows, 64):
        row_end = min(row_start + 64, rows)
        offsets = _ps5_numpy_offsets(columns, row_start, row_end, bytes_per_block)
        offsets = destination_base + offsets[..., None] + byte_indices
        if offsets.max() >= destination.size:
            raise ValueError("Swizzled PS5 mip points outside the original payload")
        destination[offsets] = source[row_start:row_end]


def _dds_dx10_header(width, height, mip_count, dxgi_format, top_level_size):
    flags = 0x000A1007
    caps = 0x1000 | (0x400008 if mip_count > 1 else 0)
    header = bytearray(b"DDS ")
    header.extend(
        struct.pack(
            "<7I11I",
            124,
            flags,
            height,
            width,
            top_level_size,
            0,
            mip_count,
            *([0] * 11),
        )
    )
    header.extend(struct.pack("<II4s5I", 32, 4, b"DX10", 0, 0, 0, 0, 0))
    header.extend(struct.pack("<5I", caps, 0, 0, 0, 0))
    header.extend(struct.pack("<5I", dxgi_format, 3, 0, 1, 3))
    return bytes(header)


def _convert_ps5_gnf_to_dds(gnf):
    if len(gnf) < 0x100 or gnf[:4] != b"GNF " or gnf[8] != 4:
        raise ValueError("Not a PS5 GNF v4 texture")
    format_word = struct.unpack_from("<I", gnf, 0x14)[0]
    dimension_word = struct.unpack_from("<I", gnf, 0x18)[0]
    mip_word = struct.unpack_from("<I", gnf, 0x1C)[0]
    texture_format = (format_word >> 20) & 0x1FF
    if texture_format not in _PS5_FORMATS:
        raise ValueError(f"Unsupported PS5 texture format {texture_format}")
    dxgi_format, bytes_per_block, block_width, block_height = _PS5_FORMATS[texture_format]
    width = (((dimension_word & 0xFFF) << 2) | ((format_word >> 30) & 0x3)) + 1
    height = ((dimension_word >> 14) & 0x3FFF) + 1
    mip_count = ((mip_word >> 16) & 0xF) + 1
    file_size = struct.unpack_from("<I", gnf, 0x0C)[0]
    data_size = struct.unpack_from("<I", gnf, 0x2C)[0]
    payload_start = file_size - data_size if file_size > data_size else gnf[4] + 8
    tiled_data = gnf[payload_start:payload_start + data_size]

    mip_sizes = []
    linear_sizes = []
    for mip in range(mip_count):
        mip_width = max(width >> mip, 1)
        mip_height = max(height >> mip, 1)
        columns = _align_up(mip_width, block_width) // block_width
        rows = _align_up(mip_height, block_height) // block_height
        linear_sizes.append(columns * rows * bytes_per_block)
        micro_width = 8 if bytes_per_block == 8 else 4 if bytes_per_block == 16 else 8
        micro_tile_bytes = micro_width * bytes_per_block
        mip_sizes.append(_align_up(((columns + micro_width - 1) // micro_width) * rows * micro_tile_bytes, 256))

    tail_start = mip_count - 1
    for mip in range(mip_count):
        if max(max(width >> mip, 1), max(height >> mip, 1)) <= 512:
            tail_start = mip
            break
    offsets = [0] * mip_count
    payload_offset = 0x200 if bytes_per_block == 16 else 0x100
    for mip in range(mip_count - 1, tail_start - 1, -1):
        if payload_offset and mip_sizes[mip] >= 0x400:
            payload_offset = _align_up(payload_offset, min(mip_sizes[mip], 0x1000))
        offsets[mip] = payload_offset
        payload_offset += mip_sizes[mip]
    payload_offset = _align_up(payload_offset, 0x1000)
    for mip in range(tail_start - 1, -1, -1):
        offsets[mip] = payload_offset
        payload_offset += mip_sizes[mip]

    linear_parts = []
    for mip in range(mip_count):
        mip_width = max(width >> mip, 1)
        mip_height = max(height >> mip, 1)
        columns = _align_up(mip_width, block_width) // block_width
        rows = _align_up(mip_height, block_height) // block_height
        source_base = offsets[mip]
        native_linear = _ps5_unswizzle_native(
            tiled_data, source_base, columns, rows, bytes_per_block
        )
        if native_linear is not None:
            linear_parts.append(native_linear)
            continue
        mip_linear = bytearray(linear_sizes[mip])
        for block_y in range(rows):
            for block_x in range(columns):
                source_offset = source_base + _ps5_tiled_offset(
                    block_x, block_y, columns, bytes_per_block
                )
                destination = (block_y * columns + block_x) * bytes_per_block
                if source_offset + bytes_per_block <= len(tiled_data):
                    mip_linear[destination:destination + bytes_per_block] = tiled_data[
                        source_offset:source_offset + bytes_per_block
                    ]
        linear_parts.append(bytes(mip_linear))

    linear = b"".join(linear_parts)

    return _dds_dx10_header(
        width, height, mip_count, dxgi_format, linear_sizes[0]
    ) + linear


_DXGI_NAMES = {
    10: "R16G16B16A16_FLOAT", 11: "R16G16B16A16_UNORM", 13: "R16G16B16A16_SNORM",
    54: "R16_FLOAT", 56: "R16_UNORM", 58: "R16_SNORM",
    71: "BC1_UNORM", 72: "BC1_UNORM_SRGB", 74: "BC2_UNORM", 75: "BC2_UNORM_SRGB",
    77: "BC3_UNORM", 78: "BC3_UNORM_SRGB", 80: "BC4_UNORM", 81: "BC4_SNORM",
    83: "BC5_UNORM", 84: "BC5_SNORM", 95: "BC6H_UF16", 96: "BC6H_SF16",
    98: "BC7_UNORM", 99: "BC7_UNORM_SRGB",
}

_PS4_FORMATS = {
    (0x23, 0): (71, 4, 4), (0x23, 9): (72, 4, 4),
    (0x24, 0): (74, 8, 4), (0x24, 9): (75, 8, 4),
    (0x25, 0): (77, 8, 4), (0x25, 9): (78, 8, 4),
    (0x26, 0): (80, 4, 4), (0x26, 1): (81, 4, 4),
    (0x27, 0): (83, 8, 4), (0x27, 1): (84, 8, 4),
    (0x28, 0): (95, 8, 4), (0x28, 1): (96, 8, 4),
    (0x29, 0): (98, 8, 4), (0x29, 9): (99, 8, 4),
}


def _round_up_power_of_two(value):
    return 1 if value <= 1 else 1 << (value - 1).bit_length()


def _ps4_morton(index, width=8, height=8):
    x = y = 0
    x_bit = y_bit = 1
    while width > 1 or height > 1:
        if width > 1:
            x += x_bit * (index & 1)
            index >>= 1
            x_bit *= 2
            width >>= 1
        if height > 1:
            y += y_bit * (index & 1)
            index >>= 1
            y_bit *= 2
            height >>= 1
    return y * 8 + x


def _ps4_unswizzle(source, width, height, bits_per_pixel, pixel_block):
    minimum = pixel_block * pixel_block * bits_per_pixel // 8
    output_size = width * height * bits_per_pixel // 8
    if output_size <= minimum:
        return source[:minimum]
    element_size = bits_per_pixel * 2 if pixel_block != 1 else bits_per_pixel // 8
    rows = height // pixel_block
    columns = width // pixel_block
    output = bytearray(output_size)
    source_offset = 0
    for tile_y in range((rows + 7) // 8):
        for tile_x in range((columns + 7) // 8):
            for index in range(64):
                morton = _ps4_morton(index)
                local_y, local_x = divmod(morton, 8)
                chunk = source[source_offset:source_offset + element_size]
                source_offset += element_size
                x = tile_x * 8 + local_x
                y = tile_y * 8 + local_y
                if x < columns and y < rows:
                    destination = element_size * (y * columns + x)
                    output[destination:destination + element_size] = chunk
    return bytes(output)


def _ps4_swizzle(source, width, height, bits_per_pixel, pixel_block):
    minimum = pixel_block * pixel_block * bits_per_pixel // 8
    output_size = width * height * bits_per_pixel // 8
    if output_size <= minimum:
        return source[:minimum]
    element_size = bits_per_pixel * 2 if pixel_block != 1 else bits_per_pixel // 8
    rows = height // pixel_block
    columns = width // pixel_block
    output = bytearray(output_size)
    destination = 0
    for tile_y in range((rows + 7) // 8):
        for tile_x in range((columns + 7) // 8):
            for index in range(64):
                morton = _ps4_morton(index)
                local_y, local_x = divmod(morton, 8)
                x = tile_x * 8 + local_x
                y = tile_y * 8 + local_y
                if x < columns and y < rows:
                    source_offset = element_size * (y * columns + x)
                    output[destination:destination + element_size] = source[
                        source_offset:source_offset + element_size
                    ]
                    destination += element_size
    return bytes(output)


def _ps4_gnf_info(gnf):
    format_word = struct.unpack_from("<I", gnf, 0x14)[0]
    dimension_word = struct.unpack_from("<I", gnf, 0x18)[0]
    mip_word = struct.unpack_from("<I", gnf, 0x1C)[0]
    texture_format = (format_word >> 20) & 0x3F
    format_type = (format_word >> 26) & 0xF
    key = (texture_format, format_type)
    if key not in _PS4_FORMATS:
        raise ValueError(f"Unsupported PS4 GNF format {texture_format}/{format_type}")
    dxgi_format, bits_per_pixel, pixel_block = _PS4_FORMATS[key]
    return {
        "width": (dimension_word & 0x3FFF) + 1,
        "height": ((dimension_word >> 14) & 0x3FFF) + 1,
        "mips": ((mip_word >> 16) & 0xF) + 1,
        "dxgi": dxgi_format,
        "bpp": bits_per_pixel,
        "pixel_block": pixel_block,
        "data_size": struct.unpack_from("<I", gnf, 0x2C)[0],
    }


def _convert_ps4_gnf_to_dds(gnf):
    info = _ps4_gnf_info(gnf)
    tiled = gnf[0x100:0x100 + info["data_size"]]
    linear_parts = []
    tiled_offset = 0
    for mip in range(info["mips"]):
        width = _align_up(max(info["width"] >> mip, info["pixel_block"]), info["pixel_block"])
        height = _align_up(max(info["height"] >> mip, info["pixel_block"]), info["pixel_block"])
        padded_width = max(_round_up_power_of_two(width), 32)
        padded_height = max(_round_up_power_of_two(height), 32)
        tiled_size = padded_width * padded_height * info["bpp"] // 8
        padded = _ps4_unswizzle(
            tiled[tiled_offset:tiled_offset + tiled_size],
            padded_width, padded_height, info["bpp"], info["pixel_block"],
        )
        tiled_offset += tiled_size
        row_size = width * info["pixel_block"] * info["bpp"] // 8
        padded_row = padded_width * info["pixel_block"] * info["bpp"] // 8
        for row in range(height // info["pixel_block"]):
            linear_parts.append(padded[row * padded_row:row * padded_row + row_size])
    linear = b"".join(linear_parts)
    top_width = _align_up(info["width"], info["pixel_block"]) // info["pixel_block"]
    top_height = _align_up(info["height"], info["pixel_block"]) // info["pixel_block"]
    top_size = top_width * top_height * (8 if info["bpp"] == 4 else 16)
    return _dds_dx10_header(
        info["width"], info["height"], info["mips"], info["dxgi"], top_size
    ) + linear


def _read_dds_dx10(dds):
    if len(dds) < 148 or dds[:4] != b"DDS " or dds[84:88] != b"DX10":
        raise ValueError("DirectXTex did not produce a DX10 DDS")
    height, width = struct.unpack_from("<II", dds, 12)
    mip_count = struct.unpack_from("<I", dds, 28)[0] or 1
    dxgi_format = struct.unpack_from("<I", dds, 128)[0]
    return width, height, mip_count, dxgi_format, dds[148:]


def _run_texconv_exact(source_path, width, height, mip_count, dxgi_format):
    format_name = _DXGI_NAMES.get(dxgi_format)
    if not format_name:
        raise ValueError(f"DirectXTex format {dxgi_format} is not supported for import")
    texconv = _resource_path("texconv.exe")
    if not os.path.isfile(texconv):
        raise FileNotFoundError("texconv.exe is missing from the application build")
    output_dir = tempfile.mkdtemp(prefix="gow_texture_convert_")
    try:
        command = [
            texconv, "-nologo", "-y", "-dx10", "-f", format_name,
            "-w", str(width), "-h", str(height), "-m", str(mip_count),
            "-o", output_dir, source_path,
        ]
        result = subprocess.run(
            command, capture_output=True, text=True, startupinfo=_hidden_startupinfo()
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "texconv failed")
        output = os.path.join(output_dir, os.path.splitext(os.path.basename(source_path))[0] + ".DDS")
        if not os.path.isfile(output):
            candidates = [os.path.join(output_dir, name) for name in os.listdir(output_dir) if name.lower().endswith(".dds")]
            if not candidates:
                raise RuntimeError("texconv did not create a DDS")
            output = candidates[0]
        with open(output, "rb") as stream:
            return stream.read()
    finally:
        shutil.rmtree(output_dir, ignore_errors=True)


def _hidden_startupinfo():
    if os.name != "nt":
        return None
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return startupinfo


def _convert_dds_to_png(dds, name):
    texconv = _resource_path("texconv.exe")
    if not os.path.isfile(texconv):
        raise FileNotFoundError("texconv.exe is missing from the application build")
    work_dir = tempfile.mkdtemp(prefix="gow_texture_png_")
    try:
        safe_name = _safe_filename(name, "") or "texture"
        source = os.path.join(work_dir, safe_name + ".dds")
        with open(source, "wb") as stream:
            stream.write(dds)
        result = subprocess.run(
            [
                texconv, "-nologo", "-y", "-f", "R8G8B8A8_UNORM",
                "-ft", "png", "-o", work_dir, source,
            ],
            capture_output=True,
            text=True,
            startupinfo=_hidden_startupinfo(),
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "PNG conversion failed")
        candidates = [
            os.path.join(work_dir, filename)
            for filename in os.listdir(work_dir)
            if filename.lower().endswith(".png")
        ]
        if not candidates:
            raise RuntimeError("texconv did not create a PNG")
        with open(candidates[0], "rb") as stream:
            return stream.read()
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _convert_dds_batch_to_png(dds_paths, output_dir):
    texconv = _resource_path("texconv.exe")
    if not os.path.isfile(texconv):
        raise FileNotFoundError("texconv.exe is missing from the application build")
    result = subprocess.run(
        [
            texconv, "-nologo", "-y", "-f", "R8G8B8A8_UNORM",
            "-ft", "png", "-o", output_dir, *dds_paths,
        ],
        capture_output=True,
        text=True,
        startupinfo=_hidden_startupinfo(),
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "PNG conversion failed")
    missing = [
        os.path.splitext(os.path.basename(path))[0] + ".png"
        for path in dds_paths
        if not os.path.isfile(
            os.path.join(output_dir, os.path.splitext(os.path.basename(path))[0] + ".png")
        )
    ]
    if missing:
        raise RuntimeError(f"texconv did not create {len(missing)} PNG file(s)")


def _dds_to_original_gnf(dds, original_gnf, platform):
    width, height, mip_count, dxgi_format, linear = _read_dds_dx10(dds)
    if platform == "PS5":
        format_word = struct.unpack_from("<I", original_gnf, 0x14)[0]
        dimension_word = struct.unpack_from("<I", original_gnf, 0x18)[0]
        mip_word = struct.unpack_from("<I", original_gnf, 0x1C)[0]
        texture_format = (format_word >> 20) & 0x1FF
        expected_dxgi, bytes_per_block, block_width, block_height = _PS5_FORMATS[texture_format]
        original_width = (((dimension_word & 0xFFF) << 2) | ((format_word >> 30) & 3)) + 1
        original_height = ((dimension_word >> 14) & 0x3FFF) + 1
        original_mips = ((mip_word >> 16) & 0xF) + 1
        data_size = struct.unpack_from("<I", original_gnf, 0x2C)[0]
        file_size = struct.unpack_from("<I", original_gnf, 0x0C)[0]
        payload_start = file_size - data_size
        payload = bytearray(original_gnf[payload_start:payload_start + data_size])
        mip_sizes, offsets = _ps5_payload_layout(
            original_width, original_height, original_mips,
            bytes_per_block, block_width, block_height,
        )
        required_linear_size = 0
        for mip in range(original_mips):
            mip_width = max(original_width >> mip, 1)
            mip_height = max(original_height >> mip, 1)
            required_linear_size += (
                _align_up(mip_width, block_width) // block_width
                * (_align_up(mip_height, block_height) // block_height)
                * bytes_per_block
            )
        if len(linear) != required_linear_size:
            raise ValueError(
                f"Converted DDS payload is {len(linear)} bytes; expected {required_linear_size}"
            )
        linear_offset = 0
        for mip in range(original_mips):
            mip_width = max(original_width >> mip, 1)
            mip_height = max(original_height >> mip, 1)
            columns = _align_up(mip_width, block_width) // block_width
            rows = _align_up(mip_height, block_height) // block_height
            mip_linear_size = columns * rows * bytes_per_block
            if _ps5_swizzle_native(
                    linear[linear_offset:linear_offset + mip_linear_size],
                    payload,
                    offsets[mip],
                    columns,
                    rows,
                    bytes_per_block,
                ):
                pass
            else:
                for block_y in range(rows):
                    for block_x in range(columns):
                        source = linear_offset + (block_y * columns + block_x) * bytes_per_block
                        destination = offsets[mip] + _ps5_tiled_offset(
                            block_x, block_y, columns, bytes_per_block
                        )
                        payload[destination:destination + bytes_per_block] = linear[
                            source:source + bytes_per_block
                        ]
            linear_offset += mip_linear_size
        expected = (original_width, original_height, original_mips, expected_dxgi)
    else:
        info = _ps4_gnf_info(original_gnf)
        payload_parts = []
        linear_offset = 0
        for mip in range(info["mips"]):
            mip_width = _align_up(max(info["width"] >> mip, info["pixel_block"]), info["pixel_block"])
            mip_height = _align_up(max(info["height"] >> mip, info["pixel_block"]), info["pixel_block"])
            padded_width = max(_round_up_power_of_two(mip_width), 32)
            padded_height = max(_round_up_power_of_two(mip_height), 32)
            padded = bytearray(padded_width * padded_height * info["bpp"] // 8)
            row_size = mip_width * info["pixel_block"] * info["bpp"] // 8
            padded_row = padded_width * info["pixel_block"] * info["bpp"] // 8
            for row in range(mip_height // info["pixel_block"]):
                padded[row * padded_row:row * padded_row + row_size] = linear[
                    linear_offset:linear_offset + row_size
                ]
                linear_offset += row_size
            payload_parts.append(_ps4_swizzle(
                padded, padded_width, padded_height, info["bpp"], info["pixel_block"]
            ))
        if linear_offset != len(linear):
            raise ValueError(
                f"Converted DDS payload is {len(linear)} bytes; expected {linear_offset}"
            )
        payload = b"".join(payload_parts)
        payload_start = 0x100
        data_size = info["data_size"]
        expected = (info["width"], info["height"], info["mips"], info["dxgi"])

    if (width, height, mip_count, dxgi_format) != expected:
        raise ValueError("Converted DDS does not match the original dimensions, format, or mip count")
    if len(payload) != data_size:
        raise ValueError(f"Converted payload is {len(payload)} bytes; expected exactly {data_size}")
    result = bytearray(original_gnf)
    result[payload_start:payload_start + data_size] = payload
    return bytes(result)


def _ps5_payload_layout(width, height, mip_count, bytes_per_block, block_width, block_height):
    sizes = []
    for mip in range(mip_count):
        columns = _align_up(max(width >> mip, 1), block_width) // block_width
        rows = _align_up(max(height >> mip, 1), block_height) // block_height
        micro_width = 8 if bytes_per_block == 8 else 4 if bytes_per_block == 16 else 8
        sizes.append(_align_up(((columns + micro_width - 1) // micro_width) * rows * micro_width * bytes_per_block, 256))
    tail_start = mip_count - 1
    for mip in range(mip_count):
        if max(max(width >> mip, 1), max(height >> mip, 1)) <= 512:
            tail_start = mip
            break
    offsets = [0] * mip_count
    offset = 0x200 if bytes_per_block == 16 else 0x100
    for mip in range(mip_count - 1, tail_start - 1, -1):
        if offset and sizes[mip] >= 0x400:
            offset = _align_up(offset, min(sizes[mip], 0x1000))
        offsets[mip] = offset
        offset += sizes[mip]
    offset = _align_up(offset, 0x1000)
    for mip in range(tail_start - 1, -1, -1):
        offsets[mip] = offset
        offset += sizes[mip]
    return sizes, offsets


def _unique_path(path):
    if not os.path.exists(path):
        return path
    base, extension = os.path.splitext(path)
    index = 1
    while os.path.exists(f"{base}_{index}{extension}"):
        index += 1
    return f"{base}_{index}{extension}"
