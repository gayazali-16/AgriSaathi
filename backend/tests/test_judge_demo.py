from scripts.seed_judge_demo import seed


def test_seed_is_offline_idempotent_and_never_reopens_closed_cases(tmp_path, monkeypatch):
    import sqlite3
    import httpx
    def unexpected_network(*args, **kwargs):
        raise AssertionError("Judge seeding must be offline")
    monkeypatch.setattr(httpx.AsyncClient, "get", unexpected_network)
    path = tmp_path / "judge.sqlite3"
    first = seed(path)
    assert first["status"] == "needs_review" and first["version"] == 2
    assert first["synthetic_only"] and not first["live_model_call"]
    assert seed(path) == first
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM cases").fetchone()[0] == 1
        assert db.execute("SELECT contact_requested_at FROM cases").fetchone()[0]
        # Simulate a closed persisted case to verify that seeding never overwrites it.
        db.execute("UPDATE cases SET status='resolved',version=3")
    closed = seed(path)
    assert closed["status"] == "resolved" and closed["version"] == 3
