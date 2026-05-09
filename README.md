<p align="center">
  <img src="assets/img1.png" width="700" alt="zhelper Linux GUI — Battery threshold, CPU clock, fan profile, GPU power, and keyboard RGB control for ASUS ROG laptops on Ubuntu, Fedora, and Arch Linux">
</p>

<h1 align="center">⚡ zhelper — ASUS Laptop Manager for Linux</h1>

<p align="center">
  <strong>The all-in-one ASUS laptop management tool for Linux</strong><br>
  Battery charge limiter · CPU underclocking · Fan profiles · NVIDIA GPU toggle · Keyboard RGB lighting
</p>

<p align="center">
  <a href="#-installation"><img alt="Get Started" src="https://img.shields.io/badge/Get_Started-blue?style=for-the-badge"></a>
  <a href="#-features"><img alt="Features" src="https://img.shields.io/badge/Features-purple?style=for-the-badge"></a>
  <a href="#-compatibility"><img alt="Compatibility" src="https://img.shields.io/badge/Compatibility-green?style=for-the-badge"></a>
  <img alt="Platform" src="https://img.shields.io/badge/Platform-Linux-informational?style=for-the-badge&logo=linux&logoColor=white">
  <img alt="License" src="https://img.shields.io/badge/License-GPL--3.0-blue?style=for-the-badge">
</p>

---

## 🔍 What Is zhelper?

**zhelper** is a free, open-source, native **Linux desktop application** that gives you full control over your **ASUS ROG, TUF, Vivobook, Zenbook, and ProArt** laptop hardware — directly from a modern GTK4 + libadwaita GUI. No more terminal commands, no Windows-only MyASUS, and no need for multiple fragmented tools.

If you own an ASUS laptop running **Ubuntu, Linux Mint, Pop!_OS, Fedora, Arch Linux, Manjaro, openSUSE**, or any systemd-based distro, this app is built for you.

### Why You Need This

ASUS laptops on Linux have always lacked the official software that Windows users get for free — **MyASUS** and **Armoury Crate** don't exist on Linux. That means:

- ❌ No way to set a battery charge limit to extend battery lifespan
- ❌ No GUI to control fan speed profiles (Silent / Balanced / Turbo)
- ❌ No way to underclock the CPU for cooler, quieter operation
- ❌ No control over keyboard RGB lighting and brightness
- ❌ No toggle for the NVIDIA discrete GPU to save power
- ❌ Settings reset after every reboot or suspend/resume

**zhelper solves all of these** in one lightweight, native application that persists your settings across reboots, suspend cycles, and lid open/close events.

---

## ✨ Features

### 🔋 Battery Charge Threshold Control

Limit your ASUS laptop's maximum charge level to **extend battery lifespan** by years. Lithium-ion batteries degrade faster when kept at 100% — setting a cap at 60–80% significantly reduces wear.

- **Quick presets**: 55%, 60%, 70%, 80%, 100%
- **Custom threshold**: any value from 50% to 100% with a precision slider
- **One-time charge override**: temporarily charge to 80%, 100%, or any custom target, then automatically revert to your normal limit
- Works with the Linux kernel's `charge_control_end_threshold` sysfs interface

### 🖥️ CPU Clock Limiter (Underclocking)

Lower the maximum CPU frequency to **reduce heat, fan noise, and power consumption** — ideal for everyday browsing, coding, or video calls where you don't need full performance.

- Adjustable clock speed slider with real-time GHz readout
- Live CPU temperature monitoring
- Uses the Linux CPUFreq scaling subsystem (`scaling_max_freq`)
- Settings persist across reboots

### 🌬️ Fan & Performance Profile Control

Switch between ASUS firmware fan profiles without rebooting or using command-line tools:

| Profile | Behavior |
|---------|----------|
| **Silent** | Lowest fan noise; fans can stop completely at idle temperatures on supported models |
| **Balanced** | Default everyday performance and fan behavior |
| **Turbo** | Maximum cooling and peak CPU/GPU performance |

