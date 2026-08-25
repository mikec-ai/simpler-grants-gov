import json
import threading
import uuid
from pathlib import Path

import boto3
import moto
import pytest

import tests.src.db.models.factories as factories
from src.constants.lookup_constants import FileScanStatus
from src.services.files import local_file_scanner
from src.services.files.local_file_scanner import (
    _detect_scenario,
    _extract_pending_file_id,
    process_metadata_change,
    setup_local_file_scanner,
)

FAKE_FILE_SCAN_BUCKET = "test-local-mock-file-scan-bucket"
FAKE_DYNAMODB_TABLE = "test-local-virus-scan"


@pytest.fixture
def aws_setup(reset_aws_env_vars, db_session, monkeypatch):
    """Single moto context covering both s3 and DynamoDB.

    Test conftest exposes s3 and DynamoDB through separately-whitelisted
    moto contexts; if you nest them, only the inner whitelist applies, so
    one of the two services gets blocked. This fixture opens a single
    non-whitelisted moto.mock_aws so tests can exercise both at once. It
    also wires factories to db_session so PendingFile rows can be created.
    """
    monkeypatch.setattr(factories, "_db_session", db_session)

    with moto.mock_aws():
        s3 = boto3.resource("s3", region_name="us-east-1")
        s3.Bucket(FAKE_FILE_SCAN_BUCKET).create()

        dynamodb = boto3.client("dynamodb", region_name="us-east-1")
        dynamodb.create_table(
            TableName=FAKE_DYNAMODB_TABLE,
            KeySchema=[{"AttributeName": "file_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "file_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        monkeypatch.setenv("FILE_SCAN_BUCKET", f"s3://{FAKE_FILE_SCAN_BUCKET}")
        monkeypatch.setenv("FILE_SCAN_CACHE_TABLE_NAME", FAKE_DYNAMODB_TABLE)

        yield {"s3": s3, "dynamodb": dynamodb, "bucket": FAKE_FILE_SCAN_BUCKET}


def _write_metadata(path: Path, key: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"id": str(uuid.uuid4()), "key": key, "size": "42"}))
    return path


class TestExtractPendingFileId:
    def test_parses_uuid_from_unscanned_key(self):
        file_id = uuid.uuid4()
        assert _extract_pending_file_id(f"unscanned/{file_id}/foo.pdf") == file_id

    def test_returns_none_when_key_is_too_short(self):
        assert _extract_pending_file_id("unscanned/foo.pdf") is None

    def test_returns_none_when_second_segment_is_not_a_uuid(self):
        assert _extract_pending_file_id("unscanned/not-a-uuid/foo.pdf") is None


class TestDetectScenario:
    def test_infected_keyword_wins(self):
        file_id = uuid.uuid4()
        assert (
            _detect_scenario(f"unscanned/{file_id}/scenario-infected-resume.pdf")
            == local_file_scanner.SCENARIO_INFECTED
        )

    def test_wait_10s_keyword(self):
        file_id = uuid.uuid4()
        assert (
            _detect_scenario(f"unscanned/{file_id}/scenario-wait10s-cover.pdf")
            == local_file_scanner.SCENARIO_WAIT_10S
        )

    def test_no_scenario_in_key(self):
        file_id = uuid.uuid4()
        assert _detect_scenario(f"unscanned/{file_id}/just-a-file.pdf") is None


class TestProcessMetadataChange:
    def test_complete_path_moves_file_and_updates_status(
        self,
        tmp_path,
        db_client,
        db_session,
        aws_setup,
        s3_scanner_user,
    ):
        pending_file = factories.PendingFileFactory.create(file_scan_status=FileScanStatus.PENDING)
        db_session.commit()

        s3_client = boto3.client("s3", region_name="us-east-1")
        unscanned_key = f"unscanned/{pending_file.pending_file_id}/resume.pdf"
        s3_client.put_object(Bucket=aws_setup["bucket"], Key=unscanned_key, Body=b"file contents")

        metadata_path = _write_metadata(
            tmp_path / pending_file.pending_file_id.hex / "objectMetadata.json",
            unscanned_key,
        )

        process_metadata_change(str(metadata_path), db_client)

        db_session.refresh(pending_file)
        assert pending_file.file_scan_status == FileScanStatus.COMPLETE

        item = aws_setup["dynamodb"].get_item(
            TableName=FAKE_DYNAMODB_TABLE,
            Key={"file_id": {"S": str(pending_file.pending_file_id)}},
        )["Item"]
        assert item["status"]["S"] == FileScanStatus.COMPLETE.value
        assert item["user_id"]["S"] == str(pending_file.user_id)

        expected_scanned_key = f"scanned/{pending_file.pending_file_id}/resume.pdf"
        moved_body = s3_client.get_object(Bucket=aws_setup["bucket"], Key=expected_scanned_key)[
            "Body"
        ].read()
        assert moved_body == b"file contents"
        with pytest.raises(s3_client.exceptions.NoSuchKey):
            s3_client.get_object(Bucket=aws_setup["bucket"], Key=unscanned_key)

    def test_infected_scenario_moves_file_and_marks_infected(
        self,
        tmp_path,
        db_client,
        db_session,
        aws_setup,
        s3_scanner_user,
    ):
        pending_file = factories.PendingFileFactory.create(file_scan_status=FileScanStatus.PENDING)
        db_session.commit()

        s3_client = boto3.client("s3", region_name="us-east-1")
        unscanned_key = f"unscanned/{pending_file.pending_file_id}/scenario-infected-resume.pdf"
        s3_client.put_object(Bucket=aws_setup["bucket"], Key=unscanned_key, Body=b"file contents")

        metadata_path = _write_metadata(
            tmp_path / pending_file.pending_file_id.hex / "objectMetadata.json",
            unscanned_key,
        )

        process_metadata_change(str(metadata_path), db_client)

        db_session.refresh(pending_file)
        assert pending_file.file_scan_status == FileScanStatus.INFECTED

        expected_infected_key = (
            f"infected/{pending_file.pending_file_id}/scenario-infected-resume.pdf"
        )
        moved_body = s3_client.get_object(Bucket=aws_setup["bucket"], Key=expected_infected_key)[
            "Body"
        ].read()
        assert moved_body == b"file contents"
        with pytest.raises(s3_client.exceptions.NoSuchKey):
            s3_client.get_object(Bucket=aws_setup["bucket"], Key=unscanned_key)

    def test_wait_10s_scenario_runs_in_progress_then_complete(
        self,
        tmp_path,
        db_client,
        db_session,
        aws_setup,
        s3_scanner_user,
        caplog,
        monkeypatch,
    ):
        # Skip the actual 10s wait; we only care about the status sequence.
        monkeypatch.setenv("LOCAL_FILE_SCANNER_WAIT_SCENARIO_DELAY_SECONDS", "0")

        pending_file = factories.PendingFileFactory.create(file_scan_status=FileScanStatus.PENDING)
        db_session.commit()

        s3_client = boto3.client("s3", region_name="us-east-1")
        unscanned_key = f"unscanned/{pending_file.pending_file_id}/scenario-wait10s-cover.pdf"
        s3_client.put_object(Bucket=aws_setup["bucket"], Key=unscanned_key, Body=b"file contents")

        metadata_path = _write_metadata(
            tmp_path / pending_file.pending_file_id.hex / "objectMetadata.json",
            unscanned_key,
        )

        with caplog.at_level("INFO"):
            process_metadata_change(str(metadata_path), db_client)

        applied_statuses = [
            r.file_scan_status
            for r in caplog.records
            if r.message == "Local file scanner applied scan status"
        ]
        assert applied_statuses == [FileScanStatus.IN_PROGRESS, FileScanStatus.COMPLETE]

        db_session.refresh(pending_file)
        assert pending_file.file_scan_status == FileScanStatus.COMPLETE

    def test_key_not_under_unscanned_is_ignored(
        self,
        tmp_path,
        db_client,
        db_session,
        aws_setup,
    ):
        pending_file = factories.PendingFileFactory.create(file_scan_status=FileScanStatus.PENDING)
        db_session.commit()

        metadata_path = _write_metadata(
            tmp_path / "obj" / "objectMetadata.json",
            f"competitions/{pending_file.pending_file_id}/cover.pdf",
        )

        process_metadata_change(str(metadata_path), db_client)

        db_session.refresh(pending_file)
        assert pending_file.file_scan_status == FileScanStatus.PENDING

    def test_missing_pending_file_skips_dynamodb_write(
        self,
        tmp_path,
        db_client,
        aws_setup,
        s3_scanner_user,
        caplog,
    ):
        unknown_id = uuid.uuid4()
        # Upload the s3 file so _move_to_terminal_prefix has something to move;
        # the test is verifying the postgres-side missing-row behavior, not S3.
        s3_client = boto3.client("s3", region_name="us-east-1")
        unscanned_key = f"unscanned/{unknown_id}/file.pdf"
        s3_client.put_object(Bucket=aws_setup["bucket"], Key=unscanned_key, Body=b"x")

        metadata_path = _write_metadata(
            tmp_path / "obj" / "objectMetadata.json",
            unscanned_key,
        )

        with caplog.at_level("WARNING"):
            process_metadata_change(str(metadata_path), db_client)

        warnings = [
            r
            for r in caplog.records
            if r.message == "Local file scanner could not find pending file row"
        ]
        assert len(warnings) >= 1

        response = aws_setup["dynamodb"].get_item(
            TableName=FAKE_DYNAMODB_TABLE,
            Key={"file_id": {"S": str(unknown_id)}},
        )
        assert "Item" not in response


class TestSetupLocalFileScanner:
    """ENABLE_LOCAL_FILE_SCANNER is forced FALSE in conftest, so each test
    re-enables it before re-checking one specific guard."""

    def _scanner_thread_running(self) -> bool:
        return any(
            t.name == local_file_scanner.LOCAL_FILE_SCANNER_THREAD_NAME
            for t in threading.enumerate()
        )

    def test_does_not_spawn_when_environment_is_not_local(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "prod")
        monkeypatch.setenv("ENABLE_LOCAL_FILE_SCANNER", "TRUE")
        setup_local_file_scanner()
        assert not self._scanner_thread_running()

    def test_does_not_spawn_when_disabled(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "local")
        monkeypatch.setenv("ENABLE_LOCAL_FILE_SCANNER", "FALSE")
        setup_local_file_scanner()
        assert not self._scanner_thread_running()

    def test_does_not_spawn_when_werkzeug_run_main_is_unset(self, monkeypatch):
        # The Flask reloader sets WERKZEUG_RUN_MAIN to "true" only in the
        # worker; the parent imports the app with the var unset. We must not
        # spawn the thread there or it ends up running twice.
        monkeypatch.setenv("ENVIRONMENT", "local")
        monkeypatch.setenv("ENABLE_LOCAL_FILE_SCANNER", "TRUE")
        monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)
        setup_local_file_scanner()
        assert not self._scanner_thread_running()

    def test_single_process_mode_can_run_without_werkzeug_reloader(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ENVIRONMENT", "local")
        monkeypatch.setenv("ENABLE_LOCAL_FILE_SCANNER", "TRUE")
        monkeypatch.setenv("LOCAL_FILE_SCANNER_RUN_WITHOUT_RELOADER", "TRUE")
        monkeypatch.setenv("LOCAL_S3_STORE_PATH", str(tmp_path))
        monkeypatch.delenv("WERKZEUG_RUN_MAIN", raising=False)

        class FakeThread:
            def __init__(self, **kwargs):
                self.name = kwargs["name"]
                captured_args.extend(kwargs["args"])

            def start(self):
                started.append(self.name)

        started: list[str] = []
        captured_args: list[object] = []
        monkeypatch.setattr(local_file_scanner.threading, "Thread", FakeThread)

        setup_local_file_scanner()

        assert started == [local_file_scanner.LOCAL_FILE_SCANNER_THREAD_NAME]
        assert captured_args == [tmp_path, "local-mock-file-scan-bucket"]

    def test_scanner_waits_for_bucket_and_reconciles_first_object(self, monkeypatch, tmp_path):
        bucket_name = "local-mock-file-scan-bucket"
        bucket_path = tmp_path / bucket_name
        metadata_path = tmp_path / bucket_name / "object-id" / "objectMetadata.json"

        class StopAfterStartup(Exception):
            pass

        watched_paths: list[str] = []
        watch_kwargs: list[dict[str, object]] = []

        def fake_watch(path, **kwargs):
            watched_paths.append(path)
            watch_kwargs.append(kwargs)
            raise StopAfterStartup
            yield  # pragma: no cover

        def fake_sleep(_seconds):
            _write_metadata(metadata_path, f"unscanned/{uuid.uuid4()}/first.pdf")

        monkeypatch.setitem(
            __import__("sys").modules,
            "watchfiles",
            type(
                "FakeWatchfiles",
                (),
                {
                    "Change": type("Change", (), {"deleted": "deleted"}),
                    "watch": staticmethod(fake_watch),
                },
            ),
        )
        monkeypatch.setattr(local_file_scanner.time, "sleep", fake_sleep)
        monkeypatch.setattr(local_file_scanner.db, "PostgresDBClient", lambda: object())
        queued: list[Path] = []

        class FakeQueue:
            def enqueue(self, path):
                queued.append(path)

        monkeypatch.setattr(
            local_file_scanner,
            "_MetadataWorkQueue",
            lambda _db_client: FakeQueue(),
        )

        with pytest.raises(StopAfterStartup):
            local_file_scanner._run_scanner(tmp_path, bucket_name)

        assert watched_paths == [str(bucket_path)]
        assert watch_kwargs == [
            {
                "force_polling": True,
                "yield_on_timeout": True,
                "rust_timeout": local_file_scanner.LOCAL_FILE_SCANNER_RECONCILE_INTERVAL_MS,
            }
        ]
        assert queued == [metadata_path]

    def test_scanner_never_watches_or_scans_other_buckets(self, monkeypatch, tmp_path):
        bucket_name = "local-mock-file-scan-bucket"
        bucket_path = tmp_path / bucket_name
        bucket_path.mkdir()
        other_metadata_path = tmp_path / "other-bucket" / "object-id" / "objectMetadata.json"
        _write_metadata(other_metadata_path, f"unscanned/{uuid.uuid4()}/other.pdf")

        class StopAfterChange(Exception):
            pass

        watched_paths: list[str] = []

        def fake_watch(path, **_kwargs):
            watched_paths.append(path)
            yield {("added", str(other_metadata_path))}
            raise StopAfterChange

        monkeypatch.setitem(
            __import__("sys").modules,
            "watchfiles",
            type(
                "FakeWatchfiles",
                (),
                {
                    "Change": type("Change", (), {"deleted": "deleted"}),
                    "watch": staticmethod(fake_watch),
                },
            ),
        )
        monkeypatch.setattr(local_file_scanner.db, "PostgresDBClient", lambda: object())
        queued: list[Path] = []

        class FakeQueue:
            def enqueue(self, path):
                queued.append(path)

        monkeypatch.setattr(
            local_file_scanner,
            "_MetadataWorkQueue",
            lambda _db_client: FakeQueue(),
        )

        with pytest.raises(StopAfterChange):
            local_file_scanner._run_scanner(tmp_path, bucket_name)

        assert watched_paths == [str(bucket_path)]
        assert queued == []

    def test_startup_reconciliation_queues_burst_paths(self, monkeypatch, tmp_path):
        bucket_name = "local-mock-file-scan-bucket"
        bucket_path = tmp_path / bucket_name
        metadata_paths = [
            _write_metadata(
                bucket_path / f"object-{index}" / "objectMetadata.json",
                f"unscanned/{uuid.uuid4()}/file-{index}.pdf",
            )
            for index in range(4)
        ]

        class StopAfterStartup(Exception):
            pass

        def fake_watch(*_args, **_kwargs):
            raise StopAfterStartup
            yield  # pragma: no cover

        monkeypatch.setitem(
            __import__("sys").modules,
            "watchfiles",
            type(
                "FakeWatchfiles",
                (),
                {
                    "Change": type("Change", (), {"deleted": "deleted"}),
                    "watch": staticmethod(fake_watch),
                },
            ),
        )
        monkeypatch.setattr(local_file_scanner.db, "PostgresDBClient", lambda: object())
        queued: list[Path] = []

        class FakeQueue:
            def enqueue(self, path):
                queued.append(path)

        monkeypatch.setattr(
            local_file_scanner,
            "_MetadataWorkQueue",
            lambda _db_client: FakeQueue(),
        )

        with pytest.raises(StopAfterStartup):
            local_file_scanner._run_scanner(tmp_path, bucket_name)

        assert set(queued) == set(metadata_paths)

    def test_periodic_reconciliation_retries_failed_worker(self, monkeypatch, tmp_path):
        bucket_name = "local-mock-file-scan-bucket"
        metadata_path = _write_metadata(
            tmp_path / bucket_name / "object" / "objectMetadata.json",
            f"unscanned/{uuid.uuid4()}/retry.pdf",
        )

        class StopAfterTimeout(Exception):
            pass

        def fake_watch(*_args, **_kwargs):
            yield set()
            raise StopAfterTimeout

        monkeypatch.setitem(
            __import__("sys").modules,
            "watchfiles",
            type(
                "FakeWatchfiles",
                (),
                {
                    "Change": type("Change", (), {"deleted": "deleted"}),
                    "watch": staticmethod(fake_watch),
                },
            ),
        )
        monkeypatch.setattr(local_file_scanner.db, "PostgresDBClient", lambda: object())

        process_calls: list[str] = []

        def fake_process(path, _db_client):
            process_calls.append(path)
            if len(process_calls) == 1:
                raise RuntimeError("transient")

        monkeypatch.setattr(local_file_scanner, "_safe_process_metadata_change", fake_process)

        class SynchronousThread:
            def __init__(self, **kwargs):
                self.target = kwargs["target"]
                self.args = kwargs["args"]

            def start(self):
                try:
                    self.target(*self.args)
                except RuntimeError:
                    pass

        monkeypatch.setattr(local_file_scanner.threading, "Thread", SynchronousThread)

        with pytest.raises(StopAfterTimeout):
            local_file_scanner._run_scanner(tmp_path, bucket_name)

        assert process_calls == [str(metadata_path), str(metadata_path)]


class TestMetadataWorkQueue:
    def test_deduplicates_in_flight_path_but_allows_concurrent_paths(self, monkeypatch, tmp_path):
        started: list[tuple[object, tuple[object, ...]]] = []

        class FakeThread:
            def __init__(self, **kwargs):
                self.target = kwargs["target"]
                self.args = kwargs["args"]

            def start(self):
                started.append((self.target, self.args))

        monkeypatch.setattr(local_file_scanner.threading, "Thread", FakeThread)
        queue = local_file_scanner._MetadataWorkQueue(object())
        first_path = tmp_path / "first" / "objectMetadata.json"
        second_path = tmp_path / "second" / "objectMetadata.json"

        queue.enqueue(first_path)
        queue.enqueue(first_path)
        queue.enqueue(second_path)

        assert len(started) == 2
        assert {args for _, args in started} == {(str(first_path),), (str(second_path),)}

    def test_failed_worker_path_can_be_retried(self, monkeypatch, tmp_path):
        started: list[tuple[object, tuple[object, ...]]] = []

        class FakeThread:
            def __init__(self, **kwargs):
                self.target = kwargs["target"]
                self.args = kwargs["args"]

            def start(self):
                started.append((self.target, self.args))

        monkeypatch.setattr(local_file_scanner.threading, "Thread", FakeThread)
        monkeypatch.setattr(
            local_file_scanner,
            "_safe_process_metadata_change",
            lambda *_args: (_ for _ in ()).throw(RuntimeError("transient")),
        )
        queue = local_file_scanner._MetadataWorkQueue(object())
        metadata_path = tmp_path / "object" / "objectMetadata.json"

        queue.enqueue(metadata_path)
        target, args = started[0]
        with pytest.raises(RuntimeError, match="transient"):
            target(*args)
        queue.enqueue(metadata_path)

        assert len(started) == 2
