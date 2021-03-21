# pylint: disable=too-many-lines

import logging
import os
import os.path
import tempfile
import tkinter as tk
import tkinter.messagebox as tkMessageBox
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, ttk

import pyclip
from PIL import Image, ImageDraw, ImageEnhance, ImageTk
from modlunky2.ui.utils import tb_info

from modlunky2.constants import BASE_DIR
from modlunky2.levels import LevelFile
from modlunky2.levels.level_chances import LevelChance, LevelChances
from modlunky2.levels.level_settings import LevelSetting, LevelSettings
from modlunky2.levels.level_templates import (
    Chunk,
    LevelTemplate,
    LevelTemplates,
    TemplateSetting,
)
from modlunky2.levels.monster_chances import MonsterChance, MonsterChances
from modlunky2.levels.tile_codes import VALID_TILE_CODES, TileCode, TileCodes
from modlunky2.sprites import SpelunkySpriteFetcher
from modlunky2.sprites.tilecode_extras import TILENAMES
from modlunky2.ui.widgets import ScrollableFrame, Tab

logger = logging.getLogger("modlunky2")


class LevelsTab(Tab):
    def __init__(
        self, tab_control, modlunky_ui, config, *args, **kwargs
    ):  # Loads editor start screen
        super().__init__(tab_control, *args, **kwargs)

        self.modlunky_ui = modlunky_ui
        self.tree_levels = LevelsTree(self, self)
        self.last_selected_room = None
        # TODO: Get actual resolution
        self.screen_width = 1290
        self.screen_height = 720
        self.extracts_mode = True
        self.dual_mode = False
        self.tab_control = tab_control
        self.install_dir = config.install_dir
        self.textures_dir = config.install_dir / "Mods/Extracted/Data/Textures"
        self._sprite_fetcher = None

        self.lvl_editor_start_canvas = tk.Canvas(self)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.lvl_editor_start_canvas.grid(row=0, column=0, columnspan=2, sticky="nswe")
        self.lvl_editor_start_canvas.columnconfigure(0, weight=1)
        self.lvl_editor_start_canvas.rowconfigure(0, weight=1)

        self.extracts_path = self.install_dir / "Mods" / "Extracted" / "Data" / "Levels"
        self.overrides_path = self.install_dir / "Mods" / "Overrides"

        self.welcome_label = tk.Label(
            self.lvl_editor_start_canvas,
            text=(
                "Welcome to the Spelunky 2 Level Editor! "
                "Created by JackHasWifi with lots of help from "
                "Garebear, Fingerspit, Wolfo, and the community\n\n "
                "NOTICE: Saving when viewing extracts will save the "
                "changes to a new file in overrides.\n"
                "When loading from extracts, if a file exists in overrides,\nit will be loaded from there instead.\n\n"
                "BIGGER NOTICE: Please make backups of your files. This is still in beta stages.."
            ),
            anchor="center",
            bg="black",
            fg="white",
        )
        self.welcome_label.grid(row=0, column=0, sticky="nswe", ipady=30, padx=(10, 10))

        # Init Attributes
        self.lvls_path = None
        self.save_needed = False
        self.last_selected_file = None
        self.cur_lvl_bg_path = None
        self.im_output = None
        self.lvl_bg = None
        self.lvl_bg_path = None
        self.lvl_bgbg = None
        self.lvl_bgbg_path = None
        self.rows = None
        self.cols = None
        self.tiles = None
        self.tiles_meta = None
        self.usable_codes_string = None
        self.usable_codes = None
        self.im_output_dual = None
        self.tile_pallete_ref_in_use = None
        self.lvl = None
        self.lvl_biome = None
        self.node = None

        def select_lvl_folder():
            dirname = filedialog.askdirectory(
                parent=self, initialdir="/", title="Please select a directory"
            )
            if not dirname:
                return
            else:
                self.extracts_mode = False
                self.lvls_path = dirname
                self.load_editor()

        def load_extracts_lvls():
            if os.path.isdir(self.extracts_path):
                self.extracts_mode = True
                self.lvls_path = self.extracts_path
                self.load_editor()

        self.btn_lvl_extracts = ttk.Button(
            self.lvl_editor_start_canvas,
            text="Load From Extracts",
            command=load_extracts_lvls,
        )
        self.btn_lvl_extracts.grid(
            row=1, column=0, sticky="nswe", ipady=30, padx=(20, 20), pady=(10, 1)
        )

        self.btn_lvl_folder = ttk.Button(
            self.lvl_editor_start_canvas,
            text="Load Levels Folder",
            command=select_lvl_folder,
        )
        self.btn_lvl_folder.grid(
            row=2, column=0, sticky="nswe", ipady=30, padx=(20, 20), pady=(10, 10)
        )

    def on_load(self):
        self._sprite_fetcher = SpelunkySpriteFetcher(
            self.install_dir / "Mods/Extracted"
        )

    # Run when start screen option is selected
    def load_editor(self):
        self.show_console = False
        self.modlunky_ui.forget_console()
        self.save_needed = False
        self.last_selected_file = None
        self.tiles = None
        self.tiles_meta = None
        self.lvl_editor_start_canvas.grid_remove()
        self.columnconfigure(0, minsize=200)  # Column 0 = Level List
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)  # Column 1 = Everything Else
        self.rowconfigure(0, weight=1)  # Row 0 = List box / Label

        # Loads lvl Files
        self.tree_files = ttk.Treeview(
            self, selectmode="browse"
        )  # This tree shows all the lvl files loaded from the chosen dir
        self.tree_files.place(x=30, y=95)
        self.vsb_tree_files = ttk.Scrollbar(
            self, orient="vertical", command=self.tree_files.yview
        )
        self.vsb_tree_files.place(x=30 + 200 + 2, y=95, height=200 + 20)
        self.tree_files.configure(yscrollcommand=self.vsb_tree_files.set)
        self.tree_files["columns"] = ("1",)
        self.tree_files["show"] = "headings"
        self.tree_files.column("1", width=100, anchor="w")
        self.tree_files.heading("1", text="Level Files")
        self.my_list = sorted(os.listdir(self.lvls_path))
        self.tree_files.grid(row=0, column=0, rowspan=1, sticky="nswe")
        self.vsb_tree_files.grid(row=0, column=0, sticky="nse")

        # Loads list of all the lvl files in the left farthest treeview
        for file in self.my_list:
            if str(file).endswith(".lvl"):
                self.tree_files.insert("", "end", values=str(file), text=str(file))

        # Seperates Level Rules and Level Editor into two tabs
        self.tab_control = ttk.Notebook(self)
        self.tab_control.grid(row=0, column=1, rowspan=3, sticky="nwse")

        self.tab1 = ttk.Frame(self.tab_control)
        self.tab2 = ttk.Frame(self.tab_control)  # Tab 2 is the actual level editor

        self.button_back = tk.Button(
            self, text="Go Back", bg="black", fg="white", command=self.go_back
        )
        self.button_back.grid(row=1, column=0, sticky="nswe")

        self.button_save = tk.Button(
            self,
            text="Save",
            bg="purple",
            fg="white",
            command=self.save_changes,
        )
        self.button_save.grid(row=2, column=0, sticky="nswe")
        self.button_save["state"] = tk.DISABLED

        # Rules Tab
        self.tab_control.add(self.tab1, text="Rules")

        self.tab1.columnconfigure(0, weight=1)  # Column 1 = Everything Else
        self.tab1.rowconfigure(0, weight=1)  # Row 0 = List box / Label

        self.tree = RulesTree(
            self.tab1, self, selectmode="browse"
        )  # This tree shows rules parses from the lvl file
        self.tree.bind("<Double-1>", lambda e: self.on_double_click(self.tree))
        self.tree.place(x=30, y=95)
        # style = ttk.Style(self)
        self.vsb = ttk.Scrollbar(self.tab1, orient="vertical", command=self.tree.yview)
        self.vsb.place(x=30 + 200 + 2, y=95, height=200 + 20)
        self.tree.configure(yscrollcommand=self.vsb.set)
        self.tree["columns"] = ("1", "2", "3")
        self.tree["show"] = "headings"
        self.tree.column("1", width=100, anchor="w")
        self.tree.column("2", width=10, anchor="w")
        self.tree.column("3", width=100, anchor="w")
        self.tree.heading("1", text="Level Settings")
        self.tree.heading("2", text="Value")
        self.tree.heading("3", text="Notes")
        self.tree.grid(row=0, column=0, sticky="nwse")
        self.vsb.grid(row=0, column=1, sticky="nse")

        self.tree_chances_levels = RulesTree(
            self.tab1, self, selectmode="browse"
        )  # This tree shows rules parses from the lvl file
        self.tree_chances_levels.bind(
            "<Double-1>", lambda e: self.on_double_click(self.tree_chances_levels)
        )
        self.tree_chances_levels.place(x=30, y=95)
        # style = ttk.Style(self)
        self.vsb_chances_levels = ttk.Scrollbar(
            self.tab1, orient="vertical", command=self.tree_chances_levels.yview
        )
        self.vsb_chances_levels.place(x=30 + 200 + 2, y=95, height=200 + 20)
        self.tree_chances_levels.configure(yscrollcommand=self.vsb_chances_levels.set)
        self.tree_chances_levels["columns"] = ("1", "2", "3")
        self.tree_chances_levels["show"] = "headings"
        self.tree_chances_levels.column("1", width=100, anchor="w")
        self.tree_chances_levels.column("2", width=10, anchor="w")
        self.tree_chances_levels.column("3", width=100, anchor="w")
        self.tree_chances_levels.heading("1", text="Level Chances")
        self.tree_chances_levels.heading("2", text="Value")
        self.tree_chances_levels.heading("3", text="Notes")
        self.tree_chances_levels.grid(row=1, column=0, sticky="nwse")
        self.vsb_chances_levels.grid(row=1, column=1, sticky="nse")

        self.tree_chances_monsters = RulesTree(
            self.tab1, self, selectmode="browse"
        )  # This tree shows rules parses from the lvl file
        self.tree_chances_monsters.bind(
            "<Double-1>", lambda e: self.on_double_click(self.tree_chances_monsters)
        )
        self.tree_chances_monsters.place(x=30, y=95)
        # style = ttk.Style(self)
        self.vsb_chances_monsters = ttk.Scrollbar(
            self.tab1, orient="vertical", command=self.tree_chances_monsters.yview
        )
        self.vsb_chances_monsters.place(x=30 + 200 + 2, y=95, height=200 + 20)
        self.tree.configure(yscrollcommand=self.vsb_chances_monsters.set)
        self.tree_chances_monsters["columns"] = ("1", "2", "3")
        self.tree_chances_monsters["show"] = "headings"
        self.tree_chances_monsters.column("1", width=100, anchor="w")
        self.tree_chances_monsters.column("2", width=10, anchor="w")
        self.tree_chances_monsters.column("3", width=100, anchor="w")
        self.tree_chances_monsters.heading("1", text="Monster Chances")
        self.tree_chances_monsters.heading("2", text="Value")
        self.tree_chances_monsters.heading("3", text="Notes")
        self.tree_chances_monsters.grid(row=2, column=0, sticky="nwse")
        self.vsb_chances_monsters.grid(row=2, column=1, sticky="nse")

        # Level Editor Tab
        self.tab_control.add(self.tab2, text="Level Editor")
        self.tab2.columnconfigure(0, minsize=200)  # Column 0 = Level List
        self.tab2.columnconfigure(1, weight=1)  # Column 1 = Everything Else
        self.tab2.rowconfigure(2, weight=1)  # Row 0 = List box / Label

        self.tree_levels = LevelsTree(
            self.tab2, self, selectmode="browse"
        )  # This tree shows the rooms in the level editor
        self.tree_levels.place(x=30, y=95)
        self.vsb_tree_levels = ttk.Scrollbar(
            self.tab2, orient="vertical", command=self.tree_levels.yview
        )
        self.vsb_tree_levels.place(x=30 + 200 + 2, y=95, height=200 + 20)
        self.tree_levels.configure(yscrollcommand=self.vsb_tree_levels.set)
        self.my_list = os.listdir(
            self.install_dir / "Mods" / "Extracted" / "Data" / "Levels"
        )
        self.tree_levels.grid(row=0, column=0, rowspan=5, sticky="nswe")
        self.vsb_tree_levels.grid(row=0, column=0, rowspan=5, sticky="nse")

        self.mag = 50  # the size of each tiles in the grid; 50 is optimal
        self.rows = (
            15  # default values, could be set to none and still work I think lol
        )
        self.cols = (
            15  # default values, could be set to none and still work I think lol
        )

        self.canvas_grids = tk.Canvas(  # this is the main level editor grid
            self.tab2,
            bg="#292929",
        )
        self.canvas_grids.grid(row=0, column=1, rowspan=4, columnspan=8, sticky="nwse")

        self.canvas_grids.columnconfigure(2, weight=1)
        self.canvas_grids.rowconfigure(0, weight=1)

        self.scrollable_canvas_frame = tk.Frame(self.canvas_grids, bg="#343434")

        # offsets the screen so user can freely scroll around work area
        self.scrollable_canvas_frame.columnconfigure(
            0, minsize=int(int(self.screen_width) / 2)
        )
        self.scrollable_canvas_frame.columnconfigure(1, weight=1)
        self.scrollable_canvas_frame.columnconfigure(2, minsize=50)
        self.scrollable_canvas_frame.columnconfigure(
            4, minsize=int(int(self.screen_width) / 2)
        )
        self.scrollable_canvas_frame.rowconfigure(
            0, minsize=int(int(self.screen_height) / 2)
        )
        self.scrollable_canvas_frame.rowconfigure(1, weight=1)
        self.scrollable_canvas_frame.rowconfigure(2, minsize=100)
        self.scrollable_canvas_frame.rowconfigure(2, minsize=100)
        self.scrollable_canvas_frame.rowconfigure(
            4, minsize=int(int(self.screen_height) / 2)
        )

        self.scrollable_canvas_frame.grid(row=0, column=0, sticky="nwes")

        self.foreground_label = tk.Label(
            self.scrollable_canvas_frame,
            text="Foreground Area",
            fg="white",
            bg="#343434",
        )
        self.foreground_label.grid(row=2, column=1, sticky="nwse")
        self.foreground_label.grid_remove()

        self.background_label = tk.Label(
            self.scrollable_canvas_frame,
            text="Background Area",
            fg="white",
            bg="#343434",
        )
        self.background_label.grid(row=2, column=3, sticky="nwse")
        self.background_label.grid_remove()

        self.vbar = ttk.Scrollbar(
            self.tab2, orient="vertical", command=self.canvas_grids.yview
        )
        self.vbar.grid(row=0, column=2, rowspan=4, columnspan=7, sticky="nse")
        self.hbar = ttk.Scrollbar(
            self.tab2, orient="horizontal", command=self.canvas_grids.xview
        )
        self.hbar.grid(row=0, column=1, rowspan=4, columnspan=8, sticky="wes")

        self.canvas_grids.config(
            xscrollcommand=self.hbar.set, yscrollcommand=self.vbar.set
        )
        x_origin = self.canvas_grids.winfo_screenwidth() / 2
        y_origin = self.canvas_grids.winfo_screenheight() / 2
        self.canvas_grids.create_window(
            (x_origin, y_origin), window=self.scrollable_canvas_frame, anchor="center"
        )
        self.canvas_grids.bind("<Enter>", self._bind_to_mousewheel)
        self.canvas_grids.bind("<Leave>", self._unbind_from_mousewheel)
        self.scrollable_canvas_frame.bind(
            "<Configure>",
            lambda e: self.canvas_grids.configure(
                scrollregion=self.canvas_grids.bbox("all")
            ),
        )

        self.canvas = tk.Canvas(  # this is the main level editor grid
            self.scrollable_canvas_frame,
            bg="#343434",
        )
        self.canvas.grid(row=1, column=1)
        self.canvas.grid_remove()
        self.canvas_dual = tk.Canvas(  # this is for dual level, it shows the back area
            self.scrollable_canvas_frame,
            width=0,
            bg="yellow",
        )
        self.canvas_dual.grid(row=1, column=3, padx=(0, 50))
        self.canvas_dual.grid_remove()  # hides it for now
        self.dual_mode = False

        self.button_hide_tree = tk.Button(
            self.canvas_grids, text="<<", command=self.toggle_list_hide
        )
        self.button_hide_tree.grid(row=0, column=0, sticky="nw")

        self.button_replace = tk.Button(
            self.canvas_grids, text="Replace", command=self.replace_tiles_dia
        )
        self.button_replace.grid(row=0, column=1, sticky="nw")
        self.button_replace["state"] = tk.DISABLED

        self.button_clear = tk.Button(
            self.canvas_grids, text="Clear Canvas", command=self.clear_canvas
        )
        self.button_clear.grid(row=0, column=2, sticky="nw")
        self.button_clear["state"] = tk.DISABLED

        # the tile palletes are loaded into here as buttons with their image
        # as a tile and txt as their value to grab when needed
        self.tile_pallete = ScrollableFrame(self.tab2, text="Tile Pallete", width=50)
        self.tile_pallete.grid(row=2, column=9, columnspan=4, rowspan=1, sticky="swne")
        self.tile_pallete.scrollable_frame["width"] = 50

        # shows selected tile. Important because this is used for more than just user
        # convenience; we can grab the currently used tile here
        self.tile_label = tk.Label(
            self.tab2,
            text="Primary Tile:",
        )
        self.tile_label.grid(row=0, column=10, columnspan=1, sticky="we")
        # shows selected tile. Important because this is used for more than just user
        # convenience; we can grab the currently used tile here
        self.tile_label_secondary = tk.Label(
            self.tab2,
            text="Secondary Tile:",
        )
        self.tile_label_secondary.grid(row=1, column=10, columnspan=1, sticky="we")

        self.button_tilecode_del = tk.Button(
            self.tab2,
            text="Del",
            bg="red",
            fg="white",
            width=10,
            command=self.del_tilecode,
        )
        self.button_tilecode_del.grid(row=0, column=9, sticky="e")
        self.button_tilecode_del["state"] = tk.DISABLED

        self.button_tilecode_del_secondary = tk.Button(
            self.tab2,
            text="Del",
            bg="red",
            fg="white",
            width=10,
            command=self.del_tilecode_secondary,
        )
        self.button_tilecode_del_secondary.grid(row=1, column=9, sticky="e")
        self.button_tilecode_del_secondary["state"] = tk.DISABLED

        self.img_sel = ImageTk.PhotoImage(
            Image.open(
                BASE_DIR / "static/images/tilecodetextures.png"
            )  ########################################### set selected img
        )
        self.panel_sel = tk.Label(
            self.tab2, image=self.img_sel, width=50
        )  # shows selected tile image
        self.panel_sel.grid(row=0, column=11)
        self.panel_sel_secondary = tk.Label(
            self.tab2, image=self.img_sel, width=50
        )  # shows selected tile image
        self.panel_sel_secondary.grid(row=1, column=11)

        self.combobox = ttk.Combobox(self.tab2, height=20)
        self.combobox.grid(row=4, column=9, columnspan=1, sticky="nswe")
        self.combobox["state"] = tk.DISABLED
        self.combobox_alt = ttk.Combobox(self.tab2, height=40)
        self.combobox_alt.grid(row=4, column=10, columnspan=1, sticky="nswe")
        self.combobox_alt.grid_remove()
        self.combobox_alt["state"] = tk.DISABLED

        self.scale = tk.Scale(
            self.tab2, from_=0, to=100, orient=tk.HORIZONTAL, command=self.update_value
        )  # scale for the percent of a selected tile
        self.scale.grid(row=3, column=9, columnspan=2, sticky="we")
        self.scale.set(100)
        self.scale["state"] = tk.DISABLED

        self.button_tilecode_add = tk.Button(
            self.tab2,
            text="Add TileCode",
            bg="yellow",
            command=lambda: self.add_tilecode(
                str(self.combobox.get()), str(self.scale.get()), self.combobox_alt.get()
            ),
        )
        self.button_tilecode_add.grid(
            row=3, column=11, rowspan=2, columnspan=2, sticky="nswe"
        )

        self.var_ignore = tk.IntVar()
        self.var_flip = tk.IntVar()
        self.var_only_flip = tk.IntVar()
        self.var_dual = tk.IntVar()
        self.var_rare = tk.IntVar()
        self.var_hard = tk.IntVar()
        self.var_liquid = tk.IntVar()
        self.var_purge = tk.IntVar()
        self.checkbox_ignore = ttk.Checkbutton(
            self.tab2,
            text="Ignore",
            var=self.var_ignore,
            onvalue=1,
            offvalue=0,
            command=self.remember_changes,
        )
        self.checkbox_flip = ttk.Checkbutton(
            self.tab2,
            text="Flip",
            var=self.var_flip,
            onvalue=1,
            offvalue=0,
            command=self.remember_changes,
        )
        self.checkbox_only_flip = ttk.Checkbutton(
            self.tab2,
            text="Only Flip",
            var=self.var_only_flip,
            onvalue=1,
            offvalue=0,
            command=self.remember_changes,
        )
        self.checkbox_rare = ttk.Checkbutton(
            self.tab2,
            text="Rare",
            var=self.var_rare,
            onvalue=1,
            offvalue=0,
            command=self.remember_changes,
        )
        self.checkbox_hard = ttk.Checkbutton(
            self.tab2,
            text="Hard",
            var=self.var_hard,
            onvalue=1,
            offvalue=0,
            command=self.remember_changes,
        )
        self.checkbox_liquid = ttk.Checkbutton(
            self.tab2,
            text="Optimize Liquids",
            var=self.var_liquid,
            onvalue=1,
            offvalue=0,
            command=self.remember_changes,
        )
        self.checkbox_purge = ttk.Checkbutton(
            self.tab2,
            text="Purge",
            var=self.var_purge,
            onvalue=1,
            offvalue=0,
            command=self.remember_changes,
        )
        self.checkbox_dual = ttk.Checkbutton(
            self.tab2,
            text="Dual",
            var=self.var_dual,
            onvalue=1,
            offvalue=0,
            command=self.dual_toggle,
        )
        self.checkbox_dual.grid(row=4, column=1, sticky="w")
        self.checkbox_ignore.grid(row=4, column=2, sticky="w")
        self.checkbox_purge.grid(row=4, column=3, sticky="w")
        self.checkbox_rare.grid(row=4, column=4, sticky="w")
        self.checkbox_hard.grid(row=4, column=5, sticky="w")
        self.checkbox_flip.grid(row=4, column=6, sticky="w")
        self.checkbox_only_flip.grid(row=4, column=7, sticky="w")
        self.checkbox_liquid.grid(row=4, column=8, sticky="w")

        # the tilecodes are in the same order as the tiles in the image(50x50, left to right)
        self.texture_images = []

        # color_base = int(random.random())
        self.uni_tile_code_list = []
        self.tile_pallete_ref = []
        self.panel_sel["image"] = ImageTk.PhotoImage(self._sprite_fetcher.get("empty"))
        self.tile_label["text"] = "Primary Tile: " + "empty 0"
        self.panel_sel_secondary["image"] = ImageTk.PhotoImage(
            self._sprite_fetcher.get("empty")
        )
        self.tile_label_secondary["text"] = "Secondary Tile: " + "empty 0"

        self.draw_mode = []  # slight adjustments of textures for tile preview
        # 1 = lower half tile
        # 2 = draw from bottom left
        # 3 = center
        # 4 = center to the right
        # 5 = draw bottom left + raise 1 tile
        # 6 = position doors
        # 7 = draw bottom left + raise half tile
        # 8 = draw bottom left + lowere 1 tile
        # 9 = draw bottom left + raise 1 tile + move left 1 tile
        # 10 = draw bottom left + raise 1 tile + move left 1 tile
        # 11 = move left 1 tile
        # 12 = raise 1 tile
        self.draw_mode.append(["anubis", 2])
        self.draw_mode.append(["olmec", 5])
        self.draw_mode.append(["alienqueen", 7])
        self.draw_mode.append(["kingu", 2])
        self.draw_mode.append(["coffin", 2])
        self.draw_mode.append(["dog_sign", 2])
        self.draw_mode.append(["bunkbed", 2])
        self.draw_mode.append(["telescope", 2])
        self.draw_mode.append(["palace_table", 11])
        self.draw_mode.append(["palace_chandelier", 11])
        self.draw_mode.append(["moai_statue", 9])
        self.draw_mode.append(["mother_statue", 10])
        self.draw_mode.append(["empress_grave", 2])
        self.draw_mode.append(["empty_mech", 2])
        self.draw_mode.append(["olmecship", 7])
        self.draw_mode.append(["lavamander", 2])
        self.draw_mode.append(["mummy", 2])
        self.draw_mode.append(["yama", 2])
        self.draw_mode.append(["crown_statue", 7])
        self.draw_mode.append(["lamassu", 2])
        self.draw_mode.append(["madametusk", 2])
        self.draw_mode.append(["giant_frog", 3])
        self.draw_mode.append(["door", 2])
        self.draw_mode.append(["starting_exit", 2])
        self.draw_mode.append(["eggplant_door", 2])
        self.draw_mode.append(["door2", 6])
        self.draw_mode.append(["palace_entrance", 6])
        self.draw_mode.append(["door2_secret", 6])
        self.draw_mode.append(["ghist_door2", 6])
        self.draw_mode.append(["ghist_door", 2])
        self.draw_mode.append(["minister", 2])
        self.draw_mode.append(["storage_guy", 2])
        self.draw_mode.append(["idol", 4])
        self.draw_mode.append(["plasma_cannon", 4])
        self.draw_mode.append(["lockedchest", 4])
        self.draw_mode.append(["shopkeeper_vat", 12])

        combo_tile_ids = []
        for tile_info in VALID_TILE_CODES:
            combo_tile_ids.append(tile_info)

        self.combobox["values"] = sorted(combo_tile_ids, key=str.lower)
        self.combobox_alt["values"] = sorted(combo_tile_ids, key=str.lower)

        def canvas_click(event, canvas):  # when the level editor grid is clicked
            # Get rectangle diameters
            col_width = self.mag
            row_height = self.mag
            col = 0
            row = 0
            if canvas == self.canvas_dual:
                col = ((event.x + int(self.canvas["width"])) + col_width) // col_width
                row = event.y // row_height

                if (
                    col * self.mag < int(self.canvas["width"]) + self.mag
                    or col * self.mag > int(self.canvas["width"]) * 2 + self.mag
                ):
                    logger.debug("col out of bounds")
                    return

                if row * self.mag < 0 or row * self.mag > int(self.canvas["height"]):
                    logger.debug("row out of bounds")
                    return
            else:
                # Calculate column and row number
                col = event.x // col_width
                row = event.y // row_height

                if col * self.mag < 0 or col * self.mag > int(self.canvas["width"]):
                    logger.debug("col out of bounds")
                    return

                if row * self.mag < 0 or row * self.mag > int(self.canvas["height"]):
                    logger.debug("row out of bounds")
                    return
            # If the tile is not filled, create a rectangle
            if self.dual_mode:
                if int(col) == int((len(self.tiles[0]) - 1) / 2):
                    logger.debug("Middle of dual detected; not tile placed")
                    return

            x_coord_offset = 0
            y_coord_offset = 0
            img = None
            # height, width, channels = img.shape
            for tile_name_ref in self.draw_mode:
                if self.tile_label["text"].split(" ", 4)[2] == str(tile_name_ref[0]):
                    logger.debug(
                        "Applying custom anchor for %s",
                        self.tile_label["text"].split(" ", 4)[2],
                    )
                    for tile_ref in self.tile_pallete_ref_in_use:
                        if (
                            str(tile_ref[0].split(" ", 1)[0])
                            == self.tile_label["text"].split(" ", 4)[2]
                        ):
                            logger.debug("Found %s", tile_ref[0])
                            img = tile_ref[1]
                            x_coord_offset, y_coord_offset = self.adjust_texture_xy(
                                img.width(),
                                img.height(),
                                int(tile_name_ref[1]),
                            )

            canvas.delete(self.tiles[int(row)][int(col)])
            if canvas == self.canvas_dual:
                x2_coord = int(int(col) - ((len(self.tiles[0]) - 1) / 2) - 1)
                self.tiles[int(row)][int(col)] = canvas.create_image(
                    x2_coord * self.mag - x_coord_offset,
                    int(row) * self.mag - y_coord_offset,
                    image=self.panel_sel["image"],
                    anchor="nw",
                )
            else:
                self.tiles[int(row)][int(col)] = canvas.create_image(
                    int(col) * self.mag - x_coord_offset,
                    int(row) * self.mag - y_coord_offset,
                    image=self.panel_sel["image"],
                    anchor="nw",
                )
            self.tiles_meta[row][col] = self.tile_label["text"].split(" ", 4)[3]
            logger.debug(
                "%s replaced with %s",
                self.tiles_meta[row][col],
                self.tile_label["text"].split(" ", 4)[3],
            )
            self.remember_changes()  # remember changes made

        def canvas_click_secondary(event, canvas):
            # when the level editor grid is clicked
            # Get rectangle diameters
            col_width = self.mag
            row_height = self.mag
            col = 0
            row = 0
            if canvas == self.canvas_dual:
                col = ((event.x + int(self.canvas["width"])) + col_width) // col_width
                row = event.y // row_height

                if (
                    col * self.mag < int(self.canvas["width"]) + self.mag
                    or col * self.mag > int(self.canvas["width"]) * 2 + self.mag
                ):
                    logger.debug("col out of bounds")
                    return

                if row * self.mag < 0 or row * self.mag > int(self.canvas["height"]):
                    logger.debug("row out of bounds")
                    return
            else:
                # Calculate column and row number
                col = event.x // col_width
                row = event.y // row_height

                if col * self.mag < 0 or col * self.mag > int(self.canvas["width"]):
                    logger.debug("col out of bounds")
                    return

                if row * self.mag < 0 or row * self.mag > int(self.canvas["height"]):
                    logger.debug("row out of bounds")
                    return
            # If the tile is not filled, create a rectangle
            if self.dual_mode:
                if int(col) == int((len(self.tiles[0]) - 1) / 2):
                    logger.debug("Middle of dual detected; not tile placed")
                    return

            x_coord_offset = 0
            y_coord_offset = 0
            img = None
            for tile_name_ref in self.draw_mode:
                if self.tile_label_secondary["text"].split(" ", 4)[2] == str(
                    tile_name_ref[0]
                ):
                    logger.debug(
                        "Applying custom anchor for %s",
                        self.tile_label_secondary["text"].split(" ", 4)[2],
                    )
                    for tile_ref in self.tile_pallete_ref_in_use:
                        if (
                            str(tile_ref[0].split(" ", 1)[0])
                            == self.tile_label_secondary["text"].split(" ", 4)[2]
                        ):
                            logger.debug("Found %s", tile_ref[0])
                            img = tile_ref[1]
                            x_coord_offset, y_coord_offset = self.adjust_texture_xy(
                                img.width(),
                                img.height(),
                                int(tile_name_ref[1]),
                            )

            canvas.delete(self.tiles[int(row)][int(col)])
            if canvas == self.canvas_dual:
                x2_coord = int(int(col) - ((len(self.tiles[0]) - 1) / 2) - 1)
                self.tiles[row][col] = canvas.create_image(
                    x2_coord * self.mag - x_coord_offset,
                    int(row) * self.mag - y_coord_offset,
                    image=self.panel_sel_secondary["image"],
                    anchor="nw",
                )
            else:
                self.tiles[row][col] = canvas.create_image(
                    int(col) * self.mag - x_coord_offset,
                    int(row) * self.mag - y_coord_offset,
                    image=self.panel_sel_secondary["image"],
                    anchor="nw",
                )
            self.tiles_meta[row][col] = self.tile_label_secondary["text"].split(" ", 4)[
                3
            ]
            logger.debug(
                "%s replaced with %s",
                self.tiles_meta[row][col],
                self.tile_label["text"].split(" ", 4)[3],
            )
            self.remember_changes()  # remember changes made

        self.canvas.bind("<Button-1>", lambda event: canvas_click(event, self.canvas))
        self.canvas.bind(
            "<B1-Motion>", lambda event: canvas_click(event, self.canvas)
        )  # These second binds are so the user can hold down their mouse button when painting tiles
        self.canvas.bind(
            "<Button-3>", lambda event: canvas_click_secondary(event, self.canvas)
        )
        self.canvas.bind(
            "<B3-Motion>", lambda event: canvas_click_secondary(event, self.canvas)
        )  # These second binds are so the user can hold down their mouse button when painting tiles
        self.canvas_dual.bind(
            "<Button-1>", lambda event: canvas_click(event, self.canvas_dual)
        )
        self.canvas_dual.bind(
            "<B1-Motion>", lambda event: canvas_click(event, self.canvas_dual)
        )
        self.canvas_dual.bind(
            "<Button-3>", lambda event: canvas_click_secondary(event, self.canvas_dual)
        )
        self.canvas_dual.bind(
            "<B3-Motion>", lambda event: canvas_click_secondary(event, self.canvas_dual)
        )

        def tree_filesitemclick(_event):
            if self.save_needed and self.last_selected_file is not None:
                msg_box = tk.messagebox.askquestion(
                    "Continue?",
                    "You have unsaved changes to "
                    + str(self.tree_files.item(self.last_selected_file, option="text"))
                    + "\nContinue without saving?",
                    icon="warning",
                )
                if msg_box == "yes":
                    self.save_needed = False
                    self.button_save["state"] = tk.DISABLED
                    logger.debug("Entered new files witout saving")
                else:
                    self.tree_files.selection_set(self.last_selected_file)
                    return
            item_text = ""
            self.canvas.delete("all")
            self.canvas_dual.delete("all")
            self.canvas.grid_remove()
            self.canvas_dual.grid_remove()
            self.foreground_label.grid_remove()
            self.background_label.grid_remove()
            for item in self.tree_files.selection():
                self.last_selected_file = item
                item_text = self.tree_files.item(item, "text")
                self.read_lvl_file(item_text)

        self.tree_files.bind("<ButtonRelease-1>", tree_filesitemclick)

    def _on_mousewheel(self, event):
        scroll_dir = None
        if event.num == 5 or event.delta == -120:
            scroll_dir = 1
        elif event.num == 4 or event.delta == 120:
            scroll_dir = -1

        if scroll_dir is None:
            return

        if event.state & (1 << 0):  # Shift / Horizontal Scroll
            self._scroll_horizontal(scroll_dir)
        else:
            self._scroll_vertical(scroll_dir)

    def _scroll_vertical(self, scroll_dir):
        # If the scrollbar is max size don't bother scrolling
        if self.vbar.get() == (0.0, 1.0):
            return

        self.canvas_grids.yview_scroll(scroll_dir, "units")

    def _scroll_horizontal(self, scroll_dir):
        # If the scrollbar is max size don't bother scrolling
        if self.hbar.get() == (0.0, 1.0):
            return

        self.canvas_grids.xview_scroll(scroll_dir, "units")

    def _bind_to_mousewheel(self, _event):
        if "nt" in os.name:
            self.canvas_grids.bind_all("<MouseWheel>", self._on_mousewheel)
        else:
            self.canvas_grids.bind_all("<Button-4>", self._on_mousewheel)
            self.canvas_grids.bind_all("<Button-5>", self._on_mousewheel)

    def _unbind_from_mousewheel(self, _event):
        if "nt" in os.name:
            self.canvas_grids.unbind_all("<MouseWheel>")
        else:
            self.canvas_grids.unbind_all("<Button-4>")
            self.canvas_grids.unbind_all("<Button-5>")

    def tile_pick(
        self, _event, button_row, button_col
    ):  # When a tile is selected from the tile pallete
        selected_tile = self.tile_pallete.scrollable_frame.grid_slaves(
            button_row, button_col
        )[0]
        self.panel_sel["image"] = selected_tile["image"]
        self.tile_label["text"] = "Primary Tile: " + selected_tile["text"]

    def tile_pick_secondary(
        self, _event, button_row, button_col
    ):  # When a tile is selected from the tile pallete
        selected_tile = self.tile_pallete.scrollable_frame.grid_slaves(
            button_row, button_col
        )[0]
        self.panel_sel_secondary["image"] = selected_tile["image"]
        self.tile_label_secondary["text"] = "Secondary Tile: " + selected_tile["text"]

    def get_codes_left(self):
        codes = ""
        for code in self.usable_codes:
            codes += str(code)
        logger.debug("%s codes left (%s)", len(self.usable_codes), codes)

    def dual_toggle(self):
        item_iid = self.tree_levels.selection()[0]
        parent_iid = self.tree_levels.parent(item_iid)  # gets selected room
        if parent_iid:
            room_name = self.tree_levels.item(item_iid, option="text")
            room_rows = self.tree_levels.item(item_iid, option="values")
            new_room_data = []

            tags = []
            tags.append(r"\!ignore")
            tags.append(r"\!flip")
            tags.append(r"\!onlyflip")
            tags.append(r"\!dual")
            tags.append(r"\!rare")
            tags.append(r"\!hard")
            tags.append(r"\!liquid")
            tags.append(r"\!purge")

            if self.var_dual.get() == 1:  # converts room into dual
                new_room_data.append(r"\!dual")
                for row in room_rows:
                    tag_row = False
                    new_row = ""
                    for tag in tags:
                        if row.startswith(tag):
                            tag_row = True
                    if not tag_row:
                        new_row = row + " "
                        for _char in row:
                            new_row += "0"
                        new_room_data.append(str(new_row))
                    else:
                        new_room_data.append(str(row))
            else:  # converts room into none dual
                msg_box = tk.messagebox.askquestion(
                    "Delete Dual Room?",
                    "Un-dualing this room will delete your background layer. This is not recoverable.\nContinue?",
                    icon="warning",
                )
                if msg_box == "yes":
                    for row in room_rows:
                        tag_row = False
                        new_row = ""
                        for tag in tags:
                            if str(row).startswith(tag):
                                tag_row = True
                        if not tag_row:
                            new_row = str(row).split(" ", 2)[0]
                        else:
                            if not row.startswith(r"\!dual"):
                                new_row = row
                        if new_row != "":
                            new_room_data.append(str(new_row))

            edited = self.tree_levels.insert(
                parent_iid,
                self.tree_levels.index(item_iid),
                text=room_name,
                values=new_room_data,
            )
            # Remove it from the tree
            self.tree_levels.delete(item_iid)
            self.tree_levels.selection_set(edited)
            self.room_select(None)
            self.remember_changes()

    def save_changes(self):
        if self.save_needed:
            try:
                tags = []
                tags.append(r"\!ignore")
                tags.append(r"\!flip")
                tags.append(r"\!onlyflip")
                tags.append(r"\!dual")
                tags.append(r"\!rare")
                tags.append(r"\!hard")
                tags.append(r"\!liquid")
                tags.append(r"\!purge")
                tile_codes = TileCodes()
                level_chances = LevelChances()
                level_settings = LevelSettings()
                monster_chances = MonsterChances()
                level_templates = LevelTemplates()

                for tilecode in self.tile_pallete_ref_in_use:
                    tile_codes.set_obj(
                        TileCode(
                            name=tilecode[0].split(" ", 1)[0],
                            value=tilecode[0].split(" ", 1)[1],
                            comment="",
                        )
                    )

                bad_chars = ["[", "]", "'", '"']
                bad_chars_settings = ["[", "]", "'", '"', ","]
                for entry in self.tree.get_children():
                    values = self.tree.item(entry)["values"]
                    value_final = ""
                    for i in bad_chars_settings:
                        value_final = str(values[1]).replace(i, "")
                    level_settings.set_obj(
                        LevelSetting(
                            name=str(values[0]),
                            value=value_final,
                            comment=str(values[2]),
                        )
                    )

                for entry in self.tree_chances_monsters.get_children():
                    values = self.tree_chances_monsters.item(entry)["values"]
                    value_final = ""
                    for i in bad_chars:
                        value_final = str(values[1]).replace(i, "")
                    monster_chances.set_obj(
                        MonsterChance(
                            name=str(values[0]),
                            value=value_final,
                            comment=str(values[2]),
                        )
                    )

                for entry in self.tree_chances_levels.get_children():
                    values = self.tree_chances_levels.item(entry)["values"]
                    value_final = ""
                    for i in bad_chars:
                        value_final = str(values[1]).replace(i, "")
                    level_chances.set_obj(
                        LevelChance(
                            name=str(values[0]),
                            value=value_final,
                            comment=str(values[2]),
                        )
                    )

                for room_parent in self.tree_levels.get_children():
                    template_chunks = []
                    room_list_name = self.tree_levels.item(room_parent)["text"].split(
                        " ", 1
                    )[0]
                    room_list_comment = ""
                    if (
                        len(self.tree_levels.item(room_parent)["text"].split("//", 1))
                        > 1
                    ):
                        room_list_comment = self.tree_levels.item(room_parent)[
                            "text"
                        ].split("//", 1)[1]
                    for room in self.tree_levels.get_children(room_parent):
                        room_data = self.tree_levels.item(room, option="values")
                        room_name = self.tree_levels.item(room)["text"]
                        room_foreground = []
                        room_background = []
                        room_settings = []

                        for line in room_data:
                            row = []
                            back_row = []
                            tag_found = False
                            background_found = False
                            for tag in tags:
                                if str(line) == str(tag):  # this line is a tag
                                    tag_found = True
                            if not tag_found:
                                for char in str(line):
                                    if not background_found and str(char) != " ":
                                        row.append(str(char))
                                    elif background_found and str(char) != " ":
                                        back_row.append(str(char))
                                    elif char == " ":
                                        background_found = True
                            else:
                                room_settings.append(
                                    TemplateSetting(str(line.split("!", 1)[1]))
                                )
                                logger.debug("FOUND %s", line.split("!", 1)[1])

                            if not tag_found:
                                room_foreground.append(row)
                                if back_row != []:
                                    room_background.append(back_row)

                        template_chunks.append(
                            Chunk(
                                comment=room_name,
                                settings=room_settings,
                                foreground=room_foreground,
                                background=room_background,
                            )
                        )
                    level_templates.set_obj(
                        LevelTemplate(
                            name=room_list_name,
                            comment=room_list_comment,
                            chunks=template_chunks,
                        )
                    )
                level_file = LevelFile(
                    "",
                    level_settings,
                    tile_codes,
                    level_chances,
                    monster_chances,
                    level_templates,
                )
                path = None
                if not self.extracts_mode:
                    path = (
                        self.lvls_path
                        + "/"
                        + str(
                            self.tree_files.item(self.last_selected_file, option="text")
                        )
                    )
                else:
                    logger.debug("adding to overrides")
                    path = (
                        self.install_dir
                        / "Mods"
                        / "Overrides"
                        / str(
                            self.tree_files.item(self.last_selected_file, option="text")
                        )
                    )
                with Path(path).open("w", encoding="cp1252") as handle:
                    level_file.write(handle)
                self.save_needed = False
                self.button_save["state"] = tk.DISABLED
                logger.debug("Saved")
            except Exception:  # pylint: disable=broad-except
                logger.critical("Failed to save level: %s", tb_info())
                _msg_box = tk.messagebox.showerror(
                    "Continue?",
                    "Error saving..",
                )
        else:
            logger.debug("No changes to save")

    def remember_changes(self):  # remembers changes made to rooms
        try:
            item_iid = self.tree_levels.selection()[0]
            parent_iid = self.tree_levels.parent(item_iid)  # gets selected room
            if parent_iid:
                room_name = str(self.tree_levels.item(item_iid)["text"])
                # self.canvas.delete("all")
                # self.canvas_dual.delete("all")
                new_room_data = ""
                if int(self.var_dual.get()) == 1:
                    if new_room_data != "":
                        new_room_data += "\n"
                    new_room_data += r"\!dual"
                if int(self.var_purge.get()) == 1:
                    if new_room_data != "":
                        new_room_data += "\n"
                    new_room_data += r"\!purge"
                if int(self.var_flip.get()) == 1:
                    if new_room_data != "":
                        new_room_data += "\n"
                    new_room_data += r"\!flip"
                if int(self.var_only_flip.get()) == 1:
                    if new_room_data != "":
                        new_room_data += "\n"
                    new_room_data += r"\!onlyflip"
                if int(self.var_rare.get()) == 1:
                    if new_room_data != "":
                        new_room_data += "\n"
                    new_room_data += r"\!rare"
                if int(self.var_hard.get()) == 1:
                    if new_room_data != "":
                        new_room_data += "\n"
                    new_room_data += r"\!hard"
                if int(self.var_liquid.get()) == 1:
                    if new_room_data != "":
                        new_room_data += "\n"
                    new_room_data += r"\!liquid"
                if int(self.var_ignore.get()) == 1:
                    if new_room_data != "":
                        new_room_data += "\n"
                    new_room_data += r"\!ignore"

                for row in self.tiles_meta:
                    if new_room_data != "":
                        new_room_data += "\n"
                    for block in row:
                        if str(block) == "None":
                            new_room_data += str(" ")
                        else:
                            new_room_data += str(block)
                room_save = []
                for line in new_room_data.split("\n", 100):
                    room_save.append(line)
                # Put it back in with the upated values
                edited = self.tree_levels.insert(
                    parent_iid,
                    self.tree_levels.index(item_iid),
                    text=room_name,
                    values=room_save,
                )
                # Remove it from the tree
                self.tree_levels.delete(item_iid)
                self.tree_levels.selection_set(edited)
                # self.room_select(None)
                logger.debug("temp saved: \n%s", new_room_data)
                logger.debug("Changes remembered!")
                self.save_needed = True
                self.button_save["state"] = tk.NORMAL
        except Exception:  # pylint: disable=broad-except
            self.canvas.delete("all")
            self.canvas_dual.delete("all")
            self.canvas.grid_remove()
            self.canvas_dual.grid_remove()
            self.foreground_label.grid_remove()
            self.background_label.grid_remove()

    def toggle_list_hide(self):
        if self.button_hide_tree["text"] == "<<":
            self.tree_levels.grid_remove()
            self.vsb_tree_levels.grid_remove()
            self.tab2.columnconfigure(0, minsize=0)  # Column 0 = Level List
            self.button_hide_tree["text"] = ">>"
        else:
            self.tree_levels.grid()
            self.vsb_tree_levels.grid()
            self.tab2.columnconfigure(0, minsize=200)  # Column 0 = Level List
            self.button_hide_tree["text"] = "<<"

    def replace_tiles_dia(self):
        # Set up window
        win = tk.Toplevel()
        win.title("Replace Tiles")
        if "nt" in os.name:
            win.attributes("-toolwindow", True)
        else:
            win.attributes("-alpha", True)
        self.center(win)

        replacees = []
        for tile in self.tile_pallete_ref_in_use:
            replacees.append(str(tile[0]))

        combo_replace = ttk.Combobox(win, height=20)
        combo_replace["values"] = replacees
        combo_replace.grid(row=0, column=1, columnspan=1)
        col1_lbl = tk.Label(win, text="Replace all ")
        col1_lbl.grid(row=0, column=0)
        combo_replacer = ttk.Combobox(win, height=20)
        combo_replacer["values"] = replacees
        combo_replacer.grid(row=0, column=3, columnspan=1)
        col2_lbl = tk.Label(win, text=" with ")
        col2_lbl.grid(row=0, column=2)

        def update_then_destroy():
            if (
                str(combo_replace.get().split(" ", 1)[0]) != "empty"
                and combo_replace.get() != ""
                and combo_replacer.get() != ""
            ):
                self.replace_tiles(
                    str(combo_replace.get().split(" ", 1)[1]),
                    str(combo_replacer.get().split(" ", 1)[1]),
                )
                win.destroy()

        ok_button = tk.Button(win, text="Replace")
        ok_button.bind("<Button-1>", lambda e: update_then_destroy())
        ok_button.grid(row=2, column=1)

        cancel_button = tk.Button(win, text="Cancel")
        cancel_button.bind("<Button-1>", lambda c: win.destroy())
        cancel_button.grid(row=2, column=2)

    def replace_tiles(self, tile, new_tile):
        for room_parent in self.tree_levels.get_children():
            for room in self.tree_levels.get_children(room_parent):
                room_data = []
                room_name = self.tree_levels.item(room, option="text")
                room_rows = self.tree_levels.item(room, option="values")
                for row in room_rows:
                    new_row = ""
                    if not str(row).startswith(r"\!"):
                        for replace_code in row:
                            if replace_code == str(tile):
                                replace_code = str(new_tile)
                                new_row += str(new_tile)
                            else:
                                new_row += str(replace_code)
                    else:
                        new_row = str(row)
                    room_data.append(new_row)
                # Put it back in with the upated values
                edited = self.tree_levels.insert(
                    room_parent,
                    self.tree_levels.index(room),
                    text=str(room_name),
                    values=room_data,
                )
                # Remove it from the tree
                self.tree_levels.delete(room)
                if room == self.last_selected_room:
                    self.tree_levels.selection_set(edited)
                    self.last_selected_room = edited
                    self.room_select(None)

    def clear_canvas(self):
        msg_box = tk.messagebox.askquestion(
            "Clear Canvases?",
            "Completelt clear your canvas? This isn't recoverable.",
            icon="warning",
        )
        if msg_box == "yes":
            row_count = 0
            for row in self.tiles_meta:
                col_count = 0
                for col in row:
                    self.tiles_meta[int(row_count)][int(col_count)] = "0"
                    col_count = col_count + 1
                row_count = row_count + 1
            self.remember_changes()  # remember changes made

    def del_tilecode(self):
        msg_box = tk.messagebox.askquestion(
            "Delete Tilecode?",
            "Are you sure you want to delete this Tilecode?\nAll of its placements will be replaced with air",
            icon="warning",
        )
        if msg_box == "yes":
            tile_id = self.tile_label["text"].split(" ", 3)[2]
            tile_code = self.tile_label["text"].split(" ", 3)[3]
            if tile_id == r"empty":
                tkMessageBox.showinfo("Uh Oh!", "Can't delete empty!")
                return

            for room_parent in self.tree_levels.get_children():
                for room in self.tree_levels.get_children(room_parent):
                    room_data = []
                    room_name = self.tree_levels.item(room, option="text")
                    room_rows = self.tree_levels.item(room, option="values")
                    for row in room_rows:
                        new_row = ""
                        if not str(row).startswith(r"\!"):
                            for replace_code in row:
                                if replace_code == tile_code:
                                    replace_code = "0"
                                    new_row += "0"
                                else:
                                    new_row += str(replace_code)
                        else:
                            new_row = str(row)
                        room_data.append(new_row)
                    # Put it back in with the upated values
                    edited = self.tree_levels.insert(
                        room_parent,
                        self.tree_levels.index(room),
                        text=str(room_name),
                        values=room_data,
                    )
                    # Remove it from the tree
                    self.tree_levels.delete(room)
                    if room == self.last_selected_room:
                        self.tree_levels.selection_set(edited)
                        self.last_selected_room = edited
                        self.room_select(None)
            logger.debug("Replaced %s in all rooms with air/empty", tile_id)

            self.usable_codes.append(str(tile_code))
            logger.debug("%s is now available for use", tile_code)
            # adds tilecode back to list to be reused
            for id_ in self.tile_pallete_ref_in_use:
                if str(tile_id) == str(id_[0].split(" ", 2)[0]):
                    self.tile_pallete_ref_in_use.remove(id_)
                    logger.debug("Deleted %s", tile_id)
            self.populate_tilecode_pallete()
            new_selection = self.tile_pallete_ref_in_use[0]
            if str(self.tile_label["text"]).split(" ", 3)[2] == tile_id:
                self.tile_label["text"] = (
                    "Primary Tile: "
                    + str(new_selection[0]).split(" ", 2)[0]
                    + " "
                    + str(new_selection[0]).split(" ", 2)[1]
                )
                self.panel_sel["image"] = new_selection[1]
            if str(self.tile_label_secondary["text"]).split(" ", 3)[2] == tile_id:
                self.tile_label_secondary["text"] = (
                    "Secondary Tile: "
                    + str(new_selection[0]).split(" ", 2)[0]
                    + " "
                    + str(new_selection[0]).split(" ", 2)[1]
                )
                self.panel_sel_secondary["image"] = new_selection[1]

            self.get_codes_left()
            self.save_needed = True
            self.button_save["state"] = tk.NORMAL
        else:
            return

    def del_tilecode_secondary(self):
        msg_box = tk.messagebox.askquestion(
            "Delete Tilecode?",
            "Are you sure you want to delete this Tilecode?\nAll of its placements will be replaced with air",
            icon="warning",
        )
        if msg_box == "yes":
            tile_id = self.tile_label_secondary["text"].split(" ", 3)[2]
            tile_code = self.tile_label_secondary["text"].split(" ", 3)[3]
            if tile_id == r"empty":
                tkMessageBox.showinfo("Uh Oh!", "Can't delete empty!")
                return

            for room_parent in self.tree_levels.get_children():
                for room in self.tree_levels.get_children(room_parent):
                    room_data = []
                    room_name = self.tree_levels.item(room, option="text")
                    room_rows = self.tree_levels.item(room, option="values")
                    for row in room_rows:
                        new_row = ""
                        if not str(row).startswith(r"\!"):
                            for replace_code in row:
                                if replace_code == tile_code:
                                    replace_code = "0"
                                    new_row += "0"
                                else:
                                    new_row += str(replace_code)
                        else:
                            new_row = str(row)
                        room_data.append(new_row)
                    # Put it back in with the upated values
                    edited = self.tree_levels.insert(
                        room_parent,
                        self.tree_levels.index(room),
                        text=str(room_name),
                        values=room_data,
                    )
                    # Remove it from the tree
                    self.tree_levels.delete(room)
                    if room == self.last_selected_room:
                        self.tree_levels.selection_set(edited)
                        self.last_selected_room = edited
                        self.room_select(None)
            logger.debug("Replaced %s in all rooms with air/empty", tile_code)

            self.usable_codes.append(str(tile_code))
            logger.debug("%s is now available for use", tile_code)
            # adds tilecode back to list to be reused
            for id_ in self.tile_pallete_ref_in_use:
                if str(tile_id) == str(id_[0].split(" ", 2)[0]):
                    self.tile_pallete_ref_in_use.remove(id_)
                    logger.debug("Deleted %s", tile_id)
            self.populate_tilecode_pallete()
            new_selection = self.tile_pallete_ref_in_use[0]
            if str(self.tile_label["text"]).split(" ", 3)[2] == tile_id:
                self.tile_label["text"] = (
                    "Primary Tile: "
                    + str(new_selection[0]).split(" ", 2)[0]
                    + " "
                    + str(new_selection[0]).split(" ", 2)[1]
                )
                self.panel_sel["image"] = new_selection[1]
            if str(self.tile_label_secondary["text"]).split(" ", 3)[2] == tile_id:
                self.tile_label_secondary["text"] = (
                    "Secondary Tile: "
                    + str(new_selection[0]).split(" ", 2)[0]
                    + " "
                    + str(new_selection[0]).split(" ", 2)[1]
                )
                self.panel_sel_secondary["image"] = new_selection[1]

            self.get_codes_left()
            self.save_needed = True
            self.button_save["state"] = tk.NORMAL
        else:
            return

    def add_tilecode(self, tile, percent, alt_tile):
        usable_code = None

        invalid_tilecodes = []
        if tile not in VALID_TILE_CODES:
            invalid_tilecodes.append(tile)

        if alt_tile not in VALID_TILE_CODES:
            invalid_tilecodes.append(alt_tile)

        if invalid_tilecodes:
            tkMessageBox.showinfo(
                "Uh Oh!",
                f"You've entered invalid tilecodes: {', '.join(invalid_tilecodes)}",
            )
            return

        new_tile_code = tile
        if int(percent) < 100:
            new_tile_code += "%" + percent
            # Have to use a temporary directory due to TCL/Tkinter is trying to write
            # to a file name, not a file handle, and windows doesn't support sharing the
            # file between processes
            if alt_tile != "empty":
                new_tile_code += "%" + alt_tile

        tile_image = ImageTk.PhotoImage(
            self.get_texture(new_tile_code, self.lvl_biome, self.lvl)
        )

        # compares tile id to tile ids in pallete list
        for palette_tile in self.tile_pallete_ref_in_use:
            palette_tile = palette_tile[0].split()[0].strip()
            if new_tile_code == palette_tile:
                tkMessageBox.showinfo("Uh Oh!", "You already have that!")
                return

        if len(self.usable_codes) > 0:
            usable_code = self.usable_codes[0]
            for code in self.usable_codes:
                if code == usable_code:
                    self.usable_codes.remove(code)
        else:
            tkMessageBox.showinfo(
                "Uh Oh!", "You've reached the tilecode limit; delete some to add more"
            )
            return

        count_row = 0
        count_col = 0
        for _ in self.tile_pallete_ref_in_use:
            if count_col == 7:
                count_col = -1
                count_row = count_row + 1
            count_col = count_col + 1

        ref_tile = []
        ref_tile.append(new_tile_code + " " + str(usable_code))
        ref_tile.append(tile_image)
        self.tile_pallete_ref_in_use.append(ref_tile)
        new_tile = tk.Button(
            self.tile_pallete.scrollable_frame,
            text=str(
                new_tile_code + " " + str(usable_code)
            ),  # keep seperate by space cause I use that for splitting
            width=40,
            height=40,
            image=tile_image,
        )
        new_tile.grid(row=count_row, column=count_col)
        new_tile.bind(
            "<Button-1>",
            lambda event, r=count_row, c=count_col: self.tile_pick(event, r, c),
        )
        new_tile.bind(
            "<Button-3>",
            lambda event, r=count_row, c=count_col: self.tile_pick_secondary(
                event, r, c
            ),
        )
        self.get_codes_left()
        self.save_needed = True
        self.button_save["state"] = tk.NORMAL

    def on_double_click(self, tree_view):
        # First check if a blank space was selected
        entry_index = tree_view.focus()
        if entry_index == "":
            return

        # Set up window
        win = tk.Toplevel()
        win.title("Edit Entry")
        if "nt" in os.name:
            win.attributes("-toolwindow", True)
        else:
            win.attributes("-alpha", True)
        self.center(win)

        ####
        # Set up the window's other attributes and geometry
        ####

        # Grab the entry's values
        for child in tree_view.get_children():
            if child == entry_index:
                values = tree_view.item(child)["values"]
                break

        col1_lbl = tk.Label(win, text="Entry: ")
        col1_ent = tk.Entry(win)
        col1_ent.insert(0, values[0])  # Default is column 1's current value
        col1_lbl.grid(row=0, column=0)
        col1_ent.grid(row=0, column=1)

        col2_lbl = tk.Label(win, text="Value: ")
        col2_ent = tk.Entry(win)
        col2_ent.insert(0, values[1])  # Default is column 2's current value
        col2_lbl.grid(row=0, column=2)
        col2_ent.grid(row=0, column=3)

        col3_lbl = tk.Label(win, text="Note: ")
        col3_ent = tk.Entry(win)
        col3_ent.insert(0, values[2])  # Default is column 3's current value
        col3_lbl.grid(row=0, column=4)
        col3_ent.grid(row=0, column=5)

        def update_then_destroy():
            if self.confirm_entry(
                tree_view, col1_ent.get(), col2_ent.get(), col3_ent.get()
            ):
                win.destroy()
                self.save_needed = True
                self.button_save["state"] = tk.NORMAL

        ok_button = tk.Button(win, text="Ok")
        ok_button.bind("<Button-1>", lambda e: update_then_destroy())
        ok_button.grid(row=1, column=2)

        cancel_button = tk.Button(win, text="Cancel")
        cancel_button.bind("<Button-1>", lambda c: win.destroy())
        cancel_button.grid(row=1, column=4)

    def confirm_entry(self, tree_view, entry1, entry2, entry3):
        ####
        # Whatever validation you need
        ####

        # Grab the current index in the tree
        current_index = tree_view.index(tree_view.focus())

        # Remove it from the tree
        self.delete_current_entry(tree_view)

        # Put it back in with the upated values
        tree_view.insert("", current_index, values=(entry1, entry2, entry3))
        self.save_needed = True

        return True

    def delete_current_entry(self, tree_view):
        curr = tree_view.focus()

        if curr == "":
            return

        tree_view.delete(curr)
        self.save_needed = True
        self.button_save["state"] = tk.NORMAL

    def center(self, toplevel):
        toplevel.update_idletasks()

        # Tkinter way to find the screen resolution
        # screen_width = toplevel.winfo_screenwidth()
        # screen_height = toplevel.winfo_screenheight()

        # find the screen resolution
        screen_width = int(self.screen_width)
        screen_height = int(self.screen_height)

        size = tuple(int(_) for _ in toplevel.geometry().split("+")[0].split("x"))
        x_coord = screen_width / 2 - size[0] / 2
        y_coord = screen_height / 2 - size[1] / 2

        toplevel.geometry("+%d+%d" % (x_coord, y_coord))

    def populate_tilecode_pallete(self):
        # resets tile pallete to add them all back without the deleted one
        for widget in self.tile_pallete.scrollable_frame.winfo_children():
            widget.destroy()
        count_row = 0
        count_col = -1
        for tile_keep in self.tile_pallete_ref_in_use:
            if count_col == 7:
                count_col = -1
                count_row = count_row + 1
            count_col = count_col + 1

            new_tile = tk.Button(
                self.tile_pallete.scrollable_frame,
                text=str(tile_keep[0].split(" ", 2)[0])
                + " "
                + str(
                    tile_keep[0].split(" ", 2)[1]
                ),  # keep seperate by space cause I use that for splitting
                width=40,
                height=40,
                image=tile_keep[1],
            )
            new_tile.grid(row=count_row, column=count_col)
            new_tile.bind(
                "<Button-1>",
                lambda event, r=count_row, c=count_col: self.tile_pick(event, r, c),
            )
            new_tile.bind(
                "<Button-3>",
                lambda event, r=count_row, c=count_col: self.tile_pick_secondary(
                    event, r, c
                ),
            )

    def go_back(self):
        msg_box = tk.messagebox.askquestion(
            "Exit Editor?",
            "Exit editor and return to start screen?\n Load data will be lost.",
            icon="warning",
        )
        if msg_box == "yes":
            self.lvl_editor_start_canvas.grid()
            self.tab_control.grid_remove()
            self.tree_files.grid_remove()
            # Resets widgets
            self.scale["state"] = tk.DISABLED
            self.button_replace["state"] = tk.DISABLED
            self.button_clear["state"] = tk.DISABLED
            self.combobox["state"] = tk.DISABLED
            self.combobox_alt["state"] = tk.DISABLED
            self.button_tilecode_del["state"] = tk.DISABLED
            self.button_tilecode_del_secondary["state"] = tk.DISABLED
            self.canvas.delete("all")
            self.canvas_dual.delete("all")
            self.canvas.grid_remove()
            self.canvas_dual.grid_remove()
            self.foreground_label.grid_remove()
            self.background_label.grid_remove()
            self.button_back.grid_remove()
            self.button_save.grid_remove()
            self.vsb_tree_files.grid_remove()
            # removes any old tiles that might be there from the last file
            for widget in self.tile_pallete.scrollable_frame.winfo_children():
                widget.destroy()

    def update_value(self, _event):
        if int(self.scale.get()) == 100:
            self.combobox_alt.grid_remove()
            self.combobox.grid(columnspan=2)
        else:
            self.combobox.grid(columnspan=1)
            self.combobox_alt.grid()

    def _draw_grid(self, cols, rows, canvas, dual):
        # resizes canvas for grids
        canvas["width"] = (self.mag * cols) - 3
        canvas["height"] = (self.mag * rows) - 3

        if not dual:  # applies normal bg image settings to main grid
            self.cur_lvl_bg_path = (
                self.lvl_bg_path
            )  # store as a temp dif variable so it can switch back to the normal bg when needed

            file_id = self.tree_files.selection()[0]
            room_item = self.tree_levels.selection()[0]
            room_id = self.tree_levels.parent(
                room_item
            )  # checks which room is being opened to see if a special bg is needed
            factor = 1.0  # keeps image the same
            if self.lvl_bg_path == self.textures_dir / "bg_ice.png" and str(
                self.tree_levels.item(room_id, option="text")
            ).startswith(
                r"\.setroom1"
            ):  # mothership rooms are setroom10-1 to setroom13-2
                self.cur_lvl_bg_path = self.textures_dir / "bg_mothership.png"
            elif str(self.tree_files.item(file_id, option="text")).startswith(
                "blackmark"
            ):
                factor = 2.5  # brightens the image for black market
            elif (
                str(self.tree_files.item(file_id, option="text")).startswith("generic")
                or str(self.tree_files.item(file_id, option="text")).startswith(
                    "cosmic"
                )
                or str(self.tree_files.item(file_id, option="text")).startswith("duat")
                or str(self.tree_files.item(file_id, option="text")).startswith(
                    "palace"
                )
                or str(self.tree_files.item(file_id, option="text")).startswith(
                    "ending_hard"
                )
                or str(self.tree_files.item(file_id, option="text")).startswith(
                    "challenge_m"
                )
                or str(self.tree_files.item(file_id, option="text")).startswith(
                    "challenge_st"
                )
            ):
                factor = 0  # darkens the image for cosmic ocean and duat and others

            image = Image.open(self.cur_lvl_bg_path).convert("RGBA")
            image = image.resize(
                (int(canvas["width"]), int(canvas["height"])), Image.BILINEAR
            )  ## The (250, 250) is (height, width)
            enhancer = ImageEnhance.Brightness(image)

            self.im_output = enhancer.enhance(factor)

            self.lvl_bg = ImageTk.PhotoImage(self.im_output)
            canvas.create_image(0, 0, image=self.lvl_bg, anchor="nw")
        else:  # applies special image settings if working with dual grid
            self.lvl_bgbg_path = (
                self.lvl_bg_path
            )  # Creates seperate image path variable for bgbg image

            file_id = self.tree_files.selection()[0]
            room_item = self.tree_levels.selection()[0]
            room_id = self.tree_levels.parent(
                room_item
            )  # checks which room is being opened to see if a special bg is needed
            factor = 0.6  # darkens the image
            if self.lvl_bg_path == self.textures_dir / "bg_ice.png":
                if str(self.tree_levels.item(room_id, option="text")).startswith(
                    r"\.mothership"
                ):
                    self.lvl_bgbg_path = self.textures_dir / "bg_mothership.png"
                    factor = 1.0  # keeps image the same
                else:
                    factor = 2.5  # brightens the image for ices caves
            elif str(self.tree_files.item(file_id, option="text")).startswith(
                "blackmark"
            ):
                factor = 2.5  # brightens the image for black market
            elif (
                str(self.tree_files.item(file_id, option="text")).startswith("generic")
                or str(self.tree_files.item(file_id, option="text")).startswith(
                    "cosmic"
                )
                or str(self.tree_files.item(file_id, option="text")).startswith("duat")
                or str(self.tree_files.item(file_id, option="text")).startswith(
                    "palace"
                )
                or str(self.tree_files.item(file_id, option="text")).startswith(
                    "ending_hard"
                )
                or str(self.tree_files.item(file_id, option="text")).startswith(
                    "challenge_m"
                )
                or str(self.tree_files.item(file_id, option="text")).startswith(
                    "challenge_st"
                )
            ):
                factor = 0  # darkens the image for cosmic ocean and duat and others

            image_dual = Image.open(self.lvl_bgbg_path).convert("RGBA")
            image_dual = image_dual.resize(
                (int(canvas["width"]), int(canvas["height"])), Image.BILINEAR
            )  ## The (250, 250) is (height, width)
            enhancer = ImageEnhance.Brightness(image_dual)

            self.im_output_dual = enhancer.enhance(factor)

            self.lvl_bgbg = ImageTk.PhotoImage(self.im_output_dual)
            canvas.create_image(0, 0, image=self.lvl_bgbg, anchor="nw")

        # finishes by drawing grid on top
        for i in range(0, cols + 2):
            canvas.create_line(
                (i) * self.mag,
                0,
                (i) * self.mag,
                (rows) * self.mag,
                fill="#F0F0F0",
            )
        for i in range(0, rows):
            canvas.create_line(
                0,
                (i) * self.mag,
                self.mag * (cols + 2),
                (i) * self.mag,
                fill="#F0F0F0",
            )

    def room_select(self, _event):  # Loads room when click if not parent node
        self.dual_mode = False
        item_iid = self.tree_levels.selection()[0]
        parent_iid = self.tree_levels.parent(item_iid)
        if parent_iid:
            self.last_selected_room = item_iid
            self.canvas.delete("all")
            self.canvas_dual.delete("all")
            current_settings = self.tree_levels.item(item_iid, option="values")[
                0
            ]  # Room settings
            current_room = self.tree_levels.item(
                item_iid, option="values"
            )  # Room foreground
            current_room_tiles = []
            current_settings = []

            for cr_line in current_room:
                if str(cr_line).startswith(r"\!"):
                    logger.debug("found tag %s", cr_line)
                    current_settings.append(cr_line)
                else:
                    logger.debug("appending %s", cr_line)
                    current_room_tiles.append(str(cr_line))
                    for char in str(cr_line):
                        if str(char) == " ":
                            self.dual_mode = True

            if r"\!dual" in current_settings:
                self.dual_mode = True
                self.var_dual.set(1)
            else:
                self.dual_mode = False
                self.var_dual.set(0)

            if r"\!flip" in current_settings:
                self.var_flip.set(1)
            else:
                self.var_flip.set(0)

            if r"\!purge" in current_settings:
                self.var_purge.set(1)
            else:
                self.var_purge.set(0)

            if r"\!onlyflip" in current_settings:
                self.var_only_flip.set(1)
            else:
                self.var_only_flip.set(0)

            if r"\!ignore" in current_settings:
                self.var_ignore.set(1)
            else:
                self.var_ignore.set(0)

            if r"\!rare" in current_settings:
                self.var_rare.set(1)
            else:
                self.var_rare.set(0)

            if r"\!hard" in current_settings:
                self.var_hard.set(1)
            else:
                self.var_hard.set(0)

            if r"\!liquid" in current_settings:
                self.var_liquid.set(1)
            else:
                self.var_liquid.set(0)

            self.rows = len(current_room_tiles)
            self.cols = len(str(current_room_tiles[0]))

            # self.mag = self.canvas.winfo_height() / self.rows - 30
            if not self.dual_mode:
                self._draw_grid(
                    self.cols, self.rows, self.canvas, False
                )  # cols rows canvas dual(True/False)
                self.canvas_dual["width"] = 0
                self.canvas_dual["height"] = 0
                self.canvas.grid()
                self.canvas_dual.grid_remove()  # hides it for now
                self.foreground_label.grid_remove()
                self.background_label.grid_remove()
            else:
                self.canvas.grid()
                self.canvas_dual.grid()  # brings it back
                self._draw_grid(
                    int((self.cols - 1) / 2), self.rows, self.canvas, False
                )  # cols rows canvas dual(True/False)
                self._draw_grid(
                    int((self.cols - 1) / 2), self.rows, self.canvas_dual, True
                )
                self.foreground_label.grid()
                self.background_label.grid()

            # Create a grid of None to store the references to the tiles
            self.tiles = [
                [None for _ in range(self.cols)] for _ in range(self.rows)
            ]  # tile image displays
            self.tiles_meta = [
                [None for _ in range(self.cols)] for _ in range(self.rows)
            ]  # meta for tile

            currow = -1
            curcol = 0
            for room_row in current_room_tiles:
                curcol = 0
                currow = currow + 1
                tile_image = None
                logger.debug("Room row: %s", room_row)
                for block in str(room_row):
                    if str(block) != " ":
                        tile_name = ""
                        for _pallete_block in self.tile_pallete_ref_in_use:
                            tiles = [
                                c
                                for c in self.tile_pallete_ref_in_use
                                if str(" " + block) in str(c[0])
                            ]
                            if tiles:
                                tile_image = tiles[-1][1]
                                tile_name = str(tiles[-1][0]).split(" ", 1)[0]
                            else:
                                # There's a missing tile id somehow
                                logger.debug("%s Not Found", block)
                        if self.dual_mode and curcol > int((self.cols - 1) / 2):
                            x2_coord = int(curcol - ((self.cols - 1) / 2) - 1)
                            x_coord = 0
                            y_coord = 0
                            for tile_name_ref in self.draw_mode:
                                if tile_name == str(tile_name_ref[0]):
                                    x_coord, y_coord = self.adjust_texture_xy(
                                        tile_image.width(),
                                        tile_image.height(),
                                        tile_name_ref[1],
                                    )
                            self.tiles[currow][curcol] = self.canvas_dual.create_image(
                                x2_coord * self.mag - x_coord,
                                currow * self.mag - y_coord,
                                image=tile_image,
                                anchor="nw",
                            )
                            _coords = (
                                x2_coord * self.mag,
                                currow * self.mag,
                                x2_coord * self.mag + 50,
                                currow * self.mag + 50,
                            )
                            self.tiles_meta[currow][curcol] = block
                        else:
                            x_coord = 0
                            y_coord = 0
                            for tile_name_ref in self.draw_mode:
                                if tile_name == str(tile_name_ref[0]):
                                    x_coord, y_coord = self.adjust_texture_xy(
                                        tile_image.width(),
                                        tile_image.height(),
                                        tile_name_ref[1],
                                    )
                            self.tiles[currow][curcol] = self.canvas.create_image(
                                curcol * self.mag - x_coord,
                                currow * self.mag - y_coord,
                                image=tile_image,
                                anchor="nw",
                            )
                            _coords = (
                                curcol * self.mag,
                                currow * self.mag,
                                curcol * self.mag + 50,
                                currow * self.mag + 50,
                            )
                            self.tiles_meta[currow][curcol] = block
                    curcol = curcol + 1
        self.button_clear["state"] = tk.NORMAL

    def read_lvl_file(self, lvl):
        self.last_selected_room = None
        self.usable_codes_string = (
            r"""!"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\]^_`"""
            r"""abcdefghijklmnopqrstuvwxyz{|}~€‚ƒ„…†‡ˆ‰Š‹Œ Ž‘’“”•–—™š›œžŸ¡¢£¤¥¦§"""
            r"""¨©ª«¬-®¯°±²³´µ¶·¸¹°»¼½¾¿ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞßàáâãäåæç"""
            r"""èéêëìíîïðñòóôõö÷øùúûüýþÿ"""
        )
        self.usable_codes = []
        for code in self.usable_codes_string:
            self.usable_codes.append(code)

        # removes any old tiles that might be there from the last file
        for widget in self.tile_pallete.scrollable_frame.winfo_children():
            widget.destroy()

        # removes any old rules that might be there from the last file
        for i in self.tree_chances_levels.get_children():
            self.tree_chances_levels.delete(i)

        # removes any old rules that might be there from the last file
        for i in self.tree_chances_monsters.get_children():
            self.tree_chances_monsters.delete(i)

        # removes any old rules that might be there from the last file
        for i in self.tree.get_children():
            self.tree.delete(i)

        self.tree.delete(*self.tree.get_children())
        self.tree_levels.delete(*self.tree_levels.get_children())

        # Enables widgets to use
        self.scale["state"] = tk.NORMAL
        self.combobox["state"] = tk.NORMAL
        self.combobox_alt["state"] = tk.NORMAL
        self.button_tilecode_del["state"] = tk.NORMAL
        self.button_tilecode_del_secondary["state"] = tk.NORMAL
        self.button_replace["state"] = tk.NORMAL

        self.combobox_alt.grid_remove()
        self.scale.set(100)
        self.combobox.set(r"empty")
        self.combobox_alt.set(r"empty")

        self.tree_levels.bind("<ButtonRelease-1>", self.room_select)
        self.tile_pallete_ref_in_use = []

        self.lvl = lvl

        self.lvl_biome = "cave"  # cave by default, depicts what background and sprites will be loaded
        self.lvl_bg_path = self.textures_dir / "bg_cave.png"
        if (
            lvl.startswith("abzu.lvl")
            or lvl.startswith("lake")
            or lvl.startswith("tide")
            or lvl.startswith("end")
            or lvl.endswith("_tidepool.lvl")
        ):
            self.lvl_biome = "tidepool"
            self.lvl_bg_path = self.textures_dir / "bg_tidepool.png"
        elif (
            lvl.startswith("babylon")
            or lvl.startswith("hallofu")
            or lvl.endswith("_babylon.lvl")
            or lvl.startswith("palace")
            or lvl.startswith("tiamat")
        ):
            self.lvl_biome = "babylon"
            self.lvl_bg_path = self.textures_dir / "bg_babylon.png"
        elif lvl.startswith("basecamp"):
            self.lvl_biome = "cave"
        elif lvl.startswith("beehive"):
            self.lvl_biome = "beehive"
            self.lvl_bg_path = self.textures_dir / "bg_beehive.png"
        elif (
            lvl.startswith("blackmark")
            or lvl.startswith("jungle")
            or lvl.startswith("challenge_moon")
            or lvl.endswith("_jungle.lvl")
        ):
            self.lvl_biome = "jungle"
            self.lvl_bg_path = self.textures_dir / "bg_jungle.png"
        elif (
            lvl.startswith("challenge_star")
            or lvl.startswith("temple")
            or lvl.endswith("_temple.lvl")
        ):
            self.lvl_biome = "temple"
            self.lvl_bg_path = self.textures_dir / "bg_temple.png"
        elif (
            lvl.startswith("challenge_sun")
            or lvl.startswith("sunken")
            or lvl.startswith("hundun")
            or lvl.startswith("ending_hard")
            or lvl.endswith("_sunkencity.lvl")
        ):
            self.lvl_biome = "sunken"
            self.lvl_bg_path = self.textures_dir / "bg_sunken.png"
        elif lvl.startswith("city"):
            self.lvl_biome = "gold"
            self.lvl_bg_path = self.textures_dir / "bg_gold.png"
        elif lvl.startswith("duat"):
            self.lvl_biome = "duat"
            self.lvl_bg_path = self.textures_dir / "bg_temple.png"
        elif lvl.startswith("egg"):
            self.lvl_biome = "eggplant"
            self.lvl_bg_path = self.textures_dir / "bg_eggplant.png"
        elif lvl.startswith("ice") or lvl.endswith("_icecavesarea.lvl"):
            self.lvl_biome = "ice"
            self.lvl_bg_path = self.textures_dir / "bg_ice.png"
        elif lvl.startswith("olmec"):
            self.lvl_biome = "jungle"
            self.lvl_bg_path = self.textures_dir / "bg_stone.png"
        elif lvl.startswith("vlad"):
            self.lvl_biome = "volcano"
            self.lvl_bg_path = self.textures_dir / "bg_vlad.png"
        elif lvl.startswith("volcano") or lvl.endswith("_volcano.lvl"):
            self.lvl_biome = "volcano"
            self.lvl_bg_path = self.textures_dir / "bg_volcano.png"

        if not self.extracts_mode:
            lvl_path = self.lvls_path + "/" + lvl
        else:
            if (self.overrides_path / lvl).exists():
                logger.debug("Found this lvl in overrides; loading it instead")
                lvl_path = self.overrides_path / lvl
            else:
                lvl_path = self.lvls_path / lvl

        levels = []  # Levels to load dependancy tilecodes from
        if not lvl.startswith("base"):
            if not self.extracts_mode:
                if Path(self.lvls_path + "/" + "generic.lvl").is_dir():
                    levels.append(
                        LevelFile.from_path(Path(self.lvls_path + "/" + "generic.lvl"))
                    )
                else:
                    logger.debug(
                        "local dependancy lvl not found, attempting load from extracts"
                    )
                    levels.append(
                        LevelFile.from_path(Path(self.extracts_path) / "generic.lvl")
                    )
            else:
                if Path(self.overrides_path / "generic.lvl").is_dir():
                    levels.append(
                        LevelFile.from_path(
                            Path(self.overrides_path + "/" + "generic.lvl")
                        )
                    )
                else:
                    levels.append(
                        LevelFile.from_path(Path(self.extracts_path) / "generic.lvl")
                    )
        if lvl.startswith("base"):
            if not self.extracts_mode:
                if Path(self.lvls_path + "/" + "basecamp.lvl").is_dir():
                    levels.append(
                        LevelFile.from_path(Path(self.lvls_path + "/" + "basecamp.lvl"))
                    )
                else:
                    logger.debug(
                        "local dependancy lvl not found, attempting load from extracts"
                    )
                    levels.append(
                        LevelFile.from_path(Path(self.extracts_path) / "basecamp.lvl")
                    )
            else:
                if Path(self.overrides_path / "basecamp.lvl").is_dir():
                    levels.append(
                        LevelFile.from_path(
                            Path(self.overrides_path + "/" + "basecamp.lvl")
                        )
                    )
                else:
                    levels.append(
                        LevelFile.from_path(Path(self.extracts_path) / "basecamp.lvl")
                    )
        elif lvl.startswith("cave"):
            if not self.extracts_mode:
                if Path(self.lvls_path + "/" + "dwellingarea.lvl").is_dir():
                    levels.append(
                        LevelFile.from_path(
                            Path(self.lvls_path + "/" + "dwellingarea.lvl")
                        )
                    )
                else:
                    logger.debug(
                        "local dependancy lvl not found, attempting load from extracts"
                    )
                    levels.append(
                        LevelFile.from_path(
                            Path(self.extracts_path) / "dwellingarea.lvl"
                        )
                    )
            else:
                if Path(self.overrides_path / "dwellingarea.lvl").is_dir():
                    levels.append(
                        LevelFile.from_path(
                            Path(self.overrides_path + "/" + "dwellingarea.lvl")
                        )
                    )
                else:
                    levels.append(
                        LevelFile.from_path(
                            Path(self.extracts_path) / "dwellingarea.lvl"
                        )
                    )
        elif (
            lvl.startswith("blackmark")
            or lvl.startswith("beehive")
            or lvl.startswith("challenge_moon")
        ):
            if not self.extracts_mode:
                if Path(self.lvls_path + "/" + "junglearea.lvl").is_dir():
                    levels.append(
                        LevelFile.from_path(
                            Path(self.lvls_path + "/" + "junglearea.lvl")
                        )
                    )
                else:
                    logger.debug(
                        "local dependancy lvl not found, attempting load from extracts"
                    )
                    levels.append(
                        LevelFile.from_path(Path(self.extracts_path) / "junglearea.lvl")
                    )
            else:
                if Path(self.overrides_path / "junglearea.lvl").is_dir():
                    levels.append(
                        LevelFile.from_path(
                            Path(self.overrides_path + "/" + "junglearea.lvl")
                        )
                    )
                else:
                    levels.append(
                        LevelFile.from_path(Path(self.extracts_path) / "junglearea.lvl")
                    )
        elif lvl.startswith("vlads"):
            if not self.extracts_mode:
                if Path(self.lvls_path + "/" + "volcanoarea.lvl").is_dir():
                    levels.append(
                        LevelFile.from_path(
                            Path(self.lvls_path + "/" + "volcanoarea.lvl")
                        )
                    )
                else:
                    logger.debug(
                        "local dependancy lvl not found, attempting load from extracts"
                    )
                    levels.append(
                        LevelFile.from_path(
                            Path(self.extracts_path) / "volcanoarea.lvl"
                        )
                    )
            else:
                if Path(self.overrides_path / "volcanoarea.lvl").is_dir():
                    levels.append(
                        LevelFile.from_path(
                            Path(self.overrides_path + "/" + "volcanoarea.lvl")
                        )
                    )
                else:
                    levels.append(
                        LevelFile.from_path(self.extracts_path / "volcanoarea.lvl")
                    )
        elif lvl.startswith("lake") or lvl.startswith("challenge_star"):
            if not self.extracts_mode:
                if Path(self.lvls_path + "/" + "tidepoolarea.lvl").is_dir():
                    levels.append(
                        LevelFile.from_path(
                            Path(self.lvls_path + "/" + "tidepoolarea.lvl")
                        )
                    )
                else:
                    logger.debug(
                        "local dependancy lvl not found, attempting load from extracts"
                    )
                    levels.append(
                        LevelFile.from_path(
                            Path(self.extracts_path) / "tidepoolarea.lvl"
                        )
                    )
            else:
                if Path(self.overrides_path / "tidepoolarea.lvl").is_dir():
                    levels.append(
                        LevelFile.from_path(
                            Path(self.overrides_path + "/" + "tidepoolarea.lvl")
                        )
                    )
                else:
                    levels.append(
                        LevelFile.from_path(
                            Path(self.extracts_path) / "tidepoolarea.lvl"
                        )
                    )
        elif (
            lvl.startswith("hallofush")
            or lvl.startswith("challenge_star")
            or lvl.startswith("babylonarea_1")
            or lvl.startswith("palace")
        ):
            if not self.extracts_mode:
                if Path(self.lvls_path + "/" + "babylonarea.lvl").is_dir():
                    levels.append(
                        LevelFile.from_path(
                            Path(self.lvls_path + "/" + "babylonarea.lvl")
                        )
                    )
                else:
                    logger.debug(
                        "local dependancy lvl not found, attempting load from extracts"
                    )
                    levels.append(
                        LevelFile.from_path(
                            Path(self.extracts_path) / "babylonarea.lvl"
                        )
                    )
            else:
                if Path(self.overrides_path / "babylonarea.lvl").is_dir():
                    levels.append(
                        LevelFile.from_path(
                            Path(self.overrides_path + "/" + "babylonarea.lvl")
                        )
                    )
                else:
                    levels.append(
                        LevelFile.from_path(
                            Path(self.extracts_path) / "babylonarea.lvl"
                        )
                    )
        elif lvl.startswith("challenge_sun"):
            if not self.extracts_mode:
                if Path(self.lvls_path + "/" + "sunkencityarea.lvl").is_dir():
                    levels.append(
                        LevelFile.from_path(
                            Path(self.lvls_path + "/" + "sunkencityarea.lvl")
                        )
                    )
                else:
                    logger.debug(
                        "local dependancy lvl not found, attempting load from extracts"
                    )
                    levels.append(
                        LevelFile.from_path(
                            Path(self.extracts_path) / "sunkencityarea.lvl"
                        )
                    )
            else:
                if Path(self.overrides_path / "sunkencityarea.lvl").is_dir():
                    levels.append(
                        LevelFile.from_path(
                            Path(self.overrides_path + "/" + "sunkencityarea.lvl")
                        )
                    )
                else:
                    levels.append(
                        LevelFile.from_path(
                            Path(self.extracts_path) / "sunkencityarea.lvl"
                        )
                    )
        elif lvl.startswith("end"):
            if not self.extracts_mode:
                if Path(self.lvls_path + "/" + "ending.lvl").is_dir():
                    levels.append(
                        LevelFile.from_path(Path(self.lvls_path + "/" + "ending.lvl"))
                    )
                else:
                    logger.debug(
                        "local dependancy lvl not found, attempting load from extracts"
                    )
                    levels.append(
                        LevelFile.from_path(Path(self.extracts_path) / "ending.lvl")
                    )
            else:
                if Path(self.overrides_path / "ending.lvl").is_dir():
                    levels.append(
                        LevelFile.from_path(
                            Path(self.overrides_path + "/" + "ending.lvl")
                        )
                    )
                else:
                    levels.append(
                        LevelFile.from_path(Path(self.extracts_path) / "ending.lvl")
                    )
        levels.append(LevelFile.from_path(Path(lvl_path)))

        level = None
        for level in levels:
            logger.debug("%s loaded.", level.comment)
            level_tilecodes = level.tile_codes.all()

            for tilecode in level_tilecodes:
                tilecode_item = []
                tilecode_item.append(str(tilecode.name) + " " + str(tilecode.value))

                img = self.get_texture(tilecode.name, self.lvl_biome, lvl)

                tilecode_item.append(ImageTk.PhotoImage(img))
                self.panel_sel["image"] = tilecode_item[1]
                self.tile_label["text"] = "Primary Tile: " + tilecode_item[0]
                self.panel_sel_secondary["image"] = tilecode_item[1]
                self.tile_label_secondary["text"] = (
                    "Secondary Tile: " + tilecode_item[0]
                )

                for i in self.tile_pallete_ref_in_use:
                    if str(i[0]).split(" ", 1)[1] == str(tilecode.value):
                        self.tile_pallete_ref_in_use.remove(i)

                for i in self.usable_codes:
                    if str(i) == str(tilecode.value):
                        self.usable_codes.remove(i)

                self.tile_pallete_ref_in_use.append(tilecode_item)

        if level is None:
            return

        if lvl.startswith(
            "generic"
        ):  # adds tilecodes to generic that it relies on yet doesn't provide
            generic_needs = [
                ["4", "push_block"],
                ["t", "treasure"],
                ["1", "floor"],
                ["6", "chunk_air"],
                ["=", "minewood_floor"],
            ]
            for need in generic_needs:
                for code in self.usable_codes:
                    if str(code) == need[0] and not any(
                        need[0] in str(code_in_use[0].split(" ", 3)[1])
                        for code_in_use in self.tile_pallete_ref_in_use
                    ):
                        for i in self.usable_codes:
                            if str(i) == str(need[0]):
                                self.usable_codes.remove(i)
                        tilecode_item = []
                        tilecode_item.append(str(need[1]) + " " + str(need[0]))

                        img = self.get_texture(str(need[1]), self.lvl_biome, lvl)

                        tilecode_item.append(ImageTk.PhotoImage(img))
                        self.tile_pallete_ref_in_use.append(tilecode_item)
        self.populate_tilecode_pallete()

        level_rules = level.level_settings.all()
        bad_chars = ["[", "]", '"', "'", "(", ")"]
        for rules in level_rules:
            value_final = str(rules.value)
            for i in bad_chars:
                value_final = value_final.replace(i, "")
            self.tree.insert(
                "",
                "end",
                text="L1",
                values=(str(rules.name), value_final, str(rules.comment)),
            )

        level_chances = level.monster_chances.all()
        for rules in level_chances:
            self.tree_chances_monsters.insert(
                "",
                "end",
                text="L1",
                values=(
                    str(rules.name),
                    str(rules.value)
                    .strip("[")
                    .strip("]")
                    .strip("(")
                    .strip(")")
                    .strip('"'),
                    str(rules.comment),
                ),
            )

        level_monsters = level.level_chances.all()
        for rules in level_monsters:
            self.tree_chances_levels.insert(
                "",
                "end",
                text="L1",
                values=(
                    str(rules.name),
                    str(rules.value)
                    .strip("[")
                    .strip("]")
                    .strip("(")
                    .strip(")")
                    .strip('"'),
                    str(rules.comment),
                ),
            )

        level_templates = level.level_templates.all()

        for template in level_templates:
            template_comment = ""
            if str(template.comment) != "":
                template_comment = "// " + str(template.comment)
            entry = self.node = self.tree_levels.insert(
                "", "end", text=str(template.name) + "   " + template_comment
            )
            for room in template.chunks:
                room_string = []  # makes room data into string for storing

                for setting in room.settings:
                    room_string.append(r"\!" + str(setting).split(".", 1)[1].lower())

                i = 0
                for line in room.foreground:
                    foreground = ""
                    background = ""
                    for code in line:
                        foreground += str(code)
                    if len(room.background) > 0:
                        background += " "
                        for code in room.background[i]:
                            background += str(code)
                    room_string.append(foreground + background)
                    i = i + 1

                room_name = "room"
                if str(room.comment) != "":
                    room_name = str(room.comment).split(" ", 1)[1].strip("\n")

                self.node = self.tree_levels.insert(
                    entry, "end", values=room_string, text=str(room_name)
                )

        # lines = file1.readlines()

    @staticmethod
    def adjust_texture_xy(width, height, mode):
        # slight adjustments of textures for tile preview
        # 1 = lower half tile
        # 2 = draw from bottom left
        # 3 = center
        # 4 = center to the right
        # 5 = draw bottom left + raise 1 tile
        # 6 = position doors
        # 7 = draw bottom left + raise half tile
        # 8 = draw bottom left + lowere 1 tile
        # 9 = draw bottom left + raise 1 tile + move left 1 tile
        # 10 = draw bottom left + raise 1 tile + move left 1 tile
        # 11 = move left 1 tile
        # 12 = raise 1 tile
        x_coord = 0
        y_coord = 0
        if mode == 1:
            y_coord = (height * -1) / 2
        elif mode == 2:
            y_coord = height / 2
        elif mode == 3:
            x_coord = width / 3.2
            y_coord = height / 2
        elif mode == 4:
            x_coord = (width * -1) / 2
        elif mode == 5:
            y_coord = height / 2 + 50
        elif mode == 6:
            x_coord = 25
            y_coord = 22
        elif mode == 7:
            y_coord = height / 2 + 25
        elif mode == 8:
            y_coord = (height / 2 + 50) * -1
        elif mode == 9:
            y_coord = height / 2 + 50
            x_coord = 75
        elif mode == 10:
            y_coord = height / 2 + 100
        elif mode == 11:
            x_coord = 50
        elif mode == 12:
            y_coord = 50
        return x_coord, y_coord

    def get_texture(self, tile, biome, lvl):
        def get_specific_tile(tile):
            img_spec = None

            if (
                lvl.startswith("generic")
                or lvl.startswith("challenge")
                or lvl.startswith("testing")
                or lvl.startswith("beehive")
                or lvl.startswith("palace")
            ):
                if tile == "floor":
                    img_spec = self._sprite_fetcher.get("generic_floor", str(biome))
                elif tile == "styled_floor":
                    img_spec = self._sprite_fetcher.get(
                        "generic_styled_floor", str(biome)
                    )
            # base is weird with its tiles so I gotta get specific here
            if lvl.startswith("base"):
                if tile == "floor":
                    img_spec = self._sprite_fetcher.get("floor", "cave")
            if lvl.startswith("duat"):  # specific floor hard for this biome
                if tile == "floor_hard":
                    img_spec = self._sprite_fetcher.get("duat_floor_hard")
                elif tile == "coffin":
                    img_spec = self._sprite_fetcher.get(
                        "duat_coffin",
                    )
            # specific floor hard for this biome
            if (
                lvl.startswith("sunken")
                or lvl.startswith("hundun")
                or lvl.endswith("_sunkencity.lvl")
            ):
                if tile == "floor_hard":
                    img_spec = self._sprite_fetcher.get("sunken_floor_hard")
            # specific floor styled for this biome
            if (
                lvl.startswith("volcan")
                or lvl.startswith("ice")
                or lvl.endswith("_icecavesarea.lvl")
                or lvl.endswith("_volcano.lvl")
            ):
                if tile == "styled_floor":
                    img_spec = self._sprite_fetcher.get("empty")
            if lvl.startswith("olmec"):  # specific door
                if tile == "door":
                    img_spec = self._sprite_fetcher.get(
                        "stone_door",
                    )
            if lvl.startswith("cityofgold"):  # specific door
                if tile == "crushtraplarge":
                    img_spec = self._sprite_fetcher.get(
                        "gold_crushtraplarge",
                    )
                elif tile == "coffin":
                    img_spec = self._sprite_fetcher.get(
                        "gold_coffin",
                    )
            if lvl.startswith("temple"):  # specific door
                if tile == "coffin":
                    img_spec = self._sprite_fetcher.get(
                        "temple_coffin",
                    )

            return img_spec

        img = self._sprite_fetcher.get(str(tile), str(biome))
        if get_specific_tile(str(tile)) != None:
            img = get_specific_tile(str(tile))

        if len(tile.split("%", 2)) > 1:
            img1 = self._sprite_fetcher.get("unknown")
            img2 = self._sprite_fetcher.get("unknown")
            primary_tile = tile.split("%", 2)[0]
            if self._sprite_fetcher.get(primary_tile, str(biome)):
                img1 = self._sprite_fetcher.get(primary_tile, str(biome))
                if get_specific_tile(str(tile)) != None:
                    img1 = get_specific_tile(str(primary_tile))
            percent = tile.split("%", 2)[1]
            secondary_tile = "empty"
            img2 = None
            if len(tile.split("%", 2)) > 2:
                secondary_tile = tile.split("%", 2)[2]
                if self._sprite_fetcher.get(secondary_tile, str(biome)):
                    img2 = self._sprite_fetcher.get(secondary_tile, str(biome))
                    if get_specific_tile(str(tile)) != None:
                        img2 = get_specific_tile(str(secondary_tile))
            img = self.get_tilecode_percent_texture(
                primary_tile, secondary_tile, percent, img1, img2
            )

        if img is None:
            img = self._sprite_fetcher.get("unknown")
        width, height = img.size
        resize = True

        # These tile textures are already sized down
        for tile_ref in TILENAMES:
            if tile_ref == tile:
                resize = False

        if resize:
            width = int(
                width / 2.65
            )  # 2.65 is the scale to get the typical 128 tile size down to the needed 50
            height = int(height / 2.65)

        _scale = 1
        # for some reason these are sized differently then everything elses typical universal scale
        # if (tile == "door2" or tile == "door2_secret" or tile == "ghist_door2"):
        #    width = int(width/2)
        #    height = int(height/2)

        # since theres rounding involved, this makes sure each tile is size
        # correctly by making up for what was rounded off
        if width < 50 and height < 50:
            difference = 0
            if width > height:
                difference = 50 - width
            else:
                difference = 50 - height

            width = width + difference
            height = height + difference

        img = img.resize((width, height), Image.ANTIALIAS)
        return img

    @staticmethod
    def get_tilecode_percent_texture(_tile, alt_tile, percent, img1, img2):
        with tempfile.TemporaryDirectory() as tempdir:
            tempdir_path = Path(tempdir)
            temp1 = tempdir_path / "temp1.png"
            temp2 = tempdir_path / "temp2.png"
            # ImageTk.PhotoImage()._PhotoImage__photo.write(temp1, format="png")

            image1_save = ImageTk.PhotoImage(img1)
            # pylint: disable=protected-access
            image1_save._PhotoImage__photo.write(temp1, format="png")
            image1 = Image.open(
                temp1,
            ).convert("RGBA")
            image1 = image1.resize((50, 50), Image.BILINEAR)
            tile_text = percent + "%"
            if alt_tile != "empty":
                tile_text += "/" + str(100 - int(percent)) + "%"

                # ImageTk.PhotoImage()._PhotoImage__photo.write(temp2, format="png")

                image2_save = ImageTk.PhotoImage(img2)
                # pylint: disable=protected-access
                image2_save._PhotoImage__photo.write(temp2, format="png")
                image2 = Image.open(temp2).convert("RGBA")
                image2 = image2.resize((50, 50), Image.BILINEAR).convert("RGBA")
                image2.crop([25, 0, 50, 50]).save(temp2)
                image1.save(temp1)
                image1 = Image.open(temp1).convert("RGBA")
                image2 = Image.open(temp2).convert("RGBA")

                offset = (25, 0)
                image1.paste(image2, offset)
            # make a blank image for the text, initialized to transparent text color
            txt = Image.new("RGBA", (50, 50), (255, 255, 255, 0))

            # get a drawing context
            draw_ctx = ImageDraw.Draw(txt)

            # draw text, half opacity
            draw_ctx.text((6, 34), tile_text, fill=(0, 0, 0, 255))
            draw_ctx.text((4, 34), tile_text, fill=(0, 0, 0, 255))
            draw_ctx.text((6, 36), tile_text, fill=(0, 0, 0, 255))
            draw_ctx.text((4, 36), tile_text, fill=(0, 0, 0, 255))
            draw_ctx.text((5, 35), tile_text, fill=(255, 255, 255, 255))

            out = Image.alpha_composite(image1, txt)
        return out


