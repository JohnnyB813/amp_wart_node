# Compile the selected upstream commit unchanged; run its native tests, never the node.
FROM alpine:3.23.4 AS build
RUN apk add --no-cache meson libgcc musl-dev gcc g++ linux-headers pkgconf fmt
ARG BUILD_JOBS=2
ARG WARTHOG_COMMIT=unknown
ENV WARTHOG_COMMIT=${WARTHOG_COMMIT}
WORKDIR /code
COPY . /code
RUN LDFLAGS='-static' meson setup /build --default-library=static --buildtype=release \
    && meson compile -C /build -j "${BUILD_JOBS}" \
    && meson test -C /build --no-rebuild --print-errorlogs \
    && DESTDIR=/install meson install -C /build --no-rebuild
FROM scratch AS export-stage
COPY --from=build /install/usr/local/bin/wart-node /wart-node-linux