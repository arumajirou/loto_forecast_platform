import json

from loto.events.publisher import EventPublisher


def test_event_publisher_writes_append_only_jsonl(tmp_path):
    pub = EventPublisher(tmp_path / "events.jsonl")
    pub.publish("run.stage.changed", {"run_id": "r1", "stage": "TRAIN"})
    pub.publish("forecast.sealed", {"forecast_id": "f1"})
    lines = (tmp_path / "events.jsonl").read_text().splitlines()
    assert [json.loads(line)["type"] for line in lines] == ["run.stage.changed", "forecast.sealed"]
