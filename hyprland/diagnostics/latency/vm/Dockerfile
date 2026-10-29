ARG DEPS_IMAGE
FROM ${DEPS_IMAGE}
USER root
RUN pacman -S --needed --noconfirm linux mkinitcpio e2fsprogs openssh perf drm-info python strace gdb \
        wayland-protocols pkgconf libdrm && \
    pacman -Scc --noconfirm
RUN kver=$(ls /usr/lib/modules) && \
    mkinitcpio -k "$kver" -g /boot/initramfs-test.img -S autodetect,kms,sd-vconsole,keyboard,microcode
COPY key.pub /root/.ssh/authorized_keys
RUN chmod 700 /root/.ssh && chmod 600 /root/.ssh/authorized_keys && \
    passwd -d root && \
    systemctl mask systemd-firstboot.service && \
    systemctl enable sshd systemd-networkd && \
    printf '[Match]\nName=en*\n[Network]\nDHCP=yes\n' > /etc/systemd/network/20-wired.network && \
    printf '/dev/vda / ext4 rw 0 1\nshare /mnt/share 9p trans=virtio,version=9p2000.L,msize=1048576,nofail 0 0\n' > /etc/fstab && \
    mkdir -p /mnt/share && \
    printf 'vkms\n9pnet_virtio\n9p\nudmabuf\n' > /etc/modules-load.d/latency.conf && \
    printf 'options vkms enable_overlay=1 enable_cursor=1\n' > /etc/modprobe.d/vkms.conf && \
    printf 'kernel.perf_event_paranoid=-1\nkernel.kptr_restrict=0\n' > /etc/sysctl.d/90-perf.conf && \
    echo latency-vm > /etc/hostname
