import http.cookiejar
import io
import json
from datetime import datetime, timezone

import pytest
from conftest import FakeDownloader, logged_in
from yt_dlp.networking import Response
from yt_dlp.networking.exceptions import HTTPError

from yt_dlp_plugins.postprocessor._nicocomments.api import (
    CommentAPIError,
    RawComments,
    fetch_comments,
    fetch_past_threads,
    fetch_watch_data,
)


def http_error(status, body=None):
    data = json.dumps(body).encode() if body is not None else b""
    return HTTPError(
        Response(
            io.BytesIO(data), "https://www.nicovideo.jp/", {}, status=status, reason=http.HTTPStatus(status).phrase
        )
    )


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
    comments, raw = fetch_comments(FakeDownloader([watch_api(), threads]), "sm9")
    assert raw.threads == threads["data"]["threads"]
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


def raw_comment(comment_id, no, posted_at):
    return {"id": comment_id, "no": no, "vposMs": 0, "body": "a", "commands": [], "postedAt": posted_at}


def threads_response(*comments, fork="main"):
    return {"data": {"threads": [{"id": "2", "fork": fork, "comments": list(comments)}]}}


def comment_data(thread_key="key"):
    return {"nvComment": {"server": "https://nv-comment.nicovideo.jp", "params": {}, "threadKey": thread_key}}


def past_threads(ydl, min_comments, threads=(), warnings=None, messages=None):
    return fetch_past_threads(
        ydl,
        "sm9",
        "ja",
        comment_data(),
        list(threads),
        min_comments,
        1000,
        (messages if messages is not None else []).append,
        (warnings if warnings is not None else []).append,
    )


def requested_whens(ydl):
    return [json.loads(request.data)["additionals"].get("when") for request in ydl.requests if request.data]


def test_past_pages_go_back_from_the_oldest_comment_of_each_page():
    ydl = FakeDownloader(
        [
            threads_response(
                raw_comment("c", 3, "1970-01-01T00:13:20+00:00"), raw_comment("b", 2, "1970-01-01T00:13:00+00:00")
            ),
            threads_response(raw_comment("a", 1, "1970-01-01T00:10:00+00:00")),
        ]
    )
    latest = [{"id": "2", "fork": "main", "comments": [raw_comment("c", 3, "1970-01-01T00:13:20+00:00")]}]
    messages = []
    threads = past_threads(ydl, 3, latest, messages=messages)
    assert requested_whens(ydl) == [1000, 780]
    assert [[raw["no"] for raw in thread["comments"]] for thread in threads] == [[1, 2, 3]]
    assert latest[0]["comments"] == [raw_comment("c", 3, "1970-01-01T00:13:20+00:00")]
    assert messages[-1] == "Loaded past comments before 1970-01-01T00:13:00+00:00 (page 2, 3/3 comments)"


def test_past_pages_stop_at_the_page_that_reaches_the_minimum():
    ydl = FakeDownloader(
        [
            threads_response(
                raw_comment("b", 2, "1970-01-01T00:13:00+00:00"), raw_comment("a", 1, "1970-01-01T00:10:00+00:00")
            )
        ]
    )
    messages = []
    threads = past_threads(ydl, 1, messages=messages)
    assert requested_whens(ydl) == [1000]
    assert [raw["no"] for raw in threads[0]["comments"]] == [1, 2]
    assert messages[-1] == "Loaded past comments before 1970-01-01T00:16:40+00:00 (page 1, 2/1 comments)"


def test_past_pages_are_not_loaded_when_the_latest_comments_reach_the_minimum():
    ydl = FakeDownloader()
    latest = [{"id": "2", "fork": "main", "comments": [raw_comment("a", 1, "1970-01-01T00:10:00+00:00")]}]
    assert past_threads(ydl, 1, latest) == latest
    assert ydl.requests == []


def test_past_page_without_new_comments_goes_back_one_more_second():
    page = threads_response(raw_comment("a", 1, "1970-01-01T00:10:00+00:00"))
    ydl = FakeDownloader([page, page, threads_response()])
    past_threads(ydl, None)
    assert requested_whens(ydl) == [1000, 600, 599]


def test_next_past_page_starts_at_the_thread_that_goes_back_the_least():
    page = {
        "data": {
            "threads": [
                {"id": "2", "fork": "main", "comments": [raw_comment("m", 2, "1970-01-01T00:15:00+00:00")]},
                {"id": "2", "fork": "easy", "comments": [raw_comment("e", 1, "1970-01-01T00:01:40+00:00")]},
            ]
        }
    }
    ydl = FakeDownloader([page, threads_response()])
    past_threads(ydl, None)
    assert requested_whens(ydl) == [1000, 900]


