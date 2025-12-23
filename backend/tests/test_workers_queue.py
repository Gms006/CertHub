from __future__ import annotations

from types import SimpleNamespace

from rq.job import JobStatus

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
            job = SimpleNamespace(
                id=job_id,
                func=func,
                args=args,
                kwargs=kwargs,
                get_status=lambda: JobStatus.QUEUED,
                cancel=lambda: None,
                delete=lambda remove_from_queue=True: None,
            )
            self.jobs[job_id] = job
            return job

    def dummy(*args, **kwargs):
        return None

    queue = FakeQueue()
    first, first_deduped = enqueue_unique(queue, dummy, "payload", job_id="job-1")
    second, second_deduped = enqueue_unique(queue, dummy, "payload", job_id="job-1")

    assert first is second
    assert first_deduped is False
    assert second_deduped is True
    assert len(queue.jobs) == 1


def test_enqueue_unique_reenqueues_finished_jobs():
    class FakeJob:
        def __init__(self, status):
            self._status = status
            self.id = "job-1"

        def get_status(self):
            return self._status

        def cancel(self):
            return None

        def delete(self, remove_from_queue=True):
            return None

    class FakeQueue:
        def __init__(self):
            self.jobs = {}
            self.enqueued = 0

        def fetch_job(self, job_id):
            return self.jobs.get(job_id)

        def enqueue(self, func, *args, job_id=None, **kwargs):
            self.enqueued += 1
            job = FakeJob(JobStatus.QUEUED)
            self.jobs[job_id] = job
            return job

    def dummy(*args, **kwargs):
        return None

    queue = FakeQueue()
    queue.jobs["job-1"] = FakeJob(JobStatus.FINISHED)
    first, first_deduped = enqueue_unique(queue, dummy, "payload", job_id="job-1")

    assert first_deduped is False
    assert queue.enqueued == 1