- Live fan RPM readout for CPU and GPU fans
- Supports both `platform_profile` and ASUS WMI (`throttle_thermal_policy`) backends
- Compatible with models that expose `/sys/firmware/acpi/platform_profile`

### 🎮 NVIDIA Discrete GPU Power Control

Disable your NVIDIA RTX/GTX GPU completely to **save battery power** when you only need integrated AMD or Intel graphics:

- Toggle dGPU on/off with a single switch
- Live GPU state, TGP wattage, and display-path information
- Uses the ASUS WMI `dgpu_disable` sysfs interface
- Persists your choice across reboots

### ⌨️ Keyboard RGB Lighting Control

Full control over your ASUS laptop's per-key or zone-based RGB keyboard lighting:

- **Brightness**: 4 levels (Off, Low, Medium, High)
- **Modes**: Static, Rainbow, Flashing, Glow
- **Color**: Full RGB color picker with custom palette support
- **Speed**: Slow, Medium, Fast animation speed
- Uses the ASUS `kbd_rgb_mode` and `kbd_rgb_state` sysfs interfaces
- Brightness and RGB settings survive suspend/resume with a built-in sleep hook

### 🔁 Persistent Enforcement

Unlike manual sysfs tweaks that vanish on reboot:

- **Systemd service + timer**: re-applies all settings 20 seconds after boot and every 60 seconds
- **Systemd sleep hook**: re-applies settings after suspend/resume with a 2-second delay to wait for ASUS firmware initialization
- **Automatic revert**: one-time charge targets automatically revert to your normal threshold once the battery reaches the goal
- All configuration stored in `/etc/asus-smart-charge/state.json`

---

## 🖥️ Compatibility

### Supported Linux Distributions

zhelper works on any modern Linux distribution with systemd, GTK4, and libadwaita:

| Distribution | Package Format | Status |
|--------------|---------------|--------|
| **Ubuntu** 22.04+ / 24.04+ | `.deb` | ✅ Fully supported |
| **Linux Mint** 21+ | `.deb` | ✅ Fully supported |
| **Pop!_OS** 22.04+ | `.deb` | ✅ Fully supported |
| **Debian** 12+ | `.deb` | ✅ Fully supported |
| **Fedora** 38+ | `.rpm` | ✅ Fully supported |
| **openSUSE** Tumbleweed | `.rpm` | ✅ Fully supported |
| **Arch Linux** / **Manjaro** | `.AppImage` | ✅ Fully supported |
| **EndeavourOS** | `.AppImage` | ✅ Fully supported |
| Any distro with GTK4 | `.AppImage` | ✅ Fully supported |

### Supported ASUS Laptop Series

The app uses standard ASUS WMI and Linux kernel interfaces, so it works with most ASUS laptops manufactured from 2018 onward:

- **ASUS ROG Zephyrus** (G14, G15, G16, GA401, GA402, GA502, GA503, GU603, GU604)
- **ASUS ROG Strix** (G15, G17, G513, G533, G713, G733, G814, G834)
- **ASUS ROG Flow** (X13, X16, Z13)
- **ASUS TUF Gaming** (A15, A17, F15, F17, FX505, FX507, FA506, FA507, FA706, FA707)
- **ASUS Vivobook** / **Vivobook Pro** (14X, 15, 16X, M1505, K3605, S5402)
- **ASUS Zenbook** (14, 14X, UX3402, UX3405, UM3402, UM5606, UX5304)
- **ASUS ProArt Studiobook** (16, H7604, W7604)
- **ASUS ExpertBook** (B1, B5, B9)
- And any ASUS laptop that exposes `charge_control_end_threshold` in `/sys/class/power_supply/BAT*/`

> **Not sure if your model is compatible?** Run this command in a terminal:
> ```bash
> ls /sys/class/power_supply/BAT*/charge_control_end_threshold 2>/dev/null && echo "✅ Supported!" || echo "❌ Not supported"
> ```

### System Requirements

| Requirement | Details |
|-------------|---------|
| **Python** | 3.8 or newer |
| **GTK** | GTK 4.0 |
| **libadwaita** | 1.0+ |
| **Polkit** | For privilege escalation (`pkexec`) |
| **systemd** | For service and timer management |
| **Kernel** | Linux 5.4+ with ASUS WMI drivers |

