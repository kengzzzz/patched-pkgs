# check=skip=InvalidDefaultArgInFrom
ARG BASE_IMAGE
FROM ${BASE_IMAGE} AS dependencies
COPY PKGBUILD /tmp/PKGBUILD
RUN bash -euo pipefail -c '\
    PKGVER=0 PKGREL=0 source /tmp/PKGBUILD; \
    packages=(git); \
    for dep in "${depends[@]}" "${makedepends[@]}"; do \
        case "$dep" in *.so*|opengl-driver) continue ;; esac; \
        packages+=("${dep%%[<>=]*}"); \
    done; \
    pacman -Syu --needed --noconfirm "${packages[@]}"'
RUN useradd --create-home builder && \
    install -d -o builder -g builder /build /artifacts
RUN sed -i 's/-march=x86-64 -mtune=generic -O2/-march=znver5 -mtune=znver5 -O3/' /etc/makepkg.conf && \
    grep -q -- '-march=znver5 -mtune=znver5 -O3' /etc/makepkg.conf && \
    gcc -march=znver5 -mtune=znver5 -Q --help=target | grep -E '^ +-m(arch|tune)='

FROM dependencies AS source
ARG UPSTREAM_URL
ARG UPSTREAM_REF
ARG UPSTREAM_COMMIT
USER builder
WORKDIR /build
RUN git clone --filter=blob:none "$UPSTREAM_URL" upstream && \
    test "$(git -C upstream rev-parse "$UPSTREAM_REF^{commit}")" = "$UPSTREAM_COMMIT" && \
    git -C upstream checkout --detach "$UPSTREAM_COMMIT" && \
    git -C upstream submodule update --init --recursive
COPY --chown=builder:builder patches/ /build/patches/
RUN cd upstream && \
    for patch in ../patches/*.patch; do \
        [ -e "$patch" ] || continue; \
        git apply --index --verbose "$patch"; \
    done

FROM source AS build
ARG PKGVER
ARG PKGREL
ARG BUILD_JOBS=8
ARG UPSTREAM_COMMIT
ENV PKGVER=${PKGVER} PKGREL=${PKGREL} BUILD_JOBS=${BUILD_JOBS} \
    MAKEFLAGS=-j${BUILD_JOBS} UPSTREAM_COMMIT=${UPSTREAM_COMMIT}
COPY --chown=builder:builder PKGBUILD /build/PKGBUILD
# Tests run znver5 code, which can crash on another CPU.
RUN native=$(gcc -march=native -Q --help=target | awk '$1 == "-march=" { print $2 }') && \
    echo "Build CPU: $native" && \
    if [ "$native" = znver5 ]; then check=; else check=--nocheck; fi && \
    nice -n 19 makepkg --noconfirm --cleanbuild $check && \
    cp -- *.pkg.tar.zst /artifacts/ && \
    makepkg --printsrcinfo > /artifacts/.SRCINFO && \
    pacman -Q > /artifacts/build-packages.txt && \
    { git -C upstream rev-parse HEAD; \
      git -C upstream describe --tags --always; \
      git -C upstream diff --cached --stat; \
      cd patches && sha256sum -- *.patch 2>/dev/null || true; } > /artifacts/source.txt

FROM scratch AS packages
COPY --from=build /artifacts/ /
