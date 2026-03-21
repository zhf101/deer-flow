from deerflow.nlp2sql.schema.enhancer import normalize_search_text, tokenize_search_text


def test_normalize_search_text_compacts_whitespace_and_underscores():
    assert normalize_search_text("  Order_Status   Value ") == "order status value"


def test_tokenize_search_text_handles_empty_input():
    assert tokenize_search_text(None) == []
    assert tokenize_search_text("  order   status ") == ["order", "status"]
