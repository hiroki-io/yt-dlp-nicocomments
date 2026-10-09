import http.cookiejar
import io

import pytest
from conftest import FakeDownloader
from yt_dlp.networking import Response
from yt_dlp.networking.exceptions import HTTPError

from yt_dlp_plugins.postprocessor._nicocomments.api import (
    CommentAPIError,
    fetch_comments,
    fetch_watch_data,
)


def http_error(status):
    return HTTPError(
        Response(io.BytesIO(), "https://www.nicovideo.jp/", {}, status=status, reason=http.HTTPStatus(status).phrase)
    )


def logged_in(ydl):
    ydl.cookiejar.set_cookie(
        http.cookiejar.Cookie(
            0,
            "user_session",
            "session",
            None,
            False,
            ".nicovideo.jp",
            True,
            True,
            "/",
            False,
            False,
            None,
            False,
            None,
            None,
            {},
        )
    )
    return ydl


def watch_api():
    return {
        "meta": {"status": 200},
        "data": {
            "comment": {
                "nvComment": {"server": "https://nv-comment.nicovideo.jp", "params": {}, "threadKey": "key"},
                "layers": [
                    {
                        "index": 0,
                        "isTranslucent": False,
                        "threadIds": [{"id": 1, "fork": 1, "forkLabel": "owner"}],
                    },
                    {
                        "index": 1,
                        "isTranslucent": False,
                        "threadIds": [
                            {"id": 2, "fork": 0, "forkLabel": "main"},
                            {"id": 2, "fork": 2, "forkLabel": "easy"},
                        ],
                    },
                ],
            }
        },
    }


def thread(thread_id, fork, *nos):
    return {
        "id": thread_id,
        "fork": fork,
        "comments": [{"no": no, "vposMs": 1000, "body": "a", "commands": []} for no in nos],
    }


def test_comments_are_built_from_the_watch_data_and_threads():
    threads = {"data": {"threads": [thread("1", "owner", 1), thread("2", "main", 2)]}}
    comments = fetch_comments(FakeDownloader([watch_api(), threads]), "sm9")
    assert [[chat.no for chat in layer.chats] for layer in comments.layers] == [[1], [2]]


def test_threads_are_requested_with_the_nv_comment_params_and_headers():
    ydl = FakeDownloader([watch_api(), {"data": {"threads": []}}])
    fetch_comments(ydl, "sm9")
    request = ydl.requests[1]
    assert request.url == "https://nv-comment.nicovideo.jp/v1/threads"
    assert request.data == b'{"additionals": {}, "params": {}, "threadKey": "key"}'
    assert request.headers["X-Frontend-Id"] == "6"


def test_watch_data_is_requested_from_the_guest_api_without_a_session():
    ydl = FakeDownloader([watch_api()])
    assert "comment" in fetch_watch_data(ydl, "sm9")
    assert "/api/watch/v3_guest/sm9?" in ydl.requests[0].url


def test_watch_data_is_requested_from_the_user_api_with_a_session():
    ydl = logged_in(FakeDownloader([watch_api()]))
    assert "comment" in fetch_watch_data(ydl, "sm9")
    assert "/api/watch/v3/sm9?" in ydl.requests[0].url


def test_watch_data_falls_back_to_the_guest_api_when_the_user_api_fails():
    ydl = logged_in(FakeDownloader([http_error(400), watch_api()]))
    assert "comment" in fetch_watch_data(ydl, "sm9")
    assert "/api/watch/v3/sm9?" in ydl.requests[0].url
    assert "/api/watch/v3_guest/sm9?" in ydl.requests[1].url
    assert ydl.warnings == [
        "Loading the watch API as a guest because the logged-in request failed: HTTP Error 400: Bad Request"
    ]


def test_watch_data_is_requested_through_the_geo_verification_proxy():
    ydl = FakeDownloader([watch_api()], {"geo_verification_proxy": "http://proxy.example"})
    fetch_watch_data(ydl, "sm9")
    assert ydl.requests[0].headers["Ytdl-request-proxy"] == "http://proxy.example"


def test_watch_data_is_requested_without_a_proxy_header_by_default():
    ydl = FakeDownloader([watch_api()])
    fetch_watch_data(ydl, "sm9")
    assert "Ytdl-request-proxy" not in ydl.requests[0].headers


@pytest.mark.parametrize(("args", "language"), [((), "ja-jp"), (("en",), "en-us"), (("zh",), "zh-tw")])
def test_watch_data_is_requested_in_the_comment_language(args, language):
    ydl = FakeDownloader([watch_api()])
    fetch_watch_data(ydl, "sm9", *args)
    assert ydl.requests[0].url.endswith(f"&i18nLanguage={language}")


def test_watch_data_error_message_contains_the_status():
    ydl = FakeDownloader([{"meta": {"status": 404}}])
    with pytest.raises(CommentAPIError, match=r"^failed to load the watch API: status 404$"):
        fetch_watch_data(ydl, "sm9")


def test_watch_data_error_message_contains_the_http_error():
    ydl = logged_in(FakeDownloader([http_error(400), http_error(404)]))
    with pytest.raises(CommentAPIError, match=r"^failed to load the watch API: HTTP Error 404: Not Found$") as e:
        fetch_watch_data(ydl, "sm9")
    assert isinstance(e.value.__cause__, HTTPError)


def test_unexpected_response_raises_comment_api_error():
    with pytest.raises(CommentAPIError, match="unexpected response"):
        fetch_comments(FakeDownloader([{"meta": {"status": 200}, "data": {}}]), "sm9")
