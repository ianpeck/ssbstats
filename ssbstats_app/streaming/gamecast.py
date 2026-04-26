"""Gamecast blueprint — local-only live match viewer.

Only registered when LOCAL_STREAMING=1. Talks to Kafka (default localhost:9094)
for the live data plane and to the prod DB (read-only) only via the picker.

Endpoints:
    GET  /gamecast            page
    POST /gamecast/start      pick a historical match + publish match.scheduled
    GET  /gamecast/stream     SSE multiplex of match.live_state / win_prob / events
"""
from __future__ import annotations

import json
import os
import queue
import threading
import time

from flask import Blueprint, Response, jsonify, render_template, request


gamecast_bp = Blueprint("gamecast", __name__)


def streaming_enabled() -> bool:
    return os.getenv("LOCAL_STREAMING", "0") == "1"


@gamecast_bp.route("/gamecast")
def gamecast_page():
    return render_template("gamecast.html")


@gamecast_bp.route("/gamecast/start", methods=["POST"])
def gamecast_start():
    """Pick a random historical match and publish it to match.scheduled."""
    from streaming_jobs.kafka_io import TOPIC_SCHEDULED, ensure_topics, make_producer, produce_json
    from streaming_jobs.picker.main import pick_match

    season = request.args.get("season", type=int)
    ppv = request.args.get("ppv")

    match = pick_match(season=season, ppv=ppv)

    ensure_topics()
    producer = make_producer()
    try:
        produce_json(producer, TOPIC_SCHEDULED, key=match["match_id"], value=match)
        producer.flush(5)
    finally:
        producer.flush(5)

    return jsonify(match)


@gamecast_bp.route("/gamecast/stream")
def gamecast_stream():
    """Server-sent events: forward Kafka topics to the browser as named events.

    Each request gets its own Kafka consumer with a unique group id, starting
    from the latest offset so a fresh tab sees current matches, not history.
    """
    from streaming_jobs.kafka_io import (
        TOPIC_EVENTS,
        TOPIC_LIVE_STATE,
        TOPIC_WIN_PROB,
        make_consumer,
    )

    topic_to_event = {
        TOPIC_LIVE_STATE: "live_state",
        TOPIC_WIN_PROB: "win_prob",
        TOPIC_EVENTS: "event",
    }
    topics = list(topic_to_event)
    group_id = f"gamecast-sse-{int(time.time() * 1000)}-{os.getpid()}"

    out_q: "queue.Queue[tuple[str, str] | None]" = queue.Queue(maxsize=1000)
    stop = threading.Event()

    def kafka_pump():
        consumer = make_consumer(group_id=group_id, topics=topics, from_latest=True)
        try:
            while not stop.is_set():
                msg = consumer.poll(timeout=0.5)
                if msg is None or msg.error():
                    continue
                event_name = topic_to_event.get(msg.topic())
                if event_name is None:
                    continue
                try:
                    out_q.put_nowait((event_name, msg.value().decode("utf-8")))
                except queue.Full:
                    pass  # browser is slow — drop rather than block
        finally:
            consumer.close()
            out_q.put(None)  # sentinel

    threading.Thread(target=kafka_pump, daemon=True).start()

    def sse_generator():
        # Initial comment so proxies / browsers open the stream immediately.
        yield ": connected\n\n"
        last_keepalive = time.time()
        try:
            while True:
                try:
                    item = out_q.get(timeout=1.0)
                except queue.Empty:
                    if time.time() - last_keepalive > 15:
                        yield ": keepalive\n\n"
                        last_keepalive = time.time()
                    continue
                if item is None:
                    break
                event_name, payload = item
                yield f"event: {event_name}\ndata: {payload}\n\n"
                last_keepalive = time.time()
        finally:
            stop.set()

    return Response(
        sse_generator(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering if anyone proxies this
            "Connection": "keep-alive",
        },
    )
