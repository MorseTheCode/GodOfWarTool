import os
import struct
import ctypes
import shutil
from ctypes import c_int, c_void_p, c_size_t, POINTER, c_ubyte

OODLE_DLL_NAME = "oo2core_7_win64.dll"

class CompressionManager:
    _oodle_handle = None
    _decompress_func = None

    @staticmethod
    def get_dll_path():
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(script_dir, OODLE_DLL_NAME)

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

class UnifiedController:
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
            return UnifiedController.extract_texpack(container_path, entry, out_dir)
            
        try:
            final_data = UnifiedController.read_file_data(container_path, entry)
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