@dataclass
class RoomType:
    name: str
    x_size: int
    y_size: int


ROOM_TYPES = {
    f"{room_type.name}: {room_type.x_size}x{room_type.y_size}": room_type
    for room_type in [
        RoomType("normal", 10, 8),
        RoomType("machine_wideroom", 20, 8),
        RoomType("machine_tallroom", 10, 16),
        RoomType("machine_bigroom", 20, 16),
        RoomType("ghistroom", 5, 5),
        RoomType("feeling", 20, 16),
        RoomType("chunk_ground", 5, 3),
        RoomType("chunk_door", 6, 3),
        RoomType("chunk_air", 5, 3),
        RoomType("cache", 5, 5),
    ]
}
DEFAULT_ROOM_TYPE = "normal"


class LevelsTree(ttk.Treeview):
    def __init__(self, parent, levels_tab, *args, **kwargs):
        ttk.Treeview.__init__(self, parent, *args, **kwargs)

        self.levels_tab = levels_tab

        # two different context menus to show depending on what is clicked (room or room list)
        self.popup_menu_child = tk.Menu(self, tearoff=0)
        self.popup_menu_parent = tk.Menu(self, tearoff=0)

        self.popup_menu_child.add_command(label="Rename Room", command=self.rename)
        self.popup_menu_child.add_command(
            label="Duplicate Room", command=self.duplicate
        )
        self.popup_menu_child.add_command(label="Copy Room", command=self.copy)
        self.popup_menu_child.add_command(label="Paste Room", command=self.paste)
        self.popup_menu_child.add_command(
            label="Delete Room", command=self.delete_selected
        )
        self.popup_menu_child.add_command(label="Add Room", command=self.add_room)
        self.popup_menu_parent.add_command(label="Add Room", command=self.add_room)
        self.popup_menu_parent.add_command(label="Paste Room", command=self.paste)

        self.bind("<Button-3>", self.popup)  # Button-2 on Aqua

    def popup(self, event):
        try:
            item_iid = self.selection()[0]
            parent_iid = self.parent(item_iid)  # gets selected room
            if parent_iid:  # if actual room is clicked
                self.popup_menu_child.tk_popup(event.x_root, event.y_root, 0)
            else:  # if room list is clicked
                self.popup_menu_parent.tk_popup(event.x_root, event.y_root, 0)

            self.levels_tab.save_needed = True
            self.levels_tab.button_save["state"] = tk.NORMAL
        except Exception:  # pylint: disable=broad-except
            self.popup_menu_child.grab_release()
            self.popup_menu_parent.grab_release()

    def rename(self):
        for _ in self.selection()[::-1]:
            self.rename_dialog()

    def duplicate(self):
        item_iid = self.selection()[0]
        parent_iid = self.parent(item_iid)  # gets selected room
        if parent_iid:
            item_name = self.item(item_iid)["text"]
            room_data = self.item(item_iid, option="values")
            self.insert(parent_iid, "end", text=item_name + " COPY", values=room_data)

    def copy(self):
        item = self.selection()[0]
        copy_text = str(self.item(item, option="text"))
        copy_values_raw = self.item(item, option="values")
        copy_values = ""
        for line in copy_values_raw:
            copy_values += str(line) + "\n"
        logger.debug("copied %s", copy_values)
        pyclip.copy(copy_text + "\n" + copy_values)

    def paste(self):
        data = pyclip.paste().decode("cp1252")

        paste_text = data.split("\n", 1)[0]
        paste_values_raw = data.split("\n", 1)[1]

        paste_values = []
        paste_values = paste_values_raw.split("\n")

        for item in paste_values:
            if item == "":
                paste_values.remove(item)  # removes empty line
        logger.debug("pasted %s", paste_values)

        item_iid = self.selection()[0]
        parent_iid = self.parent(item_iid)  # gets selected room
        if parent_iid:
            self.insert(parent_iid, "end", text=paste_text, values=paste_values)
        else:
            self.insert(item_iid, "end", text=paste_text, values=paste_values)

    def delete_selected(self):
        item_iid = self.selection()[0]
        parent_iid = self.parent(item_iid)  # gets selected room
        if parent_iid:
            msg_box = tk.messagebox.askquestion(
                "Delete Room?",
                "Are you sure you want to delete "
                + self.item(item_iid)["text"]
                + "?"
                + "\nThis won't be recoverable.",
                icon="warning",
            )
            if msg_box == "yes":
                self.delete(item_iid)
                self.levels_tab.canvas.delete("all")
                self.levels_tab.canvas_dual.delete("all")
                self.levels_tab.canvas.grid_remove()
                self.levels_tab.canvas_dual.grid_remove()

    def add_room(self):
        item_iid = self.selection()[0]
        parent_iid = self.parent(item_iid)  # gets selected room
        parent = None
        if parent_iid:
            parent = parent_iid
        else:
            parent = item_iid

        # First check if a blank space was selected
        entry_index = self.focus()
        if entry_index == "":
            return

        # Set up window
        win = tk.Toplevel()
        win.title("Add Room")
        if "nt" in os.name:
            win.attributes("-toolwindow", True)
        else:
            win.attributes("-alpha", True)
        self.center(win)

        combosizes = ttk.Combobox(win, height=20)
        combosizes["values"] = list(ROOM_TYPES.keys())
        combosizes.grid(row=0, column=1, columnspan=3)
        col1_lbl = tk.Label(win, text="Size: ")
        col1_lbl.grid(row=0, column=0)

        # Set default prompt based on parent name
        combosizes.set("normal: 10x8")
        parent_room_type = self.item(parent)["text"]
        for room_size_text, room_type in ROOM_TYPES.items():
            if parent_room_type.startswith(room_type.name):
                combosizes.set(room_size_text)
                break

        def update_then_destroy():
            room_type = ROOM_TYPES[combosizes.get()]
            new_room_data = ["0" * room_type.x_size] * room_type.y_size
            self.insert(parent, "end", text="new room", values=new_room_data)
            win.destroy()

        ok_button = tk.Button(win, text="Add")
        ok_button.bind("<Button-1>", lambda e: update_then_destroy())
        ok_button.grid(row=2, column=1)

        cancel_button = tk.Button(win, text="Cancel")
        cancel_button.bind("<Button-1>", lambda c: win.destroy())
        cancel_button.grid(row=2, column=2)

    def rename_dialog(self):
        item_iid = self.selection()[0]
        parent_iid = self.parent(item_iid)  # gets selected room
        if parent_iid:
            # First check if a blank space was selected
            entry_index = self.focus()
            if entry_index == "":
                return

            # Set up window
            win = tk.Toplevel()
            win.title("Edit Name")
            if "nt" in os.name:
                win.attributes("-toolwindow", True)
            else:
                win.attributes("-alpha", True)
            self.center(win)

            item_name = ""
            item_name = self.item(item_iid)["text"]
            room_data = self.item(item_iid, option="values")

            col1_lbl = tk.Label(win, text="Name: ")
            col1_ent = tk.Entry(win)
            col1_ent.insert(0, item_name)  # Default to rooms current name
            col1_lbl.grid(row=0, column=0)
            col1_ent.grid(row=0, column=1, columnspan=3)

            def update_then_destroy():
                if self.confirm_entry(col1_ent.get(), parent_iid, room_data):
                    win.destroy()

            ok_button = tk.Button(win, text="Ok")
            ok_button.bind("<Button-1>", lambda e: update_then_destroy())
            ok_button.grid(row=1, column=1)

            cancel_button = tk.Button(win, text="Cancel")
            cancel_button.bind("<Button-1>", lambda c: win.destroy())
            cancel_button.grid(row=1, column=2)

    def confirm_entry(self, entry1, parent, room_data):
        if entry1 != "":
            # Grab the current index in the tree
            current_index = self.index(self.focus())

            # Remove it from the tree
            self.delete(self.focus())

            # Put it back in with the upated values
            self.insert(parent, current_index, text=entry1, values=room_data)
            return True
        else:
            return False

    def center(self, toplevel):
        toplevel.update_idletasks()

        # Tkinter way to find the screen resolution
        # screen_width = toplevel.winfo_screenwidth()
        # screen_height = toplevel.winfo_screenheight()

        # find the screen resolution
        screen_width = 1280
        screen_height = 720

        size = tuple(int(_) for _ in toplevel.geometry().split("+")[0].split("x"))
        x_coord = screen_width / 2 - size[0] / 2
        y_coord = screen_height / 2 - size[1] / 2

        toplevel.geometry("+%d+%d" % (x_coord, y_coord))