---

## 📥 Installation

### Option 1: Install from .deb (Ubuntu, Debian, Mint, Pop!_OS)

```bash
# Clone the repository
git clone https://github.com/ixoz/Asus-ROG-Smart-Charge-Linux-GUI.git
cd Asus-ROG-Smart-Charge-Linux-GUI

# Install dependencies
sudo apt install python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 policykit-1

# Build the .deb package
./build-deb.sh

# Install it
sudo dpkg -i build/asus-smart-charge_0.1.0_all.deb
```

### Option 2: Install from .rpm (Fedora, openSUSE)

```bash
# Clone the repository
git clone https://github.com/ixoz/Asus-ROG-Smart-Charge-Linux-GUI.git
cd Asus-ROG-Smart-Charge-Linux-GUI

# Install dependencies
sudo dnf install python3 python3-gobject gtk4 libadwaita polkit systemd

# Build the .rpm package (requires rpmbuild)
sudo dnf install rpm-build
./build-deb.sh

# Install it
sudo rpm -i build/asus-smart-charge-0.1.0-1.noarch.rpm
```

### Option 3: Use the AppImage (Any Distribution)

```bash
# Clone the repository
git clone https://github.com/ixoz/Asus-ROG-Smart-Charge-Linux-GUI.git
cd Asus-ROG-Smart-Charge-Linux-GUI

# Build the AppImage (requires appimagetool)
./build-deb.sh

# Make it executable and run
chmod +x build/asus-smart-charge-0.1.0-x86_64.AppImage
./build/asus-smart-charge-0.1.0-x86_64.AppImage
```

### What Happens After Installation

The installer automatically:

1. Creates the config directory at `/etc/asus-smart-charge/`
2. Registers a **systemd service** that enforces your settings on boot
3. Registers a **systemd timer** that re-applies settings every 60 seconds
4. Installs a **systemd sleep hook** to restore settings after suspend/resume
5. Adds the app to your desktop applications menu

---

## 🚀 Usage

### Launch the App

After installation, search for **"zhelper"** in your desktop application launcher — or run from a terminal:

```bash
asus-smart-charge
```

The app opens with five tabbed sections: **Battery**, **CPU**, **Fan**, **GPU**, and **Keyboard**. Each section has a clean, intuitive interface with real-time status readouts.

### Setting a Battery Charge Limit

1. Open the **Battery** tab
2. Select a preset (55%, 60%, 70%, 80%, 100%) or choose **Custom** and drag the slider
3. Click **Apply Custom Limit** for custom values
4. Your threshold takes effect immediately and persists across reboots

### One-Time Charging Override

Need a full charge for a trip? Use **Quick Action**:

- **Charge To 100% Once** — temporarily allows a full charge, then reverts
- **Charge To 80% Once** — handy middle-ground option
- **Custom One Time** — pick any target between 50–100%

The app automatically reverts to your normal limit once the battery reaches the target.

### Controlling CPU Speed

1. Open the **CPU** tab
2. Drag the slider to your desired maximum clock speed (in GHz)
3. Click **Apply**
4. Watch the live CPU temperature readout to see the effect

### Switching Fan Profiles

1. Open the **Fan** tab
2. Select **Silent**, **Balanced**, or **Turbo**
3. Watch real-time fan RPM values update in the Live Fan Speed panel

### Toggling the NVIDIA GPU

1. Open the **GPU** tab
2. Flip the **Enable NVIDIA RTX** switch on or off
3. The dGPU state, TGP wattage, and display-path info update in real time

### Customizing Keyboard Lighting

1. Open the **Keyboard** tab
2. Adjust **Brightness** (0–3), select a **Mode** (Static, Rainbow, Flashing, Glow)
3. Pick a **Color** from the full RGB palette and set the animation **Speed**
4. Click **Apply Lighting**

---

## 🛠️ Local Development

Want to contribute or hack on the app? Run directly from source:

### Run the GUI

