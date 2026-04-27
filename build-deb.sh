#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="${1:-0.1.0}"
PKG_NAME="asus-smart-charge"
BUILD_DIR="${ROOT_DIR}/build/${PKG_NAME}_${VERSION}"
STAGE_DIR="${BUILD_DIR}/stage"
OUTPUT_DEB="${ROOT_DIR}/build/${PKG_NAME}_${VERSION}_all.deb"

rm -rf "${BUILD_DIR}"
mkdir -p \
  "${STAGE_DIR}/DEBIAN" \
  "${STAGE_DIR}/usr/bin" \
  "${STAGE_DIR}/usr/lib/${PKG_NAME}/src" \
  "${STAGE_DIR}/usr/share/applications" \
  "${STAGE_DIR}/usr/share/polkit-1/actions" \
  "${STAGE_DIR}/usr/lib/systemd/system" \
  "${STAGE_DIR}/usr/lib/systemd/system-sleep"

install -m 0755 "${ROOT_DIR}/bin/asus-smart-charge" "${STAGE_DIR}/usr/bin/asus-smart-charge"
install -m 0755 "${ROOT_DIR}/bin/asus-smart-charge-helper" "${STAGE_DIR}/usr/lib/${PKG_NAME}/asus-smart-charge-helper"
cp -a "${ROOT_DIR}/src/." "${STAGE_DIR}/usr/lib/${PKG_NAME}/src/"
install -m 0644 "${ROOT_DIR}/packaging/asus-smart-charge.desktop" "${STAGE_DIR}/usr/share/applications/asus-smart-charge.desktop"
install -m 0644 "${ROOT_DIR}/packaging/com.osbusters.AsusSmartCharge.policy" "${STAGE_DIR}/usr/share/polkit-1/actions/com.osbusters.AsusSmartCharge.policy"
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
Description: Desktop app for Asus battery charge thresholds
 A GTK app and system service that manage Asus battery charge thresholds,
 including a temporary one-time 100 percent mode and automatic re-apply
 after boot or resume.
EOF

cat > "${STAGE_DIR}/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
/usr/lib/asus-smart-charge/asus-smart-charge-helper bootstrap || true
systemctl daemon-reload || true
systemctl enable asus-smart-charge.service >/dev/null 2>&1 || true
systemctl enable --now asus-smart-charge.timer >/dev/null 2>&1 || true
systemctl restart asus-smart-charge.service >/dev/null 2>&1 || true
EOF

cat > "${STAGE_DIR}/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "remove" ]; then
  systemctl disable --now asus-smart-charge.timer >/dev/null 2>&1 || true
  systemctl disable asus-smart-charge.service >/dev/null 2>&1 || true
fi
EOF

cat > "${STAGE_DIR}/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
systemctl daemon-reload || true
EOF

chmod 0755 \
  "${STAGE_DIR}/DEBIAN/postinst" \
  "${STAGE_DIR}/DEBIAN/prerm" \
  "${STAGE_DIR}/DEBIAN/postrm"

dpkg-deb --root-owner-group --build "${STAGE_DIR}" "${OUTPUT_DEB}"
printf 'Built %s\n' "${OUTPUT_DEB}"
