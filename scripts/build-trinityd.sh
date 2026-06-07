#!/usr/bin/env bash
# Build Trinity daemon from source inside GitHub Actions.
# Adjust SOURCE_URL to the correct Trinity (TTY) source repo.
set -euo pipefail

SOURCE_URL="https://github.com/trinity-project/trinity/archive/refs/heads/master.tar.gz"
BUILD_DIR="/tmp/trinityd-build"
OUT_BIN="bin/trinityd"

echo "[build-trinityd] Installing build deps..."
sudo apt-get install -y -q build-essential libssl-dev libboost-all-dev libdb5.3++-dev \
  libminiupnpc-dev libzmq3-dev pkg-config libevent-dev automake libtool

mkdir -p "$BUILD_DIR" bin

echo "[build-trinityd] Downloading source..."
curl -sL "$SOURCE_URL" | tar -xz -C "$BUILD_DIR" --strip-components=1

cd "$BUILD_DIR"
echo "[build-trinityd] Running autogen..."
./autogen.sh

echo "[build-trinityd] Configuring..."
./configure --disable-wallet --without-gui --disable-tests --disable-bench \
  --with-incompatible-bdb CXXFLAGS="-O2 -march=native"

echo "[build-trinityd] Building (this takes ~5-10 min)..."
make -j$(nproc) src/trinityd

cp src/trinityd "$(pwd)/../$OUT_BIN"
echo "[build-trinityd] Done: $OUT_BIN"
