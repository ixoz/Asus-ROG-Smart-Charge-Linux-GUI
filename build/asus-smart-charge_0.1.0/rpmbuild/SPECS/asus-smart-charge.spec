Name:           asus-smart-charge
Version:        0.1.0
Release:        1%{?dist}
Summary:        Desktop app for Asus laptop controls
License:        Proprietary
BuildArch:      noarch
Source0:        %{name}-%{version}.tar.gz
Requires:       python3
Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Requires:       polkit
Requires:       systemd

%description
A GTK app and system service that manage Asus battery charge thresholds,
CPU maximum clock limits, fan/performance profiles, and keyboard lighting,
including temporary one-time charging targets and automatic re-apply
after boot or resume.

%prep
%setup -q

%build
:

%install
mkdir -p %{buildroot}/usr/bin
mkdir -p %{buildroot}/usr/lib/asus-smart-charge/src
mkdir -p %{buildroot}/usr/share/applications
mkdir -p %{buildroot}/usr/share/polkit-1/actions
mkdir -p %{buildroot}/usr/share/icons/hicolor/scalable/apps
mkdir -p %{buildroot}/usr/lib/systemd/system
mkdir -p %{buildroot}/usr/lib/systemd/system-sleep

install -m 0755 bin/asus-smart-charge %{buildroot}/usr/bin/asus-smart-charge
install -m 0755 bin/asus-smart-charge-helper %{buildroot}/usr/lib/asus-smart-charge/asus-smart-charge-helper
cp -a src/. %{buildroot}/usr/lib/asus-smart-charge/src/
install -m 0644 packaging/asus-smart-charge.desktop %{buildroot}/usr/share/applications/asus-smart-charge.desktop
install -m 0644 packaging/com.osbusters.AsusSmartCharge.policy %{buildroot}/usr/share/polkit-1/actions/com.osbusters.AsusSmartCharge.policy
install -m 0644 packaging/asus-smart-charge.svg %{buildroot}/usr/share/icons/hicolor/scalable/apps/asus-smart-charge.svg
install -m 0644 packaging/asus-smart-charge.service %{buildroot}/usr/lib/systemd/system/asus-smart-charge.service
install -m 0644 packaging/asus-smart-charge.timer %{buildroot}/usr/lib/systemd/system/asus-smart-charge.timer
install -m 0755 packaging/asus-smart-charge.system-sleep %{buildroot}/usr/lib/systemd/system-sleep/asus-smart-charge

%post
/usr/lib/asus-smart-charge/asus-smart-charge-helper bootstrap || true
systemctl daemon-reload || true
systemctl enable asus-smart-charge.service >/dev/null 2>&1 || true
systemctl enable --now asus-smart-charge.timer >/dev/null 2>&1 || true
systemctl restart asus-smart-charge.service >/dev/null 2>&1 || true

%preun
if [ $1 -eq 0 ]; then
  systemctl disable --now asus-smart-charge.timer >/dev/null 2>&1 || true
  systemctl disable asus-smart-charge.service >/dev/null 2>&1 || true
fi

%postun
systemctl daemon-reload || true

%files
/usr/bin/asus-smart-charge
/usr/lib/asus-smart-charge
/usr/share/applications/asus-smart-charge.desktop
/usr/share/polkit-1/actions/com.osbusters.AsusSmartCharge.policy
/usr/share/icons/hicolor/scalable/apps/asus-smart-charge.svg
/usr/lib/systemd/system/asus-smart-charge.service
/usr/lib/systemd/system/asus-smart-charge.timer
/usr/lib/systemd/system-sleep/asus-smart-charge
