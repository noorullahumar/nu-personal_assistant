"""
Email utilities for sending notifications
Location: backend/utils/email.py
"""
import os
import logging
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

logger = logging.getLogger(__name__)

# Email configuration (use environment variables)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "your-email@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "your-app-password")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USER)
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "AI Assistant Support")


async def send_password_reset_email(to_email: str, reset_token: str, user_name: str = "User") -> bool:
    """
    Send password reset email to user
    
    Args:
        to_email: Recipient email address
        reset_token: Password reset token
        user_name: User's name
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        # Create reset link (adjust URL as needed)
        reset_link = f"{os.getenv('FRONTEND_URL')}/frontend/reset_password.html?token={reset_token}"
        subject = "Password Reset Request"
        
        # HTML email template
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #3b82f6; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background: #f9fafb; }}
                .button {{
                    display: inline-block;
                    padding: 12px 24px;
                    background-color: #3b82f6;
                    color: white;
                    text-decoration: none;
                    border-radius: 6px;
                    margin: 20px 0;
                }}
                .footer {{ text-align: center; padding: 20px; font-size: 12px; color: #6b7280; }}
                .warning {{ color: #ef4444; font-size: 12px; margin-top: 10px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>Password Reset Request</h2>
                </div>
                <div class="content">
                    <p>Dear {user_name},</p>
                    <p>We received a request to reset your password. Click the button below to create a new password:</p>
                    
                    <div style="text-align: center;">
                        <a href="{reset_link}" class="button">Reset Password</a>
                    </div>
                    
                    <p>If the button doesn't work, copy and paste this link into your browser:</p>
                    <p style="background: #e5e7eb; padding: 10px; border-radius: 5px; word-break: break-all;">
                        {reset_link}
                    </p>
                    
                    <p class="warning">This link will expire in 1 hour for security reasons.</p>
                    <p>If you didn't request this password reset, please ignore this email or contact support.</p>
                    
                    <p>Best regards,<br>{SMTP_FROM_NAME} Team</p>
                </div>
                <div class="footer">
                    <p>This is an automated message. Please do not reply to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        text_content = f"""
        Password Reset Request
        
        Dear {user_name},
        
        We received a request to reset your password. Click the link below to create a new password:
        
        {reset_link}
        
        This link will expire in 1 hour for security reasons.
        
        If you didn't request this password reset, please ignore this email or contact support.
        
        Best regards,
        {SMTP_FROM_NAME} Team
        
        This is an automated message. Please do not reply to this email.
        """
        
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
        msg["To"] = to_email
        
        # Attach parts
        part1 = MIMEText(text_content, "plain")
        part2 = MIMEText(html_content, "html")
        msg.attach(part1)
        msg.attach(part2)
        
        # Send email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        logger.info(f"Password reset email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send password reset email to {to_email}: {str(e)}")
        return False


async def send_password_changed_email(to_email: str, user_name: str = "User") -> bool:
    """
    Send confirmation email that password has been changed
    
    Args:
        to_email: Recipient email address
        user_name: User's name
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        subject = "Your Password Has Been Changed"
        
        # HTML email template
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #10b981; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background: #f9fafb; }}
                .footer {{ text-align: center; padding: 20px; font-size: 12px; color: #6b7280; }}
                .warning {{ color: #ef4444; font-size: 12px; margin-top: 10px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>Password Changed Successfully</h2>
                </div>
                <div class="content">
                    <p>Dear {user_name},</p>
                    <p>Your password has been successfully changed.</p>
                    
                    <p>If you made this change, you can safely ignore this email.</p>
                    
                    <p class="warning">If you did NOT change your password, please contact support immediately as your account may be compromised.</p>
                    
                    <p>Best regards,<br>{SMTP_FROM_NAME} Team</p>
                </div>
                <div class="footer">
                    <p>This is an automated message. Please do not reply to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        text_content = f"""
        Password Changed Successfully
        
        Dear {user_name},
        
        Your password has been successfully changed.
        
        If you made this change, you can safely ignore this email.
        
        If you did NOT change your password, please contact support immediately as your account may be compromised.
        
        Best regards,
        {SMTP_FROM_NAME} Team
        
        This is an automated message. Please do not reply to this email.
        """
        
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
        msg["To"] = to_email
        
        # Attach parts
        part1 = MIMEText(text_content, "plain")
        part2 = MIMEText(html_content, "html")
        msg.attach(part1)
        msg.attach(part2)
        
        # Send email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        logger.info(f"Password changed confirmation email sent to {to_email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send password changed email to {to_email}: {str(e)}")
        return False


async def send_reply_email(
    to_email: str,
    user_name: str,
    original_message: str,
    reply_message: str,
    admin_name: str = "Admin"
) -> bool:
    """
    Send a reply email to the user who submitted a contact form
    
    Args:
        to_email: Recipient email address
        user_name: User's name
        original_message: Original message from user
        reply_message: Admin's reply message
        admin_name: Name of admin who replied
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        subject = f"Reply to your inquiry"
        
        # HTML email template
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: #3b82f6; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; background: #f9fafb; }}
                .original-message {{ background: #e5e7eb; padding: 15px; border-radius: 8px; margin: 15px 0; }}
                .reply-message {{ background: #dbeafe; padding: 15px; border-radius: 8px; margin: 15px 0; border-left: 4px solid #3b82f6; }}
                .footer {{ text-align: center; padding: 20px; font-size: 12px; color: #6b7280; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>Reply from Support Team</h2>
                </div>
                <div class="content">
                    <p>Dear {user_name},</p>
                    <p>Thank you for contacting us. Here's our response to your inquiry:</p>
                    
                    <div class="reply-message">
                        <strong>Our Reply:</strong><br>
                        {reply_message.replace(chr(10), '<br>')}
                    </div>
                    
                    <div class="original-message">
                        <strong>Your Original Message:</strong><br>
                        {original_message.replace(chr(10), '<br>')}
                    </div>
                    
                    <p>If you have any further questions, please don't hesitate to contact us again.</p>
                    <p>Best regards,<br>{admin_name}<br>{SMTP_FROM_NAME} Team</p>
                </div>
                <div class="footer">
                    <p>This is an automated response. Please do not reply directly to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        text_content = f"""
        Reply from Support Team
        
        Dear {user_name},
        
        Thank you for contacting us. Here's our response to your inquiry:
        
        OUR REPLY:
        {reply_message}
        
        YOUR ORIGINAL MESSAGE:
        {original_message}
        
        Best regards,
        {admin_name}
        {SMTP_FROM_NAME} Team
        
        This is an automated response. Please do not reply directly to this email.
        """
        
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
        msg["To"] = to_email
        
        # Attach parts
        part1 = MIMEText(text_content, "plain")
        part2 = MIMEText(html_content, "html")
        msg.attach(part1)
        msg.attach(part2)
        
        # Send email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        logger.info(f"Reply email sent successfully to {to_email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send reply email to {to_email}: {str(e)}")
        return False


async def send_contact_notification_email(
    user_email: str,
    subject: str
) -> bool:
    """Send notification to admin about new contact form submission"""
    try:
        msg = MIMEText(f"New contact form submission from {user_email}\nSubject: {subject}")
        msg["Subject"] = f"New Contact Form: {subject}"
        msg["From"] = SMTP_FROM_EMAIL
        msg["To"] = SMTP_USER  # Send to admin
        
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        return True
    except Exception as e:
        logger.error(f"Failed to send notification email: {str(e)}")
        return False