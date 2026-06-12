import customtkinter as ctk
from tkinter import messagebox, Toplevel, Menu, ttk
import os
import sys
import threading
import re
import struct
import json
import shutil
import binascii
import datetime
import ctypes
from collections import Counter
import tempfile
import subprocess 
from gow_unified_backend import UnifiedController, CompressionManager, Gow2018_Wad, Gow2018_Sbp

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False
    print("tkinterdnd2 not found. Drag and drop will be disabled.")

try:
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(app_dir)
    sys.path.append(app_dir)
except:
    pass

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

COLOR_BG = "#1a1a1a"
COLOR_SIDEBAR = "#212121"
COLOR_ACCENT = "#7B1E1E"
COLOR_ACCENT_HOVER = "#581212"
COLOR_BTN_NORMAL = "#2b2b2b"
COLOR_BTN_HOVER = "#3a3a3a"
COLOR_RED = "#C0392B"
COLOR_RED_HOVER = "#922B21"
COLOR_TITLE_BAR = "#1f1f1f"

# --- CUSTOM FONT CONFIGURATION ---
APP_FONT_FILE = "Berserker.ttf"  
APP_FONT_FAMILY = "Berserker"      

RECENT_FILES_JSON = "recent_files.json"

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- NATIVE AUDIO PLAYER (MCI) ---
class NativeAudioPlayer:
    def __init__(self):
        self.alias = "gow_audio_tool_player"
        self.winmm = ctypes.windll.winmm
        self.is_playing = False

    def _send(self, cmd):
        buffer = ctypes.create_unicode_buffer(255)
        error_code = self.winmm.mciSendStringW(cmd, buffer, 255, 0)
        return error_code, buffer.value

    def load(self, path):
        self.close()
        path = os.path.abspath(path)
        self._send(f'open "{path}" type waveaudio alias {self.alias}')
        self._send(f'set {self.alias} time format ms')

    def play(self):
        self._send(f'play {self.alias}')
        self.is_playing = True

    def pause(self):
        self._send(f'pause {self.alias}')
        self.is_playing = False

    def resume(self):
        self._send(f'resume {self.alias}')
        self.is_playing = True

    def close(self):
        self._send(f'close {self.alias}')
        self.is_playing = False

    def get_length(self):
        _, val = self._send(f'status {self.alias} length')
        return int(val) if val and val.isdigit() else 0

    def get_position(self):
        _, val = self._send(f'status {self.alias} position')
        return int(val) if val and val.isdigit() else 0

    def set_position(self, ms):
        state_cmd = f'play {self.alias}' if self.is_playing else ''
        self._send(f'seek {self.alias} to {ms}')
        if self.is_playing:
            self._send(f'play {self.alias}')

class CustomMessageBox(ctk.CTkToplevel):
    def __init__(self, title, message, is_error=False):
        super().__init__()
        self.title(title)
        self.geometry("400x200")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        
        icon_file = "icon6.ico" if is_error else "icon5.ico"
        try:
            self.after(200, lambda: self.iconbitmap(resource_path(icon_file)))
        except:
            pass
        
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - 400) // 2
        y = (sh - 200) // 2
        self.geometry(f"+{x}+{y}")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        icon_color = COLOR_RED if is_error else "#2ECC71"
        icon_text = "❌ Error" if is_error else "✅ Success"
        if title == "Done": icon_text = "✅ Done" 
        
        lbl_title = ctk.CTkLabel(self, text=icon_text, font=("Roboto", 20, "bold"), text_color=icon_color)
        lbl_title.grid(row=0, column=0, pady=(20, 10), sticky="ew")

        lbl_msg = ctk.CTkLabel(self, text=message, font=("Roboto", 13), wraplength=350)
        lbl_msg.grid(row=1, column=0, padx=20, pady=10, sticky="nsew")

        btn_ok = ctk.CTkButton(self, text="OK", command=self.destroy, 
                               fg_color=COLOR_BTN_NORMAL, hover_color=COLOR_BTN_HOVER, width=100)
        btn_ok.grid(row=2, column=0, pady=20)

        self.grab_set()
        self.wait_window()

