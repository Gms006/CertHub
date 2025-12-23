from __future__ import annotations

from types import SimpleNamespace

from app.workers.queue import enqueue_unique, sanitize_job_id


def test_sanitize_job_id_is_case_insensitive(tmp_path):
    path = tmp_path / "Certs" / "Teste.PFX"
    job_a = sanitize_job_id(path)
    job_b = sanitize_job_id(str(path).lower())
    assert job_a == job_b


def test_enqueue_unique_deduplicates_jobs():
    class FakeQueue:
        def __init__(self):
            self.jobs = {}

        def fetch_job(self, job_id):
            return self.jobs.get(job_id)

        def enqueue(self, func, *args, job_id=None, **kwargs):
            job = SimpleNamespace(id=job_id, func=func, args=args, kwargs=kwargs)
            self.jobs[job_id] = job
            return job

    def dummy(*args, **kwargs):
        return None

    queue = FakeQueue()
    first = enqueue_unique(queue, dummy, "payload", job_id="job-1")
    second = enqueue_unique(queue, dummy, "payload", job_id="job-1")

    assert first is second
    assert len(queue.jobs) == 1
