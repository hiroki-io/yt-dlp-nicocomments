from yt_dlp_plugins.postprocessor._nicocomments.assemble import assemble_comments


def watch_comment(ng=None, script_threads=()):
    return {
        "threads": [{"id": thread_id, "forkLabel": fork, "hasNicoscript": True} for thread_id, fork in script_threads],
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
        "ng": ng or {},
    }


def thread(thread_id, fork, *comments):
    return {"id": thread_id, "fork": fork, "comments": list(comments)}


def comment(no, body="a", vpos_ms=1000, commands=()):
    return {"no": no, "vposMs": vpos_ms, "body": body, "commands": list(commands)}


def test_threads_are_grouped_into_layers_by_id_and_fork():
    threads = [
        thread("1", "owner", comment(1)),
        thread("2", "main", comment(2), comment(3)),
        thread("2", "easy", comment(4)),
        thread("2", "owner", comment(5)),
        thread("3", "main", comment(6)),
    ]
    fetched = assemble_comments(watch_comment(), threads)
    assert [(layer.index, [chat.no for chat in layer.chats]) for layer in fetched.layers] == [(0, [1]), (1, [2, 3, 4])]
    assert fetched.layers[0].chats[0].is_owner
    assert not fetched.layers[1].chats[0].is_owner
    assert not fetched.ng_score_disabled


def test_ng_score_is_disabled_when_the_watch_api_disables_it():
    assert assemble_comments(watch_comment(ng={"ngScore": {"isDisabled": True}}), []).ng_score_disabled


def test_nicoscripts_of_threads_with_nicoscript_apply_to_comments():
    threads = [
        thread(
            "1",
            "owner",
            comment(1, "@置換 a b", vpos_ms=0, commands=["red"]),
            comment(2, "@逆 投コメ", vpos_ms=0),
        ),
        thread("2", "main", comment(3, "a"), comment(4, "@置換 a c")),
    ]
    owner_layer, main_layer = assemble_comments(watch_comment(script_threads=[(1, "owner")]), threads).layers
    assert (main_layer.chats[0].lines, main_layer.chats[0].color) == (["b"], "FF0000")
    assert main_layer.chats[1].lines == ["@置換 b c"]
    assert owner_layer.reverse_ranges == [(0, 30000)]
    assert main_layer.reverse_ranges == []


def test_owner_scripts_are_removed_before_replacement():
    threads = [
        thread(
            "1",
            "owner",
            comment(1, "@置換 a @b 全 投コメ", vpos_ms=0),
            comment(2, "a", vpos_ms=0),
            comment(3, "@a", vpos_ms=0),
        )
    ]
    owner_layer, _ = assemble_comments(watch_comment(script_threads=[(1, "owner")]), threads).layers
    assert [chat.lines for chat in owner_layer.chats] == [["@b"]]


def test_owner_ngs_apply_to_viewer_comments_before_nicoscripts():
    threads = [
        thread("1", "owner", comment(1, "@置換 b c", vpos_ms=0), comment(2, "a")),
        thread("2", "main", comment(3, "A")),
    ]
    ng = {"owner": [{"source": "a", "destination": "b"}]}
    owner_layer, main_layer = assemble_comments(watch_comment(ng=ng, script_threads=[(1, "owner")]), threads).layers
    assert owner_layer.chats[0].lines == ["a"]
    assert main_layer.chats[0].lines == ["c"]
