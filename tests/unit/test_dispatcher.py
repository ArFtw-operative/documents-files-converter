from convertvault import dispatcher


def test_development_dispatch_uses_embedded_worker_and_memory_secret(monkeypatch):
    submitted = []
    monkeypatch.setattr(dispatcher.settings, "app_env", "development")
    monkeypatch.setattr(
        dispatcher._executor,
        "submit",
        lambda function, job_id: submitted.append((function, job_id)),
    )

    dispatcher.dispatch_job("job-1", "image")
    assert submitted == [(dispatcher.run_conversion.run, "job-1")]

    dispatcher.store_job_secret("job-1", "private-password", 60)
    assert dispatcher.consume_job_secret("job-1") == "private-password"
    assert dispatcher.consume_job_secret("job-1") is None
