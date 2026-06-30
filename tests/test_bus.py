from jarvis.core.bus import EventBus


def test_subscriber_receives_published_event():
    bus = EventBus()
    received = []
    bus.subscribe("command", lambda payload: received.append(payload))
    bus.publish("command", {"text": "hi"})
    assert received == [{"text": "hi"}]


def test_multiple_subscribers_each_get_event():
    bus = EventBus()
    a, b = [], []
    bus.subscribe("evt", a.append)
    bus.subscribe("evt", b.append)
    bus.publish("evt", 1)
    assert a == [1] and b == [1]


def test_unsubscribe_stops_delivery():
    bus = EventBus()
    got = []
    unsub = bus.subscribe("evt", got.append)
    unsub()
    bus.publish("evt", 1)
    assert got == []


def test_subscriber_error_does_not_break_others():
    bus = EventBus()
    good = []
    bus.subscribe("evt", lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    bus.subscribe("evt", good.append)
    bus.publish("evt", 1)
    assert good == [1]
