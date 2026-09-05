import json
from pathlib import Path


TEMPLATE = Path("infra/aws/closeloop-dynamodb.json")


def test_cloudformation_defines_only_the_required_dynamodb_table():
    template = json.loads(TEMPLATE.read_text())
    resources = template["Resources"]
    assert set(resources) == {"ResolutionTable"}
    table = resources["ResolutionTable"]
    assert table["Type"] == "AWS::DynamoDB::Table"
    assert table["DeletionPolicy"] == "Delete"
    assert table["Properties"]["BillingMode"] == "PAY_PER_REQUEST"
    assert table["Properties"]["SSESpecification"] == {"SSEEnabled": True}
    assert table["Properties"]["KeySchema"] == [
        {"AttributeName": "owner_id", "KeyType": "HASH"},
        {"AttributeName": "resolution_id", "KeyType": "RANGE"},
    ]
    assert "GlobalSecondaryIndexes" not in table["Properties"]
    assert "StreamSpecification" not in table["Properties"]
