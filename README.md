# SteamOS Controller Changer

Decky Loader plugin that switches the InputPlumber device profile between your native handheld controller and **Lenovo Legion Go S** emulation.

Useful when you want SteamOS to treat a non-Legion device (for example ASUS ROG Xbox Ally) with the Legion Go S controller profile.

## Features

- Detects the current device profile from `/sys/devices/virtual/dmi/id/board_name`
- Shows a dropdown with the native controller (Default) and Lenovo Legion Go S
- Backs up the original YAML before switching
- Handles SteamOS read-only filesystem (`steamos-readonly disable/enable`)
- Restarts `inputplumber` after each change

## Requirements

- Decky Loader with root plugin support (`flags: ["root"]` in `plugin.json`)
- InputPlumber installed (`inputplumber` systemd service)
- A matching device YAML under `/usr/share/inputplumber/devices/`

Restart Decky as root after install:

```bash
sudo systemctl restart plugin_loader
```

## Build

```bash
pnpm install
pnpm run build
```

Create a release zip:

```bash
./release.sh
```

## Install

**One-line terminal install:** `curl -fsSL -H 'Cache-Control: no-cache' https://raw.githubusercontent.com/lonsdaleite/steamos-controller-changer/main/install.sh | bash`

Manual install:

1. Open [Releases](https://github.com/lonsdaleite/steamos-controller-changer/releases)
2. Download the latest `steamos-controller-changer-v*.zip` from Releases (not the Source code archive)
3. Install via Decky Loader plugin browser or unzip into `~/homebrew/plugins/`
4. Restart Decky: `sudo systemctl restart plugin_loader`

## How it works

On startup the plugin:

1. Reads `board_name` from DMI
2. Finds the matching InputPlumber device YAML
3. Reads the `name:` field (for example `ASUS ROG Xbox Ally`)
4. Shows that name as the Default option in the dropdown

When switching to **Lenovo Legion Go S**:

1. Disables read-only mode if enabled
2. Saves the original YAML and default name to the plugin settings directory
3. Replaces the `name:` field in the device YAML
4. Restarts `inputplumber`
5. Re-enables read-only mode if it was enabled before

When switching back to Default, the plugin restores the YAML from backup and restarts `inputplumber`.

## License

MIT
