#!/bin/bash
# =============================================================================
# Secure Database Backup Script for NU AI Assistant
# =============================================================================
# Features:
#   - Encrypted backups (AES-256)
#   - Automatic rotation (keeps last 7 days, 4 weeks, 12 months)
#   - S3/Cloud storage upload support
#   - Health check notifications
#   - Concurrent backup locking
#   - Integrity verification
# =============================================================================

set -euo pipefail  # Strict mode: exit on error, undefined vars, pipe failures

# =============================================================================
# CONFIGURATION - Load from environment or set defaults
# =============================================================================

# Backup directories
BACKUP_BASE_DIR="${BACKUP_BASE_DIR:-/backups}"
BACKUP_TEMP_DIR="${BACKUP_TEMP_DIR:-/tmp/mongodb_backup}"
LOG_FILE="${BACKUP_BASE_DIR}/backup.log"

# Retention periods (in days)
RETENTION_DAILY=7      # Keep daily backups for 7 days
RETENTION_WEEKLY=28     # Keep weekly backups for 4 weeks
RETENTION_MONTHLY=365   # Keep monthly backups for 1 year

# MongoDB configuration
MONGO_CONTAINER_NAME="${MONGO_CONTAINER_NAME:-nu-ai-mongodb}"
MONGO_USER="${MONGO_ROOT_USER:-admin}"
MONGO_PASSWORD="${MONGO_ROOT_PASSWORD:-}"
MONGO_DATABASE="${MONGO_DATABASE:-nu_ai_db}"
MONGO_AUTH_DB="${MONGO_AUTH_DB:-admin}"

# Encryption (REQUIRED for production)
BACKUP_ENCRYPTION_KEY="${BACKUP_ENCRYPTION_KEY:-}"
BACKUP_ENCRYPTION_ENABLED="${BACKUP_ENCRYPTION_ENABLED:-true}"

# Cloud storage (optional)
AWS_S3_BUCKET="${AWS_S3_BUCKET:-}"
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-}"
AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-}"

# Notifications (optional)
SLACK_WEBHOOK_URL="${SLACK_WEBHOOK_URL:-}"
HEALTHCHECKS_IO_URL="${HEALTHCHECKS_IO_URL:-}"

# Backup naming
BACKUP_PREFIX="${BACKUP_PREFIX:-nu_ai_backup}"
TIMEZONE="${TIMEZONE:-UTC}"

# =============================================================================
# COLOR OUTPUT FOR LOGGING
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =============================================================================
# LOGGING FUNCTIONS
# =============================================================================

log_info() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] [INFO]${NC} $1" | tee -a "$LOG_FILE"
}

log_warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] [WARN]${NC} $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

log_debug() {
    if [[ "${DEBUG:-false}" == "true" ]]; then
        echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')] [DEBUG]${NC} $1" | tee -a "$LOG_FILE"
    fi
}

# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

