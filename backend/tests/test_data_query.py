from unittest.mock import MagicMock, patch


def test_query_csv_data():
    csv_data = "name,age\nAlice,30\nBob,25\nCharlie,35"
    question = "What is the average age?"

    mock_provider = MagicMock()
    mock_provider.stream_deltas.return_value = iter(["The average age is 30.0"])
    with patch("ai_portal.tools.data.query.get_chat_provider", return_value=mock_provider):
        from ai_portal.tools.data.query import query_structured_data
        result = query_structured_data(csv_data, question)

    assert "30" in result
    # Verify LLM was called with data context
    call_messages = mock_provider.stream_deltas.call_args[0][0]
    system_msg = call_messages[0]["content"]
    assert "name" in system_msg
    assert "age" in system_msg
    assert question in call_messages[1]["content"]


def test_query_json_data():
    json_data = '[{"product": "A", "sales": 100}, {"product": "B", "sales": 200}]'
    question = "Which product has higher sales?"

    mock_provider = MagicMock()
    mock_provider.stream_deltas.return_value = iter(["Product B has higher sales with 200."])
    with patch("ai_portal.tools.data.query.get_chat_provider", return_value=mock_provider):
        from ai_portal.tools.data.query import query_structured_data
        result = query_structured_data(json_data, question)

    assert "B" in result


def test_query_unparseable_data():
    from ai_portal.tools.data.query import query_structured_data
    result = query_structured_data("this is not csv or json !!!###", "what?")
    assert "Could not parse" in result


def test_query_returns_error_on_llm_failure():
    csv_data = "x,y\n1,2\n3,4"
    mock_provider = MagicMock()
    mock_provider.stream_deltas.side_effect = Exception("LLM error")
    with patch("ai_portal.tools.data.query.get_chat_provider", return_value=mock_provider):
        from ai_portal.tools.data.query import query_structured_data
        result = query_structured_data(csv_data, "sum of x?")
    assert "Could not answer" in result
