import os
import tempfile
os.environ.setdefault("DATABASE_URL","sqlite:///"+tempfile.mktemp(prefix="fraudshield-test-",suffix=".db"))
import pytest
@pytest.fixture(autouse=True)
def reset_rate_limiter():
    from app.main import limits
    limits.clear()
