# SteamOS Controller Changer

Decky Loader plugin that changes how InputPlumber emulates your handheld controller on SteamOS.

You can switch between three profiles:

- **Default** — native controller profile for your device (for example `ASUS ROG Xbox Ally`)
- **Lenovo Legion Go S** — rewrites the InputPlumber device YAML so SteamOS treats the device as Legion Go S
- **PS5 DualSense Edge** — keeps the default YAML and sets the InputPlumber emulation target to DualSense Edge

Useful on devices like ROG Ally when you want Legion Go S button layout or DualSense Edge emulation without replacing hardware.

## Features

- Detects the current device profile from `/sys/devices/virtual/dmi/id/board_name`
- Dropdown with Default, Lenovo Legion Go S, and PS5 DualSense Edge
- Backs up the original InputPlumber YAML before Legion Go S switching
- Handles SteamOS read-only filesystem (`steamos-readonly disable/enable`)
- Restarts `inputplumber` after YAML profile changes
- Reapplies DualSense Edge target on plugin startup (target resets after reboots)

## Requirements

- Decky Loader with root plugin support (`flags: ["root"]` in `plugin.json`)
- InputPlumber installed (`inputplumber` systemd service and CLI)
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
5. If PS5 DualSense Edge was selected previously, runs `inputplumber device 0 targets set ds5-edge` again

### Default

Native profile. If a Legion Go S YAML override was applied earlier, the plugin restores the original YAML from backup and restarts `inputplumber`.

When switching away from PS5 DualSense Edge, the plugin first runs:

```bash
inputplumber device 0 targets set deck-uhid
```

### Lenovo Legion Go S

1. Disables read-only mode if enabled
2. Saves the original YAML and default name to the plugin settings directory
3. Replaces the `name:` field in the device YAML with `Lenovo Legion Go S`
4. Restarts `inputplumber`
5. Re-enables read-only mode if it was enabled before

If PS5 DualSense Edge was active, `deck-uhid` is restored before the YAML change.

### PS5 DualSense Edge

1. If the YAML is not on Default (for example Legion Go S is active), restores Default first
2. Runs:

```bash
inputplumber device 0 targets set ds5-edge
```

The YAML file is not modified in this mode. On every plugin startup the DualSense Edge target is reapplied because InputPlumber resets it after reboots.

When switching away from PS5 DualSense Edge to Default or Legion Go S:

```bash
inputplumber device 0 targets set deck-uhid
```

Then the usual Default or Legion Go S logic runs.

## License

MIT