validate_encryption() {
    if [[ "${BACKUP_ENCRYPTION_ENABLED}" == "true" ]]; then
        if [[ -z "${BACKUP_ENCRYPTION_KEY}" ]]; then
            log_error "BACKUP_ENCRYPTION_KEY is required when encryption is enabled"
            log_error "Generate a key with: openssl rand -base64 32"
            exit 1
        fi
        
        # Check key length (should be 32 bytes base64 = 44 chars)
        KEY_LENGTH=${#BACKUP_ENCRYPTION_KEY}
        if [[ $KEY_LENGTH -lt 32 ]]; then
            log_error "BACKUP_ENCRYPTION_KEY is too short. Minimum 32 characters."
            exit 1
        fi
        
        log_info "✓ Encryption validation passed"
    fi
}

validate_mongodb_connection() {
    log_info "Validating MongoDB connection..."
    
    if ! docker ps --format '{{.Names}}' | grep -q "^${MONGO_CONTAINER_NAME}$"; then
        log_error "MongoDB container '${MONGO_CONTAINER_NAME}' is not running"
        exit 1
    fi
    
    # Test connection
    if ! docker exec "${MONGO_CONTAINER_NAME}" mongosh \
        --username "${MONGO_USER}" \
        --password "${MONGO_PASSWORD}" \
        --authenticationDatabase "${MONGO_AUTH_DB}" \
        --eval "db.runCommand({ping:1})" &>/dev/null; then
        log_error "Cannot connect to MongoDB. Check credentials."
        exit 1
    fi
    
    log_info "✓ MongoDB connection validated"
}

validate_directories() {
    # Create backup directories
    mkdir -p "${BACKUP_BASE_DIR}"
    mkdir -p "${BACKUP_TEMP_DIR}"
    mkdir -p "${BACKUP_BASE_DIR}/daily"
    mkdir -p "${BACKUP_BASE_DIR}/weekly"
    mkdir -p "${BACKUP_BASE_DIR}/monthly"
    
    # Set secure permissions (only owner can read/write)
    chmod 750 "${BACKUP_BASE_DIR}"
    chmod 750 "${BACKUP_TEMP_DIR}"
    
    log_info "✓ Directory structure validated"
}

# =============================================================================
# ENCRYPTION FUNCTIONS
# =============================================================================

encrypt_file() {
    local input_file="$1"
    local output_file="$2"
    
    if [[ "${BACKUP_ENCRYPTION_ENABLED}" != "true" ]]; then
        cp "${input_file}" "${output_file}"
        return 0
    fi
    
    log_debug "Encrypting: ${input_file}"
    
    # Use OpenSSL AES-256-CBC for encryption
    # -salt: Add salt to encryption
    # -pbkdf2: Use PBKDF2 key derivation (more secure)
    # -iter 100000: Number of iterations for key derivation
    if openssl enc -aes-256-cbc -salt -pbkdf2 -iter 100000 \
        -in "${input_file}" \
        -out "${output_file}" \
        -pass "pass:${BACKUP_ENCRYPTION_KEY}" 2>/dev/null; then
        log_debug "✓ Encryption successful: ${output_file}"
        return 0
    else
        log_error "Encryption failed for: ${input_file}"
        return 1
    fi
}

decrypt_file() {
    local input_file="$1"
    local output_file="$2"
    
    openssl enc -d -aes-256-cbc -pbkdf2 -iter 100000 \
        -in "${input_file}" \
        -out "${output_file}" \
        -pass "pass:${BACKUP_ENCRYPTION_KEY}" 2>/dev/null
}

# =============================================================================
# BACKUP FUNCTIONS
# =============================================================================

create_backup() {
    local backup_type="$1"  # daily, weekly, monthly
    local timestamp=$(date '+%Y%m%d_%H%M%S')
    local backup_name="${BACKUP_PREFIX}_${backup_type}_${timestamp}"
    local backup_dir="${BACKUP_TEMP_DIR}/${backup_name}"
    local archive_file="${BACKUP_BASE_DIR}/${backup_type}/${backup_name}.tar.gz"
    local encrypted_file="${archive_file}.enc"
    
    log_info "=========================================="
    log_info "Starting ${backup_type^^} backup: ${backup_name}"
    log_info "=========================================="
    
    # Create temporary backup directory
    mkdir -p "${backup_dir}"
    
    # Perform mongodump
    log_info "Dumping database..."
    local dump_start=$(date +%s)
    
    if ! docker exec "${MONGO_CONTAINER_NAME}" mongodump \
        --username "${MONGO_USER}" \
        --password "${MONGO_PASSWORD}" \
        --authenticationDatabase "${MONGO_AUTH_DB}" \
        --db "${MONGO_DATABASE}" \
        --out "/data/backup/${backup_name}" 2>/dev/null; then
        log_error "mongodump failed"
        rm -rf "${backup_dir}"
        return 1
    fi
    
    # Copy backup from container to host
    log_info "Copying backup from container..."
    docker cp "${MONGO_CONTAINER_NAME}:/data/backup/${backup_name}/." "${backup_dir}/"
    
    # Clean up container temp files
    docker exec "${MONGO_CONTAINER_NAME}" rm -rf "/data/backup/${backup_name}"
    
    local dump_end=$(date +%s)
    local dump_duration=$((dump_end - dump_start))
    log_info "✓ Database dump completed in ${dump_duration} seconds"
    
    # Get backup size
    local backup_size=$(du -sh "${backup_dir}" | cut -f1)
    log_info "Backup size: ${backup_size}"
    
    # Create archive
    log_info "Creating archive..."
    local archive_start=$(date +%s)
    
    if ! tar -czf "${archive_file}" -C "${BACKUP_TEMP_DIR}" "${backup_name}" 2>/dev/null; then
        log_error "Failed to create archive"
        rm -rf "${backup_dir}"
        return 1
    fi
    
    local archive_end=$(date +%s)
    local archive_duration=$((archive_end - archive_start))
    log_info "✓ Archive created in ${archive_duration} seconds"
    
    # Encrypt archive
    if [[ "${BACKUP_ENCRYPTION_ENABLED}" == "true" ]]; then
        log_info "Encrypting archive..."
        if encrypt_file "${archive_file}" "${encrypted_file}"; then
            rm -f "${archive_file}"
            log_info "✓ Archive encrypted"
            FINAL_BACKUP_FILE="${encrypted_file}"
        else
            log_error "Encryption failed"
            rm -rf "${backup_dir}"
            rm -f "${archive_file}"
            return 1
        fi
    else
        FINAL_BACKUP_FILE="${archive_file}"
        log_warn "Backup NOT encrypted (encryption disabled)"
    fi
    
    # Create metadata file
    local metadata_file="${FINAL_BACKUP_FILE}.metadata"
    cat > "${metadata_file}" << EOF
{
  "backup_name": "${backup_name}",
  "backup_type": "${backup_type}",
  "timestamp": "${timestamp}",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "size_bytes": $(stat -f%z "${FINAL_BACKUP_FILE}" 2>/dev/null || stat -c%s "${FINAL_BACKUP_FILE}" 2>/dev/null || echo "0"),
  "size_human": "${backup_size}",
  "database": "${MONGO_DATABASE}",
  "encrypted": ${BACKUP_ENCRYPTION_ENABLED},
  "mongodb_version": "$(docker exec "${MONGO_CONTAINER_NAME}" mongod --version | head -1 | cut -d' ' -f3)",
  "backup_script_version": "1.0.0"
}
EOF
    
    log_info "✓ Metadata saved"
    
    # Verify backup integrity
    log_info "Verifying backup integrity..."
    if tar -tzf "${FINAL_BACKUP_FILE}" &>/dev/null; then
        log_info "✓ Backup integrity verified"
    else
        log_error "Backup integrity check FAILED"
        return 1
    fi
    
    # Clean up temp directory
    rm -rf "${backup_dir}"
    
    log_info "✓ Backup completed successfully: ${FINAL_BACKUP_FILE}"
    
    # Calculate checksum
    if command -v sha256sum &>/dev/null; then
        local checksum=$(sha256sum "${FINAL_BACKUP_FILE}" | cut -d' ' -f1)
        echo "${checksum}" > "${FINAL_BACKUP_FILE}.sha256"
        log_info "SHA256: ${checksum}"
    fi
    
    return 0
}

# =============================================================================
# RETENTION MANAGEMENT
# =============================================================================

rotate_backups() {
    log_info "Rotating old backups..."
    
    # Rotate daily backups
    if [[ -d "${BACKUP_BASE_DIR}/daily" ]]; then
        find "${BACKUP_BASE_DIR}/daily" -name "${BACKUP_PREFIX}_daily_*.tar.gz*" -type f -mtime +${RETENTION_DAILY} -delete
        log_info "✓ Cleaned daily backups older than ${RETENTION_DAILY} days"
    fi
    
    # Rotate weekly backups
    if [[ -d "${BACKUP_BASE_DIR}/weekly" ]]; then
        find "${BACKUP_BASE_DIR}/weekly" -name "${BACKUP_PREFIX}_weekly_*.tar.gz*" -type f -mtime +${RETENTION_WEEKLY} -delete
        log_info "✓ Cleaned weekly backups older than ${RETENTION_WEEKLY} days"
    fi
    
    # Rotate monthly backups
    if [[ -d "${BACKUP_BASE_DIR}/monthly" ]]; then
        find "${BACKUP_BASE_DIR}/monthly" -name "${BACKUP_PREFIX}_monthly_*.tar.gz*" -type f -mtime +${RETENTION_MONTHLY} -delete
        log_info "✓ Cleaned monthly backups older than ${RETENTION_MONTHLY} days"
    fi
}

# =============================================================================
# CLOUD UPLOAD (AWS S3)
# =============================================================================

upload_to_s3() {
    local backup_file="$1"
    
    if [[ -z "${AWS_S3_BUCKET}" ]]; then
        log_debug "AWS_S3_BUCKET not set, skipping S3 upload"
        return 0
    fi
    
    log_info "Uploading to S3: ${AWS_S3_BUCKET}"
    
    # Check if AWS CLI is installed
    if ! command -v aws &>/dev/null; then
        log_warn "AWS CLI not installed, skipping S3 upload"
        return 0
    fi
    
    # Configure AWS credentials if provided
    if [[ -n "${AWS_ACCESS_KEY_ID}" ]] && [[ -n "${AWS_SECRET_ACCESS_KEY}" ]]; then
        export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID}"
        export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY}"
        export AWS_DEFAULT_REGION="${AWS_REGION}"
    fi
    
    local backup_filename=$(basename "${backup_file}")
    local s3_key="backups/$(date +%Y/%m/%d)/${backup_filename}"
    
    if aws s3 cp "${backup_file}" "s3://${AWS_S3_BUCKET}/${s3_key}" --only-show-errors; then
        log_info "✓ Uploaded to S3: s3://${AWS_S3_BUCKET}/${s3_key}"
        
        # Upload metadata and checksum
        if [[ -f "${backup_file}.metadata" ]]; then
            aws s3 cp "${backup_file}.metadata" "s3://${AWS_S3_BUCKET}/${s3_key}.metadata" --only-show-errors
        fi
        if [[ -f "${backup_file}.sha256" ]]; then
            aws s3 cp "${backup_file}.sha256" "s3://${AWS_S3_BUCKET}/${s3_key}.sha256" --only-show-errors
        fi
    else
        log_error "Failed to upload to S3"
        return 1
    fi
}

