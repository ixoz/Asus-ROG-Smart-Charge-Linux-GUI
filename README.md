# Asus Smart Charge
<img src="assets/img1.png" width="600">

Ubuntu desktop app for managing Asus battery charge thresholds with:

- Fixed threshold choices: `55%`, `60%`, `70%`, `80%`, `100%`
- One-time `100%` charging that falls back to the user's normal threshold
- CPU maximum clock control through Linux CPUFreq, useful for underclocking
- ASUS fan/performance profile control: Silent, Balanced, and Turbo
- ASUS keyboard lighting brightness, color, mode, and speed control
- Persistent enforcement after reboot and after suspend/resume
- Local `.deb` packaging with the GUI, helper, systemd units, and policy file

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

## Build a package

```bash
./build-deb.sh
```
