# terraform/main.tf
terraform {
  required_version = ">= 1.0"
  
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
  
  backend "azurerm" {
    # Configure remote state storage
    resource_group_name  = "<YOUR_TERRAFORM_RG>"
    storage_account_name = "<YOUR_TERRAFORM_SA>"
    container_name       = "tfstate"
    key                  = "rag-application.tfstate"
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
  }
}

# Variables
variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "rag-app"
}

variable "environment" {
  description = "Environment (dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "location" {
  description = "Azure region"
  type        = string
  default     = "eastus"
}

variable "aks_node_count" {
  description = "Initial number of AKS nodes"
  type        = number
  default     = 3
}

variable "aks_node_vm_size" {
  description = "VM size for AKS nodes"
  type        = string
  default     = "Standard_D4s_v3"
}

# Resource Group
resource "azurerm_resource_group" "main" {
  name     = "${var.project_name}-${var.environment}-rg"
  location = var.location
  
  tags = {
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "Terraform"
  }
}

# Virtual Network
resource "azurerm_virtual_network" "main" {
  name                = "${var.project_name}-${var.environment}-vnet"
  address_space       = ["10.0.0.0/16"]
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  
  tags = azurerm_resource_group.main.tags
}

# Subnet for AKS
resource "azurerm_subnet" "aks" {
  name                 = "aks-subnet"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.0.1.0/24"]
}

# Azure Kubernetes Service
resource "azurerm_kubernetes_cluster" "main" {
  name                = "${var.project_name}-${var.environment}-aks"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = "${var.project_name}-${var.environment}"
  
  kubernetes_version = "1.28"
  
  default_node_pool {
    name                = "default"
    node_count          = var.aks_node_count
    vm_size             = var.aks_node_vm_size
    vnet_subnet_id      = azurerm_subnet.aks.id
    enable_auto_scaling = true
    min_count           = 3
    max_count           = 10
    
    upgrade_settings {
      max_surge = "33%"
    }
  }
  
  identity {
    type = "SystemAssigned"
  }
  
  network_profile {
    network_plugin    = "azure"
    network_policy    = "azure"
    load_balancer_sku = "standard"
    service_cidr      = "10.1.0.0/16"
    dns_service_ip    = "10.1.0.10"
  }
  
  azure_active_directory_role_based_access_control {
    managed                = true
    azure_rbac_enabled     = true
  }
  
  oms_agent {
    log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id
  }
  
  tags = azurerm_resource_group.main.tags
}

# Container Registry
resource "azurerm_container_registry" "main" {
  name                = "${var.project_name}${var.environment}acr"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Premium"
  admin_enabled       = false
  
  network_rule_set {
    default_action = "Deny"
    
    virtual_network {
      action    = "Allow"
      subnet_id = azurerm_subnet.aks.id
    }
  }
  
  tags = azurerm_resource_group.main.tags
}

# Grant AKS access to ACR
resource "azurerm_role_assignment" "aks_acr" {
  principal_id                     = azurerm_kubernetes_cluster.main.kubelet_identity[0].object_id
  role_definition_name             = "AcrPull"
  scope                            = azurerm_container_registry.main.id
  skip_service_principal_aad_check = true
}

# Storage Account for PDFs
resource "azurerm_storage_account" "main" {
  name                     = "${var.project_name}${var.environment}sa"
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "GRS"
  
  blob_properties {
    versioning_enabled = true
    
    delete_retention_policy {
      days = 30
    }
  }
  
  network_rules {
    default_action             = "Deny"
    bypass                     = ["AzureServices"]
    virtual_network_subnet_ids = [azurerm_subnet.aks.id]
  }
  
  tags = azurerm_resource_group.main.tags
}

# Blob Container
resource "azurerm_storage_container" "pdfs" {
  name                  = "pdf-documents"
  storage_account_name  = azurerm_storage_account.main.name
  container_access_type = "private"
}

# Azure Cognitive Search
resource "azurerm_search_service" "main" {
  name                = "${var.project_name}-${var.environment}-search"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "standard"
  replica_count       = 3
  partition_count     = 1
  
  public_network_access_enabled = false
  
  tags = azurerm_resource_group.main.tags
}

# Azure OpenAI (if available in your region)
resource "azurerm_cognitive_account" "openai" {
  name                = "${var.project_name}-${var.environment}-openai"
  resource_group_name = azurerm_resource_group.main.name
  location            = "eastus"  # OpenAI availability varies by region
  kind                = "OpenAI"
  sku_name            = "S0"
  
  network_acls {
    default_action = "Deny"
    
    virtual_network_rules {
      subnet_id = azurerm_subnet.aks.id
    }
  }
  
  tags = azurerm_resource_group.main.tags
}

# Key Vault
resource "azurerm_key_vault" "main" {
  name                       = "${var.project_name}-${var.environment}-kv"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "premium"
  soft_delete_retention_days = 90
  purge_protection_enabled   = true
  
  network_acls {
    default_action             = "Deny"
    bypass                     = "AzureServices"
    virtual_network_subnet_ids = [azurerm_subnet.aks.id]
  }
  
  tags = azurerm_resource_group.main.tags
}

# User Managed Identity for AKS pods
resource "azurerm_user_assigned_identity" "aks_pod" {
  name                = "${var.project_name}-${var.environment}-pod-identity"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  
  tags = azurerm_resource_group.main.tags
}

# Grant pod identity access to Storage
resource "azurerm_role_assignment" "pod_storage" {
  principal_id         = azurerm_user_assigned_identity.aks_pod.principal_id
  role_definition_name = "Storage Blob Data Contributor"
  scope                = azurerm_storage_account.main.id
}

# Grant pod identity access to Key Vault
resource "azurerm_key_vault_access_policy" "pod" {
  key_vault_id = azurerm_key_vault.main.id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = azurerm_user_assigned_identity.aks_pod.principal_id
  
  secret_permissions = [
    "Get",
    "List"
  ]
}

# Log Analytics Workspace
resource "azurerm_log_analytics_workspace" "main" {
  name                = "${var.project_name}-${var.environment}-logs"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
  
  tags = azurerm_resource_group.main.tags
}

# Application Insights
resource "azurerm_application_insights" "main" {
  name                = "${var.project_name}-${var.environment}-appinsights"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"
  
  tags = azurerm_resource_group.main.tags
}

# Data source
data "azurerm_client_config" "current" {}

# Outputs
output "aks_cluster_name" {
  value = azurerm_kubernetes_cluster.main.name
}

output "acr_login_server" {
  value = azurerm_container_registry.main.login_server
}

output "storage_account_name" {
  value = azurerm_storage_account.main.name
}

output "search_service_name" {
  value = azurerm_search_service.main.name
}

output "key_vault_name" {
  value = azurerm_key_vault.main.name
}

output "managed_identity_client_id" {
  value = azurerm_user_assigned_identity.aks_pod.client_id
}
