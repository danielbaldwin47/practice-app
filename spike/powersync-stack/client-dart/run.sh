#!/bin/sh
# Runs the scratch client against a stack already brought up by ../docker-compose.yaml.
#
# There is no Dart or Flutter toolchain on the NAS, so this borrows the `dart:stable`
# image and joins the stack's compose network to reach `api` and `powersync` by name.
#
# Two things this works around, both real:
#   * the PowerSync core extension must be copied off the bind mount before it can
#     be dlopen'd -- /tmp on this host is mounted noexec;
#   * `powersync_core` needs a system sqlite3 WITH extension loading enabled.
set -e
CORE_VERSION=v0.4.14
HERE=$(cd "$(dirname "$0")" && pwd)

[ -f "$HERE/libpowersync_x64.so" ] || curl -sL -o "$HERE/libpowersync_x64.so" \
  "https://github.com/powersync-ja/powersync-sqlite-core/releases/download/${CORE_VERSION}/libpowersync_x64.linux.so"

exec docker run --rm --network psspike_default -v "$HERE:/w" -w /w dart:stable sh -c '
  apt-get update -qq >/dev/null 2>&1
  apt-get install -y -qq libsqlite3-0 libsqlite3-dev >/dev/null 2>&1
  cp /w/libpowersync_x64.so /usr/lib/ && chmod 755 /usr/lib/libpowersync_x64.so
  mkdir -p /app && cp -r /w/bin /w/pubspec.yaml /app/ && cd /app
  dart pub get >/dev/null 2>&1
  exec dart run bin/client.dart'
