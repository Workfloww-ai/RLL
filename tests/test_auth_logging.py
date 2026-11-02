import pytest
import uuid
from backend.services.activity_log_service import auth_log_service

TEST_USER_ID = "00000000-0000-0000-0000-000000000099"
TEST_EMAIL = "test_audit_user@rll.com"

def test_detect_phone_type_heuristics():
    # 1. Explicit priority
    assert auth_log_service.detect_phone_type(None, None, "ios") == "ios"
    assert auth_log_service.detect_phone_type(None, None, "android") == "android"
    assert auth_log_service.detect_phone_type(None, None, "web") == "web"

    # 2. User-Agent iOS detection
    ua_ios = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15"
    assert auth_log_service.detect_phone_type(None, ua_ios) == "ios"

    ua_cfnetwork = "CFNetwork/1494.0.7 Darwin/23.4.0"
    assert auth_log_service.detect_phone_type(None, ua_cfnetwork) == "ios"

    # 3. User-Agent Android detection
    ua_android = "okhttp/4.12.0 (Linux; U; Android 14; SM-S918B)"
    assert auth_log_service.detect_phone_type(None, ua_android) == "android"

    # 4. User-Agent Web detection
    ua_web = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    assert auth_log_service.detect_phone_type(None, ua_web) == "web"

    # 5. Header based detection
    class MockRequest:
        headers = {"x-device-platform": "android"}
    assert auth_log_service.detect_phone_type(MockRequest()) == "android"

def test_auth_log_service_record_login_sync():
    ok = auth_log_service.record_login_sync(
        user_id=TEST_USER_ID,
        email=TEST_EMAIL,
        phone_type="ios",
        ip_address="127.0.0.1",
        user_agent="PyTest/AuthRunner",
        action="LOGIN",
        status="SUCCESS",
    )
    assert isinstance(ok, bool)

