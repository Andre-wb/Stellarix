FROM rust:1-bookworm AS builder

WORKDIR /app

COPY Cargo.toml Cargo.lock ./
COPY src ./src
COPY migrations ./migrations
COPY templates ./templates
COPY static ./static

RUN --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/app/target \
    cargo build --release --locked --bin stellarix && \
    cp target/release/stellarix /usr/local/bin/stellarix

FROM debian:bookworm-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 app

WORKDIR /app

COPY --from=builder /usr/local/bin/stellarix /usr/local/bin/stellarix
COPY static ./static
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod +x /usr/local/bin/entrypoint.sh && chown -R app:app /app

USER app

ENV BIND_ADDR=0.0.0.0:8000 \
    APP_ENVIRONMENT=production \
    LOG_LEVEL=info

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://localhost:8000/login || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["stellarix"]
