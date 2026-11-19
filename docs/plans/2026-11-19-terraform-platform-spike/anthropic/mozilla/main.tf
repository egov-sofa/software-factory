# Spike, Anthropic side, provider mozilla/anthropic 0.1.0: can Terraform take over the federation objects made
# by hand or by claude_federation.py, with no change? Read-only: `terraform plan` only, never `apply`.
# Token: an org:admin OAuth token in ANTHROPIC_OAUTH_TOKEN (run.sh reads it from `ant`); IDs in terraform.tfvars (git-ignored).
# Workspaces are imported too: this provider sends the org:admin token (oauth_token) to every Admin API endpoint.

terraform {
  required_version = ">= 1.7"
  required_providers {
    anthropic = {
      source  = "mozilla/anthropic"
      version = "0.1.0"
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

variable "factory_workspace_id" {
  type        = string
  description = "software-factory's workspace (wrkspc_...)"
}

variable "skills_workspace_id" {
  type        = string
  description = "claude-skills' workspace (wrkspc_...)"
}
