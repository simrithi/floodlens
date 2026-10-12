"""Load the Lambda handlers without AWS: boto3 is replaced by an in-memory fake, and each handler.py
(they all share that file name) is imported under a unique module name."""

import importlib.util
import io
import os
import sys
import types
from pathlib import Path

import pytest

LAMBDAS = Path(__file__).resolve().parent.parent / "lambdas"

os.environ.setdefault("OUTPUTS_BUCKET", "outputs-test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:000000000000:test")


class NoSuchKey(Exception):
    pass


class FakeS3:
    """Just enough of the S3 client: get_object, put_object, and the NoSuchKey exception."""

    exceptions = types.SimpleNamespace(NoSuchKey=NoSuchKey)

    def __init__(self):
        self.store: dict[tuple[str, str], bytes] = {}

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.store:
            raise NoSuchKey(Key)
        return {"Body": io.BytesIO(self.store[(Bucket, Key)])}

    def put_object(self, Bucket, Key, Body, **_):
        self.store[(Bucket, Key)] = Body.encode() if isinstance(Body, str) else Body


def _install_fake_boto3() -> None:
    fake = types.ModuleType("boto3")
    fake.client = lambda *a, **k: FakeS3()
    fake.resource = lambda *a, **k: types.SimpleNamespace(Table=lambda name: None)
    sys.modules["boto3"] = fake


def _install_fake_requests_if_missing() -> None:
    """The forecast Lambda imports `requests`, which ships inside its deployment zip but is not a
    test dependency. Tests never make a network call, so a stand-in is enough."""
    try:
        import requests  # noqa: F401
    except ImportError:
        fake = types.ModuleType("requests")
        fake.RequestException = Exception
        fake.get = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network calls are not allowed in tests"))
        sys.modules["requests"] = fake


_install_fake_boto3()
_install_fake_requests_if_missing()


def load_handler(folder: str):
    spec = importlib.util.spec_from_file_location(f"lambda_{folder.replace('-', '_')}", LAMBDAS / folder / "handler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def s3():
    return FakeS3()