class CustomFileDialog(ctk.CTkToplevel):
    def __init__(self, parent, title="Select File", mode="open", initial_dir=None, filetypes=None, initial_file=""):
        super().__init__(parent)
        self.title(title)
        self.geometry("850x550")
        self.mode = mode 
        self.filetypes = filetypes if filetypes else [("All Files", "*")]
        self.initial_file = initial_file
        self.result = None
        
        try:
            self.after(200, lambda: self.iconbitmap(resource_path("icon7.ico")))
        except:
            pass

        if initial_dir and os.path.exists(initial_dir):
            self.current_dir = os.path.abspath(initial_dir)
        else:
            self.current_dir = os.getcwd()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        
        if os.name == 'nt':
            drives = [f"{d}:\\" for d in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(f"{d}:")]
            self.drive_menu = ctk.CTkOptionMenu(top_frame, values=drives, width=70, command=self.change_drive,
                                                fg_color=COLOR_BTN_NORMAL, button_color=COLOR_BTN_NORMAL, button_hover_color=COLOR_BTN_HOVER)
            current_drive = os.path.splitdrive(self.current_dir)[0] + "\\"
            if current_drive in drives: self.drive_menu.set(current_drive)
            self.drive_menu.pack(side="left", padx=(0, 5))

        self.btn_up = ctk.CTkButton(top_frame, text="⬆", width=30, command=self.go_up,
                                    fg_color=COLOR_BTN_NORMAL, hover_color=COLOR_BTN_HOVER)
        self.btn_up.pack(side="left", padx=(0, 5))
        
        self.path_entry = ctk.CTkEntry(top_frame, height=30)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.path_entry.bind("<Return>", self.on_path_entry)
        
        ctk.CTkButton(top_frame, text="Go", width=40, command=self.on_path_entry,
                      fg_color=COLOR_BTN_NORMAL, hover_color=COLOR_BTN_HOVER).pack(side="left")
        
        ctk.CTkButton(top_frame, text="New Folder", width=80, command=self.new_folder,
                      fg_color=COLOR_BTN_NORMAL, hover_color=COLOR_BTN_HOVER).pack(side="left", padx=(5, 0))

        tree_frame = ctk.CTkFrame(self, fg_color="transparent")
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        
        style = ttk.Style()
        style.theme_use("clam")
        
        style.configure("Treeview", 
                        background="#2b2b2b", 
                        foreground="white", 
                        fieldbackground="#2b2b2b", 
                        borderwidth=0,
                        relief="flat",
                        rowheight=25,
                        font=("Roboto", 11))
        
        style.map("Treeview", background=[("selected", COLOR_ACCENT)])
        
        style.configure("Treeview.Heading", 
                        background="#1f1f1f", 
                        foreground="white", 
                        relief="flat")
        
        style.map("Treeview.Heading",
                  background=[('active', '#3a3a3a')], 
                  foreground=[('active', 'white')])
        
        self.tree = ttk.Treeview(tree_frame, columns=("size", "date"), selectmode="extended" if mode == "open_multiple" else "browse")
        self.tree.heading("#0", text="Name", anchor="w")
        self.tree.heading("size", text="Size", anchor="w")
        self.tree.heading("date", text="Date Modified", anchor="w")
        self.tree.column("#0", width=450)
        self.tree.column("size", width=100)
        self.tree.column("date", width=150)
        
        self.tree.pack(side="left", fill="both", expand=True)
        
        scrollbar = ctk.CTkScrollbar(tree_frame, orientation="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        bot_frame = ctk.CTkFrame(self, fg_color="transparent")
        bot_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        
        ctk.CTkLabel(bot_frame, text="File name:").pack(side="left")
        self.filename_entry = ctk.CTkEntry(bot_frame)
        self.filename_entry.pack(side="left", padx=10, fill="x", expand=True)
        if initial_file: self.filename_entry.insert(0, initial_file)
        
        if mode != "directory":
            self.type_map = {name: pat for name, pat in self.filetypes}
            type_labels = [name for name, pat in self.filetypes]
            self.type_menu = ctk.CTkOptionMenu(bot_frame, values=type_labels, command=lambda _: self.refresh_list(), width=150,
                                               fg_color=COLOR_BTN_NORMAL, button_color=COLOR_BTN_NORMAL, button_hover_color=COLOR_BTN_HOVER)
            self.type_menu.pack(side="left", padx=10)
        
        action_text = "Save" if mode == "save" else ("Select Folder" if mode == "directory" else "Open")
        ctk.CTkButton(bot_frame, text=action_text, command=self.confirm, fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER).pack(side="right")
        ctk.CTkButton(bot_frame, text="Cancel", command=self.destroy, fg_color="transparent", border_width=1, width=80).pack(side="right", padx=10)

        self.after(10, self.center_window)
        
        self.refresh_list()
        
        self.grab_set()
        self.wait_window()

    def center_window(self):
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            x = (sw - 850) // 2
            y = (sh - 550) // 2
            self.geometry(f"+{x}+{y}")
        except: pass

    def change_drive(self, drive):
        if os.path.exists(drive):
            self.current_dir = drive
            self.refresh_list()

    def go_up(self):
        parent = os.path.dirname(self.current_dir)
        if parent and os.path.exists(parent):
            self.current_dir = parent
            self.refresh_list()

    def on_path_entry(self, event=None):
        path = self.path_entry.get()
        if os.path.exists(path) and os.path.isdir(path):
            self.current_dir = path
            self.refresh_list()

    def new_folder(self):
        name = ctk.CTkInputDialog(text="Folder Name:", title="New Folder").get_input()
        if name:
            try:
                os.mkdir(os.path.join(self.current_dir, name))
                self.refresh_list()
            except Exception as e:
                print(e)

    def refresh_list(self, event=None):
        self.path_entry.delete(0, "end")
        self.path_entry.insert(0, self.current_dir)
        
        self.tree.delete(*self.tree.get_children())
        
        try:
            entries = os.scandir(self.current_dir)
        except PermissionError:
            return

        dirs = []
        files = []
        
        pattern_str = "*"
        if self.mode != "directory" and hasattr(self, 'type_menu'):
            selection = self.type_menu.get()
            pattern_str = self.type_map.get(selection, "*")

        patterns = pattern_str.split() 
        clean_exts = []
        for p in patterns:
            if p == "*" or p == "*.*":
                clean_exts = ["*"] 
                break
            clean_exts.append(p.lstrip("*").lower()) 

        for entry in entries:
            try:
                if entry.is_dir():
                    dirs.append(entry)
                elif self.mode != "directory":
                    if clean_exts[0] == "*":
                        files.append(entry)
                    else:
                        name_lower = entry.name.lower()
                        for ext in clean_exts:
                            if name_lower.endswith(ext):
                                files.append(entry)
                                break
            except: pass
            
        dirs.sort(key=lambda e: e.name.lower())
        files.sort(key=lambda e: e.name.lower())
        
        for d in dirs:
            ts = datetime.datetime.fromtimestamp(d.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
            self.tree.insert("", "end", text="📁 " + d.name, values=("", ts), tags=("dir", d.path))
            
        if self.mode != "directory":
            for f in files:
                size_str = self.format_bytes(f.stat().st_size)
                ts = datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
                self.tree.insert("", "end", text="📄 " + f.name, values=(size_str, ts), tags=("file", f.path))

    def format_bytes(self, size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def on_double_click(self, event):
        item_id = self.tree.selection()[0]
        tags = self.tree.item(item_id, "tags")
        path = tags[1]
        
        if "dir" in tags:
            self.current_dir = path
            self.refresh_list()
        else:
            if self.mode != "directory":
                self.filename_entry.delete(0, "end")
                self.filename_entry.insert(0, os.path.basename(path))
                self.confirm()

    def on_select(self, event):
        sel = self.tree.selection()
        if not sel: return
        tags = self.tree.item(sel[0], "tags")
        if "file" in tags:
            self.filename_entry.delete(0, "end")
            self.filename_entry.insert(0, os.path.basename(tags[1]))

    def confirm(self):
        if self.mode == "directory":
            self.result = self.current_dir
        elif self.mode == "save":
            name = self.filename_entry.get()
            if name:
                self.result = os.path.join(self.current_dir, name)
        elif self.mode == "open":
            name = self.filename_entry.get()
            if name:
                self.result = os.path.join(self.current_dir, name)
        elif self.mode == "open_multiple":
            selection = self.tree.selection()
            paths = []
            for item in selection:
                tags = self.tree.item(item, "tags")
                if "file" in tags:
                    paths.append(tags[1])
            if paths:
                self.result = paths
            else:
                name = self.filename_entry.get()
                if name: self.result = [os.path.join(self.current_dir, name)]

        if self.result:
            self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()

class FloatingMenu(ctk.CTkToplevel):
    def __init__(self, master, x, y, options):
        super().__init__(master)
        self.overrideredirect(True) 
        self.attributes("-topmost", True)
        
        self.frame = ctk.CTkFrame(self, fg_color="#2b2b2b", border_width=1, border_color="#444", corner_radius=4)
        self.frame.pack(fill="both", expand=True)

        for item in options:
            if item == "-":
                ctk.CTkFrame(self.frame, height=2, fg_color="#444").pack(fill="x", padx=5, pady=4)
            else:
                label, command = item
                btn = ctk.CTkButton(
                    self.frame, 
                    text=label, 
                    command=lambda c=command: self._on_click(c),
                    fg_color="transparent", 
                    hover_color=COLOR_BTN_HOVER,
                    anchor="w", 
                    height=32, 
                    text_color="#eee", 
                    font=("Roboto", 12)
                )
                btn.pack(fill="x", padx=2, pady=1)

        self.update_idletasks()
        width = self.frame.winfo_reqwidth() + 20 
        height = self.frame.winfo_reqheight()
        
        if y + height > self.winfo_screenheight() - 40:
            y -= height 

        self.geometry(f"+{x}+{y}")
        
        self.grab_set() 
        self.focus_force()
        self.bind("<Escape>", lambda e: self.destroy())
        self.bind("<Button-1>", self._check_click_outside)

    def _on_click(self, cmd):
        self.destroy()
        if cmd: cmd()

    def _check_click_outside(self, event):
        x, y = event.x, event.y
        w, h = self.winfo_width(), self.winfo_height()
        if not (0 <= x <= w and 0 <= y <= h):
            self.destroy()

class TypeSelectionDialog(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.selection = None
        self.title("Unknown File Type")
        self.geometry("450x180")
        self.resizable(False, False)
        
        self.update_idletasks()
        try:
            x = parent.winfo_x() + (parent.winfo_width() // 2) - 225
            y = parent.winfo_y() + (parent.winfo_height() // 2) - 90
            self.geometry(f"+{x}+{y}")
        except:
            pass
        
        try:
            self.after(200, lambda: self.iconbitmap(resource_path("icon4.ico")))
        except:
            pass
        
        ctk.CTkLabel(self, text="The file has no extension.", font=("Roboto Medium", 16)).pack(pady=(20, 5))
        ctk.CTkLabel(self, text="Please select the correct type:", font=("Roboto", 12), text_color="gray").pack(pady=(0, 20))
        
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20)
        
        ctk.CTkButton(btn_frame, text="WAD\n(Archive)", font=("Roboto", 12, "bold"), height=50, width=100,
                      fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
                      command=lambda: self.on_select("WAD")).pack(side="left", padx=5, expand=True)
        
        ctk.CTkButton(btn_frame, text="TEXPACK\n(Textures)", font=("Roboto", 12, "bold"), height=50, width=100,
                      fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
                      command=lambda: self.on_select("TEXPACK")).pack(side="left", padx=5, expand=True)

        ctk.CTkButton(btn_frame, text="SBP/BNK\n(Audio)", font=("Roboto", 12, "bold"), height=50, width=100,
                      fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
                      command=lambda: self.on_select("SBP")).pack(side="left", padx=5, expand=True)
        
        self.transient(parent)
        self.grab_set()
        self.focus_force()

    def on_select(self, type_str):
        self.selection = type_str
        self.destroy()

class RegexBuilderDialog(ctk.CTkToplevel):
    def __init__(self, parent, entry_widget):
        super().__init__(parent)
        self.title("Regex Builder")
        self.geometry("300x450")
        self.entry_widget = entry_widget
        self.attributes("-topmost", True)
        
        self.update_idletasks()
        try:
            x = parent.winfo_rootx() + 50
            y = parent.winfo_rooty() + 50
            self.geometry(f"+{x}+{y}")
        except:
            pass
        
        try:
            self.after(200, lambda: self.iconbitmap(resource_path("icon3.ico")))
        except:
            pass

        ctk.CTkLabel(self, text="Select Pattern to Append:", font=("Roboto", 14, "bold")).pack(pady=10)
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=5)

        patterns = [
            ("Any Character", "."), ("Any Digit (0-9)", "\\d"), ("Any Word Character", "\\w"),
            ("Whitespace", "\\s"), ("Start of Line", "^"), ("End of Line", "$"),
            ("Zero or more (*)", "*"), ("One or more (+)", "+"), ("Group (...)", "()"),
            ("Or ( | )", "|"), ("Range [A-Z]", "[A-Z]"), ("Range [a-z]", "[a-z]"), ("Range [0-9]", "[0-9]")
        ]

        for name, code in patterns:
            ctk.CTkButton(scroll, text=f"{name}  [ {code} ]", 
                          command=lambda c=code: self.append_pattern(c),
                          fg_color=COLOR_BTN_NORMAL, hover_color=COLOR_BTN_HOVER, anchor="w").pack(fill="x", pady=2)

    def append_pattern(self, pattern):
        current_pos = self.entry_widget.index("insert")
        self.entry_widget.insert(current_pos, pattern)
        if pattern == "()":
            self.entry_widget.icursor(current_pos + 1)
        self.focus_force()

class HexViewerWindow(ctk.CTkToplevel):
    def __init__(self, parent, file_entry, file_data):
        super().__init__(parent)
        self.title(f"Hex View - {file_entry.name}")
        self.geometry("900x600")
        self.file_data = file_data 
        
        try:
            self.after(200, lambda: self.iconbitmap(resource_path("icon2.ico")))
        except:
            pass

        self.toolbar = ctk.CTkFrame(self, height=40, fg_color="transparent")
        self.toolbar.pack(fill="x", padx=10, pady=(10, 0))

        self.edit_var = ctk.BooleanVar(value=False)
        self.chk_edit = ctk.CTkCheckBox(self.toolbar, text="Edit Mode", variable=self.edit_var, command=self.toggle_edit, font=("Roboto", 12))
        self.chk_edit.pack(side="left")

        self.full_var = ctk.BooleanVar(value=False)
        self.chk_full = ctk.CTkCheckBox(self.toolbar, text="Show Entire File", variable=self.full_var, command=self.refresh_view, font=("Roboto", 12))
        self.chk_full.pack(side="left", padx=15)

        self.textbox = ctk.CTkTextbox(self, font=("Courier New", 12), wrap="none")
        self.textbox.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.load_hex(file_data)
        self.textbox.configure(state="disabled")

    def toggle_edit(self):
        if self.edit_var.get():
            self.textbox.configure(state="normal")
        else:
            self.textbox.configure(state="disabled")

    def refresh_view(self):
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.load_hex(self.file_data)
        if not self.edit_var.get():
            self.textbox.configure(state="disabled")

    def load_hex(self, data):
        limit = 50 * 1024
        
        if self.full_var.get():
            display_data = data
        else:
            display_data = data[:limit]
        
        lines = []
        for i in range(0, len(display_data), 16):
            chunk = display_data[i:i+16]
            hex_part = " ".join(f"{b:02X}" for b in chunk)
            ascii_part = "".join((chr(b) if 32 <= b < 127 else ".") for b in chunk)
            lines.append(f"{i:08X}  {hex_part:<48}  |{ascii_part}|")
        
        if not self.full_var.get() and len(data) > limit:
            lines.append(f"\n... (Output truncated, showing first {limit/1024:.1f} KB of {len(data)/1024:.1f} KB) ...")

        self.textbox.insert("1.0", "\n".join(lines))

class TextEditorWindow(ctk.CTkToplevel):
    def __init__(self, parent, file_entry, file_data, wad_path, modifications_dict, container):
        super().__init__(parent)
        self.title(f"Editor - {file_entry.name}")
        self.geometry("950x700")
        self.entry = file_entry
        self.wad_path = wad_path
        self.parent_app = parent
        self.modifications_dict = modifications_dict
        self.container = container
        
        self.last_search_query = None
        self.last_search_regex = None
        self.last_search_case = None
        self.total_matches = 0
        
        try:
            self.after(200, lambda: self.iconbitmap(resource_path("icon2.ico")))
        except:
            pass
        
        self.toolbar = ctk.CTkFrame(self, height=50, fg_color=COLOR_SIDEBAR)
        self.toolbar.pack(fill="x", padx=10, pady=10)
        
        btn_frame_left = ctk.CTkFrame(self.toolbar, fg_color="transparent")
        btn_frame_left.pack(side="left", padx=10)

        ctk.CTkButton(btn_frame_left, text="Force Calc Header", command=self.calculate_header, width=120,
                      fg_color=COLOR_BTN_NORMAL, hover_color=COLOR_BTN_HOVER).pack(side="left", padx=5)
        
        ctk.CTkButton(btn_frame_left, text="Save", command=self.save_memory, width=120,
                      fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER).pack(side="left", padx=5)

        self.btn_repack = ctk.CTkButton(self.toolbar, text="Inject to File", command=self.save_sequence,
                      fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER)
        self.btn_repack.pack(side="right", padx=10, pady=10)

        self.chk_backup_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(self.toolbar, text="Backup", variable=self.chk_backup_var, 
                        font=("Roboto", 11), width=0, checkbox_width=18, checkbox_height=18,
                        fg_color=COLOR_ACCENT).pack(side="right", padx=5)

        self.lbl_status = ctk.CTkLabel(self.toolbar, text="", font=("Roboto", 11), text_color="#AAAAAA")
        self.lbl_status.pack(side="right", padx=10)

        self.search_frame = ctk.CTkFrame(self, height=50, fg_color="#2b2b2b", corner_radius=8, border_width=1, border_color="#444")
        ctk.CTkLabel(self.search_frame, text="Find:", font=("Roboto", 12, "bold"), text_color="#aaa").pack(side="left", padx=(15, 5))
        self.search_entry = ctk.CTkEntry(self.search_frame, placeholder_text="Type to search...", width=220, border_width=0, fg_color="#1a1a1a")
        self.search_entry.pack(side="left", padx=5, pady=8)
        self.search_entry.bind("<Return>", self.find_next)
        
        self.lbl_results = ctk.CTkLabel(self.search_frame, text="", font=("Roboto", 11), text_color="gray", width=60)
        self.lbl_results.pack(side="left", padx=5)

        self.btn_find_prev = ctk.CTkButton(self.search_frame, text="▲", width=30, height=28, command=self.find_prev, fg_color="#333", hover_color="#444")
        self.btn_find_prev.pack(side="left", padx=2)
        self.btn_find_next = ctk.CTkButton(self.search_frame, text="▼", width=30, height=28, command=self.find_next, fg_color="#333", hover_color="#444")
        self.btn_find_next.pack(side="left", padx=2)
        
        ctk.CTkFrame(self.search_frame, width=1, height=20, fg_color="#444").pack(side="left", padx=10)

        self.match_case_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self.search_frame, text="Aa", variable=self.match_case_var, width=0, checkbox_width=18, checkbox_height=18, font=("Roboto", 11)).pack(side="left", padx=5)
        
        self.regex_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(self.search_frame, text="RegEx", variable=self.regex_var, width=0, checkbox_width=18, checkbox_height=18, font=("Roboto", 11), command=self.toggle_regex_ui).pack(side="left", padx=10)
        
        self.btn_regex_build = ctk.CTkButton(self.search_frame, text="🔨", width=30, height=24, command=self.open_regex_builder, fg_color="#444", hover_color="#555", state="disabled")
        self.btn_regex_build.pack(side="left", padx=2)

        ctk.CTkButton(self.search_frame, text="✕", width=30, height=28, command=self.hide_search, fg_color="transparent", hover_color=COLOR_RED, text_color="gray").pack(side="right", padx=10)

        self.textbox = ctk.CTkTextbox(self, font=("Consolas", 14), wrap="none", undo=True)
        self.textbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.textbox._textbox.tag_config("search_highlight", background=COLOR_ACCENT, foreground="white")
        
        try:
            text_content = file_data.decode("utf-8", errors="ignore")
            text_content = text_content.replace("\r\n", "\n").replace("\r", "\n")
            self.textbox.insert("1.0", text_content)
        except Exception as e:
            self.textbox.insert("1.0", f"Error decoding file: {e}")
            self.textbox.configure(state="disabled")

        self.bind("<Control-f>", self.show_search)
        self.textbox._textbox.bind("<Control-f>", self.show_search)
        self.bind("<Escape>", self.hide_search)
        self.bind("<Control-s>", lambda e: self.save_memory())

        self.after(100, lambda: self.lift())
        self.after(100, lambda: self.focus_force())

    def toggle_regex_ui(self):
        if self.regex_var.get():
            self.btn_regex_build.configure(state="normal", fg_color=COLOR_ACCENT)
        else:
            self.btn_regex_build.configure(state="disabled", fg_color="#444")

    def open_regex_builder(self):
        RegexBuilderDialog(self, self.search_entry)

    def show_search(self, event=None):
        self.search_frame.pack(before=self.textbox, fill="x", padx=10, pady=(0, 5))
        self.search_entry.focus_set()

    def hide_search(self, event=None):
        self.textbox._textbox.tag_remove("search_highlight", "1.0", "end")
        self.search_frame.pack_forget()
        self.textbox.focus_set()

    def find_next(self, event=None):
        self.search_text(forward=True)

    def find_prev(self):
        self.search_text(forward=False)

    def update_match_count(self, search_str, nocase, use_regex):
        if (search_str == self.last_search_query and use_regex == self.last_search_regex and nocase == self.last_search_case):
            return self.total_matches
        
        text_widget = self.textbox._textbox
        count = 0
        start_index = "1.0"
        while True:
            pos = text_widget.search(search_str, start_index, stopindex="end", nocase=nocase, regexp=use_regex)
            if not pos:
                break
            count += 1
            start_index = f"{pos}+1c"
            
        self.last_search_query = search_str
        self.last_search_regex = use_regex
        self.last_search_case = nocase
        self.total_matches = count
        
        if count > 1:
            self.lbl_results.configure(text=f"{count} matches")
        elif count == 1:
            self.lbl_results.configure(text="1 match")
        else:
            self.lbl_results.configure(text="No matches")
        return count

    def search_text(self, forward=True):
        text_widget = self.textbox._textbox
        search_str = self.search_entry.get()
        if not search_str: 
            self.lbl_results.configure(text="")
            return
        
        nocase = not self.match_case_var.get()
        use_regex = self.regex_var.get()
        
        if use_regex:
            try:
                re.compile(search_str)
            except:
                return

        self.update_match_count(search_str, nocase, use_regex)
        start_pos = text_widget.index("insert")
        text_widget.tag_remove("search_highlight", "1.0", "end")
        
        found_pos = text_widget.search(search_str, start_pos + "+1c" if forward else start_pos, 
                                     stopindex="end" if forward else "1.0", backwards=not forward, 
                                     nocase=nocase, regexp=use_regex)
        
        if not found_pos:
            found_pos = text_widget.search(search_str, "1.0" if forward else "end", 
                                         stopindex=start_pos, backwards=not forward, 
                                         nocase=nocase, regexp=use_regex)
        
        if found_pos:
            count_var = ctk.StringVar()
            text_widget.search(search_str, found_pos, stopindex="end", nocase=nocase, regexp=use_regex, count=count_var)
            
            try:
                match_len = int(count_var.get())
            except:
                match_len = len(search_str) if not use_regex else 1
            
            if match_len == 0: match_len = 1
            end_pos = f"{found_pos}+{match_len}c"
            
            text_widget.tag_add("search_highlight", found_pos, end_pos)
            text_widget.mark_set("insert", end_pos if forward else found_pos)
            text_widget.see(found_pos)
        else:
            self.bell()

    def calculate_header(self):
        content = self.textbox.get("1.0", "end-1c").replace("\r", "")
        lines = content.splitlines()
        asterisk_pattern = r'\*(\d+)\*'
        type1_counter = Counter()
        type2_counter = Counter()
        found_ids = []
        total_type1_lines = 0
        total_type2_lines = 0
        current_line_count = 0
        current_type = None
        counting = False
        d_tag_count = 0

        for i, line in enumerate(lines):
            if "[[D:" in line: d_tag_count += 1
            match = re.search(asterisk_pattern, line)
            if match:
                found_ids.append(int(match.group(1)))
                if counting:
                    if current_type == 1:
                        type1_counter[current_line_count] += 1
                        total_type1_lines += current_line_count
                    else:
                        type2_counter[current_line_count] += 1
                        total_type2_lines += current_line_count
                current_line_count = 0
                counting = True
                current_type = 2 if (i + 1 < len(lines) and "[[S:" in lines[i+1]) else 1
                continue
            if counting and "[[S:" not in line: current_line_count += 1

        if counting:
            if current_type == 1:
                type1_counter[current_line_count] += 1
                total_type1_lines += current_line_count
            else:
                type2_counter[current_line_count] += 1
                total_type2_lines += current_line_count

        total_occur_sum = sum(type1_counter.values()) + sum(type2_counter.values())
        max_id = max(found_ids) if found_ids else 0
        new_header = f"{total_occur_sum} {(max_id - 100000) + 1} {d_tag_count} {(total_type1_lines + total_type2_lines) - d_tag_count}"
        self.textbox.delete("1.0", "2.0")
        self.textbox.insert("1.0", new_header + "\n")
        return new_header

    def save_memory(self):
        if self.entry.name == "MSGS_TXT":
            new_hdr = self.calculate_header()
            self.lbl_status.configure(text=f"Auto-Calc: {new_hdr}", text_color="#2ECC71")
        
        content = self.textbox.get("1.0", "end-1c")
        
        if self.entry.name == "MSGS_TXT":
            content = content.replace("\r\n", "\n").replace("\r", "\n")

        try:
            self.modifications_dict[self.entry.name] = content.encode("utf-8")
            self.lbl_status.configure(text="Saved to Memory (with Auto-Header)", text_color="#3498DB")
            self.after(3000, lambda: self.lbl_status.configure(text=""))
        except Exception as e:
            CustomMessageBox("Save Error", str(e), is_error=True)

    def save_sequence(self):
        self.save_memory()
        dialog = CustomFileDialog(self, title="Save Repacked WAD", mode="save", 
                                  filetypes=[("WAD Files", "*.wad")], 
                                  initial_file=os.path.basename(self.wad_path))
        if dialog.result:
            save_path = dialog.result
            do_backup = self.chk_backup_var.get()
            content = self.textbox.get("1.0", "end-1c")
            if self.entry.name == "MSGS_TXT":
                content = content.replace("\r\n", "\n").replace("\r", "\n")

            threading.Thread(target=self.run_save_task, args=(content, save_path, do_backup)).start()
            self.btn_repack.configure(state="disabled", text="Processing...")

    def run_save_task(self, new_text_content, save_path, do_backup):
        temp_dir = tempfile.mkdtemp()
        try:
            if do_backup:
                backup_path = self.wad_path + ".bak"
                try:
                    if not os.path.exists(backup_path):
                        shutil.copy2(self.wad_path, backup_path)
                except Exception as e:
                    print(f"Backup failed: {e}")

            true_idx = self.parent_app.scan_for_true_index(self.wad_path, self.entry.offset)
            
            if true_idx == -1:
                raise Exception("Could not find true file index in WAD structure.")

            clean_name = self.entry.name
            safe_name = clean_name.replace('/', '.').replace('\\', '.')
            target_filename = f"{safe_name}.{true_idx}.bin"
            target_path = os.path.join(temp_dir, target_filename)
            
            with open(target_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(new_text_content)
                
            success = UnifiedController.repack_wad(self.wad_path, temp_dir, save_path, None)
            
            if success:
                self.parent_app.after(0, lambda: CustomMessageBox("Success", f"WAD Repacked Successfully to:\n{os.path.basename(save_path)}"))
            else:
                self.parent_app.after(0, lambda: CustomMessageBox("Error", "Repack failed.", is_error=True))

        except Exception as e:
            print(e)
            self.parent_app.after(0, lambda: CustomMessageBox("Error", f"An error occurred: {e}", is_error=True))
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            self.parent_app.after(0, lambda: self.btn_repack.configure(state="normal", text="Inject to File"))

if HAS_DND:
    class GOWUnifiedApp(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self):
            super().__init__()
            self.TkdndVersion = TkinterDnD._require(self)
            self.init_app()
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<Drop>>', self.drop_file)
        
        def drop_file(self, event):
            raw_data = event.data
            if "{" in raw_data:
                paths = re.findall(r'\{(.*?)\}', raw_data)
            else:
                paths = raw_data.split()
            self.status_msg.set(f"Dropped {len(paths)} files...")
            self.process_file_list(paths)
else:
    class GOWUnifiedApp(ctk.CTk):
        def __init__(self):
            super().__init__()
            self.init_app()

def _shared_app_init(cls):
    def init_app(self):
        self.setup_custom_titlebar()
        self.geometry("1100x700")
        self.configure(fg_color=COLOR_BG)
        
        # Initialize drag coordinates
        self.x_pos = 0
        self.y_pos = 0
        
        # Audio Player Init
        self.audio_player = NativeAudioPlayer()
        self.audio_update_loop_running = False
        self.audio_zones = {} # Map entry.name to UI frame
        self.active_audio_widgets = {} # Stores references to active player widgets
        self.is_dragging_slider = False # Controls drag behavior
        self.current_playing_entry = None # Track current file for restoring state
        
        try:
            self.iconbitmap(resource_path("icon.ico"))
        except:
            pass

        self.open_containers = [] 
        self.active_idx = -1
        self.current_entries = []
        self.recent_files = self.load_recent_files()
        
        # New: Pagination Variables
        self.page_index = 0
        self.filtered_entries = []
        self.total_pages = 1
        self.items_per_page = 50
        
        self.status_msg = ctk.StringVar(value="Ready.")
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1) 
        
        self.bind_resize_events() 
        self.load_custom_font() # Load custom font if available

        self.create_sidebar()
        self.create_main_area()
        self.create_context_menu()
        self.check_system()

    def load_custom_font(self):
        if not APP_FONT_FILE: return
        
        font_path = os.path.join(app_dir, APP_FONT_FILE)
        if not os.path.exists(font_path): return
        
        try:
            # 0x10 = FR_PRIVATE (process-local font), 0x0 = reserved
            # Use abs path to be safe
            abs_path = os.path.abspath(font_path)
            ctypes.windll.gdi32.AddFontResourceExW(abs_path, 0x10, 0)
        except Exception as e:
            print(f"Error loading custom font: {e}")

    def bind_resize_events(self):
        self.bind("<Motion>", self.on_hover_resize)
        self.bind("<Button-1>", self.on_click_resize)
        self.bind("<ButtonRelease-1>", self.on_release_resize)
        self.bind("<B1-Motion>", self.on_drag_resize)
        self._resize_dir = None
        self._resize_margin = 8

    def on_hover_resize(self, event):
        x, y = event.x_root - self.winfo_rootx(), event.y_root - self.winfo_rooty()
        w, h = self.winfo_width(), self.winfo_height()
        m = self._resize_margin
        
        direction = ""
        if y < m: direction += "n"
        elif y > h - m: direction += "s"
        
        if x < m: direction += "w"
        elif x > w - m: direction += "e"
        
        self._resize_dir = direction
        
        if direction:
            # FIX: Use valid cross-platform cursor names
            if direction in ["nw", "se"]: cursor = "size_nw_se"
            elif direction in ["ne", "sw"]: cursor = "size_ne_sw"
            elif direction in ["n", "s"]: cursor = "size_ns"
            elif direction in ["w", "e"]: cursor = "size_we"
            else: cursor = ""
            
            if self.cget("cursor") != cursor:
                self.configure(cursor=cursor)
        else:
             if self.cget("cursor") != "arrow" and self.cget("cursor") != "":
                 self.configure(cursor="")

    def on_click_resize(self, event):
        if self._resize_dir:
            self._resize_start_x = event.x_root
            self._resize_start_y = event.y_root
            self._resize_start_w = self.winfo_width()
            self._resize_start_h = self.winfo_height()
            self._resize_start_geo_x = self.winfo_x()
            self._resize_start_geo_y = self.winfo_y()
            self._resizing = True
        else:
            self._resizing = False

    def on_drag_resize(self, event):
        if not getattr(self, "_resizing", False):
            return

        dx = event.x_root - self._resize_start_x
        dy = event.y_root - self._resize_start_y
        
        new_x, new_y = self._resize_start_geo_x, self._resize_start_geo_y
        new_w, new_h = self._resize_start_w, self._resize_start_h
        
        d = self._resize_dir
        
        if "e" in d: new_w += dx
        if "w" in d: 
            new_x += dx
            new_w -= dx
        if "s" in d: new_h += dy
        if "n" in d: 
            new_y += dy
            new_h -= dy
            
        if new_w < 400: new_w = 400
        if new_h < 300: new_h = 300
        
        self.geometry(f"{new_w}x{new_h}+{new_x}+{new_y}")

    def on_release_resize(self, event):
        self._resizing = False
        self.configure(cursor="")

    def setup_custom_titlebar(self):
        self.overrideredirect(True)
        self.after(10, self.set_appwindow) 
        self.title_bar = ctk.CTkFrame(self, height=30, fg_color=COLOR_TITLE_BAR, corner_radius=0)
        self.title_bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        
        title_lbl = ctk.CTkLabel(self.title_bar, text="God of War (2018) Asset Tool", font=("Roboto", 13, "bold"), text_color="#ccc")
        title_lbl.pack(side="left", padx=10)
        
        title_lbl.bind("<Button-1>", self.start_move)
        title_lbl.bind("<B1-Motion>", self.do_move)
        self.title_bar.bind("<Button-1>", self.start_move)
        self.title_bar.bind("<B1-Motion>", self.do_move)

        close_btn = ctk.CTkButton(self.title_bar, text="✕", width=40, height=30, command=self.quit, fg_color="transparent", hover_color="#C0392B", corner_radius=0)
        close_btn.pack(side="right")
        
        max_btn = ctk.CTkButton(self.title_bar, text="⬜", width=40, height=30, command=self.change_maximize_state, fg_color="transparent", hover_color="#333", corner_radius=0)
        max_btn.pack(side="right")
        
        min_btn = ctk.CTkButton(self.title_bar, text="─", width=40, height=30, command=self.minimize_window, fg_color="transparent", hover_color="#333", corner_radius=0)
        min_btn.pack(side="right")

    def set_appwindow(self):
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            style = style & ~0x00000080
            style = style | 0x00040000
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)
            self.withdraw()
            self.after(10, self.deiconify)
        except: pass

    def start_move(self, event):
        if getattr(self, "_resize_dir", ""): return
        self.x_pos = event.x
        self.y_pos = event.y

    def do_move(self, event):
        # Safety check for x_pos/y_pos
        if not hasattr(self, 'x_pos') or not hasattr(self, 'y_pos'):
            return
            
        deltax = event.x - self.x_pos
        deltay = event.y - self.y_pos
        x = self.winfo_x() + deltax
        y = self.winfo_y() + deltay
        self.geometry(f"+{x}+{y}")

    def minimize_window(self):
        self.overrideredirect(False)
        self.iconify()
        # Bind to <Map> instead of <FocusIn> to prevent immediate restoration
        self.bind("<Map>", self.on_deiconify)

    def on_deiconify(self, event):
        if self.state() == "normal":
            self.overrideredirect(True)
            self.unbind("<Map>")
            # Re-apply taskbar icon style
            self.set_appwindow() 

    def change_maximize_state(self):
        if self.state() == "zoomed":
            self.state("normal")
            self.overrideredirect(True)
        else:
            self.overrideredirect(False) 
            self.state("zoomed")
            self.overrideredirect(True)

    def load_recent_files(self):
        if os.path.exists(RECENT_FILES_JSON):
            try:
                with open(RECENT_FILES_JSON, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []

    def save_recent_files(self, new_path):
        if new_path in self.recent_files:
            self.recent_files.remove(new_path)
        self.recent_files.insert(0, new_path)
        self.recent_files = self.recent_files[:5]
        try:
            with open(RECENT_FILES_JSON, 'w') as f:
                json.dump(self.recent_files, f)
        except:
            pass

    def check_system(self):
        oodle = CompressionManager.load_oodle()
        self.lbl_sys_status.configure(text="● Oodle Library Active" if oodle else "● Oodle Library Missing", 
                                      text_color="#2ECC71" if oodle else "#E74C3C")

    def create_sidebar(self):
        self.sidebar = ctk.CTkFrame(self, width=250, corner_radius=0, fg_color=COLOR_SIDEBAR)
        self.sidebar.grid(row=1, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(12, weight=1)

        title_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        title_frame.grid(row=0, column=0, padx=20, pady=(30, 20), sticky="ew")
        ctk.CTkLabel(title_frame, text="GOW TOOL", font=(APP_FONT_FAMILY, 26, "bold"), text_color="white").pack(anchor="w")
        ctk.CTkLabel(title_frame, text="2018 EDITION", font=("Roboto", 10, "bold"), text_color="gray").pack(anchor="w")

        ctk.CTkFrame(self.sidebar, height=2, fg_color="#333333").grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 20))

        self.btn_load = self.create_nav_button(self.sidebar, "📂  Open Files", self.on_load_click, 3)
        
        self.btn_recent = ctk.CTkButton(
            self.sidebar, 
            text="🕒  Recent Files", 
            command=self.show_recent_menu,
            fg_color=COLOR_BTN_NORMAL, 
            hover_color=COLOR_BTN_HOVER, 
            font=("Roboto Medium", 13), 
            anchor="w", 
            height=30
        )
        self.btn_recent.grid(row=4, column=0, padx=15, pady=(0, 20), sticky="ew")

        ctk.CTkLabel(self.sidebar, text="EXTRACTION", font=("Roboto", 10, "bold"), text_color="#666666").grid(row=5, column=0, padx=25, pady=(10, 5), sticky="w")
        self.btn_extract_all = self.create_nav_button(self.sidebar, "⬇  Extract Current", self.extract_current_action, 6, state="disabled")
        self.btn_batch_extract = self.create_nav_button(self.sidebar, "📚  Batch Extract All", self.batch_extract_action, 7, state="disabled")

        ctk.CTkLabel(self.sidebar, text="MODDING", font=("Roboto", 10, "bold"), text_color="#666666").grid(row=8, column=0, padx=25, pady=(20, 5), sticky="w")
        
        self.btn_repack = self.create_nav_button(self.sidebar, "📦  Repack Folder", self.repack_action, 9, fg=COLOR_ACCENT, hover=COLOR_ACCENT_HOVER)
        
        self.btn_repack_current = self.create_nav_button(self.sidebar, "💾  Repack Current", self.repack_current_action, 10, state="disabled", fg=COLOR_ACCENT, hover=COLOR_ACCENT_HOVER)
        
        self.chk_backup_var = ctk.BooleanVar(value=True)
        self.chk_backup = ctk.CTkCheckBox(self.sidebar, text="Backup Original (.bak)", variable=self.chk_backup_var, 
                                          font=("Roboto", 11), text_color="#ccc", checkmark_color="white", fg_color=COLOR_ACCENT)
        self.chk_backup.grid(row=11, column=0, padx=25, pady=10, sticky="nw")

        self.lbl_sys_status = ctk.CTkLabel(self.sidebar, text="Checking...", font=("Roboto", 11), justify="left")
        self.lbl_sys_status.grid(row=13, column=0, padx=20, pady=(10, 0), sticky="sw")
        ctk.CTkLabel(self.sidebar, text="by Morse", font=("Roboto", 10), text_color="gray").grid(row=14, column=0, padx=20, pady=(2, 20), sticky="sw")

    def show_recent_menu(self):
        options = []
        if not self.recent_files:
            options.append(("No recent files", None))
        else:
            for path in self.recent_files:
                options.append((os.path.basename(path), lambda p=path: self.process_file_list([p])))
        
        x = self.btn_recent.winfo_rootx()
        y = self.btn_recent.winfo_rooty() + self.btn_recent.winfo_height() + 5
        FloatingMenu(self, x, y, options)

    def create_nav_button(self, parent, text, command, row, state="normal", fg=COLOR_BTN_NORMAL, hover=COLOR_BTN_HOVER):
        btn = ctk.CTkButton(parent, text=text, command=command, state=state, fg_color=fg, hover_color=hover, font=("Roboto Medium", 13), anchor="w", height=40, corner_radius=6)
        btn.grid(row=row, column=0, padx=15, pady=5, sticky="ew")
        return btn

    def create_main_area(self):
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=1, column=1, sticky="nsew")
        self.main_frame.grid_rowconfigure(5, weight=1) # Expanded weight for list
        self.main_frame.grid_columnconfigure(0, weight=1)

        self.tab_scroll = ctk.CTkScrollableFrame(self.main_frame, orientation="horizontal", height=50, fg_color="transparent")
        self.tab_scroll.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        self.tab_widgets = [] 

        self.search_container = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.search_container.grid(row=1, column=0, sticky="ew", padx=20, pady=(10, 0))
        
        self.entry_file_search = ctk.CTkEntry(self.search_container, placeholder_text="🔍 Filter files by name...", height=30, border_width=0, fg_color=COLOR_BTN_NORMAL)
        self.entry_file_search.pack(fill="x")
        self.entry_file_search.bind("<KeyRelease>", self.on_file_search)

        self.filter_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent", height=30)
        self.filter_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(5, 0))
        
        ctk.CTkLabel(self.filter_frame, text="Show:", font=("Roboto", 11, "bold"), text_color="gray").pack(side="left", padx=(0, 10))
        
        self.chk_txt_var = ctk.BooleanVar(value=True)
        self.chk_tex_var = ctk.BooleanVar(value=True)
        self.chk_audio_var = ctk.BooleanVar(value=True)  # New Audio Filter
        self.chk_bin_var = ctk.BooleanVar(value=True)
        
        ctk.CTkCheckBox(self.filter_frame, text="Text (MSGS)", variable=self.chk_txt_var, command=self.apply_filters, 
                        font=("Roboto", 11), height=20, checkbox_height=16, checkbox_width=16,
                        fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER).pack(side="left", padx=10)
        
        ctk.CTkCheckBox(self.filter_frame, text="Textures", variable=self.chk_tex_var, command=self.apply_filters, 
                        font=("Roboto", 11), height=20, checkbox_height=16, checkbox_width=16,
                        fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER).pack(side="left", padx=10)

        ctk.CTkCheckBox(self.filter_frame, text="Audio", variable=self.chk_audio_var, command=self.apply_filters, 
                        font=("Roboto", 11), height=20, checkbox_height=16, checkbox_width=16,
                        fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER).pack(side="left", padx=10)
        
        ctk.CTkCheckBox(self.filter_frame, text="Binary/Other", variable=self.chk_bin_var, command=self.apply_filters, 
                        font=("Roboto", 11), height=20, checkbox_height=16, checkbox_width=16,
                        fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER).pack(side="left", padx=10)

        # --- BATCH ACTIONS ROW ---
        self.batch_actions_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent", height=30)
        self.batch_actions_frame.grid(row=3, column=0, sticky="ew", padx=20, pady=(5, 0))

        ctk.CTkButton(self.batch_actions_frame, text="Select All", width=70, height=24, 
                      font=("Roboto", 11), fg_color="#444", hover_color="#555", 
                      command=self.select_all_files).pack(side="left", padx=(0, 5))
        
        ctk.CTkButton(self.batch_actions_frame, text="Deselect All", width=80, height=24, 
                      font=("Roboto", 11), fg_color="#444", hover_color="#555", 
                      command=self.deselect_all_files).pack(side="left", padx=5)

        self.btn_batch_replace = ctk.CTkButton(self.batch_actions_frame, text="Batch Replace Selected", width=140, height=24,
                                               font=("Roboto", 11, "bold"), fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
                                               command=self.batch_replace_selected)
        self.btn_batch_replace.pack(side="right", padx=5)
        # -------------------------

        self.file_list = ctk.CTkScrollableFrame(self.main_frame, label_text="  File Contents  ", label_font=("Roboto", 12, "bold"))
        self.file_list.grid(row=4, column=0, sticky="nsew", padx=20, pady=(10, 0)) # Less padding bottom
        self.file_list.grid_columnconfigure(0, weight=1) 

        # --- PAGINATION CONTROLS (NEW) ---
        self.pagination_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent", height=30)
        self.pagination_frame.grid(row=5, column=0, sticky="ew", padx=20, pady=(5, 5))
        
        self.btn_prev_page = ctk.CTkButton(self.pagination_frame, text="< Prev", width=80, command=self.prev_page, state="disabled", fg_color="#444", hover_color="#555")
        self.btn_prev_page.pack(side="left")
        
        self.lbl_page_info = ctk.CTkLabel(self.pagination_frame, text="", font=("Roboto", 11))
        self.lbl_page_info.pack(side="left", padx=20)
        
        self.btn_next_page = ctk.CTkButton(self.pagination_frame, text="Next >", width=80, command=self.next_page, state="disabled", fg_color="#444", hover_color="#555")
        self.btn_next_page.pack(side="left")
        # ---------------------------------

        self.status_bar_frame = ctk.CTkFrame(self.main_frame, height=30, fg_color=COLOR_SIDEBAR, corner_radius=0)
        self.status_bar_frame.grid(row=6, column=0, sticky="ew")
        
        ctk.CTkLabel(self.status_bar_frame, textvariable=self.status_msg, font=("Roboto", 11), text_color="gray").pack(side="left", padx=15, pady=5)
        
        # --- AUDIO CONTROLS (Stop, Slider, Time) ---
        self.audio_controls_frame = ctk.CTkFrame(self.status_bar_frame, fg_color="transparent")
        self.audio_controls_frame.pack(side="right", padx=10)

        self.lbl_audio_time = ctk.CTkLabel(self.audio_controls_frame, text="00:00 / 00:00", font=("Roboto Mono", 10), width=100)
        self.lbl_audio_time.pack(side="right", padx=5)

        self.audio_slider = ctk.CTkSlider(self.audio_controls_frame, from_=0, to=100, width=150, height=16, 
                                          progress_color=COLOR_ACCENT, button_color="white", button_hover_color="#ddd",
                                          command=self.seek_audio)
        self.audio_slider.set(0)
        self.audio_slider.pack(side="right", padx=5)

        self.btn_stop_audio = ctk.CTkButton(self.audio_controls_frame, text="◼", width=30, height=20, 
                                            font=("Roboto", 12, "bold"), fg_color="#444", hover_color="#C0392B", 
                                            command=self.stop_audio)
        self.btn_stop_audio.pack(side="right", padx=5)
        
        # Initially hide controls
        self.audio_controls_frame.pack_forget() 
        # -------------------------

        self.lbl_status_details = ctk.CTkLabel(self.status_bar_frame, text="", font=("Roboto Mono", 11), text_color="#888888")
        self.lbl_status_details.pack(side="right", padx=15, pady=5)

    def seek_audio(self, value):
        if hasattr(self, 'audio_player') and self.audio_player.is_playing:
            self.audio_player.set_position(int(value))

    def update_audio_progress(self):
        # 1. Check if audio loop should continue
        if not self.audio_update_loop_running:
            return

        # 2. Check player validity
        if not hasattr(self, 'audio_player'):
            self.stop_audio()
            return
            
        # 3. Check if strictly playing or valid
        try:
             # Basic check to ensure we don't spam if player crashed
             pos = self.audio_player.get_position()
             length = self.audio_player.get_length()
        except:
             # If getting position fails, likely closed
             self.stop_audio()
             return

        # Auto-stop if reached end (with small buffer)
        if length > 0 and pos >= length:
            self.stop_audio()
            return

        # Formata tempo 00:00
        def fmt_time(ms):
            s = ms // 1000
            m, s = divmod(s, 60)
            return f"{m:02d}:{s:02d}"

        time_str = f"{fmt_time(pos)} / {fmt_time(length)}"

        # 4. Safe UI Updates (Global)
        try:
            if self.lbl_audio_time.winfo_exists():
                self.lbl_audio_time.configure(text=time_str)
            
            if self.audio_slider.winfo_exists():
                if self.audio_slider.cget("to") != length and length > 0:
                     self.audio_slider.configure(to=length)
                
                if not self.is_dragging_slider:
                     if abs(self.audio_slider.get() - pos) > 500: # Threshold
                         self.audio_slider.set(pos)
        except Exception:
             pass # Ignore UI errors to keep loop alive if possible

        # 5. Safe UI Updates (Row-specific)
        if self.active_audio_widgets:
            try:
                # Label
                if 'lbl_time' in self.active_audio_widgets:
                    lbl = self.active_audio_widgets['lbl_time']
                    if lbl.winfo_exists():
                        lbl.configure(text=time_str)
                
                # Slider
                if 'slider' in self.active_audio_widgets:
                    row_slider = self.active_audio_widgets['slider']
                    if row_slider.winfo_exists():
                        # Update max if needed
                        if row_slider.cget("to") != length and length > 0:
                            row_slider.configure(to=length)
                        
                        # Update position if not dragging
                        if not self.is_dragging_slider:
                            row_slider.set(pos)
            except Exception:
                pass # Row widgets might be destroyed on page change, ignore.

        # 6. Schedule next update
        if self.audio_update_loop_running:
            self.after(100, self.update_audio_progress)

    def create_context_menu(self):
        self.selected_entry_for_context = None

    def show_context_menu(self, event, entry):
        self.selected_entry_for_context = entry
        
        options = [
            ("Open Text Editor", lambda: self.open_text_editor(self.selected_entry_for_context)),
            ("Open Hex Viewer", lambda: self.open_hex_viewer(self.selected_entry_for_context)),
            "-",
            ("Replace File", self.replace_file_context),
            ("Extract File", self.extract_file_context),
            "-",
            ("Copy Name", self.copy_name_context)
        ]
        
        FloatingMenu(self, event.x_root, event.y_root, options)

    def _find_wwise_console(self):
        """Locates WwiseConsole.exe based on environment or standard paths."""
        # 1. Env Var
        if "WWISEROOT" in os.environ:
            path = os.path.join(os.environ["WWISEROOT"], "Authoring", "x64", "Release", "bin", "WwiseConsole.exe")
            if os.path.exists(path): return path
            
        # 2. Program Files (x86) Crawl
        try:
            root_drive = os.environ.get("SystemDrive", "C:")
            x86 = os.environ.get("ProgramFiles(x86)", f"{root_drive}\\Program Files (x86)")
            ak_dir = os.path.join(x86, "Audiokinetic")
            
            if os.path.exists(ak_dir):
                # Find subfolders starting with Wwise
                dirs = [d for d in os.listdir(ak_dir) if d.startswith("Wwise")]
                dirs.sort(reverse=True) # Newest first hopefully
                
                for d in dirs:
                    path = os.path.join(ak_dir, d, "Authoring", "x64", "Release", "bin", "WwiseConsole.exe")
                    if os.path.exists(path): return path
        except: pass
        
        return None

    def _find_ffmpeg(self):
        """Locates ffmpeg.exe."""
        # 1. Check local folder or resource path
        search_paths = [app_dir, resource_path("."), os.path.join(app_dir, "ffmpeg", "bin")]
        for p in search_paths:
            exe = os.path.join(p, "ffmpeg.exe")
            if os.path.exists(exe): return exe
            
        # 2. Check PATH
        try:
            subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "ffmpeg"
        except: pass
        
        return None

    def _convert_with_wwise(self, wwise_console, ffmpeg_path, source_path):
        """Converts audio to WEM using FFmpeg (preprocess) + Wwise Console."""
        temp_dir = tempfile.mkdtemp()
        try:
            filename = os.path.basename(source_path)
            
            # --- 1. Preprocessing with FFmpeg ---
            # Converts any input (mp3, ogg, flac, etc.) to a standard WAV
            clean_wav_name = "temp_source.wav"
            clean_wav_path = os.path.join(temp_dir, clean_wav_name)
            
            self.status_msg.set("Preprocessing with FFmpeg (48kHz Mono)...")
            
            cmd_ffmpeg = [
                ffmpeg_path, 
                "-y", 
                "-hide_banner", 
                "-loglevel", "error", 
                "-i", source_path,
                "-ac", "1",       # Force Mono
                "-ar", "48000",   # Force 48kHz
                clean_wav_path
            ]
            
            subprocess.run(cmd_ffmpeg, startupinfo=self._get_startup_info(), check=True)
            
            if not os.path.exists(clean_wav_path):
                raise Exception("FFmpeg failed to create intermediate WAV.")

            # --- 2. Wwise Project Setup ---
            project_path = os.path.join(temp_dir, "TempProject", "TempProject.wproj")
            
            subprocess.run([wwise_console, "create-new-project", project_path, "--quiet"], 
                           cwd=temp_dir, startupinfo=self._get_startup_info(), check=True)
            
            # --- 3. Create Sources List ---
            sources_xml_path = os.path.join(temp_dir, "list.wsources")
            output_dir = os.path.join(temp_dir, "Output")
            os.makedirs(output_dir, exist_ok=True)
            
            # Using "Vorbis Quality High" as per zSound2wem.cmd
            xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<ExternalSourcesList SchemaVersion="1" Root="{temp_dir}">
    <Source Path="{clean_wav_name}" Conversion="Vorbis Quality High"/>
