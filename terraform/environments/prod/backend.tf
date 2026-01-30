terraform {
  backend "gcs" {
    bucket = "akscicd-tfstate"
    prefix = "prod"
  }
}
