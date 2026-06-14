"""
steamos-controller-changer - Decky Loader Plugin Backend
Switch InputPlumber device profile between native, Legion Go S, and PS5 DualSense Edge.
"""

import glob
import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path

import decky

BOARD_PATH = "/sys/devices/virtual/dmi/id/board_name"
INPUTPLUMBER_DEVICES_DIR = "/usr/share/inputplumber/devices"
LEGION_GO_S_NAME = "Lenovo Legion Go S"
PS5_EDGE_NAME = "PS5 DualSense Edge"
PS5_EDGE_TARGET = "ds5-edge"
DEFAULT_TARGET = "deck-uhid"
INPUTPLUMBER_DEVICE_INDEX = "0"

SYSTEMCTL = shutil.which("systemctl") or "/usr/bin/systemctl"
STEAMOS_READONLY = shutil.which("steamos-readonly") or "/usr/bin/steamos-readonly"
INPUTPLUMBER = shutil.which("inputplumber") or "/usr/bin/inputplumber"

VALID_SELECTIONS = ("default", "legion_go_s", "ps5_edge")

BACKUP_META_FILE = "backup_meta.json"
BACKUP_YAML_FILE = "device_yaml_backup.yaml"


class Plugin:
    settings_path: str = ""
    settings: dict = {}
    last_error: str = ""

    def _backup_meta_path(self) -> str:
        return os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, BACKUP_META_FILE)

    def _backup_yaml_path(self) -> str:
        return os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, BACKUP_YAML_FILE)

    def _set_error(self, message: str) -> str:
        self.last_error = message
        decky.logger.error(message)
        return message

    def _system_command_env(self) -> dict:
        env = {
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "LANG": os.environ.get("LANG", "C.UTF-8"),
        }
        for key in ("HOME", "USER", "LOGNAME", "SHELL"):
            if key in os.environ:
                env[key] = os.environ[key]
        return env

    def _run_command(
        self, args: list[str], *, record_error: bool = True
    ) -> subprocess.CompletedProcess | None:
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                check=False,
                env=self._system_command_env(),
            )
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "").strip()
                message = (
                    f"{' '.join(args)} failed"
                    + (f": {detail}" if detail else "")
                )
                if record_error:
                    self._set_error(message)
                else:
                    decky.logger.warning(message)
                return None
            return result
        except Exception as e:
            message = f"{' '.join(args)} error: {e}"
            if record_error:
                self._set_error(message)
            else:
                decky.logger.warning(message)
            return None

    def _set_inputplumber_target(self, target: str) -> bool:
        return (
            self._run_command(
                [
                    INPUTPLUMBER,
                    "device",
                    INPUTPLUMBER_DEVICE_INDEX,
                    "targets",
                    "set",
                    target,
                ]
            )
            is not None
        )

    def _read_board_name(self) -> str | None:
        try:
            with open(BOARD_PATH, "r", encoding="utf-8") as f:
                board = f.read().strip()
            return board or None
        except Exception as e:
            decky.logger.error(f"Failed to read board name: {e}")
            return None

    def _find_device_yaml(self) -> str | None:
        board = self._read_board_name()
        if not board:
            return None

        matches: list[str] = []
        pattern = os.path.join(INPUTPLUMBER_DEVICES_DIR, "*.yaml")
        for yaml_path in sorted(glob.glob(pattern)):
            try:
                with open(yaml_path, "r", encoding="utf-8") as f:
                    if board in f.read():
                        matches.append(yaml_path)
            except Exception as e:
                decky.logger.warning(f"Could not read {yaml_path}: {e}")

        if not matches:
            return None
        if len(matches) > 1:
            decky.logger.warning(
                "Multiple device yaml files matched board %s, using %s",
                board,
                matches[0],
            )
        return matches[0]

    def _read_device_name(self, yaml_path: str) -> str | None:
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("name:"):
                        return line.split(":", 1)[1].strip()
        except Exception as e:
            decky.logger.error(f"Failed to read device name from {yaml_path}: {e}")
        return None

    def _detect_yaml_profile(self, yaml_path: str) -> str:
        current_name = self._read_device_name(yaml_path)
        if current_name == LEGION_GO_S_NAME:
            return "legion_go_s"
        return "default"

    def _is_readonly_enabled(self) -> bool:
        if not os.path.exists(STEAMOS_READONLY):
            return False
        result = subprocess.run(
            [STEAMOS_READONLY, "status"],
            capture_output=True,
            text=True,
            check=False,
            env=self._system_command_env(),
        )
        return result.returncode == 0

    @contextmanager
    def _writable_filesystem(self):
        was_readonly = self._is_readonly_enabled()
        if was_readonly:
            if self._run_command([STEAMOS_READONLY, "disable"]) is None:
                raise RuntimeError("Failed to disable SteamOS read-only mode")
        try:
            yield
        finally:
            if was_readonly:
                self._run_command(
                    [STEAMOS_READONLY, "enable"], record_error=False
                )

    def _restart_inputplumber(self) -> bool:
        return self._run_command([SYSTEMCTL, "restart", "inputplumber"]) is not None

    def _load_backup_meta(self) -> dict | None:
        path = self._backup_meta_path()
        try:
            if not os.path.exists(path):
                return None
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            decky.logger.error(f"Failed to load backup metadata: {e}")
            return None

    def _save_backup_meta(self, meta: dict) -> bool:
        path = self._backup_meta_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
            return True
        except Exception as e:
            self._set_error(f"Failed to save backup metadata: {e}")
            return False

    def _create_backup(self, yaml_path: str, original_name: str) -> bool:
        backup_yaml = self._backup_yaml_path()
        try:
            os.makedirs(os.path.dirname(backup_yaml), exist_ok=True)
            shutil.copy2(yaml_path, backup_yaml)
            return self._save_backup_meta(
                {
                    "original_name": original_name,
                    "device_yaml_path": yaml_path,
                }
            )
        except Exception as e:
            self._set_error(f"Failed to create backup: {e}")
            return False

    def _replace_device_name(self, yaml_path: str, new_name: str) -> bool:
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            replaced = False
            new_lines: list[str] = []
            for line in lines:
                if line.startswith("name:"):
                    new_lines.append(f"name: {new_name}\n")
                    replaced = True
                else:
                    new_lines.append(line)

            if not replaced:
                self._set_error(f"No name field found in {yaml_path}")
                return False

            with open(yaml_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
            return True
        except Exception as e:
            self._set_error(f"Failed to update device name: {e}")
            return False

    def _restore_from_backup(self) -> bool:
        meta = self._load_backup_meta()
        backup_yaml = self._backup_yaml_path()
        if not meta or not os.path.exists(backup_yaml):
            self._set_error("No backup found to restore the default controller profile")
            return False

        yaml_path = meta.get("device_yaml_path")
        if not yaml_path:
            self._set_error("Backup metadata is missing device_yaml_path")
            return False

        try:
            shutil.copy2(backup_yaml, yaml_path)
            return True
        except Exception as e:
            self._set_error(f"Failed to restore backup: {e}")
            return False

    def _require_root(self) -> bool:
        if os.geteuid() == 0:
            return True
        self._set_error(
            "Controller switching requires root. Run: sudo systemctl restart plugin_loader"
        )
        return False

    async def _restore_default_yaml(self, yaml_path: str) -> bool:
        yaml_profile = self._detect_yaml_profile(yaml_path)
        if yaml_profile == "default":
            return True

        try:
            with self._writable_filesystem():
                if not self._restore_from_backup():
                    return False
                if not self._restart_inputplumber():
                    return False
        except RuntimeError as e:
            self._set_error(str(e))
            return False
        return True

    async def _apply_legion_go_s_yaml(self, yaml_path: str, current_name: str) -> bool:
        if current_name == LEGION_GO_S_NAME:
            return True

        try:
            with self._writable_filesystem():
                if not os.path.exists(self._backup_yaml_path()):
                    if not self._create_backup(yaml_path, current_name):
                        return False
                if not self._replace_device_name(yaml_path, LEGION_GO_S_NAME):
                    return False
                if not self._restart_inputplumber():
                    return False
        except RuntimeError as e:
            self._set_error(str(e))
            return False
        return True

    async def _apply_startup_settings(self):
        selection = self.settings.get("selected_controller", "default")
        if selection != "ps5_edge":
            return

        if os.geteuid() != 0:
            decky.logger.warning(
                "Cannot reapply PS5 target on startup without root (euid=%s)",
                os.geteuid(),
            )
            return

        if self._set_inputplumber_target(PS5_EDGE_TARGET):
            decky.logger.info(
                "Reapplied %s inputplumber target on startup", PS5_EDGE_NAME
            )
        else:
            decky.logger.error(
                "Failed to reapply PS5 target on startup: %s", self.last_error
            )

    async def _main(self):
        self.settings_path = os.path.join(
            decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json"
        )
        await self.load_settings()
        decky.logger.info(
            "steamos-controller-changer initialized (euid=%s, plugin_dir=%s)",
            os.geteuid(),
            decky.DECKY_PLUGIN_DIR,
        )
        await self._apply_startup_settings()

    async def _unload(self):
        decky.logger.info("steamos-controller-changer unloaded")

    async def _migration(self):
        pass

    async def load_settings(self):
        defaults = {"selected_controller": "default"}
        try:
            if os.path.exists(self.settings_path):
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self.settings = {**defaults, **loaded}
            else:
                self.settings = defaults.copy()
                await self.save_settings()
        except Exception as e:
            decky.logger.error(f"Failed to load settings: {e}")
            self.settings = defaults.copy()
        return self.settings

    async def save_settings(self):
        try:
            os.makedirs(os.path.dirname(self.settings_path), exist_ok=True)
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            decky.logger.error(f"Failed to save settings: {e}")

    def _read_plugin_version(self) -> str:
        try:
            package_json = Path(decky.DECKY_PLUGIN_DIR) / "package.json"
            if package_json.exists():
                with open(package_json, "r", encoding="utf-8") as f:
                    return json.load(f).get("version", "unknown")
        except Exception as e:
            decky.logger.error(f"Failed to read plugin version: {e}")
        return "unknown"

    def _resolve_default_name(
        self, yaml_path: str | None, current_name: str | None
    ) -> str:
        meta = self._load_backup_meta()
        if meta and meta.get("original_name"):
            return meta["original_name"]
        if current_name and current_name != LEGION_GO_S_NAME:
            return current_name
        if current_name == LEGION_GO_S_NAME:
            return meta.get("original_name") if meta else "Default Controller"
        return "Default Controller"

    async def get_controller_settings(self) -> dict:
        self.last_error = ""
        yaml_path = self._find_device_yaml()
        current_name = self._read_device_name(yaml_path) if yaml_path else None
        yaml_profile = self._detect_yaml_profile(yaml_path) if yaml_path else "default"
        selected = self.settings.get("selected_controller", "default")
        if selected not in VALID_SELECTIONS:
            selected = "default"

        return {
            "device_available": yaml_path is not None,
            "device_yaml_path": yaml_path or "",
            "board_name": self._read_board_name() or "",
            "default_name": self._resolve_default_name(yaml_path, current_name),
            "current_name": current_name or "",
            "yaml_profile": yaml_profile,
            "active_controller": selected,
            "legion_go_s_name": LEGION_GO_S_NAME,
            "ps5_edge_name": PS5_EDGE_NAME,
            "has_backup": os.path.exists(self._backup_yaml_path()),
            "last_error": self.last_error,
            "running_as_root": os.geteuid() == 0,
            "effective_uid": os.geteuid(),
            "plugin_version": self._read_plugin_version(),
        }

    async def set_controller(self, selection: str) -> bool:
        self.last_error = ""
        selection = (selection or "").strip().lower()
        if selection not in VALID_SELECTIONS:
            self._set_error(f"Invalid controller selection: {selection}")
            return False

        if not self._require_root():
            return False

        yaml_path = self._find_device_yaml()
        if not yaml_path:
            self._set_error("Could not find InputPlumber device profile for this board")
            return False

        current_name = self._read_device_name(yaml_path)
        if not current_name:
            self._set_error("Could not read current controller name from device profile")
            return False

        previous = self.settings.get("selected_controller", "default")
        if previous not in VALID_SELECTIONS:
            previous = "default"

        if previous == selection:
            if selection == "ps5_edge":
                return self._set_inputplumber_target(PS5_EDGE_TARGET)
            return True

        yaml_profile = self._detect_yaml_profile(yaml_path)

        if previous == "ps5_edge" and selection != "ps5_edge":
            if not self._set_inputplumber_target(DEFAULT_TARGET):
                return False

        if selection == "ps5_edge":
            if yaml_profile != "default":
                if not await self._restore_default_yaml(yaml_path):
                    return False
            if not self._set_inputplumber_target(PS5_EDGE_TARGET):
                return False
            self.settings["selected_controller"] = "ps5_edge"
            await self.save_settings()
            decky.logger.info("Controller switched to %s", selection)
            return True

        if selection == "legion_go_s":
            if not await self._apply_legion_go_s_yaml(yaml_path, current_name):
                return False
        elif yaml_profile != "default":
            if not await self._restore_default_yaml(yaml_path):
                return False

        self.settings["selected_controller"] = selection
        await self.save_settings()
        decky.logger.info("Controller switched to %s", selection)
        return True