```bash
PYTHONPATH=src python3 bin/asus-smart-charge
```

### Run the Helper CLI

```bash
# Check current status (no root required)
PYTHONPATH=src python3 bin/asus-smart-charge-helper status

# Set a battery charge limit
PYTHONPATH=src sudo -E python3 bin/asus-smart-charge-helper set-default 80

# Temporarily charge to 100%
PYTHONPATH=src sudo -E python3 bin/asus-smart-charge-helper charge-once 100

# Set CPU maximum clock (in kHz — e.g. 2900000 = 2.9 GHz)
PYTHONPATH=src sudo -E python3 bin/asus-smart-charge-helper set-cpu-max 2900000

# Set fan/performance profile
PYTHONPATH=src sudo -E python3 bin/asus-smart-charge-helper set-thermal-profile silent

# Set keyboard lighting
PYTHONPATH=src sudo -E python3 bin/asus-smart-charge-helper set-keyboard-lighting \
    --brightness 3 --mode static --color '#00aaff' --speed medium

# Re-apply all saved settings (used by systemd service)
PYTHONPATH=src sudo -E python3 bin/asus-smart-charge-helper enforce
```

### Project Structure

```
zhelper/
├── bin/
│   ├── asus-smart-charge            # GUI entry point
│   └── asus-smart-charge-helper     # Privileged helper CLI
├── src/asus_smart_charge/
│   ├── __init__.py                  # App ID, name, version
│   ├── common.py                    # Shared constants, sysfs readers, validators
│   ├── gui.py                       # GTK4 + libadwaita UI
│   └── helper.py                    # Root-level CLI commands
├── packaging/
│   ├── asus-smart-charge.desktop    # .desktop launcher
│   ├── asus-smart-charge.service    # systemd oneshot service
│   ├── asus-smart-charge.timer      # systemd periodic timer
│   ├── asus-smart-charge.system-sleep  # suspend/resume hook
│   ├── asus-smart-charge.svg        # App icon
│   └── com.osbusters.AsusSmartCharge.policy  # Polkit policy
├── assets/
│   └── img1.png                     # Screenshot
├── build-deb.sh                     # Multi-format build script
└── README.md
```

---

## 📦 Build Packages

The unified build script detects which packaging tools are installed and builds all available formats in one run:

```bash
./build-deb.sh           # Uses version 0.1.0 by default
./build-deb.sh 1.0.0     # Or specify a custom version
```

| Format | Required Tool | Output |
|--------|--------------|--------|
| `.deb` | `dpkg-deb` | `build/asus-smart-charge_<ver>_all.deb` |
| `.rpm` | `rpmbuild` | `build/asus-smart-charge-<ver>-1.noarch.rpm` |
| `.AppImage` | `appimagetool` | `build/asus-smart-charge-<ver>-x86_64.AppImage` |

If an optional tool is missing, the script prints a warning and skips only that format.

---

## ❓ Frequently Asked Questions

<details>
<summary><strong>Does zhelper replace asusctl / asus-linux?</strong></summary>

zhelper is a standalone tool — it does **not** depend on or conflict with `asusctl` or the asus-linux project. It talks directly to the same kernel sysfs interfaces. You can use both side by side, though running two tools that write to the same sysfs paths simultaneously may cause conflicts.
</details>

<details>
<summary><strong>Will limiting my battery charge actually extend its lifespan?</strong></summary>

Yes. Lithium-ion batteries experience significantly less chemical degradation when stored at 60–80% charge versus 100%. Studies from Battery University and real-world telemetry from laptop manufacturers confirm this. Setting a charge limit of 70–80% is the most commonly recommended sweet spot.
</details>

<details>
<summary><strong>Why does my battery still show "Not Charging" even though it's plugged in?</strong></summary>

This is normal. When your battery level is at or above the charge threshold, the kernel tells the charger to stop. The battery reports "Not Charging" because the limit is working correctly.
</details>

<details>
<summary><strong>Does the charge limit survive reboots?</strong></summary>