class RulesTree(ttk.Treeview):
    def __init__(self, parent, levels_tab, *args, **kwargs):
        ttk.Treeview.__init__(self, parent, *args, **kwargs)
        self.levels_tab = levels_tab

        self.popup_menu = tk.Menu(self, tearoff=0)
        self.popup_menu_parent = tk.Menu(self, tearoff=0)
        self.popup_menu.add_command(label="Add", command=self.add)
        self.popup_menu_parent.add_command(label="Add", command=self.add)
        self.popup_menu.add_command(label="Delete", command=self.delete_selected)

        self.bind("<Button-3>", self.popup)  # Button-2 on Aqua

    def popup(self, event):
        try:
            if len(self.selection()) == 1:
                self.popup_menu.tk_popup(event.x_root, event.y_root, 0)
            else:
                self.popup_menu_parent.tk_popup(event.x_root, event.y_root, 0)
        finally:
            self.popup_menu.grab_release()

    def delete_selected(self):
        msg_box = tk.messagebox.askquestion(
            "Delete?",
            "Delete this rule?",
            icon="warning",
        )
        if msg_box == "yes":
            item_iid = self.selection()[0]
            self.delete(item_iid)
            self.levels_tab.save_needed = True
            self.levels_tab.button_save["state"] = tk.NORMAL

    def add(self):
        _edited = self.insert(
            "",
            "end",
            values=["COMMENT", "VAL", "// COMMENT"],
        )
        self.levels_tab.save_needed = True
        self.levels_tab.button_save["state"] = tk.NORMAL
        # self.selection_set(0, 'end')
