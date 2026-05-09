#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="${1:-0.1.0}"
PKG_NAME="asus-smart-charge"
BUILD_ROOT="${ROOT_DIR}/build"
BUILD_DIR="${BUILD_ROOT}/${PKG_NAME}_${VERSION}"
STAGE_DIR="${BUILD_DIR}/stage"
RPM_ROOT="${BUILD_DIR}/rpmbuild"
APPDIR="${BUILD_DIR}/AppDir"
OUTPUT_DEB="${BUILD_ROOT}/${PKG_NAME}_${VERSION}_all.deb"
OUTPUT_RPM="${BUILD_ROOT}/${PKG_NAME}-${VERSION}-1.noarch.rpm"
OUTPUT_APPIMAGE="${BUILD_ROOT}/${PKG_NAME}-${VERSION}-x86_64.AppImage"

log() {
  printf '%s\n' "$1"
}

warn() {
  printf 'Warning: %s\n' "$1" >&2
}

require_command() {
  local command_name="$1"
  command -v "${command_name}" >/dev/null 2>&1
}

write_maintainer_scripts() {
  local target_dir="$1"

  cat > "${target_dir}/postinst" <<'EOF'
#!/bin/sh
set -e
/usr/lib/asus-smart-charge/asus-smart-charge-helper bootstrap || true
systemctl daemon-reload || true
systemctl enable asus-smart-charge.service >/dev/null 2>&1 || true
systemctl enable --now asus-smart-charge.timer >/dev/null 2>&1 || true
systemctl restart asus-smart-charge.service >/dev/null 2>&1 || true
EOF

  cat > "${target_dir}/prerm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ]; then
  systemctl disable --now asus-smart-charge.timer >/dev/null 2>&1 || true
  systemctl disable asus-smart-charge.service >/dev/null 2>&1 || true
fi
EOF

  cat > "${target_dir}/postrm" <<'EOF'
#!/bin/sh
set -e
systemctl daemon-reload || true
EOF

  chmod 0755 \
    "${target_dir}/postinst" \
    "${target_dir}/prerm" \
    "${target_dir}/postrm"
}

stage_common_tree() {
  rm -rf "${BUILD_DIR}"
  mkdir -p \
    "${STAGE_DIR}/DEBIAN" \
    "${STAGE_DIR}/usr/bin" \
    "${STAGE_DIR}/usr/lib/${PKG_NAME}/src" \
    "${STAGE_DIR}/usr/share/applications" \
    "${STAGE_DIR}/usr/share/polkit-1/actions" \
    "${STAGE_DIR}/usr/share/icons/hicolor/scalable/apps" \
    "${STAGE_DIR}/usr/lib/systemd/system" \
    "${STAGE_DIR}/usr/lib/systemd/system-sleep"

  install -m 0755 "${ROOT_DIR}/bin/asus-smart-charge" "${STAGE_DIR}/usr/bin/asus-smart-charge"
  install -m 0755 "${ROOT_DIR}/bin/asus-smart-charge-helper" "${STAGE_DIR}/usr/lib/${PKG_NAME}/asus-smart-charge-helper"
  cp -a "${ROOT_DIR}/src/." "${STAGE_DIR}/usr/lib/${PKG_NAME}/src/"
  install -m 0644 "${ROOT_DIR}/packaging/asus-smart-charge.desktop" "${STAGE_DIR}/usr/share/applications/asus-smart-charge.desktop"
  install -m 0644 "${ROOT_DIR}/packaging/com.osbusters.AsusSmartCharge.policy" "${STAGE_DIR}/usr/share/polkit-1/actions/com.osbusters.AsusSmartCharge.policy"
  install -m 0644 "${ROOT_DIR}/packaging/asus-smart-charge.svg" "${STAGE_DIR}/usr/share/icons/hicolor/scalable/apps/asus-smart-charge.svg"
  install -m 0644 "${ROOT_DIR}/packaging/asus-smart-charge.service" "${STAGE_DIR}/usr/lib/systemd/system/asus-smart-charge.service"
  install -m 0644 "${ROOT_DIR}/packaging/asus-smart-charge.timer" "${STAGE_DIR}/usr/lib/systemd/system/asus-smart-charge.timer"
  install -m 0755 "${ROOT_DIR}/packaging/asus-smart-charge.system-sleep" "${STAGE_DIR}/usr/lib/systemd/system-sleep/asus-smart-charge"

  cat > "${STAGE_DIR}/DEBIAN/control" <<EOF
Package: ${PKG_NAME}
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: all
Depends: python3, python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, pkexec, systemd
Maintainer: ixoz <local@localhost>
Description: Desktop app for Asus laptop controls
 A GTK app and system service that manage Asus battery charge thresholds,
 CPU maximum clock limits, fan/performance profiles, and keyboard lighting,
 including temporary one-time charging targets and automatic re-apply
 after boot or resume.
EOF

  write_maintainer_scripts "${STAGE_DIR}/DEBIAN"
}

build_deb() {
  if ! require_command dpkg-deb; then
    warn "dpkg-deb is not installed; skipping .deb output."
    return
  fi

  dpkg-deb --root-owner-group --build "${STAGE_DIR}" "${OUTPUT_DEB}"
  log "Built ${OUTPUT_DEB}"
}

