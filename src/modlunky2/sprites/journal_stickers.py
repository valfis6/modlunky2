from pathlib import Path

from .base_classes import BaseSpriteLoader


class StickerSheet(BaseSpriteLoader):
    _sprite_sheet_path = Path("Data/Textures/journal_stickers.png")
    _chunk_size = 80
    _chunk_map = {
        'sticker_50_percent': (8, 4, 9, 5),
        'sticker_alien_compass': (8, 3, 9, 4),
        'sticker_ankh': (3, 2, 4, 3),
        'sticker_anubis': (4, 6, 6, 8),
        'sticker_blob_blue': (8, 8, 9, 9),
        'sticker_blob_green': (9, 8, 10, 9),
        'sticker_cape': (0, 4, 1, 5),
        'sticker_cave_man': (2, 5, 3, 6),
        'sticker_char_black': (3, 0, 4, 1),
        'sticker_char_blue': (9, 0, 10, 1),
        'sticker_char_cerulean': (8, 0, 9, 1),
        'sticker_char_cinnabar': (4, 0, 5, 1),
        'sticker_char_cyan': (2, 0, 3, 1),
        'sticker_char_gold': (3, 1, 4, 2),
        'sticker_char_gray': (7, 1, 8, 2),
        'sticker_char_green': (5, 0, 6, 1),
        'sticker_char_iris': (2, 1, 3, 2),
        'sticker_char_khaki': (8, 1, 9, 2),
        'sticker_char_lemon': (1, 1, 2, 2),
        'sticker_char_lime': (0, 1, 1, 2),
        'sticker_char_locked': (9, 2, 10, 3),
        'sticker_char_magenta': (1, 0, 2, 1),
        'sticker_char_olive': (6, 0, 7, 1),
        'sticker_char_orange': (9, 1, 10, 2),
        'sticker_char_pink': (5, 1, 6, 2),
        'sticker_char_red': (4, 1, 5, 2),
        'sticker_char_violet': (6, 1, 7, 2),
        'sticker_char_white': (7, 0, 8, 1),
        'sticker_char_yellow': (0, 0, 1, 1),
        'sticker_climbing_gloves': (2, 3, 3, 4),
        'sticker_compass': (1, 3, 2, 4),
        'sticker_crown': (2, 2, 3, 3),
        'sticker_eggplant_crown': (9, 3, 10, 4),
        'sticker_eggplant_king': (4, 8, 6, 10),
        'sticker_empty_1': (8, 9, 9, 10),
        'sticker_empty_2': (9, 9, 10, 10),
        'sticker_full': (9, 4, 10, 5),
        'sticker_hedjet': (1, 2, 2, 3),
        'sticker_hover_pack': (3, 4, 4, 5),
        'sticker_hundun': (6, 8, 8, 10),
        'sticker_idol': (5, 2, 6, 3),
        'sticker_jet_pack': (1, 4, 2, 5),
        'sticker_kapala': (4, 2, 5, 3),
        'sticker_kingu': (2, 6, 4, 8),
        'sticker_lahamu': (8, 6, 10, 8),
        'sticker_lock': (8, 2, 9, 3),
        'sticker_olmec': (0, 8, 2, 10),
        'sticker_osiris': (6, 6, 8, 8),
        'sticker_parachute': (6, 3, 7, 4),
        'sticker_parmesan': (6, 5, 7, 6),
        'sticker_parsley': (4, 5, 5, 6),
        'sticker_parsnip': (5, 5, 6, 6),
        'sticker_paste': (0, 3, 1, 4),
        'sticker_pitchers_mitt': (3, 3, 4, 4),
        'sticker_power_pack': (6, 4, 7, 5),
        'sticker_quill_back': (0, 6, 2, 8),
        'sticker_shopkeeper': (0, 5, 1, 6),
        'sticker_skeleton_key': (4, 4, 5, 5),
        'sticker_sparrow': (8, 5, 9, 6),
        'sticker_speckles': (7, 3, 8, 4),
        'sticker_spike_shoes': (4, 3, 5, 4),
        'sticker_spring_shoes': (5, 3, 6, 4),
        'sticker_tablet_of_destiny': (5, 4, 6, 5),
        'sticker_tele_pack': (2, 4, 3, 5),
        'sticker_the_true_crown': (6, 2, 7, 3),
        'sticker_tiamat': (2, 8, 4, 10),
        'sticker_tun': (1, 5, 2, 6),
        'sticker_udjat_eye': (0, 2, 1, 3),
        'sticker_van_horsing': (7, 5, 8, 6),
        'sticker_vlad': (9, 5, 10, 6),
        'sticker_vlad_cape': (7, 4, 8, 5),
        'sticker_yang': (3, 5, 4, 6),
        'sticker_yellow_tile': (7, 2, 8, 3)
    }
