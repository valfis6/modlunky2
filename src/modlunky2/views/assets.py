import json
import logging
import os
import shutil
import threading
from pathlib import Path

from flask import Blueprint, current_app, render_template, request

from modlunky2.assets.assets import AssetStore
from modlunky2.assets.constants import (EXTRACTED_DIR, FILEPATH_DIRS,
                                        KNOWN_FILEPATHS, OVERRIDES_DIR,
                                        PACKS_DIR)
from modlunky2.assets.exc import MissingAsset
from modlunky2.assets.patcher import Patcher

blueprint = Blueprint("assets", __name__)
ws_blueprint = Blueprint("assets", __name__)


MODS = Path("Mods")

TOP_LEVEL_DIRS = [
    EXTRACTED_DIR,
    PACKS_DIR,
    OVERRIDES_DIR
]

def is_patched(exe_filename):
    with exe_filename.open("rb") as exe:
        return Patcher(exe).is_patched()


class BaseContext:
    def __init__(self, socket):
        self.socket = socket
        self._socket_failed = False

    def alert(self, level, msg):
        if self._socket_failed:
            return

        try:
            self.socket.send(json.dumps({
                "cmd": "alert",
                "data": {
                    "level": level,
                    "msg": str(msg),
                }
            }))
        except Exception:  # pylint: disable=broad-except
            logging.exception("Failed to call alert callback, socket likely went away.")
            self._socket_failed = True


# Extract

@blueprint.route("/extract/", methods=["GET"])
def extract():
    exes = []
    # Don't recurse forever. 3 levels should be enough
    exes.extend(current_app.config.SPELUNKY_INSTALL_DIR.glob("*.exe"))
    exes.extend(current_app.config.SPELUNKY_INSTALL_DIR.glob("*/*.exe"))
    exes.extend(current_app.config.SPELUNKY_INSTALL_DIR.glob("*/*/*.exe"))
    exes = [
        exe.relative_to(current_app.config.SPELUNKY_INSTALL_DIR)
        for exe in exes
        if exe.name not in ["modlunky2.exe"]
    ]
    return render_template("extract.html", exes=exes)


class ExtractContext(BaseContext):
    def __init__(self, socket):
        super().__init__(socket)
        self.known_filepaths = set(KNOWN_FILEPATHS)
        self.extracted = set()

    def extract_complete(self, filepath):
        if self._socket_failed:
            return

        self.extracted.add(filepath)
        percent_complete = int((len(self.extracted) / len(self.known_filepaths)) * 100)

        try:
            self.socket.send(json.dumps({
                "cmd": "extract-percent-complete",
                "data": percent_complete,
            }))
        except Exception:  # pylint: disable=broad-except
            logging.exception("Failed to call alert callback, socket likely went away.")
            self._socket_failed = True


def extract_assets(target, extract_ctx):

    exe_filename = current_app.config.SPELUNKY_INSTALL_DIR / target
    install_dir = current_app.config.SPELUNKY_INSTALL_DIR

    if is_patched(exe_filename):
        extract_ctx.alert(
            "danger",
            f"{target} is a patched exe. You can only extract from an un-patched exe."
        )
        return

    mods_dir = install_dir / MODS

    for dir_ in TOP_LEVEL_DIRS:
        (mods_dir / dir_).mkdir(parents=True, exist_ok=True)

    for dir_ in FILEPATH_DIRS:
        (mods_dir / EXTRACTED_DIR / dir_).mkdir(parents=True, exist_ok=True)
        (mods_dir / ".compressed" / EXTRACTED_DIR / dir_).mkdir(parents=True, exist_ok=True)

    with exe_filename.open("rb") as exe:
        asset_store = AssetStore.load_from_file(exe)
        unextracted = asset_store.extract(
            mods_dir / EXTRACTED_DIR,
            mods_dir / ".compressed" / EXTRACTED_DIR,
            extract_ctx=extract_ctx,
        )

    for asset in unextracted:
        extract_ctx.alert("warning", f"Un-extracted Asset {asset.asset_block}")
        logging.warning("Un-extracted Asset %s", asset.asset_block)

    dest = mods_dir / EXTRACTED_DIR / "Spel2.exe"
    if exe_filename != dest:
        logging.info("Backing up exe to %s", dest)
        shutil.copy2(exe_filename, dest)

    logging.info("Extraction complete!")


@ws_blueprint.route('/extract/')
def ws_extract(socket):
    extract_ctx = ExtractContext(socket)
    while not socket.closed:
        message = socket.receive()
        if message is None:
            return
        message = json.loads(message)
        logging.info("Message received: %s", message)
        assert message["cmd"] == "extract"
        try:
            extract_assets(**message["data"], extract_ctx=extract_ctx)
        except Exception as err:  # pylint: disable=broad-except
            extract_ctx.alert("danger", err)

        socket.send(json.dumps({
            "cmd": "extract-complete",
            "data": message
        }))


@blueprint.route("/extract/", methods=["POST"])
def assets_extract():

    exe = current_app.config.SPELUNKY_INSTALL_DIR / request.form["extract-target"]
    thread = threading.Thread(
        target=extract_assets, args=(current_app.config.SPELUNKY_INSTALL_DIR, exe)
    )
    thread.start()


# Pack


def get_overrides(install_dir):
    dir_ = install_dir / MODS / OVERRIDES_DIR

    if not dir_.exists():
        return None

    overrides = []
    for root, dirs, files in os.walk(dir_, topdown=True):
        dirs[:] = [d for d in dirs if d not in [".compressed"]]

        for file_ in files:
            overrides.append(Path(root) / file_)

    return overrides


@blueprint.route("/pack/")
def pack():
    overrides = get_overrides(current_app.config.SPELUNKY_INSTALL_DIR)

    return render_template("pack.html", overrides=overrides)


def repack_assets(mods_dir, search_dirs, extract_dir, source_exe, dest_exe):
    mods_dir = current_app.config.SPELUNKY_INSTALL_DIR / MODS
    search_dirs = [mods_dir / "Overrides"]
    extract_dir = mods_dir / "Extracted"

    source_exe = current_app.config.SPELUNKY_INSTALL_DIR / MODS/ EXTRACTED_DIR / "Spel2.exe"
    dest_exe = current_app.config.SPELUNKY_INSTALL_DIR / "Spel2.exe"

    if is_patched(source_exe):
        # FIXME: return error
        return

    shutil.copy2(source_exe, dest_exe)

    with dest_exe.open("rb+") as dest_file:
        asset_store = AssetStore.load_from_file(dest_file)
        try:
            asset_store.repackage(
                search_dirs,
                extract_dir,
                mods_dir / ".compressed",
            )
        except MissingAsset as err:
            logging.error(
                "Failed to find expected asset: %s. Unabled to proceed...", err
            )
            return

        patcher = Patcher(dest_file)
        patcher.patch()
    logging.info("Repacking complete!")


@ws_blueprint.route('/pack/')
def ws_pack(socket):
    while not socket.closed:
        message = socket.receive()
        if message is None:
            return
        socket.send(message)
