#!/bin/bash
set -euo pipefail
stage=/data/xuancheng/structural_env/cache/structural_afni
mkdir -p "$stage/rpms/rpmdb" "$stage/rpmroot"
cd "$stage/rpms"
base=https://dl.rockylinux.org/pub/rocky/9/AppStream/x86_64/os/Packages
if [ ! -f RPM-GPG-KEY-Rocky-9 ]; then
    curl -fsSL --max-time 90 -o RPM-GPG-KEY-Rocky-9 \
      https://dl.rockylinux.org/pub/rocky/RPM-GPG-KEY-Rocky-9
fi
rpm --dbpath "$stage/rpms/rpmdb" --import RPM-GPG-KEY-Rocky-9
packages=(
 m/motif-2.3.4-32.el9.x86_64.rpm
 m/mesa-libGLU-9.0.1-6.el9.x86_64.rpm
 m/mesa-libGLw-8.0.0-23.el9.x86_64.rpm
 l/libXp-1.0.3-11.el9.x86_64.rpm
 l/libjpeg-turbo-2.0.90-7.el9.x86_64.rpm
 l/libfontenc-1.1.3-17.el9.x86_64.rpm
 l/libxkbfile-1.1.0-8.el9.x86_64.rpm
 p/pixman-0.40.0-6.el9_3.x86_64.rpm
 l/libXfont2-2.0.3-12.el9_8.3.x86_64.rpm
 x/xorg-x11-server-Xvfb-1.20.11-34.el9_8.3.x86_64.rpm
 x/xorg-x11-server-common-1.20.11-34.el9_8.3.x86_64.rpm
 x/xkbcomp-1.4.4-4.el9.x86_64.rpm
 x/xkeyboard-config-2.33-2.el9.0.1.noarch.rpm
 x/xorg-x11-fonts-misc-7.5-33.el9.noarch.rpm
 n/netpbm-10.95.00-3.el9.x86_64.rpm
 n/netpbm-progs-10.95.00-3.el9.x86_64.rpm
)
for relative in "${packages[@]}"; do
    name=${relative##*/}
    curl -fsSL --connect-timeout 15 --max-time 180 --retry 2 --retry-all-errors \
         -o "$name" "$base/$relative"
    rpm --dbpath "$stage/rpms/rpmdb" -K "$name"
    sha256sum "$name"
    cd "$stage/rpmroot"
    rpm2cpio "$stage/rpms/$name" | cpio -idm --no-absolute-filenames
    cd "$stage/rpms"
done
