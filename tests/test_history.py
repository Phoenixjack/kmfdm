from kmfdm.services.history import HistoryEvent, append_history_events, load_history_events


def test_history_events_append_and_load_jsonl(tmp_path) -> None:
    history_path = tmp_path / ".kmfdm-history.jsonl"
    event = HistoryEvent.create(
        action="metadata_saved",
        scope="symbol",
        library="CONNECTORs",
        item="CONN_HDMI",
        field="MPN",
        original="SS-53000-002",
        current="SS-53000-003",
        metadata={"change_source": "manual"},
    )

    append_history_events(history_path, [event])

    loaded_events = load_history_events(history_path)
    assert loaded_events == [event]
