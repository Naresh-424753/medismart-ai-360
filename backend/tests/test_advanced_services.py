from app.services import ledger, rx_parser, wearables


def test_ledger_detects_tamper():
    blocks, prev = [], "0" * 64
    for i in range(3):
        b = {"index": i, "ts": f"2026-01-0{i+1}T00:00:00", "type": "document", "payload": {"n": i}, "prev_hash": prev}
        b["hash"] = ledger.block_hash(b["index"], b["ts"], b["type"], b["payload"], b["prev_hash"])
        prev = b["hash"]; blocks.append(b)
    assert ledger.verify_blocks(blocks)["valid"]
    blocks[1]["payload"] = {"n": 99}
    assert not ledger.verify_blocks(blocks)["valid"]


def test_rx_parser_schedule():
    out = rx_parser.parse("Rx\nTab Metformin 500mg 1-0-1 after food x 30 days")
    it = out["items"][0] if isinstance(out, dict) else out[0]
    assert "metformin" in it["name"].lower() and len(it["times"]) == 2 and it["duration_days"] == 30


def test_wearable_range_check():
    assert wearables.clean_sample({"type": "heart_rate", "value": 999, "ts": "2026-11-01T10:00:00Z"}) is None
