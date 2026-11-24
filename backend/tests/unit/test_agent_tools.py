import json

import app.tools  # noqa: F401
from app.agent.tools import inline_schema
from app.tools.base import REGISTRY


def test_tool_schemas_are_self_contained_for_the_model():
    for spec in REGISTRY.values():
        schema = inline_schema(spec.input_model.model_json_schema())
        text = json.dumps(schema)
        assert "$ref" not in text and "$defs" not in text
        assert schema.get("additionalProperties") is False  # unknown fields rejected
