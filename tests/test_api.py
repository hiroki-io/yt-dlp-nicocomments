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
    return HTTPError(Response(io.BytesIO(), "https://www.nicovideo.jp/", {}, status=status, reason="Forbidden"))


def watch_api(ng_score_disabled=False):
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
                "ng": {"ngScore": {"isDisabled": ng_score_disabled}},
            }
        },
    }


def thread(thread_id, fork, *nos):
    return {
        "id": thread_id,
        "fork": fork,
        "comments": [{"no": no, "vposMs": 1000, "body": "a", "commands": []} for no in nos],
    }


def test_threads_are_grouped_into_layers_by_id_and_fork():
    threads = {
        "data": {
            "threads": [
                thread("1", "owner", 1),
                thread("2", "main", 2, 3),
                thread("2", "easy", 4),
                thread("2", "owner", 5),
                thread("3", "main", 6),
            ]
        }
    }
    fetched = fetch_comments(FakeDownloader([watch_api(), threads]), "sm9")
    assert [(layer.index, [chat.no for chat in layer.chats]) for layer in fetched.layers] == [(0, [1]), (1, [2, 3, 4])]
    assert fetched.layers[0].chats[0].is_owner
    assert not fetched.layers[1].chats[0].is_owner
    assert not fetched.ng_score_disabled


def test_ng_score_is_disabled_when_the_watch_api_disables_it():
    threads = {"data": {"threads": []}}
    assert fetch_comments(FakeDownloader([watch_api(ng_score_disabled=True), threads]), "sm9").ng_score_disabled


def test_threads_are_requested_with_the_nv_comment_params_and_headers():
    ydl = FakeDownloader([watch_api(), {"data": {"threads": []}}])
    fetch_comments(ydl, "sm9")
    request = ydl.requests[1]
    assert request.url == "https://nv-comment.nicovideo.jp/v1/threads"
    assert request.data == b'{"additionals": {}, "params": {}, "threadKey": "key"}'
    assert request.headers["X-Frontend-Id"] == "6"


def test_watch_data_falls_back_to_the_guest_api():
    ydl = FakeDownloader([http_error(403), watch_api()])
    assert "comment" in fetch_watch_data(ydl, "sm9")
    assert "/api/watch/v3/sm9?" in ydl.requests[0].url
    assert "/api/watch/v3_guest/sm9?" in ydl.requests[1].url


@pytest.mark.parametrize(("args", "language"), [((), "ja-jp"), (("en",), "en-us"), (("zh",), "zh-tw")])
def test_watch_data_is_requested_in_the_comment_language(args, language):
    ydl = FakeDownloader([watch_api()])
    fetch_watch_data(ydl, "sm9", *args)
    assert ydl.requests[0].url.endswith(f"&i18nLanguage={language}")


def test_watch_data_error_message_contains_the_last_status():
    ydl = FakeDownloader([http_error(403), {"meta": {"status": 404}}])
    with pytest.raises(CommentAPIError, match=r"^failed to load the watch API: status 404$"):
        fetch_watch_data(ydl, "sm9")


def test_watch_data_error_message_contains_the_http_error():
    ydl = FakeDownloader([http_error(403), http_error(403)])
    with pytest.raises(CommentAPIError, match=r"^failed to load the watch API: HTTP Error 403: Forbidden$") as e:
        fetch_watch_data(ydl, "sm9")
    assert isinstance(e.value.__cause__, HTTPError)


def test_unexpected_response_raises_comment_api_error():
    with pytest.raises(CommentAPIError, match="unexpected response"):
        fetch_comments(FakeDownloader([{"meta": {"status": 200}, "data": {}}]), "sm9")


def test_nicoscripts_of_threads_with_nicoscript_apply_to_comments():
    api = watch_api()
    api["data"]["comment"]["threads"] = [{"id": 1, "forkLabel": "owner", "hasNicoscript": True}]
    threads = {
        "data": {
            "threads": [
                {
                    "id": "1",
                    "fork": "owner",
                    "comments": [
                        {"no": 1, "vposMs": 0, "body": "@置換 a b", "commands": ["red"]},
                        {"no": 2, "vposMs": 0, "body": "@逆 投コメ", "commands": []},
                    ],
                },
                {
                    "id": "2",
                    "fork": "main",
                    "comments": [
                        {"no": 3, "vposMs": 1000, "body": "a", "commands": []},
                        {"no": 4, "vposMs": 1000, "body": "@置換 a c", "commands": []},
                    ],
                },
            ]
        }
    }
    fetched = fetch_comments(FakeDownloader([api, threads]), "sm9")
    owner_layer, main_layer = fetched.layers
    assert (main_layer.chats[0].lines, main_layer.chats[0].color) == (["b"], "FF0000")
    assert main_layer.chats[1].lines == ["@置換 b c"]
    assert owner_layer.reverse_ranges == [(0, 30000)]
    assert main_layer.reverse_ranges == []


def test_owner_scripts_are_removed_before_replacement():
    api = watch_api()
    api["data"]["comment"]["threads"] = [{"id": 1, "forkLabel": "owner", "hasNicoscript": True}]
    threads = {
        "data": {
            "threads": [
                {
                    "id": "1",
                    "fork": "owner",
                    "comments": [
                        {"no": 1, "vposMs": 0, "body": "@置換 a @b 全 投コメ", "commands": []},
                        {"no": 2, "vposMs": 0, "body": "a", "commands": []},
                        {"no": 3, "vposMs": 0, "body": "@a", "commands": []},
                    ],
                }
            ]
        }
    }
    (owner_layer, _) = fetch_comments(FakeDownloader([api, threads]), "sm9").layers
    assert [chat.lines for chat in owner_layer.chats] == [["@b"]]


def test_owner_ngs_apply_to_viewer_comments_before_nicoscripts():
    api = watch_api()
    api["data"]["comment"]["threads"] = [{"id": 1, "forkLabel": "owner", "hasNicoscript": True}]
    api["data"]["comment"]["ng"]["owner"] = [{"source": "a", "destination": "b"}]
    threads = {
        "data": {
            "threads": [
                {
                    "id": "1",
                    "fork": "owner",
                    "comments": [
                        {"no": 1, "vposMs": 0, "body": "@置換 b c", "commands": []},
                        {"no": 2, "vposMs": 1000, "body": "a", "commands": []},
                    ],
                },
                {"id": "2", "fork": "main", "comments": [{"no": 3, "vposMs": 1000, "body": "A", "commands": []}]},
            ]
        }
    }
    owner_layer, main_layer = fetch_comments(FakeDownloader([api, threads]), "sm9").layers
    assert owner_layer.chats[0].lines == ["a"]
    assert main_layer.chats[0].lines == ["c"]
