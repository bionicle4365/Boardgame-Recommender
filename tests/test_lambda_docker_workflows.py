from pathlib import Path

WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / ".github" / "workflows"


def _lambda_docker_workflows():
    """Return workflow files that push Docker images and update AWS Lambda functions."""
    matched = []
    for path in sorted(WORKFLOWS_DIR.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        if "aws lambda update-function-code" in text and "--image-uri" in text:
            matched.append((path, text))
    return matched


def test_lambda_docker_workflows_exist():
    workflows = _lambda_docker_workflows()
    names = {path.name for path, _ in workflows}
    assert "recommender-docker-image.yml" in names
    assert "compactor-docker-image.yml" in names
    assert "data-scraper-docker-image.yml" in names
    assert "taste-analytics-docker-image.yml" in names
    assert "user-scraper-docker-image.yml" in names


def test_lambda_docker_workflows_disable_attestations_and_oci_mediatypes():
    """Ensure Lambda Docker builds emit single-arch Docker v2 manifests rather than OCI index lists."""
    for path, text in _lambda_docker_workflows():
        assert "docker/setup-buildx-action@" in text, f"{path.name} must set up Docker Buildx"
        assert "--platform linux/amd64" in text, f"{path.name} must target linux/amd64"
        assert "--provenance=false" in text, f"{path.name} must disable provenance attestations"
        assert "--sbom=false" in text, f"{path.name} must disable SBOM attestations"
        assert "oci-mediatypes=false" in text, f"{path.name} must disable OCI media types for AWS Lambda"
