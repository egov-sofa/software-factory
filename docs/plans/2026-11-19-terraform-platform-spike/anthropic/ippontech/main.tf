# Spike, Anthropic side, provider ippontech/anthropic 1.91.2: can Terraform take over the federation objects made
# by hand or by claude_federation.py, with no change? Read-only: `terraform plan` only, never `apply`.
# Token: an org:admin OAuth token in ANTHROPIC_AUTH_TOKEN (run.sh reads it from `ant`); IDs in terraform.tfvars (git-ignored).
# Workspaces are not imported: this provider sends the org:admin token only to the service account and federation
# endpoints, and needs a long-lived Admin API key (admin_api_key) for workspaces (its issue #524). See the plan.

terraform {
  required_version = ">= 1.7"
  required_providers {
    anthropic = {
      source  = "ippontech/anthropic"
      version = "1.91.2"
    }
  }
}

provider "anthropic" {}

variable "service_account_id" {
  type        = string
  description = "The shared service account (svac_...)"
}

variable "factory_review_rule_id" {
  type        = string
  description = "software-factory's review rule (fdrl_...)"
}

variable "skills_review_rule_id" {
  type        = string
  description = "claude-skills' review rule (fdrl_...)"
}

variable "skills_mention_rule_id" {
  type        = string
  description = "claude-skills' mention rule (fdrl_...)"
}

variable "skills_evals_rule_id" {
  type        = string
  description = "claude-skills' evals rule (fdrl_...)"
}