# =============================================================================
# NOTIFICATIONS
# =============================================================================

send_slack_notification() {
    local status="$1"
    local message="$2"
    local backup_file="$3"
    
    if [[ -z "${SLACK_WEBHOOK_URL}" ]]; then
        return 0
    fi
    
    local color="good"
    if [[ "${status}" == "failed" ]]; then
        color="danger"
    fi
    
    local payload=$(cat <<EOF
{
  "attachments": [{
    "color": "${color}",
    "title": "Database Backup ${status^^}",
    "text": "${message}",
    "fields": [
      {"title": "Backup File", "value": "${backup_file}", "short": false},
      {"title": "Environment", "value": "${ENVIRONMENT:-production}", "short": true},
      {"title": "Server", "value": "$(hostname)", "short": true}
    ],
    "footer": "NU AI Backup System",
    "ts": $(date +%s)
  }]
}
EOF
)
    
    curl -s -X POST -H 'Content-type: application/json' --data "${payload}" "${SLACK_WEBHOOK_URL}" &>/dev/null
}

send_healthcheck() {
    local status="$1"
    
    if [[ -z "${HEALTHCHECKS_IO_URL}" ]]; then
        return 0
    fi
    
    if [[ "${status}" == "success" ]]; then
        curl -fsS -m 10 --retry 5 -o /dev/null "${HEALTHCHECKS_IO_URL}" &>/dev/null
    else
        curl -fsS -m 10 --retry 5 -o /dev/null "${HEALTHCHECKS_IO_URL}/fail" &>/dev/null
    fi
}

