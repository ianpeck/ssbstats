#!/usr/bin/env bash
# Fetch the Flink-Kafka SQL connector JAR into ./lib so the Flink containers
# pick it up via the volume mount in docker-compose.local.yml.
#
# Run once after cloning, then again whenever you bump Flink/Kafka versions.

set -euo pipefail

LIB_DIR="$(cd "$(dirname "$0")" && pwd)/lib"
mkdir -p "$LIB_DIR"

FLINK_VERSION=1.18.1
CONNECTOR_VERSION=3.1.0-1.18

JAR="flink-sql-connector-kafka-${CONNECTOR_VERSION}.jar"
URL="https://repo.maven.apache.org/maven2/org/apache/flink/flink-sql-connector-kafka/${CONNECTOR_VERSION}/${JAR}"

if [[ -f "$LIB_DIR/$JAR" ]]; then
  echo "Already present: $JAR"
  exit 0
fi

echo "Downloading $JAR ..."
curl -fSL "$URL" -o "$LIB_DIR/$JAR"
echo "Saved to $LIB_DIR/$JAR"