def test_owner_comments_after_when_do_not_hold_back_the_next_past_page():
    def page(*main_comments):
        owner = {"id": "2", "fork": "owner", "comments": [raw_comment("o", 1, "1970-01-01T00:15:00+00:00")]}
        return {"data": {"threads": [owner, {"id": "2", "fork": "main", "comments": list(main_comments)}]}}

    ydl = FakeDownloader(
        [
            page(raw_comment("c", 4, "1970-01-01T00:13:20+00:00")),
            page(raw_comment("b", 3, "1970-01-01T00:11:40+00:00")),
            page(raw_comment("a", 2, "1970-01-01T00:10:00+00:00")),
            page(),
        ]
    )
    threads = past_threads(ydl, None)
    assert requested_whens(ydl) == [1000, 900, 899, 600]
    assert [[raw["no"] for raw in thread["comments"]] for thread in threads] == [[1], [2, 3, 4]]


def test_past_pages_are_not_loaded_when_the_latest_comments_have_all_comments():
    ydl = FakeDownloader()
    latest = [
        {"id": "2", "fork": "main", "commentCount": 1, "comments": [raw_comment("a", 1, "1970-01-01T00:10:00+00:00")]}
    ]
    messages = []
    assert past_threads(ydl, None, latest, messages=messages) == latest
    assert ydl.requests == []
    assert messages == ["Loaded all comments"]


def test_past_pages_stop_when_each_thread_has_its_comment_count():
    page = {
        "data": {
            "threads": [
                {
                    "id": "2",
                    "fork": "main",
                    "commentCount": 2,
                    "comments": [raw_comment("a", 1, "1970-01-01T00:10:00+00:00")],
                }
            ]
        }
    }
    latest = [
        {"id": "2", "fork": "main", "commentCount": 2, "comments": [raw_comment("b", 2, "1970-01-01T00:15:00+00:00")]}
    ]
    ydl = FakeDownloader([page])
    threads = past_threads(ydl, None, latest)
    assert requested_whens(ydl) == [1000]
    assert [raw["no"] for raw in threads[0]["comments"]] == [1, 2]


def test_past_pages_continue_while_a_thread_has_fewer_comments_than_its_count():
    latest = [
        {"id": "2", "fork": "main", "commentCount": 0, "comments": []},
        {"id": "2", "fork": "easy", "commentCount": 3, "comments": [raw_comment("a", 1, "1970-01-01T00:10:00+00:00")]},
    ]
    ydl = FakeDownloader([threads_response()])
    past_threads(ydl, None, latest)
    assert requested_whens(ydl) == [1000]


def test_latest_comments_without_no_are_kept_with_past_pages():
    latest_raw = raw_comment("b", 2, "1970-01-01T00:15:00+00:00")
    del latest_raw["no"]
    latest = [{"id": "2", "fork": "main", "comments": [latest_raw]}]
    ydl = FakeDownloader([threads_response(raw_comment("a", 1, "1970-01-01T00:10:00+00:00")), threads_response()])
    threads = past_threads(ydl, None, latest)
    assert [raw["id"] for raw in threads[0]["comments"]] == ["b", "a"]


def test_past_threads_of_other_forks_are_added():
    ydl = FakeDownloader([threads_response(raw_comment("a", 1, "1970-01-01T00:10:00+00:00"), fork="easy")])
    latest = [{"id": "2", "fork": "main", "comments": []}]
    assert [thread["fork"] for thread in past_threads(ydl, 1, latest)] == ["main", "easy"]


def test_past_pages_wait_for_the_rate_limit(sleeps):
    ydl = FakeDownloader(
        [
            threads_response(raw_comment("c", 3, "1970-01-01T00:13:20+00:00")),
            threads_response(raw_comment("b", 2, "1970-01-01T00:10:00+00:00")),
            threads_response(raw_comment("a", 1, "1970-01-01T00:05:00+00:00")),
        ]
    )
    past_threads(ydl, 3)
    assert sleeps == [1, 1, 1]


