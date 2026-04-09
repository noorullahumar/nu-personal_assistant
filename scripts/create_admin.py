#!/usr/bin/env python3
"""
Secure admin user creation script
Run: python scripts/create_admin.py
Location: scripts/create_admin.py
"""
import asyncio
import secrets
import sys
import os
from datetime import datetime
from getpass import getpass  # For hidden password input

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database.mongodb import init_database, user_collection
from backend.core.security import get_password_hash  # Fixed import


def validate_password_strength(password: str):
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if len(password) > 128:
        return False, "Password must be less than 128 characters"
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number"
    return True, "Password is strong"


async def create_admin_user():
    """Create admin user interactively with secure password"""
    
    print("\n" + "="*50)
    print("🔐 ADMIN USER CREATION")
    print("="*50)
    
    # Initialize database
    print("\n📡 Connecting to database...")
    await init_database()
    print("✅ Database connected")
    
    # Check if admin already exists
    existing_admin = await user_collection.find_one({"role": "admin"})
    
    if existing_admin:
        print(f"\n⚠️ Admin user already exists:")
        print(f"   Email: {existing_admin['email']}")
        print(f"   Username: {existing_admin.get('username', 'Unknown')}")
        
        response = input("\nDo you want to create another admin? (y/N): ").lower()
        if response != 'y':
            print("Exiting...")
            return
    
    # Get admin email
    while True:
        email = input("\nAdmin Email: ").strip().lower()
        if email and '@' in email:
            # Check if email already exists
            existing_user = await user_collection.find_one({"email": email})
            if existing_user:
                print(f"❌ Email {email} already exists. Use a different email.")
                continue
            break
        print("❌ Please enter a valid email address")
    
    # Get admin username
    while True:
        username = input("Admin Username: ").strip()
        if username:
            # Check if username already exists
            existing_user = await user_collection.find_one({"username": username})
            if existing_user:
                print(f"❌ Username {username} already exists. Choose another.")
                continue
            break
        print("❌ Username cannot be empty")
    
    # Generate or set password
    print("\n" + "-"*30)
    print("Password Options:")
    print("1. Generate secure random password")
    print("2. Enter custom password")
    
    choice = input("Choose (1/2): ").strip()
    
    if choice == "1":
        # Generate secure random password
        password = secrets.token_urlsafe(12)
        print("\n" + "!"*50)
        print(f"🔑 GENERATED PASSWORD: {password}")
        print("!"*50)
        print("\n⚠️ SAVE THIS PASSWORD NOW! It won't be shown again.")
        
        # Force confirmation
        confirm_saved = input("\nType 'SAVE' to confirm you have saved the password: ").upper()
        if confirm_saved != 'SAVE':
            print("❌ Password not saved. Exiting for security.")
            return
        
        # Ask user to re-enter for verification
        print("\nPlease re-enter the generated password to verify:")
        verify_password = getpass("Password: ")
        if verify_password != password:
            print("❌ Password verification failed. Exiting.")
            return
            
    else:
        # Custom password with validation
        while True:
            print("\nPassword requirements:")
            print("- Minimum 8 characters")
            print("- At least 1 uppercase letter")
            print("- At least 1 lowercase letter")
            print("- At least 1 number")
            
            password = getpass("Enter password: ")
            is_valid, error = validate_password_strength(password)
            
            if is_valid:
                confirm = getpass("Confirm password: ")
                if password == confirm:
                    break
                else:
                    print("❌ Passwords do not match")
            else:
                print(f"❌ {error}")
    
    # Create admin user - FIXED: Use get_password_hash instead of hash_password
    user_id = secrets.token_urlsafe(16)
    hashed_password = get_password_hash(password)  # Fixed function name
    
    admin_user = {
        "user_id": user_id,
        "username": username,
        "email": email,
        "hashed_password": hashed_password,  # Store hashed password
        "role": "admin",
        "created_at": datetime.utcnow(),  # Fixed datetime import
        "is_active": True,
        "is_verified": True,
        "failed_login_attempts": 0,
        "last_login": None
    }
    
    try:
        result = await user_collection.insert_one(admin_user)
        
        # Create index for email if not exists
        await user_collection.create_index("email", unique=True)
        
        print("\n" + "="*50)
        print("✅ ADMIN USER CREATED SUCCESSFULLY!")
        print("="*50)
        print(f"   User ID: {user_id}")
        print(f"   Email: {email}")
        print(f"   Username: {username}")
        print(f"   Role: Admin")
        print(f"   Created: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if choice == "1":
            print(f"\n🔑 PASSWORD: {password}")
            print("⚠️ Make sure you have saved this password!")
        
        print("\n📝 You can now login to the admin panel")
        
    except Exception as e:
        print(f"\n❌ Failed to create admin: {e}")
        return
    
    print("\n" + "="*50)
    print("Admin setup complete!")
    print("="*50)


async def list_admins():
    """List all admin users"""
    await init_database()
    
    admins = await user_collection.find({"role": "admin"}).to_list(length=100)
    
    print("\n" + "="*50)
    print("👥 ADMIN USERS LIST")
    print("="*50)
    
    if not admins:
        print("No admin users found")
    else:
        for admin in admins:
            print(f"\n📧 Email: {admin['email']}")
            print(f"👤 Username: {admin.get('username', 'N/A')}")
            print(f"🆔 User ID: {admin['user_id']}")
            print(f"📅 Created: {admin.get('created_at', 'Unknown')}")
            print(f"🔒 Verified: {admin.get('is_verified', False)}")
            print("-" * 30)
    
    print(f"\nTotal: {len(admins)} admin(s)")


async def delete_admin():
    """Delete an admin user"""
    await init_database()
    
    email = input("\nEnter admin email to delete: ").strip().lower()
    
    # Check if it's the last admin
    admin_count = await user_collection.count_documents({"role": "admin"})
    
    if admin_count <= 1:
        print("❌ Cannot delete the last admin user. At least one admin must exist.")
        return
    
    result = await user_collection.delete_one({"email": email, "role": "admin"})
    
    if result.deleted_count > 0:
        print(f"✅ Admin {email} deleted successfully")
    else:
        print(f"❌ Admin {email} not found")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--list":
            asyncio.run(list_admins())
        elif sys.argv[1] == "--delete":
            asyncio.run(delete_admin())
        else:
            print("Usage:")
            print("  python scripts/create_admin.py           # Create admin")
            print("  python scripts/create_admin.py --list    # List admins")
            print("  python scripts/create_admin.py --delete  # Delete admin")
    else:
        asyncio.run(create_admin_user())