#!/usr/bin/env bash
# Build Fennec daemon from source — https://github.com/FennecBlockchain/Fennec
set -euo pipefail

SOURCE_URL="https://github.com/FennecBlockchain/Fennec/archive/refs/heads/master.tar.gz"
BUILD_DIR="/tmp/fennecd-build"
OUT_DIR="$HOME/.fennecd"

echo "[build-fennecd] Installing build deps..."
sudo apt-get install -y -q build-essential libssl-dev libboost-all-dev libdb5.3++-dev \
  libminiupnpc-dev libzmq3-dev pkg-config libevent-dev automake libtool

mkdir -p "$BUILD_DIR" "$OUT_DIR"

echo "[build-fennecd] Downloading source from FennecBlockchain/Fennec..."
curl -sL "$SOURCE_URL" | tar -xz -C "$BUILD_DIR" --strip-components=1

cd "$BUILD_DIR"
./autogen.sh
./configure --disable-wallet --without-gui --disable-tests --disable-bench \
  --with-incompatible-bdb CXXFLAGS="-O2 -march=native"
make -j$(nproc) src/fennecd

cp src/fennecd "$OUT_DIR/fennecd"
echo "[build-fennecd] Done: $OUT_DIR/fennecd"
