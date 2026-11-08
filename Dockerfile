# Build Ferry from a pinned upstream commit, then patch its embedded web UI.
FROM alpine:3.23 AS source
RUN apk add --no-cache git python3
ARG FERRY_COMMIT=0c3c719fbc5cf716fe373d0e74274b458344fc58
RUN git clone --filter=blob:none https://github.com/max1874/ferry.git /src \
    && git -C /src checkout "${FERRY_COMMIT}"
COPY patch-multi-upload.py /tmp/patch-multi-upload.py
COPY patch-timelines.py /tmp/patch-timelines.py
COPY patches/timelines.go /src/internal/ferry/timelines.go
RUN python3 /tmp/patch-multi-upload.py && python3 /tmp/patch-timelines.py

FROM --platform=$BUILDPLATFORM golang:1.26.3-alpine AS build
ARG TARGETOS
ARG TARGETARCH
WORKDIR /src
COPY --from=source /src/ ./
RUN go mod download
RUN CGO_ENABLED=0 GOOS=${TARGETOS} GOARCH=${TARGETARCH} go build -trimpath -ldflags="-s -w" -o /out/ferry ./cmd/ferry

FROM alpine:3.23
LABEL org.opencontainers.image.title="Ferry Multi Upload" \
      org.opencontainers.image.description="Ferry with browser multi-file upload support" \
      org.opencontainers.image.source="https://github.com/FallenDawn/ferry-multi-upload" \
      org.opencontainers.image.licenses="MIT"
RUN addgroup -S ferry && adduser -S -D -H -u 10001 -G ferry ferry \
    && mkdir -p /data && chown ferry:ferry /data
COPY --from=build /out/ferry /usr/local/bin/ferry
COPY --from=source /src/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
USER ferry
VOLUME ["/data"]
EXPOSE 42817
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