# =============================================================================
# LOCKING MECHANISM (Prevent concurrent backups)
# =============================================================================

LOCK_FILE="/tmp/backup_db.lock"
LOCK_FD=200

acquire_lock() {
    # Create lock file if it doesn't exist
    touch "${LOCK_FILE}"
    
    # Try to acquire lock
    (
        flock -n ${LOCK_FD} || {
            log_error "Another backup process is already running"
            exit 1
        }
    ) {LOCK_FD}<"${LOCK_FILE}"
    
    log_debug "Lock acquired"
}

release_lock() {
    (
        flock -u ${LOCK_FD}
    ) {LOCK_FD}<"${LOCK_FILE}" 2>/dev/null || true
    log_debug "Lock released"
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

main() {
    local backup_type="${1:-daily}"
    local start_time=$(date +%s)
    local backup_status="success"
    local backup_file=""
    
    # Validate backup type
    if [[ ! "${backup_type}" =~ ^(daily|weekly|monthly)$ ]]; then
        echo "Usage: $0 {daily|weekly|monthly}"
        exit 1
    fi
    
    # Acquire lock to prevent concurrent backups
    acquire_lock
    
    # Trap to ensure lock is released on exit
    trap release_lock EXIT INT TERM
    
    # Validate configuration
    validate_directories
    validate_encryption
    validate_mongodb_connection
    
    # Create backup
    if create_backup "${backup_type}"; then
        backup_status="success"
        backup_file="${FINAL_BACKUP_FILE}"
        log_info "✅ Backup completed successfully"
    else
        backup_status="failed"
        log_error "❌ Backup failed"
    fi
    
    # Rotate old backups (only if backup was successful)
    if [[ "${backup_status}" == "success" ]]; then
        rotate_backups
        
        # Upload to cloud storage
        if [[ -n "${backup_file}" ]]; then
            upload_to_s3 "${backup_file}"
        fi
    fi
    
    # Calculate duration
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    local duration_min=$((duration / 60))
    local duration_sec=$((duration % 60))
    
    # Send notifications
    local message="Backup ${backup_type} completed in ${duration_min}m ${duration_sec}s"
    send_slack_notification "${backup_status}" "${message}" "${backup_file:-N/A}"
    send_healthcheck "${backup_status}"
    
    # Log completion
    log_info "=========================================="
    log_info "Backup ${backup_status} - Duration: ${duration_min}m ${duration_sec}s"
    log_info "=========================================="
    
    if [[ "${backup_status}" == "failed" ]]; then
        exit 1
    fi
}

# =============================================================================
# SCRIPT ENTRY POINT
# =============================================================================

# Check if running in test mode
if [[ "${TEST_MODE:-false}" == "true" ]]; then
    # Source the functions for testing
    return 0
fi

# Load environment variables from .env file if it exists
if [[ -f ".env" ]]; then
    set -a
    source .env
    set +a
fi

# Run main function
main "$@"