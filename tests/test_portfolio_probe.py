from acta.client import GitHubAPIError
from acta.portfolio.probe import probe


def test_native_probe_uses_node_identity_before_locator():
    class Client:
        def graphql(self, query, variables):
            assert variables == {"id": "PR_1"}
            return {"node": {"id": "PR_1", "title": "Cache", "body": "Same content", "state": "MERGED", "mergedAt": None,
                "closedAt": None, "url": "https://github.com/alice/renamed/pull/1",
                "repository": {"id": "REPO_1", "nameWithOwner": "alice/renamed", "isPrivate": False}}}
    observation, resource = probe({"kind": "pull_request", "source_key": "github:PR_1", "locator": "https://github.com/alice/old/pull/1"}, Client())
    assert observation["outcome"] == "observed"
    assert resource["key"] == "github:PR_1" and resource["project_key"] == "github:REPO_1"
    assert "/renamed/" in resource["locator"]


def test_not_found_and_transient_failure_are_distinct():
    class Client:
        def __init__(self, message): self.message = message
        def graphql(self, query, variables): raise GitHubAPIError(self.message)
    evidence = {"kind": "pull_request", "source_key": "github:PR_1", "locator": "https://github.com/alice/demo/pull/1"}
    assert probe(evidence, Client("HTTP 404"))[0]["outcome"] == "not_resolvable"
    assert probe(evidence, Client("HTTP 503"))[0]["outcome"] == "failed"


def test_secondary_rate_limit_403_is_a_retryable_failure_not_access_loss():
    class Client:
        def graphql(self, query, variables):
            raise GitHubAPIError("secondary rate limit (HTTP 403)")
    observation, _ = probe({"kind": "project", "source_key": "github:REPO_1", "locator": "https://github.com/alice/demo"}, Client())
    assert observation["outcome"] == "failed"
