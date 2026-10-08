#!/usr/bin/env python3

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import http.cookiejar


BASE_URL = os.environ.get("BASE_URL", "http://localhost")


class CloudVoteE2E:

    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()

        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies)
        )

    def request(self, method, path, data=None):

        url = f"{BASE_URL}{path}"

        encoded_data = None

        if data is not None:
            encoded_data = urllib.parse.urlencode(data).encode()

        request = urllib.request.Request(
            url,
            data=encoded_data,
            method=method,
            headers={
                "User-Agent": "CloudVote-E2E-Test/1.0"
            },
        )

        try:
            response = self.opener.open(request, timeout=10)

            body = response.read().decode()

            return response.status, body

        except urllib.error.HTTPError as error:

            body = error.read().decode()

            return error.code, body

    def json_request(self, method, path):

        status, body = self.request(method, path)

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = None

        return status, parsed, body


def assert_equal(actual, expected, message):

    if actual != expected:
        raise AssertionError(
            f"{message}: expected {expected}, got {actual}"
        )


def test_liveness(app):

    status, body, raw = app.json_request(
        "GET",
        "/health/live"
    )

    assert_equal(
        status,
        200,
        "Liveness endpoint"
    )

    assert_equal(
        body["status"],
        "ok",
        "Liveness status"
    )

    print("PASS /health/live")


def test_readiness(app):

    status, body, raw = app.json_request(
        "GET",
        "/health/ready"
    )

    assert_equal(
        status,
        200,
        "Readiness endpoint"
    )

    assert_equal(
        body["status"],
        "ok",
        "Readiness status"
    )

    print("PASS /health/ready")


def test_full_health(app):

    deadline = time.time() + 60

    while time.time() < deadline:

        status, body, raw = app.json_request(
            "GET",
            "/health"
        )

        if (
            status == 200
            and body
            and body.get("status") == "ok"
        ):
            print("PASS /health")
            return

        time.sleep(2)

    raise AssertionError(
        f"/health never became healthy: {raw}"
    )


def test_unauthenticated_admin_api(app):

    status, body, raw = app.json_request(
        "GET",
        "/api/admin/stats"
    )

    assert_equal(
        status,
        401,
        "Admin API authentication"
    )

    assert_equal(
        body["error"],
        "login_required",
        "Admin API error"
    )

    print("PASS unauthenticated admin API")


def test_homepage(app):

    status, body = app.request(
        "GET",
        "/"
    )

    assert_equal(
        status,
        200,
        "Homepage"
    )

    if "CloudVote" not in body:
        raise AssertionError(
            "Homepage does not contain CloudVote"
        )

    print("PASS homepage")


def test_missing_route(app):

    status, body = app.request(
        "GET",
        "/this-route-does-not-exist"
    )

    assert_equal(
        status,
        404,
        "404 handling"
    )

    print("PASS 404 handling")


def main():

    print()
    print("======================================")
    print(" CloudVote End-to-End Test Suite")
    print("======================================")
    print()

    app = CloudVoteE2E()

    tests = [
        test_liveness,
        test_readiness,
        test_full_health,
        test_homepage,
        test_unauthenticated_admin_api,
        test_missing_route,
    ]

    for test in tests:

        try:
            test(app)

        except Exception as error:

            print()
            print(f"FAIL {test.__name__}")
            print(error)
            sys.exit(1)

    print()
    print("======================================")
    print(" ALL E2E TESTS PASSED")
    print("======================================")


if __name__ == "__main__":
    main()
