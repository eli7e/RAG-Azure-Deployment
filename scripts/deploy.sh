#!/bin/bash
# scripts/deploy.sh
# Complete deployment script for RAG application

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== RAG Application Deployment Script ===${NC}"

# Configuration
PROJECT_NAME="${PROJECT_NAME:-rag-app}"
ENVIRONMENT="${ENVIRONMENT:-prod}"
AZURE_REGION="${AZURE_REGION:-eastus}"

# Step 1: Azure Login
echo -e "\n${YELLOW}Step 1: Azure Authentication${NC}"
az login
az account set --subscription "<YOUR_SUBSCRIPTION_ID>"

# Step 2: Deploy Infrastructure with Terraform
echo -e "\n${YELLOW}Step 2: Deploying Azure Infrastructure${NC}"
cd terraform
terraform init
terraform plan -out=tfplan
terraform apply tfplan

# Get outputs
AKS_NAME=$(terraform output -raw aks_cluster_name)
ACR_NAME=$(terraform output -raw acr_login_server | cut -d'.' -f1)
RG_NAME="${PROJECT_NAME}-${ENVIRONMENT}-rg"

echo -e "${GREEN}✓ Infrastructure deployed${NC}"

# Step 3: Configure kubectl
echo -e "\n${YELLOW}Step 3: Configuring kubectl${NC}"
az aks get-credentials --resource-group $RG_NAME --name $AKS_NAME --overwrite-existing
kubectl config use-context $AKS_NAME

echo -e "${GREEN}✓ kubectl configured${NC}"

# Step 4: Build and Push Docker Image
echo -e "\n${YELLOW}Step 4: Building and Pushing Docker Image${NC}"
cd ..
az acr login --name $ACR_NAME

docker build -t ${ACR_NAME}.azurecr.io/rag-application:latest -f Dockerfile .
docker push ${ACR_NAME}.azurecr.io/rag-application:latest

echo -e "${GREEN}✓ Docker image pushed to ACR${NC}"

# Step 5: Install Azure Key Vault CSI Driver
echo -e "\n${YELLOW}Step 5: Installing Azure Key Vault CSI Driver${NC}"
helm repo add csi-secrets-store-provider-azure https://azure.github.io/secrets-store-csi-driver-provider-azure/charts
helm repo update
helm upgrade --install csi-secrets-store-provider-azure/csi-secrets-store-provider-azure \
  --namespace kube-system \
  --set secrets-store-csi-driver.syncSecret.enabled=true

echo -e "${GREEN}✓ Key Vault CSI Driver installed${NC}"

# Step 6: Deploy Kubernetes Resources
echo -e "\n${YELLOW}Step 6: Deploying Kubernetes Resources${NC}"

# Create namespace
kubectl apply -f k8s/namespace.yaml

# Update ConfigMap and Secrets with actual values
echo "Please update k8s/configmap.yaml and k8s/secret.yaml with your Azure resource details"
echo "Press Enter when ready to continue..."
read

# Apply configurations
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/serviceaccount.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
kubectl apply -f k8s/networkpolicy.yaml
kubectl apply -f k8s/poddisruptionbudget.yaml

echo -e "${GREEN}✓ Kubernetes resources deployed${NC}"

# Step 7: Wait for Deployment
echo -e "\n${YELLOW}Step 7: Waiting for Deployment to be Ready${NC}"
kubectl wait --for=condition=available --timeout=300s deployment/rag-application -n rag-application

echo -e "${GREEN}✓ Deployment is ready${NC}"

# Step 8: Verify Deployment
echo -e "\n${YELLOW}Step 8: Verifying Deployment${NC}"
kubectl get pods -n rag-application
kubectl get svc -n rag-application

# Get service endpoint
SERVICE_IP=$(kubectl get svc rag-service -n rag-application -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
echo -e "\n${GREEN}Service endpoint: http://${SERVICE_IP}${NC}"

# Test health endpoint
echo -e "\n${YELLOW}Testing health endpoint...${NC}"
kubectl port-forward -n rag-application svc/rag-service 8080:80 &
PF_PID=$!
sleep 5
curl -f http://localhost:8080/health && echo -e "\n${GREEN}✓ Health check passed${NC}" || echo -e "\n${RED}✗ Health check failed${NC}"
kill $PF_PID

echo -e "\n${GREEN}=== Deployment Complete ===${NC}"
echo -e "Next steps:"
echo -e "1. Configure DNS for your domain"
echo -e "2. Apply ingress configuration: kubectl apply -f k8s/ingress.yaml"
echo -e "3. Test the API endpoints"
echo -e "4. Monitor logs: kubectl logs -f -n rag-application -l app=rag-application"