Yes. The systemd service re-applies your saved settings 20 seconds after boot, and the timer re-checks every 60 seconds. A separate sleep hook handles suspend/resume. Your settings are stored persistently in `/etc/asus-smart-charge/state.json`.
</details>

<details>
<summary><strong>Can I run zhelper on a non-ASUS laptop?</strong></summary>

No. The app depends on ASUS-specific kernel drivers (`asus-nb-wmi`, `asus-wmi`) and sysfs interfaces that are unique to ASUS hardware.
</details>

<details>
<summary><strong>Why does the keyboard brightness reset after waking from sleep?</strong></summary>

ASUS firmware resets keyboard RGB settings during suspend/resume. zhelper includes a systemd sleep hook that waits 2 seconds for the firmware to finish its reset, then re-applies your saved lighting settings automatically.
</details>

<details>
<summary><strong>Do I need root access?</strong></summary>

The app uses `pkexec` (Polkit) to request elevated privileges only when writing to hardware sysfs files. Reading status information does not require root. You will see a standard authentication dialog when making changes.
</details>

---

## 🐛 Troubleshooting

### The app says "No supported battery threshold file was found"

Your kernel may not have the ASUS battery charge threshold driver loaded. Try:

```bash
sudo modprobe asus_wmi
sudo modprobe asus_nb_wmi
ls /sys/class/power_supply/BAT*/charge_control_end_threshold
```

If no file appears, your laptop model may not support this feature in the current kernel version. Consider upgrading to a newer kernel (5.10+ recommended).

### Fan profile controls are greyed out

Check if the platform profile or ASUS thermal policy interface is available:

```bash
cat /sys/firmware/acpi/platform_profile_choices 2>/dev/null
cat /sys/devices/platform/asus-nb-wmi/throttle_thermal_policy 2>/dev/null
```

If both return errors, your kernel or ASUS WMI driver may not support thermal profiles for your model.

### GPU toggle has no effect

Make sure the ASUS `dgpu_disable` sysfs interface exists:

```bash
cat /sys/devices/platform/asus-nb-wmi/dgpu_disable
```

After toggling the GPU off, `nvidia-smi` may report "no device found" — this is expected behavior. Toggle it back on to restore NVIDIA GPU access.

### Keyboard RGB doesn't change

Verify that the kernel exposes the keyboard lighting interfaces:

```bash
ls /sys/class/leds/asus::kbd_backlight/kbd_rgb_mode 2>/dev/null
ls /sys/class/leds/asus::kbd_backlight/kbd_rgb_state 2>/dev/null
```

If these files don't exist, your laptop model may not expose RGB control through the ASUS WMI driver.

---

## 📄 License

zhelper is licensed under the **GNU General Public License v3.0**. See the [LICENSE](LICENSE) file for the full text.

---

## 🤝 Contributing

Contributions are welcome! If you'd like to add support for additional ASUS models, fix bugs, or improve the UI:

1. Fork this repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Make your changes and test on your ASUS hardware
4. Submit a pull request with a description of what you changed and which laptop model you tested on

Please include your ASUS laptop model and Linux distribution in bug reports.

---

## 📚 Related Projects & Resources

- [ASUS Linux Community](https://asus-linux.org/) — Broader ASUS Linux support ecosystem
- [asusctl](https://gitlab.com/asus-linux/asusctl) — Alternative CLI tool for ASUS laptops
- [Linux kernel ASUS WMI documentation](https://www.kernel.org/doc/html/latest/admin-guide/laptops/asus-wmi.html)
- [Battery University — How to prolong lithium-ion battery life](https://batteryuniversity.com/article/bu-808-how-to-prolong-lithium-based-batteries)

---

## ⭐ Star This Project

If zhelper helps you manage your ASUS laptop on Linux, please **give it a ⭐ on GitHub** — it helps other ASUS Linux users discover the tool!

---

<p align="center">
  Made with ❤️ for the ASUS Linux community<br>
  <sub>ASUS ROG · ASUS TUF Gaming · ASUS Vivobook · ASUS Zenbook · ASUS ProArt · ASUS ExpertBook — all supported on Linux</sub>
</p>