build_rpm() {
  local spec_file source_root source_tarball

  if ! require_command rpmbuild; then
    warn "rpmbuild is not installed; skipping .rpm output."
    return
  fi

  mkdir -p \
    "${RPM_ROOT}/BUILD" \
    "${RPM_ROOT}/BUILDROOT" \
    "${RPM_ROOT}/RPMS" \
    "${RPM_ROOT}/SOURCES" \
    "${RPM_ROOT}/SPECS" \
    "${RPM_ROOT}/SRPMS"

  source_root="${BUILD_DIR}/${PKG_NAME}-${VERSION}"
  rm -rf "${source_root}"
  mkdir -p "${source_root}"
  cp -a \
    "${ROOT_DIR}/bin" \
    "${ROOT_DIR}/src" \
    "${ROOT_DIR}/packaging" \
    "${ROOT_DIR}/README.md" \
    "${source_root}/"

  source_tarball="${RPM_ROOT}/SOURCES/${PKG_NAME}-${VERSION}.tar.gz"
  tar -C "${BUILD_DIR}" -czf "${source_tarball}" "${PKG_NAME}-${VERSION}"

  spec_file="${RPM_ROOT}/SPECS/${PKG_NAME}.spec"
  cat > "${spec_file}" <<EOF
Name:           ${PKG_NAME}
Version:        ${VERSION}
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
mkdir -p %{buildroot}/usr/lib/${PKG_NAME}/src
mkdir -p %{buildroot}/usr/share/applications
mkdir -p %{buildroot}/usr/share/polkit-1/actions
mkdir -p %{buildroot}/usr/share/icons/hicolor/scalable/apps
mkdir -p %{buildroot}/usr/lib/systemd/system
mkdir -p %{buildroot}/usr/lib/systemd/system-sleep

install -m 0755 bin/asus-smart-charge %{buildroot}/usr/bin/asus-smart-charge
install -m 0755 bin/asus-smart-charge-helper %{buildroot}/usr/lib/${PKG_NAME}/asus-smart-charge-helper
cp -a src/. %{buildroot}/usr/lib/${PKG_NAME}/src/
install -m 0644 packaging/asus-smart-charge.desktop %{buildroot}/usr/share/applications/asus-smart-charge.desktop
install -m 0644 packaging/com.osbusters.AsusSmartCharge.policy %{buildroot}/usr/share/polkit-1/actions/com.osbusters.AsusSmartCharge.policy
install -m 0644 packaging/asus-smart-charge.svg %{buildroot}/usr/share/icons/hicolor/scalable/apps/asus-smart-charge.svg
install -m 0644 packaging/asus-smart-charge.service %{buildroot}/usr/lib/systemd/system/asus-smart-charge.service
install -m 0644 packaging/asus-smart-charge.timer %{buildroot}/usr/lib/systemd/system/asus-smart-charge.timer
install -m 0755 packaging/asus-smart-charge.system-sleep %{buildroot}/usr/lib/systemd/system-sleep/asus-smart-charge

%post
/usr/lib/${PKG_NAME}/asus-smart-charge-helper bootstrap || true
systemctl daemon-reload || true
systemctl enable ${PKG_NAME}.service >/dev/null 2>&1 || true
systemctl enable --now ${PKG_NAME}.timer >/dev/null 2>&1 || true
systemctl restart ${PKG_NAME}.service >/dev/null 2>&1 || true

%preun
if [ \$1 -eq 0 ]; then
  systemctl disable --now ${PKG_NAME}.timer >/dev/null 2>&1 || true
  systemctl disable ${PKG_NAME}.service >/dev/null 2>&1 || true
fi

%postun
systemctl daemon-reload || true

%files
/usr/bin/asus-smart-charge
/usr/lib/${PKG_NAME}
/usr/share/applications/asus-smart-charge.desktop
/usr/share/polkit-1/actions/com.osbusters.AsusSmartCharge.policy
/usr/share/icons/hicolor/scalable/apps/asus-smart-charge.svg
/usr/lib/systemd/system/asus-smart-charge.service
/usr/lib/systemd/system/asus-smart-charge.timer
/usr/lib/systemd/system-sleep/asus-smart-charge
EOF

  rpmbuild \
    --define "_topdir ${RPM_ROOT}" \
    --buildroot "${RPM_ROOT}/BUILDROOT" \
    -bb "${spec_file}"

  find "${RPM_ROOT}/RPMS" -name '*.rpm' -exec cp {} "${OUTPUT_RPM}" \;
  log "Built ${OUTPUT_RPM}"
}

build_appimage() {
  local apprun_file

  if ! require_command appimagetool; then
    warn "appimagetool is not installed; skipping .AppImage output."
    return
  fi

  rm -rf "${APPDIR}"
  mkdir -p "${APPDIR}"
  cp -a "${STAGE_DIR}/usr" "${APPDIR}/usr"
  cp "${ROOT_DIR}/packaging/asus-smart-charge.desktop" "${APPDIR}/asus-smart-charge.desktop"
  cp "${ROOT_DIR}/packaging/asus-smart-charge.svg" "${APPDIR}/asus-smart-charge.svg"

  sed -i 's|^Exec=.*|Exec=asus-smart-charge|' "${APPDIR}/asus-smart-charge.desktop"

  apprun_file="${APPDIR}/AppRun"
  cat > "${apprun_file}" <<'EOF'
#!/bin/sh
HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec "${HERE}/usr/bin/asus-smart-charge" "$@"
EOF
  chmod 0755 "${apprun_file}"

  ARCH=x86_64 appimagetool "${APPDIR}" "${OUTPUT_APPIMAGE}"
  log "Built ${OUTPUT_APPIMAGE}"
}

stage_common_tree
build_deb
build_rpm
build_appimage
