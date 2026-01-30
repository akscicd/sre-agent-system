output "service_accounts" {
  description = "Map of SA names to their emails"
  value       = { for sa in google_service_account.sa : sa.account_id => sa.email }
}
