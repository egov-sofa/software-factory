# Spike, GitHub side: can Terraform take over what is set by hand today, with no change?
# Read-only: run `terraform plan` only, never `apply` (docs/plans/2026-11-19-terraform-platform.md).
# Token: GITHUB_TOKEN in the environment (for the spike, `gh auth token`; in CI a GitHub App token, never a PAT).

terraform {
  required_version = ">= 1.7"
  required_providers {
    github = {
      source  = "integrations/github"
      version = "6.13.0"
    }
  }
}

# One provider configuration per organization: the GitHub provider acts on one owner at a time.
provider "github" {
  alias = "egov_sofa"
  owner = "egov-sofa"
}

provider "github" {
  alias = "egov_ai"
  owner = "egov-ai"
}

provider "github" {
  alias = "egov_legacy"
  owner = "egov-legacy"
}