</ExternalSourcesList>"""
            
            with open(sources_xml_path, "w") as f:
                f.write(xml_content)
                
            # --- 4. Wwise Conversion ---
            self.status_msg.set("Running Wwise Console...")
            subprocess.run([
                wwise_console, 
                "convert-external-source", 
                project_path, 
                "--source-file", sources_xml_path, 
                "--output", output_dir, 
                "--quiet"
            ], cwd=temp_dir, startupinfo=self._get_startup_info(), check=True)
            
            # --- 5. Retrieve Output ---
            # Wwise outputs to Output/Windows/filename.wem or Output/Platform/filename.wem
            for root, dirs, files in os.walk(output_dir):
                for f in files:
                    if f.endswith(".wem"):
                        # Move to a clean location (temp_dir root) so caller can access it easily
                        final_wem = os.path.join(temp_dir, os.path.splitext(filename)[0] + ".wem")
                        shutil.move(os.path.join(root, f), final_wem)
                        return final_wem
                        
            raise Exception("Wwise did not produce a .wem file.")

        except Exception as e:
            print(f"Wwise conversion error: {e}")
            raise e
        
    def _get_startup_info(self):
        if os.name == 'nt':
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            return si
        return None

    def convert_to_wem(self, source_path):
        """Attempts to convert audio file to WEM using Wwise Console + FFmpeg."""
        
        # 1. Locate Tools
        wwise_console = self._find_wwise_console()
        ffmpeg_path = self._find_ffmpeg()

        # 2. Priority Method: Wwise + FFmpeg (Robust)
        if wwise_console and ffmpeg_path:
            try:
                return self._convert_with_wwise(wwise_console, ffmpeg_path, source_path)
            except Exception as e:
                CustomMessageBox("Conversion Error", f"Wwise+FFmpeg conversion failed:\n{e}", is_error=True)
                return None

        # 3. Fallback: Check for legacy local wav2wem.exe
        possible_execs = ["wav2wem.exe", "wwe.exe"]
        converter_path = None
        search_paths = [app_dir, resource_path(".")]
        
        for p in search_paths:
            for exe in possible_execs:
                full_path = os.path.join(p, exe)
                if os.path.exists(full_path):
                    converter_path = full_path
                    break
            if converter_path: break
        
        if converter_path:
            temp_dir = tempfile.mkdtemp()
            filename = os.path.basename(source_path)
            name_no_ext = os.path.splitext(filename)[0]
            output_wem = os.path.join(temp_dir, name_no_ext + ".wem")
            
            try:
                self.status_msg.set(f"Converting {filename} (Legacy Wrapper)...")
                temp_source = os.path.join(temp_dir, filename)
                shutil.copy2(source_path, temp_source)
                
                subprocess.run([converter_path, temp_source], cwd=temp_dir, startupinfo=self._get_startup_info(), check=True)
                
                if os.path.exists(output_wem):
                    return output_wem
                # Fallback check for any wem
                for f in os.listdir(temp_dir):
                    if f.endswith(".wem"): return os.path.join(temp_dir, f)
            except Exception as e:
                print(f"Wrapper conversion failed: {e}")

        # 4. Failure Message
        msg = "Audio conversion tools missing!\n\nRequirements:\n"
        if not wwise_console: msg += "- Wwise (Not found)\n"
        if not ffmpeg_path: msg += "- FFmpeg (Not found)\n"
        msg += "\nPlease install Wwise via Audiokinetic Launcher and ensure FFmpeg is in the app folder or PATH."
        
        CustomMessageBox("Error", msg, is_error=True)
        return None

    def replace_file_context(self):
        if not self.selected_entry_for_context: return
        entry = self.selected_entry_for_context
        
        dialog = CustomFileDialog(self, title=f"Replace {entry.name}", mode="open", 
                                  filetypes=[("All Files", "*.*"), ("Audio Files", "*.wem *.wav *.mp3 *.ogg")])
        if dialog.result:
            file_path = dialog.result
            ext = os.path.splitext(file_path)[1].lower()
            
            final_data = None
            
            # Check if it needs conversion
            if ext in [".wav", ".mp3", ".ogg", ".flac"]:
                wem_path = self.convert_to_wem(file_path)
                if wem_path and os.path.exists(wem_path):
                    try:
                        with open(wem_path, 'rb') as f:
                            final_data = f.read()
                    except Exception as e:
                        CustomMessageBox("Error", f"Read error: {e}", is_error=True)
                        return
                    
                    # Cleanup temp dir of wem_path
                    try: 
                        shutil.rmtree(os.path.dirname(wem_path))
                    except: pass
                else:
                    return # Cancel if conversion failed/cancelled
            else:
                try:
                    with open(file_path, 'rb') as f:
                        final_data = f.read()
                except Exception as e:
                     CustomMessageBox("Error", f"Read error: {e}", is_error=True)
                     return

            if final_data:
                self.open_containers[self.active_idx]['modifications'][entry.name] = final_data
                
                # Check for SBP constraint warning
                c_type = self.open_containers[self.active_idx]['type']
                msg = f"Replaced '{entry.name}' in memory.\nDon't forget to Repack."
                
                if c_type in ["SBP", "BNK"]:
                    if len(final_data) > entry.size:
                        msg += "\n\nWARNING: New file is larger than original!\nIt will be TRUNCATED during repack."
                    elif len(final_data) < entry.size:
                        msg += "\n\nNote: New file is smaller. It will be padded."
                        
                CustomMessageBox("Success", msg)
                self.status_msg.set(f"Replaced {entry.name}")

    def extract_file_context(self):
        if self.selected_entry_for_context:
            self.extract_single(self.selected_entry_for_context)

    def copy_name_context(self):
        if self.selected_entry_for_context:
            self.clipboard_clear()
            self.clipboard_append(self.selected_entry_for_context.name)
            self.update()

    def on_load_click(self):
        dialog = CustomFileDialog(self, title="Select WAD, SBP or Texpack Files", mode="open_multiple", 
                                  filetypes=[("GOW Files", "*.wad *.sbp *.bnk *.texpack"), ("All Files", "*.*")])
        if not dialog.result: return
        paths = dialog.result
        self.status_msg.set(f"Loading {len(paths)} files...")
        self.process_file_list(paths)

    def process_file_list(self, paths):
        for path in paths:
            filename = os.path.basename(path)
            _, ext = os.path.splitext(filename)
            ext = ext.lower()
            
            file_type = None
            if ext == ".wad": file_type = "WAD"
            elif ext == ".texpack": file_type = "TEXPACK"
            elif ext == ".sbp" or ext == ".bnk": file_type = "SBP"
            
            if not file_type:
                dlg = TypeSelectionDialog(self)
                self.wait_window(dlg)
                if dlg.selection: file_type = dlg.selection
            
            if file_type:
                 threading.Thread(target=self.run_parsing, args=(path, file_type)).start()

    def run_parsing(self, path, file_type):
        container = UnifiedController.get_container(path, file_type)
        success = False
        if container: success = container.read()
        self.after(0, lambda: self.add_container_result(container, success, file_type, path))

    def add_container_result(self, container, success, file_type, path):
        if not success or not container: 
            self.after(0, lambda: CustomMessageBox("Error", f"Failed to read {os.path.basename(path)}", is_error=True))
            return

        if isinstance(container, Gow2018_Wad):
            UnifiedController.prepare_unique_names(container)

        self.save_recent_files(path)
        self.open_containers.append({'container': container, 'path': path, 'type': file_type, 'modifications': {}})
        self.btn_extract_all.configure(state="normal")
        self.btn_batch_extract.configure(state="normal")
        self.btn_repack_current.configure(state="normal")
        
        self.rebuild_tab_bar()
        self.switch_to_tab(len(self.open_containers) - 1)
        self.status_msg.set(f"Loaded {os.path.basename(path)}")

    def close_tab(self, idx_to_close):
        if idx_to_close < 0 or idx_to_close >= len(self.open_containers): return
        
        # STOP AUDIO before closing
        if self.audio_player.is_playing:
            self.stop_audio()
            
        self.open_containers.pop(idx_to_close)
        
        if not self.open_containers:
            self.active_idx = -1
            self.current_entries = []
            
            # Reset Pagination on full clear
            self.page_index = 0
            self.total_pages = 1
            self.filtered_entries = []
            
            self.clear_main_view()
            self.btn_extract_all.configure(state="disabled")
            self.btn_batch_extract.configure(state="disabled")
            self.btn_repack_current.configure(state="disabled")
            
            # Reset Scrollbar
            self.file_list._parent_canvas.yview_moveto(0)
        else:
            if idx_to_close == self.active_idx:
                self.active_idx = max(0, idx_to_close - 1)
            elif idx_to_close < self.active_idx:
                self.active_idx -= 1
        
        self.rebuild_tab_bar()
        if self.active_idx != -1:
            self.switch_to_tab(self.active_idx)

    def rebuild_tab_bar(self):
        for w in self.tab_scroll.winfo_children():
            w.destroy()
        self.tab_widgets = []
        for i, data in enumerate(self.open_containers):
            color = COLOR_ACCENT if i == self.active_idx else COLOR_BTN_NORMAL
            fr = ctk.CTkFrame(self.tab_scroll, fg_color=color, corner_radius=6)
            fr.pack(side="left", padx=4, pady=5)
            ctk.CTkButton(fr, text=os.path.basename(data['path']), fg_color="transparent", hover_color=color, width=120, anchor="w", command=lambda idx=i: self.switch_to_tab(idx)).pack(side="left", padx=(5, 0), pady=2)
            ctk.CTkButton(fr, text="✕", width=24, height=24, fg_color="transparent", hover_color=COLOR_RED, text_color="#ffcccc", command=lambda idx=i: self.close_tab(idx)).pack(side="right", padx=(0, 2), pady=2)

    def switch_to_tab(self, idx):
        if idx < 0 or idx >= len(self.open_containers): return
        
        # STOP AUDIO when switching tabs (optional but good for cleanup)
        if self.audio_player.is_playing:
            self.stop_audio()
            
        self.active_idx = idx
        data = self.open_containers[idx]
        self.rebuild_tab_bar()
        self.entry_file_search.delete(0, "end")
        self.current_entries = list(data['container'].entries)
        
        # Sort WEM files by ID if SBP
        if data['type'] in ["SBP", "BNK"]:
             self.current_entries.sort(key=lambda x: int(x.name) if x.name.isdigit() else x.name)
        else:
            self.current_entries.sort(key=lambda x: 0 if x.name == "MSGS_TXT" else 1)
            
        self.lbl_status_details.configure(text=f"{data['type']} | {len(data['container'].entries)} Items | {self.format_size(os.path.getsize(data['path']))}")
        
        # Reset Pagination when switching tabs
        self.page_index = 0
        
        # Reset Scrollbar Position to top
        self.file_list._parent_canvas.yview_moveto(0)
        
        self.apply_filters()

    def stop_audio(self):
        self.audio_update_loop_running = False
        if hasattr(self, 'audio_player'):
            self.audio_player.close()
        
        # Restaura o botão verde "Play" na linha que estava tocando
        if self.current_playing_entry and self.current_playing_entry.name in self.audio_zones:
             zone = self.audio_zones[self.current_playing_entry.name]
             try:
                 if zone.winfo_exists():
                     # Limpa tudo no zone (que seria slider/pause)
                     for w in zone.winfo_children():
                         try: w.destroy()
                         except: pass
                     
                     # Recria o botão verde de play
                     ctk.CTkButton(zone, text="▶", width=30, height=24, font=("Roboto", 14), 
                                  fg_color="#2ECC71", hover_color="#27AE60", text_color="white", 
                                  command=lambda e=self.current_playing_entry: self.play_audio(e)).pack(side="left", padx=5)
             except:
                 pass
        
        self.current_playing_entry = None
        self.active_audio_widgets = {}

    # Função Toggle Pause/Resume
    def toggle_audio_state(self):
        if not self.audio_player.is_playing and not self.audio_player.is_paused:
            # Se não tá tocando nada, não faz nada (ou poderia dar play do zero)
            return

        btn = self.active_audio_widgets.get('btn_play_pause')

        if self.audio_player.is_playing:
            self.audio_player.pause()
            if btn: btn.configure(text="▶", fg_color=COLOR_ACCENT) # Volta pra icone de play
        else:
            self.audio_player.resume()
            if btn: btn.configure(text="⏸", fg_color="#C0392B") # Icone de pause (vermelho ou outra cor)

    # Eventos da Slider (Segurar para travar)
    def on_slider_press(self, event):
        self.is_dragging_slider = True
        # Opcional: Pausar o áudio visualmente/auditivamente enquanto arrasta
        # self.audio_player.pause() 

    def on_slider_release(self, event):
        self.is_dragging_slider = False
        if self.active_audio_widgets:
            slider = self.active_audio_widgets.get('slider')
            try:
                if slider.winfo_exists():
                    val = slider.get()
                    self.audio_player.set_position(int(val))
            except: pass
            # Se estava pausado pelo arraste, retomar:
            # self.audio_player.resume()

    def play_audio(self, entry):
        if self.active_idx == -1: return
        
        # 1. Parar audio atual (limpa widgets anteriores via stop_audio)
        self.stop_audio()

        # 3. Preparar Arquivo
        ext = entry.get_extension()
        safe_name = entry.name
        if not "." in safe_name and ext:
             safe_name += ext

        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, safe_name)
        
        data = self._get_entry_data(entry)
        if not data: return

        try:
            with open(temp_path, 'wb') as f:
                f.write(data)
            
            # WEM Handling
            if ext == ".wem":
                vgm_cli = resource_path("vgmstream-cli.exe")
                if not os.path.exists(vgm_cli): vgm_cli = os.path.join(app_dir, "vgmstream-cli.exe")
                
                if os.path.exists(vgm_cli):
                    wav_path = temp_path + ".wav"
                    startupinfo = None
                    if os.name == 'nt':
                        startupinfo = subprocess.STARTUPINFO()
                        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    
                    try:
                        subprocess.run([vgm_cli, "-o", wav_path, temp_path], startupinfo=startupinfo, check=True)
                        if os.path.exists(wav_path):
                            temp_path = wav_path
                    except Exception as e:
                        print(f"Conversion error: {e}")
            
            # 4. Tocar com Native Player (MCI)
            if os.name == 'nt':
                # Encontra o container UI reservado para este arquivo
                audio_zone = self.audio_zones.get(entry.name)
                
                # Check existency safely
                try:
                    if audio_zone and audio_zone.winfo_exists():
                        # Limpa o botão verde de play
                        for w in audio_zone.winfo_children():
                             try: w.destroy()
                             except: pass

                        # Cria os controles na linha do arquivo
                        
                        # Botão Pause/Play
                        btn_pp = ctk.CTkButton(audio_zone, text="⏸", width=30, height=24, 
                                              font=("Roboto", 14), fg_color="#C0392B", hover_color="#922B21", 
                                              command=self.toggle_audio_state)
                        btn_pp.pack(side="left", padx=(0, 5))
                        
                        # Slider
                        slider = ctk.CTkSlider(audio_zone, from_=0, to=100, width=120, height=16, 
                                              progress_color=COLOR_ACCENT, button_color="white", button_hover_color="#ddd",
                                              command=lambda v: None) # Command vazio pois usamos bind
                        slider.set(0)
                        slider.pack(side="left", padx=5)
                        
                        # Binds para segurar a bolinha
                        slider.bind("<Button-1>", self.on_slider_press)
                        slider.bind("<ButtonRelease-1>", self.on_slider_release)
                        
                        # Label Tempo
                        lbl_time = ctk.CTkLabel(audio_zone, text="00:00 / 00:00", font=("Roboto Mono", 10), width=80)
                        lbl_time.pack(side="left", padx=5)

                        # Guarda referencias
                        self.active_audio_widgets = {
                            'btn_play_pause': btn_pp,
                            'slider': slider,
                            'lbl_time': lbl_time
                        }
                        self.current_playing_entry = entry
                except: pass

                self.audio_player.load(temp_path)
                self.audio_player.play()
                self.status_msg.set(f"Playing: {safe_name}")
                
                self.audio_update_loop_running = True
                self.update_audio_progress()
                self.audio_controls_frame.pack(side="right", padx=10) # Show global controls
            else:
                if sys.platform == "darwin": subprocess.call(('open', temp_path))
                else: subprocess.call(('xdg-open', temp_path))
                    
        except Exception as e:
            CustomMessageBox("Error", f"Could not play audio: {e}", is_error=True)

    def apply_filters(self):
        if not self.current_entries: return
        query = self.entry_file_search.get().lower()
        
        filtered = []
        for e in self.current_entries:
            if query and query not in e.name.lower(): continue
            ext = e.get_extension()
            is_txt = e.name == "MSGS_TXT"
            is_tex = ext == ".texpack" or ext == ".dds" or e.type_id == 0x80A1
            is_wem = ext == ".wem" or ext == ".ogg"
            
            # "Binary/Other" is everything else
            is_bin = not (is_txt or is_tex or is_wem)

            if is_txt and not self.chk_txt_var.get(): continue
            if is_tex and not self.chk_tex_var.get(): continue
            if is_wem and not self.chk_audio_var.get(): continue
            if is_bin and not self.chk_bin_var.get(): continue
            
            filtered.append(e)
            
        self.filtered_entries = filtered
        self.total_pages = (len(self.filtered_entries) + self.items_per_page - 1) // self.items_per_page
        if self.total_pages == 0: self.total_pages = 1
        
        # Clamp page index
        if self.page_index >= self.total_pages: 
            self.page_index = 0
        
        self.update_file_list_view()

    def on_file_search(self, event=None):
        self.apply_filters()

    def select_all_files(self):
        if not hasattr(self, 'file_selection_vars'): return
        for _, var in self.file_selection_vars.values():
            var.set(True)

    def deselect_all_files(self):
        if not hasattr(self, 'file_selection_vars'): return
        for _, var in self.file_selection_vars.values():
            var.set(False)

    def batch_replace_selected(self):
        if not hasattr(self, 'file_selection_vars'): return
        selected_entries = [entry for entry, var in self.file_selection_vars.values() if var.get()]
        
        if not selected_entries:
            CustomMessageBox("Info", "No files selected.\nCheck the boxes next to files you want to replace.")
            return

        dialog = CustomFileDialog(self, title="Select One Audio Source to Apply to All Selected", mode="open", 
                                  filetypes=[("Audio Files", "*.wem *.wav *.mp3 *.ogg *.flac"), ("All Files", "*.*")])
        if not dialog.result: return
        source_path = dialog.result

        # Convert source once
        final_data = None
        ext = os.path.splitext(source_path)[1].lower()
        
        self.status_msg.set("Processing batch replacement...")
        
        if ext in [".wav", ".mp3", ".ogg", ".flac"]:
            wem_path = self.convert_to_wem(source_path)
            if wem_path and os.path.exists(wem_path):
                try:
                    with open(wem_path, 'rb') as f: final_data = f.read()
                    try: shutil.rmtree(os.path.dirname(wem_path))
                    except: pass
                except Exception as e:
                    CustomMessageBox("Error", f"Read error: {e}", is_error=True)
                    return
            else: return # Conversion failed
        else:
            try:
                with open(source_path, 'rb') as f: final_data = f.read()
            except Exception as e:
                CustomMessageBox("Error", f"Read error: {e}", is_error=True)
                return

        if final_data:
            replaced_count = 0
            container_mods = self.open_containers[self.active_idx]['modifications']
            
            for entry in selected_entries:
                container_mods[entry.name] = final_data
                replaced_count += 1
            
            CustomMessageBox("Success", f"Replaced {replaced_count} files with:\n{os.path.basename(source_path)}")
            self.status_msg.set(f"Batch replaced {replaced_count} files.")

    def update_file_list_view(self):
        entries = self.filtered_entries
        
        # Limpa widgets anteriores
        for w in self.file_list.winfo_children(): w.destroy()
        
        # Limpa referencias de zonas de audio
        self.audio_zones = {}
        # If we refresh the list, we lose the row widgets, so we must stop audio update for rows
        # But we can keep global audio playing if desired. For now, stop to avoid orphans.
        self.stop_audio() 
        self.audio_controls_frame.pack_forget()

        self.file_selection_vars = {} # Initialize selection dict

        if not entries:
            self.lbl_page_info.configure(text="")
            self.btn_prev_page.configure(state="disabled")
            self.btn_next_page.configure(state="disabled")
            ctk.CTkLabel(self.file_list, text="No matches found.", text_color="gray").pack(pady=20)
            return

        # PAGINATION SLICING
        start_idx = self.page_index * self.items_per_page
        end_idx = start_idx + self.items_per_page
        page_entries = entries[start_idx:end_idx]

        # Update Pagination Controls
        self.lbl_page_info.configure(text=f"Page {self.page_index + 1} / {self.total_pages} ({len(entries)} items)")
        self.btn_prev_page.configure(state="normal" if self.page_index > 0 else "disabled")
        self.btn_next_page.configure(state="normal" if self.page_index < self.total_pages - 1 else "disabled")

        header_row = ctk.CTkFrame(self.file_list, height=30, fg_color="transparent")
        header_row.pack(fill="x")
        ctk.CTkLabel(header_row, text="FILENAME / ID", font=("Roboto", 11, "bold"), text_color="gray").pack(side="left", padx=40) # Increased pad for checkbox
        ctk.CTkLabel(header_row, text="SIZE", font=("Roboto", 11, "bold"), text_color="gray").pack(side="right", padx=70)

        is_lang_wad = "r_lang" in os.path.basename(self.open_containers[self.active_idx]['path']).lower()

        for i, entry in enumerate(page_entries):
            bg_col = "#252525" if i % 2 == 0 else "transparent"
            row = ctk.CTkFrame(self.file_list, fg_color=bg_col, corner_radius=4)
            row.pack(fill="x", pady=1)
            row.bind("<Button-3>", lambda e, en=entry: self.show_context_menu(e, en))

            # --- Checkbox Selection ---
            chk_var = ctk.BooleanVar(value=False)
            chk = ctk.CTkCheckBox(row, text="", variable=chk_var, width=20, height=20, 
                                  checkbox_width=18, checkbox_height=18, border_width=2,
                                  fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER)
            chk.pack(side="left", padx=(5, 5))
            self.file_selection_vars[entry.name] = (entry, chk_var)
            # --------------------------

            # 1. Tamanho (Direita)
            lbl_sz = ctk.CTkLabel(row, text=f"{entry.size:,} B", font=("Roboto Mono", 11), text_color="gray")
            lbl_sz.pack(side="right", padx=10)
            lbl_sz.bind("<Button-3>", lambda e, en=entry: self.show_context_menu(e, en))

            # 2. Ações (Direita - Extract/Edit)
            actions = ctk.CTkFrame(row, fg_color="transparent")
            actions.pack(side="right", padx=5)

            if is_lang_wad and entry.name == "MSGS_TXT":
                ctk.CTkButton(actions, text="Edit", width=60, height=24, font=("Roboto", 11), fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER, command=lambda e=entry: self.open_text_editor(e)).pack(side="left", padx=5)
            
            ctk.CTkButton(actions, text="Extract", width=60, height=24, font=("Roboto", 11), fg_color="#444", hover_color="#555", command=lambda e=entry: self.extract_single(e)).pack(side="left", padx=5)

            # 3. Nome (Esquerda)
            lbl = ctk.CTkLabel(row, text=entry.name, font=("Roboto Mono", 12))
            lbl.pack(side="left", padx=5, pady=5)
            lbl.bind("<Button-3>", lambda e, en=entry: self.show_context_menu(e, en))
            
            ext = entry.get_extension()
            is_audio = ext == ".wem" or ext == ".ogg"

            # 4. Zona do Player de Audio (CENTRO - Preenche o espaço restante)
            if is_audio:
                audio_zone = ctk.CTkFrame(row, fg_color="transparent", height=30)
                audio_zone.pack(side="left", fill="x", expand=True, padx=10) # fill="x" e expand=True faz ele ocupar o meio
                self.audio_zones[entry.name] = audio_zone 
                
                # Cria o Botão Play Verde INICIALMENTE aqui, no meio
                ctk.CTkButton(audio_zone, text="▶", width=30, height=24, font=("Roboto", 14), 
                              fg_color="#2ECC71", hover_color="#27AE60", text_color="white", 
                              command=lambda e=entry: self.play_audio(e)).pack(side="left", padx=5)

    def next_page(self):
        if self.page_index < self.total_pages - 1:
            self.page_index += 1
            self.file_list._parent_canvas.yview_moveto(0) # SCROLL RESET HERE
            self.update_file_list_view()

    def prev_page(self):
        if self.page_index > 0:
            self.page_index -= 1
            self.file_list._parent_canvas.yview_moveto(0) # SCROLL RESET HERE
            self.update_file_list_view()

    def _get_entry_data(self, entry):
        if self.active_idx == -1: return None
        data_c = self.open_containers[self.active_idx]
        if entry.name in data_c['modifications']: return data_c['modifications'][entry.name]
        return UnifiedController.read_file_data(data_c['path'], entry)

    def open_text_editor(self, entry):
        if not entry: return
        raw_data = self._get_entry_data(entry)
        if raw_data:
            TextEditorWindow(self, entry, raw_data, self.open_containers[self.active_idx]['path'], 
                             self.open_containers[self.active_idx]['modifications'],
                             self.open_containers[self.active_idx]['container'])
        else:
            CustomMessageBox("Error", "Failed to read data.", is_error=True)

    def open_hex_viewer(self, entry):
        if not entry: return
        raw_data = self._get_entry_data(entry)
        if raw_data:
            HexViewerWindow(self, entry, raw_data)
        else:
            CustomMessageBox("Error", "Failed to read data.", is_error=True)

    def clear_main_view(self):
        self.lbl_status_details.configure(text="")
        self.entry_file_search.delete(0, "end")
        self.lbl_page_info.configure(text="") # Clear pagination text
        self.btn_prev_page.configure(state="disabled")
        self.btn_next_page.configure(state="disabled")
        for w in self.file_list.winfo_children(): w.destroy()
        self.rebuild_tab_bar()

    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024: return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"

    def scan_for_true_index(self, wad_path, target_data_offset):
        idx = 0
        try:
            with open(wad_path, 'rb') as f:
                f.seek(0, 2)
                wad_size = f.tell()
                f.seek(0)
                offset = 0
                while offset < wad_size:
                    f.seek(offset)
                    header_data = f.read(96)
                    if len(header_data) < 96: break
                    size = struct.unpack('<I', header_data[4:8])[0]
                    if offset + 96 == target_data_offset: return idx
                    
                    next_offset = offset + 96 + size + 0x0F
                    next_offset &= 0xFFFFFFF0
                    offset = next_offset
                    idx += 1
        except:
            return -1
        return -1

    def _extract_entry_with_conversion(self, container_data, entry, out_dir):
        """Helper to extract an entry, converting audio to WAV if possible."""
        try:
            # 1. Get Data (Check modifications first)
            if entry.name in container_data['modifications']:
                data = container_data['modifications'][entry.name]
            else:
                data = UnifiedController.read_file_data(container_data['path'], entry)

            # If no data (e.g. Texpack), use backend extractor directly
            if data is None:
                return UnifiedController.extract_file(container_data['path'], entry, out_dir)

            # 2. Determine Safe Name
            safe_name = "".join([c for c in entry.name if c.isalnum() or c in "._- "]).strip()
            if not safe_name: safe_name = f"file_{entry.offset}"
            
            ext = entry.get_extension()
            
            # Magic Check for extension if .bin
            if ext == ".bin" and len(data) > 4:
                magic = data[0:4]
                if magic == b'RIFF': ext = ".wem"
                elif magic == b'BKHD': ext = ".wem"
                elif magic == b'OggS': ext = ".ogg"

            final_name = safe_name
            converted = False

            # 3. Audio Conversion (WEM -> WAV)
            if ext == ".wem":
                vgm_cli = resource_path("vgmstream-cli.exe")
                if not os.path.exists(vgm_cli): vgm_cli = os.path.join(app_dir, "vgmstream-cli.exe")
                
                if os.path.exists(vgm_cli):
                    temp_wem_path = os.path.join(out_dir, safe_name + ".wem")
                    wav_name = safe_name + ".wav"
                    wav_path = os.path.join(out_dir, wav_name)
                    
                    try:
                        # Write temp file
                        with open(temp_wem_path, 'wb') as f:
                            f.write(data)
                        
                        startupinfo = None
                        if os.name == 'nt':
                            startupinfo = subprocess.STARTUPINFO()
                            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        
                        # Run Conversion
                        subprocess.run([vgm_cli, "-o", wav_path, temp_wem_path], startupinfo=startupinfo, check=True)
                        
                        # Cleanup
                        if os.path.exists(wav_path):
                            if os.path.exists(temp_wem_path): os.remove(temp_wem_path)
                            final_name = wav_name
                            converted = True
                    except Exception as e:
                        print(f"Conversion failed, falling back to raw: {e}")
            
            # 4. Write Raw if not converted
            if not converted:
                if "." not in safe_name and ext: safe_name += ext
                final_name = safe_name
                final_path = os.path.join(out_dir, safe_name)
                with open(final_path, 'wb') as f:
                    f.write(data)
            
            return final_name

        except Exception as e:
            print(f"Extraction error: {e}")
            return None

    def extract_single(self, entry):
        if self.active_idx == -1: return
        container_data = self.open_containers[self.active_idx]
        
        dialog = CustomFileDialog(self, title="Select Output Directory", mode="directory")
        if dialog.result:
            out_dir = dialog.result
            result_name = self._extract_entry_with_conversion(container_data, entry, out_dir)
            
            if result_name:
                CustomMessageBox("Success", f"Extracted: {result_name}")
            else:
                CustomMessageBox("Error", "Extraction failed.", is_error=True)

    def extract_current_action(self):
        if self.active_idx == -1: return
        dialog = CustomFileDialog(self, title="Select Output Directory", mode="directory")
        if dialog.result:
            base_out_dir = dialog.result
            self.status_msg.set("Preparing extraction...")
            self.disable_buttons()
            threading.Thread(target=self.run_extraction_task, args=(base_out_dir, [self.open_containers[self.active_idx]])).start()

    def batch_extract_action(self):
        if not self.open_containers: return
        dialog = CustomFileDialog(self, title="Select Base Output Directory", mode="directory")
        if dialog.result:
            base_out_dir = dialog.result
            self.status_msg.set("Starting Batch Extraction...")
            self.disable_buttons()
            threading.Thread(target=self.run_extraction_task, args=(base_out_dir, self.open_containers)).start()
    
    def repack_action(self):
        dlg_mod = CustomFileDialog(self, title="1. Select Folder with Modified Files", mode="directory")
        if not dlg_mod.result: return
        mod_folder = dlg_mod.result

        dlg_wad = CustomFileDialog(self, title="2. Select Original WAD File", mode="open", filetypes=[("WAD Files", "*.wad"), ("All Files", "*.*")])
        if not dlg_wad.result: return
        orig_wad = dlg_wad.result

        dlg_save = CustomFileDialog(self, title="3. Save New WAD As...", mode="save", filetypes=[("WAD Files", "*.wad")], initial_file="new_archive.wad")
        if not dlg_save.result: return
        save_path = dlg_save.result

        self.disable_buttons()
        self.status_msg.set("Repacking WAD...")
        threading.Thread(target=self.run_repack_task, args=(orig_wad, mod_folder, save_path)).start()

    def repack_current_action(self):
        if self.active_idx == -1: return
        
        data = self.open_containers[self.active_idx]
        ext_filter = "*.wad"
        if data['type'] in ["SBP", "BNK"]:
            ext_filter = "*.sbp *.bnk"
        elif data['type'] == "TEXPACK":
            ext_filter = "*.texpack"
            
        dialog = CustomFileDialog(self, title="Save Repacked File As...", mode="save", 
                                  filetypes=[("Archive", ext_filter)], 
                                  initial_file=os.path.basename(data['path']))
        
        if not dialog.result: return
        save_path = dialog.result

        self.disable_buttons()
        self.status_msg.set("Preparing to repack current file...")
        threading.Thread(target=self.run_repack_current_task, args=(self.active_idx, save_path)).start()

    def run_repack_current_task(self, idx, save_path):
        data = self.open_containers[idx]
        container_path = data['path']
        modifications = data['modifications']
        container = data['container']
        file_type = data['type']
        
        if self.chk_backup_var.get():
            backup_path = container_path + ".bak"
            try:
                if not os.path.exists(backup_path):
                    self.status_msg.set("Creating Backup...")
                    shutil.copy2(container_path, backup_path)
            except Exception as e:
                print(f"Backup failed: {e}")

        try:
            success = False
            
            if file_type == "WAD":
                # WAD Repacking Logic (Rebuilds archive)
                temp_dir = tempfile.mkdtemp()
                try:
                    self.status_msg.set("Staging modified files...")
                    name_to_entry = {e.name: e for e in container.entries}
                    
                    for name, content in modifications.items():
                        if name not in name_to_entry: continue
                        
                        entry = name_to_entry[name]
                        true_idx = self.scan_for_true_index(container_path, entry.offset)
                        if true_idx == -1: continue
                        
                        clean_name = name.replace('/', '.').replace('\\', '.')
                        target_filename = f"{clean_name}.{true_idx}.bin"
                        target_path = os.path.join(temp_dir, target_filename)
                        
                        with open(target_path, 'wb') as f:
                            f.write(content)
                    
                    def update_status(curr, total, name):
                        if curr % 20 == 0: self.status_msg.set(f"Repacking: {curr} files processed...")

                    success = UnifiedController.repack_wad(container_path, temp_dir, save_path, update_status)
                finally:
                    if os.path.exists(temp_dir):
                        shutil.rmtree(temp_dir)
            
            elif file_type in ["SBP", "BNK"]:
                # SBP Repacking Logic (In-place replacement with DIDX Size Update)
                self.status_msg.set("Injecting Audio files...")
                
                try:
                    # 1. Copy original file to destination
                    shutil.copy2(container_path, save_path)
                    
                    with open(save_path, "r+b") as f:
                        # 2. Parse Headers to find DIDX (Scan first 1MB)
                        f.seek(0)
                        header_chunk = f.read(1024 * 1024)
                        
                        bkhd_pos = header_chunk.find(b"BKHD")
                        if bkhd_pos == -1:
                            raise Exception("Invalid SBP/BNK: BKHD header not found.")
                            
                        didx_pos = header_chunk.find(b"DIDX", bkhd_pos)
                        data_pos = header_chunk.find(b"DATA", bkhd_pos)
                        
                        if didx_pos == -1 or data_pos == -1:
                            raise Exception("Invalid SBP/BNK: DIDX or DATA chunk not found.")
                            
                        audio_base_offset = data_pos + 8
                        didx_size = struct.unpack_from("<I", header_chunk, didx_pos + 4)[0]
                        entry_count = didx_size // 12
                        
                        # 3. Build Map: ID -> {offset, length, didx_ptr}
                        wem_map = {}
                        curr_didx = didx_pos + 8
                        
                        for _ in range(entry_count):
                            # Handle reading beyond the initial chunk if necessary
                            if curr_didx + 12 > len(header_chunk):
                                f.seek(curr_didx)
                                entry_bytes = f.read(12)
                                wem_id, off, length = struct.unpack("<III", entry_bytes)
                            else:
                                wem_id, off, length = struct.unpack_from("<III", header_chunk, curr_didx)
                            
                            # ID matches app.py's string format
                            wem_map[str(wem_id)] = {
                                'offset': off,
                                'original_length': length,
                                'didx_ptr': curr_didx
                            }
                            curr_didx += 12
                        
                        # 4. Inject Files
                        processed_count = 0
                        for name, new_data in modifications.items():
                            if name not in wem_map:
                                print(f"Skipping {name}: Not found in SBP")
                                continue
                                
                            entry = wem_map[name]
                            start_ptr = audio_base_offset + entry['offset']
                            original_len = entry['original_length']
                            new_len = len(new_data)
                            
                            # Write Audio Data
                            f.seek(start_ptr)
                            if new_len > original_len:
                                # Truncate if larger
                                f.write(new_data[:original_len])
                                final_len = original_len
                            else:
                                # Write & Pad if smaller
                                f.write(new_data)
                                padding = original_len - new_len
                                if padding > 0:
                                    f.write(b'\x00' * padding)
                                final_len = new_len
                                
                            # KEY FIX: Update DIDX Table Size
                            f.seek(entry['didx_ptr'] + 8)
                            f.write(struct.pack("<I", final_len))
                            
                            processed_count += 1
                            if processed_count % 5 == 0:
                                self.status_msg.set(f"Injecting: {name}")
                                
                    success = True
                except Exception as e:
                    print(f"SBP Injection Error: {e}")
                    success = False
            
            else:
                self.after(0, lambda: CustomMessageBox("Error", "Repacking not supported for this file type yet.", is_error=True))
                self.after(0, self.enable_buttons)
                return

            self.after(0, self.enable_buttons)
            if success:
                self.after(0, lambda: CustomMessageBox("Success", "Repack Successfully!"))
                self.status_msg.set("Repack Complete.")
            else:
                self.after(0, lambda: CustomMessageBox("Error", "Repack failed.", is_error=True))
                self.status_msg.set("Repack Failed.")
                
        except Exception as e:
            print(e)
            self.after(0, lambda: CustomMessageBox("Error", f"An error occurred: {e}", is_error=True))
            self.after(0, self.enable_buttons)

    def run_repack_task(self, orig_wad, mod_folder, save_path):
        # This is strictly for WAD batch repacking from folder
        if self.chk_backup_var.get():
            backup_path = orig_wad + ".bak"
            try:
                if not os.path.exists(backup_path):
                    self.status_msg.set("Creating Backup...")
                    shutil.copy2(orig_wad, backup_path)
                else:
                    print(f"Backup skipped: {backup_path} already exists.")
            except Exception as e:
                print(f"Backup failed: {e}")

        def update_status(curr, total, name):
            if curr % 20 == 0: self.status_msg.set(f"Repacking: {curr} files processed...")

        success = UnifiedController.repack_wad(orig_wad, mod_folder, save_path, update_status)
        self.after(0, self.enable_buttons)
        if success:
            self.after(0, lambda: CustomMessageBox("Success", "WAD Repacked Successfully!"))
            self.status_msg.set("Repack Complete.")
        else:
            self.after(0, lambda: CustomMessageBox("Error", "Repack failed. Check console.", is_error=True))
            self.status_msg.set("Repack Failed.")

    def disable_buttons(self):
        self.btn_load.configure(state="disabled")
        self.btn_extract_all.configure(state="disabled")
        self.btn_batch_extract.configure(state="disabled")
        self.btn_repack.configure(state="disabled")
        self.btn_repack_current.configure(state="disabled")

    def enable_buttons(self):
        self.btn_load.configure(state="normal")
        self.btn_extract_all.configure(state="normal")
        self.btn_batch_extract.configure(state="normal")
        self.btn_repack.configure(state="normal")
        self.btn_repack_current.configure(state="normal")

    def run_extraction_task(self, base_out_dir, container_list):
        total_files = len(container_list)
        for idx, data in enumerate(container_list):
            container = data['container']
            path = data['path']
            filename = os.path.basename(path) 
            modifications = data.get('modifications', {})
            self.status_msg.set(f"Extracting {filename} ({idx+1}/{total_files})...")
            
            folder_name = os.path.splitext(filename)[0]
            final_out_dir = os.path.join(base_out_dir, folder_name)
            if not os.path.exists(final_out_dir): os.makedirs(final_out_dir)
            
            for i, entry in enumerate(container.entries):
                if entry.name in modifications:
                    try:
                        safe_name = "".join([c for c in entry.name if c.isalnum() or c in "._- "]).strip()
                        if not safe_name: safe_name = f"file_{entry.offset}"
                        ext = entry.get_extension()
                        if "." not in safe_name and ext: safe_name += ext
                        
                        with open(os.path.join(final_out_dir, safe_name), 'wb') as f:
                            f.write(modifications[entry.name])
                    except: pass
                else:
                    # Use helper for WAV conversion
                    self._extract_entry_with_conversion(data, entry, final_out_dir)
                
                if i % 50 == 0:
                    self.status_msg.set(f"Extracting {filename}: {i}/{len(container.entries)}")

        self.status_msg.set("Extraction Complete.")
        self.after(0, self.enable_buttons)
        self.after(0, lambda: CustomMessageBox("Done", "Batch operation completed."))

    def _shared_app_init(cls):
        return cls

    cls.init_app = init_app
    cls.setup_custom_titlebar = setup_custom_titlebar
    cls.start_move = start_move
    cls.do_move = do_move
    cls.minimize_window = minimize_window
    cls.on_deiconify = on_deiconify
    cls.change_maximize_state = change_maximize_state
    cls.load_recent_files = load_recent_files
    cls.save_recent_files = save_recent_files
    cls.check_system = check_system
    cls.create_sidebar = create_sidebar
    cls.show_recent_menu = show_recent_menu
    cls.create_nav_button = create_nav_button
    cls.create_main_area = create_main_area
    cls.create_context_menu = create_context_menu
    cls.show_context_menu = show_context_menu
    cls.replace_file_context = replace_file_context
    cls.extract_file_context = extract_file_context
    cls.copy_name_context = copy_name_context
    cls.on_load_click = on_load_click
    cls.process_file_list = process_file_list
    cls.run_parsing = run_parsing
    cls.add_container_result = add_container_result
    cls.close_tab = close_tab
    cls.rebuild_tab_bar = rebuild_tab_bar
    cls.switch_to_tab = switch_to_tab
    cls.apply_filters = apply_filters
    cls.on_file_search = on_file_search
    cls.update_file_list_view = update_file_list_view
    cls._get_entry_data = _get_entry_data
    cls.open_text_editor = open_text_editor
    cls.open_hex_viewer = open_hex_viewer
    cls.clear_main_view = clear_main_view
    cls.format_size = format_size
    cls.scan_for_true_index = scan_for_true_index
    cls._extract_entry_with_conversion = _extract_entry_with_conversion
    cls.extract_single = extract_single
    cls.extract_current_action = extract_current_action
    cls.batch_extract_action = batch_extract_action
    cls.repack_action = repack_action
    cls.run_repack_task = run_repack_task
    cls.repack_current_action = repack_current_action
    cls.run_repack_current_task = run_repack_current_task
    cls.disable_buttons = disable_buttons
    cls.enable_buttons = enable_buttons
    cls.run_extraction_task = run_extraction_task
    cls.set_appwindow = set_appwindow
    cls.bind_resize_events = bind_resize_events
    cls.on_hover_resize = on_hover_resize
    cls.on_click_resize = on_click_resize
    cls.on_drag_resize = on_drag_resize
    cls.on_release_resize = on_release_resize
    cls.load_custom_font = load_custom_font
    cls.play_audio = play_audio
    cls.stop_audio = stop_audio
    cls.seek_audio = seek_audio
    cls.update_audio_progress = update_audio_progress
    cls.toggle_audio_state = toggle_audio_state
    cls.on_slider_press = on_slider_press
    cls.on_slider_release = on_slider_release
    cls.convert_to_wem = convert_to_wem  # Nova função
    cls._find_wwise_console = _find_wwise_console # Helper
    cls._find_ffmpeg = _find_ffmpeg # Helper - ADDED
    cls._convert_with_wwise = _convert_with_wwise # Helper
    cls._get_startup_info = _get_startup_info # Helper
    cls.select_all_files = select_all_files
    cls.deselect_all_files = deselect_all_files
    cls.batch_replace_selected = batch_replace_selected
    
    # Pagination
    cls.next_page = next_page
    cls.prev_page = prev_page
    
    return cls

GOWUnifiedApp = _shared_app_init(GOWUnifiedApp)

if __name__ == "__main__":
    app = GOWUnifiedApp()
    app.mainloop()