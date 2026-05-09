# Asus Smart Charge
<img src="assets/img1.png" width="600">

Ubuntu desktop app for managing Asus battery charge thresholds with:

- Fixed threshold choices: `55%`, `60%`, `70%`, `80%`, `100%`
- Custom threshold selection in the supported `50%` to `100%` range
- One-time charging to `80%`, `100%`, or a custom target that falls back to the user's normal threshold
- CPU maximum clock control through Linux CPUFreq, useful for underclocking
- ASUS fan/performance profile control: Silent, Balanced, and Turbo
- ASUS keyboard lighting brightness, color, mode, and speed control
- Persistent enforcement after reboot and after suspend/resume
- Local `.deb`, `.rpm`, and `.AppImage` packaging from one build script

## Local development

Run the GUI from the project directory:

```bash
PYTHONPATH=src python3 bin/asus-smart-charge
```

Run the helper directly:

```bash
PYTHONPATH=src python3 bin/asus-smart-charge-helper status
```

Set a CPU maximum clock directly, using kHz:

```bash
PYTHONPATH=src python3 bin/asus-smart-charge-helper set-cpu-max 2900000
```

Set a fan/performance profile directly:

```bash
PYTHONPATH=src python3 bin/asus-smart-charge-helper set-thermal-profile silent
```

Set keyboard lighting directly:

```bash
PYTHONPATH=src python3 bin/asus-smart-charge-helper set-keyboard-lighting --brightness 3 --mode static --color '#00aaff' --speed medium
```

## Build packages

```bash
./build-deb.sh
```

The script always stages the app once, then:

- Builds a `.deb` when `dpkg-deb` is installed
- Builds a Fedora-friendly `.rpm` when `rpmbuild` is installed
- Builds an `.AppImage` when `appimagetool` is installed

If an optional packaging tool is missing, the script prints a warning and skips only that artifact.