def test_expired_thread_key_is_renewed_from_the_watch_api():
    watch = watch_api()
    watch["data"]["comment"]["nvComment"]["threadKey"] = "new key"
    ydl = logged_in(
        FakeDownloader(
            [http_error(400, {"meta": {"errorCode": "EXPIRED_TOKEN"}}), watch, threads_response(), threads_response()]
        )
    )
    past_threads(ydl, None)
    assert [json.loads(ydl.requests[i].data)["threadKey"] for i in (0, 2)] == ["key", "new key"]
    assert "/api/watch/v3/sm9?" in ydl.requests[1].url


def test_past_pages_without_a_login_are_stopped_with_a_warning():
    rejected = http_error(400, {"meta": {"status": 400, "errorCode": "INVALID_TOKEN"}})
    ydl = FakeDownloader([rejected, watch_api(), rejected])
    latest = [{"id": "2", "fork": "main", "comments": [raw_comment("a", 1, "1970-01-01T00:10:00+00:00")]}]
    warnings = []
    threads = past_threads(ydl, None, latest, warnings=warnings)
    assert warnings == [
        "Stopped loading past comments: the comment API needs a login for past comments. "
        "Use --cookies-from-browser or --cookies"
    ]
    assert threads == latest


def test_loaded_comments_are_kept_after_an_error_in_the_past_pages():
    ydl = FakeDownloader([threads_response(raw_comment("a", 1, "1970-01-01T00:10:00+00:00")), http_error(503)])
    warnings = []
    threads = past_threads(ydl, None, warnings=warnings)
    assert warnings == ["Stopped loading past comments: HTTP Error 503: Service Unavailable"]
    assert [raw["no"] for raw in threads[0]["comments"]] == [1]


def test_comments_of_an_unexpected_past_page_are_not_added():
    broken = {"id": "c", "no": 3, "vposMs": 0, "body": "a", "commands": []}
    ydl = FakeDownloader(
        [
            threads_response(raw_comment("b", 2, "1970-01-01T00:13:20+00:00")),
            threads_response(raw_comment("a", 1, "1970-01-01T00:10:00+00:00"), broken),
        ]
    )
    warnings = []
    threads = past_threads(ydl, None, warnings=warnings)
    assert warnings == ["Stopped loading past comments: unexpected response from the comment API: KeyError('postedAt')"]
    assert [raw["no"] for raw in threads[0]["comments"]] == [2]


def test_unexpected_watch_data_in_the_past_pages_keeps_the_loaded_comments():
    ydl = logged_in(FakeDownloader([http_error(400), {"meta": {"status": 200}, "data": {}}]))
    latest = [{"id": "2", "fork": "main", "comments": [raw_comment("a", 1, "1970-01-01T00:10:00+00:00")]}]
    warnings = []
    assert past_threads(ydl, None, latest, warnings=warnings) == latest
    assert warnings == ["Stopped loading past comments: unexpected response from the comment API: KeyError('comment')"]


def test_past_pages_are_added_to_the_layers_and_the_raw_comments():
    page = threads_response(raw_comment("a", 1, "1970-01-01T00:10:00+00:00"))
    ydl = FakeDownloader([watch_api(), threads_response(), page])
    comments, raw = fetch_comments(ydl, "sm9", min_comments=1)
    assert [[chat.no for chat in layer.chats] for layer in comments.layers] == [[], [1]]
    assert raw.threads == page["data"]["threads"]


def test_raw_json_drops_the_values_of_the_viewer():
    comment = {
        "keys": {"userKey": "secret"},
        "nvComment": {"server": "s", "params": {}, "threadKey": "secret"},
        "ng": {"owner": [], "viewer": {"count": 1, "items": [{"type": "word", "source": "a"}]}},
        "threads": [{"id": 2, "forkLabel": "main", "threadkey": "secret"}],
    }
    threads = [{"id": "2", "fork": "main", "comments": [{"id": "a", "no": 1, "isMyPost": True, "nicoruId": "n"}]}]
    raw = RawComments(comment, threads, datetime(2026, 10, 9, tzinfo=timezone.utc))
    assert json.loads(raw.to_json("sm9", "ja")) == {
        "videoId": "sm9",
        "language": "ja",
        "fetchedAt": "2026-10-09T00:00:00+00:00",
        "comment": {
            "nvComment": {"server": "s", "params": {}},
            "ng": {"owner": []},
            "threads": [{"id": 2, "forkLabel": "main"}],
        },
        "threads": [{"id": "2", "fork": "main", "comments": [{"id": "a", "no": 1}]}],
    }
    assert "threadKey" in comment["nvComment"]
    assert "viewer" in comment["ng"]
    assert "threadkey" in comment["threads"][0]
    assert "isMyPost" in threads[0]["comments"][0]
