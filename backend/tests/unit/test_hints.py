from app.services.hints import extract_resources, guess_services, make_title


def test_extracts_explicit_identifiers():
    refs = extract_resources(
        "Why is i-0a1b2c3d4e5f67890 unhealthy and is "
        "arn:aws:lambda:us-east-1:123456789012:function:invoice-renderer erroring?"
    )
    assert [(r.service, r.identifier) for r in refs] == [
        ("ec2", "i-0a1b2c3d4e5f67890"),
        ("lambda", "arn:aws:lambda:us-east-1:123456789012:function:invoice-renderer"),
    ]


def test_named_resources_and_stopwords():
    assert extract_resources("lambda invoice-renderer is timing out")[0].identifier == (
        "invoice-renderer"
    )
    assert extract_resources("my lambda functions are slow") == []


def test_no_identifiers_means_discovery():
    assert extract_resources("why is checkout slow today?") == []


def test_guess_services_and_title():
    assert guess_services("database CPU high on postgres", []) == ["rds"]
    assert make_title("  a\n b  ") == "a b"
    assert len(make_title("x" * 300)) == 120
