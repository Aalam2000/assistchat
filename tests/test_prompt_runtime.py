from src.app.core.prompt_runtime import format_examples_block, get_examples


def test_get_examples_ui_format():
    examples = get_examples({
        "prompt": {
            "examples": [
                {"user": "Нужен бот", "assistant": '{"match": true}'},
            ],
        },
    })
    assert examples == [{"q": "Нужен бот", "a": '{"match": true}'}]


def test_get_examples_legacy_format():
    examples = get_examples({
        "prompt": {
            "examples": [
                {"q": "Hello", "a": "Hi"},
            ],
        },
    })
    assert examples == [{"q": "Hello", "a": "Hi"}]


def test_format_examples_block():
    block = format_examples_block([{"q": "Q1", "a": "A1"}])
    assert "EXAMPLES:" in block
    assert "Q: Q1" in block
    assert "A: A1" in block


def test_format_examples_block_empty():
    assert format_examples_block([]) == ""
