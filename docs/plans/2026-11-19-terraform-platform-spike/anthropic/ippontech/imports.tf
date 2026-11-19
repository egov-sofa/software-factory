# Import blocks only: `terraform plan -generate-config-out=generated.tf` writes the matching resources.

import {
  to = anthropic_service_account.shared
  id = var.service_account_id
}

import {
  to = anthropic_federation_rule.factory_review
  id = var.factory_review_rule_id
}

import {
  to = anthropic_federation_rule.skills_review
  id = var.skills_review_rule_id
}

import {
  to = anthropic_federation_rule.skills_mention
  id = var.skills_mention_rule_id
}

import {
  to = anthropic_federation_rule.skills_evals
  id = var.skills_evals_rule_id
}
